"""Cierra las sugerencias manuales de una sola vez cuando su compra aparece en el ERP.

Nadie aprieta "Marcar como pedido" (al 08-10-2026 no habia ni un pedido registrado
desde que existe el boton). Sin otra señal, una sugerencia de una sola vez seguia
sumando las mismas unidades hasta vencer, y la descarga del sugerido de unos dias
despues la volvia a pedir: se compraba dos veces.

El motor manda cada mañana las OC de los ultimos 90 dias, las mismas que lee para
el transito. El ERP no dice por que se hizo una OC, asi que esto es una
coincidencia y no una prueba. Se exige lo que una compra de esa sugerencia tendria
que cumplir:

- mismo producto y misma sucursal;
- fecha de la OC igual o posterior al dia, en hora de Chile, en que se creo la
  sugerencia;
- al menos las unidades sugeridas en esa OC, sumando sus lineas del producto;
- cualquier motivo de compra. Los pedidos especiales se compran como "compra
  calzada", y el transito del sugerido solo cuenta las de reposicion: si se mirara
  el transito, esas compras nunca cerrarian nada.

Lo que queda abierto: una OC sin relacion que cumpla todo eso, o una del mismo dia
hecha antes de la sugerencia, porque la fecha de la OC no trae hora. Por eso queda
anotado que OC la cerro: si no tenia nada que ver, se vuelve a crear.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import SugerenciaManual
from . import auditoria_service, sugerido_service

TZ_CHILE = ZoneInfo("America/Santiago")


def _norm(texto: object) -> str:
    return str(texto or "").strip().upper()


def _a_fecha(valor: object) -> date | None:
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    try:
        return date.fromisoformat(str(valor or "")[:10])
    except ValueError:
        return None


def dia_chile(instante: datetime) -> date:
    """El dia, en hora de Chile, de un instante guardado en UTC.

    Una sugerencia creada el lunes a las 22:00 en Chile ya es martes en UTC: con la
    fecha UTC, la OC que el comprador hizo el lunes quedaria "antes" y no la cerraria.
    """
    if instante.tzinfo is None:
        instante = instante.replace(tzinfo=timezone.utc)
    return instante.astimezone(TZ_CHILE).date()


def ocs_por_par(filas: list[dict]) -> dict[tuple[str, str], list[dict]]:
    """{(producto, sucursal): [{n_oc, fecha, cantidad}]}, una entrada por OC.

    Las lineas de una misma OC y producto se suman: una OC que trae el repuesto en
    dos lineas sigue siendo una compra. Ordenadas por fecha y numero, para que la
    sugerencia la cierre la primera OC que cumple.
    """
    acumulado: dict[tuple[str, str, str, date], float] = defaultdict(float)
    for f in filas:
        producto, sucursal = _norm(f.get("producto")), _norm(f.get("sucursal_id"))
        n_oc = str(f.get("n_oc") or "").strip()
        fecha = _a_fecha(f.get("fecha_oc"))
        try:
            cantidad = float(f.get("cantidad") or 0)
        except (TypeError, ValueError):
            cantidad = 0.0
        if not producto or not sucursal or not n_oc or fecha is None or cantidad <= 0:
            continue
        acumulado[(producto, sucursal, n_oc, fecha)] += cantidad
    por_par: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for (producto, sucursal, n_oc, fecha), cantidad in acumulado.items():
        por_par[(producto, sucursal)].append({"n_oc": n_oc, "fecha": fecha, "cantidad": cantidad})
    for ocs in por_par.values():
        ocs.sort(key=lambda o: (o["fecha"], o["n_oc"]))
    return por_par


def coincidencias(db: Session, filas: list[dict]) -> list[tuple[SugerenciaManual, dict]]:
    """Cada sugerencia de una sola vez vigente con la primera OC que la cumple.

    Las instancias de una regla quedan fuera: la regla se recalcula cada dia con lo
    que viene en camino. Las vencidas tambien: ya no suman, y las archiva la limpieza.
    """
    por_par = ocs_por_par(filas)
    if not por_par:
        return []
    vigentes = db.scalars(
        select(SugerenciaManual).where(
            SugerenciaManual.archivada.is_(False),
            SugerenciaManual.recurrente_id.is_(None),
            sugerido_service._no_vencida(),
        )
    ).all()
    salida: list[tuple[SugerenciaManual, dict]] = []
    for s in vigentes:
        if not s.unidades or s.unidades <= 0:
            continue
        ocs = por_par.get((_norm(s.producto), _norm(s.sucursal_id)))
        if not ocs:
            continue
        desde = dia_chile(s.creado_en)
        oc = next(
            (o for o in ocs if o["fecha"] >= desde and o["cantidad"] >= s.unidades), None
        )
        if oc:
            salida.append((s, oc))
    return salida


def cerrar_por_oc(db: Session, filas: list[dict], *, previsualizar: bool = False) -> dict:
    """Cierra (archiva) las sugerencias ya compradas y anota con que OC.

    Con `previsualizar` solo dice cuales cerraria, sin escribir nada.
    """
    pares = coincidencias(db, filas)
    detalle = [
        {
            "id": s.id, "producto": s.producto, "sucursal_id": s.sucursal_id,
            "unidades": s.unidades, "n_oc": oc["n_oc"], "fecha_oc": oc["fecha"].isoformat(),
            "cantidad_oc": oc["cantidad"],
        }
        for s, oc in pares
    ]
    if previsualizar:
        return {"lineas_recibidas": len(filas), "sugerencias_cerradas": 0, "a_cerrar": detalle}
    ahora = datetime.now(timezone.utc)
    for s, oc in pares:
        s.archivada = True
        s.cerrada_por_oc = oc["n_oc"]
        s.cerrada_oc_fecha = oc["fecha"]
        s.cerrada_oc_unidades = oc["cantidad"]
        s.cerrada_en = ahora
        auditoria_service.registrar(
            db, accion="cerrada_por_oc", entidad="sugerencia_manual", entidad_id=s.id,
            usuario_email="motor", producto=s.producto, sucursal_id=s.sucursal_id,
            unidades=s.unidades,
            detalle=(
                f"Aparecio en el ERP la OC N° {oc['n_oc']} del "
                f"{oc['fecha']:%d-%m-%Y} con {oc['cantidad']:g} u"
            ),
        )
    db.commit()
    return {"lineas_recibidas": len(filas), "sugerencias_cerradas": len(pares), "cerradas": detalle}
