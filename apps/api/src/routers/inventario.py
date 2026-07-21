"""Endpoints de inventario: salud (inmovilizado, sobre-stock, quiebres) y simulador."""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..schemas import SugeridoFiltros
from ..services import inventario_service, simulador_service
from ..services.auth import sucursales_permitidas

router = APIRouter(prefix="/api/inventario", tags=["inventario"])


class SimulacionRequest(BaseModel):
    """Parametros a simular. Los que no vengan usan los del modelo vigente."""

    sucursales: list[str] = Field(default_factory=list)
    marcas: list[str] = Field(default_factory=list)
    ciclo_orden_dias: int = Field(simulador_service.CICLO_ORDEN_DIAS, ge=1, le=60)
    ciclo_orden_dias_cd: int = Field(simulador_service.CICLO_ORDEN_DIAS_CD, ge=1, le=60)
    z_por_clase: dict[str, float] | None = None
    factor_lead_time: float = Field(1.0, gt=0, le=5)


@router.get("/salud")
def salud(
    sucursal: list[str] = Query(default=[], description="Nombres de sucursal"),
    filtro1: list[str] = Query(default=[], description="Marca / segmento"),
    dias_sobre_stock: int = Query(
        inventario_service.DIAS_SOBRE_STOCK, ge=30, le=1825,
        description="Sobre cuantos dias de cobertura se considera sobre-stock",
    ),
    db: Session = Depends(get_db),
    permitidas: list[str] | None = Depends(sucursales_permitidas),
):
    f = SugeridoFiltros(
        sucursales=sucursal, filtro1=filtro1, solo_pedir=False,
        sucursales_permitidas=permitidas,
    )
    return inventario_service.salud(db, f, dias_sobre_stock=dias_sobre_stock)


@router.post("/simular")
def simular(
    req: SimulacionRequest,
    db: Session = Depends(get_db),
    permitidas: list[str] | None = Depends(sucursales_permitidas),
):
    """Recalcula el sugerido con otros parametros y compara contra el vigente.

    No toca ningun dato: es un calculo al vuelo para dimensionar el impacto."""
    f = SugeridoFiltros(
        sucursales=req.sucursales, filtro1=req.marcas, solo_pedir=False,
        sucursales_permitidas=permitidas,
    )
    return simulador_service.simular(
        db, f,
        ciclo_orden_dias=req.ciclo_orden_dias,
        ciclo_orden_dias_cd=req.ciclo_orden_dias_cd,
        z_por_clase=req.z_por_clase,
        factor_lead_time=req.factor_lead_time,
    )
