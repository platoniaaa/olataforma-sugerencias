"""Consulta y exportación de la Planilla Post Venta cargada en la base."""
from __future__ import annotations

import io
import json
import unicodedata
from datetime import date, datetime

from openpyxl import Workbook
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import PostVentaFila, PostVentaMeta

settings = get_settings()

# Límite de Excel: 1.048.576 filas por hoja (menos la cabecera).
EXCEL_MAX_FILAS = 1_048_575

# Columnas (por nombre normalizado) que conviene escribir como número.
_NUM_COLS = {"items", "cantidad", "neto", "total", "costo_neto", "total_neta"}


def _norm(s: str) -> str:
    s = (s or "").strip().lower()
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    for ch in (" ", "-", "/", ".", "°", "º"):
        s = s.replace(ch, "_")
    while "__" in s:
        s = s.replace("__", "_")
    return s.strip("_")


def _parse_fecha_celda(s) -> date | None:
    """Parsea el valor de la columna 'Fecha' del Post Venta. Viene como string
    en formato US: 'MM/DD/YYYY HH:MM:SS' (lo emite el extractor del Power BI).
    Devuelve None si no se puede parsear (no rompe la fila)."""
    if not s:
        return None
    txt = str(s).strip()
    if not txt:
        return None
    # Cortar la parte de hora si existe.
    txt = txt.split(" ")[0]
    for fmt in ("%m/%d/%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(txt, fmt).date()
        except ValueError:
            continue
    return None


def _parse_iso(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return datetime.strptime(s.strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def _periodos_de_rango(d_desde: date | None, d_hasta: date | None) -> tuple[str | None, str | None]:
    """Deriva (periodo_desde, periodo_hasta) en YYYYMM a partir de fechas YYYY-MM-DD.
    Sirve para acotar la consulta SQL antes de filtrar por dia en Python."""
    pd = f"{d_desde.year}{d_desde.month:02d}" if d_desde else None
    ph = f"{d_hasta.year}{d_hasta.month:02d}" if d_hasta else None
    return pd, ph


def _resolver_filtros(
    periodo_desde, periodo_hasta, fecha_desde, fecha_hasta
) -> tuple[str | None, str | None, date | None, date | None]:
    """Combina filtros de mes + dia. Si llegan fechas, derivan los periodos para
    acotar el SQL; los periodos explicitos solo se usan si no hay fechas."""
    fd = _parse_iso(fecha_desde) if isinstance(fecha_desde, str) else fecha_desde
    fh = _parse_iso(fecha_hasta) if isinstance(fecha_hasta, str) else fecha_hasta
    pd_from_fechas, ph_from_fechas = _periodos_de_rango(fd, fh)
    pd_final = pd_from_fechas or periodo_desde
    ph_final = ph_from_fechas or periodo_hasta
    return pd_final, ph_final, fd, fh


def meta(db: Session) -> dict:
    m = db.get(PostVentaMeta, settings.default_tenant_id)
    if not m:
        return {"columnas": [], "filas": 0, "periodos": [], "sucursales": [], "actualizado_en": None}
    return {
        "columnas": json.loads(m.columnas or "[]"),
        "filas": m.filas,
        "periodos": json.loads(m.periodos or "[]"),
        "sucursales": json.loads(m.sucursales or "[]"),
        "actualizado_en": m.actualizado_en,
    }


def _stmt_filtrado(periodo_desde, periodo_hasta, sucursal):
    stmt = select(PostVentaFila).where(PostVentaFila.tenant_id == settings.default_tenant_id)
    if periodo_desde:
        stmt = stmt.where(PostVentaFila.periodo >= periodo_desde)
    if periodo_hasta:
        stmt = stmt.where(PostVentaFila.periodo <= periodo_hasta)
    if sucursal:
        stmt = stmt.where(PostVentaFila.sucursal == sucursal)
    return stmt


def _idx_fecha(columnas: list[str]) -> int | None:
    for i, c in enumerate(columnas):
        if _norm(c) == "fecha":
            return i
    return None


def _pasa_filtro_dia(valores: list, i_fecha: int | None, fd: date | None, fh: date | None) -> bool:
    """Aplica el filtro de dia exacto a una fila. Si no se puede parsear la fecha,
    deja pasar la fila (mejor mostrar de mas que ocultar info)."""
    if fd is None and fh is None:
        return True
    if i_fecha is None or i_fecha >= len(valores):
        return True
    d = _parse_fecha_celda(valores[i_fecha])
    if d is None:
        return True
    if fd and d < fd:
        return False
    if fh and d > fh:
        return False
    return True


def contar(db: Session, periodo_desde, periodo_hasta, sucursal,
           fecha_desde=None, fecha_hasta=None) -> int:
    pd_eff, ph_eff, fd, fh = _resolver_filtros(periodo_desde, periodo_hasta, fecha_desde, fecha_hasta)
    stmt = _stmt_filtrado(pd_eff, ph_eff, sucursal)
    if fd is None and fh is None:
        # Sin filtro de dia: contamos en SQL (rapido).
        return db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    # Con filtro de dia: tenemos que parsear el JSON fila por fila.
    m = db.get(PostVentaMeta, settings.default_tenant_id)
    columnas = json.loads((m.columnas if m else "[]") or "[]")
    i_fecha = _idx_fecha(columnas)
    n = 0
    for fila in db.scalars(stmt).yield_per(2000):
        try:
            valores = json.loads(fila.datos)
        except Exception:
            continue
        if _pasa_filtro_dia(valores, i_fecha, fd, fh):
            n += 1
    return n


def generar_csv_stream(db: Session, columnas, periodo_desde, periodo_hasta, sucursal,
                       fecha_desde=None, fecha_hasta=None):
    """Generador que va emitiendo el CSV fila por fila (streaming real)."""
    if not columnas:
        m = db.get(PostVentaMeta, settings.default_tenant_id)
        columnas = json.loads((m.columnas if m else "[]") or "[]")

    i_fecha = _idx_fecha(columnas)
    pd_eff, ph_eff, fd, fh = _resolver_filtros(periodo_desde, periodo_hasta, fecha_desde, fecha_hasta)

    # BOM UTF-8 para que Excel reconozca acentos en Windows.
    yield "﻿".encode("utf-8")

    def _esc(v) -> str:
        if v is None:
            return ""
        s = str(v)
        if any(ch in s for ch in [",", '"', "\n", "\r"]):
            return '"' + s.replace('"', '""') + '"'
        return s

    yield (",".join(_esc(c) for c in columnas) + "\n").encode("utf-8")

    stmt = _stmt_filtrado(pd_eff, ph_eff, sucursal).order_by(PostVentaFila.id)
    for fila in db.scalars(stmt).yield_per(2000):
        try:
            valores = json.loads(fila.datos)
        except Exception:
            continue
        if not _pasa_filtro_dia(valores, i_fecha, fd, fh):
            continue
        if len(valores) < len(columnas):
            valores = valores + [""] * (len(columnas) - len(valores))
        yield (",".join(_esc(v) for v in valores[: len(columnas)]) + "\n").encode("utf-8")


def generar_excel(db: Session, columnas, periodo_desde, periodo_hasta, sucursal,
                  fecha_desde=None, fecha_hasta=None) -> bytes:
    """Excel de la Planilla Post Venta filtrada. write_only para soportar muchas filas."""
    if not columnas:
        m = db.get(PostVentaMeta, settings.default_tenant_id)
        columnas = json.loads((m.columnas if m else "[]") or "[]")

    num_idx = {i for i, c in enumerate(columnas) if _norm(c) in _NUM_COLS}
    i_fecha = _idx_fecha(columnas)
    pd_eff, ph_eff, fd, fh = _resolver_filtros(periodo_desde, periodo_hasta, fecha_desde, fecha_hasta)

    wb = Workbook(write_only=True)
    ws = wb.create_sheet("Post Venta")
    ws.append(columnas)

    stmt = _stmt_filtrado(pd_eff, ph_eff, sucursal).order_by(PostVentaFila.id)
    for fila in db.scalars(stmt).yield_per(2000):
        valores = json.loads(fila.datos)
        if not _pasa_filtro_dia(valores, i_fecha, fd, fh):
            continue
        if num_idx:
            for i in num_idx:
                if i < len(valores) and valores[i] not in ("", None):
                    try:
                        valores[i] = float(str(valores[i]).replace(",", "."))
                    except (ValueError, TypeError):
                        pass
        ws.append(valores)

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
