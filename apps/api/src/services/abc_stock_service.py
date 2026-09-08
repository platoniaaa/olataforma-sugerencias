"""Detalle ABC por sucursal de lo que hay en stock.

Responde una pregunta que el sugerido no responde: **de lo que tengo guardado,
que se mueve y que no**. El sugerido mira al reves -que hay que comprar- y solo
existe para producto x sucursal CON VENTA en los ultimos 12 meses. Lo que esta
en bodega y no vendio nada no aparece ahi, y es justamente el inventario que hay
que mirar.

Como se arma:

- **El stock entero**, sin filtrar ninguna bodega. La clasificacion de bodegas
  reales/virtuales es de la lista de precios y no se mezcla aca. Las bodegas de
  proceso (danados, devolucion, transito, PE por regularizar) aparecen como una
  sucursal mas, y en ellas el modelo no calcula clase: van marcadas.
- **La clase ABC** sale de `sugerido`, tal cual la calculo el motor. No se
  recalcula nada: si la pantalla mostrara otra clase que el sugerido, una de las
  dos estaria mintiendo.
- **Lo que no tiene fila en el sugerido es D**, por la misma regla del modelo
  (0 meses con venta -> D). Va marcado como "Sin venta 12m" para distinguirlo de
  una D calculada sobre venta real: no es lo mismo un repuesto que vendio 2 de
  12 meses que uno que no vendio nunca.
- **Un codigo que es reemplazo de otro hereda la clase de su master**, porque la
  venta del grupo se acumula en el master.

Medido el 08-09-2026: 29.094 pares (sucursal, producto) con stock, de los cuales
solo 5.514 tienen clase calculada por el modelo.
"""
from __future__ import annotations

import re
from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import ProductoCatalogo, StockUnificado, Sugerido

settings = get_settings()

CLASES = ("A", "B", "C", "D")

# Un codigo interno de Curifor es "<rubro> <codigo>". El filtro hace falta porque
# `sugerido.reemplazos` mezcla el grupo de reemplazo con equivalencias de
# proveedor ("LF595", "PH346", "WK 10 006 Z"): 603 de 1.463 miembros tienen forma
# de codigo interno. Heredar una clase por una equivalencia de catalogo seria
# inventar venta donde no la hubo.
_CODIGO_INTERNO = re.compile(r"^\d+\s+\S")

# Cantidad sobre la que la unidad de medida deja de ser creible: el producto
# tipico tiene 2 unidades y el percentil 99 son 189. Lo que pasa de aca es granel
# cargado en mililitros -o un error de carga-.
UMBRAL_ATIPICO = 5000

BASE_MODELO = "Modelo"
BASE_SIN_VENTA = "Sin venta 12m"


def _tenant() -> str:
    return settings.default_tenant_id


def _version(db: Session) -> tuple:
    """Huella barata de los datos de entrada, para no rearmar en cada request.

    Las dos tablas se reemplazan enteras en cada corrida, asi que el par
    (filas, ultimo id) cambia con cada publicacion.
    """
    t = _tenant()
    out = []
    for modelo in (StockUnificado, Sugerido):
        fila = db.execute(
            select(func.count(modelo.id), func.max(modelo.id)).where(modelo.tenant_id == t)
        ).one()
        out.append((fila[0], fila[1]))
    return tuple(out)


def _masters(db: Session, con_stock: set[str]) -> dict[str, str]:
    """codigo miembro -> codigo master, para heredar la clase del grupo.

    Solo se acepta un miembro que tenga forma de codigo interno Y exista en el
    stock: cualquier otra cosa en esa columna es una equivalencia de catalogo.
    """
    filas = db.execute(
        select(Sugerido.producto, Sugerido.reemplazos).where(
            Sugerido.tenant_id == _tenant(), Sugerido.reemplazos.is_not(None)
        )
    ).all()
    mapa: dict[str, str] = {}
    for master, txt in filas:
        for miembro in str(txt or "").split(","):
            miembro = miembro.strip()
            if (
                miembro
                and miembro != master
                and miembro in con_stock
                and _CODIGO_INTERNO.match(miembro)
            ):
                mapa.setdefault(miembro, master)
    return mapa


def _descripciones(db: Session, productos: set[str]) -> dict[str, str]:
    """Glosa del maestro del ERP; el sugerido rellena lo que falte."""
    t = _tenant()
    desc: dict[str, str] = {}
    for p, g in db.execute(
        select(ProductoCatalogo.producto, ProductoCatalogo.glosa).where(
            ProductoCatalogo.tenant_id == t, ProductoCatalogo.glosa.is_not(None)
        )
    ).all():
        if p in productos:
            desc[p] = g
    for p, g in db.execute(
        select(Sugerido.producto, Sugerido.descripcion).where(
            Sugerido.tenant_id == t, Sugerido.descripcion.is_not(None)
        )
    ).all():
        if p in productos:
            desc.setdefault(p, g)
    return desc


def _construir(db: Session) -> dict:
    """Arma las filas y la matriz de una sola pasada."""
    t = _tenant()

    stock = db.execute(
        select(
            StockUnificado.sucursal_id,
            StockUnificado.producto,
            StockUnificado.bodega,
            StockUnificado.stock,
            StockUnificado.origen,
        ).where(StockUnificado.tenant_id == t)
    ).all()

    unidades: dict[tuple[str, str], float] = defaultdict(float)
    bodegas: dict[tuple[str, str], set[str]] = defaultdict(set)
    empresas: dict[tuple[str, str], set[str]] = defaultdict(set)
    for suc, prod, bod, u, origen in stock:
        clave = (suc or "SIN SUCURSAL", prod)
        unidades[clave] += float(u or 0)
        if bod:
            bodegas[clave].add(bod)
        if origen:
            empresas[clave].add(origen)

    con_stock = {p for _, p in unidades}

    clases: dict[tuple[str, str], tuple] = {}
    evaluadas: set[str] = set()
    for prod, suc, clase, m6, m12 in db.execute(
        select(
            Sugerido.producto,
            Sugerido.sucursal_id,
            Sugerido.clasificacion_abc,
            Sugerido.meses_con_venta_6m,
            Sugerido.meses_con_venta_12m,
        ).where(Sugerido.tenant_id == t)
    ).all():
        evaluadas.add(suc)
        if clase:
            clases[(prod, suc)] = (clase, m6 or 0, m12 or 0)

    master = _masters(db, con_stock)
    desc = _descripciones(db, con_stock)

    filas = []
    for (suc, prod), u in unidades.items():
        hit = clases.get((master.get(prod, prod), suc))
        if hit:
            clase, m6, m12, base = hit[0], hit[1], hit[2], BASE_MODELO
        else:
            clase, m6, m12, base = "D", 0, 0, BASE_SIN_VENTA

        avisos = []
        if u >= UMBRAL_ATIPICO:
            avisos.append("Cantidad atipica: revisar la unidad de medida")
        if prod not in desc:
            avisos.append("Sin descripcion en el maestro")
        if suc not in evaluadas:
            avisos.append("Sucursal que el modelo no evalua")

        emp = sorted(empresas[(suc, prod)])
        filas.append({
            "sucursal": suc,
            "bodegas": ", ".join(sorted(bodegas[(suc, prod)])) or "(sin bodega)",
            "producto": prod,
            "descripcion": desc.get(prod, ""),
            "clase": clase,
            "base_clase": base,
            "meses_con_venta_6m": m6,
            "meses_con_venta_12m": m12,
            "unidades": u,
            "empresa": emp[0] if len(emp) == 1 else ("AMBAS" if emp else ""),
            "aviso": "; ".join(avisos),
        })

    orden = {c: i for i, c in enumerate(CLASES)}
    filas.sort(key=lambda f: (f["sucursal"], orden[f["clase"]], -f["unidades"], f["producto"]))
    return {"filas": filas, "evaluadas": evaluadas}


_cache: dict = {"version": None, "datos": None}


def _datos(db: Session) -> dict:
    v = _version(db)
    if _cache["version"] != v:
        _cache["datos"] = _construir(db)
        _cache["version"] = v
    return _cache["datos"]


def limpiar_cache() -> None:
    """La usan los tests y la carga de datos: la foto cambio, hay que rearmar."""
    _cache["version"] = None
    _cache["datos"] = None


def resumen(db: Session) -> dict:
    """La matriz sucursal x clase, mas lo que hay que saber para leerla."""
    d = _datos(db)
    filas, evaluadas = d["filas"], d["evaluadas"]

    por_suc: dict[str, dict] = {}
    for f in filas:
        s = por_suc.setdefault(f["sucursal"], {
            "sucursal": f["sucursal"],
            "evaluada": f["sucursal"] in evaluadas,
            **{c.lower(): 0 for c in CLASES},
            "skus": 0, "unidades": 0.0,
        })
        s[f["clase"].lower()] += 1
        s["skus"] += 1
        s["unidades"] += f["unidades"]

    sucursales = sorted(por_suc.values(), key=lambda s: -s["skus"])
    total = {
        **{c.lower(): sum(s[c.lower()] for s in sucursales) for c in CLASES},
        "skus": len(filas),
        "unidades": sum(f["unidades"] for f in filas),
        "productos": len({f["producto"] for f in filas}),
    }
    atipicos = {f["producto"] for f in filas if f["unidades"] >= UMBRAL_ATIPICO}
    return {
        "sucursales": sucursales,
        "total": total,
        "cobertura": {
            "del_modelo": sum(1 for f in filas if f["base_clase"] == BASE_MODELO),
            "sin_venta_12m": sum(1 for f in filas if f["base_clase"] == BASE_SIN_VENTA),
        },
        "atipicos": {
            "codigos": len(atipicos),
            "unidades": sum(f["unidades"] for f in filas if f["producto"] in atipicos),
        },
        "sin_descripcion": len({f["producto"] for f in filas if not f["descripcion"]}),
    }


def detalle(
    db: Session,
    *,
    sucursal: list[str] | None = None,
    clase: list[str] | None = None,
    base_clase: str | None = None,
    q: str | None = None,
    page: int = 1,
    limit: int = 200,
) -> tuple[list[dict], int]:
    filas = _datos(db)["filas"]
    if sucursal:
        s = set(sucursal)
        filas = [f for f in filas if f["sucursal"] in s]
    if clase:
        c = {x.upper() for x in clase}
        filas = [f for f in filas if f["clase"] in c]
    if base_clase:
        filas = [f for f in filas if f["base_clase"] == base_clase]
    if q:
        t = q.strip().lower()
        filas = [f for f in filas
                 if t in f["producto"].lower() or t in (f["descripcion"] or "").lower()]
    total = len(filas)
    ini = (page - 1) * limit
    return filas[ini:ini + limit], total
