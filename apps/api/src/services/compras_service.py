"""Agente comprador (Nivel 1): arma carros de compra agrupando el sugerido por proveedor.

La cantidad a pedir a cada proveedor es la "compra neta" (lo que no se cubre con traslado
desde el CD): sugerido_compra_neto, o total_sugerido_suc si el neto viene vacio. Se suma
por producto a traves de las sucursales -> una linea por producto por proveedor.

Las filas salen de `sugerido_service.listar`, la MISMA resolucion que usa la grilla del
sugerido. Hasta oct-2026 este modulo tenia su propio SELECT sobre la tabla `sugerido` y
solo le sumaba las manuales por JOIN: se perdia todo lo que `listar` agrega en Python.
La orden de compra traia menos que la grilla en tres casos (auditoria del 17-10):

- el minimo InStock (repuesto de pauta con minimo 5 y el modelo pide 3: carro 3);
- una manual sobre una sucursal sin fila para ese producto, si el producto tenia fila
  en OTRA sucursal (se miraba si el producto existia, no el par);
- una manual sobre una fila con pedir = No (el "solo pedir" de la pantalla la sacaba).

Lo que sigue igual que antes:
- Una fila del sugerido del BI sin proveedor no entra a ningun carro.
- Las filas que `listar` fabrica para pares sin fila en el BI (manual o InStock) van
  al carro de su proveedor si `listar` lo encontro en otra fuente, y si no, a "Sin
  proveedor asignado".
- Las filas del catalogo que la busqueda agrega (sin sucursal ni cantidad) no son
  compra.
"""
from __future__ import annotations

from ..schemas import CarroProveedor, CarrosResponse, LineaCarro, SugeridoFiltros
from . import sugerido_service

SIN_PROVEEDOR = "Sin proveedor asignado"
# Mismo tope que el Excel de la grilla (routers/sugerido.py): todas las filas.
LIMITE_FILAS = 100_000
# Filas que `listar` fabrica porque el par no tiene fila en el sugerido del BI.
_SINTETICAS = ("manual", "instock")


def _cantidad_compra(fila: dict) -> float:
    """La compra neta de la fila, ya con las manuales y el minimo InStock sumados."""
    neto = fila.get("sugerido_compra_neto")
    if neto is None:
        neto = fila.get("total_sugerido_suc")
    return float(neto or 0)


def _normalizar(texto: str | None) -> str:
    return sugerido_service._sin_tildes((texto or "").strip().upper())


def _sintetica_pasa_filtros(fila: dict, proveedor: str, f: SugeridoFiltros) -> bool:
    """Los filtros de la pantalla, aplicados a una fila fabricada.

    Las filas que vienen de la tabla ya pasaron el WHERE de `_apply_filters`. Las
    fabricadas no: `listar` las agrega sin mirar proveedor, marca, clase ni sucursal.
    En la grilla se ven igual; en un carro, filtrar por un proveedor y recibir lineas
    de otro seria un error, asi que aca se filtran con lo que la fila trae despues de
    completarse (el proveedor puede venir de otra sucursal o de las OC historicas).
    """
    if f.proveedor and f.proveedor.strip().lower() not in proveedor.lower():
        return False
    if f.proveedores and proveedor not in f.proveedores:
        return False
    if f.filtro1 and fila.get("filtro1_final") not in f.filtro1:
        return False
    if f.tipo_origen and fila.get("tipo_origen") not in f.tipo_origen:
        return False
    if f.abc and fila.get("clasificacion_abc") not in f.abc:
        return False
    if f.sucursales:
        elegidas = {_normalizar(s) for s in f.sucursales}
        if (_normalizar(fila.get("sucursal_id")) not in elegidas
                and _normalizar(fila.get("nombre_sucursal")) not in elegidas):
            return False
    return True


def _mayor(actual, nuevo):
    """El mayor de los dos sin perder un valor por un None (como MAX() en SQL)."""
    if actual is None:
        return nuevo
    if nuevo is None:
        return actual
    return max(actual, nuevo)


def carros_por_proveedor(db, f: SugeridoFiltros) -> CarrosResponse:
    items, _total = sugerido_service.listar(db, f, page=1, limit=LIMITE_FILAS)

    # (proveedor, producto) -> acumulado de la linea.
    lineas: dict[tuple[str, str], dict] = {}
    for fila in items:
        producto = fila.get("producto")
        if not producto or not fila.get("sucursal_id"):
            continue  # fila del catalogo: aparece al buscar, pero no es compra
        proveedor = fila.get("proveedor")
        sintetica = fila.get("origen") in _SINTETICAS
        if not proveedor:
            if not sintetica:
                continue
            proveedor = SIN_PROVEEDOR
        if sintetica and not _sintetica_pasa_filtros(fila, proveedor, f):
            continue
        costo = fila.get("costo_unitario")
        acc = lineas.setdefault(
            (proveedor, producto),
            {"descripcion": None, "abc": None, "costo": None, "cantidad": 0.0},
        )
        acc["cantidad"] += _cantidad_compra(fila)
        acc["descripcion"] = _mayor(acc["descripcion"], fila.get("descripcion"))
        acc["abc"] = _mayor(acc["abc"], fila.get("clasificacion_abc"))
        acc["costo"] = _mayor(acc["costo"], float(costo) if costo is not None else None)

    carros: dict[str, CarroProveedor] = {}
    for (proveedor, producto), acc in lineas.items():
        cantidad = acc["cantidad"]
        if cantidad <= 0:
            continue
        costo = acc["costo"]
        carro = carros.get(proveedor)
        if carro is None:
            carro = CarroProveedor(proveedor=proveedor, lineas=[])
            carros[proveedor] = carro
        carro.lineas.append(
            LineaCarro(
                producto=producto,
                descripcion=acc["descripcion"],
                clasificacion_abc=acc["abc"],
                cantidad=cantidad,
                costo_unitario=costo,
                subtotal_clp=cantidad * (costo or 0),
            )
        )

    # Totales y orden.
    lista: list[CarroProveedor] = []
    for carro in carros.values():
        carro.lineas.sort(key=lambda x: x.subtotal_clp, reverse=True)
        carro.n_productos = len(carro.lineas)
        carro.total_unidades = sum(x.cantidad for x in carro.lineas)
        carro.total_clp = sum(x.subtotal_clp for x in carro.lineas)
        lista.append(carro)
    lista.sort(key=lambda c: c.total_clp, reverse=True)

    return CarrosResponse(
        carros=lista,
        total_proveedores=len(lista),
        total_clp=sum(c.total_clp for c in lista),
        total_unidades=sum(c.total_unidades for c in lista),
    )
