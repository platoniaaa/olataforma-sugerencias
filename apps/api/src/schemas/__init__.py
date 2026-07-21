"""Schemas Pydantic (contratos de la API)."""
from .sugerido import (
    SugeridoRow,
    SugeridoPage,
    SugeridoKpis,
    SugeridoFiltros,
    ColumnaFiltro,
    ExportRequest,
    AgrupadoRow,
    VentaMes,
    VentasResponse,
)
from .sugerencia_manual import (
    SugerenciaManualOut,
    SugerenciaManualCreate,
    SugerenciaManualUpdate,
    SugerenciaManualMasiva,
    SugerenciaManualMasivaResultado,
    RecurrenteCreate,
    RecurrenteOut,
)
from .catalogo import ProductoOut, ProductoPage, SucursalOut
from .producto_catalogo import (
    CatalogoRow,
    CatalogoPage,
    CatalogoFiltros,
    CatalogoDetalle,
    StockSucursalRow,
)
from .compras import (
    LineaCarro,
    CarroProveedor,
    CarrosResponse,
    ExportCarrosRequest,
)
from .post_venta import PostVentaMetaOut, PostVentaFiltros
from .auditoria import (
    AuditoriaLogOut,
    AuditoriaPage,
    NotificacionOut,
    NotificacionesResponse,
    MarcarLeidasRequest,
)
from .documento import DocumentoOut, DocumentoCreate, DocumentoUpdate

__all__ = [
    "SugeridoRow",
    "SugeridoPage",
    "SugeridoKpis",
    "SugeridoFiltros",
    "ColumnaFiltro",
    "ExportRequest",
    "AgrupadoRow",
    "VentaMes",
    "VentasResponse",
    "SugerenciaManualOut",
    "SugerenciaManualCreate",
    "SugerenciaManualUpdate",
    "SugerenciaManualMasiva",
    "SugerenciaManualMasivaResultado",
    "RecurrenteCreate",
    "RecurrenteOut",
    "ProductoOut",
    "ProductoPage",
    "SucursalOut",
    "CatalogoRow",
    "CatalogoPage",
    "CatalogoFiltros",
    "CatalogoDetalle",
    "StockSucursalRow",
    "LineaCarro",
    "CarroProveedor",
    "CarrosResponse",
    "ExportCarrosRequest",
    "PostVentaMetaOut",
    "PostVentaFiltros",
    "AuditoriaLogOut",
    "AuditoriaPage",
    "NotificacionOut",
    "NotificacionesResponse",
    "MarcarLeidasRequest",
    "DocumentoOut",
    "DocumentoCreate",
    "DocumentoUpdate",
]
