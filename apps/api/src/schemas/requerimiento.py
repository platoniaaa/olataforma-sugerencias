"""Schemas del requerimiento de sucursal (pegar lista -> decidir -> archivo)."""
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class LineaPegada(BaseModel):
    """Una linea tal como salio del texto pegado."""

    producto: str
    cantidad: float | None = None
    texto_original: str | None = None


class AnalizarTextoRequest(BaseModel):
    """Lo que pega el comprador, tal cual. El parseo va en el servidor."""

    sucursal_id: str
    texto: str


class AnalizarLineasRequest(BaseModel):
    """Re-analisis con las lineas ya editadas en pantalla."""

    sucursal_id: str
    lineas: list[LineaPegada] = Field(default_factory=list)


class FrecuenciaOtraSucursal(BaseModel):
    sucursal_id: str
    nombre_sucursal: str
    meses_con_venta_12m: int
    clasificacion_abc: str | None = None


class LineaRequerimiento(BaseModel):
    """Una linea con todo lo necesario para decidir comprarla o no."""

    producto: str
    texto_original: str | None = None
    cantidad: float | None = None
    # en_sugerido | sin_venta_local | no_existe
    estado: str
    duplicado: bool = False
    descripcion: str | None = None
    proveedor: str | None = None
    costo_unitario: float | None = None
    reemplazos: str | None = None
    nombre_sucursal: str | None = None
    stock_sucursal: float | None = None
    stock_cd: float | None = None
    stock_nacional: float | None = None
    meses_con_venta_3m: int | None = None
    meses_con_venta_6m: int | None = None
    meses_con_venta_12m: int | None = None
    clasificacion_abc: str | None = None
    total_sugerido_suc: float | None = None
    frecuencia_otra_sucursal: FrecuenciaOtraSucursal | None = None


class ResumenRequerimiento(BaseModel):
    total: int = 0
    en_sugerido: int = 0
    sin_venta_local: int = 0
    no_existe: int = 0
    duplicados: int = 0


class RequerimientoResponse(BaseModel):
    lineas: list[LineaRequerimiento] = Field(default_factory=list)
    resumen: ResumenRequerimiento = Field(default_factory=ResumenRequerimiento)


class ArchivoPortalRequest(BaseModel):
    """Lineas ya decididas -> archivo del portal."""

    proveedor: str  # FORD | GILDEMEISTER
    sucursal_id: str | None = None
    lineas: list[LineaPegada] = Field(default_factory=list)


class SkuProveedorFila(BaseModel):
    clave: str
    sku: str


class SkuProveedorCarga(BaseModel):
    """Lo que publica el motor: la equivalencia codigo -> SKU del portal."""

    proveedor: str
    filas: list[SkuProveedorFila] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Carro del vendedor: buscar en la lista de precios, pedir, y que el comprador
# lo reciba en su bandeja. Reemplaza el correo.
# --------------------------------------------------------------------------- #
class ProductoBuscado(BaseModel):
    """Una fila del buscador del carro: lo minimo para decidir si es el correcto."""

    producto: str
    descripcion: str | None = None
    precio: float | None = None
    stock_sucursal: float | None = None
    stock_nacional: float | None = None
    familia: str | None = None


class ProductoPegado(ProductoBuscado):
    """Una linea de la lista pegada, ya resuelta contra la lista de precios.

    Las que no existen vuelven igual, con `encontrado=False`: el vendedor tiene
    que VER que su codigo no existe, no que desaparezca sin decir nada.
    """

    cantidad: float | None = None
    encontrado: bool = True
    texto_original: str | None = None


class LineaNueva(BaseModel):
    """Una linea del carro tal como la manda el vendedor."""

    producto: str
    cantidad: float
    comentario: str | None = None

    @field_validator("cantidad")
    @classmethod
    def _positiva(cls, v: float) -> float:
        # Poka-yoke: una cantidad 0 o negativa es siempre un error de tipeo, y si
        # entra a la base el comprador tiene que adivinar que quiso pedir.
        if v is None or v <= 0:
            raise ValueError("La cantidad tiene que ser mayor que cero.")
        return v


class RequerimientoCreate(BaseModel):
    """Lo que envia el vendedor al apretar "Enviar requerimiento"."""

    sucursal_id: str | None = None  # None = su unica sucursal
    nota: str | None = None
    lineas: list[LineaNueva] = Field(default_factory=list)


class LineaGuardada(BaseModel):
    """Una linea ya guardada, con lo que decidio el comprador si ya la reviso."""

    id: int
    producto: str
    descripcion: str | None = None
    precio_lista: float | None = None
    cantidad_pedida: float
    cantidad_aprobada: float | None = None
    comentario: str | None = None
    # Solo en el detalle del comprador: el contexto para decidir (mismo que la
    # pantalla de pegar lista). En la vista del vendedor va en None.
    analisis: LineaRequerimiento | None = None


class RequerimientoOut(BaseModel):
    """Un requerimiento en la bandeja o en el detalle."""

    id: int
    sucursal_id: str
    nombre_sucursal: str | None = None
    creado_por: str
    creado_por_nombre: str | None = None
    creado_en: datetime
    estado: str
    nota: str | None = None
    revisado_por: str | None = None
    revisado_en: datetime | None = None
    nota_comprador: str | None = None
    n_lineas: int = 0
    # Valorizado a la lista de precios que vio el vendedor.
    total_estimado: float | None = None
    lineas: list[LineaGuardada] = Field(default_factory=list)


class RequerimientosPage(BaseModel):
    items: list[RequerimientoOut] = Field(default_factory=list)
    total: int = 0
    # Cuantos hay sin abrir. Es el numero del badge de la bandeja.
    sin_revisar: int = 0


class CantidadAprobada(BaseModel):
    linea_id: int
    cantidad: float | None = None


class RequerimientoUpdate(BaseModel):
    """Lo que puede cambiar el comprador al revisar."""

    estado: str | None = None
    nota_comprador: str | None = None
    cantidades: list[CantidadAprobada] = Field(default_factory=list)
