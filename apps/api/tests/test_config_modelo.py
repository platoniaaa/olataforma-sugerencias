"""Configuracion calibrable del modelo: leer, aplicar, validar, historial, auditar."""
from sqlalchemy import select

from src.models import AuditoriaLog, ConfiguracionModelo


def test_config_vigente_devuelve_defaults_cuando_no_hay_nada(client):
    r = client.get("/api/admin/config-modelo")
    assert r.status_code == 200
    d = r.json()
    assert d["es_default"] is True
    assert d["ciclo_orden_dias"] == 5 and d["ciclo_orden_dias_cd"] == 5
    assert d["z_por_clase"] == {"A": 1.645, "B": 1.282, "C": 0.842, "D": 0.0}
    assert d["z_importado_cd"] == {"A": 1.282, "B": 1.036}
    assert d["winsor_k"] == 3.0 and d["lead_time_fallback_dias"] == 8


def test_put_aplica_el_cambio_y_lo_persiste(client, db_session):
    r = client.put("/api/admin/config-modelo", json={
        "ciclo_orden_dias_cd": 7, "z_c": 1.0, "nota": "prueba jefa",
    })
    assert r.status_code == 200
    d = r.json()
    assert d["es_default"] is False
    assert d["ciclo_orden_dias_cd"] == 7
    assert d["z_por_clase"]["C"] == 1.0
    # Lo no tocado conserva el default.
    assert d["ciclo_orden_dias"] == 5 and d["z_por_clase"]["A"] == 1.645
    assert d["creado_por"] == "test@curifor.com" and d["nota"] == "prueba jefa"

    # Y queda como vigente en una lectura nueva.
    d2 = client.get("/api/admin/config-modelo").json()
    assert d2["ciclo_orden_dias_cd"] == 7 and d2["z_por_clase"]["C"] == 1.0

    # Se registro en la auditoria con el detalle del cambio.
    log = db_session.scalars(
        select(AuditoriaLog).where(AuditoriaLog.accion == "config_modelo_actualizada")
    ).first()
    assert log is not None and "ciclo_orden_dias_cd: 5 -> 7" in (log.detalle or "")


def test_put_fuera_de_rango_se_rechaza(client, db_session):
    # z hasta 3.5; 9 debe rebotar (validacion del schema) y NO crear version.
    r = client.put("/api/admin/config-modelo", json={"z_a": 9})
    assert r.status_code == 422
    assert db_session.scalars(select(ConfiguracionModelo)).first() is None


def test_historial_lista_las_versiones(client):
    client.put("/api/admin/config-modelo", json={"ciclo_orden_dias_cd": 6})
    client.put("/api/admin/config-modelo", json={"ciclo_orden_dias_cd": 7})
    h = client.get("/api/admin/config-modelo/historial").json()
    assert len(h) == 2
    # Mas reciente primero.
    assert h[0]["ciclo_orden_dias_cd"] == 7 and h[1]["ciclo_orden_dias_cd"] == 6


def test_no_admin_no_puede_cambiar(client):
    """Un usuario sin es_admin recibe 403 al intentar aplicar cambios."""
    from src.main import app
    from src.services.auth import requiere_auth

    app.dependency_overrides[requiere_auth] = lambda: "noadmin@curifor.com"
    try:
        r = client.put("/api/admin/config-modelo", json={"ciclo_orden_dias_cd": 9})
        assert r.status_code == 403
    finally:
        app.dependency_overrides[requiere_auth] = lambda: "test@curifor.com"
