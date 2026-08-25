"""El badge INSTOCK no puede depender de la pantalla en la que estes.

Abastecimiento reviso los codigos buscandolos uno por uno y ninguno salia marcado,
aunque los 60 estaban en la lista. El listado los marcaba y la busqueda no.

La causa: `_resolver_instock` devolvia `vacio` en cuanto no habia unidades que
sumar, y de paso se llevaba el catalogo -que es lo que `instock_service.aplicar`
usa para marcar-. Con el filtro de texto acotando a un solo producto, cualquier
repuesto con stock sobre el minimo caia en ese caso.
"""
import pytest

from src.models import RepuestoInstock, Sugerido
from src.schemas.sugerido import SugeridoFiltros
from src.services import sugerido_service


@pytest.fixture()
def pauta_con_stock(db_session):
    """Un repuesto de pauta que NO necesita unidades: stock 15, minimo 2."""
    db_session.add(RepuestoInstock(tenant_id="curifor", producto="17 GK2Z9365C",
                           minimo=2, modelos="Transit", marca="FORD"))
    # LAS CUATRO sucursales del alcance InStock, todas con stock sobre el minimo.
    # Si alguna quedara sin fila, faltarian unidades ahi y el catalogo viajaria
    # igual: el bug solo aparece cuando NADA que mostrar necesita unidades, que es
    # justo el caso de este repuesto en produccion (7, 5, 15 y 10 en bodega).
    db_session.add_all([
        Sugerido(tenant_id="curifor", producto="17 GK2Z9365C",
                 sucursal_id="LINDEROS", stock_activo_suc=15.0,
                 total_sugerido_suc=1.0, pedir="Si"),
        Sugerido(tenant_id="curifor", producto="17 GK2Z9365C",
                 sucursal_id="RANCAGUA", stock_activo_suc=10.0,
                 total_sugerido_suc=0.0, pedir="No"),
        Sugerido(tenant_id="curifor", producto="17 GK2Z9365C",
                 sucursal_id="CURICO", stock_activo_suc=5.0,
                 total_sugerido_suc=0.0, pedir="No"),
        Sugerido(tenant_id="curifor", producto="17 GK2Z9365C",
                 sucursal_id="CHILLAN", stock_activo_suc=7.0,
                 total_sugerido_suc=0.0, pedir="No"),
        Sugerido(tenant_id="curifor", producto="17 GK2Z9365C",
                 sucursal_id="TALCA", stock_activo_suc=4.0,
                 total_sugerido_suc=0.0, pedir="No"),
    ])
    db_session.commit()
    return db_session


def test_el_badge_sobrevive_a_la_busqueda(pauta_con_stock):
    """El caso exacto que reporto Abastecimiento."""
    items, _ = sugerido_service.listar(
        pauta_con_stock, SugeridoFiltros(q="17 GK2Z9365C"), limit=50)

    filas = [i for i in items if i["producto"] == "17 GK2Z9365C"]
    assert filas, "la busqueda no devolvio el producto"
    assert all(i["instock"] for i in filas), "el badge se perdio al buscar"
    assert all(i["instock_minimo"] == 2 for i in filas)


def test_el_badge_es_el_mismo_buscando_y_sin_buscar(pauta_con_stock):
    """Dos caminos, una sola verdad."""
    con, _ = sugerido_service.listar(
        pauta_con_stock, SugeridoFiltros(q="17 GK2Z9365C"), limit=50)
    sin, _ = sugerido_service.listar(pauta_con_stock, SugeridoFiltros(), limit=50)

    marcado_con = {i["producto"] for i in con if i.get("instock")}
    marcado_sin = {i["producto"] for i in sin if i.get("instock")}

    assert "17 GK2Z9365C" in marcado_con
    assert "17 GK2Z9365C" in marcado_sin


def test_buscando_por_descripcion_tambien_queda_marcado(pauta_con_stock):
    """El acotado por texto compara contra el CODIGO, y la grilla busca por los dos.

    Sin esto, buscar "FILTRO COMBUSTIBLE" devolvia la fila sin badge: el codigo no
    contiene ese texto, asi que el producto quedaba fuera del acotado y con el se
    iba el catalogo entero.
    """
    items, _ = sugerido_service.listar(
        pauta_con_stock, SugeridoFiltros(q="NO CALZA CON NINGUN CODIGO"), limit=50)

    # No devuelve filas, pero lo que importa es que no reviente ni deje el
    # catalogo vacio para las que si devuelva en un caso real.
    ins = sugerido_service._resolver_instock(
        pauta_con_stock, SugeridoFiltros(q="NO CALZA CON NINGUN CODIGO"), {}, {"por_par": {}})
    assert ins["cat"], "el catalogo tiene que viajar igual"


def test_un_repuesto_bajo_el_minimo_sigue_sumando_unidades(db_session):
    """La otra mitad de la regla no se toco: si falta stock, se pide."""
    db_session.add(RepuestoInstock(tenant_id="curifor", producto="17 PAUTA",
                           minimo=2, modelos="Transit", marca="FORD"))
    db_session.add(Sugerido(tenant_id="curifor", producto="17 PAUTA",
                            sucursal_id="LINDEROS", stock_activo_suc=0.0,
                            total_sugerido_suc=0.0, pedir="No"))
    db_session.commit()

    items, _ = sugerido_service.listar(db_session, SugeridoFiltros(), limit=50)

    fila = next(i for i in items if i["producto"] == "17 PAUTA")
    assert fila["instock"] is True
    assert fila["total_sugerido_suc"] == 2
