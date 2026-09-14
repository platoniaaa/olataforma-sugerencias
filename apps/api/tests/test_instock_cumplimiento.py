"""% de cumplimiento InStock del mes.

El compromiso InStock es "nunca menos de N unidades" de cada repuesto de pauta
en las 4 sucursales con taller. El tablero lo media como "dias en cero", que
deja pasar el repuesto con 1 unidad y minimo 2, y ademas la foto diaria solo
guardaba filas con actividad: un repuesto de pauta en cero y sin sugerido
-justo el caso que hay que ver- no quedaba en la foto.

Lo que estos tests cuidan:

1. Que se mida contra el MINIMO, no contra cero.
2. Que la foto guarde SIEMPRE las posiciones InStock, con su minimo, aunque
   esten en cero y sin sugerido, y aunque no esten en el sugerido.
3. Que lo que no tiene fila en la foto salga como "sin dato" y no como cumplido
   ni incumplido.
4. Que los peores sean los que mas dias pasaron bajo el minimo.
"""
from datetime import date

from src.models import RepuestoInstock, StockUnificado, Sugerido, SugeridoSnapshot
from src.services import snapshot_service, tablero_service


def _instock(db, producto, minimo=2):
    db.add(RepuestoInstock(tenant_id="curifor", producto=producto, minimo=minimo,
                           activo=True, origen="pauta"))


def _foto(db, fecha, producto, sucursal, stock, minimo=None):
    db.add(SugeridoSnapshot(tenant_id="curifor", fecha=fecha, producto=producto,
                            sucursal_id=sucursal, stock_activo_suc=stock,
                            instock_minimo=minimo))


def _sug(db, producto, sucursal, stock, sugerido=0.0, punto=0):
    db.add(Sugerido(tenant_id="curifor", producto=producto, sucursal_id=sucursal,
                    nombre_sucursal=sucursal, stock_activo_suc=stock,
                    total_sugerido_suc=sugerido, punto_de_pedido=punto, pedir="No"))


D1, D2 = date(2026, 9, 1), date(2026, 9, 2)


# --- Se mide contra el minimo -----------------------------------------------------


def test_una_unidad_con_minimo_dos_incumple(db_session):
    _instock(db_session, "17 PAUTA", minimo=2)
    _foto(db_session, D1, "17 PAUTA", "LINDEROS", stock=1, minimo=2)
    _foto(db_session, D1, "17 PAUTA", "RANCAGUA", stock=2, minimo=2)
    _foto(db_session, D1, "17 PAUTA", "CURICO", stock=5, minimo=2)
    _foto(db_session, D1, "17 PAUTA", "CHILLAN", stock=0, minimo=2)
    db_session.commit()

    r = tablero_service._instock(db_session, D1, D1)

    assert r["cumplen"] == 2 and r["incumplen"] == 2
    assert r["pct"] == 50.0
    assert r["sin_dato"] == 0


def test_la_foto_vieja_sin_minimo_usa_el_vigente(db_session):
    """Las fotos anteriores a septiembre 2026 no traen el minimo."""
    _instock(db_session, "17 PAUTA", minimo=3)
    for s in ("LINDEROS", "RANCAGUA", "CURICO", "CHILLAN"):
        _foto(db_session, D1, "17 PAUTA", s, stock=2, minimo=None)
    db_session.commit()

    r = tablero_service._instock(db_session, D1, D1)

    assert r["incumplen"] == 4, "2 unidades con minimo 3 es incumplir"


def test_solo_cuentan_las_sucursales_con_taller(db_session):
    _instock(db_session, "17 PAUTA")
    for s in ("LINDEROS", "RANCAGUA", "CURICO", "CHILLAN"):
        _foto(db_session, D1, "17 PAUTA", s, stock=9, minimo=2)
    _foto(db_session, D1, "17 PAUTA", "TALCA", stock=0, minimo=None)   # sin taller
    db_session.commit()

    r = tablero_service._instock(db_session, D1, D1)

    assert r["pct"] == 100.0
    assert r["posiciones"] == 4


# --- Sin dato no es cumplido ni incumplido --------------------------------------


def test_lo_que_no_esta_en_la_foto_es_sin_dato(db_session):
    _instock(db_session, "17 PAUTA")
    _foto(db_session, D1, "17 PAUTA", "LINDEROS", stock=9, minimo=2)
    # Las otras 3 sucursales no tienen fila ese dia.
    db_session.commit()

    r = tablero_service._instock(db_session, D1, D1)

    assert r["cumplen"] == 1 and r["incumplen"] == 0
    assert r["sin_dato"] == 3
    assert r["pct"] == 100.0, "el porcentaje es sobre lo que si se sabe"


def test_sin_fotos_no_hay_porcentaje(db_session):
    _instock(db_session, "17 PAUTA")
    db_session.commit()

    r = tablero_service._instock(db_session, D1, D1)

    assert r["disponible"] is False
    assert r["pct"] is None


# --- Los peores -------------------------------------------------------------------


def test_los_peores_son_los_que_mas_dias_pasaron_bajo_el_minimo(db_session):
    _instock(db_session, "17 MAL")
    _instock(db_session, "17 BIEN")
    for d in (D1, D2):
        _foto(db_session, d, "17 MAL", "LINDEROS", stock=0, minimo=2)
        _foto(db_session, d, "17 BIEN", "LINDEROS", stock=5, minimo=2)
    _foto(db_session, D1, "17 BIEN", "CURICO", stock=1, minimo=2)
    db_session.commit()

    r = tablero_service._instock(db_session, D1, D2)

    assert r["peores"][0] == {"producto": "17 MAL", "sucursal_id": "LINDEROS",
                              "dias_bajo_minimo": 2, "minimo": 2, "marca": None}
    assert r["peores"][1]["producto"] == "17 BIEN"
    assert r["peores"][1]["dias_bajo_minimo"] == 1


# --- La foto cubre siempre las posiciones InStock --------------------------------


def test_la_foto_guarda_el_repuesto_de_pauta_en_cero_y_sin_sugerido(db_session):
    """El caso que el filtro de actividad dejaba fuera."""
    _instock(db_session, "17 PAUTA", minimo=2)
    _sug(db_session, "17 PAUTA", "LINDEROS", stock=0, sugerido=0, punto=0)
    # Una fila normal con actividad, para que la foto tenga algo que guardar.
    _sug(db_session, "17 OTRO", "TALCA", stock=4)
    db_session.commit()

    n = snapshot_service.guardar_snapshot(db_session, D1)

    fila = db_session.query(SugeridoSnapshot).filter_by(
        producto="17 PAUTA", sucursal_id="LINDEROS").one()
    assert fila.stock_activo_suc == 0
    assert fila.instock_minimo == 2
    assert n >= 2


def test_la_foto_fabrica_la_posicion_que_no_esta_en_el_sugerido(db_session):
    """Repuesto de pauta sin venta en 12 meses en esa sucursal: el sugerido no lo
    tiene, pero el stock real si existe."""
    _instock(db_session, "17 PAUTA", minimo=2)
    _sug(db_session, "17 OTRO", "TALCA", stock=4)
    db_session.add(StockUnificado(tenant_id="curifor", producto="17 PAUTA",
                                  bodega="CURICO", sucursal_id="CURICO", stock=3))
    db_session.commit()

    snapshot_service.guardar_snapshot(db_session, D1)

    por_suc = {f.sucursal_id: f for f in db_session.query(SugeridoSnapshot)
               .filter_by(producto="17 PAUTA").all()}
    assert set(por_suc) == {"LINDEROS", "RANCAGUA", "CURICO", "CHILLAN"}
    assert por_suc["CURICO"].stock_activo_suc == 3
    assert por_suc["LINDEROS"].stock_activo_suc == 0
    assert all(f.instock_minimo == 2 for f in por_suc.values())


def test_la_fila_normal_con_actividad_gana_el_minimo_si_es_de_pauta(db_session):
    _instock(db_session, "17 PAUTA", minimo=4)
    _sug(db_session, "17 PAUTA", "RANCAGUA", stock=10)
    db_session.commit()

    snapshot_service.guardar_snapshot(db_session, D1)

    fila = db_session.query(SugeridoSnapshot).filter_by(
        producto="17 PAUTA", sucursal_id="RANCAGUA").one()
    assert fila.instock_minimo == 4
    assert fila.stock_activo_suc == 10


def test_las_filas_que_no_son_de_pauta_quedan_sin_minimo(db_session):
    _instock(db_session, "17 PAUTA")
    _sug(db_session, "17 NORMAL", "LINDEROS", stock=7)
    db_session.commit()

    snapshot_service.guardar_snapshot(db_session, D1)

    assert db_session.query(SugeridoSnapshot).filter_by(
        producto="17 NORMAL").one().instock_minimo is None


# --- De punta a punta: la foto de hoy alimenta el KPI ---------------------------


def test_de_la_foto_al_porcentaje(client, db_session):
    _instock(db_session, "17 PAUTA", minimo=2)
    _sug(db_session, "17 PAUTA", "LINDEROS", stock=0)
    _sug(db_session, "17 PAUTA", "RANCAGUA", stock=1)
    _sug(db_session, "17 PAUTA", "CURICO", stock=2)
    _sug(db_session, "17 PAUTA", "CHILLAN", stock=8)
    db_session.commit()
    snapshot_service.guardar_snapshot(db_session, date.today())

    r = client.get("/api/tablero")

    assert r.status_code == 200, r.text
    i = r.json()["instock"]
    assert i["disponible"] is True
    assert i["cumplen"] == 2 and i["incumplen"] == 2
    assert i["pct"] == 50.0
    assert i["sin_dato"] == 0
    assert len(i["tendencia"]) == 6
    assert i["tendencia"][-1]["pct"] == 50.0


# --- Volver a tomar la foto de hoy ------------------------------------------------


def test_el_admin_puede_retomar_la_foto_de_hoy(client, db_session):
    _instock(db_session, "17 PAUTA", minimo=2)
    _sug(db_session, "17 PAUTA", "LINDEROS", stock=0)
    db_session.commit()

    r = client.post("/api/admin/snapshot")

    assert r.status_code == 200, r.text
    assert r.json()["filas"] >= 4
    assert db_session.query(SugeridoSnapshot).filter_by(
        producto="17 PAUTA", sucursal_id="CHILLAN").one().instock_minimo == 2


def test_retomar_dos_veces_no_duplica(client, db_session):
    _instock(db_session, "17 PAUTA", minimo=2)
    _sug(db_session, "17 PAUTA", "LINDEROS", stock=3)
    db_session.commit()

    client.post("/api/admin/snapshot")
    client.post("/api/admin/snapshot")

    assert db_session.query(SugeridoSnapshot).filter_by(
        producto="17 PAUTA", sucursal_id="LINDEROS").count() == 1
