"""Canal Digital: acceso a las tablas del modulo (bodega, venta semanal, politica).

El nucleo de calculo vive en `src.canal_digital` y no conoce la base de datos; aqui se lee
y se escribe lo que ese nucleo necesita.
"""
from __future__ import annotations

import datetime as dt
import math
import re
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

settings = get_settings()
_LOTE = 1000


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

    Cada fila: {producto, semana (YYYY-MM-DD lunes), periodo (YYYYMM), unid_brutas,
    unid_devueltas, valor_costo, unid_liquidacion, n_lineas}. Las filas mal formadas se
    cuentan como ignoradas, no se cargan a medias.
    """
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


def _finito(valor, *, obligatorio: bool) -> float | None:
    """float finito, o None si no sirve. Un valor ausente es 0 cuando no es obligatorio."""
    if valor is None:
        return None if obligatorio else 0.0
    if isinstance(valor, bool):
        return None
    try:
        x = float(valor)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _validar_linea(l, tipos: tuple[str, ...], bodega: str) -> tuple[dict | None, str]:
    """(fila lista para insertar, "") o (None, motivo). Motivos: "tipo_venta" (no es del canal) o "invalida"."""
    if not isinstance(l, dict):
        return None, "invalida"
    tipo_venta = _texto(l.get("tipo_venta"))
    if tipo_venta not in tipos:
        return None, "tipo_venta"
    periodo = _texto(l.get("periodo"))
    tipo_docto = _texto(l.get("tipo_docto"))
    producto = normalizar_codigo(_texto(l.get("producto")))
    fecha = _texto(l.get("fecha"))
    cantidad = _finito(l.get("cantidad"), obligatorio=True)
    costo = _finito(l.get("costo_neto"), obligatorio=False)
    if (
        len(periodo) != 6 or not periodo.isdigit() or not 1 <= int(periodo[4:]) <= 12
        or not tipo_docto or not producto or len(fecha) != 10 or cantidad is None or costo is None
    ):
        return None, "invalida"
    try:
        dt.datetime.strptime(fecha, "%Y-%m-%d")
    except ValueError:
        return None, "invalida"
    return {
        "tenant_id": _tenant(), "bodega": bodega, "periodo": periodo, "tipo_docto": tipo_docto,
        "numero": _numero_documento(l.get("numero")), "fecha": fecha, "tipo_venta": tipo_venta,
        "producto": producto, "cantidad": cantidad, "costo_neto": costo,
        "doc_ref": _texto(l.get("doc_ref")), "nro_doc_ref": _numero_documento(l.get("nro_doc_ref")),
    }, ""


def _contar_ventas(db: Session, bodega: str) -> int:
    return db.execute(
        select(func.count()).select_from(CanalDigitalVenta).where(
            CanalDigitalVenta.tenant_id == _tenant(), CanalDigitalVenta.bodega == bodega
        )
    ).scalar_one()


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
    borrar = delete(CanalDigitalVenta).where(
        CanalDigitalVenta.tenant_id == tenant, CanalDigitalVenta.bodega == bodega
    )
    if conservar_sin_lineas:
        # La venta de un periodo sin lineas (cargada antes con reemplazar_ventas) no se puede rearmar: se deja.
        borrar = borrar.where(CanalDigitalVenta.periodo.in_(sorted({l.periodo for l in lineas})))
    db.execute(borrar)
    nuevas = [
        {
            "tenant_id": tenant, "bodega": bodega, "producto": f.producto, "semana": f.semana,
            "periodo": f.periodo, "unid_brutas": f.unid_brutas, "unid_devueltas": f.unid_devueltas,
            "valor_costo": f.valor_costo, "unid_liquidacion": f.unid_liquidacion, "n_lineas": f.n_lineas,
        }
        for f in resultado.filas
    ]
    for i in range(0, len(nuevas), _LOTE):
        db.execute(insert(CanalDigitalVenta), nuevas[i : i + _LOTE])
    total = _contar_ventas(db, bodega)
    estadisticas = dict(sorted(resultado.estadisticas.items()))
    estadisticas["filas_recalculadas"] = len(nuevas)
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


def reemplazar_lineas(db: Session, bodega: str, lineas: list) -> dict:
    """Carga las lineas de documento del ERP reemplazando SOLO los periodos (del documento) que vienen, y
    recalcula la venta semanal de la bodega con todas las lineas guardadas.

    Cada linea: {periodo (YYYYMM), tipo_docto, numero, fecha (YYYY-MM-DD), tipo_venta, producto, cantidad,
    costo_neto, doc_ref, nro_doc_ref}. Solo entran las de los tipos de venta de la bodega; las mal formadas se
    cuentan como ignoradas, no se cargan a medias. Un periodo sin ninguna linea valida no se toca y un envio sin
    lineas validas no cambia nada. Todo o nada: si el recalculo falla, las lineas vuelven a como estaban.
    """
    tipos = _tipos_venta(asegurar_bodega(db, bodega))  # hace commit: va antes de tocar las lineas
    validas: list[dict] = []
    ignoradas = {"invalida": 0, "tipo_venta": 0}
    for l in lineas:
        fila, motivo = _validar_linea(l, tipos, bodega)
        if fila is None:
            ignoradas[motivo] += 1
        else:
            validas.append(fila)
    estadisticas = {"ignoradas_invalidas": ignoradas["invalida"], "ignoradas_tipo_venta": ignoradas["tipo_venta"]}
    if not validas:
        return {
            "lineas_cargadas": 0, "lineas_ignoradas": len(lineas), "periodos": [],
            "filas_venta": _contar_ventas(db, bodega), "estadisticas": estadisticas,
        }
    periodos = sorted({f["periodo"] for f in validas})
    try:
        db.execute(
            delete(CanalDigitalLinea).where(
                CanalDigitalLinea.tenant_id == _tenant(), CanalDigitalLinea.bodega == bodega,
                CanalDigitalLinea.periodo.in_(periodos),
            )
        )
        for i in range(0, len(validas), _LOTE):
            db.execute(insert(CanalDigitalLinea), validas[i : i + _LOTE])
        venta = _recalcular(db, bodega, tipos, conservar_sin_lineas=True)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {
        "lineas_cargadas": len(validas), "lineas_ignoradas": len(lineas) - len(validas), "periodos": periodos,
        "filas_venta": venta["filas_venta"], "estadisticas": {**estadisticas, **venta["estadisticas"]},
    }


def meta_ventas(db: Session, bodega: str = BODEGA_CANAL_DIGITAL) -> dict:
    """Que hay cargado: filas, productos, rango de periodos y de semanas."""
    q = select(
        func.count(), func.count(func.distinct(CanalDigitalVenta.producto)),
        func.min(CanalDigitalVenta.periodo), func.max(CanalDigitalVenta.periodo),
        func.min(CanalDigitalVenta.semana), func.max(CanalDigitalVenta.semana),
    ).where(CanalDigitalVenta.tenant_id == _tenant(), CanalDigitalVenta.bodega == bodega)
    n, prods, p0, p1, s0, s1 = db.execute(q).one()
    return {
        "bodega": bodega, "filas": n, "productos": prods,
        "periodo_desde": p0, "periodo_hasta": p1, "semana_desde": s0, "semana_hasta": s1,
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
