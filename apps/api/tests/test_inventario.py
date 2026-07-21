"""Tests del panel de salud de inventario."""
from src.models import Sugerido


def _sugerido(**kw):
    base = dict(tenant_id="curifor", sucursal_id="LINDEROS", nombre_sucursal="Linderos")
    base.update(kw)
    return Sugerido(**base)


def test_inmovilizado_es_stock_sin_demanda(client, db_session):
    db_session.add(_sugerido(
        producto="MUERTO-1", stock_activo_suc=10, demanda_mensual=0, costo_unitario=5000.0,
    ))
    db_session.commit()
    r = client.get("/api/inventario/salud").json()
    assert r["resumen"]["inmovilizado_n"] == 1
    assert r["resumen"]["inmovilizado_clp"] == 50000
    assert r["top_inmovilizado"][0]["producto"] == "MUERTO-1"


def test_producto_que_se_mueve_no_es_inmovilizado(client, db_session):
    db_session.add(_sugerido(
        producto="VIVO-1", stock_activo_suc=10, demanda_mensual=30, demanda_diaria=1.0,
        costo_unitario=5000.0,
    ))
    db_session.commit()
    r = client.get("/api/inventario/salud").json()
    assert r["resumen"]["inmovilizado_n"] == 0
    # 10 unidades a 1 por dia = 10 dias de cobertura.
    assert r["resumen"]["cobertura_dias_mediana"] == 10.0


def test_sobre_stock_depende_del_umbral(client, db_session):
    """365 dias de cobertura: es sobre-stock a 180 dias, no a 365."""
    db_session.add(_sugerido(
        producto="LENTO-1", stock_activo_suc=365, demanda_mensual=30, demanda_diaria=1.0,
        costo_unitario=1000.0,
    ))
    db_session.commit()
    assert client.get("/api/inventario/salud?dias_sobre_stock=180").json()["resumen"]["sobre_stock_n"] == 1
    assert client.get("/api/inventario/salud?dias_sobre_stock=365").json()["resumen"]["sobre_stock_n"] == 0


def test_quiebre_solo_cuenta_si_hay_demanda(client, db_session):
    db_session.add(_sugerido(producto="QUIEBRE-1", stock_activo_suc=0, demanda_mensual=20))
    db_session.add(_sugerido(producto="SIN-NADA", stock_activo_suc=0, demanda_mensual=0))
    db_session.commit()
    r = client.get("/api/inventario/salud").json()
    assert r["resumen"]["quiebre_con_demanda_n"] == 1


def test_bajo_punto_de_pedido_considera_el_transito(client, db_session):
    """Lo que viene en camino cuenta: si no, se pide dos veces lo mismo."""
    db_session.add(_sugerido(
        producto="PP-CUBIERTO", stock_activo_suc=5, stock_en_transito_suc=10,
        punto_de_pedido=12, demanda_mensual=30,
    ))
    db_session.add(_sugerido(
        producto="PP-BAJO", stock_activo_suc=5, stock_en_transito_suc=0,
        punto_de_pedido=12, demanda_mensual=30,
    ))
    db_session.commit()
    r = client.get("/api/inventario/salud").json()
    assert r["resumen"]["bajo_punto_pedido_n"] == 1


def test_stock_sin_costo_se_reporta_aparte(client, db_session):
    """No se puede valorizar: se avisa en vez de contarlo como cero en silencio."""
    db_session.add(_sugerido(producto="SIN-COSTO", stock_activo_suc=100, costo_unitario=None))
    db_session.commit()
    r = client.get("/api/inventario/salud").json()
    assert r["resumen"]["sin_costo_n"] == 1
    assert r["resumen"]["valor_inventario_clp"] == 0


def test_desglose_por_sucursal(client, db_session):
    db_session.add(_sugerido(
        producto="P-A", sucursal_id="LINDEROS", nombre_sucursal="Linderos",
        stock_activo_suc=10, demanda_mensual=0, costo_unitario=1000.0,
    ))
    db_session.add(_sugerido(
        producto="P-B", sucursal_id="TALCA", nombre_sucursal="Talca",
        stock_activo_suc=5, demanda_mensual=0, costo_unitario=1000.0,
    ))
    db_session.commit()
    por_suc = {s["sucursal_id"]: s for s in client.get("/api/inventario/salud").json()["por_sucursal"]}
    assert por_suc["LINDEROS"]["inmovilizado_clp"] == 10000
    assert por_suc["TALCA"]["inmovilizado_clp"] == 5000


def test_respeta_el_acceso_por_sucursal(client, db_session):
    """Un usuario restringido no puede ver el inventario de otras sucursales."""
    import json

    from src.main import app
    from src.models import Usuario
    from src.services.auth import hash_password, requiere_auth

    db_session.add(Usuario(
        email="luis@x.com", password_hash=hash_password("x"),
        sucursales_permitidas=json.dumps(["BRASIL 18"]),
    ))
    db_session.add(_sugerido(
        producto="P-LIN", sucursal_id="LINDEROS", stock_activo_suc=10,
        demanda_mensual=0, costo_unitario=1000.0,
    ))
    db_session.add(_sugerido(
        producto="P-BRA", sucursal_id="BRASIL 18", stock_activo_suc=3,
        demanda_mensual=0, costo_unitario=1000.0,
    ))
    db_session.commit()

    app.dependency_overrides[requiere_auth] = lambda: "luis@x.com"
    try:
        r = client.get("/api/inventario/salud").json()
        sucs = {s["sucursal_id"] for s in r["por_sucursal"]}
        assert sucs == {"BRASIL 18"}
        assert r["resumen"]["inmovilizado_clp"] == 3000
    finally:
        app.dependency_overrides[requiere_auth] = lambda: "test@curifor.com"
