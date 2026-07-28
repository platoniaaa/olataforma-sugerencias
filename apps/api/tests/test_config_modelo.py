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


def _catalogar(db_session, producto="20 BXO5W30AA"):
    """La ficha del catalogo solo responde si el producto esta en el maestro."""
    from src.models import ProductoCatalogo

    db_session.add(ProductoCatalogo(
        producto=producto, tenant_id="curifor", glosa="ACEITE 5W30 LITRO FORD",
    ))
    db_session.commit()


def test_stock_publicar_y_verlo_en_el_catalogo(client, db_session):
    """El motor publica el stock por bodega y la ficha del catalogo lo muestra.

    Antes esta tabla la llenaba solo el Power BI Desktop; al retirarlo, el stock
    del catalogo quedo congelado.
    """
    _catalogar(db_session)
    r = client.post("/api/admin/stock-unificado", json={"filas": [
        {"producto": "20 BXO5W30AA", "bodega": "LINDEROS 1",
         "sucursal_id": "LINDEROS", "stock": 30, "origen": "CURIFOR"},
        {"producto": "20 BXO5W30AA", "bodega": "CD REPUESTOS",
         "sucursal_id": "CD REPUESTOS", "stock": 12, "origen": "CURIFOR"},
        {"producto": "20 BXO5W30AA", "bodega": "FRONTERA 1",
         "sucursal_id": "TALCA", "stock": 5, "origen": "FRONTERA"},
        {"producto": "", "bodega": "X", "stock": 99},  # sin codigo -> se ignora
    ]})
    assert r.status_code == 200
    assert r.json() == {"filas_cargadas": 3, "ignoradas": 1, "reemplazo": True}

    d = client.get("/api/catalogo/20 BXO5W30AA").json()
    assert d["stock_total"] == 47
    # Ordenado por stock desc, con la bodega y la empresa de cada fila.
    assert [f["bodega"] for f in d["stock_por_sucursal"]] == [
        "LINDEROS 1", "CD REPUESTOS", "FRONTERA 1",
    ]
    assert d["stock_por_sucursal"][2]["origen"] == "FRONTERA"


def test_catalogo_muestra_los_reemplazos_del_mix(client, db_session):
    """La ficha del catalogo muestra el grupo de reemplazo que calculo el motor.

    El maestro del ERP trae la columna Reemplazo vacia en el 99% de los productos;
    la agrupacion buena sale del mix y llega en `sugerido.reemplazos`. Por eso se
    prefiere esa fuente y el maestro queda de respaldo.
    """
    _catalogar(db_session, "80 173897")
    d = client.get("/api/catalogo/80 173897").json()
    assert d["reemplazo"] is None, "sin fila en sugerido no hay grupo que mostrar"

    from src.models import Sugerido

    db_session.add(Sugerido(
        tenant_id="curifor", producto="80 173897", descripcion="LIMPIADOR DE FRENOS",
        sucursal_id="LINDEROS", nombre_sucursal="Linderos", reemplazos="80 391732",
    ))
    db_session.commit()

    assert client.get("/api/catalogo/80 173897").json()["reemplazo"] == "80 391732"


def test_catalogo_muestra_el_grupo_desde_cualquier_miembro(client, db_session):
    """Entrar por un miembro que no es master igual debe mostrar el grupo.

    El motor escribe la lista de reemplazos solo en la fila del master (el que mas
    vendio). Buscando por otro codigo del grupo parecia que no tenia equivalentes.
    """
    from src.models import Sugerido

    # Master del grupo: 80 391732, con los otros dos como reemplazos.
    db_session.add(Sugerido(
        tenant_id="curifor", producto="80 391732", descripcion="LIMPIADOR HELLA",
        sucursal_id="LINDEROS", nombre_sucursal="Linderos",
        reemplazos="80 PR/51822, 80 173897",
    ))
    # Distractor: contiene "80 17" como substring, pero NO es del grupo. Cubre el
    # falso positivo del LIKE.
    db_session.add(Sugerido(
        tenant_id="curifor", producto="OTRO", descripcion="Otro grupo",
        sucursal_id="LINDEROS", nombre_sucursal="Linderos", reemplazos="80 1738000",
    ))
    db_session.commit()

    # Desde el master: los otros dos.
    _catalogar(db_session, "80 391732")
    assert client.get("/api/catalogo/80 391732").json()["reemplazo"] == (
        "80 PR/51822, 80 173897"
    )

    # Desde un miembro: el master primero y despues el otro miembro, sin repetirse.
    _catalogar(db_session, "80 PR/51822")
    assert client.get("/api/catalogo/80 PR/51822").json()["reemplazo"] == (
        "80 391732, 80 173897"
    )

    _catalogar(db_session, "80 173897")
    assert client.get("/api/catalogo/80 173897").json()["reemplazo"] == (
        "80 391732, 80 PR/51822"
    )

    # El codigo parecido no pertenece a ningun grupo: el LIKE no debe colarlo.
    _catalogar(db_session, "80 17")
    assert client.get("/api/catalogo/80 17").json()["reemplazo"] is None


def test_stock_publicar_vacio_no_borra_la_foto_anterior(client, db_session):
    """Una corrida que no trajo filas no debe dejar el catalogo sin stock.

    Es preferible mostrar la foto de ayer que borrarla por un Excel que llego
    vacio o un error de lectura a medio camino.
    """
    _catalogar(db_session)
    client.post("/api/admin/stock-unificado", json={"filas": [
        {"producto": "20 BXO5W30AA", "bodega": "B1", "sucursal_id": "LINDEROS", "stock": 7},
    ]})
    r = client.post("/api/admin/stock-unificado", json={"filas": []})
    assert r.json() == {"filas_cargadas": 0, "ignoradas": 0, "reemplazo": False}

    assert client.get("/api/catalogo/20 BXO5W30AA").json()["stock_total"] == 7
