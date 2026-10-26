"""Tablas e interfaz del modulo Canal Digital: siembra, politica, carga semanal y ruta del motor."""
import pytest

from src.canal_digital.politica import CLUSTERS, PoliticaInvalida
from src.main import app
from src.models import CanalDigitalPolitica, CanalDigitalVenta
from src.services import canal_digital_service as svc
from src.services.auth import requiere_admin


def _fila(producto="P1", semana="2026-09-21", periodo="202609", **kw):
    base = {"producto": producto, "semana": semana, "periodo": periodo, "unid_brutas": 5, "unid_devueltas": 1,
            "valor_costo": 400, "unid_liquidacion": 0, "n_lineas": 2}
    base.update(kw)
    return base


def test_asegurar_bodega_siembra_la_politica_y_es_idempotente(db_session):
    svc.asegurar_bodega(db_session, "430")
    svc.asegurar_bodega(db_session, "430")
    assert db_session.query(CanalDigitalPolitica).count() == 27
    pol = svc.leer_politica(db_session, "430")
    assert tuple(f.cluster for f in pol.filas) == CLUSTERS
    assert pol.validar() == []


def test_otra_bodega_tiene_su_propia_politica(db_session):
    svc.asegurar_bodega(db_session, "430")
    svc.asegurar_bodega(db_session, "999")
    assert db_session.query(CanalDigitalPolitica).count() == 54


def test_politica_incompleta_no_se_lee(db_session):
    svc.asegurar_bodega(db_session, "430")
    db_session.query(CanalDigitalPolitica).filter_by(cluster="AAA").delete()
    db_session.commit()
    with pytest.raises(PoliticaInvalida):
        svc.leer_politica(db_session, "430")


def test_reemplazar_ventas_solo_toca_los_periodos_que_vienen(db_session):
    svc.reemplazar_ventas(db_session, "430", [_fila(periodo="202608", semana="2026-08-24"), _fila()])
    r = svc.reemplazar_ventas(db_session, "430", [_fila(unid_brutas=9)])
    assert r == {"filas_cargadas": 1, "ignoradas": 0, "periodos": ["202609"]}
    por = {v.periodo: v.unid_brutas for v in db_session.query(CanalDigitalVenta).all()}
    assert por == {"202608": 5.0, "202609": 9.0}


def test_reemplazar_ventas_no_mezcla_bodegas_y_descarta_filas_malas(db_session):
    svc.reemplazar_ventas(db_session, "430", [_fila()])
    r = svc.reemplazar_ventas(db_session, "999", [_fila(), _fila(periodo="2026-09"), _fila(producto=""),
                                                  _fila(semana="mala")])
    assert r["filas_cargadas"] == 1 and r["ignoradas"] == 3
    assert db_session.query(CanalDigitalVenta).filter_by(bodega="430").count() == 1


def test_claves_repetidas_se_suman(db_session):
    r = svc.reemplazar_ventas(db_session, "430", [_fila(), _fila()])
    assert r["filas_cargadas"] == 1
    v = db_session.query(CanalDigitalVenta).one()
    assert v.unid_brutas == 10 and v.n_lineas == 4


def test_una_tanda_vacia_no_borra_nada(db_session):
    svc.reemplazar_ventas(db_session, "430", [_fila()])
    assert svc.reemplazar_ventas(db_session, "430", [])["filas_cargadas"] == 0
    assert db_session.query(CanalDigitalVenta).count() == 1


def test_ruta_del_motor_publica_y_meta_lo_cuenta(client):
    app.dependency_overrides[requiere_admin] = lambda: "motor"
    r = client.post("/api/canal-digital/ventas", json={"bodega": "430", "filas": [_fila(), _fila("P2")]})
    assert r.status_code == 200 and r.json()["filas_cargadas"] == 2
    m = client.get("/api/canal-digital/meta").json()
    assert m["filas"] == 2 and m["productos"] == 2 and m["periodo_hasta"] == "202609"
    assert client.post("/api/canal-digital/ventas", json={"filas": "x"}).status_code == 400


def test_publicar_exige_admin(client, db_session):
    from src.models import Usuario

    db_session.get(Usuario, "test@curifor.com").es_admin = False
    db_session.commit()
    r = client.post("/api/canal-digital/ventas", json={"filas": []})
    assert r.status_code == 403
