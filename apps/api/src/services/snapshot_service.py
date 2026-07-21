"""Historia del sugerido y alertas post-sincronizacion.

Dos cosas que solo se pueden hacer justo despues de una carga:

1. **Snapshot**: guardar la foto del dia antes de que la proxima sync reemplace
   la tabla `sugerido`. Sin esto no hay forma de responder "¿esto ya venia
   pasando la semana pasada?".
2. **Alertas**: avisar por la campanita lo que necesita atencion (quiebres con
   demanda, productos bajo el punto de pedido), **agregado por sucursal**. Una
   notificacion por producto serian miles por dia y nadie las leeria.

Ambas son best-effort: si fallan, la carga del sugerido ya esta commiteada y no
se toca. Un problema guardando historia no puede dejar sin datos a la plataforma.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Sugerido, SugeridoSnapshot
from . import auditoria_service

settings = get_settings()

# Columnas que viajan del sugerido al snapshot.
_COLUMNAS = (
    "producto", "sucursal_id", "clasificacion_abc", "total_sugerido_suc",
    "stock_activo_suc", "stock_en_transito_suc", "punto_de_pedido",
    "demanda_diaria", "costo_unitario", "pedir",
)


def guardar_snapshot(db: Session, fecha: date | None = None) -> int:
    """Guarda la foto del dia. Idempotente: reescribe la del mismo dia.

    Devuelve cuantas filas quedaron guardadas."""
    if not settings.snapshot_habilitado:
        return 0
    tenant = settings.default_tenant_id
    hoy = fecha or date.today()

    filas = db.execute(
        select(*[getattr(Sugerido, c) for c in _COLUMNAS]).where(
            Sugerido.tenant_id == tenant,
            # Solo lo que tiene actividad: las filas en cero son la mayoria y no
            # aportan historia (y multiplicarian el tamano de la tabla por 3).
            (func.coalesce(Sugerido.total_sugerido_suc, 0) > 0)
            | (func.coalesce(Sugerido.stock_activo_suc, 0) > 0)
            | (func.coalesce(Sugerido.punto_de_pedido, 0) > 0),
        )
    ).all()
    if not filas:
        return 0

    registros = [
        {"tenant_id": tenant, "fecha": hoy, **dict(zip(_COLUMNAS, f))} for f in filas
    ]
    db.execute(
        delete(SugeridoSnapshot).where(
            SugeridoSnapshot.tenant_id == tenant, SugeridoSnapshot.fecha == hoy
        )
    )
    for i in range(0, len(registros), 500):
        db.execute(insert(SugeridoSnapshot).values(registros[i : i + 500]))
    db.commit()
    return len(registros)


def purgar_antiguos(db: Session, dias: int | None = None) -> int:
    """Borra snapshots mas viejos que la retencion configurada."""
    dias = dias if dias is not None else settings.snapshot_retencion_dias
    corte = date.today() - timedelta(days=dias)
    r = db.execute(
        delete(SugeridoSnapshot).where(
            SugeridoSnapshot.tenant_id == settings.default_tenant_id,
            SugeridoSnapshot.fecha < corte,
        )
    )
    db.commit()
    return r.rowcount or 0


def serie(
    db: Session, producto: str, sucursal_id: str, dias: int = 90
) -> list[dict]:
    """Evolucion de un producto/sucursal para el mini-grafico de la ficha."""
    desde = date.today() - timedelta(days=dias)
    filas = db.execute(
        select(
            SugeridoSnapshot.fecha,
            SugeridoSnapshot.total_sugerido_suc,
            SugeridoSnapshot.stock_activo_suc,
            SugeridoSnapshot.punto_de_pedido,
        )
        .where(
            SugeridoSnapshot.tenant_id == settings.default_tenant_id,
            SugeridoSnapshot.producto == producto,
            SugeridoSnapshot.sucursal_id == sucursal_id,
            SugeridoSnapshot.fecha >= desde,
        )
        .order_by(SugeridoSnapshot.fecha.asc())
    ).all()
    return [
        {
            "fecha": f.fecha.isoformat(),
            "sugerido": f.total_sugerido_suc or 0,
            "stock": f.stock_activo_suc or 0,
            "punto_pedido": f.punto_de_pedido or 0,
        }
        for f in filas
    ]


def generar_alertas(db: Session) -> dict:
    """Notificacion por sucursal con lo que necesita atencion. Agregada, no por producto."""
    if not settings.alertas_habilitadas:
        return {"sucursales_avisadas": 0}

    filas = db.execute(
        select(
            Sugerido.sucursal_id,
            Sugerido.nombre_sucursal,
            Sugerido.stock_activo_suc,
            Sugerido.stock_en_transito_suc,
            Sugerido.punto_de_pedido,
            Sugerido.demanda_mensual,
            Sugerido.total_sugerido_suc,
            Sugerido.costo_unitario,
        ).where(Sugerido.tenant_id == settings.default_tenant_id)
    ).all()

    por_suc: dict[str, dict] = {}
    for f in filas:
        demanda = f.demanda_mensual or 0
        if demanda <= 0:
            continue
        stock = f.stock_activo_suc or 0
        d = por_suc.setdefault(
            f.sucursal_id,
            {"nombre": f.nombre_sucursal or f.sucursal_id, "quiebre": 0, "bajo_pp": 0,
             "valor_urgente": 0.0},
        )
        if stock <= 0:
            d["quiebre"] += 1
            d["valor_urgente"] += (f.total_sugerido_suc or 0) * (f.costo_unitario or 0)
        elif f.punto_de_pedido and stock + (f.stock_en_transito_suc or 0) < f.punto_de_pedido:
            d["bajo_pp"] += 1

    avisadas = 0
    for datos in sorted(por_suc.values(), key=lambda d: d["quiebre"], reverse=True):
        if not datos["quiebre"] and not datos["bajo_pp"]:
            continue
        partes = []
        if datos["quiebre"]:
            partes.append(f"{datos['quiebre']} en quiebre con demanda")
        if datos["bajo_pp"]:
            partes.append(f"{datos['bajo_pp']} bajo el punto de pedido")
        auditoria_service.notificar(
            db,
            tipo="alerta_stock",
            titulo=f"{datos['nombre']}: {', '.join(partes)}",
            mensaje=(
                f"Reponer los quiebres cuesta aprox. {round(datos['valor_urgente']):,} CLP."
                .replace(",", ".")
                if datos["valor_urgente"]
                else None
            ),
            creado_por_email="sistema",
            sucursal_id=datos["nombre"],
        )
        avisadas += 1
    db.commit()
    return {"sucursales_avisadas": avisadas}


def post_carga(db: Session) -> dict:
    """Se llama despues de una carga exitosa del sugerido. Nunca propaga errores:
    la carga ya esta commiteada y un fallo guardando historia no puede romperla."""
    resultado: dict = {}
    for nombre, fn in (
        ("snapshot_filas", guardar_snapshot),
        ("snapshot_purgados", purgar_antiguos),
        ("alertas", generar_alertas),
    ):
        try:
            resultado[nombre] = fn(db)
        except Exception as e:  # noqa: BLE001
            db.rollback()
            resultado[nombre] = f"fallo: {e}"
    return resultado
