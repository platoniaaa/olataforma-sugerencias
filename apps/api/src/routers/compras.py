"""Endpoints del agente comprador: carros de compra por proveedor + export."""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..schemas import CarrosResponse, ExportCarrosRequest, SugeridoFiltros
from ..services import compras_service, excel_export, pedidos_service
from ..services.auth import requiere_escritura, sucursales_permitidas


class PedidoCreate(BaseModel):
    producto: str
    sucursal_id: str
    unidades: float
    n_oc: str | None = None
    proveedor: str | None = None

router = APIRouter(prefix="/api/compras", tags=["compras"])


def _filtros(
    q: str | None = Query(None),
    sucursal: list[str] = Query(default=[]),
    abc: list[str] = Query(default=[]),
    filtro1: list[str] = Query(default=[]),
    tipo_origen: list[str] = Query(default=[]),
    proveedor: str | None = Query(None),
    solo_pedir: bool = Query(True),
    permitidas: list[str] | None = Depends(sucursales_permitidas),
) -> SugeridoFiltros:
    return SugeridoFiltros(
        q=q, sucursales=sucursal, abc=abc, filtro1=filtro1,
        tipo_origen=tipo_origen, proveedor=proveedor, solo_pedir=solo_pedir,
        sucursales_permitidas=permitidas,
    )


@router.get("/carros", response_model=CarrosResponse)
def carros(f: SugeridoFiltros = Depends(_filtros), db: Session = Depends(get_db)):
    """Arma los carros de compra agrupados por proveedor segun los filtros."""
    return compras_service.carros_por_proveedor(db, f)


@router.get("/pedidos")
def listar_pedidos(
    producto: str | None = Query(None),
    sucursal_id: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """Lineas del sugerido que ya se pidieron."""
    filas = pedidos_service.listar(db, producto=producto, sucursal_id=sucursal_id)
    return {
        "items": [
            {
                "id": f.id, "producto": f.producto, "sucursal_id": f.sucursal_id,
                "unidades": f.unidades, "n_oc": f.n_oc, "proveedor": f.proveedor,
                "recibido": f.recibido, "fecha_recepcion": f.fecha_recepcion,
                "creado_por": f.creado_por, "creado_en": f.creado_en,
            }
            for f in filas
        ]
    }


@router.post("/pedidos", status_code=201)
def crear_pedido(
    payload: PedidoCreate,
    db: Session = Depends(get_db),
    email: str = Depends(requiere_escritura),
):
    """Marca que una linea del sugerido ya se pidio (con su N de OC si se tiene)."""
    linea = pedidos_service.registrar(
        db,
        producto=payload.producto,
        sucursal_id=payload.sucursal_id,
        unidades=payload.unidades,
        n_oc=payload.n_oc,
        proveedor=payload.proveedor,
        usuario_email=email,
    )
    return {"id": linea.id, "producto": linea.producto, "unidades": linea.unidades}


@router.post("/pedidos/{linea_id}/recibida")
def marcar_recibida(
    linea_id: str,
    db: Session = Depends(get_db),
    _email: str = Depends(requiere_escritura),
):
    linea = pedidos_service.marcar_recibida(db, linea_id)
    if not linea:
        raise HTTPException(status_code=404, detail="La linea no existe")
    return {"id": linea.id, "recibido": linea.recibido}


@router.delete("/pedidos/{linea_id}", status_code=204)
def eliminar_pedido(
    linea_id: str,
    db: Session = Depends(get_db),
    _email: str = Depends(requiere_escritura),
):
    if not pedidos_service.eliminar(db, linea_id):
        raise HTTPException(status_code=404, detail="La linea no existe")


@router.post("/export-excel")
def export_excel(
    req: ExportCarrosRequest, db: Session = Depends(get_db),
    permitidas: list[str] | None = Depends(sucursales_permitidas),
):
    """Genera la orden de compra en Excel (una hoja por proveedor)."""
    # La restriccion por usuario se aplica del lado servidor (ignora el body).
    req.filtros.sucursales_permitidas = permitidas
    resp = compras_service.carros_por_proveedor(db, req.filtros)
    contenido = excel_export.generar_orden_compra(resp.carros, req.proveedor)
    nombre = excel_export.nombre_orden(req.proveedor)
    return StreamingResponse(
        iter([contenido]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )
