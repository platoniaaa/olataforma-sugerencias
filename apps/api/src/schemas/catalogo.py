"""Schemas del catalogo (productos y sucursales)."""
from pydantic import BaseModel, ConfigDict


class ProductoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    producto: str
    descripcion: str | None = None
    filtro1_final: str | None = None
    unidad_medida: str | None = None
    costo_unitario: float | None = None
    proveedor: str | None = None
    es_importado: bool | None = None
    # Cuando FORD dio de baja el codigo, cual lo reemplaza (en codigo de Curifor).
    # Viaja en el autocomplete para que el modal de sugerencia manual pueda avisar
    # mientras se escribe, sin una segunda llamada por cada tecla.
    reemplazado_por: str | None = None


class ProductoPage(BaseModel):
    items: list[ProductoOut]
    total: int
    page: int
    limit: int


class SucursalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sucursal_id: str
    nombre: str | None = None
    region: str | None = None
    abastece_desde_cd: str | None = None
    prioridad_cd: int | None = None
