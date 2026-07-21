"""El modo 'mantener stock' tiene que servir para productos que el sistema NO sugiere.

Es el caso donde mas se usa: un repuesto sin demanda registrada (campana, VOR,
pedido especial) del que igual se quieren tener unas unidades siempre. Antes
respondia "ese producto no esta en la sucursal elegida" y no dejaba avanzar.
"""
from src.models import StockUnificado, Sugerido, SugerenciaManual
from src.services import sugerido_service


def _stock(db_session, producto, sucursal_id, cantidad):
    db_session.add(StockUnificado(
        tenant_id="curifor", producto=producto, sucursal_id=sucursal_id,
        bodega=sucursal_id, stock=cantidad,
    ))
    db_session.commit()


def test_producto_fuera_del_sugerido_pide_el_nivel_completo(client, db_session):
    """Sin stock ni sugerido: se pide todo el nivel."""
    r = client.post("/api/sugerencias-manuales", json={
        "producto": "83 1025100GH20A", "sucursal_id": "CD REPUESTOS",
        "stock_objetivo": 3, "motivo": "Campana movil",
    })
    assert r.status_code == 201
    assert r.json()["unidades"] == 3
    assert r.json()["stock_objetivo"] == 3


def test_descuenta_el_stock_de_bodega(client, db_session):
    """Aunque no este en el sugerido, el stock real de la bodega si se conoce."""
    _stock(db_session, "SIN-SUG", "CD REPUESTOS", 2)
    r = client.post("/api/sugerencias-manuales", json={
        "producto": "SIN-SUG", "sucursal_id": "CD REPUESTOS", "stock_objetivo": 5,
    })
    assert r.json()["unidades"] == 3


def test_suma_las_bodegas_de_la_misma_sucursal(client, db_session):
    _stock(db_session, "MULTI-BOD", "CD REPUESTOS", 2)
    _stock(db_session, "MULTI-BOD", "CD REPUESTOS", 3)
    assert sugerido_service.unidades_para_objetivo(
        db_session, "MULTI-BOD", "CD REPUESTOS", 10
    ) == 5


def test_stock_de_otra_sucursal_no_cuenta(client, db_session):
    """El nivel es por sucursal: lo que hay en Linderos no cubre el CD."""
    _stock(db_session, "OTRA-SUC", "LINDEROS", 50)
    assert sugerido_service.unidades_para_objetivo(
        db_session, "OTRA-SUC", "CD REPUESTOS", 4
    ) == 4


def test_nivel_ya_cubierto_en_bodega_sigue_avisando(client, db_session):
    _stock(db_session, "YA-OK", "CD REPUESTOS", 10)
    r = client.post("/api/sugerencias-manuales", json={
        "producto": "YA-OK", "sucursal_id": "CD REPUESTOS", "stock_objetivo": 5,
    })
    assert r.status_code == 409


def test_la_sugerencia_aparece_en_el_listado_sin_buscarla(client, db_session):
    """Si no se ve en la grilla, se compra a ciegas: tiene que salir en la pagina 1."""
    client.post("/api/sugerencias-manuales", json={
        "producto": "FUERA-1", "sucursal_id": "CD REPUESTOS", "stock_objetivo": 4,
    })
    items = client.get("/api/sugerido?page=1").json()["items"]
    fila = next((i for i in items if i["producto"] == "FUERA-1"), None)
    assert fila is not None
    assert fila["total_sugerido_suc"] == 4
    assert fila["origen"] == "manual"


def test_no_se_repite_en_cada_pagina(client, db_session):
    """Se agrega despues de paginar: si no se acotara a la pagina 1, saldria N veces."""
    for i in range(3):
        db_session.add(Sugerido(
            tenant_id="curifor", producto=f"P-PAG-{i}", sucursal_id="LINDEROS",
            pedir="Si", total_sugerido_suc=5,
        ))
    db_session.commit()
    client.post("/api/sugerencias-manuales", json={
        "producto": "FUERA-2", "sucursal_id": "CD REPUESTOS", "stock_objetivo": 4,
    })

    pagina2 = client.get("/api/sugerido?page=2&limit=2").json()["items"]
    assert not any(i["producto"] == "FUERA-2" for i in pagina2)


def test_respeta_el_acceso_por_sucursal(client, db_session):
    """Un usuario restringido no puede ver manuales de sucursales ajenas."""
    import json

    from src.main import app
    from src.models import Usuario
    from src.services.auth import hash_password, requiere_auth

    db_session.add(Usuario(
        email="luis2@x.com", password_hash=hash_password("x"),
        sucursales_permitidas=json.dumps(["BRASIL 18"]),
    ))
    db_session.commit()
    client.post("/api/sugerencias-manuales", json={
        "producto": "AJENA-1", "sucursal_id": "CD REPUESTOS", "stock_objetivo": 4,
    })

    app.dependency_overrides[requiere_auth] = lambda: "luis2@x.com"
    try:
        items = client.get("/api/sugerido?page=1").json()["items"]
        assert not any(i["producto"] == "AJENA-1" for i in items)
    finally:
        app.dependency_overrides[requiere_auth] = lambda: "test@curifor.com"


def test_llega_al_excel_exportado(client, db_session):
    import io

    import openpyxl

    client.post("/api/sugerencias-manuales", json={
        "producto": "FUERA-XLS", "sucursal_id": "CD REPUESTOS", "stock_objetivo": 6,
    })
    r = client.post("/api/sugerido/export-excel", json={
        "filtros": {}, "columnas": ["producto", "total_sugerido_suc"],
    })
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    filas = list(wb.active.iter_rows(values_only=True))
    productos = [f[0] for f in filas[1:]]
    assert "FUERA-XLS" in productos


def test_recurrente_sobre_producto_fuera_del_sugerido(client, db_session):
    """El caso completo de la jefa: mantener 3 u y que se mantenga solo."""
    r = client.post("/api/sugerencias-manuales/recurrentes", json={
        "modo": "individual", "producto": "REC-FUERA", "sucursal_id": "CD REPUESTOS",
        "stock_objetivo": 3, "cada_dias": 7, "motivo": "Campana movil",
    })
    assert r.status_code == 201
    inst = db_session.query(SugerenciaManual).filter_by(producto="REC-FUERA").one()
    assert inst.unidades == 3
    assert inst.stock_objetivo == 3
