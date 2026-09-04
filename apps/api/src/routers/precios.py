"""La lista de precios: verla, decidir sobre un precio, crear productos y exportar al ERP.

Permisos, en dos niveles y por endpoint (el router se monta con el gate de
Abastecimiento, asi que el vendedor de sucursal no entra a nada de esto):

- **Ver y exportar**: cualquiera de Abastecimiento.
- **Editar un precio** (fijo, congelar, tipo, procedencia, crear producto,
  marcar cambios vistos, recalcular): admin o email en `EMAILS_PRECIOS`. Es el
  mismo esquema de Calibracion: quien mantiene la lista no tiene por que
  administrar la plataforma.
- **La politica** (factores y rubros): solo admin. Un factor mueve miles de
  precios de una; un precio fijo mueve uno.

No va bajo /api/admin por la misma razon tecnica que Calibracion: las
dependencias del include se ejecutan siempre y no se pueden excluir por endpoint.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..schemas.precios import (
    FactoresIn,
    OverrideIn,
    PrecioDetalleOut,
    PrecioFiltros,
    PrecioPage,
    PrecioRow,
    ProductoNuevoIn,
    RubrosIn,
    VistosIn,
)
from ..services import politica_precio_service as politica
from ..services import precios_service
from ..services.auth import requiere_admin, requiere_precios

router = APIRouter(prefix="/api/precios", tags=["precios"])

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _filtros(
    q: str | None = Query(None, description="Busca en codigo o glosa"),
    rubro: list[str] = Query(default=[]),
    tipo: list[str] = Query(default=[]),
    procedencia: list[str] = Query(default=[]),
    estado: list[str] = Query(default=[]),
    origen: str | None = Query(None, description="maestro | manual"),
    con_cambios: bool = Query(False, description="Solo productos con cambios sin revisar"),
    con_stock: bool = Query(False),
) -> PrecioFiltros:
    return PrecioFiltros(
        q=q, rubro=rubro, tipo=tipo, procedencia=procedencia, estado=estado,
        origen=origen, con_cambios=con_cambios, con_stock=con_stock,
    )


# ------------------------------------------------------------------ lectura
@router.get("", response_model=PrecioPage)
def listar(
    f: PrecioFiltros = Depends(_filtros),
    page: int = Query(1, ge=1),
    limit: int = Query(200, ge=1, le=2000),
    sort: str | None = Query(None, description="columna, con '-' adelante para descendente"),
    db: Session = Depends(get_db),
) -> PrecioPage:
    items, total = precios_service.listar(db, f, page=page, limit=limit, sort=sort)
    return PrecioPage(items=[PrecioRow.model_validate(i) for i in items], total=total, page=page, limit=limit)


@router.get("/filtros")
def filtros(db: Session = Depends(get_db)) -> dict:
    return precios_service.opciones_filtros(db)


@router.get("/resumen")
def resumen(db: Session = Depends(get_db)) -> dict:
    return precios_service.resumen(db)


@router.get("/politica/factores")
def factores(db: Session = Depends(get_db)) -> list[dict]:
    return politica.listar_factores(db)


@router.get("/politica/rubros")
def rubros(db: Session = Depends(get_db)) -> list[dict]:
    return politica.listar_rubros(db)


@router.get("/exportar")
def exportar(
    solo_diferencias: bool = Query(False, description="Solo lo que cambio desde el ultimo envio"),
    formato: str = Query("erp", pattern="^(erp|completa)$"),
    registrar: bool = Query(True, description="Anotar este envio para el proximo delta"),
    db: Session = Depends(get_db),
    email: str = Depends(requiere_precios),
):
    """El Excel para subir al ERP. `erp` son las 3 columnas que el ERP acepta
    (SKU | Precio_Optimo | Costo); `completa` es para revisar."""
    contenido, nombre, n = precios_service.exportar(
        db, solo_diferencias=solo_diferencias, registrar=registrar and formato == "erp",
        usuario=email, formato=formato,
    )
    return StreamingResponse(
        iter([contenido]), media_type=_XLSX,
        headers={"Content-Disposition": f'attachment; filename="{nombre}"', "X-Filas": str(n)},
    )


# Va ANTES del catch-all {producto:path}, si no FastAPI lo lee como un producto.
@router.get("/{producto:path}", response_model=PrecioDetalleOut)
def detalle(producto: str, db: Session = Depends(get_db)) -> dict:
    d = precios_service.detalle(db, producto)
    if not d:
        raise HTTPException(status_code=404, detail="El producto no esta en la lista de precios")
    return d


# ----------------------------------------------------------------- escritura
@router.post("/recalcular")
def recalcular(
    refrescar_insumos: bool = Query(True),
    db: Session = Depends(get_db),
    email: str = Depends(requiere_precios),
) -> dict:
    """Recalcula toda la lista con el stock, costo y compras que tiene la plataforma."""
    return precios_service.recalcular(db, usuario=email, refrescar_insumos=refrescar_insumos)


@router.post("/cambios/vistos")
def marcar_vistos(
    payload: VistosIn, db: Session = Depends(get_db), email: str = Depends(requiere_precios),
) -> dict:
    return precios_service.marcar_vistos(db, payload.productos, email)


@router.post("", status_code=201, response_model=PrecioRow)
def crear(
    payload: ProductoNuevoIn, db: Session = Depends(get_db), email: str = Depends(requiere_precios),
) -> dict:
    """Un producto nuevo, creado desde la plataforma. Sale en el proximo envio al ERP."""
    try:
        return precios_service.crear_producto(db, payload.model_dump(), email)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.put("/{producto:path}/override", response_model=PrecioRow)
def guardar_override(
    producto: str, payload: OverrideIn,
    db: Session = Depends(get_db), email: str = Depends(requiere_precios),
) -> dict:
    """Precio fijo, congelar, tipo o procedencia a mano. Solo se tocan los campos que vienen."""
    datos = payload.model_dump(exclude_unset=True)
    if not datos:
        raise HTTPException(status_code=422, detail="No viene ningun campo para cambiar")
    try:
        return precios_service.guardar_override(db, producto, datos, email)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.delete("/{producto:path}/override", response_model=PrecioRow)
def quitar_override(
    producto: str, db: Session = Depends(get_db), email: str = Depends(requiere_precios),
) -> dict:
    """Vuelve el producto a la regla: sin precio fijo, sin congelar, sin clasificacion manual."""
    try:
        return precios_service.quitar_override(db, producto, email)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


# ------------------------------------------------------------------ politica
@router.put("/politica/factores")
def guardar_factores(
    payload: FactoresIn, db: Session = Depends(get_db), email: str = Depends(requiere_admin),
) -> dict:
    try:
        r = politica.guardar_factores(db, [f.model_dump() for f in payload.filas], email)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    # Un factor nuevo cambia precios: se recalcula con los insumos que ya hay.
    r["recalculo"] = precios_service.recalcular(db, usuario=email, refrescar_insumos=False)
    return r


@router.put("/politica/rubros")
def guardar_rubros(
    payload: RubrosIn, db: Session = Depends(get_db), email: str = Depends(requiere_admin),
) -> dict:
    try:
        r = politica.guardar_rubros(db, [f.model_dump() for f in payload.filas], email)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    r["recalculo"] = precios_service.recalcular(db, usuario=email, refrescar_insumos=False)
    return r
