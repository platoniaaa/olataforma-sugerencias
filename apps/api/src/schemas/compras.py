"""Schemas del agente comprador: carros de compra agrupados por proveedor."""
from pydantic import BaseModel, Field

from .sugerido import SugeridoFiltros


class LineaCarro(BaseModel):
    producto: str
    descripcion: str | None = None
    clasificacion_abc: str | None = None
    cantidad: float
    costo_unitario: float | None = None
    subtotal_clp: float = 0


class CarroProveedor(BaseModel):
    proveedor: str
    n_productos: int = 0
    total_unidades: float = 0
    total_clp: float = 0
    lineas: list[LineaCarro] = Field(default_factory=list)


class CarrosResponse(BaseModel):
    carros: list[CarroProveedor] = Field(default_factory=list)
    total_proveedores: int = 0
    total_clp: float = 0
    total_unidades: float = 0


class ExportCarrosRequest(BaseModel):
    filtros: SugeridoFiltros = Field(default_factory=SugeridoFiltros)
    # Si se indica, solo exporta el carro de ese proveedor; si no, todos.
    proveedor: str | None = None
