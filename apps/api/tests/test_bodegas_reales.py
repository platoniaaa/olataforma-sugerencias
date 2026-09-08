"""La lista de precios solo cuenta el stock de bodegas reales.

El ERP mezcla bodegas fisicas con bodegas de proceso -danados, devolucion,
scrap, PE por regularizar, importacion-. Ese stock existe pero no se puede
vender, y decidir un precio con el es decir que hay algo que no hay.

Medido el 08-09-2026 sobre las 30 mil filas de stock: **436 productos** tenian
stock UNICAMENTE en bodegas no reales -salian con precio como si estuvieran
disponibles- y a otros 535 les sobraba stock que no se puede vender.

Lo que estos tests cuidan:

1. Que el cruce aguante las dos escrituras del mismo deposito ("CHILLAN 2" y
   "CHILLAN2"). Comparando el texto crudo quedaban 1,4 millones de unidades sin
   clasificar, o sea fuera del filtro.
2. Que una bodega NO clasificada siga contando. Excluir lo desconocido haria
   desaparecer stock real el dia que el ERP agregue un deposito.
3. Que con la tabla vacia no se filtre nada, en vez de dejar la lista en cero.
"""
import pytest

from src.models import BodegaTipo, PrecioProducto, StockUnificado
from src.services import precios_service


# --- La clave con la que se cruza ------------------------------------------------


@pytest.mark.parametrize("a,b", [
    ("CHILLAN 2", "CHILLAN2"),
    ("TALCA (2)", "TALCA(2)"),
    ("BODEGA DAÑADOS", "BODEGA DANADOS"),
    ("BODEGA DyP CURICO", "BODEGA DYP CURICO"),
    ("  LINDEROS  ", "LINDEROS"),
])
def test_las_dos_escrituras_dan_la_misma_clave(a, b):
    assert precios_service.clave_bodega(a) == precios_service.clave_bodega(b)


def test_bodegas_distintas_no_colisionan():
    assert precios_service.clave_bodega("TALCA") != precios_service.clave_bodega("TALCA 2")
    assert precios_service.clave_bodega("RANCAGUA") != precios_service.clave_bodega("ST_RANCAGUA")


def test_sin_nombre_no_revienta():
    assert precios_service.clave_bodega(None) == ""


# --- El filtro ------------------------------------------------------------------


def _stock(db, producto, bodega, unidades):
    db.add(StockUnificado(tenant_id="curifor", producto=producto, bodega=bodega,
                          sucursal_id="LINDEROS", stock=unidades))


def _tipo(db, bodega, tipo):
    db.add(BodegaTipo(tenant_id="curifor", bodega=bodega,
                      clave=precios_service.clave_bodega(bodega), tipo=tipo))


def test_el_stock_de_una_bodega_virtual_no_cuenta(db_session):
    _stock(db_session, "17 A", "LINDEROS", 5)
    _stock(db_session, "17 A", "BODEGA SCRAP", 90)
    _tipo(db_session, "LINDEROS", "REAL")
    _tipo(db_session, "BODEGA SCRAP", "VIRT")
    db_session.commit()

    stock, _ = precios_service._stock(db_session, ["17 A"])

    assert stock["17 A"] == 5


def test_un_producto_que_solo_esta_en_bodega_virtual_queda_sin_stock(db_session):
    """Los 436 del 08-09-2026: salian con precio como si estuvieran disponibles."""
    _stock(db_session, "17 SOLO-SCRAP", "BODEGA DAÑADOS", 20)
    _tipo(db_session, "BODEGA DAÑADOS", "VIRT")
    db_session.commit()

    stock, _ = precios_service._stock(db_session, ["17 SOLO-SCRAP"])

    assert stock.get("17 SOLO-SCRAP", 0) == 0


def test_la_bodega_eliminada_tampoco_cuenta(db_session):
    _stock(db_session, "17 A", "CASA MATRIZ", 12)
    _tipo(db_session, "CASA MATRIZ", "ELIM")
    db_session.commit()

    assert precios_service._stock(db_session, ["17 A"])[0].get("17 A", 0) == 0


def test_el_cruce_aguanta_la_otra_escritura(db_session):
    """El stock dice "CHILLAN 2" y el Excel de Abastecimiento "CHILLAN2"."""
    _stock(db_session, "17 A", "CHILLAN 2", 7)
    _tipo(db_session, "CHILLAN2", "VIRT")   # marcada virtual con el otro nombre
    db_session.commit()

    assert precios_service._stock(db_session, ["17 A"])[0].get("17 A", 0) == 0


def test_una_bodega_sin_clasificar_sigue_contando(db_session):
    """Excluir lo desconocido haria desaparecer stock real el dia que el ERP
    agregue un deposito nuevo. Se excluye solo lo marcado."""
    _stock(db_session, "17 A", "BODEGA NUEVA", 15)
    _tipo(db_session, "BODEGA SCRAP", "VIRT")
    db_session.commit()

    assert precios_service._stock(db_session, ["17 A"])[0]["17 A"] == 15


def test_sin_clasificacion_cargada_no_se_filtra_nada(db_session):
    """Con la tabla vacia la lista sigue como antes, no se queda sin stock."""
    _stock(db_session, "17 A", "BODEGA SCRAP", 30)
    db_session.commit()

    assert precios_service._stock(db_session, ["17 A"])[0]["17 A"] == 30


# --- La carga -------------------------------------------------------------------


def test_carga_y_reemplaza(db_session):
    precios_service.cargar_bodegas_tipo(db_session, [
        {"bodega": "LINDEROS", "tipo": "REAL"},
        {"bodega": "BODEGA SCRAP", "tipo": "VIRT"},
    ], usuario="x@curifor.com")

    r = precios_service.cargar_bodegas_tipo(db_session, [
        {"bodega": "LINDEROS", "tipo": "REAL"},
    ], usuario="x@curifor.com")

    assert r["bodegas"] == 1
    assert db_session.query(BodegaTipo).count() == 1


def test_las_dos_escrituras_no_crean_dos_filas(db_session):
    r = precios_service.cargar_bodegas_tipo(db_session, [
        {"bodega": "CHILLAN 2", "tipo": "REAL"},
        {"bodega": "CHILLAN2", "tipo": "REAL"},
    ], usuario=None)

    assert r["bodegas"] == 1


def test_un_tipo_mal_escrito_se_rechaza(db_session):
    """Guardarlo lo dejaria como "no real" -la exclusion es tipo != REAL- y una
    bodega fisica desapareceria del stock por un error de tipeo."""
    with pytest.raises(ValueError, match="no validos"):
        precios_service.cargar_bodegas_tipo(
            db_session, [{"bodega": "LINDEROS", "tipo": "REALL"}], usuario=None)

    assert db_session.query(BodegaTipo).count() == 0


def test_el_endpoint_de_carga_rechaza_el_tipo_malo(client, db_session):
    r = client.post("/api/admin/precios/bodegas-tipo",
                    json={"filas": [{"bodega": "X", "tipo": "FISICA"}]})

    assert r.status_code == 422
    assert "REAL" in r.json()["detail"]


def test_la_pantalla_puede_ver_la_clasificacion(client, db_session):
    _stock(db_session, "17 A", "LINDEROS", 5)
    _tipo(db_session, "LINDEROS", "REAL")
    _tipo(db_session, "BODEGA SCRAP", "VIRT")
    db_session.commit()

    r = client.get("/api/precios/bodegas")

    assert r.status_code == 200, r.text
    por_bodega = {b["bodega"]: b for b in r.json()}
    assert por_bodega["LINDEROS"]["tipo"] == "REAL"
    assert por_bodega["LINDEROS"]["con_stock"] is True
    # Saber cual esta clasificada pero ya no aparece con stock evita revisar
    # bodegas que no existen mas.
    assert por_bodega["BODEGA SCRAP"]["con_stock"] is False
