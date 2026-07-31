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


def test_apretar_dos_veces_no_encola_dos_corridas(client):
    primera = client.post("/api/actualizacion/solicitar").json()
    segunda = client.post("/api/actualizacion/solicitar").json()
    assert segunda["ya_en_curso"] is True
    assert segunda["id"] == primera["id"]


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
    s.tomado_en = datetime.now(timezone.utc) - timedelta(minutes=45)
    db_session.commit()

    assert client.get("/api/actualizacion/estado").json()["estado"] == "error"


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
