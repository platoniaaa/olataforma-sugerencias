"""Consulta del historico de ventas (desde 2018)."""
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..services import ventas_historicas_service as svc

router = APIRouter(prefix="/api/ventas-historicas", tags=["ventas historicas"])


def _filtros(
    producto: str | None = Query(None, description="Codigo o parte del codigo"),
    sucursal: str | None = Query(None),
    periodo_desde: str | None = Query(None, description="YYYYMM"),
    periodo_hasta: str | None = Query(None, description="YYYYMM"),
    incluir_internos: bool = Query(
        False, description="Incluir conceptos internos (D&P, insumos, incentivos)"
    ),
) -> dict:
    return {
        "producto": producto, "sucursal": sucursal,
        "periodo_desde": periodo_desde, "periodo_hasta": periodo_hasta,
        "incluir_internos": incluir_internos,
    }


@router.get("/meta")
def meta(db: Session = Depends(get_db)):
    """Que hay cargado: rango de periodos, filas y sucursales."""
    return svc.meta(db)


@router.get("")
def consultar(
    f: dict = Depends(_filtros),
    limit: int = Query(500, ge=1, le=svc.LIMITE_FILAS),
    db: Session = Depends(get_db),
):
    return {
        "detalle": svc.detalle(db, f, limit=limit),
        "por_periodo": svc.por_periodo(db, f),
        "por_sucursal": svc.por_sucursal(db, f),
    }


@router.get("/export-csv")
def export_csv(f: dict = Depends(_filtros), db: Session = Depends(get_db)):
    """Descarga lo consultado en CSV (Excel lo abre directo)."""
    import csv
    import io

    datos = svc.detalle(db, f, limit=svc.LIMITE_FILAS)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Periodo", "Producto", "Sucursal", "Cantidad", "Neto CLP", "Lineas"])
    for it in datos["items"]:
        w.writerow([
            it["periodo"], it["producto"], it["sucursal"] or "",
            it["cantidad"], it["neto"] or "", it["n_lineas"] or "",
        ])
    contenido = buf.getvalue().encode("utf-8-sig")  # BOM: Excel respeta las tildes
    return StreamingResponse(
        iter([contenido]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="ventas_historicas.csv"'},
    )
