"""Carga la lista InStock: repuestos de pauta que nunca pueden faltar en bodega.

Lee `src/data/pautas_instock.csv` (lo genera `scripts/extraer_instock_pautas.py`
desde las pautas del fabricante) y lo cruza contra el maestro de productos para
resolver el código real de cada part number.

Por qué el cruce se hace acá y no en el script: la pauta trae el part number del
fabricante ("2630035505") y la plataforma trabaja con el código del ERP, que
lleva el rubro adelante ("95 2630035505"). Un mismo part number puede existir
bajo varios rubros (pasa con FORD: "19 BE8Z6731AB" y "61 BE8Z6731AB"): son el
mismo repuesto físico y se marcan todos. Resolver contra la base y no contra un
CSV congelado deja que una recarga del catálogo agregue códigos nuevos sin tener
que volver a abrir los Excel de las pautas.

Uso:
    python -m src.jobs.cargar_instock [ruta_csv]
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

from sqlalchemy import delete, distinct, insert, select

from ..config import get_settings
from ..db import SessionLocal, create_all
from ..models import ProductoCatalogo, RepuestoInstock, Sugerido
from ..services.instock_service import MINIMO_DEFECTO

DEFAULT_PATH = Path(__file__).resolve().parents[1] / "data" / "pautas_instock.csv"


def _norm(texto: str | None) -> str:
    """Código comparable: solo letras y números, en mayúsculas."""
    return re.sub(r"[^A-Z0-9]", "", (texto or "").upper())


def _sin_rubro(producto: str) -> str | None:
    """"95 2630035505" -> "2630035505" normalizado. None si no tiene rubro."""
    m = re.match(r"^\d+\s+(.+)$", producto.strip())
    return _norm(m.group(1)) if m else None


def _indice_de_codigos(db) -> dict[str, set[str]]:
    """{part_number normalizado: {códigos de producto}} de todo el maestro.

    Mira el catálogo y también el sugerido: si el BI trae un código que el
    maestro todavía no tiene, igual se puede marcar (mismo criterio tolerante que
    `producto_existe`).
    """
    indice: dict[str, set[str]] = {}

    def _agregar(producto: str | None) -> None:
        if not producto:
            return
        codigo = _sin_rubro(producto)
        if codigo:
            indice.setdefault(codigo, set()).add(producto.strip())

    for (producto,) in db.execute(select(ProductoCatalogo.producto)).all():
        _agregar(producto)
    for (producto,) in db.execute(select(distinct(Sugerido.producto))).all():
        _agregar(producto)
    return indice


def _leer_csv(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"No encuentro la lista de pautas: {path}")
    with open(path, encoding="utf-8", newline="") as fh:
        return [f for f in csv.DictReader(fh, delimiter=";") if (f.get("part_number") or "").strip()]


def cargar(path: Path = DEFAULT_PATH) -> dict:
    settings = get_settings()
    tenant = settings.default_tenant_id
    pautas = _leer_csv(path)
    print(f"Pautas leídas: {len(pautas)} part numbers ({path.name})")

    create_all()
    db = SessionLocal()
    try:
        indice = _indice_de_codigos(db)
        print(f"Códigos en el maestro: {len(indice)} part numbers distintos")

        registros: dict[str, dict] = {}
        sin_codigo: list[dict] = []
        for fila in pautas:
            part = (fila.get("part_number") or "").strip()
            codigos = indice.get(_norm(part))
            if not codigos:
                sin_codigo.append(fila)
                continue
            for producto in codigos:
                # Un producto puede venir de dos pautas (mismo repuesto en dos
                # modelos): se queda con la primera y se acumulan los modelos.
                previo = registros.get(producto)
                if previo:
                    modelos = {m.strip() for m in (previo["modelos"] or "").split(",") if m.strip()}
                    modelos |= {m.strip() for m in (fila.get("modelos") or "").split(",") if m.strip()}
                    previo["modelos"] = ", ".join(sorted(modelos))
                    continue
                registros[producto] = {
                    "tenant_id": tenant,
                    "producto": producto,
                    "part_number": part,
                    "marca": (fila.get("marca") or "").strip() or None,
                    "modelos": (fila.get("modelos") or "").strip() or None,
                    "operacion": (fila.get("operacion") or "").strip() or None,
                    "detalle": (fila.get("detalle") or "").strip() or None,
                    "minimo": MINIMO_DEFECTO,
                    "activo": True,
                }

        db.execute(delete(RepuestoInstock).where(RepuestoInstock.tenant_id == tenant))
        if registros:
            db.execute(insert(RepuestoInstock).values(list(registros.values())))
        db.commit()

        print(f"Productos marcados InStock: {len(registros)}")
        if sin_codigo:
            print(f"\nSin código en el maestro ({len(sin_codigo)}), no se marcan:")
            for fila in sin_codigo:
                print(f"  - {fila.get('marca')} {fila.get('part_number')} · "
                      f"{fila.get('operacion')} · {fila.get('modelos')}")
        return {"productos": len(registros), "sin_codigo": len(sin_codigo)}
    finally:
        db.close()


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
