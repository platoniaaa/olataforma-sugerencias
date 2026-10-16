"""Fuentes de datos: de donde saca el motor cada archivo, que encontro y si esta bien.

Tres piezas:

1. **La configuracion** (`fuente_config`, append-only). La siembra copia lo que el
   motor usa hoy (`config_efectiva` de un reporte), deja el modo en `prueba` y fija
   el PC titular. Desde ahi un admin edita fuente por fuente con vista previa, y
   cada guardado es una version nueva (`base_version` vieja -> 409).
2. **Los reportes** (`motor_corrida`). El motor manda uno al partir y otro al
   terminar, con el mismo id (upsert portable: get y despues update, sin
   `ON CONFLICT`, porque los tests corren en SQLite).
3. **El semaforo** (`semaforo`, funcion pura) y el panel que lo arma. La edad de
   cada archivo se recalcula HOY en dias habiles, en hora de Chile.

Nada de esto pasa por `auditoria_log` (lo ve todo el que no es vendedor) ni por
`notificar()` sin `para_email` (le llegaria a todo el equipo): la regla del dueno es
que nada nuevo quede visible para el equipo. La unica salida hacia afuera es la
campanita PERSONAL a cada admin activo (aprobada el 16-10-2026), ver `_avisar_admins`.

El servicio no tiene ninguna clave de fuente escrita: todo se valida contra el
`catalogo` que declara el motor.
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import re
import unicodedata
from datetime import date, datetime, timedelta, timezone
from typing import Any

from pydantic import ValidationError
from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import FuenteConfig, MotorCorrida, Notificacion, Usuario
from ..schemas.fuentes import (
    CambiosCarpeta,
    CambiosFuente,
    CarpetaCfg,
    ConfigEfectiva,
    ConfigFuentes,
    FuenteCfg,
    PcCfg,
    ReporteIn,
)
from . import auditoria_service
from .calendario import (
    TZ_CHILE,
    a_chile,
    ahora_chile,
    dias_habiles_entre,
    inicio_del_dia_chile,
)

settings = get_settings()

# Corridas oficiales seguidas del PC titular, en verde y con la configuracion de la
# plataforma, que hacen falta para habilitar "Activar". Decision del dueno (16-10):
# 2 y no 3, para que quede funcionando antes.
CORRIDAS_PARA_ACTIVAR = 2

# Palabras que son rutas fijas del router: una fuente no se puede llamar asi, porque
# `/{clave}` va declarada despues y nunca la alcanzaria.
PALABRAS_RESERVADAS = frozenset({
    "config", "reporte", "corridas", "carpetas", "pcs", "titular", "modo",
    "sembrar", "revertir",
})

# Ademas de las rutas, una fuente no puede llamarse como una de las entradas de
# `claves_cambiadas` que no son fuentes: se mezclaria su historial.
_NOMBRES_PROHIBIDOS = PALABRAS_RESERVADAS | {"pc_titular"}

MODOS_CONOCIDOS = ("archivo_exacto", "mas_reciente", "por_descarte")
MAX_CARACTERES_PATRON = 100
# Un archivo que llega con menos de este porcentaje de las filas de la corrida
# anterior se da por incompleto (solo en las fuentes que lo controlan).
RATIO_FILAS_MINIMO = 0.6
# Una corrida que lleva mas que esto "en curso" se cayo sin avisar. Las del 14 al
# 16-10-2026 duraron 27 a 29 minutos.
MINUTOS_PARA_DAR_POR_CORTADA = 75
# Desde esta hora de Chile, un dia habil sin corrida oficial del titular es alarma.
HORA_LIMITE_CORRIDA = 11
# Igual que el motor: los dias 1 a 3 la falta del mes cerrado avisa; desde el 4 frena.
DIA_DESDE_QUE_FRENA_VENTAS = 4
# Prefijo del `tipo` de la notificacion. Despues de los dos puntos va el motivo, y
# eso es lo que limita la campanita a una por dia, por admin y por motivo.
TIPO_AVISO = "fuentes_datos"
MAX_CARACTERES_MOTIVO = 20000

MSG_OTRO_ADMIN = "Otro admin guardó un cambio; recarga"

_DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
_MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
          "septiembre", "octubre", "noviembre", "diciembre")
_SEVERIDAD = {"rojo": 0, "amarillo": 1, "gris": 2, "verde": 3}


class ConflictoFuentes(Exception):
    """Se responde 409: otro admin guardo antes, ya hay configuracion, o no se
    cumple la condicion para activar."""


class NoEncontrado(LookupError):
    """Se responde 404."""


# --------------------------------------------------------------------------- #
# Utilidades
# --------------------------------------------------------------------------- #
def _cargar(texto: str | None, defecto: Any) -> Any:
    if not texto:
        return defecto
    try:
        return json.loads(texto)
    except (ValueError, TypeError):
        return defecto


def _canonico(datos: dict) -> str:
    return json.dumps(datos, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                      default=str)


def hash_config(datos: dict) -> str:
    """sha256 del JSON canonico de la configuracion."""
    return hashlib.sha256(_canonico(datos).encode("utf-8")).hexdigest()


def _norm(s: str) -> str:
    """Minusculas y sin tildes, igual que `motor/fuentes.py::_norm`."""
    s = unicodedata.normalize("NFKD", (s or "").lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def _calza(nombre: str, patrones: list[str]) -> bool:
    n = _norm(nombre)
    # fnmatchcase y no fnmatch: fnmatch depende del sistema (en Windows ignora
    # mayusculas y en Linux no). Los dos lados ya van normalizados.
    return any(fnmatch.fnmatchcase(n, _norm(p.strip())) for p in patrones if p and p.strip())


def _matchea(nombre: str, incluye: list[str], excluye: list[str]) -> bool:
    """La misma regla del motor: descarta si calza con una exclusion; si no, basta
    que calce con un patron de los que incluye."""
    if _calza(nombre, excluye):
        return False
    return _calza(nombre, incluye)


def _utc(dt: datetime | None) -> datetime | None:
    """A UTC con zona. SQLite guarda las fechas sin zona: si no se pasan a UTC antes
    de guardar, una hora de Chile quedaria escrita como si fuera UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _utc_motor(dt: datetime | None) -> datetime | None:
    """Una hora que manda el motor. Sin zona es la hora local del PC (Chile), no UTC."""
    if dt is not None and dt.tzinfo is None:
        dt = dt.replace(tzinfo=TZ_CHILE)
    return _utc(dt)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _fecha_archivo(valor: Any) -> datetime | None:
    """`modificado_en` de un archivo (lo manda el motor). Sin zona se toma como hora
    de Chile: es la hora local del PC que lo leyo."""
    if valor is None or valor == "":
        return None
    if isinstance(valor, datetime):
        dt = valor
    else:
        try:
            dt = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TZ_CHILE)
    return dt.astimezone(TZ_CHILE)


def _ruta(valor: Any) -> str:
    return str(valor or "").replace("\\", "/").strip("/")


def _subcarpeta(valor: Any) -> str:
    """Como `_ruta`, pero sin quitar la "/" del inicio: esa se rechaza al validar."""
    return str(valor or "").replace("\\", "/").strip().rstrip("/")


def _entero(valor: Any) -> int | None:
    # El reporte se guarda suelto: un valor con otra forma se muestra vacio en vez
    # de botar la pantalla.
    if isinstance(valor, bool):
        return None
    if isinstance(valor, int):
        return valor
    if isinstance(valor, float) and valor.is_integer():
        return int(valor)
    return None


def _texto(valor: Any) -> str | None:
    return valor if isinstance(valor, str) else None


def _nombre_de(ruta_relativa: str) -> str:
    return _ruta(ruta_relativa).rsplit("/", 1)[-1]


def _miles(n: int | float) -> str:
    return f"{int(n):,}".replace(",", ".")


def _cuando(dt: datetime, ahora: datetime) -> str:
    """"hoy a las 09:34", "ayer a las 10:29", "el martes a las 09:30", "el 05-10 a las 09:30"."""
    d = dt.astimezone(TZ_CHILE)
    hoy = ahora.astimezone(TZ_CHILE).date()
    hora = d.strftime("%H:%M")
    dias = (hoy - d.date()).days
    if dias == 0:
        return f"hoy a las {hora}"
    if dias == 1:
        return f"ayer a las {hora}"
    if 1 < dias < 7:
        return f"el {_DIAS[d.weekday()]} a las {hora}"
    if d.year == hoy.year:
        return f"el {d:%d-%m} a las {hora}"
    return f"el {d:%d-%m-%Y} a las {hora}"


def _de(cuando: str) -> str:
    return "del " + cuando[3:] if cuando.startswith("el ") else "de " + cuando


def _fecha_corta(dt: datetime) -> str:
    d = a_chile(dt)
    return f"{d:%d-%m} a las {d:%H:%M}"


def _sujeto_pc(alias: str | None, pc: str | None, *, minuscula: bool = False) -> str:
    """"El PC de la jefa", o "El PC PC-ABAST-01" si no tiene alias. Con `minuscula`,
    para usarlo a mitad de frase ("el PC de la jefa")."""
    if alias:
        texto = "El " + alias if alias.lower().startswith("pc ") else alias
    else:
        texto = f"El PC {pc}" if pc else "El PC del motor"
    if minuscula and texto.startswith("El "):
        texto = "el " + texto[3:]
    return texto


def _reporte(corrida: MotorCorrida) -> dict:
    """El reporte de una corrida, leido una sola vez por objeto: el historial evalua
    13 fuentes por corrida contra su anterior, y sin esto cada consulta volvia a
    parsear el JSON entero. Se guarda junto al texto del que salio: si el reporte
    cambia, se vuelve a leer. Quien lo usa no lo modifica."""
    texto = corrida.reporte
    guardado = corrida.__dict__.get("_reporte_leido")
    if guardado is not None and guardado[0] is texto:
        return guardado[1]
    datos = _cargar(texto, {})
    datos = datos if isinstance(datos, dict) else {}
    corrida.__dict__["_reporte_leido"] = (texto, datos)
    return datos


def _fuentes_de(corrida: MotorCorrida) -> dict:
    f = _reporte(corrida).get("fuentes")
    return f if isinstance(f, dict) else {}


def _listados_de(corrida: MotorCorrida | None) -> dict[str, dict]:
    if corrida is None:
        return {}
    carpetas = _reporte(corrida).get("carpetas")
    if not isinstance(carpetas, list):
        return {}
    return {c["clave"]: c for c in carpetas if isinstance(c, dict) and c.get("clave")}


def _archivos_estado(estado: dict | None) -> list[dict]:
    if not estado:
        return []
    archivos = estado.get("archivos")
    return [a for a in archivos if isinstance(a, dict) and a.get("ruta_relativa")] \
        if isinstance(archivos, list) else []


def _mas_nuevo(archivos: list[dict]) -> dict | None:
    if not archivos:
        return None
    minimo = datetime.min.replace(tzinfo=TZ_CHILE)
    return max(archivos, key=lambda a: _fecha_archivo(a.get("modificado_en")) or minimo)


# --------------------------------------------------------------------------- #
# Configuracion vigente y versiones
# --------------------------------------------------------------------------- #
def _fila_vigente(db: Session) -> FuenteConfig | None:
    return db.scalars(
        select(FuenteConfig)
        .where(FuenteConfig.tenant_id == settings.default_tenant_id)
        .order_by(desc(FuenteConfig.version))
        .limit(1)
    ).first()


def _config_de(fila: FuenteConfig) -> ConfigFuentes:
    return ConfigFuentes.model_validate(_cargar(fila.config, {}))


def _dump(cfg: ConfigFuentes) -> dict:
    return cfg.model_dump(mode="json")


def _vigente_o_error(db: Session) -> tuple[FuenteConfig, ConfigFuentes]:
    fila = _fila_vigente(db)
    if fila is None:
        raise ValueError(
            "Todavía no hay configuración: primero usa la configuración de un PC como "
            "punto de partida."
        )
    return fila, _config_de(fila)


def _chequear_base(fila: FuenteConfig | None, base_version: int | None) -> None:
    actual = fila.version if fila else 0
    if base_version is not None and base_version != actual:
        raise ConflictoFuentes(MSG_OTRO_ADMIN)


def _claves_cambiadas(antes: dict | None, despues: dict) -> list[str]:
    """Que cambio entre dos configuraciones: claves de fuente, "carpeta:<clave>",
    "modo", "pc_titular", "pcs" y "catalogo:motor". Alimenta el historial por fuente.

    El catalogo lleva los dos puntos porque hay una FUENTE que se llama "catalogo"
    (el maestro de repuestos): sin ellos, su historial mostraria la siembra del
    catalogo del motor como si fuera un cambio suyo. Ninguna clave de fuente puede
    llevar ":" ni llamarse "modo", "pc_titular" o "pcs" (ver `_NOMBRES_PROHIBIDOS`)."""
    antes = antes or {}
    claves: list[str] = []
    for campo, nombre in (("modo", "modo"), ("pc_titular", "pc_titular"), ("pcs", "pcs"),
                          ("catalogo", "catalogo:motor")):
        if antes.get(campo) != despues.get(campo):
            claves.append(nombre)
    ca = {c.get("clave"): c for c in antes.get("carpetas") or []}
    cd = {c.get("clave"): c for c in despues.get("carpetas") or []}
    for k in list(cd) + [k for k in ca if k not in cd]:
        if ca.get(k) != cd.get(k):
            claves.append(f"carpeta:{k}")
    fa = {f.get("clave"): f for f in antes.get("fuentes") or []}
    fd = {f.get("clave"): f for f in despues.get("fuentes") or []}
    for k in list(fd) + [k for k in fa if k not in fd]:
        if fa.get(k) != fd.get(k):
            claves.append(k)
    return claves


def _guardar(
    db: Session,
    nueva: ConfigFuentes,
    *,
    antes: ConfigFuentes | None,
    usuario: str | None,
    nota: str,
    base_version: int | None,
    revierte_a: int | None = None,
    avisos: list[str] | None = None,
) -> dict:
    """Inserta la version siguiente. Un guardado sin cambios no crea version."""
    fila = _fila_vigente(db)
    _chequear_base(fila, base_version)
    datos = _dump(nueva)
    claves = _claves_cambiadas(_dump(antes) if antes else None, datos)
    if not claves:
        raise ValueError("No hay cambios para guardar.")
    version = (fila.version if fila else 0) + 1
    h = hash_config(datos)
    db.add(FuenteConfig(
        tenant_id=settings.default_tenant_id,
        version=version,
        config=_canonico(datos),
        hash=h,
        claves_cambiadas=json.dumps(claves, ensure_ascii=False),
        nota=nota.strip(),
        revierte_a=revierte_a,
        creado_por=usuario,
    ))
    try:
        db.commit()
    except IntegrityError:
        # Otro admin inserto la misma version entre la lectura y el commit.
        db.rollback()
        raise ConflictoFuentes(MSG_OTRO_ADMIN) from None
    return {"version": version, "modo": nueva.modo, "hash": h,
            "claves_cambiadas": claves, "avisos": avisos or []}


def _uso(catalogo: dict, clave: str) -> str:
    entrada = catalogo.get(clave) or {}
    return entrada.get("uso") or "lee"


def _obligatoria(fuente: dict, catalogo: dict) -> bool:
    return bool(fuente.get("obligatoria") or (catalogo.get(fuente.get("clave")) or {}).get("requerida"))


# --------------------------------------------------------------------------- #
# Lo que usa el motor
# --------------------------------------------------------------------------- #
def config_para_motor(db: Session) -> dict:
    """`GET /config`. Sin filas: `{"modo": "sin_configurar"}` y el motor sigue con su
    `.env`. `anterior` sale de la ultima corrida oficial `ok` del titular: con eso el
    motor detecta "mismo contenido que ayer" y la caida de filas."""
    fila = _fila_vigente(db)
    if fila is None:
        return {"modo": "sin_configurar"}
    cfg = _cargar(fila.config, {})
    return {
        "modo": cfg.get("modo", "prueba"),
        "version": fila.version,
        "hash": fila.hash,
        "pc_titular": cfg.get("pc_titular"),
        "pcs": cfg.get("pcs") or {},
        "catalogo": cfg.get("catalogo") or {},
        "carpetas": cfg.get("carpetas") or [],
        "fuentes": cfg.get("fuentes") or [],
        "anterior": _anterior(db, cfg.get("pc_titular")),
    }


def _anterior(db: Session, titular: str | None) -> dict:
    if not titular:
        return {}
    corrida = db.scalars(
        select(MotorCorrida)
        .where(
            MotorCorrida.tenant_id == settings.default_tenant_id,
            MotorCorrida.pc == titular,
            MotorCorrida.tipo == "oficial",
            MotorCorrida.resultado == "ok",
        )
        .order_by(desc(MotorCorrida.iniciada_en))
        .limit(1)
    ).first()
    if corrida is None:
        return {}
    salida: dict = {}
    for clave, estado in _fuentes_de(corrida).items():
        if not isinstance(estado, dict):
            continue
        archivos = _archivos_estado(estado)
        if not archivos:
            continue
        salida[clave] = {
            "sha256": archivos[0].get("sha256"),
            "modificado_en": archivos[0].get("modificado_en"),
            "filas": estado.get("filas"),
            "archivos": [
                {"ruta_relativa": a.get("ruta_relativa"), "sha256": a.get("sha256"),
                 "modificado_en": a.get("modificado_en")}
                for a in archivos
            ],
        }
    return salida


def registrar_reporte(db: Session, datos: ReporteIn, *, usuario: str | None) -> dict:
    """`POST /reporte`: upsert por id. Una clave de fuente desconocida se guarda con
    un aviso; nunca da error. Al recibir el fin de una corrida oficial, avisa a los
    admins por la campanita si corresponde."""
    avisos: list[str] = []
    reporte = datos.reporte.model_dump(mode="json") if datos.reporte is not None else None

    efectiva = datos.config_efectiva
    catalogo_efectivo: dict = {}
    if efectiva is not None:
        try:
            catalogo_efectivo = _dump_catalogo(ConfigEfectiva.model_validate(efectiva))
        except ValidationError:
            avisos.append("La configuración que mandó el motor no tiene la forma esperada: "
                          "se guardó, pero no se puede sembrar desde esta corrida.")

    if reporte is not None:
        fila_cfg = _fila_vigente(db)
        conocidas = set(catalogo_efectivo)
        if fila_cfg is not None:
            conocidas |= set((_cargar(fila_cfg.config, {}).get("catalogo") or {}))
        if conocidas:
            for clave in reporte.get("fuentes") or {}:
                if clave not in conocidas:
                    avisos.append(f"La fuente '{clave}' no está en el catálogo: se guardó igual.")
        reporte.setdefault("avisos", [])
        reporte["avisos"] = list(reporte["avisos"]) + [f"Plataforma: {a}" for a in avisos]

    fila = db.get(MotorCorrida, datos.id)
    if fila is not None and fila.tenant_id != settings.default_tenant_id:
        raise ValueError("Ese id de corrida ya existe en otra empresa.")
    if fila is None:
        fila = MotorCorrida(
            id=datos.id,
            tenant_id=settings.default_tenant_id,
            pc=datos.pc,
            tipo=datos.tipo,
            iniciada_en=_utc_motor(datos.iniciada_en) or _now(),
            resultado="en_curso",
            titular=False,
            publico=False,
        )
        db.add(fila)
    elif datos.fase == "inicio" and fila.resultado != "en_curso":
        # Un inicio que llega despues del fin (el motor reenvia lo pendiente): no
        # pisa el resultado ni el reporte final, solo completa lo que falte.
        if fila.config_efectiva is None and efectiva is not None:
            fila.config_efectiva = json.dumps(efectiva, ensure_ascii=False, default=str)
        fila.version_motor = fila.version_motor or datos.version_motor
        db.commit()
        return {"id": fila.id, "resultado": fila.resultado, "avisos": avisos, "notificados": 0}

    fila.pc = datos.pc
    fila.tipo = datos.tipo
    if datos.iniciada_en is not None:
        fila.iniciada_en = _utc_motor(datos.iniciada_en)
    for campo in ("titular", "publico", "config_origen", "config_version"):
        valor = getattr(datos, campo)
        if valor is not None:
            setattr(fila, campo, valor)
    if datos.version_motor is not None:
        fila.version_motor = datos.version_motor[:200]
    if datos.motivo is not None:
        fila.motivo = datos.motivo[:MAX_CARACTERES_MOTIVO]
    if reporte is not None:
        previo = _cargar(fila.reporte, None)
        if isinstance(previo, dict) and not reporte.get("fuentes") and not reporte.get("carpetas"):
            # Una corrida huerfana se reporta como `cortada` sin su manifiesto (el
            # proceso murio): no se borra lo que trajo el reporte de inicio.
            reporte = {**previo, **{k: v for k, v in reporte.items()
                                    if k not in ("fuentes", "carpetas")},
                       "fuentes": previo.get("fuentes") or {},
                       "carpetas": previo.get("carpetas") or [],
                       "avisos": list(previo.get("avisos") or []) + list(reporte.get("avisos") or [])}
        fila.reporte = json.dumps(reporte, ensure_ascii=False, default=str)
    if efectiva is not None:
        fila.config_efectiva = json.dumps(efectiva, ensure_ascii=False, default=str)
    if datos.fase == "fin":
        fila.resultado = datos.resultado
        # Una cortada no sabe cuando termino: queda sin hora en vez de con la del reenvio.
        fila.terminada_en = _utc_motor(datos.terminada_en) or (
            None if datos.resultado == "cortada" else _now())
    elif datos.resultado is not None:
        fila.resultado = datos.resultado
    fila.actualizado_en = _now()
    db.commit()

    notificados = 0
    if datos.fase == "fin" and fila.tipo == "oficial":
        notificados = _avisar_admins(db, fila, usuario)
    return {"id": fila.id, "resultado": fila.resultado, "avisos": avisos,
            "notificados": notificados}


def _dump_catalogo(efectiva: ConfigEfectiva) -> dict:
    return {k: v.model_dump(mode="json") for k, v in efectiva.catalogo.items()}


# --------------------------------------------------------------------------- #
# Siembra, modo, titular, alias, carpetas, fuentes, revertir
# --------------------------------------------------------------------------- #
_CLAVE_VALIDA = re.compile(r"[a-z0-9_]{1,60}")


def sembrar(db: Session, corrida_id: str, *, usuario: str | None, nota: str | None = None) -> dict:
    """Copia `config_efectiva` de una corrida (oficial o `probar`), deja el modo en
    prueba y fija como titular al PC de esa corrida. Con configuracion ya hecha, 409."""
    if _fila_vigente(db) is not None:
        raise ConflictoFuentes(
            "Ya hay una configuración guardada: no se puede volver a sembrar. "
            "Para volver atrás usa el historial de versiones."
        )
    corrida = db.get(MotorCorrida, corrida_id)
    if corrida is None or corrida.tenant_id != settings.default_tenant_id:
        raise NoEncontrado("No existe esa corrida.")
    efectiva = _cargar(corrida.config_efectiva, None)
    if not isinstance(efectiva, dict):
        raise ValueError("Esa corrida no trae la configuración del PC: elige otra.")
    try:
        ce = ConfigEfectiva.model_validate(efectiva)
    except ValidationError as e:
        raise ValueError(
            "La configuración de esa corrida no tiene la forma esperada "
            f"({e.error_count()} errores): elige otra corrida o actualiza el motor."
        ) from None
    if not ce.fuentes:
        raise ValueError("La configuración de esa corrida no trae ninguna fuente.")
    for f in ce.fuentes:
        if not _CLAVE_VALIDA.fullmatch(f.clave) or f.clave in _NOMBRES_PROHIBIDOS:
            raise ValueError(f"La fuente '{f.clave}' tiene un nombre que no se puede usar.")
    pcs = {k: PcCfg.model_validate(v) for k, v in (efectiva.get("pcs") or {}).items()
           if isinstance(v, dict)}
    # El motor siembra el alias con el mismo hostname: eso no es un nombre, y el
    # panel diria "PC-ABAST-01 no tiene esta carpeta" en vez de "El PC PC-ABAST-01...".
    for host, p in list(pcs.items()):
        if (p.alias or "").strip() == host:
            pcs[host] = p.model_copy(update={"alias": None})
    pcs.setdefault(corrida.pc, PcCfg(alias=None))
    cfg = ConfigFuentes(
        modo="prueba",
        pc_titular=corrida.pc,
        pcs=pcs,
        catalogo=ce.catalogo,
        carpetas=ce.carpetas,
        fuentes=ce.fuentes,
    )
    fecha = _fecha_corta(corrida.iniciada_en)
    return _guardar(
        db, cfg, antes=None, usuario=usuario, base_version=0,
        nota=(nota or "").strip() or f"Configuración inicial copiada del PC {corrida.pc} "
                                      f"(corrida del {fecha}).",
    )


def cambiar_modo(db: Session, modo: str, *, nota: str, base_version: int,
                 usuario: str | None) -> dict:
    """Prueba <-> activa. Activar exige la condicion de `condicion_activar`; si no se
    cumple, 409 con el motivo. Rige desde la corrida siguiente."""
    fila, cfg = _vigente_o_error(db)
    _chequear_base(fila, base_version)
    if cfg.modo == modo:
        raise ValueError(f"La configuración ya está en modo {modo}.")
    if modo == "activa":
        ok, motivo, _ = condicion_activar(db, fila, cfg)
        if not ok:
            raise ConflictoFuentes(motivo)
    nueva = cfg.model_copy(update={"modo": modo})
    return _guardar(db, nueva, antes=cfg, usuario=usuario, nota=nota, base_version=base_version)


def _pcs_que_reportaron(db: Session) -> set[str]:
    return set(db.scalars(
        select(MotorCorrida.pc).where(MotorCorrida.tenant_id == settings.default_tenant_id)
        .distinct()
    ).all())


def cambiar_titular(db: Session, pc: str, *, nota: str, base_version: int,
                    usuario: str | None) -> dict:
    """Solo acepta un PC que ya reporto alguna corrida (aunque sea un `--probar`)."""
    fila, cfg = _vigente_o_error(db)
    _chequear_base(fila, base_version)
    pc = pc.strip()
    if pc not in _pcs_que_reportaron(db):
        raise ValueError(
            f"El PC {pc} todavía no ha reportado ninguna corrida: no puede ser el titular. "
            "Corre una vez el motor en modo revisión (--probar --reportar) en ese PC."
        )
    if cfg.pc_titular == pc:
        raise ValueError(f"El PC {pc} ya es el titular.")
    pcs = dict(cfg.pcs)
    pcs.setdefault(pc, PcCfg(alias=None))
    nueva = cfg.model_copy(update={"pc_titular": pc, "pcs": pcs})
    return _guardar(db, nueva, antes=cfg, usuario=usuario, nota=nota, base_version=base_version)


def cambiar_alias(db: Session, hostname: str, alias: str, *, nota: str | None,
                  base_version: int, usuario: str | None) -> dict:
    fila, cfg = _vigente_o_error(db)
    _chequear_base(fila, base_version)
    if hostname not in cfg.pcs and hostname not in _pcs_que_reportaron(db):
        raise NoEncontrado(f"El PC {hostname} no ha reportado ninguna corrida.")
    pcs = dict(cfg.pcs)
    anterior = pcs.get(hostname) or PcCfg(alias=None)
    pcs[hostname] = anterior.model_copy(update={"alias": alias.strip()})
    nueva = cfg.model_copy(update={"pcs": pcs})
    return _guardar(db, nueva, antes=cfg, usuario=usuario, base_version=base_version,
                    nota=(nota or "").strip() or f"Nombre del PC {hostname}: {alias.strip()}")


# ---- validaciones ---------------------------------------------------------- #
_LETRA_UNIDAD = re.compile(r"^[A-Za-z]:")
_EXTENSION = re.compile(r"\.[a-z0-9]{1,10}")
_SITIO_SHAREPOINT = re.compile(r"https://[A-Za-z0-9-]+\.sharepoint\.com/sites/[^/\s?#]+.*")


def _validar_patron(p: str, que: str) -> None:
    p = (p or "").strip()
    if not p:
        raise ValueError(f"{que} está vacío.")
    if len(p) > MAX_CARACTERES_PATRON:
        raise ValueError(f"{que} '{p[:30]}…' pasa de {MAX_CARACTERES_PATRON} caracteres.")
    if "/" in p or "\\" in p or ".." in p or _LETRA_UNIDAD.match(p):
        raise ValueError(
            f"{que} '{p}' no puede llevar /, \\, .. ni una letra de unidad: es solo el "
            "nombre del archivo, la carpeta se elige aparte."
        )


def _validar_subcarpeta(s: str) -> None:
    if not s:
        return
    if len(s) > MAX_CARACTERES_PATRON:
        raise ValueError(f"La subcarpeta '{s[:30]}…' pasa de {MAX_CARACTERES_PATRON} caracteres.")
    if s.startswith("/") or _LETRA_UNIDAD.match(s):
        raise ValueError(f"La subcarpeta '{s}' tiene que ser relativa a la carpeta: sin / al "
                         "inicio ni letra de unidad.")
    partes = s.split("/")
    if any(p.strip() in ("", "..", ".") for p in partes):
        raise ValueError(f"La subcarpeta '{s}' no es válida: no puede llevar .. ni partes vacías.")


def _validar_ruta_carpeta(ruta: str, que: str) -> None:
    if not ruta:
        raise ValueError(f"{que}: falta la ruta (al menos una carpeta, por ejemplo "
                         "'Documentos/Bases de datos').")
    if len(ruta) > 300:
        raise ValueError(f"{que}: la ruta pasa de 300 caracteres.")
    if _LETRA_UNIDAD.match(ruta) or any(p.strip() in ("", "..", ".") for p in ruta.split("/")):
        raise ValueError(f"{que}: la ruta '{ruta}' tiene que ser relativa a OneDrive, sin letra "
                         "de unidad ni '..'.")


def _validar_fuente(f: FuenteCfg, cfg: ConfigFuentes) -> None:
    """Las validaciones de §3.3: todas contra el catalogo, sin claves a mano."""
    cat = cfg.catalogo.get(f.clave)
    if cat is None:
        raise ValueError(f"La fuente '{f.clave}' no está en el catálogo del motor.")
    nombre = f.nombre or f.clave
    if f.modo not in MODOS_CONOCIDOS or f.modo not in cat.modos:
        raise ValueError(f"{nombre}: esa forma de elegir el archivo no está permitida para esta "
                         "fuente.")
    if f.modo == "archivo_exacto":
        if not (f.nombre_archivo or "").strip():
            raise ValueError(f"{nombre}: falta el nombre del archivo.")
        _validar_patron(f.nombre_archivo, "El nombre del archivo")
    if f.modo == "mas_reciente" and not [p for p in f.incluye if p and p.strip()]:
        raise ValueError(f"{nombre}: falta al menos un texto que tenga que contener el nombre "
                         "del archivo.")
    for p in f.incluye:
        _validar_patron(p, "El patrón")
    for p in f.excluye:
        _validar_patron(p, "La exclusión")
    if not f.extensiones:
        raise ValueError(f"{nombre}: indica al menos una extensión de archivo (.xlsx, .csv…).")
    for e in f.extensiones:
        if not _EXTENSION.fullmatch((e or "").strip().lower()):
            raise ValueError(f"{nombre}: la extensión '{e}' no es válida (por ejemplo, .xlsx).")
    carpetas = {c.clave: c for c in cfg.carpetas}
    for u in f.ubicaciones:
        c = carpetas.get(u.carpeta)
        if c is None:
            raise ValueError(f"{nombre}: la carpeta '{u.carpeta}' no existe.")
        if not c.activa:
            raise ValueError(f"{nombre}: la carpeta '{c.nombre}' está desactivada.")
        _validar_subcarpeta(u.subcarpeta)
    if f.activa and not f.ubicaciones:
        raise ValueError(f"{nombre}: indica al menos una carpeta donde buscar el archivo.")
    if f.frecuencia_dias is not None and not 1 <= f.frecuencia_dias <= 365:
        raise ValueError(f"{nombre}: el plazo tiene que ir de 1 a 365 días hábiles.")
    if cat.requerida and not f.obligatoria:
        raise ValueError(f"{nombre}: sin esta fuente el motor no calcula; tiene que ser "
                         "obligatoria.")
    if cat.requerida and not f.activa:
        raise ValueError(f"{nombre}: sin esta fuente el motor no calcula; no se puede desactivar.")
    if cat.frecuencia_max is not None and (
        f.frecuencia_dias is None or f.frecuencia_dias > cat.frecuencia_max
    ):
        raise ValueError(f"{nombre}: el plazo no puede pasar de {cat.frecuencia_max} días "
                         "hábiles.")
    if cat.al_vencer_fijo and f.al_vencer != cat.al_vencer_fijo:
        conducta = "frenar la publicación" if cat.al_vencer_fijo == "frena" else "solo avisar"
        raise ValueError(f"{nombre}: cuando se atrasa tiene que {conducta}.")


def _validar_carpeta(c: CarpetaCfg, cfg: ConfigFuentes, *, nueva: bool,
                     validar_params: bool = True) -> None:
    """`validar_params=False` al editar solo el nombre, las rutas por PC o si esta
    activa: la carpeta sembrada no tiene por que pasar las reglas de una nueva, y
    exigirlo bloquearia ediciones que no la tocan."""
    if not re.fullmatch(r"[a-z0-9_]{1,40}", c.clave):
        raise ValueError("La clave de la carpeta solo puede tener minúsculas, números y guion "
                         "bajo (hasta 40).")
    if nueva and any(x.clave == c.clave for x in cfg.carpetas):
        raise ValueError(f"Ya existe una carpeta con la clave '{c.clave}'.")
    if not (c.nombre or "").strip():
        raise ValueError("Falta el nombre de la carpeta.")
    if c.tipo not in ("sharepoint", "onedrive"):
        raise ValueError("El tipo de carpeta tiene que ser SharePoint u OneDrive.")
    _validar_rutas_por_pc(c)
    if not validar_params:
        return
    params = c.params or {}
    ruta = _ruta(params.get("ruta"))
    if c.tipo == "sharepoint":
        if not _SITIO_SHAREPOINT.fullmatch(str(params.get("sitio_url") or "").strip()):
            raise ValueError("El sitio de SharePoint tiene que ser de la forma "
                             "https://<empresa>.sharepoint.com/sites/<sitio>.")
        if not str(params.get("biblioteca") or "").strip():
            raise ValueError("Falta la biblioteca de SharePoint (por ejemplo, "
                             "'Documentos compartidos').")
        _validar_ruta_carpeta(ruta, "SharePoint")
        atajo = str(params.get("nombre_atajo") or "").strip()
        if atajo and ("/" in atajo or "\\" in atajo or ".." in atajo or len(atajo) > 200):
            raise ValueError("El nombre del acceso directo es solo un nombre, sin / ni \\.")
    else:
        _validar_ruta_carpeta(ruta, "OneDrive")


def _validar_rutas_por_pc(c: CarpetaCfg) -> None:
    for host, r in (c.rutas_por_pc or {}).items():
        if not (host or "").strip() or len(host) > 100:
            raise ValueError("Cada ruta por PC necesita el nombre del PC.")
        if not (r or "").strip() or len(r) > 400 or ".." in r:
            raise ValueError(f"La ruta del PC {host} no es válida.")


def _aplicar_cambios_fuente(f: FuenteCfg, cambios: CambiosFuente) -> FuenteCfg:
    datos = f.model_dump(mode="json")
    for campo in cambios.model_fields_set:
        valor = getattr(cambios, campo)
        if valor is None and campo != "frecuencia_dias" and campo != "nombre_archivo":
            continue
        if campo == "ubicaciones":
            valor = [
                {"carpeta": u.carpeta.strip(),
                 "subcarpeta": _subcarpeta(u.subcarpeta),
                 "recursiva": u.recursiva}
                for u in valor
            ]
        elif campo in ("incluye", "excluye"):
            valor = [p.strip() for p in valor if p and p.strip()]
        elif campo == "extensiones":
            valor = [e.strip().lower() for e in valor if e and e.strip()]
        elif campo in ("nombre", "nombre_archivo") and isinstance(valor, str):
            valor = valor.strip() or None
        datos[campo] = valor
    if not datos.get("nombre"):
        datos["nombre"] = f.nombre
    return FuenteCfg.model_validate(datos)


def _buscar_fuente(cfg: ConfigFuentes, clave: str) -> FuenteCfg:
    for f in cfg.fuentes:
        if f.clave == clave:
            return f
    raise NoEncontrado(f"No existe la fuente '{clave}'.")


def _reemplazar_fuente(cfg: ConfigFuentes, nueva: FuenteCfg) -> ConfigFuentes:
    fuentes = [nueva if f.clave == nueva.clave else f for f in cfg.fuentes]
    if not any(f.clave == nueva.clave for f in cfg.fuentes):
        fuentes.append(nueva)
    return cfg.model_copy(update={"fuentes": fuentes})


def guardar_fuente(db: Session, clave: str, cambios: CambiosFuente, *, nota: str,
                   base_version: int, usuario: str | None) -> dict:
    """`PUT /{clave}`: valida, prueba contra el ultimo listado del titular y guarda.
    Con un conflicto de la vista previa (dos fuentes con el mismo archivo, o en
    activa una obligatoria sin archivo) responde 422 y no guarda."""
    fila, cfg = _vigente_o_error(db)
    _chequear_base(fila, base_version)
    nueva_f = _aplicar_cambios_fuente(_buscar_fuente(cfg, clave), cambios)
    _validar_fuente(nueva_f, cfg)
    nueva = _reemplazar_fuente(cfg, nueva_f)
    vp = _vista_previa(db, nueva, clave)
    if vp["conflictos"]:
        raise ValueError(vp["conflictos"][0])
    return _guardar(db, nueva, antes=cfg, usuario=usuario, nota=nota,
                    base_version=base_version, avisos=vp["avisos"])


def crear_carpeta(db: Session, carpeta: dict, *, nota: str, base_version: int,
                  usuario: str | None) -> dict:
    fila, cfg = _vigente_o_error(db)
    _chequear_base(fila, base_version)
    datos = dict(carpeta)
    datos["params"] = {k: (_ruta(v) if k == "ruta" else str(v).strip())
                       for k, v in (datos.get("params") or {}).items()}
    datos["rutas_por_pc"] = {k.strip(): v.strip() for k, v in (datos.get("rutas_por_pc") or {}).items()
                             if v and v.strip()}
    nueva_c = CarpetaCfg.model_validate(datos)
    _validar_carpeta(nueva_c, cfg, nueva=True)
    nueva = cfg.model_copy(update={"carpetas": list(cfg.carpetas) + [nueva_c]})
    return _guardar(db, nueva, antes=cfg, usuario=usuario, nota=nota, base_version=base_version)


def editar_carpeta(db: Session, clave: str, cambios: CambiosCarpeta, *, nota: str,
                   base_version: int, usuario: str | None) -> dict:
    fila, cfg = _vigente_o_error(db)
    _chequear_base(fila, base_version)
    actual = next((c for c in cfg.carpetas if c.clave == clave), None)
    if actual is None:
        raise NoEncontrado(f"No existe la carpeta '{clave}'.")
    datos = actual.model_dump(mode="json")
    if cambios.nombre is not None:
        datos["nombre"] = cambios.nombre.strip()
    if cambios.tipo is not None:
        datos["tipo"] = cambios.tipo
    if cambios.params is not None:
        datos["params"] = {k: (_ruta(v) if k == "ruta" else str(v).strip())
                           for k, v in cambios.params.items()}
    if cambios.rutas_por_pc is not None:
        datos["rutas_por_pc"] = {k.strip(): v.strip() for k, v in cambios.rutas_por_pc.items()
                                 if v and v.strip()}
    if cambios.activa is not None:
        datos["activa"] = cambios.activa
    nueva_c = CarpetaCfg.model_validate(datos)
    _validar_carpeta(nueva_c, cfg, nueva=False,
                     validar_params=cambios.params is not None or cambios.tipo is not None)
    if not nueva_c.activa:
        usan = [f.nombre for f in cfg.fuentes if any(u.carpeta == clave for u in f.ubicaciones)]
        if usan:
            raise ValueError(f"La carpeta '{nueva_c.nombre}' la usan estas fuentes: "
                             f"{', '.join(usan)}. Sácala de ellas antes de desactivarla.")
    carpetas = [nueva_c if c.clave == clave else c for c in cfg.carpetas]
    nueva = cfg.model_copy(update={"carpetas": carpetas})
    return _guardar(db, nueva, antes=cfg, usuario=usuario, nota=nota, base_version=base_version)


def revertir(db: Session, version: int, *, usuario: str | None, nota: str | None = None,
             base_version: int | None = None, clave: str | None = None) -> dict:
    """Inserta una copia de esa version, igual que `config_modelo_service.revertir`.

    Se copian las carpetas y las fuentes (o solo una fuente, con `clave`). El modo,
    el titular, los nombres de los PCs y el catalogo quedan como estan: revertir a
    una version vieja en `activa` no puede saltarse la condicion para activar, ni
    cambiar de titular sin pasar por `POST /titular`.
    """
    fila, cfg = _vigente_o_error(db)
    _chequear_base(fila, base_version)
    origen = db.scalars(
        select(FuenteConfig).where(
            FuenteConfig.tenant_id == settings.default_tenant_id,
            FuenteConfig.version == version,
        )
    ).first()
    if origen is None:
        raise NoEncontrado(f"No existe la versión {version}.")
    cfg_origen = _config_de(origen)
    if clave:
        f = next((x for x in cfg_origen.fuentes if x.clave == clave), None)
        if f is None:
            raise NoEncontrado(f"La versión {version} no tiene la fuente '{clave}'.")
        carpetas = {c.clave: c for c in cfg.carpetas}
        for u in f.ubicaciones:
            c = carpetas.get(u.carpeta)
            if c is None or not c.activa:
                raise ValueError(f"{f.nombre}: esa versión usa la carpeta '{u.carpeta}', que hoy "
                                 "no existe o está desactivada.")
        nueva = _reemplazar_fuente(cfg, f)
    else:
        nueva = cfg.model_copy(update={"carpetas": cfg_origen.carpetas,
                                       "fuentes": cfg_origen.fuentes})
    try:
        return _guardar(db, nueva, antes=cfg, usuario=usuario, base_version=base_version,
                        revierte_a=version,
                        nota=(nota or "").strip() or f"Volver a la versión {version}")
    except ValueError as e:
        if "No hay cambios" in str(e):
            raise ValueError("Esa versión es igual a la vigente: no hay nada que revertir.") from None
        raise


def historial(db: Session, clave: str | None = None, limite: int = 50) -> list[dict]:
    filas = db.scalars(
        select(FuenteConfig)
        .where(FuenteConfig.tenant_id == settings.default_tenant_id)
        .order_by(desc(FuenteConfig.version))
    ).all()
    salida = []
    for f in filas:
        claves = _cargar(f.claves_cambiadas, [])
        if clave and clave not in claves:
            continue
        salida.append({
            "version": f.version, "creado_por": f.creado_por, "creado_en": _utc(f.creado_en),
            "nota": f.nota, "revierte_a": f.revierte_a, "claves_cambiadas": claves,
        })
        if len(salida) >= limite:
            break
    return salida


# --------------------------------------------------------------------------- #
# Activacion
# --------------------------------------------------------------------------- #
_CAMBIOS_QUE_NO_INVALIDAN = {"modo", "pcs"}


def condicion_activar(db: Session, fila: FuenteConfig, cfg: ConfigFuentes) -> tuple[bool, str | None, int]:
    """(se puede, motivo si no, corridas en verde).

    `CORRIDAS_PARA_ACTIVAR` corridas oficiales seguidas del PC titular, `ok`, con
    `config_origen=plataforma`, y en cada una:
    - cada fuente `lee` activa en `coincide` o `difiere_esperado` (una no obligatoria
      puede estar en `falta` si el `.env` tampoco la encontro: activar no cambia nada);
    - ninguna obligatoria en `falta`.
    Ademas, la configuracion no puede haber cambiado (salvo modo o nombres de PC)
    despues de esas corridas: si cambio, lo que se comparo ya no es lo que se activa.
    """
    titular = cfg.pc_titular
    if not titular:
        return False, "Falta elegir el PC titular.", 0
    corridas = db.scalars(
        select(MotorCorrida)
        .where(
            MotorCorrida.tenant_id == settings.default_tenant_id,
            MotorCorrida.pc == titular,
            MotorCorrida.tipo == "oficial",
            MotorCorrida.resultado != "en_curso",
        )
        .order_by(desc(MotorCorrida.iniciada_en))
        .limit(CORRIDAS_PARA_ACTIVAR)
    ).all()
    catalogo = {k: v.model_dump() for k, v in cfg.catalogo.items()}
    lee = [f.model_dump() for f in cfg.fuentes if f.activa and _uso(catalogo, f.clave) == "lee"]
    versiones = [(v.version, set(_cargar(v.claves_cambiadas, [])))
                 for v in db.scalars(select(FuenteConfig).where(
                     FuenteConfig.tenant_id == settings.default_tenant_id)).all()]
    ahora = ahora_chile()
    verdes = 0
    problema = None
    for c in corridas:
        problema = _problema_para_activar(c, lee, catalogo, versiones, ahora)
        if problema:
            break
        verdes += 1
    if verdes >= CORRIDAS_PARA_ACTIVAR:
        return True, None, verdes
    base = (f"Para activar hacen falta {CORRIDAS_PARA_ACTIVAR} corridas oficiales seguidas del "
            f"PC titular en verde, y hay {verdes}.")
    return False, f"{base} {problema}" if problema else base, verdes


def _problema_para_activar(c: MotorCorrida, lee: list[dict], catalogo: dict,
                           versiones: list[tuple[int, set]], ahora: datetime) -> str | None:
    cuando = _cuando(a_chile(c.iniciada_en), ahora)
    if c.resultado != "ok":
        return f"La corrida {_de(cuando)} no terminó bien ({_texto_resultado(c).lower()})."
    if c.config_origen != "plataforma":
        return f"La corrida {_de(cuando)} no usó la configuración de la plataforma."
    if c.config_version is None:
        return f"La corrida {_de(cuando)} no dice con qué versión de la configuración corrió."
    for v, claves in versiones:
        if v > c.config_version and claves - _CAMBIOS_QUE_NO_INVALIDAN:
            return (f"La configuración cambió después de la corrida {_de(cuando)}: hace falta "
                    "que el motor corra con la versión actual.")
    fuentes = _fuentes_de(c)
    for f in lee:
        estado = fuentes.get(f["clave"]) or {}
        prueba = estado.get("prueba") if isinstance(estado.get("prueba"), dict) else {}
        r = prueba.get("resultado")
        if r in ("coincide", "difiere_esperado"):
            continue
        if r == "falta" and not _obligatoria(f, catalogo) and estado.get("hecho") != "encontrado":
            continue
        if r == "difiere":
            detalle = ("toma un archivo distinto del que toma hoy el motor (si es un ensayo, "
                       "márcalo como diferencia esperada)")
        elif r == "falta":
            detalle = "no encuentra archivo con la configuración de la plataforma"
        else:
            detalle = "no trae la comparación con la configuración de la plataforma"
        return f"En la corrida {_de(cuando)}, {f.get('nombre') or f['clave']} {detalle}."
    return None


# --------------------------------------------------------------------------- #
# Vista previa: que archivo tomaria el motor
# --------------------------------------------------------------------------- #
def _archivos_listado(listado: dict | None) -> list[dict]:
    if not listado:
        return []
    archivos = listado.get("archivos")
    return [a for a in archivos if isinstance(a, dict) and a.get("ruta_relativa")] \
        if isinstance(archivos, list) else []


def _en_ubicacion(ruta_relativa: str, subcarpeta: str, recursiva: bool) -> bool:
    partes = _ruta(ruta_relativa).split("/")
    carpeta = "/".join(partes[:-1])
    sub = _ruta(subcarpeta)
    if sub:
        nc, ns = _norm(carpeta), _norm(sub)
        if not (nc == ns or nc.startswith(ns + "/")):
            return False
        resto = carpeta[len(sub):].strip("/")
    else:
        resto = carpeta
    return recursiva or not resto


def _anios_de_ventas(hoy: date) -> set[str]:
    # El motor usa `_fin_mes_cerrado(hoy) = hoy.replace(day=1)` y se queda con los
    # respaldos que traen en el nombre ese ano o el anterior.
    return {str(hoy.year), str(hoy.year - 1)}


def _candidatos(fuente: dict, todas: list[dict], listados: dict[str, dict],
                hoy: date) -> tuple[list[tuple[str, dict]], list[str]]:
    """((carpeta, archivo) que calzan, mas nuevo primero; carpetas que no estan)."""
    exts = {str(e).lower() for e in fuente.get("extensiones") or []}
    modo = fuente.get("modo")
    otras = [f for f in todas if f.get("clave") != fuente.get("clave")]
    anios = _anios_de_ventas(hoy)
    salida: list[tuple[str, dict]] = []
    sin_carpeta: list[str] = []
    for u in fuente.get("ubicaciones") or []:
        listado = listados.get(u.get("carpeta"))
        if not listado or not listado.get("existe", False):
            sin_carpeta.append(u.get("carpeta"))
            continue
        for a in _archivos_listado(listado):
            ruta = _ruta(a["ruta_relativa"])
            nombre = _nombre_de(ruta)
            if nombre.startswith("~$") or nombre.lower() == "desktop.ini":
                continue
            if exts and ("." + nombre.rsplit(".", 1)[-1].lower() if "." in nombre else "") not in exts:
                continue
            if not _en_ubicacion(ruta, u.get("subcarpeta") or "", bool(u.get("recursiva"))):
                continue
            if modo == "archivo_exacto":
                ok = _norm(nombre) == _norm(fuente.get("nombre_archivo") or "")
            elif modo == "por_descarte":
                ok = (not any(_matchea(nombre, o.get("incluye") or [], o.get("excluye") or [])
                              for o in otras)
                      and any(x in nombre for x in anios))
            else:
                ok = _matchea(nombre, fuente.get("incluye") or [], fuente.get("excluye") or [])
            if ok:
                salida.append((u.get("carpeta"), a))
    minimo = datetime.min.replace(tzinfo=TZ_CHILE)
    salida.sort(key=lambda ca: _fecha_archivo(ca[1].get("modificado_en")) or minimo, reverse=True)
    return salida, sin_carpeta


def _elegidos(fuente: dict, candidatos: list[tuple[str, dict]]) -> list[tuple[str, dict]]:
    if fuente.get("modo") == "por_descarte":
        return sorted(candidatos, key=lambda ca: _ruta(ca[1]["ruta_relativa"]))
    return candidatos[:1]


def _archivo_out(carpeta: str | None, a: dict, carpetas: dict[str, dict]) -> dict:
    ruta = _ruta(a.get("ruta_relativa"))
    carpeta = _texto(carpeta)
    return {
        "carpeta": carpeta,
        "carpeta_nombre": (carpetas.get(carpeta) or {}).get("nombre") if carpeta else None,
        "ruta_relativa": ruta,
        "nombre": _nombre_de(ruta),
        "modificado_en": _fecha_archivo(a.get("modificado_en")),
        "tamano": _entero(a.get("tamano")),
        "onedrive": _texto(a.get("onedrive")),
    }


def _describir(archivos: list[dict], ahora: datetime) -> str:
    if not archivos:
        return "ningún archivo"
    if len(archivos) == 1:
        a = archivos[0]
        cuando = f" (modificado {_cuando(a['modificado_en'], ahora)})" if a.get("modificado_en") else ""
        return f"{a['nombre']}{cuando}"
    nombres = ", ".join(a["nombre"] for a in archivos[:4])
    return f"{len(archivos)} archivos: {nombres}"


def _ultima_con_listado(db: Session, pc: str | None) -> MotorCorrida | None:
    if not pc:
        return None
    for c in db.scalars(
        select(MotorCorrida)
        .where(MotorCorrida.tenant_id == settings.default_tenant_id, MotorCorrida.pc == pc)
        .order_by(desc(MotorCorrida.iniciada_en))
        .limit(30)
    ).all():
        if _listados_de(c):
            return c
    return None


def _ultima_con_fuentes(db: Session, pc: str | None) -> MotorCorrida | None:
    if not pc:
        return None
    for c in db.scalars(
        select(MotorCorrida)
        .where(MotorCorrida.tenant_id == settings.default_tenant_id, MotorCorrida.pc == pc)
        .order_by(desc(MotorCorrida.iniciada_en))
        .limit(30)
    ).all():
        if _fuentes_de(c):
            return c
    return None


def vista_previa(db: Session, clave: str, cambios: CambiosFuente) -> dict:
    """`POST /{clave}/vista-previa`: no guarda nada."""
    _, cfg = _vigente_o_error(db)
    nueva_f = _aplicar_cambios_fuente(_buscar_fuente(cfg, clave), cambios)
    _validar_fuente(nueva_f, cfg)
    return _vista_previa(db, _reemplazar_fuente(cfg, nueva_f), clave)


def _vista_previa(db: Session, cfg: ConfigFuentes, clave: str) -> dict:
    ahora = ahora_chile()
    datos = _dump(cfg)
    catalogo = datos.get("catalogo") or {}
    carpetas = {c["clave"]: c for c in datos.get("carpetas") or []}
    todas = datos.get("fuentes") or []
    fuente = next(f for f in todas if f["clave"] == clave)
    nombre = fuente.get("nombre") or clave
    corrida = _ultima_con_listado(db, cfg.pc_titular)
    alias = (datos.get("pcs") or {}).get(cfg.pc_titular or "", {}).get("alias")
    conflictos: list[str] = []
    avisos: list[str] = []

    base_fuentes = _ultima_con_fuentes(db, cfg.pc_titular)
    estado_hoy = _fuentes_de(base_fuentes).get(clave) if base_fuentes else None
    hoy_archivos = [_archivo_out(a.get("carpeta"), a, carpetas) for a in _archivos_estado(estado_hoy)]
    hoy_toma = {"archivos": hoy_archivos, "candidatos": len(hoy_archivos),
                "texto": f"Hoy toma {_describir(hoy_archivos, ahora)}."}

    if corrida is None:
        avisos.append("Todavía no hay un listado de carpetas del PC titular: no se puede mostrar "
                      "qué archivo tomaría. Se verá después de la próxima corrida.")
        return {"elegiria": {"archivos": [], "candidatos": 0,
                             "texto": "Sin listado del PC titular."},
                "hoy_toma": hoy_toma, "conflictos": conflictos, "avisos": avisos,
                "listado": None}

    listados = _listados_de(corrida)
    hoy = ahora.date()
    cands, sin_carpeta = _candidatos(fuente, todas, listados, hoy)
    elegidos = _elegidos(fuente, cands)
    elegidos_out = [_archivo_out(c, a, carpetas) for c, a in elegidos]
    for c in sin_carpeta:
        avisos.append(f"{_sujeto_pc(alias, cfg.pc_titular)} no tiene la carpeta "
                      f"'{(carpetas.get(c) or {}).get('nombre') or c}'.")
    if fuente.get("modo") == "por_descarte":
        avisos.append("El motor además revisa el contenido de cada respaldo: los que no tengan "
                      "forma de respaldo de venta se descartan.")

    if fuente.get("activa", True) and not elegidos and _obligatoria(fuente, catalogo):
        if cfg.modo == "activa":
            conflictos.append("Con este cambio el motor no encontraría el archivo y la "
                              "publicación se frenaría.")
        else:
            avisos.append("Con este cambio el motor no encontraría el archivo: en modo activa, "
                          "esto frenaría la publicación.")

    # Dos fuentes con el mismo archivo: entre dos `lee` es conflicto; con una
    # `reconoce` es solo aviso (precios_ford y precios_proveedor comparten archivo).
    mios = {(c, _norm(_ruta(a["ruta_relativa"]))) for c, a in elegidos}
    uso_mio = _uso(catalogo, clave)
    for otra in todas:
        if otra["clave"] == clave or not otra.get("activa", True):
            continue
        sus, _ = _candidatos(otra, todas, listados, hoy)
        comunes = mios & {(c, _norm(_ruta(a["ruta_relativa"]))) for c, a in _elegidos(otra, sus)}
        if not comunes:
            continue
        archivo = _nombre_de(next(iter(comunes))[1])
        texto = (f"{nombre} y {otra.get('nombre') or otra['clave']} tomarían el mismo archivo: "
                 f"{archivo}.")
        if uso_mio == "lee" and _uso(catalogo, otra["clave"]) == "lee":
            conflictos.append(texto)
        else:
            avisos.append(texto)

    texto = f"Con este cambio el motor tomaría {_describir(elegidos_out, ahora)}."
    return {
        "elegiria": {"archivos": elegidos_out, "candidatos": len(cands), "texto": texto},
        "hoy_toma": hoy_toma,
        "conflictos": conflictos,
        "avisos": avisos,
        "listado": {"pc": corrida.pc, "alias": alias, "corrida_id": corrida.id,
                    "iniciada_en": _utc(corrida.iniciada_en)},
    }


def proponer_patron(nombre: str) -> str:
    """Patron para "el más reciente cuyo nombre contenga…": fechas y numeros como
    comodin. "Precios Gildemeister 20260728.xlsx" -> "precios gildemeister *"."""
    base = nombre.rsplit(".", 1)[0] if "." in nombre else nombre
    n = _norm(base)
    n = re.sub(r"\d+(?:[.\-_]\d+)*", "*", n)
    n = re.sub(r"\(\s*\*\s*\)", "*", n)
    n = re.sub(r"\*(?:\s*\*)+", "*", n)
    n = re.sub(r"\s+", " ", n).strip()
    if n.replace("*", "").strip() == "":
        return _norm(nombre)
    return n if n.endswith("*") else n + ".*"


# --------------------------------------------------------------------------- #
# Semaforo (funcion pura)
# --------------------------------------------------------------------------- #
def _alerta(nivel: str, etiqueta: str, texto: str, regla: str) -> dict:
    return {"nivel": nivel, "etiqueta": etiqueta, "texto": texto, "regla": regla}


def _periodo(valor: Any) -> int | None:
    """"202609", "2026-09", "09-2026" o 202609 -> 202609."""
    if valor is None:
        return None
    s = re.sub(r"\D", "", str(valor))
    if len(s) != 6:
        return None
    if str(valor).strip()[:4].isdigit() and int(s[:4]) > 1900:
        return int(s)
    return int(s[2:] + s[:2])


def _mes_cerrado(hoy: date) -> int:
    ultimo = hoy.replace(day=1) - timedelta(days=1)
    return ultimo.year * 100 + ultimo.month


def _donde(fuente: dict, carpetas: dict[str, dict]) -> str:
    lugares = []
    for u in fuente.get("ubicaciones") or []:
        nombre = (carpetas.get(u.get("carpeta")) or {}).get("nombre") or u.get("carpeta")
        sub = _ruta(u.get("subcarpeta"))
        lugares.append(f"{nombre} › {sub.replace('/', ' › ')}" if sub else str(nombre))
    return " ni en ".join(lugares) if lugares else "ninguna carpeta"


def _que_busca(fuente: dict) -> str:
    modo = fuente.get("modo")
    if modo == "archivo_exacto":
        return f"el archivo '{fuente.get('nombre_archivo')}'"
    if modo == "por_descarte":
        return "ningún respaldo"
    textos = []
    for p in (fuente.get("incluye") or [])[:2]:
        piezas = [x.strip() for x in str(p).split("*") if x.strip()]
        if piezas:
            textos.append(" y ".join(f"'{x}'" for x in piezas))
    if not textos:
        return "ningún archivo"
    return "ningún archivo cuyo nombre contenga " + " o ".join(textos)


def _efecto(texto: str | None) -> str:
    t = (texto or "").strip().rstrip(".")
    if not t:
        return "faltará ese dato"
    if len(t) > 1 and t[0].isupper() and t[1].islower():
        t = t[0].lower() + t[1:]
    return t


def _texto_prueba(prueba: dict, obligatoria: bool) -> dict | None:
    r = _texto(prueba.get("resultado"))
    if not r:
        return None
    # El motor manda el archivo como objeto ({carpeta, ruta_relativa, ...}); se acepta
    # tambien la ruta sola.
    archivo = prueba.get("archivo")
    if isinstance(archivo, dict):
        archivo = archivo.get("ruta_relativa")
    archivo = _texto(archivo)
    nombre = _nombre_de(archivo) if archivo else None
    # `frenaria` es el motivo en texto ("Falta el archivo de ...") o un booleano.
    por_que = _texto(prueba.get("frenaria"))
    frenaria = bool(prueba.get("frenaria")) or (r == "falta" and obligatoria)
    if r == "coincide":
        texto = "La configuración de la plataforma toma el mismo archivo."
    elif r == "difiere_esperado":
        texto = (f"La configuración de la plataforma tomaría {nombre or 'otro archivo'}: es una "
                 "diferencia esperada (ensayo).")
    elif r == "difiere":
        texto = (f"La configuración de la plataforma tomaría {nombre or 'otro archivo'}, distinto "
                 "de lo que toma hoy. Revisa la fuente antes de activar.")
    elif r == "falta":
        texto = "Con la configuración de la plataforma el motor no encontraría el archivo."
    else:
        texto = f"Comparación: {r}."
    if frenaria:
        texto += " En modo activa, esto frenaría la publicación"
        texto += f" ({por_que})." if por_que else "."
    return {"resultado": r, "archivo": nombre, "texto": texto, "frenaria": frenaria}


def semaforo(
    estado: dict | None,
    cfg: dict | None,
    anterior: dict | None,
    ahora_chile: datetime,
    *,
    catalogo: dict | None = None,
    modo: str = "prueba",
    carpetas: dict[str, dict] | None = None,
    listados: dict[str, dict] | None = None,
    alias_pc: str | None = None,
    pc: str | None = None,
) -> dict:
    """Semaforo de UNA fuente: `{nivel, etiqueta, texto, regla, alertas, edad_dias_habiles}`.

    - `estado`: `reporte.fuentes[clave]` de la corrida que se muestra.
    - `cfg`: la fuente en la configuracion (FuenteCfg como dict).
    - `anterior`: el estado de la misma fuente en la corrida anterior (filas,
      descartados y carpeta, para "llegó vacío", "archivo nuevo" y "cambió de carpeta").
    - `ahora_chile`: con zona. La edad se recalcula a esta hora en dias habiles.
    - `catalogo`: la entrada del catalogo de esta fuente.

    Se evaluan todas las reglas de §3.6 en su orden; la principal es la primera de la
    peor. Pura: no lee la base ni el reloj.
    """
    cfg = cfg or {}
    cat = catalogo or {}
    carpetas = carpetas or {}
    nombre = cfg.get("nombre") or cfg.get("clave") or "La fuente"
    edad = None

    def _fin(alertas: list[dict]) -> dict:
        principal = min(alertas, key=lambda a: _SEVERIDAD[a["nivel"]]) if alertas else \
            _alerta("gris", "Sin datos", "Todavía no hay una corrida que haya revisado esta "
                    "fuente.", "sin_datos")
        return {**principal, "alertas": alertas, "edad_dias_habiles": edad}

    if not cfg.get("activa", True):
        return _fin([_alerta("gris", "Desactivada", f"{nombre} está desactivada: el motor no "
                             "la lee.", "desactivada")])
    if not isinstance(estado, dict) or not estado.get("hecho"):
        return _fin([])

    hecho = estado.get("hecho")
    archivos = _archivos_estado(estado)
    principal = _mas_nuevo(archivos)
    modificado = _fecha_archivo(principal.get("modificado_en")) if principal else None
    hoy = ahora_chile.astimezone(TZ_CHILE).date()
    if modificado is not None:
        edad = dias_habiles_entre(modificado.date(), hoy)
    elif isinstance(estado.get("edad_dias_habiles"), int):
        edad = estado["edad_dias_habiles"]
    freq = cfg.get("frecuencia_dias")
    al_vencer = cfg.get("al_vencer") or "frena"
    obligatoria = bool(cfg.get("obligatoria") or cat.get("requerida"))
    encontrado = hecho == "encontrado"
    filas = estado.get("filas")
    archivo_txt = _nombre_de(principal["ruta_relativa"]) if principal else nombre
    if len(archivos) > 1:
        nombres = ", ".join(_nombre_de(a["ruta_relativa"]) for a in archivos[:3])
        archivo_txt = f"{len(archivos)} archivos ({nombres})"
    cuando = _de(_cuando(modificado, ahora_chile)) if modificado else None
    filas_txt = f", {_miles(filas)} filas" if isinstance(filas, (int, float)) and filas > 0 else ""
    activa_config = modo == "activa"
    alertas: list[dict] = []

    # ---- rojo ----
    if encontrado and freq is not None and edad is not None and edad > freq and al_vencer == "frena":
        alertas.append(_alerta(
            "rojo", "Vencido",
            f"Vencido: {archivo_txt} tiene {edad} días hábiles y se espera cada {freq}. "
            "Mientras siga así, el sugerido no se publica. Revisa que el archivo se haya "
            "actualizado (si lo deja el programa del ERP, que haya corrido hoy) y que OneDrive "
            "esté sincronizado.",
            "vencido"))
    if hecho == "falta" and obligatoria:
        consecuencia = ("El sugerido no se publica hasta que aparezca."
                        if activa_config or cat.get("requerida")
                        else "Hoy el sugerido se publica igual, pero con la configuración activa "
                             "esto frenaría la publicación.")
        alertas.append(_alerta(
            "rojo", "Falta",
            f"Falta: no hay {_que_busca(cfg)} en {_donde(cfg, carpetas)}. {consecuencia}",
            "falta"))
    if hecho == "carpeta_no_encontrada":
        alertas.append(_alerta("rojo", "Carpeta no encontrada",
                               _texto_sin_carpeta(cfg, carpetas, listados or {}, alias_pc, pc),
                               "carpeta_no_encontrada"))
    controla = cat.get("controla_filas")
    if controla is None:
        controla = cat.get("frecuencia_max") is not None
    ant_filas = (anterior or {}).get("filas") if isinstance(anterior, dict) else None
    if controla and encontrado and isinstance(filas, (int, float)) and (
        filas == 0 or (isinstance(ant_filas, (int, float)) and ant_filas > 0
                       and filas < RATIO_FILAS_MINIMO * ant_filas)
    ):
        antes = (f" (la corrida anterior traía {_miles(ant_filas)})"
                 if isinstance(ant_filas, (int, float)) and ant_filas > 0 else "")
        efecto = ("No se publicó para no calcular con datos incompletos."
                  if activa_config else "Con la configuración activa no se publicaría.")
        alertas.append(_alerta(
            "rojo", "Llegó vacío o incompleto",
            f"{nombre} llegó con {_miles(filas)} filas{antes}. {efecto} Vuelve a generar el "
            "archivo (si lo deja el programa del ERP, córrelo de nuevo).",
            "incompleto"))
    if hecho == "error_lectura":
        detalle = f" ({estado['mensaje']})" if estado.get("mensaje") else ""
        alertas.append(_alerta(
            "rojo", "No se pudo leer",
            f"No se pudo leer {archivo_txt}{detalle}. Revisa que el archivo abra bien en Excel y "
            "vuelve a correr.",
            "error_lectura"))
    extra = estado.get("extra") if isinstance(estado.get("extra"), dict) else {}
    if encontrado and ("periodo_ultimo_mes" in extra or "total_mes_cerrado" in extra):
        # El motor manda el ultimo mes cerrado que uso (`periodo_ultimo_mes`) y la venta
        # total de ese mes en el CSV. Falta el mes si esa venta es cero, o si el
        # periodo quedo atras del mes cerrado de hoy (un dato de otro mes).
        cerrado = _mes_cerrado(hoy)
        periodo = _periodo(extra.get("periodo_ultimo_mes"))
        total = extra.get("total_mes_cerrado")
        falta_mes = None
        if isinstance(total, (int, float)) and not isinstance(total, bool) and total <= 0:
            falta_mes = periodo or cerrado
        elif periodo is not None and periodo < cerrado:
            falta_mes = cerrado
        if falta_mes is not None:
            mes = _MESES[falta_mes % 100 - 1]
            texto = (f"El respaldo de ventas no trae {mes}: el sugerido saldría con ese mes en "
                     "cero. Exporta el respaldo del año y vuelve a correr.")
            if hoy.day < DIA_DESDE_QUE_FRENA_VENTAS:
                alertas.append(_alerta("amarillo", "Ventas sin el mes cerrado",
                                       texto + f" Desde el día {DIA_DESDE_QUE_FRENA_VENTAS} esto "
                                       "frena la publicación.", "ventas_sin_mes"))
            else:
                alertas.append(_alerta("rojo", "Ventas sin el mes cerrado", texto,
                                       "ventas_sin_mes"))

    # ---- amarillo ----
    if encontrado and freq is not None and edad is not None and edad > freq and al_vencer == "avisa":
        alertas.append(_alerta(
            "amarillo", "Atrasado, no frena",
            f"Atrasado: {archivo_txt} tiene {edad} días hábiles y se espera cada {freq}. No frena "
            "la publicación.",
            "atrasado"))
    if hecho == "falta" and not obligatoria:
        alertas.append(_alerta(
            "amarillo", "Falta (no frena)",
            f"Falta {nombre}. El sugerido se publica igual, pero "
            f"{_efecto(cat.get('efecto_si_falta'))}.",
            "falta_no_frena"))
    if encontrado and estado.get("mismo_contenido_que_anterior") and freq is not None and freq <= 2:
        alertas.append(_alerta(
            "amarillo", "Mismo contenido que ayer",
            "Revisar: la fecha del archivo cambió, pero el contenido es idéntico al de ayer. "
            "Puede que OneDrive no haya terminado de bajarlo.",
            "mismo_contenido"))
    if hecho == "inestable":
        alertas.append(_alerta(
            "amarillo", "Bajando de OneDrive",
            "OneDrive no terminó de bajar el archivo. Abre OneDrive, espera a que termine de "
            "sincronizar y vuelve a correr.",
            "inestable"))
    if estado.get("abierto_en_excel"):
        alertas.append(_alerta(
            "amarillo", "Abierto en Excel",
            "Este archivo está abierto en Excel en el PC del motor: el programa del ERP no puede "
            "actualizarlo. Ciérralo.",
            "abierto_en_excel"))
    if isinstance(anterior, dict):
        antes = {str(d.get("nombre")) for d in anterior.get("descartados") or [] if isinstance(d, dict)}
        nuevos = [d for d in estado.get("descartados") or []
                  if isinstance(d, dict) and str(d.get("nombre")) not in antes]
        if nuevos:
            d = nuevos[0]
            motivo = f" ({d['motivo']})" if d.get("motivo") else ""
            mas = f" y {len(nuevos) - 1} más" if len(nuevos) > 1 else ""
            alertas.append(_alerta(
                "amarillo", "Archivo nuevo en la carpeta",
                f"Apareció un archivo nuevo que el motor no usa para esta fuente: "
                f"{d.get('nombre')}{motivo}{mas}. No cambia lo que se lee; si debería usarse, "
                "revisa la configuración de la fuente.",
                "archivo_nuevo"))
        ant_principal = _mas_nuevo(_archivos_estado(anterior))
        if principal and ant_principal and principal.get("carpeta") and ant_principal.get("carpeta") \
                and principal["carpeta"] != ant_principal["carpeta"]:
            nueva_c = (carpetas.get(principal["carpeta"]) or {}).get("nombre") or principal["carpeta"]
            vieja_c = (carpetas.get(ant_principal["carpeta"]) or {}).get("nombre") or ant_principal["carpeta"]
            alertas.append(_alerta(
                "amarillo", "Cambió de carpeta",
                f"El archivo ahora viene de {nueva_c} y en la corrida anterior venía de "
                f"{vieja_c}. Revisa que sea el correcto.",
                "cambio_carpeta"))

    # ---- verde ----
    if encontrado and freq is not None and edad is not None and edad <= freq:
        alertas.append(_alerta("verde", "Al día",
                               f"Al día: {archivo_txt}{', ' + cuando if cuando else ''}{filas_txt}.",
                               "al_dia"))
    if encontrado and freq is None:
        alertas.append(_alerta("verde", "Encontrado, sin plazo",
                               f"Encontrado: {archivo_txt}{', ' + cuando if cuando else ''}"
                               f"{filas_txt}. No tiene plazo de actualización.",
                               "sin_plazo"))
    if not alertas:
        alertas.append(_alerta("gris", "Estado desconocido",
                               f"El motor informó un estado que esta pantalla no conoce "
                               f"('{hecho}').", "desconocido"))
    return _fin(alertas)


def _texto_sin_carpeta(cfg: dict, carpetas: dict[str, dict], listados: dict[str, dict],
                       alias: str | None, pc: str | None) -> str:
    falta = None
    for u in cfg.get("ubicaciones") or []:
        listado = listados.get(u.get("carpeta"))
        if not listado or not listado.get("existe", False):
            falta = carpetas.get(u.get("carpeta")) or {"nombre": u.get("carpeta")}
            break
    if falta is None and cfg.get("ubicaciones"):
        u = cfg["ubicaciones"][0]
        falta = carpetas.get(u.get("carpeta")) or {"nombre": u.get("carpeta")}
    sujeto = _sujeto_pc(alias, pc)
    if not falta:
        return f"{sujeto} no tiene la carpeta de esta fuente."
    ruta = _ruta((falta.get("params") or {}).get("ruta")).replace("/", " › ")
    if falta.get("tipo") == "sharepoint":
        return (f"{sujeto} no tiene esta carpeta. Abre OneDrive, agrega el acceso directo a "
                f"'{ruta or falta.get('nombre')}' y, con clic derecho, elige 'Mantener siempre en "
                "este dispositivo'.")
    return (f"{sujeto} no tiene la carpeta '{ruta or falta.get('nombre')}'. Revisa que OneDrive "
            "esté abierto y sincronizado, y que esa carpeta exista en este PC.")


# --------------------------------------------------------------------------- #
# Franja superior (funcion pura)
# --------------------------------------------------------------------------- #
_TEXTO_RESULTADO = {
    "en_curso": "En curso",
    "ok": "Terminó bien",
    "frenada": "Frenada: no publicó",
    "fallo": "Falló: no publicó",
    "incompleta": "Publicó, pero algunos pasos fallaron",
    "cortada": "Se cortó antes de terminar",
    "no_titular": "No publicó: el PC no es el titular",
}


def _texto_resultado(c: MotorCorrida) -> str:
    if c.resultado == "ok":
        if c.tipo == "probar":
            return "Revisión sin publicar"
        return "Publicó" if c.publico else "Terminó bien"
    return _TEXTO_RESULTADO.get(c.resultado, c.resultado)


# Motivos conocidos de `_fallar` del motor -> frase para la persona.
_MOTIVOS = (
    ("archivos desactualizados", "No se publicó porque hay archivos vencidos."),
    ("no pudo calcular", "No se publicó: el motor no pudo calcular el sugerido."),
    ("ultimo mes de ventas vacio", "No se publicó: el respaldo de ventas no trae el último mes "
                                   "cerrado."),
    ("rechazo la carga", "El motor calculó, pero la plataforma rechazó la carga."),
    ("vacío o incompleto", "No se publicó: un archivo llegó vacío o incompleto."),
    ("vacio o incompleto", "No se publicó: un archivo llegó vacío o incompleto."),
    ("no es el titular", "No se publicó: este PC no es el titular."),
)


def traducir_motivo(motivo: str | None) -> str | None:
    """El motivo del log, en una frase. Nunca muestra opciones de linea de comandos
    (el "corre con --ignorar-frescura" queda solo en el log)."""
    if not motivo:
        return None
    primera = motivo.strip().splitlines()[0].strip()
    n = _norm(primera)
    for clave, frase in _MOTIVOS:
        if _norm(clave) in n:
            return frase
    frases = [f.strip() for f in re.split(r"(?<=[.!?])\s+", primera) if f.strip()]
    limpio = " ".join(f for f in frases if "--" not in f)
    return limpio or None


def _corrida_out(c: MotorCorrida, alias: str | None, resumen: dict | None = None) -> dict:
    dur = None
    if c.terminada_en and c.iniciada_en:
        dur = int((_utc(c.terminada_en) - _utc(c.iniciada_en)).total_seconds() // 60)
    return {
        "id": c.id, "pc": c.pc, "alias": alias, "tipo": c.tipo,
        "titular": bool(c.titular), "publico": bool(c.publico),
        "iniciada_en": _utc(c.iniciada_en), "terminada_en": _utc(c.terminada_en),
        "duracion_min": dur, "resultado": c.resultado,
        "resultado_texto": _texto_resultado(c), "motivo_texto": traducir_motivo(c.motivo),
        "config_origen": c.config_origen, "config_version": c.config_version,
        "version_motor": c.version_motor, "resumen": resumen or {},
    }


def alertas_franja(
    *,
    ultima_oficial: MotorCorrida | None,
    corridas_hoy: list[MotorCorrida],
    titular: str | None,
    alias_titular: str | None,
    modo: str,
    ahora: datetime,
    alias_de: dict[str, str | None] | None = None,
) -> list[dict]:
    """Alertas globales de §3.6 (franja superior). Pura."""
    alias_de = alias_de or {}
    alertas: list[dict] = []
    hoy = ahora.astimezone(TZ_CHILE).date()
    sujeto = _sujeto_pc(alias_titular, titular)
    if titular and ahora.weekday() < 5 and ahora.astimezone(TZ_CHILE).hour >= HORA_LIMITE_CORRIDA:
        corrio = any(c.pc == titular and c.tipo == "oficial" and a_chile(c.iniciada_en).date() == hoy
                     for c in corridas_hoy)
        if not corrio:
            desde = (f"no corre desde {_cuando(a_chile(ultima_oficial.iniciada_en), ahora)}"
                     if ultima_oficial else "todavía no ha corrido la tarea diaria")
            alertas.append(_alerta("rojo", "El PC titular no corrió hoy",
                                   f"{sujeto} {desde}. Revisa que esté prendido y con la sesión "
                                   "abierta.", "titular_no_corrio"))
    u = ultima_oficial
    if u is not None:
        minutos = (ahora - a_chile(u.iniciada_en)).total_seconds() / 60
        if u.resultado == "cortada" or (u.resultado == "en_curso"
                                        and minutos > MINUTOS_PARA_DAR_POR_CORTADA):
            cuando = _cuando(a_chile(u.iniciada_en), ahora)
            if u.resultado == "cortada":
                texto = (f"La corrida {_de(cuando)} se cortó antes de terminar: ese día el "
                         "sugerido puede no haberse publicado. Revisa el PC del motor y vuelve a "
                         "correr.")
            else:
                texto = (f"La corrida {_de(cuando)} lleva más de {MINUTOS_PARA_DAR_POR_CORTADA} "
                         "minutos sin terminar: probablemente se cortó. Revisa el PC del motor y "
                         "vuelve a correr.")
            alertas.append(_alerta("rojo", "La última corrida se cortó", texto, "cortada"))
        if u.config_origen == "env" and modo == "activa":
            alertas.append(_alerta(
                "rojo", "Corrió con la configuración del PC",
                "La última corrida no usó la configuración de esta pantalla sino la escrita en el "
                "PC: los cambios hechos aquí no se aplicaron. Revisa que el PC tenga internet y "
                "que no se haya dejado activada la salida de emergencia del motor.",
                "config_env"))
        if u.config_origen == "cache":
            guardada = _fecha_archivo(_reporte(u).get("cache_guardada_en"))
            antiguedad = (f" (guardada {_cuando(guardada, ahora)})" if guardada else "")
            alertas.append(_alerta(
                "amarillo", "Usó la configuración guardada",
                f"La última corrida no pudo traer la configuración de la plataforma y usó la copia "
                f"guardada en el PC{antiguedad}. Si se repite, revisa la conexión del PC.",
                "config_cache"))
        if _reporte(u).get("onedrive_corriendo") is False:
            alertas.append(_alerta(
                "amarillo", "OneDrive cerrado",
                f"OneDrive no estaba abierto en {_sujeto_pc(alias_de.get(u.pc), u.pc, minuscula=True)} "
                "durante la última corrida: los archivos pueden no estar al día. Ábrelo y espera a "
                "que sincronice.",
                "onedrive_cerrado"))
    pcs_hoy = []
    for c in sorted(corridas_hoy, key=lambda x: _utc(x.iniciada_en)):
        if c.tipo == "oficial" and a_chile(c.iniciada_en).date() == hoy and c.pc not in pcs_hoy:
            pcs_hoy.append(c.pc)
    if len(pcs_hoy) > 1:
        nombres = " y ".join(alias_de.get(p) or p for p in pcs_hoy)
        alertas.append(_alerta(
            "amarillo", "Hoy corrieron dos PCs",
            f"Hoy corrieron la tarea diaria {len(pcs_hoy)} PCs: {nombres}. Solo publica el "
            "titular; deshabilita la tarea en el otro.",
            "dos_pcs"))
    return alertas


# --------------------------------------------------------------------------- #
# Panel, corridas, detalle y listados
# --------------------------------------------------------------------------- #
class _Contexto:
    """Lo que necesitan el panel, el detalle y la campanita, leido una sola vez."""

    def __init__(self, db: Session, ahora: datetime | None = None, limite: int = 60):
        self.ahora = ahora or ahora_chile()
        self.fila = _fila_vigente(db)
        self.cfg = _config_de(self.fila) if self.fila else None
        self.recientes: list[MotorCorrida] = list(db.scalars(
            select(MotorCorrida)
            .where(MotorCorrida.tenant_id == settings.default_tenant_id)
            .order_by(desc(MotorCorrida.iniciada_en))
            .limit(limite)
        ).all())
        oficiales = [c for c in self.recientes if c.tipo == "oficial"]
        if self.cfg and self.cfg.pc_titular:
            self.titular = self.cfg.pc_titular
        elif oficiales:
            self.titular = oficiales[0].pc
        elif self.recientes:
            self.titular = self.recientes[0].pc
        else:
            self.titular = None
        self.base = next((c for c in self.recientes
                          if c.pc == self.titular and _fuentes_de(c)), None)
        # Sin configuracion, el semaforo usa lo que el motor usa hoy.
        if self.cfg is not None:
            self.datos = _dump(self.cfg)
        else:
            con_efectiva = next((c for c in self.recientes if c.pc == self.titular
                                 and _cargar(c.config_efectiva, None)), None) \
                or next((c for c in self.recientes if _cargar(c.config_efectiva, None)), None)
            efectiva = _cargar(con_efectiva.config_efectiva, {}) if con_efectiva else {}
            try:
                self.datos = ConfigEfectiva.model_validate(efectiva).model_dump(mode="json")
            except ValidationError:
                self.datos = {}
        self.catalogo: dict = self.datos.get("catalogo") or {}
        self.carpetas: dict[str, dict] = {c["clave"]: c for c in self.datos.get("carpetas") or []}
        self.fuentes: list[dict] = self.datos.get("fuentes") or []
        self.modo = self.cfg.modo if self.cfg else "sin_configurar"
        pcs = (self.datos.get("pcs") or {}) if self.cfg else {}
        self.alias_de: dict[str, str | None] = {k: (v or {}).get("alias") for k, v in pcs.items()}
        self._anteriores: dict[str, MotorCorrida | None] = {}

    def anterior_de(self, c: MotorCorrida) -> MotorCorrida | None:
        """La corrida terminada anterior del mismo PC (contra ella se comparan filas,
        descartados y carpeta)."""
        if c.id in self._anteriores:
            return self._anteriores[c.id]
        anterior = None
        for x in self.recientes:
            if x.pc == c.pc and x.id != c.id and _utc(x.iniciada_en) < _utc(c.iniciada_en) \
                    and x.resultado not in ("en_curso", "cortada") and _fuentes_de(x):
                anterior = x
                break
        self._anteriores[c.id] = anterior
        return anterior

    def lee(self) -> list[dict]:
        return [f for f in self.fuentes if _uso(self.catalogo, f["clave"]) == "lee"]

    def semaforo_de(self, f: dict, c: MotorCorrida | None, ahora: datetime | None = None) -> dict:
        if c is None:
            return semaforo(None, f, None, ahora or self.ahora,
                            catalogo=self.catalogo.get(f["clave"]), modo=self.modo)
        ant = self.anterior_de(c)
        return semaforo(
            _fuentes_de(c).get(f["clave"]), f,
            _fuentes_de(ant).get(f["clave"]) if ant else None,
            ahora or self.ahora,
            catalogo=self.catalogo.get(f["clave"]), modo=self.modo,
            carpetas=self.carpetas, listados=_listados_de(c),
            alias_pc=self.alias_de.get(c.pc), pc=c.pc,
        )

    def fila_fuente(self, f: dict, c: MotorCorrida | None, dato_de: str | None = None,
                    ahora: datetime | None = None) -> dict:
        sem = self.semaforo_de(f, c, ahora)
        estado = _fuentes_de(c).get(f["clave"]) if c else None
        archivos = [_archivo_out(a.get("carpeta"), a, self.carpetas) for a in _archivos_estado(estado)]
        principal = max(archivos, key=lambda a: a["modificado_en"] or datetime.min.replace(
            tzinfo=TZ_CHILE)) if archivos else None
        prueba = None
        if isinstance(estado, dict) and isinstance(estado.get("prueba"), dict):
            prueba = _texto_prueba(estado["prueba"], _obligatoria(f, self.catalogo))
        carpeta = principal["carpeta"] if principal else None
        return {
            "clave": f["clave"], "nombre": f.get("nombre") or f["clave"],
            "nivel": sem["nivel"], "etiqueta": sem["etiqueta"], "texto": sem["texto"],
            "regla": sem["regla"], "alertas": sem["alertas"],
            "hecho": _texto(estado.get("hecho")) if isinstance(estado, dict) else None,
            "archivo": principal["nombre"] if principal else None,
            "archivos": archivos,
            "modificado_en": principal["modificado_en"] if principal else None,
            "edad_dias_habiles": sem["edad_dias_habiles"],
            "filas": _entero(estado.get("filas")) if isinstance(estado, dict) else None,
            "carpeta": carpeta,
            "carpeta_nombre": (self.carpetas.get(carpeta) or {}).get("nombre") if carpeta else None,
            "obligatoria": _obligatoria(f, self.catalogo),
            "frecuencia_dias": f.get("frecuencia_dias"),
            "al_vencer": f.get("al_vencer"),
            "activa": f.get("activa", True),
            "prueba": prueba,
            "dato_de": dato_de,
        }


def panel(db: Session, ahora: datetime | None = None) -> dict:
    """`GET /`: franja, fuentes `lee` de la peor a la mejor, carpetas por PC, modo y
    si se puede activar. Todo calculado aca."""
    ctx = _Contexto(db, ahora)
    ahora = ctx.ahora
    hoy = ahora.date()
    alias_titular = ctx.alias_de.get(ctx.titular or "")
    oficiales_titular = [c for c in ctx.recientes if c.tipo == "oficial" and c.pc == ctx.titular]
    ultima_oficial = oficiales_titular[0] if oficiales_titular else None
    corridas_hoy = [c for c in ctx.recientes if a_chile(c.iniciada_en).date() == hoy]
    alertas = alertas_franja(
        ultima_oficial=ultima_oficial, corridas_hoy=corridas_hoy, titular=ctx.titular,
        alias_titular=alias_titular, modo=ctx.modo, ahora=ahora, alias_de=ctx.alias_de,
    )
    if not ctx.recientes:
        alertas.append(_alerta("gris", "Sin reportes", "Todavía no llega ningún reporte del motor. "
                               "Aparecerá después de la próxima corrida.", "sin_reportes"))
    nivel_franja = min((a["nivel"] for a in alertas), key=lambda n: _SEVERIDAD[n]) if alertas \
        else "verde"
    ultima = ultima_oficial or (ctx.recientes[0] if ctx.recientes else None)
    no_corrio = any(a["regla"] == "titular_no_corrio" for a in alertas)
    dato_de = (f"Dato de la corrida del {_fecha_corta(ctx.base.iniciada_en)}"
               if no_corrio and ctx.base is not None else None)

    filas = [ctx.fila_fuente(f, ctx.base, dato_de) for f in ctx.lee()]
    orden = {f["clave"]: i for i, f in enumerate(ctx.fuentes)}
    filas.sort(key=lambda x: (_SEVERIDAD[x["nivel"]], orden.get(x["clave"], 0)))

    estado_base = _fuentes_de(ctx.base) if ctx.base else {}
    reconoce = []
    for f in ctx.fuentes:
        if _uso(ctx.catalogo, f["clave"]) != "reconoce":
            continue
        reconoce.append({
            "clave": f["clave"], "nombre": f.get("nombre") or f["clave"],
            "incluye": f.get("incluye") or [], "excluye": f.get("excluye") or [],
            "archivos": [_archivo_out(a.get("carpeta"), a, ctx.carpetas)
                         for a in _archivos_estado(estado_base.get(f["clave"]))],
        })

    activacion = _activacion(db, ctx)
    sembrar_desde = []
    if ctx.cfg is None:
        vistos = set()
        for c in ctx.recientes:
            if c.pc in vistos or not isinstance(_cargar(c.config_efectiva, None), dict):
                continue
            vistos.add(c.pc)
            sembrar_desde.append({"corrida_id": c.id, "pc": c.pc, "alias": None, "tipo": c.tipo,
                                  "iniciada_en": _utc(c.iniciada_en)})

    return {
        "modo": ctx.modo,
        "modo_texto": {"sin_configurar": "Sin configurar", "prueba": "En prueba",
                       "activa": "Activa"}[ctx.modo],
        "version": ctx.fila.version if ctx.fila else None,
        "pc_titular": ctx.titular,
        "pc_titular_alias": alias_titular,
        "ahora": ahora,
        "franja": {"nivel": nivel_franja,
                   "ultima_corrida": _corrida_out(ultima, ctx.alias_de.get(ultima.pc))
                   if ultima else None,
                   "alertas": alertas},
        "corrida_id": ctx.base.id if ctx.base else None,
        "dato_de_corrida": dato_de,
        "fuentes": filas,
        "reconoce": reconoce,
        "carpetas_por_pc": _carpetas_por_pc(ctx),
        "activacion": activacion,
        "sembrar_desde": sembrar_desde,
    }


def _activacion(db: Session, ctx: _Contexto) -> dict:
    if ctx.cfg is None:
        return {"puede_activar": False, "corridas_necesarias": CORRIDAS_PARA_ACTIVAR,
                "corridas_en_verde": 0,
                "motivo": "Primero usa la configuración de un PC como punto de partida."}
    if ctx.cfg.modo == "activa":
        return {"puede_activar": False, "corridas_necesarias": CORRIDAS_PARA_ACTIVAR,
                "corridas_en_verde": 0, "motivo": "La configuración ya está activa."}
    ok, motivo, verdes = condicion_activar(db, ctx.fila, ctx.cfg)
    return {"puede_activar": ok, "motivo": motivo, "corridas_necesarias": CORRIDAS_PARA_ACTIVAR,
            "corridas_en_verde": verdes}


def _carpetas_por_pc(ctx: _Contexto) -> list[dict]:
    salida = []
    vistos: set[str] = set()
    orden = sorted(ctx.recientes, key=lambda c: (c.pc != ctx.titular,))
    for c in orden:
        if c.pc in vistos:
            continue
        listados = _listados_de(c)
        if not listados:
            continue
        vistos.add(c.pc)
        carpetas = []
        for clave, l in listados.items():
            cfg_c = ctx.carpetas.get(clave) or {}
            carpetas.append({
                "clave": clave, "nombre": cfg_c.get("nombre") or clave, "tipo": cfg_c.get("tipo"),
                "ruta_portable": l.get("ruta_portable"), "metodo": l.get("metodo"),
                "existe": bool(l.get("existe")), "archivos": len(_archivos_listado(l)),
                "truncado": bool(l.get("truncado")),
            })
        salida.append({"pc": c.pc, "alias": ctx.alias_de.get(c.pc), "es_titular": c.pc == ctx.titular,
                       "corrida_id": c.id, "tipo": c.tipo, "iniciada_en": _utc(c.iniciada_en),
                       "carpetas": carpetas})
    return salida


def corridas(db: Session, limite: int = 30) -> list[dict]:
    """`GET /corridas`: historial, con cuantas fuentes `lee` quedaron en cada color
    (evaluadas a la hora de cada corrida, no hoy)."""
    ctx = _Contexto(db, limite=limite + 20)
    salida = []
    for c in ctx.recientes[:limite]:
        resumen: dict[str, int] = {}
        if _fuentes_de(c):
            momento = a_chile(c.terminada_en or c.iniciada_en)
            for f in ctx.lee():
                n = ctx.semaforo_de(f, c, momento)["nivel"]
                resumen[n] = resumen.get(n, 0) + 1
        salida.append(_corrida_out(c, ctx.alias_de.get(c.pc), resumen))
    return salida


def detalle_fuente(db: Session, clave: str) -> dict:
    """`GET /{clave}`: configuracion, estado en las ultimas 20 corridas, competencia
    entre carpetas, descartados y versiones que la cambiaron."""
    ctx = _Contexto(db, limite=60)
    f = next((x for x in ctx.fuentes if x["clave"] == clave), None)
    if f is None:
        raise NoEncontrado(f"No existe la fuente '{clave}'.")
    cat = ctx.catalogo.get(clave)
    bloqueos: dict[str, str] = {}
    if cat and cat.get("requerida"):
        bloqueos["obligatoria"] = "Sin esta fuente el motor no calcula: tiene que ser obligatoria."
        bloqueos["activa"] = "Sin esta fuente el motor no calcula: no se puede desactivar."
    if cat and cat.get("frecuencia_max") is not None:
        bloqueos["frecuencia_dias"] = (f"El motor fija un plazo máximo de {cat['frecuencia_max']} "
                                       "días hábiles: con un dato más viejo el sugerido sale mal.")
    if cat and cat.get("al_vencer_fijo"):
        conducta = "frene la publicación" if cat["al_vencer_fijo"] == "frena" else "solo avise"
        bloqueos["al_vencer"] = f"El motor exige que esta fuente {conducta} si se atrasa."
    if cat and len(cat.get("modos") or []) == 1:
        bloqueos["modo"] = "Esta fuente solo se puede elegir de una forma."

    estado_base = _fuentes_de(ctx.base).get(clave) if ctx.base else None
    hoja = estado_base.get("hoja_leida") if isinstance(estado_base, dict) else None
    fila_enc = (estado_base.get("fila_encabezado") if isinstance(estado_base, dict) else None)
    if fila_enc is None:
        fila_enc = f.get("fila_encabezado")
    n_fila = (int(fila_enc) + 1) if isinstance(fila_enc, int) else 1
    if hoja is not None:
        hoja_texto = f"Automático (detectado: hoja '{hoja}', fila {n_fila})"
    elif f.get("hoja") is not None:
        hoja_texto = f"Hoja '{f['hoja']}', fila {n_fila}"
    else:
        hoja_texto = "Automático (todavía no se ha leído)"

    historia = []
    for c in ctx.recientes:
        estado = _fuentes_de(c).get(clave)
        if not isinstance(estado, dict):
            continue
        sem = ctx.semaforo_de(f, c, a_chile(c.terminada_en or c.iniciada_en))
        prueba = _texto_prueba(estado["prueba"], _obligatoria(f, ctx.catalogo)) \
            if isinstance(estado.get("prueba"), dict) else None
        hoja_leida = estado.get("hoja_leida")
        historia.append({
            "corrida_id": c.id, "pc": c.pc, "alias": ctx.alias_de.get(c.pc), "tipo": c.tipo,
            "iniciada_en": _utc(c.iniciada_en), "resultado": c.resultado,
            "hecho": _texto(estado.get("hecho")), "nivel": sem["nivel"],
            "etiqueta": sem["etiqueta"],
            "archivos": [_archivo_out(a.get("carpeta"), a, ctx.carpetas)
                         for a in _archivos_estado(estado)],
            "filas": _entero(estado.get("filas")),
            "hoja_leida": hoja_leida if isinstance(hoja_leida, (str, int)) else None,
            "prueba": prueba,
        })
        if len(historia) >= 20:
            break

    competencia = []
    if ctx.base is not None:
        listados = _listados_de(ctx.base)
        cands, _ = _candidatos(f, ctx.fuentes, listados, ctx.ahora.date())
        elegidos = {(a.get("carpeta"), _norm(_ruta(a["ruta_relativa"])))
                    for a in _archivos_estado(estado_base)}
        por_carpeta: dict[str, list[dict]] = {}
        for carpeta, a in cands:
            por_carpeta.setdefault(carpeta, []).append(
                _archivo_carpeta_out(a, elegido=(carpeta, _norm(_ruta(a["ruta_relativa"]))) in elegidos))
        for carpeta, lista in por_carpeta.items():
            competencia.append({
                "carpeta": carpeta,
                "carpeta_nombre": (ctx.carpetas.get(carpeta) or {}).get("nombre"),
                "ruta_absoluta": (listados.get(carpeta) or {}).get("ruta_absoluta"),
                "candidatos": lista,
            })

    descartados = []
    if isinstance(estado_base, dict):
        ant = ctx.anterior_de(ctx.base)
        ant_estado = _fuentes_de(ant).get(clave) if ant else None
        antes = {str(d.get("nombre")) for d in (ant_estado or {}).get("descartados") or []
                 if isinstance(d, dict)}
        for d in estado_base.get("descartados") or []:
            if isinstance(d, dict) and d.get("nombre"):
                descartados.append({"nombre": str(d["nombre"]), "motivo": _texto(d.get("motivo")),
                                    "nuevo": ant_estado is not None and str(d["nombre"]) not in antes})

    return {
        "clave": clave, "nombre": f.get("nombre") or clave,
        "uso": (cat or {}).get("uso"), "modo": ctx.modo,
        "version": ctx.fila.version if ctx.fila else None,
        "config": f, "catalogo": cat, "bloqueos": bloqueos, "hoja_texto": hoja_texto,
        "estado": ctx.fila_fuente(f, ctx.base) if ctx.base else None,
        "corridas": historia, "competencia": competencia, "descartados": descartados,
        "versiones": historial(db, clave) if ctx.fila else [],
    }


def _archivo_carpeta_out(a: dict, *, elegido: bool | None = None) -> dict:
    ruta = _ruta(a.get("ruta_relativa"))
    nombre = _nombre_de(ruta)
    return {
        "ruta_relativa": ruta, "nombre": nombre,
        "subcarpeta": ruta.rsplit("/", 1)[0] if "/" in ruta else "",
        "tamano": _entero(a.get("tamano")), "modificado_en": _fecha_archivo(a.get("modificado_en")),
        "onedrive": _texto(a.get("onedrive")), "fuente": _texto(a.get("fuente")),
        "elegido": bool(a.get("elegido")) if elegido is None else elegido,
        "patron_propuesto": proponer_patron(nombre),
    }


def archivos_de_carpeta(db: Session, clave: str, pc: str | None = None) -> dict:
    """`GET /carpetas/{clave}/archivos?pc=`: el ultimo listado de esa carpeta en ese PC
    (por defecto el titular), para armar los selectores del editor."""
    ctx = _Contexto(db, limite=60)
    pc = pc or ctx.titular
    nombre = (ctx.carpetas.get(clave) or {}).get("nombre")
    for c in ctx.recientes:
        if c.pc != pc:
            continue
        listado = _listados_de(c).get(clave)
        if listado is None:
            continue
        archivos = [_archivo_carpeta_out(a) for a in _archivos_listado(listado)]
        subcarpetas: set[str] = set()
        for a in archivos:
            partes = a["subcarpeta"].split("/") if a["subcarpeta"] else []
            for i in range(1, len(partes) + 1):
                subcarpetas.add("/".join(partes[:i]))
        return {
            "clave": clave, "nombre": nombre, "pc": pc, "alias": ctx.alias_de.get(pc or ""),
            "corrida_id": c.id, "iniciada_en": _utc(c.iniciada_en),
            "existe": bool(listado.get("existe")), "metodo": listado.get("metodo"),
            "ruta_portable": listado.get("ruta_portable"),
            "ruta_absoluta": listado.get("ruta_absoluta"),
            "truncado": bool(listado.get("truncado")),
            "subcarpetas": sorted(subcarpetas, key=_norm), "archivos": archivos,
        }
    return {"clave": clave, "nombre": nombre, "pc": pc, "alias": ctx.alias_de.get(pc or ""),
            "subcarpetas": [], "archivos": []}


# --------------------------------------------------------------------------- #
# Campanita a los admins (Anexo C, punto 4)
# --------------------------------------------------------------------------- #
_TITULO_RESULTADO = {
    "frenada": "Fuentes de datos: la corrida no publicó",
    "fallo": "Fuentes de datos: la corrida falló",
    "incompleta": "Fuentes de datos: la corrida publicó, pero algunos pasos fallaron",
}


def _avisar_admins(db: Session, corrida: MotorCorrida, usuario: str | None) -> int:
    """Aviso PERSONAL (`para_email`) a cada admin activo, sin el usuario que reporta
    (el del motor), como maximo uno al dia por admin y por motivo. Se dispara al
    recibir el fin de una corrida oficial frenada, fallida o incompleta, o con alguna
    fuente en rojo. "El PC titular no corrió hoy" queda solo en el panel: si no corre
    nada, no hay quien lo revise.

    Nunca rompe el reporte: si algo falla aca, el reporte ya quedo guardado."""
    try:
        if corrida.resultado == "no_titular":
            return 0
        motivos: list[tuple[str, str, str]] = []
        if corrida.resultado in _TITULO_RESULTADO:
            motivos.append((corrida.resultado, _TITULO_RESULTADO[corrida.resultado],
                            traducir_motivo(corrida.motivo) or "Revisa el panel de Fuentes de datos."))
        ctx = _Contexto(db, limite=40)
        momento = a_chile(corrida.terminada_en or corrida.iniciada_en)
        for f in ctx.lee():
            if not f.get("activa", True) or f["clave"] not in _fuentes_de(corrida):
                continue
            sem = ctx.semaforo_de(f, corrida, momento)
            if sem["nivel"] == "rojo":
                motivos.append((f"rojo:{f['clave']}",
                                f"Fuentes de datos: {f.get('nombre') or f['clave']} en rojo "
                                f"({sem['etiqueta'].lower()})", sem["texto"]))
        if not motivos:
            return 0
        admins = db.scalars(
            select(Usuario).where(Usuario.es_admin.is_(True), Usuario.activo.is_(True))
        ).all()
        desde = inicio_del_dia_chile(ahora_chile().date())
        enviados = 0
        for admin in admins:
            if usuario and admin.email.lower() == usuario.lower():
                continue
            for clave, titulo, mensaje in motivos:
                tipo = f"{TIPO_AVISO}:{clave}"
                ya = db.scalars(
                    select(Notificacion.id).where(
                        Notificacion.tenant_id == settings.default_tenant_id,
                        Notificacion.para_email == admin.email,
                        Notificacion.tipo == tipo,
                        Notificacion.creado_en >= desde,
                    ).limit(1)
                ).first()
                if ya:
                    continue
                if auditoria_service.notificar(
                    db, tipo=tipo, titulo=titulo[:250], mensaje=mensaje,
                    creado_por_email=usuario, para_email=admin.email,
                ):
                    enviados += 1
        db.commit()
        return enviados
    except Exception:  # noqa: BLE001 - la campanita no puede botar el reporte
        db.rollback()
        return 0
