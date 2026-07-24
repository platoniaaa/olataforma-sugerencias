"""Configuracion calibrable del modelo: leer la vigente, actualizarla, historial.

La vigente es la fila mas reciente de `configuracion_modelo`. Si la tabla esta
vacia (primera vez), se devuelven los valores por defecto —los mismos que tenian
las constantes del codigo— sin persistir nada; la primera edicion crea la fila.
"""
from __future__ import annotations

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import ConfiguracionModelo
from . import auditoria_service

settings = get_settings()

# Valores por defecto: iguales a las constantes historicas de motor/parametros.py
# (incluye el ciclo via CD ya unificado a 5 el 24-jul-2026).
DEFAULTS: dict = {
    "ciclo_orden_dias": 5,
    "ciclo_orden_dias_cd": 5,
    "z_a": 1.645, "z_b": 1.282, "z_c": 0.842, "z_d": 0.0,
    "z_imp_cd_a": 1.282, "z_imp_cd_b": 1.036,
    "lead_time_fallback_dias": 8,
    "winsor_k": 3.0,
}

# Rangos aceptados por parametro (min, max). Fuera de esto la edicion se rechaza:
# es la red que evita, por ejemplo, un Z=5 que multiplicaria el inventario.
_RANGOS: dict[str, tuple[float, float]] = {
    "ciclo_orden_dias": (1, 60),
    "ciclo_orden_dias_cd": (1, 60),
    "z_a": (0, 3.5), "z_b": (0, 3.5), "z_c": (0, 3.5), "z_d": (0, 3.5),
    "z_imp_cd_a": (0, 3.5), "z_imp_cd_b": (0, 3.5),
    "lead_time_fallback_dias": (1, 90),
    "winsor_k": (0.5, 6.0),
}

_CAMPOS = list(DEFAULTS.keys())


def _fila_vigente(db: Session) -> ConfiguracionModelo | None:
    return db.scalars(
        select(ConfiguracionModelo)
        .where(ConfiguracionModelo.tenant_id == settings.default_tenant_id)
        .order_by(desc(ConfiguracionModelo.creado_en))
        .limit(1)
    ).first()


def _a_dict(fila: ConfiguracionModelo | None) -> dict:
    """Config en la forma que consumen el motor y el simulador (Z como diccionarios)."""
    base = {c: (getattr(fila, c) if fila else DEFAULTS[c]) for c in _CAMPOS}
    return {
        "ciclo_orden_dias": int(base["ciclo_orden_dias"]),
        "ciclo_orden_dias_cd": int(base["ciclo_orden_dias_cd"]),
        "z_por_clase": {"A": base["z_a"], "B": base["z_b"], "C": base["z_c"], "D": base["z_d"]},
        "z_importado_cd": {"A": base["z_imp_cd_a"], "B": base["z_imp_cd_b"]},
        "lead_time_fallback_dias": int(base["lead_time_fallback_dias"]),
        "winsor_k": float(base["winsor_k"]),
        "creado_en": fila.creado_en if fila else None,
        "creado_por": fila.creado_por if fila else None,
        "nota": fila.nota if fila else None,
        "es_default": fila is None,
    }


def vigente(db: Session) -> dict:
    """La configuracion vigente (o los defaults si nunca se ha editado)."""
    return _a_dict(_fila_vigente(db))


def actualizar(db: Session, cambios: dict, *, usuario: str | None, nota: str | None) -> dict:
    """Inserta una version nueva = vigente + `cambios`, validando rangos. Audita.

    `cambios` usa los nombres planos de la tabla (ciclo_orden_dias, z_a, ...).
    """
    actual = _fila_vigente(db)
    valores = {c: (getattr(actual, c) if actual else DEFAULTS[c]) for c in _CAMPOS}

    tocados: list[str] = []
    for campo, valor in cambios.items():
        if campo not in _RANGOS:
            raise ValueError(f"Parametro desconocido: {campo!r}")
        if valor is None:
            continue
        lo, hi = _RANGOS[campo]
        if not (lo <= valor <= hi):
            raise ValueError(f"{campo} = {valor} fuera de rango [{lo}, {hi}]")
        if valor != valores[campo]:
            tocados.append(f"{campo}: {valores[campo]} -> {valor}")
        valores[campo] = valor

    fila = ConfiguracionModelo(**valores, creado_por=usuario, nota=nota)
    db.add(fila)
    auditoria_service.registrar(
        db,
        accion="config_modelo_actualizada",
        entidad="configuracion_modelo",
        entidad_id=fila.id,
        usuario_email=usuario,
        detalle="; ".join(tocados) if tocados else "sin cambios de valor",
    )
    db.commit()
    db.refresh(fila)
    return _a_dict(fila)


def historial(db: Session, limite: int = 50) -> list[dict]:
    filas = db.scalars(
        select(ConfiguracionModelo)
        .where(ConfiguracionModelo.tenant_id == settings.default_tenant_id)
        .order_by(desc(ConfiguracionModelo.creado_en))
        .limit(limite)
    ).all()
    return [_a_dict(f) for f in filas]
