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
    # Modulo Lead time / transito
    "lt_cd_rm_dias": 1, "lt_cd_resto_dias": 2, "lt_tope_dias": 30,
    "transito_nacional_dias": 30, "transito_importado_dias": 180,
    # Modulo Demanda
    "dias_habiles_mes": 22,
    # Modulo Reposicion al nivel maximo
    "reponer_a_maximo": True,
    "clases_que_reponen": "AB",
    # Modulo Clasificacion ABC
    "abc_umbral_a_m6": 5, "abc_umbral_b_m6": 4, "abc_umbral_c_m6": 3,
    "abc_umbral_c_m3": 2, "abc_umbral_c_m12": 6,
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
    "lt_cd_rm_dias": (0, 30), "lt_cd_resto_dias": (0, 30), "lt_tope_dias": (1, 365),
    "transito_nacional_dias": (1, 365), "transito_importado_dias": (1, 730),
    "dias_habiles_mes": (15, 31),
    "abc_umbral_a_m6": (1, 6), "abc_umbral_b_m6": (0, 6), "abc_umbral_c_m6": (0, 6),
    "abc_umbral_c_m3": (0, 3), "abc_umbral_c_m12": (0, 12),
}

# Parametros que no son numeros: se validan por lista de valores permitidos en vez
# de por rango. Van aparte de `_RANGOS` para que la red de seguridad siga siendo
# explicita —un parametro sin regla no se puede editar, caiga donde caiga—.
_OPCIONES: dict[str, tuple] = {
    "reponer_a_maximo": (True, False),
    "clases_que_reponen": ("AB", "ABCD"),
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
        "lt_cd_rm_dias": int(base["lt_cd_rm_dias"]),
        "lt_cd_resto_dias": int(base["lt_cd_resto_dias"]),
        "lt_tope_dias": int(base["lt_tope_dias"]),
        "transito_nacional_dias": int(base["transito_nacional_dias"]),
        "transito_importado_dias": int(base["transito_importado_dias"]),
        "dias_habiles_mes": int(base["dias_habiles_mes"]),
        "reponer_a_maximo": bool(base["reponer_a_maximo"]),
        "clases_que_reponen": str(base["clases_que_reponen"] or "AB"),
        "abc_umbral_a_m6": int(base["abc_umbral_a_m6"]),
        "abc_umbral_b_m6": int(base["abc_umbral_b_m6"]),
        "abc_umbral_c_m6": int(base["abc_umbral_c_m6"]),
        "abc_umbral_c_m3": int(base["abc_umbral_c_m3"]),
        "abc_umbral_c_m12": int(base["abc_umbral_c_m12"]),
        # Lo necesita la UI para poder revertir a esta version.
        "id": fila.id if fila else None,
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
        if campo not in _RANGOS and campo not in _OPCIONES:
            raise ValueError(f"Parametro desconocido: {campo!r}")
        if valor is None:
            continue
        if campo in _RANGOS:
            lo, hi = _RANGOS[campo]
            if not (lo <= valor <= hi):
                raise ValueError(f"{campo} = {valor} fuera de rango [{lo}, {hi}]")
        elif valor not in _OPCIONES[campo]:
            opciones = ", ".join(str(v) for v in _OPCIONES[campo])
            raise ValueError(f"{campo} = {valor!r} no es un valor valido ({opciones})")
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


def revertir(db: Session, version_id: str, *, usuario: str | None) -> dict:
    """Vuelve a una version anterior insertando una COPIA de sus valores.

    No se borra nada del historial: revertir es avanzar hacia atras, asi queda el
    rastro de que se revirtio y quien lo hizo.
    """
    origen = db.get(ConfiguracionModelo, version_id)
    if origen is None or origen.tenant_id != settings.default_tenant_id:
        raise ValueError(f"No existe la version {version_id!r}")
    valores = {c: getattr(origen, c) for c in _CAMPOS}
    fecha = origen.creado_en.strftime("%d-%m-%Y %H:%M") if origen.creado_en else "?"
    return actualizar(
        db, valores, usuario=usuario, nota=f"Revertido a la version del {fecha}"
    )


def historial(db: Session, limite: int = 50) -> list[dict]:
    filas = db.scalars(
        select(ConfiguracionModelo)
        .where(ConfiguracionModelo.tenant_id == settings.default_tenant_id)
        .order_by(desc(ConfiguracionModelo.creado_en))
        .limit(limite)
    ).all()
    return [_a_dict(f) for f in filas]
