"""Configuracion calibrable del modelo: leer, aplicar, validar, historial, auditar."""
from sqlalchemy import select

from src.models import AuditoriaLog, ConfiguracionModelo


def test_config_vigente_devuelve_defaults_cuando_no_hay_nada(client):
    r = client.get("/api/calibracion/config-modelo")
    assert r.status_code == 200
    d = r.json()
    assert d["es_default"] is True
    assert d["ciclo_orden_dias"] == 5 and d["ciclo_orden_dias_cd"] == 5
    assert d["z_por_clase"] == {"A": 1.645, "B": 1.282, "C": 0.842, "D": 0.0}
    assert d["z_importado_cd"] == {"A": 1.282, "B": 1.036}
    assert d["winsor_k"] == 3.0 and d["lead_time_fallback_dias"] == 8


def test_put_aplica_el_cambio_y_lo_persiste(client, db_session):
    r = client.put("/api/calibracion/config-modelo", json={
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
    d2 = client.get("/api/calibracion/config-modelo").json()
    assert d2["ciclo_orden_dias_cd"] == 7 and d2["z_por_clase"]["C"] == 1.0

    # Se registro en la auditoria con el detalle del cambio.
    log = db_session.scalars(
        select(AuditoriaLog).where(AuditoriaLog.accion == "config_modelo_actualizada")
    ).first()
    assert log is not None and "ciclo_orden_dias_cd: 5 -> 7" in (log.detalle or "")


def test_put_fuera_de_rango_se_rechaza(client, db_session):
    # z hasta 3.5; 9 debe rebotar (validacion del schema) y NO crear version.
    r = client.put("/api/calibracion/config-modelo", json={"z_a": 9})
    assert r.status_code == 422
    assert db_session.scalars(select(ConfiguracionModelo)).first() is None


def test_historial_lista_las_versiones(client):
    client.put("/api/calibracion/config-modelo", json={"ciclo_orden_dias_cd": 6})
    client.put("/api/calibracion/config-modelo", json={"ciclo_orden_dias_cd": 7})
    h = client.get("/api/calibracion/config-modelo/historial").json()
    assert len(h) == 2
    # Mas reciente primero.
    assert h[0]["ciclo_orden_dias_cd"] == 7 and h[1]["ciclo_orden_dias_cd"] == 6


def test_usuario_sin_permiso_no_puede_cambiar(client):
    """Un usuario que no es admin NI esta autorizado a calibrar recibe 403.

    (mramos@ si puede aunque no sea admin: ver test_permiso_calibracion.py)"""
    from src.main import app
    from src.services.auth import requiere_auth

    app.dependency_overrides[requiere_auth] = lambda: "noadmin@curifor.com"
    try:
        r = client.put("/api/calibracion/config-modelo", json={"ciclo_orden_dias_cd": 9})
        assert r.status_code == 403
    finally:
        app.dependency_overrides[requiere_auth] = lambda: "test@curifor.com"


def test_revertir_vuelve_a_una_version_anterior(client):
    """Revertir inserta una COPIA de la version elegida: el historial no se pierde."""
    client.put("/api/calibracion/config-modelo", json={"ciclo_orden_dias_cd": 6})
    client.put("/api/calibracion/config-modelo", json={"ciclo_orden_dias_cd": 9})
    h = client.get("/api/calibracion/config-modelo/historial").json()
    id_vieja = h[1]["id"]  # la del 6

    r = client.post(f"/api/calibracion/config-modelo/revertir/{id_vieja}")
    assert r.status_code == 200
    assert r.json()["ciclo_orden_dias_cd"] == 6
    assert "Revertido" in (r.json()["nota"] or "")
    # Quedan 3 versiones: no se borro nada.
    assert len(client.get("/api/calibracion/config-modelo/historial").json()) == 3


def test_revertir_version_inexistente_da_404(client):
    assert client.post("/api/calibracion/config-modelo/revertir/no-existe").status_code == 404


def test_lead_time_publicar_y_consultar(client):
    """El motor publica su lead time y la web lo consulta con buscador."""
    r = client.post("/api/admin/lead-time-proveedor", json={"filas": [
        {"proveedor": "FORD MOTOR", "sucursal_id": None, "lead_time_dias": 2.66, "n_muestras": None},
        {"proveedor": "FORD MOTOR", "sucursal_id": "LINDEROS", "lead_time_dias": 2.1, "n_muestras": 40},
        {"proveedor": "MAHLE", "sucursal_id": "CURICO", "lead_time_dias": 88.7, "n_muestras": 3},
        {"proveedor": "", "sucursal_id": "X", "lead_time_dias": 5, "n_muestras": 1},  # se ignora
    ]})
    assert r.status_code == 200
    assert r.json() == {"filas_cargadas": 3, "ignoradas": 1}

    d = client.get("/api/calibracion/lead-time-proveedor").json()
    assert d["total"] == 3 and d["actualizado_en"] is not None
    # La fila global (sin sucursal) va primero dentro de su proveedor.
    assert d["items"][0] == {
        "proveedor": "FORD MOTOR", "sucursal_id": None,
        "lead_time_dias": 2.66, "n_muestras": None,
    }

    # Buscador por proveedor y por sucursal.
    assert client.get("/api/calibracion/lead-time-proveedor?buscar=mahle").json()["total"] == 1
    assert client.get("/api/calibracion/lead-time-proveedor?buscar=linderos").json()["total"] == 1
    assert client.get("/api/calibracion/lead-time-proveedor?solo_global=true").json()["total"] == 1


def test_lead_time_publicar_reemplaza_la_foto(client):
    """Cada corrida del motor reemplaza la tabla: es una foto, no un historico."""
    client.post("/api/admin/lead-time-proveedor", json={"filas": [
        {"proveedor": "VIEJO", "sucursal_id": None, "lead_time_dias": 10},
    ]})
    client.post("/api/admin/lead-time-proveedor", json={"filas": [
        {"proveedor": "NUEVO", "sucursal_id": None, "lead_time_dias": 20},
    ]})
    d = client.get("/api/calibracion/lead-time-proveedor").json()
    assert d["total"] == 1 and d["items"][0]["proveedor"] == "NUEVO"
