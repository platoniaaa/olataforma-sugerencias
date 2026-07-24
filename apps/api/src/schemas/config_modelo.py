"""Schemas de la configuracion calibrable del modelo."""
from __future__ import annotations

from pydantic import BaseModel, Field


class ConfigModeloUpdate(BaseModel):
    """Cambios a aplicar. Todos opcionales: solo se tocan los que vengan."""

    ciclo_orden_dias: int | None = Field(default=None, ge=1, le=60)
    ciclo_orden_dias_cd: int | None = Field(default=None, ge=1, le=60)
    z_a: float | None = Field(default=None, ge=0, le=3.5)
    z_b: float | None = Field(default=None, ge=0, le=3.5)
    z_c: float | None = Field(default=None, ge=0, le=3.5)
    z_d: float | None = Field(default=None, ge=0, le=3.5)
    z_imp_cd_a: float | None = Field(default=None, ge=0, le=3.5)
    z_imp_cd_b: float | None = Field(default=None, ge=0, le=3.5)
    lead_time_fallback_dias: int | None = Field(default=None, ge=1, le=90)
    winsor_k: float | None = Field(default=None, ge=0.5, le=6.0)
    nota: str | None = Field(default=None, max_length=500)
