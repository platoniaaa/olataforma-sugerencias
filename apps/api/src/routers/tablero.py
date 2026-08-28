"""El tablero mensual de Abastecimiento.

Solo lectura y sin permisos especiales: es el resumen que mira la gerencia, y
esconderlo detras de un rol solo lograria que lo pidieran por correo.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..services import tablero_service

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
