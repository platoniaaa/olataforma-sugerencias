"""Tests del modo 'mantener nivel de stock' en las sugerencias manuales.

A diferencia de los otros dos modos (que SUMAN sobre el sugerido), este apunta a
un nivel final: pide solo la brecha que falta, descontando lo que hay, lo que
viene en transito y lo que el sistema ya esta sugiriendo.
"""
from datetime import date

from src.models import Sugerido, SugerenciaManual, SugerenciaRecurrente
from src.services import recurrentes_service, sugerido_service


def _sug(db_session, **kw):
    base = dict(
        tenant_id="curifor", sucursal_id="LINDEROS", nombre_sucursal="Linderos",
        pedir="Si", stock_activo_suc=0, stock_en_transito_suc=0, total_sugerido_suc=0,
    )
    base.update(kw)
    s = Sugerido(**base)
    db_session.add(s)
    db_session.commit()
    return s


def test_pide_solo_la_brecha(client, db_session):
    """Stock 5, quiero 20, el sistema no pide nada -> faltan 15."""
    _sug(db_session, producto="OBJ-1", stock_activo_suc=5)
    r = client.post("/api/sugerencias-manuales", json={
        "producto": "OBJ-1", "sucursal_id": "LINDEROS", "stock_objetivo": 20,
    })
    assert r.status_code == 201
    assert r.json()["unidades"] == 15


def test_descuenta_el_transito(client, db_session):
    """Si vienen 8 en camino, no hay que volver a pedirlas."""
    _sug(db_session, producto="OBJ-2", stock_activo_suc=5, stock_en_transito_suc=8)
    r = client.post("/api/sugerencias-manuales", json={
        "producto": "OBJ-2", "sucursal_id": "LINDEROS", "stock_objetivo": 20,
    })
    assert r.json()["unidades"] == 7


def test_descuenta_lo_que_el_sistema_ya_sugiere(client, db_session):
    """Sin esto la manual se sumaria encima y se compraria dos veces el nivel."""
    _sug(db_session, producto="OBJ-3", stock_activo_suc=5, total_sugerido_suc=10)
    r = client.post("/api/sugerencias-manuales", json={
        "producto": "OBJ-3", "sucursal_id": "LINDEROS", "stock_objetivo": 20,
    })
    assert r.json()["unidades"] == 5


def test_nivel_ya_cubierto_no_crea_nada(client, db_session):
    """Responde 409 con un mensaje claro en vez de crear una sugerencia de 0."""
    _sug(db_session, producto="OBJ-4", stock_activo_suc=30)
    r = client.post("/api/sugerencias-manuales", json={
        "producto": "OBJ-4", "sucursal_id": "LINDEROS", "stock_objetivo": 20,
    })
    assert r.status_code == 409
    assert "ya esta cubierto" in r.json()["detail"]


def test_producto_inexistente_avisa(client):
    r = client.post("/api/sugerencias-manuales", json={
        "producto": "NO-EXISTE", "sucursal_id": "LINDEROS", "stock_objetivo": 20,
    })
    assert r.status_code == 400


def test_masiva_omite_los_que_ya_estan_en_nivel(client, db_session):
    _sug(db_session, producto="MAS-BAJO", stock_activo_suc=2)
    _sug(db_session, producto="MAS-OK", stock_activo_suc=50)
    r = client.post("/api/sugerencias-manuales/masiva", json={
        "filtros": {"q": "MAS-", "solo_pedir": False}, "stock_objetivo": 10,
    })
    assert r.status_code == 201
    assert r.json()["creadas"] == 1
    assert r.json()["omitidas"] == 1

    creada = db_session.query(SugerenciaManual).filter_by(producto="MAS-BAJO").one()
    assert creada.unidades == 8


def test_recurrente_recalcula_contra_el_stock_del_momento(client, db_session):
    """El corazon de la mantencion automatica: si se vendio, repone; si no, no pide."""
    s = _sug(db_session, producto="REC-1", stock_activo_suc=4)
    rec = client.post("/api/sugerencias-manuales/recurrentes", json={
        "modo": "individual", "producto": "REC-1", "sucursal_id": "LINDEROS",
        "stock_objetivo": 10, "cada_dias": 7,
    })
    assert rec.status_code == 201
    # Primera ejecucion: faltan 6.
    inst = db_session.query(SugerenciaManual).filter_by(producto="REC-1", archivada=False).one()
    assert inst.unidades == 6

    # Llega la reposicion: el stock sube a 10. La siguiente ejecucion no pide nada.
    s.stock_activo_suc = 10
    db_session.commit()
    regla = db_session.query(SugerenciaRecurrente).filter_by(producto="REC-1").one()
    regla.proxima_ejecucion = date.today()
    db_session.commit()
    recurrentes_service.procesar(db_session, hoy=date.today())
    vigentes = db_session.query(SugerenciaManual).filter_by(
        producto="REC-1", archivada=False
    ).all()
    assert vigentes == []

    # Se vende y el stock baja a 3: vuelve a pedir la diferencia.
    s.stock_activo_suc = 3
    db_session.commit()
    regla.proxima_ejecucion = date.today()
    db_session.commit()
    recurrentes_service.procesar(db_session, hoy=date.today())
    inst2 = db_session.query(SugerenciaManual).filter_by(producto="REC-1", archivada=False).one()
    assert inst2.unidades == 7


def test_recurrente_guarda_el_objetivo(client, db_session):
    r = client.post("/api/sugerencias-manuales/recurrentes", json={
        "modo": "individual", "producto": "REC-2", "sucursal_id": "LINDEROS",
        "stock_objetivo": 15, "cada_dias": 7,
    })
    assert r.json()["stock_objetivo"] == 15


def test_recurrente_por_grupo(client, db_session):
    _sug(db_session, producto="GRP-1", stock_activo_suc=1)
    _sug(db_session, producto="GRP-2", stock_activo_suc=1)
    r = client.post("/api/sugerencias-manuales/recurrentes", json={
        "modo": "grupo", "filtros": {"q": "GRP-", "solo_pedir": False},
        "stock_objetivo": 5, "cada_dias": 7,
    })
    assert r.status_code == 201
    creadas = db_session.query(SugerenciaManual).filter(
        SugerenciaManual.producto.in_(["GRP-1", "GRP-2"])
    ).all()
    assert {c.unidades for c in creadas} == {4}


def test_sin_ningun_modo_falla(client, db_session):
    _sug(db_session, producto="X-1")
    r = client.post("/api/sugerencias-manuales", json={
        "producto": "X-1", "sucursal_id": "LINDEROS",
    })
    assert r.status_code == 400


def test_calculo_directo_del_helper(db_session):
    _sug(db_session, producto="H-1", stock_activo_suc=2, stock_en_transito_suc=1,
         total_sugerido_suc=3)
    assert sugerido_service.unidades_para_objetivo(db_session, "H-1", "LINDEROS", 10) == 4
    # Nivel cubierto -> 0 (no None: el par existe).
    assert sugerido_service.unidades_para_objetivo(db_session, "H-1", "LINDEROS", 5) == 0
    # Par inexistente -> None.
    assert sugerido_service.unidades_para_objetivo(db_session, "H-1", "TALCA", 10) is None
