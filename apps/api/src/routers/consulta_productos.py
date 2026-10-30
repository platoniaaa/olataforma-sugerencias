"""Consulta de productos para el vendedor de sucursal (y cualquier usuario con sesión).

Lista con buscador y, por producto: stock en todas las sucursales, reemplazos (los
equivalentes del mix y lo que dice FORD) y la venta de los últimos 12 meses.

Es la misma información del catálogo de Abastecimiento, pero por una ruta propia
porque `/api/catalogo` está cerrada para el vendedor (ver `requiere_comprador`) y
porque acá el costo no sale nunca: las respuestas pasan por modelos que no lo tienen
(`schemas/consulta_productos.py`). No hay escritura: es solo lectura.

Ojo con el orden: `/ventas` y `/grupo-ventas` van ANTES del `{producto:path}` de
abajo, si no FastAPI los enruta como producto="<producto>/ventas".
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..schemas import CatalogoFiltros, VentasResponse
from ..schemas.consulta_productos import (
    ProductoConsultaDetalle,
    ProductoConsultaPage,
    ProductoConsultaRow,
)
from ..services import catalogo_service, sugerido_service

router = APIRouter(prefix="/api/consulta/productos", tags=["consulta-productos"])

# Una lista de 5.000 filas en un celular no la lee nadie: se busca y se pagina.
LIMITE_MAXIMO = 200


@router.get("", response_model=ProductoConsultaPage)
def listar(
    q: str | None = Query(None, description="Búsqueda en código o descripción"),
    familia: list[str] = Query(default=[]),
    procedencia: list[str] = Query(default=[]),
    categoria: list[str] = Query(default=[]),
    con_stock: bool = Query(False, description="Solo productos con stock > 0"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=LIMITE_MAXIMO),
    db: Session = Depends(get_db),
) -> ProductoConsultaPage:
    f = CatalogoFiltros(
        q=q, familia=familia, procedencia=procedencia,
        categoria=categoria, con_stock=con_stock,
    )
    items, total = catalogo_service.listar(db, f, page=page, limit=limit, sort="producto")
    return ProductoConsultaPage(
        items=[ProductoConsultaRow.model_validate(i) for i in items],
        total=total,
        page=page,
        limit=limit,
    )


@router.get("/filtros")
def filtros_disponibles(db: Session = Depends(get_db)) -> dict:
    """Listas únicas de familia/procedencia/categoría para los desplegables."""
    return catalogo_service.opciones_filtros(db)


@router.get("/{producto:path}/ventas", response_model=VentasResponse)
def ventas(producto: str, db: Session = Depends(get_db)) -> VentasResponse:
    """Venta del producto, mes a mes, en TODAS las sucursales (12 meses). Solo
    unidades: no lleva costo ni margen."""
    return VentasResponse(**sugerido_service.ventas_12m(db, producto))


@router.get("/{producto:path}/grupo-ventas")
def grupo_ventas(producto: str, db: Session = Depends(get_db)) -> dict:
    """Venta mes a mes de cada código del grupo de reemplazos (vacío si no tiene)."""
    return sugerido_service.grupo_ventas(db, producto)


@router.get("/{producto:path}", response_model=ProductoConsultaDetalle)
def detalle(producto: str, db: Session = Depends(get_db)) -> ProductoConsultaDetalle:
    d = catalogo_service.detalle(db, producto)
    if not d:
        raise HTTPException(status_code=404, detail="Producto no esta en el catalogo")
    return ProductoConsultaDetalle.model_validate(d)
