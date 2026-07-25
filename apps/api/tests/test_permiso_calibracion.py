"""Calibracion: admin o autorizado de Abastecimiento (no cualquier usuario).

El caso real: Mary (mramos@) es duena del modelo pero NO es admin de la
plataforma. Debe poder ver y aplicar la calibracion sin darle el resto de los
poderes de admin (cargar datos, comparar motor, etc.).
"""
import pytest

from src.main import app
from src.models import Usuario
from src.services.auth import hash_password, requiere_auth

MARY = "mramos@curifor.com"


@pytest.fixture()
def como(client, db_session):
    """Permite ejecutar peticiones como un email cualquiera."""
    def _como(email: str):
        app.dependency_overrides[requiere_auth] = lambda: email
    yield _como
    app.dependency_overrides[requiere_auth] = lambda: "test@curifor.com"


def _crear(db, email, *, admin=False):
    db.add(Usuario(email=email, password_hash=hash_password("123456"),
                   nombre=email, es_admin=admin))
    db.commit()


def test_mary_puede_ver_y_aplicar_la_calibracion(client, db_session, como):
    _crear(db_session, MARY)
    como(MARY)

    assert client.get("/api/calibracion/config-modelo").status_code == 200
    r = client.put("/api/calibracion/config-modelo",
                   json={"ciclo_orden_dias_cd": 6, "nota": "prueba Mary"})
    assert r.status_code == 200
    assert r.json()["ciclo_orden_dias_cd"] == 6
    # Queda registrado a su nombre, no como "admin".
    assert r.json()["creado_por"] == MARY
    assert client.get("/api/calibracion/config-modelo/historial").status_code == 200
    assert client.get("/api/calibracion/lead-time-proveedor").status_code == 200


def test_mary_no_gana_los_demas_poderes_de_admin(client, db_session, como):
    """El permiso es acotado: sigue sin poder cargar datos ni ver el motor."""
    _crear(db_session, MARY)
    como(MARY)
    assert client.get("/api/admin/motor/comparaciones").status_code == 403
    assert client.get("/api/admin/config-modelo").status_code == 403


def test_un_usuario_cualquiera_no_puede_calibrar(client, db_session, como):
    _crear(db_session, "otro@curifor.com")
    como("otro@curifor.com")
    assert client.get("/api/calibracion/config-modelo").status_code == 403
    assert client.put("/api/calibracion/config-modelo",
                      json={"ciclo_orden_dias_cd": 9}).status_code == 403


def test_el_admin_sigue_pudiendo(client):
    assert client.get("/api/calibracion/config-modelo").status_code == 200
    assert client.put("/api/calibracion/config-modelo",
                      json={"ciclo_orden_dias_cd": 7}).status_code == 200


def test_el_login_dice_si_puede_calibrar(client, db_session):
    """El frontend usa este flag para mostrar la seccion; la lista no se duplica."""
    _crear(db_session, MARY)
    _crear(db_session, "otro2@curifor.com")

    r = client.post("/api/auth/login", json={"email": MARY, "password": "123456"})
    assert r.status_code == 200 and r.json()["puede_calibrar"] is True
    assert r.json()["es_admin"] is False  # no se le dio admin

    r = client.post("/api/auth/login", json={"email": "otro2@curifor.com", "password": "123456"})
    assert r.json()["puede_calibrar"] is False

    r = client.post("/api/auth/login", json={"email": "test@curifor.com", "password": "123456"})
    assert r.json()["puede_calibrar"] is True  # admin siempre
