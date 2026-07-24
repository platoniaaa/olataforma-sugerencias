"""Simulador what-if: cuanto cambiaria la compra si se movieran los parametros.

Responde "¿que pasa si subo el ciclo de orden a 7 dias?" o "¿y si bajo el nivel
de servicio de la clase C?" ANTES de tocar nada, con el impacto en unidades y en
plata.

**Alcance honesto**: recalcula la formula del modelo sobre el snapshot vigente
(la tabla `sugerido`), no vuelve a correr el motor. Es decir, usa la demanda, la
desviacion y el lead time YA calculados y solo cambia lo que dependa de los
parametros simulados. Para un cambio que altere la clasificacion ABC o la
demanda hay que correr el motor de verdad; esto sirve para dimensionar el
impacto de los parametros de reposicion, que es la pregunta frecuente.

Las constantes son las mismas del motor (`src/motor/parametros.py`), que replican
el modelo DAX auditado.
"""
from __future__ import annotations

import math

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Sugerido
from ..schemas import SugeridoFiltros

# --- Constantes del modelo (espejo de src/motor/parametros.py) ---
DIAS_HABILES_MES = 22
CICLO_ORDEN_DIAS = 5          # compra directa al proveedor
CICLO_ORDEN_DIAS_CD = 5       # abastecido del CD (antes 3; unificado a 5 el 24-jul-2026)
Z_POR_CLASE = {"A": 1.645, "B": 1.282, "C": 0.842, "D": 0.0}
Z_IMPORTADO_CD = {"A": 1.282, "B": 1.036}
# Solo estas clases generan compra (las C/D locales se consolidan en el CD).
CLASES_COMPRA = {"A", "B"}


def _round_com(x: float) -> int:
    """ROUND half-away-from-zero, como DAX (no el redondeo bancario de Python)."""
    return math.floor(x + 0.5)


def _z(clase: str | None, es_importado_cd: bool, z_por_clase: dict[str, float]) -> float:
    if es_importado_cd and clase in Z_IMPORTADO_CD:
        return Z_IMPORTADO_CD[clase]
    return z_por_clase.get(clase or "", 0.0)


def simular(
    db: Session,
    f: SugeridoFiltros,
    *,
    ciclo_orden_dias: int = CICLO_ORDEN_DIAS,
    ciclo_orden_dias_cd: int = CICLO_ORDEN_DIAS_CD,
    z_por_clase: dict[str, float] | None = None,
    factor_lead_time: float = 1.0,
) -> dict:
    """Recalcula el sugerido con otros parametros y compara contra el vigente."""
    from .sugerido_service import _apply_filters

    z_por_clase = z_por_clase or dict(Z_POR_CLASE)
    filtros = f.model_copy(update={"solo_pedir": False})
    filas = db.execute(
        _apply_filters(
            select(
                Sugerido.producto,
                Sugerido.sucursal_id,
                Sugerido.nombre_sucursal,
                Sugerido.clasificacion_abc,
                Sugerido.clasificacion_abc_agregada,
                Sugerido.abastece_cd,
                Sugerido.es_importado,
                Sugerido.demanda_diaria,
                Sugerido.desv_std_mensual,
                Sugerido.lt_efectivo,
                Sugerido.stock_activo_suc,
                Sugerido.stock_en_transito_suc,
                Sugerido.total_sugerido_suc,
                Sugerido.costo_unitario,
            ),
            filtros,
        )
    ).all()

    actual_u = simulado_u = 0.0
    actual_clp = simulado_clp = 0.0
    por_sucursal: dict[str, dict] = {}
    mayores: list[dict] = []

    for r in filas:
        abastece_cd = (r.abastece_cd or "").strip().lower() in ("si", "sí")
        clase = r.clasificacion_abc_agregada if r.sucursal_id == "CD REPUESTOS" else r.clasificacion_abc
        co = ciclo_orden_dias_cd if abastece_cd else ciclo_orden_dias
        lt = (r.lt_efectivo or 0) * factor_lead_time

        # Stock de seguridad con el Z simulado.
        sigma = r.desv_std_mensual
        if sigma is None:
            ss = 0.0
        else:
            proteccion = (lt + co) / DIAS_HABILES_MES
            z = _z(clase, abastece_cd and bool(r.es_importado), z_por_clase)
            ss = _round_com(z * sigma * math.sqrt(max(proteccion, 0)))

        # Sugerido: demanda del periodo protegido + SS - lo que ya hay.
        if (r.clasificacion_abc or "") in CLASES_COMPRA or (
            r.clasificacion_abc_agregada or ""
        ) in CLASES_COMPRA:
            bruto = (r.demanda_diaria or 0) * (co + lt) + ss
            neto = bruto - (r.stock_activo_suc or 0) - (r.stock_en_transito_suc or 0)
            nuevo = max(_round_com(neto), 0)
        else:
            nuevo = 0

        vigente = r.total_sugerido_suc or 0
        costo = r.costo_unitario or 0
        actual_u += vigente
        simulado_u += nuevo
        actual_clp += vigente * costo
        simulado_clp += nuevo * costo

        suc = por_sucursal.setdefault(
            r.sucursal_id,
            {"sucursal_id": r.sucursal_id,
             "nombre_sucursal": r.nombre_sucursal or r.sucursal_id,
             "actual_u": 0.0, "simulado_u": 0.0, "actual_clp": 0.0, "simulado_clp": 0.0},
        )
        suc["actual_u"] += vigente
        suc["simulado_u"] += nuevo
        suc["actual_clp"] += vigente * costo
        suc["simulado_clp"] += nuevo * costo

        if nuevo != vigente:
            mayores.append({
                "producto": r.producto,
                "sucursal_id": r.sucursal_id,
                "actual": vigente,
                "simulado": nuevo,
                "delta": nuevo - vigente,
                "delta_clp": round((nuevo - vigente) * costo),
            })

    mayores.sort(key=lambda x: abs(x["delta_clp"]), reverse=True)
    for s in por_sucursal.values():
        s["delta_u"] = round(s["simulado_u"] - s["actual_u"])
        s["delta_clp"] = round(s["simulado_clp"] - s["actual_clp"])
        for k in ("actual_u", "simulado_u", "actual_clp", "simulado_clp"):
            s[k] = round(s[k])

    return {
        "parametros": {
            "ciclo_orden_dias": ciclo_orden_dias,
            "ciclo_orden_dias_cd": ciclo_orden_dias_cd,
            "z_por_clase": z_por_clase,
            "factor_lead_time": factor_lead_time,
        },
        "resumen": {
            "actual_unidades": round(actual_u),
            "simulado_unidades": round(simulado_u),
            "delta_unidades": round(simulado_u - actual_u),
            "actual_clp": round(actual_clp),
            "simulado_clp": round(simulado_clp),
            "delta_clp": round(simulado_clp - actual_clp),
            "lineas_que_cambian": len(mayores),
            "n_filas": len(filas),
        },
        "por_sucursal": sorted(
            por_sucursal.values(), key=lambda s: abs(s["delta_clp"]), reverse=True
        ),
        "mayores_cambios": mayores[:25],
    }
