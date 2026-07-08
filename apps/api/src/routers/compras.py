"""Endpoints del agente comprador: carros de compra por proveedor + export."""
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..schemas import CarrosResponse, ExportCarrosRequest, SugeridoFiltros
from ..services import compras_service, excel_export
from ..services.auth import sucursales_permitidas

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
