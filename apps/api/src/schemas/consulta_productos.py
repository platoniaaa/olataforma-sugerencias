"""Consulta de productos para el vendedor de sucursal.

Es la ficha del catálogo SIN lo que un vendedor no debe ver: el costo, el stock
mínimo y máximo y la clasificación de stock son datos de Abastecimiento. Se declaran
acá aparte (y no se reutilizan `CatalogoRow` / `CatalogoDetalle`) a propósito: FastAPI
serializa solo los campos del `response_model`, así que aunque el servicio de catálogo
devuelva el costo en su diccionario, nunca sale por esta ruta. Si se agrega un campo
sensible al catálogo, no aparece aquí hasta que alguien lo pida.
"""
from pydantic import BaseModel, ConfigDict, Field

from .producto_catalogo import ReemplazoFordRow, StockSucursalRow


class ProductoConsultaRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    producto: str
    glosa: str | None = None
    familia: str | None = None
    subfamilia: str | None = None
    procedencia: str | None = None
    categoria: str | None = None
    unidad: str | None = None
    # Precio de venta del ERP (el que cobra el vendedor). El costo NO va.
    precio: float | None = None
    stock_total: float | None = None
    # Equivalentes del mix, separados por coma (se arma igual que en el catálogo).
    reemplazo: str | None = None


class ProductoConsultaPage(BaseModel):
    items: list[ProductoConsultaRow]
    total: int
    page: int
    limit: int


class ProductoConsultaDetalle(ProductoConsultaRow):
    sub_categoria: str | None = None
    tipo_producto: str | None = None
    sub_modelo: str | None = None
    cilindrada: str | None = None
    combustible: str | None = None
    anio: str | None = None
    stock_por_sucursal: list[StockSucursalRow] = Field(default_factory=list)
    reemplazo_ford: ReemplazoFordRow | None = None
