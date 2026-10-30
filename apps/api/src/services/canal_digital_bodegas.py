"""Canal Digital: parametros de cada bodega (leer, validar, editar y crear).

Usa la tabla que ya existe (`canal_digital_bodega`): ninguna tabla nueva, ningun historial. Las listas (tipos de
venta y bodegas del ERP) se guardan como texto separado por coma; aqui se convierten a listas y se normalizan
(sin vacios, sin duplicados, sin espacios sobrantes).

Editar valida TODO antes de tocar la fila: si algo esta mal no se guarda nada y se informan todos los problemas
juntos. Las funciones de aqui no conocen HTTP.
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..canal_digital.clasificacion import ParametrosClasificacion
from ..canal_digital.politica import BODEGA_CANAL_DIGITAL
from ..canal_digital.reposicion import ParametrosReposicion
from ..models import CanalDigitalBodega, CanalDigitalLinea
from .canal_digital_calculo import _clave
from .canal_digital_service import _tenant, asegurar_bodega

# Los umbrales de frecuencia (A 8 a 12 meses con venta, B 5 a 7, C 1 a 4) estan atados a 12 meses.
VENTANA_MESES = 12
MAX_LARGO = 60  # caracteres de un nombre o de un elemento de lista
MAX_ELEMENTOS = 20  # por lista: las respuestas y la base se mantienen chicas
_CODIGO = re.compile(r"[A-Za-z0-9]{1,12}", re.ASCII)

LISTAS = ("tipos_venta", "bodegas_stock", "bodegas_aparte", "bodegas_informativas")
EDITABLES = ("nombre", "activa", "tipos_venta", "r_semanas", "nuevo_meses", "corte_a_pct", "corte_b_pct",
             "gestion_dias", "bodegas_stock", "bodegas_aparte", "bodegas_informativas")

# Como nombra cada campo la pantalla: los mensajes usan estas mismas palabras.
ETIQUETA = {
    "nombre": "El nombre",
    "activa": "«Bodega activa»",
    "tipos_venta": "«Tipos de venta que cuentan como venta del canal»",
    "r_semanas": "«Semanas entre revisiones»",
    "nuevo_meses": "«Meses para considerar nuevo un producto»",
    "corte_a_pct": "El corte A del Pareto",
    "corte_b_pct": "El corte B del Pareto",
    "gestion_dias": "«Días de gestión que se suman al plazo»",
    "bodegas_stock": "«Bodegas cuyo stock cuenta como disponible»",
    "bodegas_aparte": "«Bodegas que se muestran aparte (no suman)»",
    "bodegas_informativas": "«Bodegas solo informativas»",
}


def _lineas(n: int) -> str:
    return f"{n} {'línea guardada' if n == 1 else 'líneas guardadas'}"


def avisos_tipos_venta(db: Session, bodega: str, antes: list[str], despues: list[str]) -> list[str]:
    """Lo que hay que saber al cambiar los tipos de venta, con las cifras de lo que hay guardado (sin tablas nuevas).

    Guardar NO toca la venta que ya esta guardada. Pero la proxima carga de lineas del ERP vuelve a armar la venta de
    TODOS los meses que tienen lineas guardadas, no solo del mes que se envia: un tipo que se quita deja de contar en
    todos esos meses; uno que se agrega solo suma donde haya lineas de ese tipo guardadas, y las de un tipo que no
    contaba no se guardaron. Solo cambiar el orden no avisa nada."""
    quitados = [t for t in antes if t not in despues]
    agregados = [t for t in despues if t not in antes]
    if not quitados and not agregados:
        return []
    L = CanalDigitalLinea
    guardadas = dict(
        db.execute(
            select(L.tipo_venta, func.count()).where(
                L.tenant_id == _tenant(), L.bodega == bodega, L.tipo_venta.in_(quitados + agregados)
            ).group_by(L.tipo_venta)
        ).all()
    )
    avisos = [
        "La venta que ya está guardada no cambia al guardar. En la próxima carga de líneas del ERP se vuelve a armar "
        "la venta de TODOS los meses que tienen líneas guardadas (no solo la del mes que se envía), con los tipos nuevos."
    ]
    if quitados:
        n = sum(guardadas.get(t, 0) for t in quitados)
        avisos.append(
            f"Los tipos que quitaste ({', '.join(quitados)}) dejan de contar en todos los meses: "
            + (f"hoy hay {_lineas(n)} de esos tipos." if n else "no hay líneas guardadas de esos tipos, así que no cambia nada.")
        )
    if agregados:
        n = sum(guardadas.get(t, 0) for t in agregados)
        avisos.append(
            f"Los tipos que agregaste ({', '.join(agregados)}) "
            + (f"ya tienen {_lineas(n)}, que se suman en esa carga; el resto solo suma si se vuelve a enviar su mes."
               if n else "solo suman en los meses cuyas líneas se vuelvan a enviar: las líneas de un tipo que no "
                         "contaba no se guardaron.")
        )
    return avisos



class ParametrosInvalidos(Exception):
    """Algo de lo que llego no se puede guardar. `problemas` los trae todos, en palabras de la pantalla."""

    def __init__(self, problemas: list[str]):
        super().__init__("; ".join(problemas))
        self.problemas = problemas


class BodegaNoExiste(Exception):
    pass


class BodegaYaExiste(Exception):
    pass


def normalizar_codigo_bodega(valor) -> str | None:
    """El codigo en mayusculas, o None si no sirve (1 a 12 letras o numeros, sin espacios ni signos).

    Es la unica regla de codigos: la usan el alta de bodegas y los envios del motor, para que no existan dos bodegas
    que difieren solo en el caso ni una a la que la direccion de la pantalla no pueda llegar."""
    if not isinstance(valor, str):
        return None
    t = valor.strip()
    return t.upper() if _CODIGO.fullmatch(t) else None


def _fmt(x) -> str:
    """Numero con coma decimal: 1.5 -> "1,5"; 8.0 -> "8"."""
    return f"{x:g}".replace(".", ",") if isinstance(x, float) else str(x)


# --------------------------------------------------------------------------- listas

def normalizar_lista(elementos, por_clave: bool) -> list[str]:
    """Sin vacios, sin duplicados y sin espacios sobrantes, en el orden en que vienen.

    `por_clave`: las bodegas del ERP se comparan sin signos ni espacios (como en el calculo), asi que "Bodega ML"
    y "BODEGA-ML" son la misma; los tipos de venta se comparan tal cual, que es como se filtran las lineas."""
    vistos: set[str] = set()
    out: list[str] = []
    for e in elementos:
        t = str(e).strip()
        k = _clave(t) if por_clave else t
        if not t or k in vistos:
            continue
        vistos.add(k)
        out.append(t)
    return out


def _de_texto(txt: str | None, por_clave: bool) -> list[str]:
    return normalizar_lista(str(txt or "").split(","), por_clave)


def _a_texto(lista: list[str]) -> str:
    return ",".join(lista)


def _lista_valida(valor, campo: str, problemas: list[str]) -> list[str] | None:
    """La lista normalizada, o None (y un problema) si lo que llego no es una lista de textos que se pueda guardar."""
    if not isinstance(valor, list):
        problemas.append(f"{ETIQUETA[campo]} debe ser una lista de textos.")
        return None
    if any(not isinstance(e, str) for e in valor):
        problemas.append(f"{ETIQUETA[campo]} solo puede tener textos.")
        return None
    por_clave = campo != "tipos_venta"
    lista = normalizar_lista(valor, por_clave)
    ok = True
    for t in lista:
        if "," in t:
            problemas.append(f"{ETIQUETA[campo]}: «{t}» lleva una coma; escribe cada elemento por separado.")
            ok = False
        elif len(t) > MAX_LARGO:
            problemas.append(f"{ETIQUETA[campo]}: «{t[:20]}…» pasa de {MAX_LARGO} caracteres.")
            ok = False
        elif por_clave and not _clave(t):
            problemas.append(f"{ETIQUETA[campo]}: «{t}» no tiene letras ni números.")
            ok = False
    if len(lista) > MAX_ELEMENTOS:
        problemas.append(f"{ETIQUETA[campo]} admite hasta {MAX_ELEMENTOS} elementos (llegaron {len(lista)}).")
        ok = False
    return lista if ok else None


# --------------------------------------------------------------------------- numeros

def _numero(valor, campo: str, problemas: list[str]) -> float | None:
    """Un numero finito. Un booleano, un texto, NaN o infinito no son numeros."""
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        problemas.append(f"{ETIQUETA[campo]} debe ser un número.")
        return None
    try:
        x = float(valor)
    except OverflowError:  # un entero JSON gigante
        x = math.inf
    if not math.isfinite(x):
        problemas.append(f"{ETIQUETA[campo]} debe ser un número finito.")
        return None
    return x


def _entre(valor, campo: str, minimo: float, maximo: float, problemas: list[str]) -> float | None:
    x = _numero(valor, campo, problemas)
    if x is not None and not minimo <= x <= maximo:
        problemas.append(f"{ETIQUETA[campo]} debe estar entre {_fmt(minimo)} y {_fmt(maximo)} (llegó {_fmt(x)}).")
        return None
    return x


def _texto_corto(valor, campo: str, problemas: list[str]) -> str | None:
    if not isinstance(valor, str):
        problemas.append(f"{ETIQUETA[campo]} debe ser un texto.")
        return None
    t = valor.strip()
    if not t:
        problemas.append(f"{ETIQUETA[campo]} no puede quedar vacío.")
        return None
    if len(t) > MAX_LARGO:
        problemas.append(f"{ETIQUETA[campo]} pasa de {MAX_LARGO} caracteres.")
        return None
    return t


# --------------------------------------------------------------------------- lectura

def a_json(f: CanalDigitalBodega) -> dict:
    return {
        "bodega": f.bodega, "nombre": f.nombre, "activa": bool(f.activa),
        "tipos_venta": _de_texto(f.tipos_venta, por_clave=False),
        "r_semanas": f.r_semanas, "ventana_meses": f.ventana_meses, "nuevo_meses": f.nuevo_meses,
        "corte_a_pct": f.corte_a_pct, "corte_b_pct": f.corte_b_pct, "gestion_dias": f.gestion_dias,
        "bodegas_stock": _de_texto(f.bodegas_stock, por_clave=True),
        "bodegas_aparte": _de_texto(f.bodegas_aparte, por_clave=True),
        "bodegas_informativas": _de_texto(f.bodegas_informativas, por_clave=True),
    }


def buscar(db: Session, bodega: str) -> CanalDigitalBodega | None:
    return db.execute(
        select(CanalDigitalBodega).where(CanalDigitalBodega.tenant_id == _tenant(), CanalDigitalBodega.bodega == bodega)
    ).scalar_one_or_none()


def _sembrar_defecto(db: Session) -> None:
    """Crea la bodega por defecto (y su politica provisoria). Si otra peticion la creo al mismo tiempo, no pasa nada."""
    try:
        asegurar_bodega(db, BODEGA_CANAL_DIGITAL)
    except IntegrityError:
        db.rollback()


def _todas(db: Session) -> list[CanalDigitalBodega]:
    return list(db.execute(select(CanalDigitalBodega).where(CanalDigitalBodega.tenant_id == _tenant())).scalars())


def listar(db: Session) -> list[dict]:
    """Las bodegas del canal, la por defecto primero. Es una lectura: solo la por defecto se siembra, y una sola vez.

    Se siembra siempre que falte (como en el resumen y la politica): el selector de la pantalla tiene que poder
    ofrecerla aunque la tabla tenga otras bodegas."""
    filas = _todas(db)
    if not any(f.bodega == BODEGA_CANAL_DIGITAL for f in filas):
        _sembrar_defecto(db)
        filas = _todas(db)
    filas = sorted(filas, key=lambda f: (f.bodega != BODEGA_CANAL_DIGITAL, f.bodega))
    return [a_json(f) for f in filas]


# --------------------------------------------------------------------------- validacion

def validar(cambios: dict, actual: dict, bodega: str) -> dict:
    """Los valores finales de la bodega (los actuales con los `cambios` ya normalizados), o `ParametrosInvalidos`.

    Se valida el resultado completo, no solo lo que llego: un corte nuevo se compara con el otro corte que ya
    estaba guardado. Junta todos los problemas en una sola respuesta."""
    problemas: list[str] = []
    final = {k: actual[k] for k in EDITABLES}
    malos: set[str] = set()  # campos que llegaron mal: no se les revisan las reglas cruzadas

    for campo in cambios:
        if campo == "ventana_meses":
            v = cambios[campo]
            if isinstance(v, bool) or not isinstance(v, (int, float)) or v != VENTANA_MESES:
                problemas.append(
                    f"La ventana es de {VENTANA_MESES} meses y no se puede cambiar: los umbrales de frecuencia "
                    f"(A de 8 a 12 meses con venta, B de 5 a 7, C de 1 a 4) están pensados para {VENTANA_MESES} meses."
                )
            continue
        if campo == "bodega":
            if cambios[campo] != bodega:
                problemas.append(f"La bodega del cuerpo ({cambios[campo]!r}) no es la de la dirección ({bodega}).")
            continue
        if campo not in EDITABLES:
            problemas.append(f"«{campo}» no es un parámetro que se pueda cambiar.")
            continue
        n_antes = len(problemas)
        v = cambios[campo]
        if campo == "nombre":
            nuevo = _texto_corto(v, campo, problemas)
        elif campo == "activa":
            nuevo = v
            if not isinstance(v, bool):
                problemas.append(f"{ETIQUETA[campo]} debe ser verdadero o falso.")
        elif campo in LISTAS:
            nuevo = _lista_valida(v, campo, problemas)
        elif campo == "r_semanas":
            nuevo = _entre(v, campo, 0, 8, problemas)
        elif campo == "gestion_dias":
            nuevo = _entre(v, campo, 0, 30, problemas)
        elif campo == "nuevo_meses":
            x = _entre(v, campo, 1, 12, problemas)
            nuevo = int(x) if x is not None else None
            if x is not None and x != int(x):
                problemas.append(f"{ETIQUETA[campo]} debe ser un número entero (llegó {_fmt(x)}).")
                nuevo = None
        else:  # corte_a_pct, corte_b_pct
            nuevo = _entre(v, campo, 0, 100, problemas)
            if nuevo == 0:
                problemas.append(f"{ETIQUETA[campo]} debe ser mayor que 0.")
        if len(problemas) > n_antes or nuevo is None:
            malos.add(campo)
        else:
            final[campo] = nuevo

    # reglas que cruzan campos
    for campo in ("tipos_venta", "bodegas_stock"):
        if campo not in malos and not final[campo]:
            problemas.append(f"{ETIQUETA[campo]} no puede quedar vacío.")
    if not malos & {"corte_a_pct", "corte_b_pct"} and not 0 < final["corte_a_pct"] < final["corte_b_pct"] <= 100:
        problemas.append(
            f"El corte A ({_fmt(float(final['corte_a_pct']))}) debe ser menor que el corte B "
            f"({_fmt(float(final['corte_b_pct']))}), y el corte B no puede pasar de 100."
        )
    por_lista = {c: {_clave(t) for t in final[c]} for c in LISTAS[1:] if c not in malos}
    nombres = {c: {_clave(t): t for t in final[c]} for c in por_lista}
    pares = [("bodegas_stock", "bodegas_aparte"), ("bodegas_stock", "bodegas_informativas"),
             ("bodegas_aparte", "bodegas_informativas")]
    for a, b in pares:
        if a in por_lista and b in por_lista:
            for k in sorted(por_lista[a] & por_lista[b]):
                problemas.append(
                    f"La bodega «{nombres[a][k]}» está en {ETIQUETA[a]} y en {ETIQUETA[b]}: "
                    "cada bodega va en una sola lista."
                )

    if not problemas:  # ultima red: lo que se guarda tiene que poder calcularse
        try:
            ParametrosClasificacion(
                ventana_meses=VENTANA_MESES, nuevo_meses=final["nuevo_meses"],
                corte_a_pct=final["corte_a_pct"], corte_b_pct=final["corte_b_pct"],
            )
            ParametrosReposicion(r_semanas=final["r_semanas"])
        except ValueError as e:
            problemas.append(f"Los parámetros no se pueden calcular: {e}.")
    if problemas:
        raise ParametrosInvalidos(problemas)
    return final


def _valores_actuales(f: CanalDigitalBodega) -> dict:
    j = a_json(f)
    return {k: j[k] for k in EDITABLES}


def actualizar(db: Session, bodega: str, cambios: dict, email: str | None) -> tuple[dict, dict, list[str]]:
    """Guarda `cambios` en la bodega. Devuelve (bodega, {campo: (antes, despues)} de lo que cambio, avisos).

    La bodega por defecto se siembra si falta (como en la politica); cualquier otra debe existir. No hace commit:
    quien llama registra la auditoria y confirma, para que todo quede en la misma transaccion."""
    fila = buscar(db, bodega)
    if fila is None and bodega == BODEGA_CANAL_DIGITAL:
        fila = asegurar_bodega(db, bodega)
    if fila is None:
        raise BodegaNoExiste(bodega)
    actual = _valores_actuales(fila)
    final = validar(cambios, actual, bodega)
    cambiado = {k: (actual[k], final[k]) for k in EDITABLES if final[k] != actual[k]}
    avisos: list[str] = []
    if cambiado:
        for k, (_, despues) in cambiado.items():
            setattr(fila, k, _a_texto(despues) if k in LISTAS else despues)
        fila.actualizado_en = datetime.now(timezone.utc).replace(tzinfo=None)
        db.flush()
        if "tipos_venta" in cambiado:
            avisos += avisos_tipos_venta(db, bodega, *cambiado["tipos_venta"])
    return a_json(fila), cambiado, avisos


# --------------------------------------------------------------------------- crear

def crear(db: Session, payload: dict) -> dict:
    """Crea una bodega nueva con los parametros de siembra y su politica provisoria de 27 filas."""
    problemas: list[str] = []
    codigo = normalizar_codigo_bodega(payload.get("bodega"))
    if codigo is None:
        problemas.append("El código de la bodega debe tener de 1 a 12 letras o números, sin espacios ni signos.")
    nombre = payload.get("nombre")
    if nombre is None:
        nombre = f"Canal digital {codigo}" if codigo else None
    else:
        nombre = _texto_corto(nombre, "nombre", problemas)
    desconocidos = sorted(set(payload) - {"bodega", "nombre"})
    for k in desconocidos:
        problemas.append(f"«{k}» no se pide al crear una bodega: los parámetros se ajustan después, en la pestaña Bodegas.")
    if problemas:
        raise ParametrosInvalidos(problemas)
    if buscar(db, BODEGA_CANAL_DIGITAL) is None:
        _sembrar_defecto(db)  # la por defecto existe siempre que exista alguna otra
    # El codigo se compara sin importar mayusculas: una bodega cargada antes en minusculas tambien cuenta como repetida.
    if db.execute(
        select(CanalDigitalBodega.id).where(
            CanalDigitalBodega.tenant_id == _tenant(), func.upper(CanalDigitalBodega.bodega) == codigo
        )
    ).first() is not None:
        raise BodegaYaExiste(codigo)
    try:
        fila = asegurar_bodega(db, codigo, nombre)
    except IntegrityError:  # otra peticion creo el mismo codigo al mismo tiempo
        db.rollback()
        raise BodegaYaExiste(codigo)
    return a_json(fila)


__all__ = [
    "BodegaNoExiste", "BodegaYaExiste", "ParametrosInvalidos", "a_json", "actualizar", "avisos_tipos_venta", "buscar",
    "crear", "listar", "normalizar_codigo_bodega", "normalizar_lista", "validar",
]
