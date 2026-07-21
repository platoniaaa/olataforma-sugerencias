"""Tests de la historia del sugerido (snapshots) y las alertas post-carga."""
from datetime import date, timedelta

import pytest

from src.models import Sugerido, SugeridoSnapshot
from src.services import snapshot_service


def _sug(**kw):
    base = dict(tenant_id="curifor", sucursal_id="LINDEROS", nombre_sucursal="Linderos")
    base.update(kw)
    return Sugerido(**base)


@pytest.fixture
def alertas_on(monkeypatch):
    """Las alertas vienen APAGADAS por defecto (el umbral no esta calibrado); los
    tests que prueban su logica las encienden a proposito."""
    monkeypatch.setattr(snapshot_service.settings, "alertas_habilitadas", True)


def test_guarda_solo_las_filas_con_actividad(db_session):
    """Las filas en cero son la mayoria y no aportan historia."""
    db_session.add(_sug(producto="CON-SUG", total_sugerido_suc=5))
    db_session.add(_sug(producto="CON-STOCK", stock_activo_suc=10))
    db_session.add(_sug(producto="CON-PP", punto_de_pedido=3))
    db_session.add(_sug(producto="EN-CERO", total_sugerido_suc=0, stock_activo_suc=0))
    db_session.commit()

    snapshot_service.guardar_snapshot(db_session)
    productos = {s.producto for s in db_session.query(SugeridoSnapshot).all()}
    assert {"CON-SUG", "CON-STOCK", "CON-PP"} <= productos
    assert "EN-CERO" not in productos


def test_dos_sync_el_mismo_dia_no_duplican(db_session):
    """La sync puede correr dos veces en un dia: la foto se reescribe, no se apila."""
    db_session.add(_sug(producto="P1", total_sugerido_suc=5))
    db_session.commit()

    snapshot_service.guardar_snapshot(db_session)
    snapshot_service.guardar_snapshot(db_session)
    assert db_session.query(SugeridoSnapshot).filter_by(producto="P1").count() == 1


def test_purga_respeta_la_retencion(db_session):
    db_session.add(_sug(producto="P1", total_sugerido_suc=5))
    db_session.commit()
    hoy = date.today()
    snapshot_service.guardar_snapshot(db_session, fecha=hoy - timedelta(days=100))
    snapshot_service.guardar_snapshot(db_session, fecha=hoy)

    borrados = snapshot_service.purgar_antiguos(db_session, dias=60)
    assert borrados >= 1
    # No queda nada mas viejo que la retencion.
    assert all(s.fecha == hoy for s in db_session.query(SugeridoSnapshot).all())


def test_serie_devuelve_la_evolucion_ordenada(db_session):
    db_session.add(_sug(producto="P1", total_sugerido_suc=5, stock_activo_suc=2))
    db_session.commit()
    hoy = date.today()
    snapshot_service.guardar_snapshot(db_session, fecha=hoy - timedelta(days=2))
    snapshot_service.guardar_snapshot(db_session, fecha=hoy)

    serie = snapshot_service.serie(db_session, "P1", "LINDEROS")
    assert len(serie) == 2
    assert serie[0]["fecha"] < serie[1]["fecha"]
    assert serie[0]["sugerido"] == 5
    assert serie[0]["stock"] == 2


def test_alerta_agrupa_por_sucursal(db_session, alertas_on):
    """Una notificacion por sucursal, no una por producto: si no, nadie las lee."""
    for i in range(3):
        db_session.add(_sug(producto=f"QUIEBRE-{i}", stock_activo_suc=0, demanda_mensual=10))
    db_session.add(_sug(
        producto="BAJO-PP", stock_activo_suc=2, punto_de_pedido=10, demanda_mensual=10,
    ))
    db_session.commit()

    r = snapshot_service.generar_alertas(db_session)
    assert r["sucursales_avisadas"] == 1

    from src.models import Notificacion

    notis = db_session.query(Notificacion).all()
    assert len(notis) == 1
    assert "3 en quiebre" in notis[0].titulo
    assert "1 bajo el punto de pedido" in notis[0].titulo


def test_alerta_ignora_productos_sin_demanda(db_session):
    """Sin stock y sin demanda no es un quiebre: es un producto que no se vende."""
    db_session.add(_sug(producto="MUERTO", stock_activo_suc=0, demanda_mensual=0))
    db_session.commit()
    assert snapshot_service.generar_alertas(db_session)["sucursales_avisadas"] == 0


def test_alerta_considera_el_transito(db_session):
    db_session.add(_sug(
        producto="EN-CAMINO", stock_activo_suc=2, stock_en_transito_suc=20,
        punto_de_pedido=10, demanda_mensual=10,
    ))
    db_session.commit()
    assert snapshot_service.generar_alertas(db_session)["sucursales_avisadas"] == 0


def test_post_carga_no_propaga_errores(db_session, monkeypatch):
    """Un fallo guardando historia no puede dejar la plataforma sin datos."""
    def _explota(*a, **kw):
        raise RuntimeError("base caida")

    monkeypatch.setattr(snapshot_service, "guardar_snapshot", _explota)
    r = snapshot_service.post_carga(db_session)
    assert "fallo" in str(r["snapshot_filas"])
    # Las otras etapas siguen corriendo igual.
    assert "alertas" in r


def test_endpoint_historia(client, db_session):
    db_session.add(_sug(producto="HIST-1", total_sugerido_suc=7, stock_activo_suc=3))
    db_session.commit()
    snapshot_service.guardar_snapshot(db_session, fecha=date.today() - timedelta(days=1))
    snapshot_service.guardar_snapshot(db_session)

    r = client.get("/api/sugerido/HIST-1/LINDEROS/historia")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 2
    assert items[0]["sugerido"] == 7 and items[0]["stock"] == 3
