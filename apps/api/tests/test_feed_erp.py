"""La lista de precios se alimenta del export del ERP.

La lista nacio de un Excel y desde ahi nadie la alimentaba: un repuesto creado
en el ERP no existia para la plataforma, y "Precio ERP" quedo congelado en la
carga del 04-09-2026. Medido el 20-09-2026 con el export del 21-08: 371.355
codigos del ERP fuera de la lista, 114 con stock, 111 que pasan la regla.

Lo que estos tests cuidan:

1. Que ENTRE solo lo que pasa la regla: repuesto, con stock, rubro en la
   politica, no sacado a mano. El ERP trae 410 mil codigos y la lista tiene 39
   mil a proposito.
2. Que lo que YA esta solo reciba el precio ERP (y la glosa si faltaba). El costo
   y el stock los trae el motor de fuentes mejores; lo manual no se toca.
3. Que lo que una persona saco con clic derecho NO vuelva, y que lo que saco la
   depuracion masiva SI pueda volver si tiene stock.
"""
from src.models import PrecioBaja, PrecioOverride, PrecioProducto
from src.services import politica_precio_service as pol
from src.services import precios_service as svc

RUBROS = [{"rubro": "17", "tipo": "Liviano", "procedencia_forzada": None},
          {"rubro": "74", "tipo": "Liviano", "procedencia_forzada": None}]
FACT = [{"tipo": "Liviano", "procedencia": "Nacional", "factor": 1.78}]


def _politica(db):
    pol.sembrar(db, FACT, RUBROS)


def _erp(producto, stock=5, precio=1000, tipo="REPUESTOS", glosa="X", costo=500, proc="NACIONAL"):
    return {"producto": producto, "glosa": glosa, "stock": stock, "costo": costo,
            "precio_erp": precio, "tipo_erp": tipo, "procedencia": proc}


def _en_lista(db, producto, glosa="EN LISTA", precio_erp=900.0):
    db.add(PrecioProducto(tenant_id="curifor", producto=producto, glosa=glosa, rubro="17",
                          costo=500.0, precio_erp=precio_erp, stock=1.0, origen="maestro"))


# --- Que entra ------------------------------------------------------------------


def test_un_repuesto_nuevo_con_stock_entra(db_session):
    _politica(db_session)
    db_session.commit()

    r = svc.sincronizar_erp(db_session, [_erp("74 8880027CRV0000", stock=8, glosa="FILTRO DE POLEN")])

    assert r["creados"] == 1
    p = db_session.query(PrecioProducto).filter_by(producto="74 8880027CRV0000").one()
    assert p.origen == "erp"
    assert p.rubro == "74"
    assert p.glosa == "FILTRO DE POLEN"
    assert p.precio_erp == 1000
    assert p.stock == 8
    assert p.procedencia_maestro == "Nacional"   # normalizada como el resto de la lista


def test_sin_stock_no_entra(db_session):
    """Es la misma regla con la que se depuro la lista: sin stock no se precia."""
    _politica(db_session)
    db_session.commit()

    r = svc.sincronizar_erp(db_session, [_erp("17 NUEVO", stock=0)])

    assert r["creados"] == 0
    assert r["no_entran"] == {"sin stock": 1}


def test_un_servicio_no_entra_aunque_tenga_stock(db_session):
    _politica(db_session)
    db_session.commit()

    r = svc.sincronizar_erp(db_session, [_erp("17 TRAB DE TERCERO", tipo="MO_TERC")])

    assert r["no_entran"] == {"no es repuesto": 1}


def test_un_rubro_fuera_de_la_politica_no_entra(db_session):
    """Los rubros que se sacaron en agosto (cajas, ropa, servicios) no estan en
    la politica: asi no vuelven solos."""
    _politica(db_session)
    db_session.commit()

    r = svc.sincronizar_erp(db_session, [_erp("01 CAJA CARTON 1")])

    assert r["no_entran"] == {"rubro fuera de la politica": 1}


def test_un_codigo_sin_rubro_no_entra(db_session):
    """Los kits CU no traen rubro adelante y se borraron a proposito."""
    _politica(db_session)
    db_session.commit()

    r = svc.sincronizar_erp(db_session, [_erp("CUP0123")])

    assert r["no_entran"] == {"sin rubro": 1}


# --- Lo que ya esta -------------------------------------------------------------


def test_al_que_ya_esta_solo_se_le_actualiza_el_precio_erp(db_session):
    _politica(db_session)
    _en_lista(db_session, "17 A", precio_erp=900.0)
    db_session.commit()

    r = svc.sincronizar_erp(db_session, [_erp("17 A", stock=99, costo=1, precio=1234, glosa="OTRA GLOSA")])

    p = db_session.query(PrecioProducto).filter_by(producto="17 A").one()
    assert r["actualizados"] == 1 and r["creados"] == 0
    assert p.precio_erp == 1234
    assert p.stock == 1.0, "el stock lo trae el motor, no el ERP"
    assert p.costo == 500.0, "el costo lo trae el motor, no el ERP"
    assert p.glosa == "EN LISTA", "una glosa que ya existia no se pisa"


def test_la_glosa_vacia_si_se_rellena(db_session):
    _politica(db_session)
    _en_lista(db_session, "17 A", glosa=None)
    db_session.commit()

    svc.sincronizar_erp(db_session, [_erp("17 A", glosa="AMORTIGUADOR")])

    assert db_session.query(PrecioProducto).filter_by(producto="17 A").one().glosa == "AMORTIGUADOR"


def test_el_mismo_precio_no_cuenta_como_actualizado(db_session):
    _politica(db_session)
    _en_lista(db_session, "17 A", precio_erp=1000.0)
    db_session.commit()

    assert svc.sincronizar_erp(db_session, [_erp("17 A", precio=1000)])["actualizados"] == 0


def test_no_toca_lo_manual(db_session):
    _politica(db_session)
    _en_lista(db_session, "17 A")
    db_session.add(PrecioOverride(tenant_id="curifor", producto="17 A", precio_fijo=777.0, obs="piso"))
    db_session.commit()

    svc.sincronizar_erp(db_session, [_erp("17 A", precio=5555)])

    ov = db_session.query(PrecioOverride).filter_by(producto="17 A").one()
    assert ov.precio_fijo == 777.0


# --- Sacado a mano vs depuracion masiva -----------------------------------------


def test_lo_sacado_desde_la_pantalla_no_vuelve(db_session):
    _politica(db_session)
    _en_lista(db_session, "17 SERVICIO")
    db_session.commit()

    svc.eliminar(db_session, ["17 SERVICIO"], "fmora@curifor.com", proteger=True,
                 motivo="sacado desde la pantalla")
    r = svc.sincronizar_erp(db_session, [_erp("17 SERVICIO", stock=10)])

    assert r["creados"] == 0
    assert r["no_entran"] == {"sacado a mano": 1}
    baja = db_session.query(PrecioBaja).filter_by(producto="17 SERVICIO").one()
    assert baja.sacado_por == "fmora@curifor.com"


def test_lo_que_saco_la_depuracion_masiva_vuelve_si_tiene_stock(db_session):
    """Un producto sin stock ni venta que vuelve a tener stock tiene que volver:
    esa es la gracia del feed."""
    _politica(db_session)
    _en_lista(db_session, "17 DORMIDO")
    db_session.commit()

    svc.eliminar(db_session, ["17 DORMIDO"], "excel")          # sin proteger
    r = svc.sincronizar_erp(db_session, [_erp("17 DORMIDO", stock=3)])

    assert r["creados"] == 1
    assert db_session.query(PrecioBaja).filter_by(producto="17 DORMIDO").count() == 0


def test_sacar_dos_veces_no_duplica_la_marca(db_session):
    _politica(db_session)
    _en_lista(db_session, "17 A")
    db_session.commit()

    svc.eliminar(db_session, ["17 A"], "x", proteger=True)
    _en_lista(db_session, "17 A")
    db_session.commit()
    svc.eliminar(db_session, ["17 A"], "x", proteger=True)

    assert db_session.query(PrecioBaja).filter_by(producto="17 A").count() == 1


def test_la_pantalla_protege_y_el_admin_masivo_no(client, db_session):
    _politica(db_session)
    _en_lista(db_session, "17 PANTALLA")
    _en_lista(db_session, "17 MASIVO")
    db_session.commit()

    assert client.delete("/api/precios/17 PANTALLA").status_code == 200
    assert client.post("/api/admin/precios/eliminar",
                       json={"productos": ["17 MASIVO"]}).status_code == 200

    bajas = {b.producto for b in db_session.query(PrecioBaja).all()}
    assert bajas == {"17 PANTALLA"}


# --- El endpoint y el recalculo que sigue ----------------------------------------


def test_el_endpoint_crea_y_el_recalculo_le_pone_precio(client, db_session):
    _politica(db_session)
    db_session.commit()

    r = client.post("/api/admin/precios/erp",
                    json={"filas": [_erp("17 NUEVO", stock=4, costo=1000)]})
    assert r.status_code == 200, r.text
    assert r.json()["creados"] == 1

    svc.recalcular(db_session)

    p = db_session.query(PrecioProducto).filter_by(producto="17 NUEVO").one()
    assert p.estado == "OK"
    assert p.precio_final == 1780, "1000 x 1.78"


def test_el_endpoint_rechaza_un_payload_sin_filas(client, db_session):
    assert client.post("/api/admin/precios/erp", json={}).status_code == 400
