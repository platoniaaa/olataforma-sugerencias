"""La regla InStock: consultar la lista y agregarle repuestos a mano.

La lista tiene dos origenes. Las **pautas del fabricante** entran por
`jobs/cargar_instock.py`, que recarga sola en cada corrida del motor. Lo que se
agrega **a mano** desde aca sobrevive a esa recarga porque la carga solo borra las
filas con `origen = "pauta"`.

Agregar un repuesto no es una accion de administracion sino de compra -es decir
"esto no puede faltar en el taller"-, asi que basta permiso de escritura, igual
que una sugerencia manual. Queda con motivo y autor para poder preguntar despues
por que esta ahi.

Los de la pauta NO se pueden borrar desde la plataforma: la proxima carga los
repondria y el boton estaria mintiendo. Para sacar uno de esos hay que cambiar la
pauta.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..schemas import InstockResumen
from ..services import auditoria_service, instock_service
from ..services.auth import requiere_escritura

router = APIRouter(prefix="/api/instock", tags=["instock"])


class InstockNuevo(BaseModel):
    producto: str = Field(min_length=1)
    minimo: int = Field(default=2, ge=1, le=999)
    motivo: str | None = None
    modelos: str | None = None


@router.get("/resumen", response_model=InstockResumen)
def resumen(db: Session = Depends(get_db)) -> InstockResumen:
    return InstockResumen(**instock_service.resumen(db))


@router.get("")
def listar(solo_manuales: bool = False, db: Session = Depends(get_db)) -> list[dict]:
    """La lista completa, con el origen de cada fila."""
    return instock_service.listar(db, solo_manuales=solo_manuales)


@router.post("", status_code=201)
def agregar(
    payload: InstockNuevo,
    db: Session = Depends(get_db),
    email: str = Depends(requiere_escritura),
) -> dict:
    """Suma un repuesto a la lista. Si ya estaba, lo reactiva y ajusta el minimo."""
    try:
        r = instock_service.agregar_manual(
            db,
            producto=payload.producto,
            minimo=payload.minimo,
            motivo=payload.motivo,
            modelos=payload.modelos,
            email=email,
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    auditoria_service.registrar(
        db,
        accion="instock_agregado" if not r["ya_estaba"] else "instock_actualizado",
        entidad="instock",
        entidad_id=r["producto"],
        usuario_email=email,
        detalle=f"minimo {r['minimo']}"
                + (f" - {payload.motivo}" if payload.motivo else ""),
    )
    db.commit()
    return r


@router.delete("/{producto:path}", status_code=204)
def quitar(
    producto: str,
    db: Session = Depends(get_db),
    email: str = Depends(requiere_escritura),
) -> None:
    """Saca de la lista un repuesto agregado a mano. Los de la pauta no se tocan."""
    try:
        instock_service.quitar_manual(db, producto)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except PermissionError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e

    auditoria_service.registrar(
        db, accion="instock_quitado", entidad="instock", entidad_id=producto,
        usuario_email=email, detalle="quitado desde la plataforma",
    )
    db.commit()
