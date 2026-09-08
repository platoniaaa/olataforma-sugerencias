"""Carga la clasificación de bodegas (REAL / VIRT / ELIM) a la plataforma.

El ERP mezcla bodegas físicas con bodegas de proceso —dañados, devolución,
scrap, PE por regularizar, importación—. La lista de precios solo cuenta el
stock de las **REAL**: lo que está en las otras existe pero no se puede vender,
y ponerle precio es decir que hay algo que no hay.

El Excel lo mantiene Abastecimiento:

    Bodega              | TIPO BOD
    BODEGA SCRAP        | VIRT
    LINDEROS            | REAL
    CASA MATRIZ         | ELIM

Uso:

    python bodegas_tipo.py "C:\\ruta\\1 Tipo bodega.xlsx" --env "ruta\\al\\.env"
    python bodegas_tipo.py archivo.xlsx --api http://localhost:8000 --email x --password y
    python bodegas_tipo.py archivo.xlsx --env ... --simular   # no escribe nada

Antes de subir compara contra el stock que la plataforma tiene hoy y avisa de
las bodegas que aparecen con stock y no están en el Excel: esas siguen contando
(se excluye solo lo marcado), pero conviene saber que existen.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
import urllib.request

from openpyxl import load_workbook

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from push_precios import CTX  # noqa: E402  (el arreglo de TLS de la red de Curifor)

TIPOS = {"REAL", "VIRT", "ELIM"}


def clave(nombre) -> str:
    """Igual que `precios_service.clave_bodega`: el nombre sin espacios ni signos.

    "CHILLAN 2" y "CHILLAN2" son la misma bodega; comparando el texto crudo
    quedaban 1,4 millones de unidades sin clasificar.
    """
    txt = str(nombre if nombre is not None else "").upper()
    txt = "".join(c for c in unicodedata.normalize("NFKD", txt) if not unicodedata.combining(c))
    return re.sub(r"[^A-Z0-9]", "", txt)


def leer_excel(ruta: str) -> list[dict]:
    wb = load_workbook(ruta, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    filas, vistas = [], set()
    for i, fila in enumerate(ws.iter_rows(values_only=True)):
        if i == 0 or not fila or len(fila) < 2:
            continue
        bodega, tipo = fila[0], (str(fila[1] or "")).strip().upper()
        if tipo not in TIPOS:
            continue
        k = clave(bodega)
        if k in vistas:
            continue
        vistas.add(k)
        filas.append({"bodega": str(bodega or "").strip(), "tipo": tipo})
    return filas


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("excel")
    ap.add_argument("--env")
    ap.add_argument("--api")
    ap.add_argument("--email")
    ap.add_argument("--password")
    ap.add_argument("--simular", action="store_true", help="no escribe nada")
    a = ap.parse_args()

    base, email, password = a.api, a.email, a.password
    if a.env:
        with open(a.env, encoding="utf-8") as f:
            for linea in f:
                if "=" in linea and not linea.strip().startswith("#"):
                    k, _, v = linea.partition("=")
                    v = v.strip().strip('"')
                    if k.strip() == "PLATAFORMA_API_URL":
                        base = base or v
                    elif k.strip() == "PLATAFORMA_EMAIL":
                        email = email or v
                    elif k.strip() == "PLATAFORMA_PASSWORD":
                        password = password or v
    if not (base and email and password):
        print("Faltan --api/--email/--password o un --env que los traiga", file=sys.stderr)
        return 1
    base = base.rstrip("/")

    filas = leer_excel(a.excel)
    por_tipo: dict[str, int] = {}
    for f in filas:
        por_tipo[f["tipo"]] = por_tipo.get(f["tipo"], 0) + 1
    print(f"Excel: {len(filas)} bodegas  {por_tipo}")
    if not filas:
        print("El Excel no trajo ninguna bodega con tipo REAL/VIRT/ELIM", file=sys.stderr)
        return 1

    def pedir(ruta, metodo="GET", cuerpo=None, token=None):
        datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
        req = urllib.request.Request(base + ruta, data=datos, method=metodo)
        if token:
            req.add_header("Authorization", "Bearer " + token)
        if datos:
            req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=300, context=CTX) as r:
            return json.load(r)

    token = pedir("/api/auth/login", "POST", {"email": email, "password": password})["token"]

    # Que bodegas ve la plataforma hoy con stock, para avisar de las que faltan.
    conocidas = {clave(f["bodega"]) for f in filas}
    try:
        actuales = pedir("/api/precios/bodegas", token=token)
        con_stock = {clave(b["bodega"]) for b in actuales if b.get("con_stock")}
        faltan = con_stock - conocidas
        if faltan:
            print(f"AVISO: {len(faltan)} bodega(s) con stock no estan en el Excel. "
                  "Siguen contando (se excluye solo lo marcado), pero conviene clasificarlas.")
    except Exception as e:  # noqa: BLE001 - es un aviso, no puede frenar la carga
        print(f"(no se pudo comparar contra el stock: {e})")

    if a.simular:
        print("--simular: no se escribio nada.")
        return 0

    r = pedir("/api/admin/precios/bodegas-tipo", "POST", {"filas": filas}, token)
    print(f"Cargadas: {r}")
    print("Corre un recalculo para que el stock de la lista deje de contar las no reales.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
