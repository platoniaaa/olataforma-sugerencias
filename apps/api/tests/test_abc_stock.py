"""El detalle ABC por sucursal de lo que hay en stock.

Lo que estos tests cuidan:

1. Que entre TODO el stock. La clasificacion de bodegas reales/virtuales es de la
   lista de precios y no se mezcla aca: danados, transito y PE por regularizar
   son una sucursal mas.
2. Que lo que no tiene fila en el sugerido salga D pero MARCADO, para que no se
   confunda con una D calculada sobre venta real.
3. Que la clase sea la del sugerido y no una recalculada aca. Si la pantalla
   mostrara otra clase que el sugerido, una de las dos estaria mintiendo.
4. Que un codigo que es reemplazo de otro herede la clase del master, y que no la
   herede por una equivalencia de proveedor: `sugerido.reemplazos` mezcla las dos
   cosas.
"""
import pytest

from src.models import ProductoCatalogo, StockUnificado, Sugerido
from src.services import abc_stock_service as svc


@pytest.fixture(autouse=True)
def _sin_cache():
    svc.limpiar_cache()
    yield
    svc.limpiar_cache()


def _stock(db, producto, sucursal, unidades, bodega="B1", origen="CURIFOR"):
    db.add(StockUnificado(tenant_id="curifor", producto=producto, bodega=bodega,
                          sucursal_id=sucursal, stock=unidades, origen=origen))


def _sug(db, producto, sucursal, clase, m6=0, m12=0, descripcion="X", reemplazos=None):
    db.add(Sugerido(tenant_id="curifor", producto=producto, sucursal_id=sucursal,
                    nombre_sucursal=sucursal, clasificacion_abc=clase,
                    meses_con_venta_6m=m6, meses_con_venta_12m=m12,
                    descripcion=descripcion, reemplazos=reemplazos))


# --- La clase sale del sugerido, no se recalcula ---------------------------------


def test_toma_la_clase_del_sugerido(db_session):
    _stock(db_session, "17 A", "LINDEROS", 5)
    _sug(db_session, "17 A", "LINDEROS", "A", m6=6, m12=12)
    db_session.commit()

    filas, total = svc.detalle(db_session)

    assert total == 1
    assert filas[0]["clase"] == "A"
    assert filas[0]["base_clase"] == "Modelo"
    assert filas[0]["meses_con_venta_6m"] == 6


def test_lo_que_no_esta_en_el_sugerido_es_D_pero_marcado(db_session):
    """Por la regla del modelo, 0 meses con venta da D. Va marcado para que no se
    confunda con una D calculada sobre venta real."""
    _stock(db_session, "17 SIN-VENTA", "LINDEROS", 3)
    _sug(db_session, "17 OTRO", "LINDEROS", "A")
    db_session.commit()

    filas, _ = svc.detalle(db_session, q="SIN-VENTA")

    assert filas[0]["clase"] == "D"
    assert filas[0]["base_clase"] == "Sin venta 12m"
    assert filas[0]["meses_con_venta_12m"] == 0


def test_la_clase_es_por_sucursal(db_session):
    """El mismo repuesto puede ser A donde se mueve y D donde no."""
    _stock(db_session, "17 A", "LINDEROS", 5)
    _stock(db_session, "17 A", "TALCA", 2)
    _sug(db_session, "17 A", "LINDEROS", "A", m6=6)
    _sug(db_session, "17 A", "TALCA", "D")
    db_session.commit()

    por_suc = {f["sucursal"]: f["clase"] for f in svc.detalle(db_session)[0]}

    assert por_suc == {"LINDEROS": "A", "TALCA": "D"}


# --- Todo el stock, sin filtrar bodegas -----------------------------------------


def test_las_bodegas_de_proceso_entran_igual(db_session):
    """No se filtra ninguna bodega: eso es de la lista de precios."""
    _stock(db_session, "17 A", "BODEGA DANADOS", 9, bodega="BODEGA DAÑADOS")
    _stock(db_session, "17 A", "TRANSITO", 4, bodega="TRANSITO")
    db_session.commit()

    sucursales = {s["sucursal"]: s for s in svc.resumen(db_session)["sucursales"]}

    assert sucursales["BODEGA DANADOS"]["skus"] == 1
    assert sucursales["TRANSITO"]["unidades"] == 4


def test_la_sucursal_que_el_modelo_no_evalua_va_marcada(db_session):
    _stock(db_session, "17 A", "BODEGA DANADOS", 9)
    _stock(db_session, "17 B", "LINDEROS", 1)
    _sug(db_session, "17 B", "LINDEROS", "D")
    db_session.commit()

    por_suc = {s["sucursal"]: s for s in svc.resumen(db_session)["sucursales"]}
    assert por_suc["BODEGA DANADOS"]["evaluada"] is False
    assert por_suc["LINDEROS"]["evaluada"] is True

    fila = svc.detalle(db_session, sucursal=["BODEGA DANADOS"])[0][0]
    assert "no evalua" in fila["aviso"]


def test_suma_las_bodegas_de_la_misma_sucursal_y_las_nombra(db_session):
    _stock(db_session, "17 A", "CURICO", 5, bodega="CURICO")
    _stock(db_session, "17 A", "CURICO", 3, bodega="BODEGA DyP CURICO")
    db_session.commit()

    fila = svc.detalle(db_session)[0][0]

    assert fila["unidades"] == 8
    assert fila["bodegas"] == "BODEGA DyP CURICO, CURICO"


def test_el_stock_sin_bodega_se_dice(db_session):
    """53 filas del ERP vienen sin bodega; dejarlo en blanco parece un error de la
    pantalla."""
    _stock(db_session, "17 A", "DESCONOCIDO", 6, bodega=None)
    db_session.commit()

    assert svc.detalle(db_session)[0][0]["bodegas"] == "(sin bodega)"


# --- Grupos de reemplazo --------------------------------------------------------


def test_el_miembro_hereda_la_clase_del_master(db_session):
    """La venta del grupo se acumula en el master; el miembro no tiene fila."""
    _stock(db_session, "13 VIEJO", "LINDEROS", 4)
    _sug(db_session, "13 NUEVO", "LINDEROS", "A", m6=6, reemplazos="13 VIEJO")
    db_session.commit()

    fila = svc.detalle(db_session, q="VIEJO")[0][0]

    assert fila["clase"] == "A"
    assert fila["base_clase"] == "Modelo"


def test_no_hereda_por_una_equivalencia_de_proveedor(db_session):
    """`sugerido.reemplazos` mezcla el grupo con equivalencias de catalogo
    ("LF595", "PH346"). Heredar por ahi seria inventar venta donde no la hubo."""
    _stock(db_session, "LF595", "LINDEROS", 4)
    _sug(db_session, "100 FILTRO", "LINDEROS", "A", m6=6, reemplazos="LF595, PH346")
    db_session.commit()

    fila = svc.detalle(db_session, q="LF595")[0][0]

    assert fila["clase"] == "D"
    assert fila["base_clase"] == "Sin venta 12m"


# --- Resumen y avisos -----------------------------------------------------------


def test_el_resumen_cuadra_con_el_detalle(db_session):
    _stock(db_session, "17 A", "LINDEROS", 5)
    _stock(db_session, "17 B", "LINDEROS", 2)
    _stock(db_session, "17 C", "TALCA", 1)
    _sug(db_session, "17 A", "LINDEROS", "A")
    db_session.commit()

    r = svc.resumen(db_session)
    _, total = svc.detalle(db_session)

    assert r["total"]["skus"] == total == 3
    assert r["total"]["unidades"] == 8
    assert r["total"]["a"] == 1 and r["total"]["d"] == 2
    assert r["cobertura"] == {"del_modelo": 1, "sin_venta_12m": 2}


def test_avisa_de_la_cantidad_atipica(db_session):
    """Los aceites a granel vienen en mililitros y se llevan el 95% del total."""
    _stock(db_session, "70 GRANEL", "LINDEROS", 1_000_000)
    _stock(db_session, "17 NORMAL", "LINDEROS", 3)
    db_session.commit()

    por_prod = {f["producto"]: f for f in svc.detalle(db_session)[0]}

    assert "atipica" in por_prod["70 GRANEL"]["aviso"]
    assert "atipica" not in por_prod["17 NORMAL"]["aviso"]
    assert svc.resumen(db_session)["atipicos"]["codigos"] == 1


def test_la_descripcion_sale_del_maestro(db_session):
    db_session.add(ProductoCatalogo(tenant_id="curifor", producto="17 A", glosa="AMORTIGUADOR"))
    _stock(db_session, "17 A", "LINDEROS", 5)
    _sug(db_session, "17 A", "LINDEROS", "A", descripcion="viene del sugerido")
    db_session.commit()

    assert svc.detalle(db_session)[0][0]["descripcion"] == "AMORTIGUADOR"


def test_sin_descripcion_en_ningun_lado_se_avisa(db_session):
    _stock(db_session, "17 HUERFANO", "LINDEROS", 5)
    db_session.commit()

    fila = svc.detalle(db_session)[0][0]

    assert fila["descripcion"] == ""
    assert "Sin descripcion" in fila["aviso"]
    assert svc.resumen(db_session)["sin_descripcion"] == 1


# --- Filtros y paginacion -------------------------------------------------------


def test_filtra_por_sucursal_y_clase(db_session):
    _stock(db_session, "17 A", "LINDEROS", 5)
    _stock(db_session, "17 B", "LINDEROS", 5)
    _stock(db_session, "17 C", "TALCA", 5)
    _sug(db_session, "17 A", "LINDEROS", "A")
    db_session.commit()

    assert svc.detalle(db_session, sucursal=["LINDEROS"])[1] == 2
    assert svc.detalle(db_session, clase=["A"])[1] == 1
    assert svc.detalle(db_session, base_clase="Sin venta 12m")[1] == 2


def test_paginar_no_repite_ni_pierde(db_session):
    for i in range(12):
        _stock(db_session, f"17 P{i:02d}", "LINDEROS", 1)
    db_session.commit()

    vistos = []
    for page in range(1, 4):
        items, total = svc.detalle(db_session, page=page, limit=5)
        vistos.extend(i["producto"] for i in items)

    assert total == 12
    assert len(vistos) == len(set(vistos)) == 12


# --- La cache no puede servir una foto vieja ------------------------------------


def test_la_cache_se_entera_de_que_llego_stock_nuevo(db_session):
    _stock(db_session, "17 A", "LINDEROS", 5)
    db_session.commit()
    assert svc.detalle(db_session)[1] == 1

    _stock(db_session, "17 B", "LINDEROS", 2)
    db_session.commit()

    assert svc.detalle(db_session)[1] == 2, "la cache sirvio la foto vieja"


# --- API ------------------------------------------------------------------------


def test_endpoints(client, db_session):
    _stock(db_session, "17 A", "LINDEROS", 5)
    _sug(db_session, "17 A", "LINDEROS", "A", m6=6)
    db_session.commit()

    r = client.get("/api/tablero/abc-stock")
    assert r.status_code == 200, r.text
    assert r.json()["total"]["skus"] == 1

    d = client.get("/api/tablero/abc-stock/detalle", params={"clase": "A"})
    assert d.status_code == 200, d.text
    assert d.json()["items"][0]["producto"] == "17 A"


def test_una_clase_inventada_se_rechaza(client, db_session):
    r = client.get("/api/tablero/abc-stock/detalle", params={"clase": "Z"})

    assert r.status_code == 422
    assert "A, B, C o D" in r.json()["detail"]
