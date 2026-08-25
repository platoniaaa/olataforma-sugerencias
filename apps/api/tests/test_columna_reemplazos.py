r"""La columna `Reemplazos` del sugerido tiene UNA sola fuente.

Abastecimiento levanto el caso el 11-08-2026: tres codigos hermanos mostraban tres
cosas distintas en la misma columna.

    17 GK2Z9365A  ->  "2005485 GK2Z9365A"         (sin coma, sin rubro)
    17 GK2Z9365C  ->  "17 GK2Z9365A, 17 2005485"  (formato del motor)
    17 2005485    ->  "GK2Z9365A\GK2Z9365C"       (backslash, fila de catalogo)

No era un problema de formato sino de origen: la fila del master traia el grupo
del motor, y las demas -InStock, manuales, catalogo- caian al texto crudo del mix.
"""
import pytest

from src.models import ProductoCatalogo, Sugerido
from src.services import sugerido_service

BACK = chr(92)  # el separador del mix, sin pelear con los escapes


@pytest.fixture()
def familia(db_session):
    """El motor agrupo los tres bajo `17 GK2Z9365C`, pero solo publico su fila."""
    db_session.add(Sugerido(
        tenant_id="curifor", producto="17 GK2Z9365C", sucursal_id="LINDEROS",
        reemplazos="17 2005485, 17 GK2Z9365A"))
    # El mix guarda lo suyo con backslash y sin rubro.
    db_session.add_all([
        ProductoCatalogo(tenant_id="curifor", producto="17 GK2Z9365A",
                         glosa="FILTRO", reemplazo="2005485" + BACK + "GK2Z9365C"),
        ProductoCatalogo(tenant_id="curifor", producto="17 2005485",
                         glosa="FILTRO", reemplazo="GK2Z9365A" + BACK + "GK2Z9365C"),
    ])
    db_session.commit()
    return db_session


def test_los_tres_hermanos_muestran_el_mismo_grupo(familia):
    """El caso exacto que levanto Abastecimiento.

    Cada uno lista a los OTROS dos, asi que los textos no son identicos, pero
    describen el mismo grupo y en el mismo formato.
    """
    items = [{"producto": p} for p in
             ("17 GK2Z9365A", "17 GK2Z9365C", "17 2005485")]

    sugerido_service._enriquecer_con_catalogo(items, familia)

    assert items[0]["reemplazos"] == "17 2005485, 17 GK2Z9365C"
    assert items[1]["reemplazos"] == "17 2005485, 17 GK2Z9365A"
    assert items[2]["reemplazos"] == "17 GK2Z9365A, 17 GK2Z9365C"


def test_ninguno_queda_con_el_texto_crudo_del_mix(familia):
    """El backslash del mix no puede llegar a la pantalla."""
    items = [{"producto": p} for p in
             ("17 GK2Z9365A", "17 GK2Z9365C", "17 2005485")]

    sugerido_service._enriquecer_con_catalogo(items, familia)

    for it in items:
        assert BACK not in (it["reemplazos"] or "")


def test_un_producto_que_el_motor_no_agrupo_conserva_el_del_mix(db_session):
    """El plan B sigue existiendo, pero con el separador normalizado.

    El mix agrupa equivalentes que FORD nunca va a nombrar, y esa informacion es
    util: lo unico que cambia es que se muestra como el resto.
    """
    db_session.add(ProductoCatalogo(
        tenant_id="curifor", producto="80 PR51822", glosa="X",
        reemplazo="173897" + BACK + "391732"))
    db_session.commit()
    items = [{"producto": "80 PR51822"}]

    sugerido_service._enriquecer_con_catalogo(items, db_session)

    assert items[0]["reemplazos"] == "173897, 391732"
