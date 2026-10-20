"""La lista de precios cuenta el stock de todas las bodegas menos las no disponibles.

El ERP mezcla bodegas fisicas con bodegas de proceso -danados, devolucion,
scrap, PE por regularizar, importacion-. Hasta el 20-10-2026 la lista solo
contaba las marcadas REAL, y eso dejaba sin precio a productos que SI se pueden
vender (PE X REGULARIZAR, COMEX, IMPORTACION MOTOS). La regla de Abastecimiento
es otra: cuenta todo MENOS danados, scrap y devolucion.

Desde entonces hay un cuarto tipo, `NODISP` (no disponible), y es el unico que
deja fuera el stock. REAL, VIRT y ELIM son etiquetas descriptivas. Como una
bodega nueva o mal escrita cuenta en silencio, hay ademas una red de seguridad
por nombre: una bodega VIRT o sin clasificar cuya clave diga DANADOS, SCRAP o
DEVOLUCION tampoco cuenta, y lo mismo la bodega SIN NOMBRE (el ERP no dice donde
esta ese stock).

Lo que estos tests cuidan:

1. Que el cruce aguante las dos escrituras del mismo deposito ("CHILLAN 2" y
   "CHILLAN2"). Comparando el texto crudo quedaban 1,4 millones de unidades sin
   clasificar, o sea fuera del filtro.
2. Que una bodega NO clasificada con un nombre cualquiera siga contando.
3. Que las TRES grafias de danados que trae el ERP queden fuera aunque la tabla
   no tenga una fila para cada una.
4. Que con la tabla vacia no se filtre nada, en vez de dejar la lista en cero.
5. Que la carga no pueda reponer danados por error (Excel viejo sin NODISP).
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


# --- La regla, sin base de datos --------------------------------------------------


@pytest.mark.parametrize("tipo,clave,cuenta", [
    # NODISP es lo unico que lo saca, venga como venga el nombre.
    ("NODISP", "LINDEROS", False),
    ("NODISP", "", False),
    # REAL y ELIM cuentan, y le ganan a la red de seguridad por nombre: asi el
    # dueno puede decidir lo contrario con una fila.
    ("REAL", "LINDEROS", True),
    ("REAL", "BODEGADEVOLUCION", True),
    ("REAL", "", True),
    ("ELIM", "CASAMATRIZ", True),
    ("ELIM", "BODEGASCRAP", True),
    # VIRT y sin clasificar cuentan, salvo por la red de seguridad.
    ("VIRT", "PEXREGULARIZAR", True),
    ("VIRT", "COMEX", True),
    ("VIRT", "IMPORTACIONMOTOS", True),
    ("VIRT", "PEFALTANTE", True),
    ("VIRT", "TALCA2DIFERENCIA", True),
    (None, "BODEGANUEVA", True),
    (None, "LINDEROS", True),
    # Las tres grafias de danados que trae el ERP: con N, con el mojibake de la N
    # (queda una A de mas) y la que perdio la letra ("DA?ADOS").
    ("VIRT", "BODEGADANADOS", False),
    ("VIRT", "BODEGADAAADOS", False),
    ("VIRT", "BODEGADAADOS", False),
    (None, "BODEGADANADOS", False),
    (None, "BODEGADAAADOS", False),
    (None, "BODEGADAADOS", False),
    ("VIRT", "BODEGADEVOLUCION", False),
    ("VIRT", "BODEGASCRAP", False),
    (None, "BODEGASCRAP", False),
    ("VIRT", "DEVOLUCIONESTALCA", False),
    # La bodega sin nombre: el ERP no dice donde esta ese stock.
    ("VIRT", "", False),
    (None, "", False),
])
def test_bodega_cuenta(tipo, clave, cuenta):
    assert precios_service.bodega_cuenta(tipo, clave) is cuenta


# --- El filtro ------------------------------------------------------------------


def _stock(db, producto, bodega, unidades, origen=None):
    db.add(StockUnificado(tenant_id="curifor", producto=producto, bodega=bodega,
                          sucursal_id="LINDEROS", stock=unidades, origen=origen))


def _tipo(db, bodega, tipo):
    db.add(BodegaTipo(tenant_id="curifor", bodega=bodega,
                      clave=precios_service.clave_bodega(bodega), tipo=tipo))


def _cuenta(db, producto):
    return precios_service._stock(db, [producto])[0].get(producto, 0)


def test_el_stock_de_una_bodega_no_disponible_no_cuenta(db_session):
    _stock(db_session, "17 A", "LINDEROS", 5)
    _stock(db_session, "17 A", "BODEGA SCRAP", 90)
    _tipo(db_session, "LINDEROS", "REAL")
    _tipo(db_session, "BODEGA SCRAP", "NODISP")
    db_session.commit()

    stock, _, _ = precios_service._stock(db_session, ["17 A"])

    assert stock["17 A"] == 5


def test_un_producto_que_solo_esta_en_bodega_no_disponible_queda_sin_stock(db_session):
    """Los 436 del 08-09-2026: salian con precio como si estuvieran disponibles."""
    _stock(db_session, "17 SOLO-SCRAP", "BODEGA DAÑADOS", 20)
    _tipo(db_session, "BODEGA DAÑADOS", "NODISP")
    db_session.commit()

    assert _cuenta(db_session, "17 SOLO-SCRAP") == 0


def test_la_bodega_eliminada_ahora_cuenta(db_session):
    """ELIM es una etiqueta: si todavia tiene stock, es stock que esta ahi."""
    _stock(db_session, "17 A", "CASA MATRIZ", 12)
    _tipo(db_session, "CASA MATRIZ", "ELIM")
    db_session.commit()

    assert _cuenta(db_session, "17 A") == 12


def test_el_cruce_aguanta_la_otra_escritura(db_session):
    """El stock dice "CHILLAN 2" y el Excel de Abastecimiento "CHILLAN2"."""
    _stock(db_session, "17 A", "CHILLAN 2", 7)
    _tipo(db_session, "CHILLAN2", "NODISP")   # marcada con el otro nombre
    db_session.commit()

    assert _cuenta(db_session, "17 A") == 0


def test_dyp_y_dyp_se_cruzan_igual(db_session):
    _stock(db_session, "17 A", "BODEGA DyP CURICO", 7)
    _tipo(db_session, "BODEGA DYP CURICO", "NODISP")
    db_session.commit()

    assert _cuenta(db_session, "17 A") == 0


@pytest.mark.parametrize("bodega", [
    "PE X REGULARIZAR", "COMEX", "IMPORTACION MOTOS", "PE-FALTANTE", "TALCA 2 DIFERENCIA",
])
def test_las_bodegas_virtuales_que_si_se_venden_cuentan(db_session, bodega):
    """Antes se perdian: 191 productos solo estaban en PE X REGULARIZAR y salian
    SIN STOCK aunque se podian vender."""
    _stock(db_session, "17 A", bodega, 9)
    _tipo(db_session, bodega, "VIRT")
    _tipo(db_session, "LINDEROS", "REAL")
    db_session.commit()

    assert _cuenta(db_session, "17 A") == 9


def test_un_producto_que_solo_esta_en_una_bodega_virtual_que_se_vende_sale_de_sin_stock(db_session):
    """De punta a punta: pasa por `recalcular` y recupera su estado."""
    db_session.add(PrecioProducto(tenant_id="curifor", producto="17 SOLO-PE",
                                  glosa="X", rubro="17", costo=1000.0, stock=0.0,
                                  estado="SIN STOCK", precio_final=0.0))
    _stock(db_session, "17 SOLO-PE", "PE X REGULARIZAR", 3)
    _stock(db_session, "17 OTRO", "LINDEROS", 4)
    _tipo(db_session, "PE X REGULARIZAR", "VIRT")
    _tipo(db_session, "LINDEROS", "REAL")
    _tipo(db_session, "BODEGA SCRAP", "NODISP")
    db_session.commit()

    precios_service.recalcular(db_session)

    p = db_session.query(PrecioProducto).filter_by(producto="17 SOLO-PE").one()
    assert p.stock == 3
    assert p.estado != "SIN STOCK"


def test_las_dos_grafias_de_danados_quedan_fuera_con_una_fila_cada_una(db_session):
    """"BODEGA DAÑADOS" (BODEGADANADOS) y "BODEGA DAÃ‘ADOS" (BODEGADAAADOS) son dos
    claves distintas: el ERP las trae las dos y cada una tiene su fila NODISP."""
    _stock(db_session, "17 A", "LINDEROS", 5)
    _stock(db_session, "17 A", "BODEGA DAÑADOS", 20)
    _stock(db_session, "17 A", "BODEGA DAÃ‘ADOS", 3)
    _tipo(db_session, "LINDEROS", "REAL")
    _tipo(db_session, "BODEGA DAÑADOS", "NODISP")
    _tipo(db_session, "BODEGA DAÃ‘ADOS", "NODISP")
    db_session.commit()

    assert precios_service.clave_bodega("BODEGA DAÃ‘ADOS") == "BODEGADAAADOS"
    assert _cuenta(db_session, "17 A") == 5


def test_devolucion_y_scrap_quedan_fuera_con_una_fila_nodisp_cada_una(db_session):
    _stock(db_session, "17 A", "LINDEROS", 5)
    _stock(db_session, "17 A", "BODEGA DEVOLUCION", 8)
    _stock(db_session, "17 A", "BODEGA SCRAP", 2)
    _tipo(db_session, "LINDEROS", "REAL")
    _tipo(db_session, "BODEGA DEVOLUCION", "NODISP")
    _tipo(db_session, "BODEGA SCRAP", "NODISP")
    db_session.commit()

    assert _cuenta(db_session, "17 A") == 5


@pytest.mark.parametrize("tipo", ["VIRT", None])
def test_la_tercera_grafia_de_danados_queda_fuera_por_el_nombre(db_session, tipo):
    """"DA?ADOS" (clave BODEGADAADOS) no tiene fila NODISP en produccion: la red de
    seguridad por nombre la saca aunque este VIRT o sin clasificar."""
    _stock(db_session, "17 A", "LINDEROS", 5)
    _stock(db_session, "17 A", "BODEGA DA?ADOS", 11)
    _tipo(db_session, "LINDEROS", "REAL")
    if tipo:
        _tipo(db_session, "BODEGA DA?ADOS", tipo)
    db_session.commit()

    assert precios_service.clave_bodega("BODEGA DA?ADOS") == "BODEGADAADOS"
    assert _cuenta(db_session, "17 A") == 5


def test_danados_virt_o_sin_clasificar_quedan_fuera_aunque_la_tabla_no_tenga_nodisp(db_session):
    """Si el arranque no alcanzo a sembrar NODISP (create_all puede fallar y el
    servidor lo tolera), o se recargo un Excel viejo, el nombre igual la saca."""
    _stock(db_session, "17 A", "LINDEROS", 5)
    _stock(db_session, "17 A", "BODEGA DAÑADOS", 20)      # VIRT
    _stock(db_session, "17 A", "BODEGA DEVOLUCION", 8)    # sin fila
    _tipo(db_session, "LINDEROS", "REAL")
    _tipo(db_session, "BODEGA DAÑADOS", "VIRT")
    db_session.commit()

    assert _cuenta(db_session, "17 A") == 5


def test_una_real_con_nombre_de_devolucion_cuenta(db_session):
    """El dueno puede decidir lo contrario con una fila: REAL le gana al nombre."""
    _stock(db_session, "17 A", "BODEGA DEVOLUCION", 8)
    _tipo(db_session, "BODEGA DEVOLUCION", "REAL")
    db_session.commit()

    assert _cuenta(db_session, "17 A") == 8


def test_una_bodega_sin_clasificar_con_un_nombre_cualquiera_sigue_contando(db_session):
    """Excluir lo desconocido haria desaparecer stock real el dia que el ERP
    agregue un deposito nuevo. Se excluye lo marcado y lo que dice danados, scrap
    o devolucion."""
    _stock(db_session, "17 A", "BODEGA NUEVA", 15)
    _tipo(db_session, "BODEGA SCRAP", "NODISP")
    db_session.commit()

    assert _cuenta(db_session, "17 A") == 15


def test_sin_clasificacion_cargada_no_se_filtra_nada(db_session):
    """Con la tabla vacia la lista sigue como antes, no se queda sin stock."""
    _stock(db_session, "17 A", "BODEGA SCRAP", 30)
    _stock(db_session, "17 A", None, 4)
    db_session.commit()

    assert _cuenta(db_session, "17 A") == 34
    assert precios_service.bodegas_excluidas(db_session) == set()


def test_una_tabla_sin_ninguna_nodisp_solo_excluye_por_nombre(db_session):
    """El dato intermedio (la tabla de antes de sembrar NODISP): REAL, ELIM y VIRT
    cuentan; solo el nombre saca a scrap."""
    _stock(db_session, "17 A", "LINDEROS", 5)
    _stock(db_session, "17 A", "CASA MATRIZ", 2)
    _stock(db_session, "17 A", "COMEX", 3)
    _stock(db_session, "17 A", "BODEGA SCRAP", 90)
    _tipo(db_session, "LINDEROS", "REAL")
    _tipo(db_session, "CASA MATRIZ", "ELIM")
    _tipo(db_session, "COMEX", "VIRT")
    _tipo(db_session, "BODEGA SCRAP", "VIRT")
    db_session.commit()

    assert _cuenta(db_session, "17 A") == 10


# --- La bodega sin nombre -------------------------------------------------------
#
# El ERP deja 53 filas de stock (345 unidades, 29 productos) sin bodega: nadie
# sabe donde estan. Mientras el responsable de Abastecimiento no confirme, NO
# cuentan. Si luego dice que si, se cambia con una fila (REAL), sin tocar codigo.


def _con_sin_nombre(db, tipo_de_la_fila):
    db.add(StockUnificado(tenant_id="curifor", producto="17 SIN-BODEGA",
                          bodega=None, sucursal_id="DESCONOCIDO", stock=6))
    _stock(db, "17 SIN-BODEGA", "LINDEROS", 4)
    _tipo(db, "LINDEROS", "REAL")
    if tipo_de_la_fila:
        _tipo(db, "", tipo_de_la_fila)
    db.commit()


@pytest.mark.parametrize("tipo", ["NODISP", "VIRT", None])
def test_el_stock_sin_bodega_no_cuenta(db_session, tipo):
    """NODISP es la siembra; VIRT es lo que traia la tabla antes; y sin fila
    (tabla con otras bodegas) lo saca la red de seguridad por la clave vacia."""
    _con_sin_nombre(db_session, tipo)

    assert _cuenta(db_session, "17 SIN-BODEGA") == 4


def test_el_stock_sin_bodega_cuenta_si_alguien_lo_marca_real(db_session):
    """El cambio de criterio es una fila de la tabla, no un deploy."""
    _con_sin_nombre(db_session, "REAL")

    assert _cuenta(db_session, "17 SIN-BODEGA") == 10


def test_la_bodega_vacia_y_la_nula_son_la_misma(db_session):
    """Hay filas con bodega NULL y filas con bodega '': las dos son sin nombre."""
    db_session.add(StockUnificado(tenant_id="curifor", producto="17 A", bodega="",
                                  sucursal_id="X", stock=6))
    db_session.add(StockUnificado(tenant_id="curifor", producto="17 A", bodega=None,
                                  sucursal_id="X", stock=7))
    _stock(db_session, "17 A", "LINDEROS", 4)
    _tipo(db_session, "LINDEROS", "REAL")
    _tipo(db_session, "", "NODISP")
    db_session.commit()

    assert _cuenta(db_session, "17 A") == 4


# --- El transito y Frontera no cambian -----------------------------------------------


def test_el_stock_de_frontera_sigue_sin_contar(db_session):
    _stock(db_session, "17 A", "COMEX", 9, origen="FRONTERA")
    _stock(db_session, "17 A", "COMEX", 2, origen="CURIFOR")
    _tipo(db_session, "COMEX", "VIRT")
    db_session.commit()

    assert _cuenta(db_session, "17 A") == 2


# --- La carga -------------------------------------------------------------------


def _nodisp(*nombres):
    return [{"bodega": n, "tipo": "NODISP"} for n in nombres]


def test_carga_y_reemplaza(db_session):
    precios_service.cargar_bodegas_tipo(db_session, [
        {"bodega": "LINDEROS", "tipo": "REAL"},
        {"bodega": "BODEGA SCRAP", "tipo": "NODISP"},
    ], usuario="x@curifor.com")

    r = precios_service.cargar_bodegas_tipo(db_session, [
        {"bodega": "LINDEROS", "tipo": "REAL"},
        *_nodisp("BODEGA SCRAP"),
    ], usuario="x@curifor.com")

    assert r["bodegas"] == 2
    assert db_session.query(BodegaTipo).count() == 2


def test_las_dos_escrituras_no_crean_dos_filas(db_session):
    r = precios_service.cargar_bodegas_tipo(db_session, [
        {"bodega": "CHILLAN 2", "tipo": "REAL"},
        {"bodega": "CHILLAN2", "tipo": "REAL"},
        *_nodisp("BODEGA SCRAP"),
    ], usuario=None)

    assert r["bodegas"] == 2


@pytest.mark.parametrize("alias", [
    "NODISP", "nodisp", "NO DISPONIBLE", "No Disponible", "no_disp", "NO-DISP", "NO DISP",
    " no disponible ", "NO DISPONIBLES",
])
def test_los_alias_de_no_disponible_se_guardan_como_nodisp(db_session, alias):
    r = precios_service.cargar_bodegas_tipo(db_session, [
        {"bodega": "BODEGA SCRAP", "tipo": alias},
    ], usuario=None)

    assert db_session.query(BodegaTipo).one().tipo == "NODISP"
    assert r["por_tipo"] == {"NODISP": 1}


def test_un_tipo_mal_escrito_se_rechaza(db_session):
    """Guardarlo lo dejaria sin tipo y una bodega fisica quedaria mal clasificada
    por un error de tipeo. El mensaje dice cuales son los tipos que existen."""
    with pytest.raises(ValueError, match="no validos") as e:
        precios_service.cargar_bodegas_tipo(
            db_session, [{"bodega": "LINDEROS", "tipo": "REALL"}], usuario=None)

    assert "NODISP" in str(e.value)
    assert db_session.query(BodegaTipo).count() == 0


def test_una_carga_sin_ninguna_nodisp_se_rechaza(db_session):
    """Recargar el Excel viejo (sin NODISP) volveria a contar danados y devolucion
    sin que nadie lo note."""
    _tipo(db_session, "BODEGA SCRAP", "NODISP")
    db_session.commit()

    with pytest.raises(ValueError, match="NODISP"):
        precios_service.cargar_bodegas_tipo(db_session, [
            {"bodega": "LINDEROS", "tipo": "REAL"},
            {"bodega": "BODEGA DAÑADOS", "tipo": "VIRT"},
        ], usuario="x@curifor.com")

    # No toco nada: la tabla sigue como estaba.
    assert [(b.bodega, b.tipo) for b in db_session.query(BodegaTipo).all()] == [
        ("BODEGA SCRAP", "NODISP")]


def test_sin_no_disponibles_deja_cargar_una_tabla_sin_nodisp(db_session):
    r = precios_service.cargar_bodegas_tipo(db_session, [
        {"bodega": "LINDEROS", "tipo": "REAL"},
        {"bodega": "BODEGA DAÑADOS", "tipo": "VIRT"},
    ], usuario="x@curifor.com", sin_no_disponibles=True)

    assert r["bodegas"] == 2
    assert r["no_disponibles"] == []


def test_la_carga_guarda_quien_la_hizo(db_session):
    precios_service.cargar_bodegas_tipo(
        db_session, [{"bodega": "LINDEROS", "tipo": "REAL"}, *_nodisp("BODEGA SCRAP")],
        usuario="admin@curifor.com")

    assert {b.actualizado_por for b in db_session.query(BodegaTipo).all()} == {"admin@curifor.com"}


def test_la_respuesta_nombra_las_no_disponibles_y_las_sin_clasificar_con_stock(db_session):
    _stock(db_session, "17 A", "LINDEROS", 5)
    _stock(db_session, "17 A", "BODEGA RARA", 1)                    # sin fila
    _stock(db_session, "17 B", "BODEGA DEL SUR", 1, origen="FRONTERA")  # solo Frontera: no avisa
    db_session.add(StockUnificado(tenant_id="curifor", producto="17 C", bodega=None,
                                  sucursal_id="X", stock=2))        # sin nombre y sin fila
    db_session.commit()

    r = precios_service.cargar_bodegas_tipo(db_session, [
        {"bodega": "LINDEROS", "tipo": "REAL"},
        *_nodisp("BODEGA SCRAP", "BODEGA DAÑADOS"),
    ], usuario=None)

    assert r["bodegas"] == 3
    assert r["por_tipo"] == {"REAL": 1, "NODISP": 2}
    assert r["no_disponibles"] == ["BODEGA DAÑADOS", "BODEGA SCRAP"]
    assert r["sin_clasificar_con_stock"] == ["(sin nombre)", "BODEGA RARA"]


def test_la_respuesta_no_avisa_de_la_bodega_sin_nombre_si_la_carga_la_trae(db_session):
    db_session.add(StockUnificado(tenant_id="curifor", producto="17 C", bodega=None,
                                  sucursal_id="X", stock=2))
    db_session.commit()

    r = precios_service.cargar_bodegas_tipo(db_session, [
        {"bodega": "", "tipo": "NODISP"},
    ], usuario=None)

    assert r["no_disponibles"] == ["(sin nombre)"]
    assert r["sin_clasificar_con_stock"] == []


def test_el_endpoint_de_carga_rechaza_el_tipo_malo(client, db_session):
    r = client.post("/api/admin/precios/bodegas-tipo",
                    json={"filas": [{"bodega": "X", "tipo": "FISICA"}]})

    assert r.status_code == 422
    assert "REAL" in r.json()["detail"]
    assert "NODISP" in r.json()["detail"]


def test_el_endpoint_rechaza_una_carga_sin_nodisp(client, db_session):
    r = client.post("/api/admin/precios/bodegas-tipo",
                    json={"filas": [{"bodega": "LINDEROS", "tipo": "REAL"}]})

    assert r.status_code == 422
    assert "NODISP" in r.json()["detail"]
    assert db_session.query(BodegaTipo).count() == 0


def test_el_endpoint_deja_cargar_sin_nodisp_si_se_pide(client, db_session):
    r = client.post("/api/admin/precios/bodegas-tipo", json={
        "filas": [{"bodega": "LINDEROS", "tipo": "REAL"}], "sin_no_disponibles": True})

    assert r.status_code == 200, r.text
    assert r.json()["bodegas"] == 1


def test_el_endpoint_guarda_el_email_del_admin_y_acepta_alias(client, db_session):
    r = client.post("/api/admin/precios/bodegas-tipo", json={"filas": [
        {"bodega": "LINDEROS", "tipo": "REAL"},
        {"bodega": "BODEGA SCRAP", "tipo": "NO DISPONIBLE"},
    ]})

    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["no_disponibles"] == ["BODEGA SCRAP"]
    assert cuerpo["sin_clasificar_con_stock"] == []
    assert {b.actualizado_por for b in db_session.query(BodegaTipo).all()} == {"test@curifor.com"}


# --- Lo que se ve en pantalla -------------------------------------------------------


def test_la_pantalla_puede_ver_la_clasificacion(client, db_session):
    _stock(db_session, "17 A", "LINDEROS", 5)
    _tipo(db_session, "LINDEROS", "REAL")
    _tipo(db_session, "BODEGA SCRAP", "NODISP")
    _tipo(db_session, "PE X REGULARIZAR", "VIRT")
    db_session.commit()

    r = client.get("/api/precios/bodegas")

    assert r.status_code == 200, r.text
    por_bodega = {b["bodega"]: b for b in r.json()}
    assert por_bodega["LINDEROS"]["tipo"] == "REAL"
    assert por_bodega["LINDEROS"]["con_stock"] is True
    assert por_bodega["LINDEROS"]["cuenta"] is True
    # Saber cual esta clasificada pero ya no aparece con stock evita revisar
    # bodegas que no existen mas.
    assert por_bodega["BODEGA SCRAP"]["con_stock"] is False
    assert por_bodega["BODEGA SCRAP"]["cuenta"] is False
    # La virtual que se vende cuenta: la pantalla tiene que poder decirlo.
    assert por_bodega["PE X REGULARIZAR"]["tipo"] == "VIRT"
    assert por_bodega["PE X REGULARIZAR"]["cuenta"] is True
    assert all(b["sin_clasificar"] is False for b in por_bodega.values())


def test_la_pantalla_lista_las_bodegas_con_stock_que_nadie_clasifico(client, db_session):
    _stock(db_session, "17 A", "LINDEROS", 5)
    _stock(db_session, "17 A", "BODEGA NUEVA", 3)
    _stock(db_session, "17 A", "BODEGA DEVOLUCION", 3)       # sin fila: la saca el nombre
    _stock(db_session, "17 A", "BODEGA DE FRONTERA", 3, origen="FRONTERA")
    db_session.add(StockUnificado(tenant_id="curifor", producto="17 B", bodega=None,
                                  sucursal_id="X", stock=2))
    _tipo(db_session, "LINDEROS", "REAL")
    db_session.commit()

    filas = client.get("/api/precios/bodegas").json()

    sin = {b["bodega"]: b for b in filas if b["sin_clasificar"]}
    assert set(sin) == {"BODEGA NUEVA", "BODEGA DEVOLUCION", ""}
    assert sin["BODEGA NUEVA"] == {
        "bodega": "BODEGA NUEVA", "tipo": None, "con_stock": True,
        "actualizado_por": None, "sin_clasificar": True, "cuenta": True}
    assert sin["BODEGA DEVOLUCION"]["cuenta"] is False
    assert sin[""]["cuenta"] is False


def test_la_ficha_muestra_de_que_bodegas_sale_el_stock(client, db_session):
    db_session.add(PrecioProducto(tenant_id="curifor", producto="17 FICHA", glosa="X",
                                  rubro="17", costo=1000.0, stock=15.0))
    _stock(db_session, "17 FICHA", "LINDEROS", 12)
    _stock(db_session, "17 FICHA", "PE X REGULARIZAR", 3)
    _stock(db_session, "17 FICHA", "BODEGA DAÑADOS", 1)
    _stock(db_session, "17 FICHA", "COMEX", 40, origen="FRONTERA")   # no es de Curifor
    _stock(db_session, "17 FICHA", "TALCA", 0)                        # sin stock: no sale
    db_session.add(StockUnificado(tenant_id="curifor", producto="17 FICHA", bodega=None,
                                  sucursal_id="X", stock=2))
    _tipo(db_session, "LINDEROS", "REAL")
    _tipo(db_session, "PE X REGULARIZAR", "VIRT")
    _tipo(db_session, "BODEGA DAÑADOS", "NODISP")
    db_session.commit()

    r = client.get("/api/precios/17 FICHA")

    assert r.status_code == 200, r.text
    assert r.json()["stock_bodegas"] == [
        {"bodega": "LINDEROS", "stock": 12.0, "cuenta": True},
        {"bodega": "PE X REGULARIZAR", "stock": 3.0, "cuenta": True},
        {"bodega": "(sin nombre)", "stock": 2.0, "cuenta": False},
        {"bodega": "BODEGA DAÑADOS", "stock": 1.0, "cuenta": False},
    ]


def test_la_ficha_con_la_tabla_de_bodegas_vacia_dice_que_todo_cuenta(client, db_session):
    db_session.add(PrecioProducto(tenant_id="curifor", producto="17 FICHA", glosa="X",
                                  rubro="17", costo=1000.0, stock=15.0))
    _stock(db_session, "17 FICHA", "BODEGA SCRAP", 4)
    db_session.commit()

    r = client.get("/api/precios/17 FICHA")

    assert r.json()["stock_bodegas"] == [{"bodega": "BODEGA SCRAP", "stock": 4.0, "cuenta": True}]


def test_la_ficha_de_un_producto_sin_stock_trae_la_lista_vacia(client, db_session):
    db_session.add(PrecioProducto(tenant_id="curifor", producto="17 NADA", glosa="X",
                                  rubro="17", costo=1000.0, stock=0.0))
    db_session.commit()

    r = client.get("/api/precios/17 NADA")

    assert r.status_code == 200, r.text
    assert r.json()["stock_bodegas"] == []


# --- El stock que se quedaba pegado ---------------------------------------------
#
# El motor publica `stock_unificado` SIN filas en cero, asi que un producto que se
# agota DESAPARECE de la tabla. `recalcular` solo pisaba el stock "si el producto
# aparece", o sea que el agotado conservaba el stock del dia que lo tuvo: la regla
# "stock 0 -> precio 0" no se disparaba nunca y salia al ERP con precio.
#
# Eran 758 productos. Y ademas dejaba sin efecto el filtro de bodegas: los 436
# que solo tenian stock en danados o scrap desaparecian de la consulta filtrada y
# por lo tanto conservaban su stock viejo.


def test_lo_que_desaparece_del_stock_pasa_a_cero(db_session):
    """El caso del producto que se agoto: ya no esta en la tabla de stock."""
    db_session.add(PrecioProducto(tenant_id="curifor", producto="17 AGOTADO",
                                  glosa="X", rubro="17", costo=1000.0, stock=12.0))
    _stock(db_session, "17 OTRO", "LINDEROS", 4)   # la tabla tiene datos
    db_session.commit()

    precios_service.recalcular(db_session)

    p = db_session.query(PrecioProducto).filter_by(producto="17 AGOTADO").one()
    assert p.stock == 0
    assert p.estado == "SIN STOCK"
    assert p.precio_final == 0


def test_con_la_tabla_de_stock_vacia_no_se_pisa_nada(db_session):
    """Es el caso de la primera carga del Excel, antes de que el motor publique.
    Ahi vaciar el stock dejaria la lista entera en precio 0."""
    db_session.add(PrecioProducto(tenant_id="curifor", producto="17 DEL-EXCEL",
                                  glosa="X", rubro="17", costo=1000.0, stock=9.0))
    db_session.commit()

    precios_service.recalcular(db_session)

    assert db_session.query(PrecioProducto).filter_by(producto="17 DEL-EXCEL").one().stock == 9


def test_el_filtro_de_bodegas_llega_hasta_el_precio(db_session):
    """Los dos arreglos juntos: es lo que se pidio de punta a punta."""
    db_session.add(PrecioProducto(tenant_id="curifor", producto="61 FAC208",
                                  glosa="X", rubro="61", costo=1000.0, stock=81.0))
    _stock(db_session, "61 FAC208", "BODEGA DAÑADOS", 81)
    _stock(db_session, "17 OTRO", "LINDEROS", 4)
    _tipo(db_session, "BODEGA DAÑADOS", "NODISP")
    _tipo(db_session, "LINDEROS", "REAL")
    db_session.commit()

    precios_service.recalcular(db_session)

    p = db_session.query(PrecioProducto).filter_by(producto="61 FAC208").one()
    assert p.stock == 0, "las 81 unidades estan en una bodega que no vende"
    assert p.estado == "SIN STOCK"


def test_el_transito_salva_al_que_no_tiene_stock(db_session):
    """Sin stock pero con algo en camino NO es precio 0."""
    from src.models import StockTransito

    db_session.add(PrecioProducto(tenant_id="curifor", producto="17 EN-CAMINO",
                                  glosa="X", rubro="17", costo=1000.0, stock=0.0))
    db_session.add(StockTransito(tenant_id="curifor", producto="17 EN-CAMINO", cantidad=5))
    _stock(db_session, "17 OTRO", "LINDEROS", 4)
    db_session.commit()

    precios_service.recalcular(db_session)

    p = db_session.query(PrecioProducto).filter_by(producto="17 EN-CAMINO").one()
    assert p.stock_transito == 5
    assert p.estado != "SIN STOCK"
