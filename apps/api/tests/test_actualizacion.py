"""El buzon del boton "Actualizar ahora" (web <-> agente que corre el motor)."""
from datetime import datetime, timedelta, timezone

import pytest

from src.main import app
from src.models import SolicitudActualizacion
from src.routers import actualizacion as router_actualizacion
from src.services.auth import requiere_auth

SECRETO = "secreto-de-prueba"


@pytest.fixture()
def agente(monkeypatch):
    """Habilita al agente. Sin AGENTE_SECRET configurado sus endpoints rechazan todo."""
    monkeypatch.setattr(router_actualizacion.settings, "agente_secret", SECRETO)
    return {"X-Agente-Secret": SECRETO}


def test_sin_solicitudes_el_estado_viene_vacio(client):
    r = client.get("/api/actualizacion/estado")
    assert r.status_code == 200
    assert r.json()["estado"] is None


def test_ciclo_completo_pedir_tomar_y_terminar(client, agente):
    pedido = client.post("/api/actualizacion/solicitar").json()
    assert pedido["estado"] == "pendiente"
    assert pedido["ya_en_curso"] is False

    tomada = client.get("/api/actualizacion/pendiente?agente=PC-JEFA", headers=agente).json()
    assert tomada["hay"] is True
    assert tomada["id"] == pedido["id"]
    # Ya tomada, deja de estar disponible para el siguiente ciclo del agente.
    assert client.get("/api/actualizacion/pendiente", headers=agente).json() == {"hay": False}
    assert client.get("/api/actualizacion/estado").json()["estado"] == "en_curso"

    client.post(
        "/api/actualizacion/terminar",
        json={"id": tomada["id"], "ok": True, "mensaje": "Listo: 18.869 filas."},
        headers=agente,
    )
    estado = client.get("/api/actualizacion/estado").json()
    assert estado["estado"] == "ok"
    assert estado["mensaje"] == "Listo: 18.869 filas."


def test_el_error_del_motor_llega_a_la_web(client, agente):
    pedido = client.post("/api/actualizacion/solicitar").json()
    client.get("/api/actualizacion/pendiente", headers=agente)
    client.post(
        "/api/actualizacion/terminar",
        json={"id": pedido["id"], "ok": False, "mensaje": "Falta el Excel de stock."},
        headers=agente,
    )
    estado = client.get("/api/actualizacion/estado").json()
    assert estado["estado"] == "error"
    assert estado["mensaje"] == "Falta el Excel de stock."


def test_apretar_dos_veces_no_encola_dos_corridas(client, db_session):
    """Dos corridas del motor encoladas publicarian dos veces. La segunda recibe un
    409 con un motivo que se puede mostrar tal cual."""
    primera = client.post("/api/actualizacion/solicitar")
    assert primera.status_code == 200
    segunda = client.post("/api/actualizacion/solicitar")
    assert segunda.status_code == 409
    assert "Ya hay un recálculo" in segunda.json()["detail"]
    assert "Tarda entre 25 y 40 minutos" in segunda.json()["detail"]
    assert db_session.query(SolicitudActualizacion).count() == 1


def test_una_solicitud_que_nadie_tomo_caduca_con_un_motivo(client, db_session):
    """Con el PC apagado nadie la toma. Si quedara "pendiente" para siempre, la tarjeta
    giraria sin fin y ademas bloquearia el proximo intento."""
    client.post("/api/actualizacion/solicitar")
    s = db_session.query(SolicitudActualizacion).one()
    s.creado_en = datetime.now(timezone.utc) - timedelta(minutes=10)
    db_session.commit()

    estado = client.get("/api/actualizacion/estado").json()
    assert estado["estado"] == "expirada"
    assert "apagado" in (estado["mensaje"] or "")
    # Y con la anterior cerrada, se puede volver a pedir.
    assert client.post("/api/actualizacion/solicitar").json()["ya_en_curso"] is False


def test_una_corrida_que_nunca_reporto_no_queda_colgada(client, agente, db_session):
    pedido = client.post("/api/actualizacion/solicitar").json()
    client.get("/api/actualizacion/pendiente", headers=agente)
    s = db_session.get(SolicitudActualizacion, pedido["id"])
    s.tomado_en = datetime.now(timezone.utc) - timedelta(minutes=80)
    db_session.commit()

    estado = client.get("/api/actualizacion/estado").json()
    assert estado["estado"] == "error"
    assert "75 minutos" in estado["mensaje"]


def test_el_agente_sin_el_secreto_no_ve_ni_toca_nada(client, agente):
    client.post("/api/actualizacion/solicitar")
    assert client.get("/api/actualizacion/pendiente").status_code == 403
    assert client.get(
        "/api/actualizacion/pendiente", headers={"X-Agente-Secret": "otro"}
    ).status_code == 403


def test_sin_agente_secret_configurado_los_endpoints_del_agente_estan_cerrados(client):
    """Por defecto la clave viene vacia: no debe equivaler a "sin cabecera vale"."""
    assert client.get(
        "/api/actualizacion/pendiente", headers={"X-Agente-Secret": ""}
    ).status_code == 403


def test_un_usuario_cualquiera_no_puede_republicar_los_datos(client):
    """Recalcular cambia lo que ve todo el equipo: solo admin o los emails de
    EMAILS_ACTUALIZAR. Pero mirar el estado si lo puede hacer cualquiera."""
    app.dependency_overrides[requiere_auth] = lambda: "noadmin@curifor.com"
    try:
        assert client.post("/api/actualizacion/solicitar").status_code == 403
        r = client.get("/api/actualizacion/estado")
        assert r.status_code == 200
        assert r.json()["puede_actualizar"] is False
    finally:
        app.dependency_overrides[requiere_auth] = lambda: "test@curifor.com"


def test_un_email_autorizado_sin_ser_admin_si_puede(client, monkeypatch):
    monkeypatch.setattr(
        router_actualizacion.settings, "emails_actualizar", "noadmin@curifor.com"
    )
    monkeypatch.setattr(
        "src.services.auth.settings.emails_actualizar", "noadmin@curifor.com"
    )
    app.dependency_overrides[requiere_auth] = lambda: "noadmin@curifor.com"
    try:
        assert client.post("/api/actualizacion/solicitar").status_code == 200
    finally:
        app.dependency_overrides[requiere_auth] = lambda: "test@curifor.com"


# ------------------------- tipo "actualizar_motor" ------------------------- #
def _pedir(client, tipo: str | None = None):
    if tipo is None:
        return client.post("/api/actualizacion/solicitar")
    return client.post("/api/actualizacion/solicitar", json={"tipo": tipo})


def test_sin_cuerpo_es_recalcular_como_antes(client, agente):
    """La web de antes no manda cuerpo: tiene que seguir pidiendo un recalculo."""
    pedido = _pedir(client).json()
    assert pedido["tipo"] == "recalcular"
    tomada = client.get("/api/actualizacion/pendiente", headers=agente).json()
    assert tomada["tipo"] == "recalcular"
    assert client.get("/api/actualizacion/estado").json()["tipo"] == "recalcular"


def test_cuerpo_vacio_o_sin_tipo_tambien_es_recalcular(client, agente):
    r = client.post(
        "/api/actualizacion/solicitar", headers={"Content-Type": "application/json"}
    )
    assert r.status_code == 200
    assert r.json()["tipo"] == "recalcular"
    client.get("/api/actualizacion/pendiente", headers=agente)
    client.post(
        "/api/actualizacion/terminar", json={"id": r.json()["id"], "ok": True}, headers=agente
    )
    r = client.post("/api/actualizacion/solicitar", json={})
    assert r.status_code == 200
    assert r.json()["tipo"] == "recalcular"


def test_ciclo_de_actualizar_el_motor_con_su_version(client, agente):
    pedido = _pedir(client, "actualizar_motor")
    assert pedido.status_code == 200
    assert pedido.json()["tipo"] == "actualizar_motor"

    tomada = client.get("/api/actualizacion/pendiente?agente=PC-MOTOR", headers=agente).json()
    assert tomada == {
        "hay": True, "id": pedido.json()["id"], "tipo": "actualizar_motor",
        "solicitado_por": "test@curifor.com",
    }
    r = client.post(
        "/api/actualizacion/terminar",
        json={"id": tomada["id"], "ok": True, "version": "a1b2c3d arreglar-job-diario",
              "mensaje": "Motor actualizado de 9f8e7d6 a a1b2c3d (3 cambios)"},
        headers=agente,
    )
    assert r.status_code == 200
    estado = client.get("/api/actualizacion/estado").json()
    assert estado["estado"] == "ok"
    assert estado["tipo"] == "actualizar_motor"
    assert estado["version"] == "a1b2c3d arreglar-job-diario"
    assert estado["mensaje"] == "Motor actualizado de 9f8e7d6 a a1b2c3d (3 cambios)"


def test_terminar_sin_version_sigue_sirviendo(client, agente):
    """El agente que recalcula no manda version: no puede romperse por eso."""
    pedido = _pedir(client).json()
    client.get("/api/actualizacion/pendiente", headers=agente)
    r = client.post(
        "/api/actualizacion/terminar",
        json={"id": pedido["id"], "ok": True, "mensaje": "Se publicaron 18.252 filas."},
        headers=agente,
    )
    assert r.status_code == 200
    assert client.get("/api/actualizacion/estado").json()["version"] is None


def test_actualizar_el_motor_es_solo_para_admin(client, monkeypatch, db_session):
    """Estar autorizado a recalcular no alcanza: actualizar el motor cambia el
    programa que calcula para todo el equipo."""
    monkeypatch.setattr(
        router_actualizacion.settings, "emails_actualizar", "noadmin@curifor.com"
    )
    app.dependency_overrides[requiere_auth] = lambda: "noadmin@curifor.com"
    try:
        r = _pedir(client, "actualizar_motor")
        assert r.status_code == 403
        assert "administradores" in r.json()["detail"]
        assert _pedir(client, "recalcular").status_code == 200
    finally:
        app.dependency_overrides[requiere_auth] = lambda: "test@curifor.com"
    assert db_session.query(SolicitudActualizacion).count() == 1


def test_un_tipo_que_no_existe_se_rechaza(client, db_session):
    assert _pedir(client, "borrar_todo").status_code == 422
    assert db_session.query(SolicitudActualizacion).count() == 0


@pytest.mark.parametrize(
    ("primero", "segundo", "frase"),
    [
        ("recalcular", "actualizar_motor", "Ya hay un recálculo"),
        ("actualizar_motor", "recalcular", "Ya hay una actualización del motor"),
        ("actualizar_motor", "actualizar_motor", "Ya hay una actualización del motor"),
    ],
)
def test_nunca_hay_dos_solicitudes_vivas_de_ningun_tipo(
    client, db_session, primero, segundo, frase
):
    """Actualizar el motor mientras calcula le cambiaria el programa a mitad de
    camino, y recalcular mientras se actualiza correria una version a medio bajar."""
    assert _pedir(client, primero).status_code == 200
    r = _pedir(client, segundo)
    assert r.status_code == 409
    assert frase in r.json()["detail"]
    assert db_session.query(SolicitudActualizacion).count() == 1


def test_dos_clics_simultaneos_dejan_una_sola_solicitud(client, db_session, monkeypatch):
    """Cada pedido corre en su hilo: los dos pueden pasar el control antes de que el
    otro guarde. Se simula dejando que el primer control no vea a la otra."""
    otra = SolicitudActualizacion(
        tenant_id="curifor", estado="pendiente", tipo="recalcular",
        solicitado_por="otra@curifor.com",
        creado_en=datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    db_session.add(otra)
    db_session.commit()
    real = router_actualizacion._vivas
    llamadas = {"n": 0}

    def _vivas_con_carrera(db):
        llamadas["n"] += 1
        return [] if llamadas["n"] == 1 else real(db)

    monkeypatch.setattr(router_actualizacion, "_vivas", _vivas_con_carrera)
    r = _pedir(client, "actualizar_motor")
    assert r.status_code == 409
    vivas = db_session.query(SolicitudActualizacion).all()
    assert [s.id for s in vivas] == [otra.id]


def test_el_409_dice_si_el_pedido_ya_lo_tomo_el_pc(client, agente):
    _pedir(client, "actualizar_motor")
    assert "esperando al computador" in _pedir(client).json()["detail"]
    client.get("/api/actualizacion/pendiente", headers=agente)
    detalle = _pedir(client).json()["detail"]
    assert "en curso (pedida a las " in detalle
    assert "Tarda 1 a 2 minutos" in detalle


def test_terminada_la_anterior_se_puede_pedir_otra(client, agente):
    pedido = _pedir(client, "actualizar_motor").json()
    client.get("/api/actualizacion/pendiente", headers=agente)
    client.post(
        "/api/actualizacion/terminar",
        json={"id": pedido["id"], "ok": True, "mensaje": "El motor ya estaba al dia (a1b2c3d)"},
        headers=agente,
    )
    assert _pedir(client).status_code == 200


def test_un_recalculo_de_45_minutos_sigue_en_curso(client, agente, db_session):
    """El motor tarda 22 a 35 minutos: con el plazo viejo de 20 una corrida sana se
    daba por muerta a la mitad."""
    pedido = _pedir(client).json()
    client.get("/api/actualizacion/pendiente", headers=agente)
    s = db_session.get(SolicitudActualizacion, pedido["id"])
    s.tomado_en = datetime.now(timezone.utc) - timedelta(minutes=45)
    db_session.commit()
    assert client.get("/api/actualizacion/estado").json()["estado"] == "en_curso"


def test_una_actualizacion_del_motor_colgada_caduca_a_los_15_minutos(
    client, agente, db_session
):
    pedido = _pedir(client, "actualizar_motor").json()
    client.get("/api/actualizacion/pendiente", headers=agente)
    s = db_session.get(SolicitudActualizacion, pedido["id"])
    s.tomado_en = datetime.now(timezone.utc) - timedelta(minutes=14)
    db_session.commit()
    assert client.get("/api/actualizacion/estado").json()["estado"] == "en_curso"

    s.tomado_en = datetime.now(timezone.utc) - timedelta(minutes=16)
    db_session.commit()
    estado = client.get("/api/actualizacion/estado").json()
    assert estado["estado"] == "error"
    assert "motor" in estado["mensaje"]
    # Cerrada la colgada, el boton vuelve a funcionar.
    assert _pedir(client).status_code == 200


def test_una_actualizacion_del_motor_que_nadie_tomo_caduca(client, db_session):
    _pedir(client, "actualizar_motor")
    s = db_session.query(SolicitudActualizacion).one()
    s.creado_en = datetime.now(timezone.utc) - timedelta(minutes=6)
    db_session.commit()
    estado = client.get("/api/actualizacion/estado").json()
    assert estado["estado"] == "expirada"
    assert "sesión iniciada" in estado["mensaje"]


def test_la_migracion_agrega_tipo_y_version_a_la_tabla_de_antes(monkeypatch):
    """La tabla de produccion ya existe sin las dos columnas: `create_all()` no las
    agrega solo, y sin `tipo` el buzon entero se caeria. Las filas viejas quedan como
    recalcular, que era lo unico que se pedia."""
    from sqlalchemy import create_engine, inspect, text
    from sqlalchemy.pool import StaticPool

    from src import db as db_modulo

    eng = create_engine("sqlite://", connect_args={"check_same_thread": False},
                        poolclass=StaticPool)
    with eng.begin() as cx:
        cx.execute(text(
            "CREATE TABLE solicitud_actualizacion (id VARCHAR PRIMARY KEY, "
            "tenant_id VARCHAR NOT NULL, estado VARCHAR NOT NULL, solicitado_por VARCHAR, "
            "agente VARCHAR, mensaje TEXT, creado_en TIMESTAMP, tomado_en TIMESTAMP, "
            "terminado_en TIMESTAMP)"
        ))
        cx.execute(text(
            "INSERT INTO solicitud_actualizacion (id, tenant_id, estado) "
            "VALUES ('vieja', 'curifor', 'ok')"
        ))
    monkeypatch.setattr(db_modulo, "engine", eng)
    db_modulo.create_all()

    columnas = {c["name"] for c in inspect(eng).get_columns("solicitud_actualizacion")}
    assert {"tipo", "version"} <= columnas
    with eng.connect() as cx:
        assert cx.execute(
            text("SELECT tipo FROM solicitud_actualizacion WHERE id = 'vieja'")
        ).scalar() == "recalcular"
