"""Endpoints de salud del inventario (inmovilizado, sobre-stock, quiebres)."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..schemas import SugeridoFiltros
from ..services import inventario_service
from ..services.auth import sucursales_permitidas

router = APIRouter(prefix="/api/inventario", tags=["inventario"])


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
