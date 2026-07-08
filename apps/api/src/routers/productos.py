"""Endpoints del catalogo: productos y sucursales."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import DimProducto, DimSucursal, ProductoCatalogo
from ..schemas import ProductoOut, ProductoPage, SucursalOut
from ..services.auth import sucursales_permitidas
from ..services.sugerido_service import SUCURSALES_OCULTAS

router = APIRouter(prefix="/api", tags=["catalogo"])


@router.get("/productos", response_model=ProductoPage)
def listar_productos(
    q: str | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
):
    base = select(DimProducto)
    if q:
        like = f"%{q}%"
        base = base.where(
            or_(DimProducto.producto.ilike(like), DimProducto.descripcion.ilike(like))
        )
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    items = db.scalars(
        base.order_by(DimProducto.producto).offset((page - 1) * limit).limit(limit)
    ).all()
    items_list = [
        ProductoOut(
            producto=p.producto,
            descripcion=p.descripcion,
            filtro1_final=p.filtro1_final,
            unidad_medida=p.unidad_medida,
            costo_unitario=p.costo_unitario,
            proveedor=p.proveedor,
            es_importado=p.es_importado,
        )
        for p in items
    ]

    # Si la busqueda devuelve poco del catalogo del BI, completamos con el
    # catalogo maestro (productos que no estan en dim_producto). Asi el
    # autocomplete del modal puede sugerir cualquier producto del listado maestro.
    if q and len(items_list) < limit:
        codigos = {p.producto for p in items}
        falta = limit - len(items_list)
        like = f"%{q}%"
        cat_stmt = (
            select(ProductoCatalogo)
            .where(
                or_(
                    ProductoCatalogo.producto.ilike(like),
                    ProductoCatalogo.glosa.ilike(like),
                )
            )
            .where(~ProductoCatalogo.producto.in_(codigos))
            .order_by(ProductoCatalogo.producto.asc())
            .limit(falta)
        )
        for c in db.scalars(cat_stmt).all():
            items_list.append(
                ProductoOut(
                    producto=c.producto,
                    descripcion=c.glosa,
                    filtro1_final=None,
                    unidad_medida=c.unidad,
                    costo_unitario=c.costo,
                    proveedor=None,
                    es_importado=None,
                )
            )
        # Total aproximado: lo del BI + lo que matchea en catalogo (limitado)
        total = total + db.scalar(
            select(func.count())
            .select_from(
                select(ProductoCatalogo.id)
                .where(
                    or_(
                        ProductoCatalogo.producto.ilike(like),
                        ProductoCatalogo.glosa.ilike(like),
                    )
                )
                .where(~ProductoCatalogo.producto.in_(codigos))
                .subquery()
            )
        ) or 0

    return ProductoPage(items=items_list, total=total, page=page, limit=limit)


@router.get("/productos/{producto}", response_model=ProductoOut)
def detalle_producto(producto: str, db: Session = Depends(get_db)):
    p = db.get(DimProducto, producto)
    if not p:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    return p


@router.get("/sucursales", response_model=list[SucursalOut])
def listar_sucursales(
    db: Session = Depends(get_db),
    permitidas: list[str] | None = Depends(sucursales_permitidas),
):
    stmt = select(DimSucursal).order_by(DimSucursal.prioridad_cd)
    if permitidas is not None:  # usuario restringido: solo sus sucursales
        stmt = stmt.where(DimSucursal.sucursal_id.in_(permitidas))
    # Ocultar sucursales cerradas del selector (misma regla que el sugerido).
    ocultas = [s.lower() for s in SUCURSALES_OCULTAS]
    if ocultas:
        stmt = stmt.where(func.lower(DimSucursal.sucursal_id).notin_(ocultas))
    return list(db.scalars(stmt).all())
