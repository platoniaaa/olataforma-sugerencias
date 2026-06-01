"""Carga (única) del catálogo maestro de productos desde CSV.

Lee el CSV exportado del ERP (formato chileno: `;` como separador, `,` como decimal),
dedupea por código de producto sumando el Stock entre todas las bodegas, y carga
el resultado en la tabla producto_catalogo de Supabase.

Uso:
    python -m src.jobs.cargar_catalogo "C:\\ruta\\al\\archivo.csv"

Si no se pasa ruta, busca el archivo por defecto en la raíz del repo.
"""
from __future__ import annotations

import csv
import sys
import time
from pathlib import Path
from typing import Any

from sqlalchemy import delete, insert

from ..config import get_settings
from ..db import SessionLocal, create_all
from ..models import ProductoCatalogo

DEFAULT_PATH = (
    Path(__file__).resolve().parents[4] / "lista productos.csv"
)


# Columnas del CSV que queremos. Mapeo: header_csv -> campo_modelo.
COLS_TEXTO = {
    "Producto": "producto",
    "Glosa": "glosa",
    "Familia": "familia",
    "SubFamilia": "subfamilia",
    "Procedencia": "procedencia",
    "Tipo Repuesto": "tipo_repuesto",
    "Categoria": "categoria",
    "Sub Categoria": "sub_categoria",
    "TipoProducto": "tipo_producto",
    "Clasificacion Stock": "clasificacion_stock",
    "Sub-Modelo": "sub_modelo",
    "Cilindrada": "cilindrada",
    "Combustible": "combustible",
    "Año": "anio",
    "Unidad": "unidad",
    "Reemplazo": "reemplazo",
}
COLS_NUMERICAS = {
    "Costo": "costo",
    "Precio": "precio",
    "Stock": "stock_total",  # se ACUMULA por producto
    "StockMinimo": "stock_minimo",  # primera lectura no vacía
    "StockMaximo": "stock_maximo",
}


def _to_float(s: Any) -> float | None:
    if s is None:
        return None
    txt = str(s).strip()
    if not txt:
        return None
    # Formato chileno: "1.234,56" -> 1234.56 ; "0,00000000" -> 0.0
    # Si tiene ambos, el . es miles. Si solo coma, la , es decimal.
    if "," in txt and "." in txt:
        txt = txt.replace(".", "").replace(",", ".")
    elif "," in txt:
        txt = txt.replace(",", ".")
    try:
        return float(txt)
    except ValueError:
        return None


def _norm_str(s: Any) -> str | None:
    if s is None:
        return None
    t = str(s).strip()
    return t or None


def cargar(path: Path) -> dict:
    """Lee el CSV, agrega por producto y persiste en la base."""
    if not path.exists():
        raise FileNotFoundError(f"No encuentro el archivo: {path}")

    print(f"Leyendo {path} ({path.stat().st_size / 1024 / 1024:.1f} MB)…")
    t0 = time.time()

    # Acumulador: producto -> dict de campos
    acum: dict[str, dict[str, Any]] = {}
    saltadas = 0
    leidas = 0

    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            leidas += 1
            producto = _norm_str(row.get("Producto"))
            if not producto:
                saltadas += 1
                continue

            d = acum.get(producto)
            if d is None:
                d = {"producto": producto, "stock_total": 0.0}
                # Cargar campos de texto (primera lectura no vacía)
                for csv_h, field in COLS_TEXTO.items():
                    if field == "producto":
                        continue
                    val = _norm_str(row.get(csv_h))
                    if val:
                        d[field] = val
                # Cargar campos numéricos (excepto stock_total)
                for csv_h, field in COLS_NUMERICAS.items():
                    if field == "stock_total":
                        continue
                    val = _to_float(row.get(csv_h))
                    if val is not None:
                        d[field] = val
                acum[producto] = d
            else:
                # Completar campos vacíos con el valor del row actual
                for csv_h, field in COLS_TEXTO.items():
                    if field == "producto" or d.get(field):
                        continue
                    val = _norm_str(row.get(csv_h))
                    if val:
                        d[field] = val
                for csv_h, field in COLS_NUMERICAS.items():
                    if field == "stock_total" or d.get(field) is not None:
                        continue
                    val = _to_float(row.get(csv_h))
                    if val is not None:
                        d[field] = val

            # Sumar stock siempre
            stock_row = _to_float(row.get("Stock"))
            if stock_row is not None:
                d["stock_total"] = d.get("stock_total", 0.0) + stock_row

            if leidas % 50000 == 0:
                print(
                    f"  {leidas:,} filas leídas, {len(acum):,} productos únicos…"
                    .replace(",", ".")
                )

    print(
        f"Parseado en {time.time() - t0:.1f}s — "
        f"{leidas:,} filas leídas, {len(acum):,} productos únicos, {saltadas} saltadas"
        .replace(",", ".")
    )

    # Persistir
    settings = get_settings()
    tenant = settings.default_tenant_id
    create_all()
    db = SessionLocal()
    try:
        print("Vaciando tabla producto_catalogo (carga snapshot)…")
        db.execute(delete(ProductoCatalogo).where(ProductoCatalogo.tenant_id == tenant))
        db.commit()

        # SQLAlchemy bulk insert requiere que TODOS los dicts tengan las mismas llaves.
        # Normalizamos: cada registro lleva siempre todas las columnas (con None si falta).
        todas_cols = set(COLS_TEXTO.values()) | set(COLS_NUMERICAS.values())
        registros: list[dict[str, Any]] = []
        for d in acum.values():
            r = {"tenant_id": tenant}
            for col in todas_cols:
                r[col] = d.get(col)
            registros.append(r)
        total = len(registros)
        chunk = 1000  # mas grande -> menos round-trips a Supabase
        print(f"Insertando {total:,} productos en chunks de {chunk}…".replace(",", ""), flush=True)
        t1 = time.time()
        for i in range(0, total, chunk):
            lote = registros[i : i + chunk]
            db.execute(insert(ProductoCatalogo).values(lote))
            db.commit()  # commit por chunk -> progreso visible y reanudable si falla
            if i % 10000 == 0 or i + chunk >= total:
                pct = 100 * (i + len(lote)) / total
                elapsed = time.time() - t1
                print(
                    f"  {i + len(lote)}/{total} ({pct:.0f}%) "
                    f"en {elapsed:.0f}s",
                    flush=True,
                )
        print(f"OK en {time.time() - t1:.0f}s. Total productos cargados: {total}", flush=True)
    finally:
        db.close()

    return {"productos": len(acum), "filas_csv": leidas}


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PATH
    try:
        r = cargar(path)
        print(f"\nLISTO: {r}")
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
