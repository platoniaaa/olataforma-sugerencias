"""Las tarjetas de arriba tienen que dar lo mismo que la tabla de abajo.

Hasta jul-2026 `kpis()` consultaba solo la tabla `Sugerido`, asi que las
sugerencias manuales —que la grilla si suma— no aparecian en ningun KPI: lo que
Mary cargaba a mano quedaba fuera del total a comprar y del valor en CLP.

Ademas, `pares_en_sugerido` se armaba con las filas de la PAGINA en vez de con
todo el set filtrado: una manual cuyo par caia en la pagina 2 se mostraba ademas
como fila suelta en la pagina 1 y se contaba dos veces.
"""
from src.models import ProductoCatalogo, Sugerido, SugerenciaManual


def _sug(db_session, producto, total=10, costo=1000.0, **kw):
    base = dict(
        tenant_id="curifor", producto=producto, sucursal_id="LINDEROS",
        nombre_sucursal="Linderos", pedir="Si", total_sugerido_suc=total,
        sugerido_compra_neto=total, costo_unitario=costo,
        total_valor_sugerido_clp=total * costo, proveedor="Ford Motor Company Chile",
    )
    base.update(kw)
    db_session.add(Sugerido(**base))
    db_session.commit()


def _manual(db_session, producto, unidades, sucursal_id="LINDEROS"):
    db_session.add(SugerenciaManual(
        tenant_id="curifor", producto=producto, sucursal_id=sucursal_id,
        unidades=unidades, creado_por="test",
    ))
    db_session.commit()


def _kpis(client, **filtros):
    r = client.get("/api/sugerido/kpis", params=filtros)
    assert r.status_code == 200
    return r.json()


def _grilla(client, **params):
    r = client.get("/api/sugerido", params=params)
    assert r.status_code == 200
    return r.json()


def test_kpis_suman_la_manual_sobre_una_fila_existente(client, db_session):
    _sug(db_session, "KPI-1", total=10, costo=1000.0)
    _manual(db_session, "KPI-1", 7)

    k = _kpis(client, q="KPI-1")
    # 10 del modelo + 7 cargadas a mano, valorizadas al costo de la fila.
    assert k["total_sugerido"] == 17
    assert k["valor_total_clp"] == 17000
    assert k["total_sugerido_manual"] == 7
    assert k["valor_manual_clp"] == 7000
    # La manual cae sobre una fila que ya existe: no agrega fila ni producto.
    assert k["n_filas"] == 1
    assert k["n_productos"] == 1


def test_kpis_suman_la_manual_de_un_producto_que_el_modelo_no_pide(client, db_session):
    # Sin fila en Sugerido: la manual es una fila propia y se valoriza con el catalogo.
    db_session.add(ProductoCatalogo(
        tenant_id="curifor", producto="KPI-SOLO", glosa="Repuesto suelto", costo=2500.0,
    ))
    db_session.commit()
    _manual(db_session, "KPI-SOLO", 4)

    k = _kpis(client, q="KPI-SOLO")
    assert k["total_sugerido"] == 4
    assert k["valor_total_clp"] == 10000
    assert k["total_sugerido_manual"] == 4
    assert k["valor_manual_clp"] == 10000
    # Aporta su propia fila y su propio producto al conteo.
    assert k["n_filas"] == 1
    assert k["n_productos"] == 1


def test_sin_manuales_los_kpis_no_cambian(client, db_session):
    _sug(db_session, "KPI-2", total=25, costo=200.0)

    k = _kpis(client, q="KPI-2")
    assert k["total_sugerido"] == 25
    assert k["valor_total_clp"] == 5000
    assert k["total_sugerido_manual"] == 0
    assert k["valor_manual_clp"] == 0


def test_los_kpis_cuadran_con_la_tabla(client, db_session):
    """El invariante que motiva todo: tarjetas == suma de lo que se ve abajo."""
    _sug(db_session, "CUA-1", total=10, costo=1000.0)
    _sug(db_session, "CUA-2", total=5, costo=400.0)
    db_session.add(ProductoCatalogo(
        tenant_id="curifor", producto="CUA-3", glosa="Solo manual", costo=300.0,
    ))
    db_session.commit()
    _manual(db_session, "CUA-1", 3)   # sobre una fila existente
    _manual(db_session, "CUA-3", 6)   # fila suelta

    k = _kpis(client, q="CUA-", solo_pedir=False)
    filas = _grilla(client, q="CUA-", solo_pedir=False, limit=5000)["items"]

    assert k["n_filas"] == len(filas)
    assert k["total_sugerido"] == sum(f["total_sugerido_suc"] or 0 for f in filas)
    assert k["valor_total_clp"] == sum(f["total_valor_sugerido_clp"] or 0 for f in filas)
    assert k["n_productos"] == len({f["producto"] for f in filas})


def test_el_total_no_depende_del_tamano_de_pagina(client, db_session):
    for i, total in enumerate([40, 30, 20, 10], start=1):
        _sug(db_session, f"PAG-{i}", total=total)
    _manual(db_session, "PAG-4", 5)  # la fila PAG-4 queda en la ultima pagina

    totales = {
        _grilla(client, q="PAG-", solo_pedir=False, limit=lim, page=1)["total"]
        for lim in (1, 2, 3, 100)
    }
    # 4 filas del modelo y ninguna suelta: la manual ya tiene su fila.
    assert totales == {4}


def test_manual_de_otra_pagina_no_se_duplica_como_fila_suelta(client, db_session):
    for i, total in enumerate([40, 30, 20, 10], start=1):
        _sug(db_session, f"DUP-{i}", total=total)
    _manual(db_session, "DUP-4", 5)

    p1 = _grilla(client, q="DUP-", solo_pedir=False, limit=2, page=1,
                 sort="-total_sugerido_suc")
    # DUP-4 no esta en la pagina 1, pero su manual tampoco: la fila real la espera.
    assert [f["producto"] for f in p1["items"]] == ["DUP-1", "DUP-2"]
    assert not [f for f in p1["items"] if f["origen"] == "manual"]

    p2 = _grilla(client, q="DUP-", solo_pedir=False, limit=2, page=2,
                 sort="-total_sugerido_suc")
    dup4 = next(f for f in p2["items"] if f["producto"] == "DUP-4")
    # Las unidades manuales se suman UNA vez, sobre su fila.
    assert dup4["total_sugerido_suc"] == 15
    assert p1["total"] == p2["total"] == 4
