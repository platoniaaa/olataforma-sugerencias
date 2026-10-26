"""Canal Digital: acceso a las tablas del modulo (bodega, venta semanal, politica).

El nucleo de calculo vive en `src.canal_digital` y no conoce la base de datos; aqui se lee
y se escribe lo que ese nucleo necesita.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import Session

from ..canal_digital.politica import (
    BODEGA_CANAL_DIGITAL, CLUSTERS, FilaPolitica, Politica, filas_provisorias,
)
from ..config import get_settings
from ..models import CanalDigitalBodega, CanalDigitalPolitica, CanalDigitalVenta

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
