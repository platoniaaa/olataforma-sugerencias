"""El contexto con el que el comprador decide UNA linea del requerimiento.

Lo que importa probar aca no es que los numeros salgan, sino que salgan cuando el
producto NO esta en el sugerido: ese es el caso normal de un requerimiento (el
vendedor pide justo lo que no se stockea) y es donde la pantalla vieja mostraba
todo en guiones.
"""
import json
from datetime import date

import pytest

from src.main import app
from src.models import (
    ProductoCatalogo,
    StockTransito,
    StockUnificado,
    Sugerido,
    Usuario,
    VentaHistorica,
)
from src.services import requerimiento_service, transito_service
from src.services.auth import hash_password, requiere_auth


@pytest.fixture()
def escenario(db_session):
    """Un repuesto que Linderos vende, con stock y una OC en camino."""
    db_session.add(Usuario(
        email="v@curifor.cl", password_hash=hash_password("123456"),
        nombre="V", es_vendedor=True,
        sucursales_permitidas=json.dumps(["LINDEROS"]),
    ))
    db_session.add(ProductoCatalogo(
        tenant_id="curifor", producto="70 2723982", glosa="FILTRO DE ACEITE",
        precio=10000.0, costo=6000.0,
    ))
    db_session.add_all([
        StockUnificado(tenant_id="curifor", producto="70 2723982",
                       sucursal_id="LINDEROS", stock=4),
        StockUnificado(tenant_id="curifor", producto="70 2723982",
                       sucursal_id="CURICO", stock=11),
    ])
    db_session.add_all([
        StockTransito(tenant_id="curifor", producto="70 2723982",
                      sucursal_id="LINDEROS", cantidad=6,
                      pedido_desde=date(2026, 5, 2)),
        StockTransito(tenant_id="curifor", producto="70 2723982",
                      sucursal_id="CURICO", cantidad=2),
    ])
    db_session.commit()
    return db_session


def _venta(db, periodo, sucursal, cantidad, producto="70 2723982"):
    db.add(VentaHistorica(tenant_id="curifor", periodo=periodo, producto=producto,
                          sucursal=sucursal, cantidad=cantidad))


# --- Transito: la razon de ser de la tabla nueva ----------------------------- #

def test_el_transito_aparece_aunque_el_producto_no_este_en_el_sugerido(escenario):
    """El caso que motivo todo: sin fila en el sugerido tambien hay transito.

    Antes el transito solo existia pegado a `sugerido.stock_en_transito_suc`, y
    el sugerido de una sucursal son ~2.000 filas de un catalogo de 409K. El
    comprador podia volver a comprar algo que ya venia en camino.
    """
    db = escenario
    # A proposito: este par NO tiene fila en el sugerido (el conftest siembra
    # otras, asi que se comprueba el par y no el total de la tabla).
    assert db.query(Sugerido).filter_by(
        producto="70 2723982", sucursal_id="LINDEROS"
    ).count() == 0

    d = requerimiento_service.detalle_producto(db, "70 2723982", "LINDEROS")
    assert d["transito"]["sucursal"] == 6
    assert d["transito"]["pedido_desde"] == "2026-05-02"
    # Y se ve donde mas hay, que a veces convierte la compra en un traslado.
    porsuc = {t["sucursal_id"]: t["cantidad"] for t in d["transito"]["por_sucursal"]}
    assert porsuc == {"LINDEROS": 6, "CURICO": 2}


def test_un_cero_del_sugerido_es_un_dato_y_no_una_falta(escenario):
    """"No viene nada" y "no sabemos" se ven distinto en pantalla y no son lo mismo.

    Si el producto tiene fila en el sugerido, su `stock_en_transito_suc` es
    autoridad aunque sea CERO. Tratarlo como falta mostraria "sin dato" cuando el
    modelo si sabe la respuesta.
    """
    db = escenario
    db.query(StockTransito).delete()
    db.add(Sugerido(
        tenant_id="curifor", producto="70 2723982", sucursal_id="LINDEROS",
        clasificacion_abc="C", stock_en_transito_suc=0,
    ))
    db.commit()

    d = requerimiento_service.detalle_producto(db, "70 2723982", "LINDEROS")
    assert d["transito"]["sucursal"] == 0  # no es None

    # Y la tabla dice lo mismo que el panel: una sola verdad.
    fila = requerimiento_service.analizar(
        db, "LINDEROS", [{"producto": "70 2723982", "cantidad": 1}]
    )["lineas"][0]
    assert fila["transito_sucursal"] == 0


def test_una_tanda_vacia_no_borra_el_transito_que_ya_estaba(escenario):
    """Una corrida fallida del motor no puede decir 'no viene nada en camino'."""
    db = escenario
    antes = db.query(StockTransito).count()
    resumen = transito_service.reemplazar(db, [])
    assert resumen["reemplazo"] is False
    assert db.query(StockTransito).count() == antes


def test_reemplazar_bota_las_cantidades_en_cero(escenario):
    """Una OC en cero no es informacion: solo agranda la tabla."""
    db = escenario
    resumen = transito_service.reemplazar(db, [
        {"producto": "70 2723982", "sucursal_id": "LINDEROS", "cantidad": 3,
         "pedido_desde": "2026-06-01"},
        {"producto": "70 2723982", "sucursal_id": "TALCA", "cantidad": 0},
        {"producto": "", "sucursal_id": "TALCA", "cantidad": 9},
    ])
    assert resumen["filas_cargadas"] == 1
    assert resumen["ignoradas"] == 2
    assert db.query(StockTransito).count() == 1


def test_una_fecha_rota_no_bota_la_fila(escenario):
    """La cantidad es el dato; la fecha es contexto y no puede costar la fila."""
    db = escenario
    transito_service.reemplazar(db, [
        {"producto": "70 2723982", "sucursal_id": "LINDEROS", "cantidad": 5,
         "pedido_desde": "no es una fecha"},
    ])
    fila = db.query(StockTransito).one()
    assert fila.cantidad == 5
    assert fila.pedido_desde is None


# --- Consumo: 12 meses siempre, con ceros explicitos ------------------------- #

def test_el_consumo_trae_los_12_meses_aunque_falten_ventas(escenario):
    """Una serie con huecos se dibuja como si esos meses no existieran."""
    db = escenario
    _venta(db, "202505", "LINDEROS", 3)
    _venta(db, "202503", "LINDEROS", 1)
    db.commit()

    d = requerimiento_service.detalle_producto(db, "70 2723982", "LINDEROS")
    assert len(d["consumo"]) == 12
    # Del mas viejo al mas nuevo, que es como se grafica.
    assert d["consumo"][0]["periodo"] < d["consumo"][-1]["periodo"]
    assert d["consumo_12m_sucursal"] == 4
    assert d["meses_con_venta_12m"] == 2
    con_cero = [m for m in d["consumo"] if m["sucursal"] == 0]
    assert len(con_cero) == 10


def test_el_consumo_cuenta_la_sucursal_con_prefijo_numerico(escenario):
    """"02 LINDEROS" es Linderos. Medido contra produccion: 22 de 30 productos
    del sugerido de Linderos tienen su venta SOLO bajo la forma numerada."""
    db = escenario
    _venta(db, "202505", "02 LINDEROS", 7)
    _venta(db, "202505", "LINDEROS", 1)
    db.commit()

    d = requerimiento_service.detalle_producto(db, "70 2723982", "LINDEROS")
    assert d["consumo_12m_sucursal"] == 8


def test_no_se_come_una_sucursal_que_termina_igual(escenario):
    """"% CHILLAN" no puede tomar "10 CHILLAN VIEJO": son sucursales distintas."""
    db = escenario
    _venta(db, "202505", "10 CHILLAN VIEJO", 50)
    _venta(db, "202505", "09 CHILLAN", 3)
    db.commit()

    d = requerimiento_service.detalle_producto(db, "70 2723982", "CHILLAN")
    assert d["consumo_12m_sucursal"] == 3


# --- Honestidad: distinguir "no se vende" de "falta el dato" ----------------- #

def test_sin_fila_en_el_sugerido_el_modelo_vuelve_en_none(escenario):
    """No es un cero: es que el modelo no evalua este repuesto aca."""
    db = escenario
    d = requerimiento_service.detalle_producto(db, "70 2723982", "LINDEROS")
    assert d["modelo"] is None
    assert d["en_sugerido"] is False
    # Pero el resto del contexto SI esta: stock, transito y precio no dependen
    # del sugerido.
    assert d["stock"]["sucursal"] == 4
    assert d["precio"]["precio"] == 10000.0
    assert d["precio"]["margen_pct"] == 40.0


def test_un_costo_en_cero_no_es_margen_100(escenario):
    """Costo 0 = no tenemos el costo, no un repuesto gratis.

    Sin la guarda el panel muestra "margen 100%" y el comprador compra convencido
    de que es el mejor negocio del requerimiento. Paso de verdad con `06 ML01129`.
    """
    db = escenario
    prod = db.query(ProductoCatalogo).filter_by(producto="70 2723982").one()
    prod.costo = 0.0
    db.commit()

    d = requerimiento_service.detalle_producto(db, "70 2723982", "LINDEROS")
    assert d["precio"]["margen_pct"] is None
    assert d["precio"]["costo"] is None
    assert d["precio"]["precio"] == 10000.0  # el precio si se sabe


def test_con_fila_en_el_sugerido_llegan_los_parametros(escenario):
    db = escenario
    db.add(Sugerido(
        tenant_id="curifor", producto="70 2723982", sucursal_id="LINDEROS",
        clasificacion_abc="A", punto_de_pedido=9, stock_seguridad=4,
        demanda_mensual=12.5, total_sugerido_suc=7, lead_time_dias=15,
    ))
    db.commit()

    d = requerimiento_service.detalle_producto(db, "70 2723982", "LINDEROS")
    assert d["en_sugerido"] is True
    assert d["modelo"]["punto_de_pedido"] == 9
    assert d["modelo"]["stock_seguridad"] == 4
    assert d["modelo"]["sugerido"] == 7
    assert d["modelo"]["lead_time_dias"] == 15


def test_el_stock_por_sucursal_dice_donde_estan_las_unidades(escenario):
    """A veces la respuesta no es comprar sino traer de otra sucursal."""
    db = escenario
    d = requerimiento_service.detalle_producto(db, "70 2723982", "LINDEROS")
    por_suc = {s["sucursal_id"]: s["stock"] for s in d["stock"]["por_sucursal"]}
    assert por_suc == {"LINDEROS": 4.0, "CURICO": 11.0}


# --- El endpoint ------------------------------------------------------------- #

def test_el_endpoint_es_solo_del_comprador(client, escenario):
    """El vendedor no ve el analisis de compra de su propio requerimiento."""
    db = escenario
    app.dependency_overrides[requiere_auth] = lambda: "v@curifor.cl"
    try:
        rid = client.post("/api/requerimientos", json={
            "lineas": [{"producto": "70 2723982", "cantidad": 2}],
        }).json()["id"]
        r = client.get(f"/api/requerimientos/{rid}/producto/70 2723982")
        assert r.status_code == 403
    finally:
        app.dependency_overrides[requiere_auth] = lambda: "test@curifor.com"

    r = client.get(f"/api/requerimientos/{rid}/producto/70 2723982")
    assert r.status_code == 200, r.text[:200]
    assert r.json()["producto"] == "70 2723982"
    assert r.json()["transito"]["sucursal"] == 6


def test_la_linea_del_requerimiento_trae_el_transito(client, escenario):
    """El transito tambien viaja en la tabla, no solo en el panel."""
    db = escenario
    app.dependency_overrides[requiere_auth] = lambda: "v@curifor.cl"
    try:
        rid = client.post("/api/requerimientos", json={
            "lineas": [{"producto": "70 2723982", "cantidad": 2}],
        }).json()["id"]
    finally:
        app.dependency_overrides[requiere_auth] = lambda: "test@curifor.com"

    det = client.get(f"/api/requerimientos/{rid}").json()
    a = det["lineas"][0]["analisis"]
    assert a["transito_sucursal"] == 6
    assert a["transito_nacional"] == 8
    assert a["transito_pedido_desde"] == "2026-05-02"
