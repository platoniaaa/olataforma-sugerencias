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

from sqlalchemy import delete, distinct, func, insert, select

from ..config import get_settings
from ..db import SessionLocal, create_all
from ..models import ProductoCatalogo, RepuestoInstock, StockUnificado, Sugerido
from ..services import reemplazo_service
from ..services.instock_service import MINIMO_DEFECTO

DEFAULT_PATH = Path(__file__).resolve().parents[1] / "data" / "pautas_instock.csv"


def _norm(texto: str | None) -> str:
    """Código comparable: solo letras y números, en mayúsculas."""
    return re.sub(r"[^A-Z0-9]", "", (texto or "").upper())


def _sin_rubro(producto: str) -> str | None:
    """"95 2630035505" -> "2630035505" normalizado. None si no tiene rubro."""
    m = re.match(r"^\d+\s+(.+)$", producto.strip())
    return _norm(m.group(1)) if m else None


def elegir_codigo(
    codigos: set[str] | list[str],
    en_sugerido: set[str],
    stock: dict[str, float],
) -> str:
    """UN solo codigo de producto por part number de la pauta.

    Un mismo part number puede existir bajo varios rubros del ERP ("28 2151323001"
    y "95 2151323001" son la misma golilla). Marcar los dos era un error caro: el
    minimo se aplica POR CODIGO, asi que la plataforma pediria 2 unidades de cada
    rubro -4 del mismo repuesto fisico por sucursal, 16 entre las cuatro- y encima
    la mitad sobre un rubro que Curifor no usa (rubro 28: cero stock; rubro 95:
    301 unidades).

    El criterio, en orden:

    1. **El que esta en el sugerido.** Es el codigo con el que la plataforma
       representa esa pieza, y ademas el maestro de su grupo de reemplazos (el
       motor ya consolida ahi la venta y el stock de los codigos equivalentes).
       Colgar el minimo de otro codigo seria pedirlo aparte del que se mira.
    2. **El que Curifor stockea**, y de esos el de mayor stock: si nadie esta en el
       sugerido, al menos que sea un codigo vivo en bodega.
    3. **Orden alfabetico**, para que dos corridas den lo mismo.
    """
    return sorted(
        codigos,
        key=lambda c: (0 if c in en_sugerido else 1, -stock.get(c, 0.0), c),
    )[0]


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


def vigentes_de(db, codigos: set[str]) -> dict[str, str]:
    """{codigo dado de baja: su vigente} para los que el motor SI agrupo.

    La pauta del fabricante trae part numbers que FORD despues descontinuo, y el
    indice de arriba no ayuda con eso: busca el MISMO part number bajo otro
    rubro, y el vigente es un part number distinto ("BR3Z8620S" -> "RB5Z8620D").
    Sin este paso la fila InStock queda colgada del codigo muerto, que es lo que
    se veia en pantalla: el sugerido pedia `19 BR3Z8620S` teniendo el vigente.

    Solo se siguen los reemplazos que el motor efectivamente agrupo
    (`agrupado`). Si no agrupo, el stock de los dos codigos se cuenta por
    separado y colgar el minimo del vigente pediria de mas: se estaria exigiendo
    el minimo completo del vigente sin descontar lo que hay del viejo.
    """
    if not codigos:
        return {}
    salida: dict[str, str] = {}
    for producto, f in reemplazo_service.por_producto(db, codigos).items():
        vigente = f.get("reemplazado_por")
        if vigente and vigente != producto and f.get("agrupado"):
            salida[producto] = vigente
    return salida


def _leer_csv(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"No encuentro la lista de pautas: {path}")
    with open(path, encoding="utf-8", newline="") as fh:
        return [f for f in csv.DictReader(fh, delimiter=";") if (f.get("part_number") or "").strip()]


def cargar_en(db, pautas: list[dict]) -> dict:
    """Resuelve las pautas contra ESTA base y reemplaza la lista InStock.

    Recibe la sesion en vez de abrirla: asi la misma logica sirve para el job de
    linea de comandos (que se conecta directo a la base) y para el endpoint de
    administracion, que corre dentro de la API. Sin esto, cargar la lista en la
    nube exigia tener la cadena de conexion a Supabase a mano, y por eso la
    plataforma estuvo con la regla desplegada pero la tabla vacia.

    Devuelve el detalle del cruce (que se marco, que se descarto, que no calzo)
    para poder mostrarlo tanto en la consola como en la respuesta HTTP.
    """
    tenant = get_settings().default_tenant_id
    indice = _indice_de_codigos(db)

    # Contexto para desempatar cuando un part number cae en varios rubros.
    candidatos: set[str] = set()
    for fila in pautas:
        candidatos |= indice.get(_norm(fila["part_number"].strip()), set())
    # Los vigentes entran como candidatos mas. Van ANTES de mirar el sugerido y
    # el stock, porque son justamente esos dos datos los que hacen que
    # `elegir_codigo` prefiera el vigente: al estar agrupado, el que aparece en
    # el sugerido es el master del grupo, o sea el vigente.
    vigentes = vigentes_de(db, candidatos)
    candidatos |= set(vigentes.values())
    en_sugerido = {
        p for (p,) in db.execute(
            select(distinct(Sugerido.producto)).where(Sugerido.producto.in_(candidatos))
        ).all()
    } if candidatos else set()
    stock: dict[str, float] = {}
    if candidatos:
        for p, total in db.execute(
            select(StockUnificado.producto, func.coalesce(func.sum(StockUnificado.stock), 0))
            .where(StockUnificado.producto.in_(candidatos))
            .group_by(StockUnificado.producto)
        ).all():
            stock[p] = float(total or 0)

    registros: dict[str, dict] = {}
    sin_codigo: list[dict] = []
    descartados: list[tuple[str, str, list[str]]] = []
    for fila in pautas:
        part = (fila.get("part_number") or "").strip()
        codigos = indice.get(_norm(part))
        if not codigos:
            sin_codigo.append(fila)
            continue
        # Si alguno de los codigos de este part number esta dado de baja y el
        # motor lo agrupo, su vigente compite tambien. `elegir_codigo` se queda
        # con el que esta en el sugerido, que es el master del grupo.
        codigos = set(codigos) | {vigentes[c] for c in codigos if c in vigentes}
        producto = elegir_codigo(codigos, en_sugerido, stock)
        otros = sorted(c for c in codigos if c != producto)
        if otros:
            descartados.append((part, producto, otros))
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

    return {
        "pautas_leidas": len(pautas),
        "productos": len(registros),
        "sin_codigo": len(sin_codigo),
        "part_numbers_en_maestro": len(indice),
        # Detalle para revisar con Repuestos, no para la operacion del dia a dia.
        "sin_codigo_detalle": [
            {
                "marca": f.get("marca"),
                "part_number": f.get("part_number"),
                "operacion": f.get("operacion"),
                "modelos": f.get("modelos"),
            }
            for f in sin_codigo
        ],
        "varios_rubros": [
            {"part_number": part, "se_marca": elegido, "se_descarta": otros}
            for part, elegido, otros in descartados
        ],
        "sin_stock": sorted(p for p in registros if p not in stock),
        "_en_sugerido": en_sugerido,
        "_stock": stock,
        "_registros": registros,
    }


def cargar(path: Path = DEFAULT_PATH) -> dict:
    """Version de linea de comandos: abre su propia sesion y cuenta lo que hizo."""
    pautas = _leer_csv(path)
    print(f"Pautas leídas: {len(pautas)} part numbers ({path.name})")

    create_all()
    db = SessionLocal()
    try:
        r = cargar_en(db, pautas)
        print(f"Códigos en el maestro: {r['part_numbers_en_maestro']} part numbers distintos")
        print(f"Productos marcados InStock: {r['productos']}")
        if r["varios_rubros"]:
            print(f"\nPart numbers que existen bajo varios rubros ({len(r['varios_rubros'])}): "
                  "se marca UNO solo, si no el minimo se pediria una vez por rubro.")
            for d in r["varios_rubros"]:
                elegido = d["se_marca"]
                marca_stock = f"stock={r['_stock'].get(elegido, 0):.0f}"
                en_sug = "en el sugerido" if elegido in r["_en_sugerido"] else "fuera del sugerido"
                print(f"  {d['part_number']}: se marca {elegido} ({en_sug}, {marca_stock}); "
                      f"se descarta {', '.join(d['se_descarta'])}")
        # Codigos elegidos que Curifor no stockea hoy: no es un error del cruce, pero
        # conviene revisarlos con Repuestos (puede ser un codigo que se dejo de usar).
        if r["sin_stock"]:
            print(f"\nCodigos marcados que NO aparecen en el stock de Curifor ({len(r['sin_stock'])}):")
            for p in r["sin_stock"]:
                reg = r["_registros"][p]
                print(f"  {p:<24} {reg['marca']:<8} {reg['operacion']} · {reg['modelos']}")
        if r["sin_codigo_detalle"]:
            print(f"\nSin código en el maestro ({r['sin_codigo']}), no se marcan:")
            for f in r["sin_codigo_detalle"]:
                print(f"  - {f['marca']} {f['part_number']} · {f['operacion']} · {f['modelos']}")
        return {"productos": r["productos"], "sin_codigo": r["sin_codigo"]}
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
