"""Endpoint de consulta de la regla InStock (repuestos de pauta con minimo).

Solo lectura: la lista se arma desde las pautas del fabricante con
`jobs/cargar_instock.py`, no desde la interfaz. La pantalla de sugerencias
manuales la muestra en la pestania "Recurrentes" porque, para el comprador,
hace lo mismo que una recurrente de "mantener N unidades" que nunca vence.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..schemas import InstockResumen
from ..services import instock_service

router = APIRouter(prefix="/api/instock", tags=["instock"])


@router.get("/resumen", response_model=InstockResumen)
def resumen(db: Session = Depends(get_db)) -> InstockResumen:
    return InstockResumen(**instock_service.resumen(db))
