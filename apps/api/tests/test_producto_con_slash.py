"""Un codigo con "/" adentro rompia la ficha del producto.

`80 PR/51822` (LIMPIADOR DE FRENOS) existe en el maestro y hoy pide 156 unidades
en Linderos. Al hacerle clic en la grilla, la ficha mostraba:

    No se encontro el producto 80 PR/51822 en la sucursal LINDEROS.
    Error 404 en /api/sugerido/80%20PR%2F51822/LINDEROS

El front encodea bien el "/" como %2F, pero el servidor lo decodifica ANTES de
enrutar, asi que la ruta `/{producto}/{sucursal_id}` -que espera dos segmentos-
recibe tres y no calza. El catalogo ya usaba `{producto:path}` por esta misma
razon; al sugerido nunca se le hizo.

Son 34 productos con "/" en el codigo (65 filas del sugerido). No revienta nada
en el listado: solo no se puede abrir la ficha, que es donde el comprador va a
mirar la venta antes de decidir.
"""
import pytest

from src.models import ProductoCatalogo, Sugerido

# Codigos reales del maestro. El primero es el que reporto Abastecimiento.
CON_SLASH = "80 PR/51822"
OTRO = "13 7153-6206/6306"


@pytest.fixture()
def con_slash(db_session):
    db_session.add_all([
        ProductoCatalogo(tenant_id="curifor", producto=CON_SLASH,
                         glosa="LIMPIADOR DE FRENOS"),
        Sugerido(tenant_id="curifor", producto=CON_SLASH, sucursal_id="LINDEROS",
                 stock_activo_suc=12.0, total_sugerido_suc=156.0, pedir="Si"),
        Sugerido(tenant_id="curifor", producto=OTRO, sucursal_id="CURICO",
                 stock_activo_suc=0.0, total_sugerido_suc=3.0, pedir="Si"),
    ])
    db_session.commit()
    return db_session


def test_la_ficha_abre_un_codigo_con_slash(con_slash, client):
    """El caso exacto del reporte."""
    r = client.get(f"/api/sugerido/{CON_SLASH}/LINDEROS")

    assert r.status_code == 200, r.text
    d = r.json()
    assert d["producto"] == CON_SLASH
    assert d["sucursal_id"] == "LINDEROS"
    assert d["total_sugerido_suc"] == 156


def test_las_ventas_del_codigo_con_slash(con_slash, client):
    """La ficha pide las ventas por su propia ruta: si esa queda rota, el
    grafico sale vacio aunque la ficha haya abierto."""
    r = client.get(f"/api/sugerido/{CON_SLASH}/LINDEROS/ventas")

    assert r.status_code == 200, r.text
    assert r.json()["producto"] == CON_SLASH


def test_la_historia_del_codigo_con_slash(con_slash, client):
    r = client.get(f"/api/sugerido/{CON_SLASH}/LINDEROS/historia")

    assert r.status_code == 200, r.text
    assert "items" in r.json()


def test_un_slash_de_mas_no_confunde_producto_con_sucursal(con_slash, client):
    """El riesgo de `{producto:path}`: que se coma la sucursal.

    El comodin es codicioso, asi que hay que comprobar que el ULTIMO segmento
    siga siendo la sucursal y no parte del codigo.
    """
    r = client.get(f"/api/sugerido/{OTRO}/CURICO")

    assert r.status_code == 200, r.text
    assert r.json()["producto"] == OTRO
    assert r.json()["sucursal_id"] == "CURICO"


def test_un_codigo_sin_slash_sigue_funcionando(db_session, client):
    """Lo de siempre no se puede romper al arreglar lo raro."""
    db_session.add(Sugerido(tenant_id="curifor", producto="17 GK2Z9365C",
                            sucursal_id="LINDEROS", stock_activo_suc=1.0,
                            total_sugerido_suc=2.0, pedir="Si"))
    db_session.commit()

    r = client.get("/api/sugerido/17 GK2Z9365C/LINDEROS")

    assert r.status_code == 200, r.text
    assert r.json()["producto"] == "17 GK2Z9365C"


def test_una_sucursal_que_no_existe_sigue_dando_404(con_slash, client):
    """`{producto:path}` no puede convertir un 404 legitimo en un 200."""
    assert client.get(f"/api/sugerido/{CON_SLASH}/NO-EXISTE").status_code == 404


def test_el_maestro_tambien_abre_un_codigo_con_slash(db_session, client):
    """Hoy no lo llama nadie desde la pantalla, pero es la misma ruta rota: el
    primero que la use se estrella igual."""
    from src.models import DimProducto

    db_session.add(DimProducto(producto=CON_SLASH, descripcion="LIMPIADOR DE FRENOS"))
    db_session.commit()

    r = client.get(f"/api/productos/{CON_SLASH}")

    assert r.status_code == 200, r.text
    assert r.json()["producto"] == CON_SLASH
