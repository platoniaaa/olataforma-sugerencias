"""El tablero mensual de Abastecimiento.

Solo lectura y sin permisos especiales: es el resumen que mira la gerencia, y
esconderlo detras de un rol solo lograria que lo pidieran por correo.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..services import abc_stock_service, tablero_service

router = APIRouter(prefix="/api/tablero", tags=["tablero"])


@router.get("")
def mensual(
    periodo: str | None = Query(
        None, description='Mes en formato "YYYY-MM". Por defecto, el ultimo con datos.'
    ),
    db: Session = Depends(get_db),
) -> dict:
    if periodo is not None:
        # Un periodo mal formado reventaria adentro con un ValueError feo; mejor
        # decir que se espera.
        ok = (len(periodo) == 7 and periodo[4] == "-"
              and periodo[:4].isdigit() and periodo[5:].isdigit()
              and 1 <= int(periodo[5:]) <= 12)
        if not ok:
            raise HTTPException(
                status_code=422, detail='El periodo va como "YYYY-MM", por ejemplo "2026-08".')
    return tablero_service.mensual(db, periodo)


# --- Submodulo: ABC por sucursal de lo que hay en stock -------------------------
#
# El tablero mide el mes; esto mira la foto de hoy. Va aca y no en su propia
# seccion porque la pregunta es la misma que se hace la gerencia al leer el
# tablero: de lo que tengo guardado, que se mueve y que no.


@router.get("/abc-stock")
def abc_stock(db: Session = Depends(get_db)) -> dict:
    """La matriz sucursal x clase ABC de todo el stock, con como leerla."""
    return abc_stock_service.resumen(db)


@router.get("/abc-stock/detalle")
def abc_stock_detalle(
    sucursal: list[str] = Query(default=[]),
    clase: list[str] = Query(default=[], description="A | B | C | D"),
    base_clase: str | None = Query(
        None, description='"Modelo" o "Sin venta 12m"'),
    q: str | None = Query(None, description="Busca en codigo o descripcion"),
    page: int = Query(1, ge=1),
    limit: int = Query(200, ge=1, le=2000),
    db: Session = Depends(get_db),
) -> dict:
    malas = [c for c in clase if c.upper() not in abc_stock_service.CLASES]
    if malas:
        raise HTTPException(status_code=422, detail=f"Clases no validas: {malas}. Van A, B, C o D.")
    items, total = abc_stock_service.detalle(
        db, sucursal=sucursal, clase=clase, base_clase=base_clase, q=q, page=page, limit=limit)
    return {"items": items, "total": total, "page": page, "limit": limit}
