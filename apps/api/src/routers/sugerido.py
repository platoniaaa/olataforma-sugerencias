"""Endpoints del sugerido: listado, KPIs, detalle y export a Excel."""
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Sugerido
from ..schemas import (
    AgrupadoRow,
    ColumnaFiltro,
    ExportRequest,
    SugeridoFiltros,
    SugeridoKpis,
    SugeridoPage,
    SugeridoRow,
    VentasResponse,
)
from ..services import excel_export, margen, sugerido_service
from ..services.auth import sucursales_permitidas
from ..services.sugerido_service import SUCURSALES_OCULTAS

router = APIRouter(prefix="/api/sugerido", tags=["sugerido"])

_OCULTAS_LOWER = {s.lower() for s in SUCURSALES_OCULTAS}


def _parse_filtros_columna(raw: str | None) -> list[ColumnaFiltro]:
    """Parsea el query param `filtros_columna` (JSON) a una lista de ColumnaFiltro.
    Tolera JSON invalido o entradas mal formadas (las ignora)."""
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return []
    out: list[ColumnaFiltro] = []
    if isinstance(data, list):
        for c in data:
            if isinstance(c, dict):
                try:
                    out.append(ColumnaFiltro(**c))
                except Exception:  # noqa: BLE001 - entrada del cliente, se ignora
                    pass
    return out


def _filtros(
    q: str | None = Query(None, description="Busqueda en producto o descripcion"),
    sucursal: list[str] = Query(default=[], description="Nombres de sucursal"),
    abc: list[str] = Query(default=[], description="Clasificacion ABC"),
    filtro1: list[str] = Query(default=[], description="Marca / segmento"),
    tipo_origen: list[str] = Query(default=[]),
    proveedor: str | None = Query(None),
    solo_pedir: bool = Query(True, description="Mostrar solo pedir=Si"),
    solo_nacionales: bool = Query(False, description="Excluye productos importados"),
    vista: str = Query("todas", description="todas | sucursales | cd | distribucion"),
    filtros_columna: str | None = Query(
        None, description="Filtros de columna del grid (JSON): [{campo, contiene|valores}]"
    ),
    permitidas: list[str] | None = Depends(sucursales_permitidas),
) -> SugeridoFiltros:
    return SugeridoFiltros(
        q=q, sucursales=sucursal, abc=abc, filtro1=filtro1,
        tipo_origen=tipo_origen, proveedor=proveedor, solo_pedir=solo_pedir,
        solo_nacionales=solo_nacionales, vista=vista,
        sucursales_permitidas=permitidas,
        filtros_columna=_parse_filtros_columna(filtros_columna),
    )


@router.get("", response_model=SugeridoPage)
def listar(
    f: SugeridoFiltros = Depends(_filtros),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=5000),
    sort: str | None = Query(None, description="Campo de orden, prefijo '-' para desc"),
    db: Session = Depends(get_db),
):
    items, total = sugerido_service.listar(db, f, page=page, limit=limit, sort=sort)
    # items son dicts (mix de sugerido + catalogo). Validamos explicitamente
    # para que Pydantic no intente getattr en dicts.
    rows = [SugeridoRow.model_validate(i) for i in items]
    return SugeridoPage(items=rows, total=total, page=page, limit=limit)


@router.get("/kpis", response_model=SugeridoKpis)
def kpis(f: SugeridoFiltros = Depends(_filtros), db: Session = Depends(get_db)):
    return SugeridoKpis(**sugerido_service.kpis(db, f))


@router.get("/agrupado", response_model=list[AgrupadoRow])
def agrupado(
    por: str = Query("sucursal", description="Dimension: sucursal | marca | proveedor"),
    f: SugeridoFiltros = Depends(_filtros),
    db: Session = Depends(get_db),
):
    try:
        return sugerido_service.agrupado(db, f, por)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


def _sin_acceso(sucursal_id: str, permitidas: list[str] | None) -> bool:
    # Sucursal cerrada/oculta: se comporta como inexistente (404) aunque se pida por URL.
    if sucursal_id and sucursal_id.strip().lower() in _OCULTAS_LOWER:
        return True
    return permitidas is not None and sucursal_id not in permitidas


@router.get("/{producto}/{sucursal_id}/ventas", response_model=VentasResponse)
def ventas(
    producto: str, sucursal_id: str, db: Session = Depends(get_db),
    permitidas: list[str] | None = Depends(sucursales_permitidas),
):
    """Histórico de venta del producto en la sucursal (últimos 12 meses)."""
    if _sin_acceso(sucursal_id, permitidas):
        raise HTTPException(status_code=404, detail="No existe sugerido para ese producto/sucursal")
    return VentasResponse(**sugerido_service.ventas_12m(db, producto, sucursal_id))


@router.get("/{producto}/{sucursal_id}", response_model=SugeridoRow)
def detalle(
    producto: str, sucursal_id: str, db: Session = Depends(get_db),
    permitidas: list[str] | None = Depends(sucursales_permitidas),
):
    if _sin_acceso(sucursal_id, permitidas):
        raise HTTPException(status_code=404, detail="No existe sugerido para ese producto/sucursal")
    row = sugerido_service.detalle(db, producto, sucursal_id)
    if not row:
        raise HTTPException(status_code=404, detail="No existe sugerido para ese producto/sucursal")
    # El detalle no pasa por listar(): el margen se calcula aca para que la ficha
    # del producto muestre lo mismo que las columnas de la tabla.
    fila = {c.name: getattr(row, c.name) for c in Sugerido.__table__.columns}
    margen.calcular_margen(fila)
    return SugeridoRow.model_validate(fila)


@router.post("/export-excel")
def export_excel(
    req: ExportRequest, db: Session = Depends(get_db),
    permitidas: list[str] | None = Depends(sucursales_permitidas),
):
    # Si vienen IDs, exportamos exactamente esas filas (preserva los filtros que el
    # usuario aplico en las columnas del AG Grid). Sino, usamos filtros server-side.
    # La restriccion por usuario (permitidas) se aplica SIEMPRE del lado servidor,
    # ignorando lo que venga en el body.
    if req.ids:
        items = sugerido_service.listar_por_ids(db, req.ids, sucursales_permitidas=permitidas)
    else:
        req.filtros.sucursales_permitidas = permitidas
        items, _ = sugerido_service.listar(db, req.filtros, page=1, limit=100000, sort=req.sort)
    contenido = excel_export.generar_excel(items, req.columnas)
    nombre = excel_export.nombre_archivo()
    return StreamingResponse(
        iter([contenido]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )
