"""La auditoria y las notificaciones NO pueden voltear la accion principal.

El modulo lo promete en su docstring, pero no lo cumplia: el `except` tragaba el
error del INSERT sin deshacerlo, la sesion de SQLAlchemy quedaba en
pending-rollback, y el `db.commit()` del endpoint reventaba con un 500 DESPUES de
que la accion principal ya se habia guardado.

El escenario real que lo dispara: una migracion que no alcanzo a correr (el
`create_all` de Render se traga los errores) deja el modelo declarando una
columna que la tabla no tiene. Ahi el INSERT de la notificacion falla siempre.

Lo caro no es el 500: es lo que pasa despues. El vendedor ve el error, reintenta,
y crea un requerimiento DUPLICADO en la bandeja del comprador.
"""
import pytest
from sqlalchemy import text

from src.models import Requerimiento
from src.services import auditoria_service


@pytest.fixture()
def notificacion_rota(db_session):
    """Simula el deploy a medias: la tabla existe sin la columna del modelo."""
    db_session.execute(text("DROP TABLE IF EXISTS notificacion"))
    db_session.execute(text(
        "CREATE TABLE notificacion ("
        " id VARCHAR PRIMARY KEY, tenant_id VARCHAR, tipo VARCHAR, titulo VARCHAR,"
        " mensaje TEXT, creado_por_email VARCHAR, creado_en TIMESTAMP,"
        " producto VARCHAR, sucursal_id VARCHAR, vistas_por TEXT)"
    ))
    db_session.commit()
    return db_session


def test_una_notificacion_que_falla_no_voltea_el_commit(notificacion_rota):
    """El corazon del asunto: tras el fallo, la sesion sigue usable."""
    db = notificacion_rota
    r = auditoria_service.notificar(db, tipo="x", titulo="no va a poder guardarse")
    assert r is None  # fallo, como se espera

    # Y la transaccion del endpoint tiene que poder cerrarse igual.
    db.add(Requerimiento(
        tenant_id="curifor", sucursal_id="LINDEROS", nombre_sucursal="Linderos",
        creado_por="v@curifor.cl", estado="enviado",
    ))
    db.commit()  # sin el SAVEPOINT, esto lanzaba PendingRollbackError
    assert db.query(Requerimiento).count() == 1


def test_una_auditoria_que_falla_tampoco(db_session):
    db_session.execute(text("DROP TABLE IF EXISTS auditoria_log"))
    db_session.commit()

    assert auditoria_service.registrar(db_session, accion="x", entidad="y") is None
    db_session.add(Requerimiento(
        tenant_id="curifor", sucursal_id="LINDEROS", nombre_sucursal="Linderos",
        creado_por="v@curifor.cl", estado="enviado",
    ))
    db_session.commit()
    assert db_session.query(Requerimiento).count() == 1


def test_el_endpoint_no_devuelve_500_ni_duplica(client, notificacion_rota):
    """El escenario completo, por HTTP: crear un requerimiento con la campanita rota."""
    import json

    from src.models import ProductoCatalogo, Usuario
    from src.main import app
    from src.services.auth import hash_password, requiere_auth

    db = notificacion_rota
    db.add(Usuario(email="v@curifor.cl", password_hash=hash_password("123456"),
                   nombre="V", es_vendedor=True,
                   sucursales_permitidas=json.dumps(["LINDEROS"])))
    db.add(ProductoCatalogo(tenant_id="curifor", producto="19 TEST",
                            glosa="Repuesto", precio=1000.0))
    db.commit()

    app.dependency_overrides[requiere_auth] = lambda: "v@curifor.cl"
    try:
        cuerpo = {"lineas": [{"producto": "19 TEST", "cantidad": 2}]}
        r1 = client.post("/api/requerimientos", json=cuerpo)
        assert r1.status_code == 201, f"el aviso roto volteo la creacion: {r1.text[:200]}"
        # Y el vendedor NO tiene motivo para reintentar, asi que no hay duplicado.
        assert db.query(Requerimiento).count() == 1
    finally:
        app.dependency_overrides[requiere_auth] = lambda: "test@curifor.com"


def test_cerrar_un_requerimiento_tampoco_se_cae(client, notificacion_rota):
    """El PATCH avisa al vendedor; si ese aviso falla, el cierre igual responde 200."""
    import json

    from src.models import ProductoCatalogo, Usuario
    from src.main import app
    from src.services.auth import hash_password, requiere_auth

    db = notificacion_rota
    db.add(Usuario(email="v2@curifor.cl", password_hash=hash_password("123456"),
                   nombre="V2", es_vendedor=True,
                   sucursales_permitidas=json.dumps(["LINDEROS"])))
    db.add(ProductoCatalogo(tenant_id="curifor", producto="19 TEST2",
                            glosa="Repuesto", precio=1000.0))
    db.commit()

    app.dependency_overrides[requiere_auth] = lambda: "v2@curifor.cl"
    rid = client.post("/api/requerimientos", json={
        "lineas": [{"producto": "19 TEST2", "cantidad": 1}],
    }).json()["id"]

    app.dependency_overrides[requiere_auth] = lambda: "test@curifor.com"
    r = client.patch(f"/api/requerimientos/{rid}", json={
        "estado": "procesado", "nota_comprador": "ok",
    })
    assert r.status_code == 200, f"el aviso roto volteo el cierre: {r.text[:200]}"
    assert r.json()["estado"] == "procesado"
