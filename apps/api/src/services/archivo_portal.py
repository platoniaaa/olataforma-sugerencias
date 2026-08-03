"""Archivo para cargar el pedido en el portal del proveedor.

Cada portal quiere lo suyo y el comprador lo armaba a mano en un Excel:

    FORD           sku,cantidad   empezando en A1
    GILDEMEISTER   sku,cantidad   empezando en A2 (la primera fila va vacia)

Poka-yoke: el comprador no elige formato ni fila de inicio, no convierte codigos
y no puede mezclar proveedores. Pide "el archivo para Ford" y sale el archivo
para Ford.

El SKU no es el codigo de Curifor
---------------------------------
Curifor usa "<rubro> <codigo>" ("19 SZ6Z3B437B"); Ford pide su formato con
barras ("SZ6Z/3B437/B/"), que separa prefijo/basico/sufijos y NO se puede derivar
con una regla: hay que mirarlo en la lista de Ford. El motor publica esa
equivalencia (`sku_proveedor`) desde la misma lista de precios que ya lee.

Gildemeister si es regla: su codigo es el de Curifor sin el rubro.
"""
from __future__ import annotations

import csv
import io
import re
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import SkuProveedor

FORD = "FORD"
GILDEMEISTER = "GILDEMEISTER"

# Fila en la que arranca el detalle. Ford lee desde la primera; Gildemeister
# espera la primera vacia y empieza en la segunda.
FILA_INICIAL = {FORD: 1, GILDEMEISTER: 2}


def clave_producto(codigo: str | None) -> str | None:
    """Codigo comparable: sin el rubro de Curifor y solo alfanumerico.

    Misma normalizacion que usa el motor para cruzar las listas de precios, para
    que los dos lados hablen del mismo codigo.
    """
    if not codigo:
        return None
    s = str(codigo).strip()
    m = re.match(r"^\d+\s+(.*)$", s)
    if m:
        s = m.group(1)
    limpio = re.sub(r"[^A-Za-z0-9]", "", s).upper()
    return limpio or None


def sku_de(db: Session, productos: list[str], proveedor: str) -> dict[str, str | None]:
    """Codigo Curifor -> SKU del portal. None cuando no hay equivalencia."""
    if not productos:
        return {}
    claves = {p: clave_producto(p) for p in productos}
    if proveedor == GILDEMEISTER:
        # El portal de Gildemeister usa el codigo del fabricante tal cual.
        return {p: c for p, c in claves.items()}
    mapa: dict[str, str] = {}
    validas = {c for c in claves.values() if c}
    if validas:
        try:
            filas = db.execute(
                select(SkuProveedor.clave, SkuProveedor.sku).where(
                    SkuProveedor.proveedor == proveedor, SkuProveedor.clave.in_(validas)
                )
            ).all()
            mapa = {c: s for c, s in filas}
        except Exception:  # noqa: BLE001 - tabla ausente en un deploy nuevo
            db.rollback()
    return {p: (mapa.get(c) if c else None) for p, c in claves.items()}


def generar_csv(db: Session, lineas: list[dict], proveedor: str) -> tuple[bytes, list[dict]]:
    """CSV listo para el portal. Devuelve (contenido, lineas_descartadas).

    Se descarta lo que el portal rechazaria igual: sin SKU o sin cantidad. Se
    devuelven aparte para poder decirle al comprador que quedo fuera y por que,
    en vez de que lo descubra cuando el portal le tire un error.
    """
    proveedor = (proveedor or "").strip().upper()
    if proveedor not in FILA_INICIAL:
        raise ValueError(
            f"Proveedor no soportado: {proveedor!r}. Validos: {sorted(FILA_INICIAL)}"
        )
    productos = [str(l.get("producto") or "") for l in lineas]
    skus = sku_de(db, productos, proveedor)

    buffer = io.StringIO(newline="")
    w = csv.writer(buffer, lineterminator="\r\n")
    for _ in range(FILA_INICIAL[proveedor] - 1):
        w.writerow([])  # Gildemeister arranca en A2

    descartadas: list[dict] = []
    for linea in lineas:
        prod = str(linea.get("producto") or "")
        cantidad = linea.get("cantidad")
        sku = skus.get(prod)
        if not sku:
            descartadas.append({**linea, "motivo": f"sin codigo de {proveedor.title()}"})
            continue
        try:
            n = int(round(float(cantidad)))
        except (TypeError, ValueError):
            n = 0
        if n <= 0:
            descartadas.append({**linea, "motivo": "sin cantidad"})
            continue
        w.writerow([sku, n])
    # El portal de Ford lee latin-1; UTF-8 con BOM le mete basura al primer SKU.
    return buffer.getvalue().encode("latin-1", errors="replace"), descartadas


def nombre_archivo(proveedor: str, sucursal_id: str | None = None) -> str:
    partes = ["pedido", proveedor.lower()]
    if sucursal_id:
        partes.append(re.sub(r"[^A-Za-z0-9]+", "-", sucursal_id).strip("-").lower())
    partes.append(f"{date.today():%Y%m%d}")
    return "_".join(p for p in partes if p) + ".csv"
