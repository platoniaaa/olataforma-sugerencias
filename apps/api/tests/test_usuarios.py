"""Administracion de usuarios desde la plataforma.

Existe porque hasta ahora crear un usuario exigia acceso directo a Supabase, y
eso dejo la vista de vendedor desplegada pero inerte: no habia forma de crear un
vendedor. Lo que se prueba aca es sobre todo lo que NO se puede hacer.
"""
import json

from src.main import app
from src.models import Usuario
from src.routers.usuarios import LARGO_MINIMO_CLAVE
from src.services.auth import requiere_auth, verify_password


def _como(email: str):
    app.dependency_overrides[requiere_auth] = lambda: email


def test_crea_un_vendedor_con_su_sucursal(client, db_session):
    r = client.post("/api/admin/usuarios", json={
        "email": "Vendedor.Prueba@Curifor.CL",
        "password": "vendedor1234",
        "nombre": "Vendedor de prueba",
        "es_vendedor": True,
        "sucursales": ["LINDEROS"],
    })
    assert r.status_code == 200
    d = r.json()
    assert d["email"] == "vendedor.prueba@curifor.cl"  # normalizado a minusculas
    assert d["es_vendedor"] is True
    assert d["sucursales"] == ["LINDEROS"]

    u = db_session.get(Usuario, "vendedor.prueba@curifor.cl")
    assert verify_password("vendedor1234", u.password_hash)
    assert json.loads(u.sucursales_permitidas) == ["LINDEROS"]


def test_la_respuesta_nunca_trae_la_contrasena(client, db_session):
    r = client.post("/api/admin/usuarios", json={
        "email": "x@curifor.cl", "password": "clave12345", "nombre": "X",
    }).json()
    assert "password" not in r
    assert "password_hash" not in r
    listado = client.get("/api/admin/usuarios").json()
    assert all("password_hash" not in u for u in listado)


def test_un_vendedor_sin_sucursal_no_se_puede_crear(client, db_session):
    """Sin sucursal no puede pedir por ninguna: quedaria adentro sin poder hacer nada."""
    r = client.post("/api/admin/usuarios", json={
        "email": "sinsucursal@curifor.cl", "password": "clave12345", "es_vendedor": True,
    })
    assert r.status_code == 400
    assert "sucursal" in r.json()["detail"].lower()
    assert db_session.get(Usuario, "sinsucursal@curifor.cl") is None


def test_una_clave_corta_se_rechaza(client, db_session):
    """El minimo vigente es 4 (ver `LARGO_MINIMO_CLAVE`). Se prueba UNA menos que
    el minimo y no un largo fijo, para que el test siga diciendo la verdad si el
    numero vuelve a cambiar."""
    corta = "x" * (LARGO_MINIMO_CLAVE - 1)
    r = client.post("/api/admin/usuarios", json={"email": "y@curifor.cl", "password": corta})
    assert r.status_code == 400
    assert "contraseña" in r.json()["detail"].lower()


def test_una_clave_del_largo_minimo_se_acepta(client, db_session):
    """La contracara: el minimo tiene que ser usable, no solo declarado."""
    r = client.post("/api/admin/usuarios", json={
        "email": "justa@curifor.cl", "password": "x" * LARGO_MINIMO_CLAVE,
    })
    assert r.status_code == 200, r.text[:200]
    assert db_session.get(Usuario, "justa@curifor.cl") is not None


def test_un_usuario_nuevo_sin_clave_se_rechaza(client, db_session):
    r = client.post("/api/admin/usuarios", json={"email": "z@curifor.cl", "nombre": "Z"})
    assert r.status_code == 400


def test_mandarlo_de_nuevo_actualiza_en_vez_de_fallar(client, db_session):
    client.post("/api/admin/usuarios", json={
        "email": "v@curifor.cl", "password": "clave12345",
        "es_vendedor": True, "sucursales": ["LINDEROS"],
    })
    r = client.post("/api/admin/usuarios", json={
        "email": "v@curifor.cl", "sucursales": ["LINDEROS", "CURICO"],
    })
    assert r.status_code == 200
    assert r.json()["sucursales"] == ["LINDEROS", "CURICO"]
    # No mandar la clave la deja como estaba.
    assert verify_password("clave12345", db_session.get(Usuario, "v@curifor.cl").password_hash)


def test_no_mandar_un_campo_no_lo_apaga(client, db_session):
    """Actualizar el nombre no puede quitarle el admin de rebote."""
    client.post("/api/admin/usuarios", json={
        "email": "a@curifor.cl", "password": "clave12345", "es_admin": True,
    })
    r = client.post("/api/admin/usuarios", json={"email": "a@curifor.cl", "nombre": "Nuevo"})
    assert r.json()["es_admin"] is True
    assert r.json()["nombre"] == "Nuevo"


def test_un_admin_no_puede_quitarse_el_admin_a_si_mismo(client, db_session):
    """Es la forma clasica de quedarse sin ningun administrador."""
    r = client.post("/api/admin/usuarios", json={
        "email": "test@curifor.com", "es_admin": False,
    })
    assert r.status_code == 400
    assert db_session.get(Usuario, "test@curifor.com").es_admin is True


def test_un_admin_no_puede_desactivarse_a_si_mismo(client, db_session):
    assert client.post("/api/admin/usuarios", json={
        "email": "test@curifor.com", "activo": False,
    }).status_code == 400
    assert client.post(
        "/api/admin/usuarios/test@curifor.com/desactivar"
    ).status_code == 400


def test_desactivar_le_quita_el_acceso_sin_borrarlo(client, db_session):
    """Borrarlo se llevaria la trazabilidad de todo lo que creo."""
    client.post("/api/admin/usuarios", json={"email": "b@curifor.cl", "password": "clave12345"})
    r = client.post("/api/admin/usuarios/b@curifor.cl/desactivar")
    assert r.status_code == 200
    assert r.json()["activo"] is False
    assert db_session.get(Usuario, "b@curifor.cl") is not None  # sigue existiendo

    # Y ya no puede entrar.
    assert client.post("/api/auth/login", json={
        "email": "b@curifor.cl", "password": "clave12345",
    }).status_code == 401


def test_un_correo_invalido_se_rechaza(client, db_session):
    assert client.post("/api/admin/usuarios", json={
        "email": "sin-arroba", "password": "clave12345",
    }).status_code == 400


def test_solo_admin(client, db_session):
    _como("noadmin@curifor.com")
    try:
        assert client.get("/api/admin/usuarios").status_code == 403
        assert client.post("/api/admin/usuarios", json={
            "email": "colado@curifor.cl", "password": "clave12345",
        }).status_code == 403
    finally:
        _como("test@curifor.com")


def test_queda_en_la_auditoria(client, db_session):
    from src.models import AuditoriaLog

    client.post("/api/admin/usuarios", json={"email": "c@curifor.cl", "password": "clave12345"})
    acciones = [a.accion for a in db_session.query(AuditoriaLog).all()]
    assert "usuario_creado" in acciones


def test_el_vendedor_creado_puede_entrar_y_pedir(client, db_session):
    """La prueba de que el endpoint resuelve el problema que lo motivo."""
    from src.models import ProductoCatalogo

    db_session.add(ProductoCatalogo(tenant_id="curifor", producto="19 TEST123",
                                    glosa="Repuesto de prueba", precio=1000.0))
    db_session.commit()

    client.post("/api/admin/usuarios", json={
        "email": "vend@curifor.cl", "password": "vendedor1234",
        "nombre": "Vendedor", "es_vendedor": True, "sucursales": ["LINDEROS"],
    })
    login = client.post("/api/auth/login", json={
        "email": "vend@curifor.cl", "password": "vendedor1234",
    })
    assert login.status_code == 200
    assert login.json()["es_vendedor"] is True
    assert login.json()["sucursales"] == ["LINDEROS"]

    _como("vend@curifor.cl")
    try:
        r = client.post("/api/requerimientos", json={
            "lineas": [{"producto": "19 TEST123", "cantidad": 2}],
        })
        assert r.status_code == 201
        assert r.json()["sucursal_id"] == "LINDEROS"
        # Y sigue sin poder entrar al sugerido.
        assert client.get("/api/sugerido").status_code == 403
    finally:
        _como("test@curifor.com")
