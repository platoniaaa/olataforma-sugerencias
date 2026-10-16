"""Lo que la pantalla de Usuarios necesita de la API (16-10-2026).

Hasta ahora los usuarios se manejaban solo por el endpoint, y lo conocia una
persona. La pantalla suma dos datos que la base no tiene: si la cuenta la usa el
motor para publicar, y que permisos le da la configuracion del servidor por
correo. Lo que se cuida aca:

1. Que los campos nuevos no rompan a quien ya leia la respuesta.
2. Que la cuenta del motor quede marcada, con el mismo criterio de las otras
   listas por correo (sin importar mayusculas ni espacios).
3. Que los permisos especiales digan lo mismo que deciden los permisos de verdad
   (services/auth.py): si se desfasan, la pantalla mentiria.
"""
import pytest
from fastapi import HTTPException

from src.config import Settings
from src.main import app
from src.models import AuditoriaLog
from src.routers import usuarios as router_usuarios
from src.routers.usuarios import LARGO_MINIMO_CLAVE
from src.services import auth
from src.services.auth import requiere_auth

CAMPOS_DE_ANTES = {
    "email", "nombre", "activo", "es_admin", "solo_lectura", "es_vendedor",
    "sucursales", "creado_en",
}


@pytest.fixture()
def listas(monkeypatch):
    """Fija las listas por correo del servidor con correos ficticios."""
    def _fijar(**valores: str):
        for campo, valor in valores.items():
            monkeypatch.setattr(router_usuarios.settings, campo, valor)
    _fijar(emails_precios="", emails_calibracion="", emails_ver_accesos="",
           emails_actualizar="", emails_motor="")
    return _fijar


def _crear(client, email: str, **extra):
    r = client.post("/api/admin/usuarios", json={"email": email, "password": "clave1234", **extra})
    assert r.status_code == 200, r.text[:200]
    return r.json()


def _del_listado(client, email: str) -> dict:
    return next(u for u in client.get("/api/admin/usuarios").json() if u["email"] == email)


def _auditoria(db, email: str) -> tuple[AuditoriaLog, AuditoriaLog]:
    """El alta y la (unica) edicion de un usuario. El id es un UUID: no sirve para ordenar."""
    filas = db.query(AuditoriaLog).filter(AuditoriaLog.entidad_id == email).all()
    alta = [f for f in filas if f.accion == "usuario_creado"]
    cambios = [f for f in filas if f.accion == "usuario_actualizado"]
    assert len(alta) == 1 and len(cambios) == 1, [f.accion for f in filas]
    return alta[0], cambios[0]


# --------------------------- compatibilidad --------------------------- #
def test_los_campos_de_antes_siguen_iguales(client, db_session, listas):
    """Otros consumidores (scripts/clave_usuario.py) leen estos campos."""
    _crear(client, "vendedor@ejemplo.cl", nombre="Vendedor", es_vendedor=True,
           sucursales=["LINDEROS"])
    u = _del_listado(client, "vendedor@ejemplo.cl")
    assert CAMPOS_DE_ANTES <= set(u)
    assert u["email"] == "vendedor@ejemplo.cl"
    assert u["nombre"] == "Vendedor"
    assert u["activo"] is True
    assert u["es_admin"] is False
    assert u["solo_lectura"] is False
    assert u["es_vendedor"] is True
    assert u["sucursales"] == ["LINDEROS"]


def test_los_campos_nuevos_vienen_siempre_con_valor(client, db_session, listas):
    """Una cuenta comun trae los dos campos nuevos en su valor neutro, no ausentes."""
    for u in client.get("/api/admin/usuarios").json():
        assert u["es_cuenta_motor"] is False
        assert u["permisos_especiales"] == []
        assert "password_hash" not in u


# --------------------------- cuenta del motor --------------------------- #
def test_por_defecto_la_cuenta_del_motor_es_la_generica():
    assert Settings.model_fields["emails_motor"].default == "admin@curifor.com"


def test_la_cuenta_del_motor_queda_marcada(client, db_session, listas):
    listas(emails_motor=" Publicador@Ejemplo.cl , respaldo@ejemplo.cl")
    creado = _crear(client, "publicador@ejemplo.cl", es_admin=True)
    _crear(client, "persona@ejemplo.cl")

    # En la respuesta del alta y en el listado.
    assert creado["es_cuenta_motor"] is True
    assert _del_listado(client, "publicador@ejemplo.cl")["es_cuenta_motor"] is True
    assert _del_listado(client, "persona@ejemplo.cl")["es_cuenta_motor"] is False


def test_la_cuenta_del_motor_no_da_permisos(client, db_session, listas):
    """Estar en EMAILS_MOTOR solo sirve para avisar: no hace admin a nadie."""
    listas(emails_motor="publicador@ejemplo.cl")
    _crear(client, "publicador@ejemplo.cl")
    app.dependency_overrides[requiere_auth] = lambda: "publicador@ejemplo.cl"
    try:
        assert client.get("/api/admin/usuarios").status_code == 403
    finally:
        app.dependency_overrides[requiere_auth] = lambda: "test@curifor.com"


def test_cambiarle_la_clave_al_motor_queda_en_la_auditoria(client, db_session, listas):
    """Para saber quien la cambio el dia que el motor deje de publicar."""
    listas(emails_motor="publicador@ejemplo.cl")
    _crear(client, "publicador@ejemplo.cl", es_admin=True)
    r = client.post("/api/admin/usuarios", json={
        "email": "publicador@ejemplo.cl", "password": "otraclave99",
    })
    assert r.status_code == 200

    alta, cambio = _auditoria(db_session, "publicador@ejemplo.cl")
    # El alta trae clave, pero no "cambiada": no habia otra antes.
    assert "clave=" not in alta.detalle
    assert "clave=cambiada" in cambio.detalle
    assert "cuenta_motor=si" in cambio.detalle
    assert "otraclave99" not in cambio.detalle


def test_editar_sin_clave_no_dice_que_la_cambio(client, db_session, listas):
    _crear(client, "persona@ejemplo.cl")
    client.post("/api/admin/usuarios", json={"email": "persona@ejemplo.cl", "nombre": "Otra"})
    _, cambio = _auditoria(db_session, "persona@ejemplo.cl")
    assert "clave=" not in cambio.detalle
    assert "cuenta_motor" not in cambio.detalle


# --------------------------- permisos especiales --------------------------- #
def test_los_permisos_especiales_salen_de_las_listas_por_correo(client, db_session, listas):
    listas(
        emails_precios="Persona.Uno@Ejemplo.cl, otra@ejemplo.cl",
        emails_calibracion="persona.uno@ejemplo.cl",
        emails_ver_accesos="otra@ejemplo.cl",
        emails_actualizar=" persona.uno@ejemplo.cl ",
    )
    _crear(client, "persona.uno@ejemplo.cl")
    _crear(client, "otra@ejemplo.cl")
    _crear(client, "nadie@ejemplo.cl")

    assert _del_listado(client, "persona.uno@ejemplo.cl")["permisos_especiales"] == [
        "precios", "calibracion", "actualizar",
    ]
    assert _del_listado(client, "otra@ejemplo.cl")["permisos_especiales"] == ["precios", "ver_accesos"]
    assert _del_listado(client, "nadie@ejemplo.cl")["permisos_especiales"] == []


def test_un_admin_no_aparece_con_permisos_que_no_estan_en_las_listas(client, db_session, listas):
    """El admin ya tiene todo; la lista muestra solo lo que dice la configuracion."""
    assert _del_listado(client, "test@curifor.com")["permisos_especiales"] == []


def test_los_permisos_especiales_dicen_lo_mismo_que_los_permisos_de_verdad(
    client, db_session, listas,
):
    """Si alguien cambia como se evalua un permiso en auth.py y no aca, esto falla."""
    listas(
        emails_precios="a@ejemplo.cl",
        emails_calibracion="b@ejemplo.cl",
        emails_ver_accesos="a@ejemplo.cl,b@ejemplo.cl",
        emails_actualizar="c@ejemplo.cl",
    )
    for email in ("a@ejemplo.cl", "b@ejemplo.cl", "c@ejemplo.cl", "d@ejemplo.cl"):
        _crear(client, email)

    def ve_accesos(email: str) -> bool:
        try:
            auth.requiere_ver_accesos(email=email, db=db_session)
            return True
        except HTTPException:
            return False

    for email in ("a@ejemplo.cl", "b@ejemplo.cl", "c@ejemplo.cl", "d@ejemplo.cl"):
        permisos = _del_listado(client, email)["permisos_especiales"]
        assert ("precios" in permisos) == auth.puede_precios(email, db_session), email
        assert ("calibracion" in permisos) == auth.puede_calibrar(email, db_session), email
        assert ("actualizar" in permisos) == auth.puede_actualizar(email, db_session), email
        assert ("ver_accesos" in permisos) == ve_accesos(email), email


# --------------------------- reglas --------------------------- #
def test_las_reglas_dan_el_largo_minimo_de_la_clave(client, db_session):
    r = client.get("/api/admin/usuarios/reglas")
    assert r.status_code == 200
    assert r.json()["largo_minimo_clave"] == LARGO_MINIMO_CLAVE


def test_las_reglas_son_solo_para_admin(client, db_session):
    app.dependency_overrides[requiere_auth] = lambda: "noadmin@curifor.com"
    try:
        assert client.get("/api/admin/usuarios/reglas").status_code == 403
    finally:
        app.dependency_overrides[requiere_auth] = lambda: "test@curifor.com"
