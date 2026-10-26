"""Canal Digital: acceso a las tablas del modulo (bodega, venta semanal, politica).

El nucleo de calculo vive en `src.canal_digital` y no conoce la base de datos; aqui se lee
y se escribe lo que ese nucleo necesita.
"""
from __future__ import annotations

import datetime as dt
import math
import re
import threading
from collections import Counter
from datetime import datetime, timezone

from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import Session

from ..canal_digital.politica import (
    BODEGA_CANAL_DIGITAL, CLUSTERS, FilaPolitica, Politica, filas_provisorias,
)
from ..canal_digital.ventas_semanales import (
    TIPOS_VENTA_DEFECTO, LineaVenta, agregar, indice_originales, normalizar_codigo, normalizar_numero,
)
from ..config import get_settings
from ..models import CanalDigitalBodega, CanalDigitalLinea, CanalDigitalPolitica, CanalDigitalVenta
from .excel_loader import _insertar_en_lote

settings = get_settings()
_LOTE = 1000
_BORRAR_POR_LOTE = 500  # ids por DELETE ... IN (...): lejos del tope de parametros de cualquier driver

# Una carga a la vez. Dos envios que se pisan (el reintento del motor sobre un envio que sigue en curso) arman
# la venta cada uno con la foto que ve y los dos borran e insertan las mismas filas de canal_digital_venta: el
# segundo puede chocar con uq_cd_venta y fallar con un 500, y ese mes no se carga. El segundo espera al primero
# y despues reemplaza, igual que si hubiera llegado despues. La API corre con un solo proceso en Render (ver
# `excel_loader.CARGA_SUGERIDO`), asi que un candado del proceso alcanza.
CARGA_CANAL_DIGITAL = threading.RLock()

# Un envio que deja un periodo con menos de la mitad de las lineas que tenia (y tenia al menos 20) casi seguro no
# trae el mes completo: se rechaza salvo que venga "forzar". Un mes chico no dispara la guarda.
_GUARDA_MIN_LINEAS = 20


class ConflictoCarga(Exception):
    """La carga se rechaza sin tocar nada. `detalle` es lo que el endpoint devuelve en el 409."""

    def __init__(self, detalle: dict):
        super().__init__(detalle.get("mensaje", ""))
        self.detalle = detalle


def _tenant() -> str:
    return settings.default_tenant_id


def asegurar_bodega(db: Session, bodega: str = BODEGA_CANAL_DIGITAL) -> CanalDigitalBodega:
    """Crea la bodega con sus parametros de siembra y su politica provisoria si aun no existen."""
    fila = db.execute(
        select(CanalDigitalBodega).where(
            CanalDigitalBodega.tenant_id == _tenant(), CanalDigitalBodega.bodega == bodega
        )
    ).scalar_one_or_none()
    if fila is None:
        fila = CanalDigitalBodega(
            tenant_id=_tenant(), bodega=bodega, nombre=f"Canal digital {bodega}",
            actualizado_en=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        db.add(fila)
        db.flush()
    existentes = set(
        db.execute(
            select(CanalDigitalPolitica.cluster).where(
                CanalDigitalPolitica.tenant_id == _tenant(), CanalDigitalPolitica.bodega == bodega
            )
        ).scalars()
    )
    faltan = [f for f in filas_provisorias(bodega) if f.cluster not in existentes]
    for f in faltan:
        db.add(
            CanalDigitalPolitica(
                tenant_id=_tenant(), bodega=bodega, cluster=f.cluster, modo=f.modo,
                nivel_servicio=f.nivel_servicio, z=f.z, minimo_fijo=f.minimo_fijo,
                actualizado_por="siembra provisoria", actualizado_en=datetime.now(timezone.utc).replace(tzinfo=None),
            )
        )
    db.commit()
    return fila


def leer_politica(db: Session, bodega: str = BODEGA_CANAL_DIGITAL) -> Politica:
    """Las 27 filas guardadas. Falla (PoliticaInvalida) si la tabla no tiene exactamente los 27 clusters."""
    filas = db.execute(
        select(CanalDigitalPolitica).where(
            CanalDigitalPolitica.tenant_id == _tenant(), CanalDigitalPolitica.bodega == bodega
        )
    ).scalars().all()
    return Politica(
        bodega,
        tuple(
            FilaPolitica(bodega, f.cluster, f.modo, f.nivel_servicio, f.z, f.minimo_fijo)
            for f in filas
        ),
    )


def reemplazar_ventas(db: Session, bodega: str, filas: list[dict]) -> dict:
    """Carga la venta semanal del canal reemplazando SOLO los periodos (del documento) que vienen.

    Ruta heredada: la venta llega ya agregada. Desde que existe `reemplazar_lineas`, un periodo que tiene lineas
    queda gobernado por ellas (cada envio de lineas recalcula la venta de todos sus periodos), asi que cargarle
    una venta aparte se rechaza con `ConflictoCarga` en vez de dejar que el proximo envio la revierta en silencio.

    Cada fila: {producto, semana (YYYY-MM-DD lunes), periodo (YYYYMM), unid_brutas,
    unid_devueltas, valor_costo, unid_liquidacion, n_lineas}. Las filas mal formadas se
    cuentan como ignoradas, no se cargan a medias.
    """
    with CARGA_CANAL_DIGITAL:
        return _reemplazar_ventas(db, bodega, filas)


def _reemplazar_ventas(db: Session, bodega: str, filas: list[dict]) -> dict:
    tenant = _tenant()
    validas: dict[tuple[str, str, str], dict] = {}
    for f in filas:
        periodo = str(f.get("periodo") or "").strip()
        producto = str(f.get("producto") or "").strip()
        semana = str(f.get("semana") or "").strip()
        if len(periodo) != 6 or not periodo.isdigit() or not producto or len(semana) != 10:
            continue
        try:
            datetime.strptime(semana, "%Y-%m-%d")
            fila = {
                "tenant_id": tenant, "bodega": bodega, "producto": producto,
                "semana": semana, "periodo": periodo,
                "unid_brutas": float(f.get("unid_brutas") or 0),
                "unid_devueltas": float(f.get("unid_devueltas") or 0),
                "valor_costo": float(f.get("valor_costo") or 0),
                "unid_liquidacion": float(f.get("unid_liquidacion") or 0),
                "n_lineas": int(f.get("n_lineas") or 0),
            }
        except (TypeError, ValueError):
            continue
        clave = (producto, semana, periodo)
        if clave in validas:  # la misma clave dos veces: se suman, no se pisan
            v = validas[clave]
            for k in ("unid_brutas", "unid_devueltas", "valor_costo", "unid_liquidacion", "n_lineas"):
                v[k] += fila[k]
        else:
            validas[clave] = fila
    if not validas:
        return {"filas_cargadas": 0, "ignoradas": len(filas), "periodos": []}
    periodos = sorted({k[2] for k in validas})
    con_lineas = sorted(
        db.execute(
            select(CanalDigitalLinea.periodo).where(
                CanalDigitalLinea.tenant_id == tenant, CanalDigitalLinea.bodega == bodega,
                CanalDigitalLinea.periodo.in_(periodos),
            ).distinct()
        ).scalars()
    )
    if con_lineas:
        raise ConflictoCarga({
            "mensaje": f"Los periodos {', '.join(con_lineas)} ya tienen lineas del ERP y la venta se arma con ellas: "
                       "envialos por /lineas. No se cargo nada.",
            "periodos_con_lineas": con_lineas,
        })
    db.execute(
        delete(CanalDigitalVenta).where(
            CanalDigitalVenta.tenant_id == tenant, CanalDigitalVenta.bodega == bodega,
            CanalDigitalVenta.periodo.in_(periodos),
        )
    )
    lista = list(validas.values())
    for i in range(0, len(lista), _LOTE):
        db.execute(insert(CanalDigitalVenta), lista[i : i + _LOTE])
    db.commit()
    return {"filas_cargadas": len(lista), "ignoradas": len(filas) - len(lista), "periodos": periodos}


def _tipos_venta(fila: CanalDigitalBodega | None) -> tuple[str, ...]:
    """Los tipos de venta que cuentan para la bodega (separados por coma). Sin fila de bodega, los de siembra."""
    if fila is None:
        return TIPOS_VENTA_DEFECTO
    return tuple(t.strip() for t in (fila.tipos_venta or "").split(",") if t.strip())


def _texto(valor) -> str:
    """Texto de un campo que pudo venir como numero (202610 o 202610.0)."""
    if valor is None or isinstance(valor, bool):
        return ""
    if isinstance(valor, float) and math.isfinite(valor) and valor == int(valor):
        valor = int(valor)
    return str(valor).strip()


def _numero_documento(valor) -> str:
    """Numero de documento sin ceros a la izquierda ni '.0': '007720' -> '7720', '835066.0' -> '835066'."""
    return re.sub(r"\.0+$", "", normalizar_numero(_texto(valor) or None))


def _finito(valor) -> float | None:
    """float finito, o None si no sirve (ausente, booleano, texto que no es numero, NaN, infinito, desborde)."""
    if valor is None or isinstance(valor, bool):
        return None
    try:
        x = float(valor)
    except (TypeError, ValueError, OverflowError):
        return None
    return x if math.isfinite(x) else None


def _costo(valor) -> tuple[float, bool]:
    """(costo unitario, ajustado). Un costo ausente, en blanco o que no es un numero finito (el NaN con que pandas
    escribe una celda vacia) vale 0 y se cuenta: afecta al valor, no a las unidades, y no vale una venta perdida."""
    x = _finito(valor)
    return (0.0, True) if x is None else (x, False)


# Fecha y periodo se leen con las mismas reglas que despues los consume `_recalcular` (solo ASCII: `isdigit` y
# `strptime` aceptan digitos arabes, de ancho completo y espacios que `date.fromisoformat` rechaza). La fecha
# puede traer hora; el periodo, el ".0" de una celda numerica de Excel.
_PERIODO = re.compile(r"(\d{4})(0[1-9]|1[0-2])(?:\.0+)?", re.ASCII)
_FECHA = re.compile(r"(\d{4})-(\d{2})-(\d{2})(?:[T ].*)?", re.ASCII)


def _validar_linea(l, tipos: tuple[str, ...], bodega: str) -> tuple[dict | None, str, bool]:
    """(fila lista para insertar, "", costo_en_cero) o (None, motivo, False).

    Motivos: "tipo_venta" (no es del canal) o "invalida:<campo>" (el campo que no sirve). Nunca lanza: lo que no se
    puede leer es una linea invalida, no un error del envio."""
    if not isinstance(l, dict):
        return None, "invalida:linea", False
    try:
        return _leer_linea(l, tipos, bodega)
    except (ValueError, TypeError, OverflowError):
        return None, "invalida:formato", False


def _leer_linea(l: dict, tipos: tuple[str, ...], bodega: str) -> tuple[dict | None, str, bool]:
    tipo_venta = _texto(l.get("tipo_venta"))
    if tipo_venta not in tipos:
        return None, "tipo_venta", False
    m = _PERIODO.fullmatch(_texto(l.get("periodo")))
    if m is None:
        return None, "invalida:periodo", False
    tipo_docto = _texto(l.get("tipo_docto"))
    if not tipo_docto:
        return None, "invalida:tipo_docto", False
    producto = normalizar_codigo(_texto(l.get("producto")))
    if not producto:
        return None, "invalida:producto", False
    f = _FECHA.fullmatch(_texto(l.get("fecha")))
    try:
        fecha = dt.date(int(f[1]), int(f[2]), int(f[3])).isoformat() if f else None
    except ValueError:  # 2026-02-30
        fecha = None
    if fecha is None:
        return None, "invalida:fecha", False
    cantidad = _finito(l.get("cantidad"))
    if cantidad is None:
        return None, "invalida:cantidad", False
    if "costo_neto" not in l:  # el campo faltante es una deriva del contrato; un valor en blanco es otra cosa
        return None, "invalida:costo_neto", False
    costo, costo_en_cero = _costo(l["costo_neto"])
    return {
        "tenant_id": _tenant(), "bodega": bodega, "periodo": m[1] + m[2], "tipo_docto": tipo_docto,
        "numero": _numero_documento(l.get("numero")), "fecha": fecha, "tipo_venta": tipo_venta,
        "producto": producto, "cantidad": cantidad, "costo_neto": costo,
        "doc_ref": _texto(l.get("doc_ref")), "nro_doc_ref": _numero_documento(l.get("nro_doc_ref")),
    }, "", costo_en_cero


def _contar_ventas(db: Session, bodega: str) -> int:
    return db.execute(
        select(func.count()).select_from(CanalDigitalVenta).where(
            CanalDigitalVenta.tenant_id == _tenant(), CanalDigitalVenta.bodega == bodega
        )
    ).scalar_one()


_CAMPOS_VENTA = ("unid_brutas", "unid_devueltas", "valor_costo", "unid_liquidacion", "n_lineas")


def _sincronizar_venta(db: Session, bodega: str, nuevas: list[dict], periodos: list[str] | None) -> int:
    """Deja la venta guardada (de `periodos`, o de toda la bodega si es None) igual a `nuevas`, escribiendo SOLO lo
    que cambio. Devuelve las filas escritas.

    Antes cada envio borraba y reinsertaba la venta completa de la bodega (unas 7.500 filas en un mes normal), y en
    Postgres cada fila insertada es un viaje a la base: un envio de ~700 lineas costaba lo que la venta de 21 meses.
    Una fila que cambio se borra y se vuelve a insertar: asi todo el trabajo va por INSERT en lote y DELETE por ids,
    sin UPDATE fila por fila."""
    tenant = _tenant()
    V = CanalDigitalVenta
    guardadas: dict[tuple[str, str, str], tuple[int, tuple]] = {}
    if periodos is None or periodos:
        q = select(V.id, V.producto, V.semana, V.periodo, *(getattr(V, c) for c in _CAMPOS_VENTA)).where(
            V.tenant_id == tenant, V.bodega == bodega
        )
        if periodos is not None:
            q = q.where(V.periodo.in_(periodos))
        for r in db.execute(q):
            guardadas[(r.producto, r.semana, r.periodo)] = (r.id, tuple(r[4:]))
    borrar: list[int] = []
    escribir: list[dict] = []
    vistas: set[tuple[str, str, str]] = set()
    for f in nuevas:
        clave = (f["producto"], f["semana"], f["periodo"])
        vistas.add(clave)
        previa = guardadas.get(clave)
        if previa is not None:
            if all(math.isclose(a, f[c], rel_tol=1e-12, abs_tol=1e-9) for a, c in zip(previa[1], _CAMPOS_VENTA)):
                continue
            borrar.append(previa[0])
        escribir.append(f)
    borrar += [i for clave, (i, _) in guardadas.items() if clave not in vistas]
    for i in range(0, len(borrar), _BORRAR_POR_LOTE):
        db.execute(delete(V).where(V.id.in_(borrar[i : i + _BORRAR_POR_LOTE])))
    _insertar_en_lote(db, V, escribir)
    return len(escribir)


def _recalcular(db: Session, bodega: str, tipos: tuple[str, ...], conservar_sin_lineas: bool) -> dict:
    """Arma la venta semanal con TODAS las lineas guardadas de la bodega. No hace commit."""
    tenant = _tenant()
    L = CanalDigitalLinea
    lineas = [
        LineaVenta(
            periodo=r.periodo, tipo_docto=r.tipo_docto, numero=r.numero, fecha=dt.date.fromisoformat(r.fecha),
            tipo_venta=r.tipo_venta, producto=r.producto, cantidad=r.cantidad, costo_neto=r.costo_neto,
            doc_ref=r.doc_ref, nro_doc_ref=r.nro_doc_ref,
        )
        for r in db.execute(
            select(
                L.periodo, L.tipo_docto, L.numero, L.fecha, L.tipo_venta, L.producto, L.cantidad,
                L.costo_neto, L.doc_ref, L.nro_doc_ref,
            ).where(L.tenant_id == tenant, L.bodega == bodega)
        )
    ]
    # El indice de originales mira todos los periodos: una devolucion de noviembre encuentra su venta de octubre.
    resultado = agregar(lineas, tipos, indice_originales(lineas, tipos))
    nuevas = [
        {
            "tenant_id": tenant, "bodega": bodega, "producto": f.producto, "semana": f.semana,
            "periodo": f.periodo, "unid_brutas": f.unid_brutas, "unid_devueltas": f.unid_devueltas,
            "valor_costo": f.valor_costo, "unid_liquidacion": f.unid_liquidacion, "n_lineas": f.n_lineas,
        }
        for f in resultado.filas
    ]
    # La venta de un periodo sin lineas (cargada antes con reemplazar_ventas) no se puede rearmar: se deja.
    alcance = sorted({l.periodo for l in lineas}) if conservar_sin_lineas else None
    escritas = _sincronizar_venta(db, bodega, nuevas, alcance)
    total = _contar_ventas(db, bodega)
    estadisticas = dict(sorted(resultado.estadisticas.items()))
    estadisticas["filas_recalculadas"] = len(nuevas)
    estadisticas["filas_escritas"] = escritas
    estadisticas["filas_sin_cambio"] = len(nuevas) - escritas
    estadisticas["filas_conservadas_sin_lineas"] = total - len(nuevas)
    return {"filas_venta": total, "estadisticas": estadisticas}


def recalcular_ventas(
    db: Session, bodega: str = BODEGA_CANAL_DIGITAL, *, conservar_sin_lineas: bool = True
) -> dict:
    """Reemplaza la venta semanal de la bodega por la que sale de TODAS sus lineas guardadas, en una transaccion.

    Por defecto deja intacta la venta de los periodos que no tienen lineas (cargada antes con `reemplazar_ventas`):
    sin sus lineas no se puede rearmar y borrarla vaciaria las pantallas. Con `conservar_sin_lineas=False` se
    reemplaza la tabla entera de la bodega.
    """
    with CARGA_CANAL_DIGITAL:
        fila = db.execute(
            select(CanalDigitalBodega).where(
                CanalDigitalBodega.tenant_id == _tenant(), CanalDigitalBodega.bodega == bodega
            )
        ).scalar_one_or_none()
        try:
            resultado = _recalcular(db, bodega, _tipos_venta(fila), conservar_sin_lineas)
            db.commit()
        except Exception:
            db.rollback()
            raise
        return resultado


def reemplazar_lineas(db: Session, bodega: str, lineas: list, *, forzar: bool = False) -> dict:
    """Carga las lineas de documento del ERP reemplazando SOLO los periodos (del documento) que vienen, y
    recalcula la venta semanal de la bodega con todas las lineas guardadas.

    Cada linea: {periodo (YYYYMM), tipo_docto, numero, fecha (YYYY-MM-DD), tipo_venta, producto, cantidad,
    costo_neto, doc_ref, nro_doc_ref}. Solo entran las de los tipos de venta de la bodega; las mal formadas se
    cuentan como ignoradas (y por campo, en `estadisticas`), no se cargan a medias. Un periodo sin ninguna linea
    valida no se toca y un envio sin lineas validas no cambia nada. Todo o nada: si el recalculo falla, las lineas
    vuelven a como estaban.

    El servidor no sabe si el envio trae el mes completo: un periodo se reemplaza entero con lo que llegue. Para que
    una linea rezagada no vacie un mes, un periodo que quedaria con menos de la mitad de sus lineas (teniendo al
    menos 20) se rechaza con `ConflictoCarga` salvo `forzar=True`. La respuesta trae, por periodo, cuantas lineas
    tenia antes y cuantas tiene despues (`reemplazo`).

    Un periodo cargado antes por `reemplazar_ventas` y despues por aca queda gobernado por las lineas.
    """
    with CARGA_CANAL_DIGITAL:
        return _reemplazar_lineas(db, bodega, lineas, forzar)


def _reemplazar_lineas(db: Session, bodega: str, lineas: list, forzar: bool) -> dict:
    tipos = _tipos_venta(asegurar_bodega(db, bodega))  # hace commit: va antes de tocar las lineas
    validas: list[dict] = []
    ignoradas = {"invalida": 0, "tipo_venta": 0}
    por_campo: Counter = Counter()
    costo_en_cero = 0
    for l in lineas:
        fila, motivo, ajustado = _validar_linea(l, tipos, bodega)
        if fila is None:
            base, _, campo = motivo.partition(":")
            ignoradas[base] += 1
            if campo:
                por_campo[f"invalida_campo:{campo}"] += 1
        else:
            validas.append(fila)
            costo_en_cero += ajustado
    estadisticas = {
        "ignoradas_invalidas": ignoradas["invalida"], "ignoradas_tipo_venta": ignoradas["tipo_venta"],
        "costo_en_cero": costo_en_cero, **dict(sorted(por_campo.items())),
    }
    if not validas:
        return {
            "lineas_cargadas": 0, "lineas_ignoradas": len(lineas), "periodos": [], "reemplazo": {},
            "filas_venta": _contar_ventas(db, bodega), "estadisticas": estadisticas,
        }
    tenant = _tenant()
    L = CanalDigitalLinea
    despues = Counter(f["periodo"] for f in validas)
    periodos = sorted(despues)
    antes = dict(
        db.execute(
            select(L.periodo, func.count()).where(
                L.tenant_id == tenant, L.bodega == bodega, L.periodo.in_(periodos)
            ).group_by(L.periodo)
        ).all()
    )
    reemplazo = {p: {"antes": antes.get(p, 0), "despues": despues[p]} for p in periodos}
    if not forzar:
        sospechosos = {
            p: r for p, r in reemplazo.items() if r["antes"] >= _GUARDA_MIN_LINEAS and r["despues"] * 2 < r["antes"]
        }
        if sospechosos:
            raise ConflictoCarga({
                "mensaje": "El envio dejaria un periodo con menos de la mitad de las lineas que tiene: parece un envio "
                           "parcial. No se cargo nada. Si es correcto, repite el envio con \"forzar\": true.",
                "periodos": sospechosos,
            })
    try:
        db.execute(delete(L).where(L.tenant_id == tenant, L.bodega == bodega, L.periodo.in_(periodos)))
        _insertar_en_lote(db, L, validas)
        venta = _recalcular(db, bodega, tipos, conservar_sin_lineas=True)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {
        "lineas_cargadas": len(validas), "lineas_ignoradas": len(lineas) - len(validas), "periodos": periodos,
        "reemplazo": reemplazo, "filas_venta": venta["filas_venta"],
        "estadisticas": {**estadisticas, **venta["estadisticas"]},
    }


def meta_ventas(db: Session, bodega: str = BODEGA_CANAL_DIGITAL) -> dict:
    """Que hay cargado: filas, productos, rango de periodos y de semanas de la venta, y el rango de las lineas.

    `periodo_hasta` es el ultimo mes con VENTA; un mes puede tener venta (cargada por la ruta heredada /ventas) y
    ninguna linea. Quien sube lineas decide con `lineas_periodo_hasta` y `n_lineas`, que salen de las lineas.
    """
    q = select(
        func.count(), func.count(func.distinct(CanalDigitalVenta.producto)),
        func.min(CanalDigitalVenta.periodo), func.max(CanalDigitalVenta.periodo),
        func.min(CanalDigitalVenta.semana), func.max(CanalDigitalVenta.semana),
    ).where(CanalDigitalVenta.tenant_id == _tenant(), CanalDigitalVenta.bodega == bodega)
    n, prods, p0, p1, s0, s1 = db.execute(q).one()
    L = CanalDigitalLinea
    n_lineas, l0, l1 = db.execute(
        select(func.count(), func.min(L.periodo), func.max(L.periodo)).where(
            L.tenant_id == _tenant(), L.bodega == bodega
        )
    ).one()
    return {
        "bodega": bodega, "filas": n, "productos": prods,
        "periodo_desde": p0, "periodo_hasta": p1, "semana_desde": s0, "semana_hasta": s1,
        "n_lineas": n_lineas, "lineas_periodo_desde": l0, "lineas_periodo_hasta": l1,
        "clusters_en_politica": len(CLUSTERS),
    }


def guardar_politica(db: Session, bodega: str, politica: Politica, email: str | None) -> None:
    """Reemplaza las 27 filas de la bodega por las de `politica` (ya validada por quien llama)."""
    tenant = _tenant()
    existentes = {
        f.cluster: f
        for f in db.execute(
            select(CanalDigitalPolitica).where(
                CanalDigitalPolitica.tenant_id == tenant, CanalDigitalPolitica.bodega == bodega
            )
        ).scalars()
    }
    ahora = datetime.now(timezone.utc).replace(tzinfo=None)
    for f in politica.filas:
        fila = existentes.get(f.cluster)
        if fila is None:
            fila = CanalDigitalPolitica(tenant_id=tenant, bodega=bodega, cluster=f.cluster, modo=f.modo)
            db.add(fila)
        fila.modo, fila.nivel_servicio, fila.z, fila.minimo_fijo = f.modo, f.nivel_servicio, f.z, f.minimo_fijo
        fila.actualizado_por, fila.actualizado_en = email, ahora
    db.flush()
