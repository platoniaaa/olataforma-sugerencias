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

    dentro = [i for i in items
              if i["producto"] == "17 GK2Z9365C"
              and i["sucursal_id"] in ("LINDEROS", "RANCAGUA", "CURICO", "CHILLAN")]
    assert dentro, "la busqueda no devolvio el producto"
    assert all(i["instock"] for i in dentro), "el badge se perdio al buscar"
    assert all(i["instock_minimo"] == 2 for i in dentro)


def test_fuera_de_las_sucursales_con_taller_no_se_marca(pauta_con_stock):
    """InStock es producto-SUCURSAL: en Talca el mismo codigo es uno cualquiera.

    Marcarlo en todas confundia: el comprador veia "Si" en Talca y esperaba el
    minimo de 2, que ahi no aplica.
    """
    items, _ = sugerido_service.listar(
        pauta_con_stock, SugeridoFiltros(q="17 GK2Z9365C"), limit=50)

    talca = [i for i in items
             if i["producto"] == "17 GK2Z9365C" and i["sucursal_id"] == "TALCA"]
    assert talca, "no se devolvio la fila de Talca"
    assert all(not i["instock"] for i in talca)
    assert all(i["instock_minimo"] is None for i in talca)


def test_el_marcado_no_depende_del_camino(pauta_con_stock):
    """Dos caminos, una sola regla.

    No se comparan los conjuntos de filas -sin busqueda el filtro por defecto deja
    solo las que piden- sino la REGLA: toda fila devuelta que este en una sucursal
    con taller tiene que salir marcada, entre por donde entre.
    """
    ALCANCE = ("LINDEROS", "RANCAGUA", "CURICO", "CHILLAN")

    for filtros in (SugeridoFiltros(q="17 GK2Z9365C"), SugeridoFiltros()):
        items, _ = sugerido_service.listar(pauta_con_stock, filtros, limit=50)
        mias = [i for i in items if i["producto"] == "17 GK2Z9365C"]
        assert mias, f"no devolvio el producto con {filtros.q!r}"
        for i in mias:
            esperado = i["sucursal_id"] in ALCANCE
            assert bool(i["instock"]) is esperado, (
                f"{i['sucursal_id']} deberia estar {'marcada' if esperado else 'sin marcar'}"
                f" y salio {i['instock']} (busqueda={filtros.q!r})")


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
