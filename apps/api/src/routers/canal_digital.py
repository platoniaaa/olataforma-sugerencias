"""Canal Digital: reposicion semanal de la bodega 430 (y otras bodegas del canal).

Hoy: publicacion de la venta semanal (la hace el motor, como admin) y consulta de lo cargado.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..services import canal_digital_service as svc
from ..services.auth import requiere_admin

router = APIRouter(prefix="/api/canal-digital", tags=["canal digital"])


@router.get("/meta")
def meta(bodega: str = "430", db: Session = Depends(get_db)) -> dict:
    """Que venta semanal hay cargada para la bodega."""
    return svc.meta_ventas(db, bodega)


@router.post("/ventas", dependencies=[Depends(requiere_admin)])
def publicar_ventas(payload: dict, db: Session = Depends(get_db)) -> dict:
    """El motor publica la venta semanal del canal. Reemplaza SOLO los periodos que vienen.

    payload: {"bodega": "430", "filas": [{producto, semana, periodo, unid_brutas,
    unid_devueltas, valor_costo, unid_liquidacion, n_lineas}]}
    """
    filas = payload.get("filas")
    if not isinstance(filas, list):
        raise HTTPException(status_code=400, detail="Falta la lista 'filas'")
    bodega = str(payload.get("bodega") or "430").strip()
    svc.asegurar_bodega(db, bodega)
    return svc.reemplazar_ventas(db, bodega, filas)
