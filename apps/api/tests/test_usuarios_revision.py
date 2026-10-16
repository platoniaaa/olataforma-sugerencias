"""Revision de seguridad de la pantalla de Usuarios (16-10-2026).

La pantalla convierte en rutina cosas que antes hacia una sola persona por la
API: crear cuentas, desactivar a quien se va, cambiar claves. Cada test de aca
corresponde a un hueco que la revision encontro probandolo:

1. "Crear usuario" con un correo que ya existe pisaba esa cuenta (clave, roles,
   sucursales), incluida la del motor. Ahora el alta puede pedir `solo_crear` y
   el servidor responde 409 si el correo ya tiene cuenta.
2. Un admin desactivado seguia siendo admin con la sesion que tenia abierta
   (hasta `token_horas`): podia reactivarse y desactivar a quien lo desactivo.
3. La cuenta del motor marcada como vendedor deja de publicar compras y precios
   (`requiere_comprador` le responde 403).
4. Un admin que se marca vendedor pierde Abastecimiento y el menu de admin.
5. "Solo lectura" bloquea lo que la pantalla dice que bloquea.
6. Las sucursales para asignar no dependen de las que tiene el admin que mira.
"""
import json

import pytest

from src.main import app
from src.models import DimSucursal, Usuario
from src.routers import usuarios as router_usuarios
from src.services.auth import crear_token, requiere_auth, verify_password


@pytest.fixture()
def motor(monkeypatch):
    """La cuenta del motor con un correo ficticio: admin, con clave y una sucursal."""
    monkeypatch.setattr(router_usuarios.settings, "emails_motor", "publicador@ejemplo.cl")
    return "publicador@ejemplo.cl"


def _crear(client, email: str, headers: dict | None = None, **extra):
    r = client.post("/api/admin/usuarios", headers=headers,
                    json={"email": email, "password": "clave1234", **extra})
    assert r.status_code == 200, r.text[:200]
    return r.json()


@pytest.fixture()
def con_token(client):
    """Las peticiones pasan por la autenticacion de verdad (token firmado), no por el
    atajo de los tests. Devuelve el header para cada correo."""
    app.dependency_overrides.pop(requiere_auth, None)
    yield lambda email: {"Authorization": f"Bearer {crear_token(email)}"}
    app.dependency_overrides[requiere_auth] = lambda: "test@curifor.com"


# --------------------------- 1. alta que no pisa --------------------------- #
def test_el_alta_estricta_no_pisa_una_cuenta_que_ya_existe(client, db_session, motor):
    _crear(client, motor, nombre="Motor", es_admin=True, sucursales=["LINDEROS"])

    r = client.post("/api/admin/usuarios", json={
        "email": " Publicador@Ejemplo.cl ", "password": "otra1234", "nombre": "",
        "es_admin": False, "solo_lectura": False, "es_vendedor": False, "sucursales": [],
        "solo_crear": True,
    })

    assert r.status_code == 409, r.text[:200]
    assert "Ya existe un usuario con ese correo" in r.json()["detail"]
    db_session.expire_all()
    u = db_session.get(Usuario, motor)
    assert u.es_admin is True
    assert u.nombre == "Motor"
    assert json.loads(u.sucursales_permitidas) == ["LINDEROS"]
    assert verify_password("clave1234", u.password_hash)
    assert not verify_password("otra1234", u.password_hash)


def test_el_alta_estricta_con_un_correo_nuevo_crea(client, db_session):
    r = client.post("/api/admin/usuarios", json={
        "email": "nueva@ejemplo.cl", "password": "clave1234", "solo_crear": True,
    })
    assert r.status_code == 200, r.text[:200]
    assert db_session.get(Usuario, "nueva@ejemplo.cl") is not None


def test_sin_solo_crear_el_post_sigue_siendo_idempotente(client, db_session):
    """scripts/clave_usuario.py cambia claves con este mismo POST: no se rompe."""
    _crear(client, "persona@ejemplo.cl")
    r = client.post("/api/admin/usuarios", json={"email": "persona@ejemplo.cl", "password": "otra1234"})
    assert r.status_code == 200
    db_session.expire_all()
    assert verify_password("otra1234", db_session.get(Usuario, "persona@ejemplo.cl").password_hash)


# --------------------------- 2. sesion de un desactivado --------------------------- #
def test_un_admin_desactivado_queda_afuera_aunque_tenga_la_sesion_abierta(
    client, db_session, con_token,
):
    _crear(client, "otroadmin@ejemplo.cl", headers=con_token("test@curifor.com"), es_admin=True)
    sesion_vieja = con_token("otroadmin@ejemplo.cl")
    assert client.get("/api/admin/usuarios", headers=sesion_vieja).status_code == 200

    r = client.post("/api/admin/usuarios", headers=con_token("test@curifor.com"),
                    json={"email": "otroadmin@ejemplo.cl", "activo": False})
    assert r.status_code == 200 and r.json()["activo"] is False

    # Con el token que ya tenia: no lista, no se reactiva, no desactiva a nadie.
    assert client.get("/api/admin/usuarios", headers=sesion_vieja).status_code == 401
    assert client.post("/api/admin/usuarios", headers=sesion_vieja,
                       json={"email": "otroadmin@ejemplo.cl", "activo": True}).status_code == 401
    assert client.post("/api/admin/usuarios", headers=sesion_vieja,
                       json={"email": "test@curifor.com", "activo": False}).status_code == 401
    assert client.get("/api/auth/me", headers=sesion_vieja).status_code == 401
    db_session.expire_all()
    assert db_session.get(Usuario, "otroadmin@ejemplo.cl").activo is False
    assert db_session.get(Usuario, "test@curifor.com").activo is True


def test_un_usuario_desactivado_tampoco_entra_al_resto(client, db_session, con_token):
    """No es solo /usuarios: cualquier ruta protegida lo deja afuera."""
    _crear(client, "persona@ejemplo.cl", headers=con_token("test@curifor.com"))
    sesion = con_token("persona@ejemplo.cl")
    assert client.get("/api/sucursales", headers=sesion).status_code == 200
    client.post("/api/admin/usuarios", headers=con_token("test@curifor.com"),
                json={"email": "persona@ejemplo.cl", "activo": False})
    r = client.get("/api/sucursales", headers=sesion)
    assert r.status_code == 401
    assert "desactivada" in r.json()["detail"]


def test_un_token_de_un_correo_que_no_existe_no_sirve(client, db_session, con_token):
    assert client.get("/api/sucursales", headers=con_token("nadie@ejemplo.cl")).status_code == 401


def test_requiere_admin_tambien_mira_si_esta_activo(client, db_session):
    """Defensa doble: aunque alguien salte requiere_auth (como hacen los tests)."""
    _crear(client, "otroadmin@ejemplo.cl", es_admin=True)
    client.post("/api/admin/usuarios", json={"email": "otroadmin@ejemplo.cl", "activo": False})
    app.dependency_overrides[requiere_auth] = lambda: "otroadmin@ejemplo.cl"
    try:
        assert client.get("/api/admin/usuarios").status_code == 403
    finally:
        app.dependency_overrides[requiere_auth] = lambda: "test@curifor.com"


def test_las_reglas_dicen_cuanto_dura_una_sesion(client, db_session):
    """La pantalla avisa que cambiar la clave no corta una sesion ya abierta."""
    r = client.get("/api/admin/usuarios/reglas")
    assert r.json()["horas_sesion"] == router_usuarios.settings.token_horas


# --------------------------- 3. motor como vendedor --------------------------- #
def test_la_cuenta_del_motor_no_puede_ser_vendedor(client, db_session, motor):
    _crear(client, motor, es_admin=True)
    r = client.post("/api/admin/usuarios", json={
        "email": motor, "es_vendedor": True, "sucursales": ["LINDEROS"],
    })
    assert r.status_code == 400, r.text[:200]
    assert "motor" in r.json()["detail"]
    db_session.expire_all()
    u = db_session.get(Usuario, motor)
    assert u.es_vendedor is False
    assert u.sucursales_permitidas is None


# --------------------------- 4. admin vendedor de si mismo --------------------------- #
def test_un_admin_no_puede_marcarse_vendedor_a_si_mismo(client, db_session):
    r = client.post("/api/admin/usuarios", json={
        "email": "test@curifor.com", "es_vendedor": True, "sucursales": ["LINDEROS"],
    })
    assert r.status_code == 400, r.text[:200]
    db_session.expire_all()
    assert db_session.get(Usuario, "test@curifor.com").es_vendedor is False


def test_un_admin_si_puede_marcar_vendedor_a_otro(client, db_session):
    _crear(client, "persona@ejemplo.cl")
    r = client.post("/api/admin/usuarios", json={
        "email": "persona@ejemplo.cl", "es_vendedor": True, "sucursales": ["LINDEROS"],
    })
    assert r.status_code == 200


# --------------------------- 5. lo que bloquea solo lectura --------------------------- #
def test_solo_lectura_bloquea_sugerencias_pedidos_e_instock(client, db_session):
    """Lo que promete la pantalla. Si alguien saca `requiere_escritura` de una de
    estas rutas, el texto de "Solo lectura" pasa a mentir."""
    _crear(client, "lectura@ejemplo.cl", solo_lectura=True)
    app.dependency_overrides[requiere_auth] = lambda: "lectura@ejemplo.cl"
    try:
        sugerencia = client.post("/api/sugerencias-manuales", json={
            "producto": "20 BXO5W30AA", "sucursal_id": "LINDEROS", "unidades": 1,
        })
        pedido = client.post("/api/compras/pedidos", json={
            "producto": "20 BXO5W30AA", "sucursal_id": "LINDEROS", "unidades": 1,
        })
        instock = client.post("/api/instock", json={"producto": "20 BXO5W30AA"})
    finally:
        app.dependency_overrides[requiere_auth] = lambda: "test@curifor.com"
    assert (sugerencia.status_code, pedido.status_code, instock.status_code) == (403, 403, 403)


# --------------------------- 6. sucursales para asignar --------------------------- #
def test_las_sucursales_para_asignar_no_dependen_de_las_del_admin(client, db_session):
    db_session.add(DimSucursal(sucursal_id="CURICO", tenant_id="curifor", nombre="Curicó"))
    db_session.get(Usuario, "test@curifor.com").sucursales_permitidas = json.dumps(["LINDEROS"])
    db_session.commit()

    # La lista general sigue filtrada por las sucursales de quien mira...
    assert [s["sucursal_id"] for s in client.get("/api/sucursales").json()] == ["LINDEROS"]
    # ...pero para asignarle sucursales a otro usuario se necesitan todas.
    r = client.get("/api/admin/usuarios/sucursales")
    assert r.status_code == 200
    assert sorted(s["sucursal_id"] for s in r.json()) == ["CURICO", "LINDEROS"]


def test_las_sucursales_para_asignar_son_solo_para_admin(client, db_session):
    app.dependency_overrides[requiere_auth] = lambda: "noadmin@curifor.com"
    try:
        assert client.get("/api/admin/usuarios/sucursales").status_code == 403
    finally:
        app.dependency_overrides[requiere_auth] = lambda: "test@curifor.com"
