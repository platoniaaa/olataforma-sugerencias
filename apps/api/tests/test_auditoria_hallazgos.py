"""Hallazgos de la auditoria del 05-ago-2026, cada uno con su regresion.

Los tres se verificaron primero contra produccion, no en teoria.
"""
import json

import pytest

from src.main import app
from src.models import AuditoriaLog, ProductoCatalogo, StockUnificado, Sugerido, Usuario
from src.services import auditoria_service, requerimiento_service
from src.services.auth import hash_password, requiere_auth


@pytest.fixture()
def equipo(db_session):
    db_session.add(Usuario(
        email="vend@curifor.cl", password_hash=hash_password("1234"),
        nombre="Vendedor", es_vendedor=True,
        sucursales_permitidas=json.dumps(["LINDEROS"]),
    ))
    db_session.add_all([
        AuditoriaLog(tenant_id="curifor", accion="sugerencia_creada", entidad="sugerencia",
                     usuario_email="mramos@curifor.com", detalle="+1 u en CD"),
        AuditoriaLog(tenant_id="curifor", accion="lote_eliminado", entidad="sugerencia",
                     usuario_email="mramos@curifor.com", detalle="95 eliminadas"),
        AuditoriaLog(tenant_id="curifor", accion="requerimiento_creado", entidad="requerimiento",
                     usuario_email="vend@curifor.cl", detalle="2 lineas"),
    ])
    db_session.commit()
    return db_session


# --- 1. El vendedor no ve la auditoria del equipo --------------------------- #

def test_el_vendedor_solo_ve_lo_suyo_en_la_auditoria(client, equipo):
    """Medido en produccion: el vendedor de prueba veia las 100 ultimas entradas
    del equipo, incluidas las ediciones de usuarios."""
    app.dependency_overrides[requiere_auth] = lambda: "vend@curifor.cl"
    try:
        r = client.get("/api/auditoria")
        assert r.status_code == 200
        items = r.json()["items"]
        assert items, "el vendedor deberia ver AL MENOS lo suyo"
        assert {i["usuario_email"] for i in items} == {"vend@curifor.cl"}
        assert r.json()["total"] == 1
    finally:
        app.dependency_overrides[requiere_auth] = lambda: "test@curifor.com"


def test_el_comprador_sigue_viendo_todo(client, equipo):
    """La contracara: el arreglo no puede dejar ciego al equipo de compras."""
    r = client.get("/api/auditoria")
    assert r.status_code == 200
    emails = {i["usuario_email"] for i in r.json()["items"]}
    assert "mramos@curifor.com" in emails and "vend@curifor.cl" in emails


def test_el_total_respeta_el_filtro(equipo):
    """El total tiene que contar lo filtrado, no la tabla entera: si no, la
    paginacion promete paginas que no existen."""
    _, total_todos = auditoria_service.listar_auditoria(equipo)
    _, total_suyo = auditoria_service.listar_auditoria(equipo, solo_de="vend@curifor.cl")
    assert total_todos >= 3
    assert total_suyo == 1


def test_el_total_no_depende_de_la_pagina(equipo):
    """Se contaba con `len(...all())` sobre la consulta completa. Al pasar a
    COUNT hay que asegurar que el limit no se cuele en el total."""
    rows, total = auditoria_service.listar_auditoria(equipo, limit=1)
    assert len(rows) == 1
    assert total >= 3


# --- 2. La tabla y el panel tienen que decir lo MISMO ----------------------- #

def test_el_stock_cd_de_la_tabla_calza_con_el_del_panel(db_session):
    """En produccion `14 1495982` salia con "Stock CD 0" en la tabla y "6" en el
    panel de la misma linea: la tabla solo miraba el sugerido y el producto no
    tiene fila ahi."""
    db = db_session
    db.add(ProductoCatalogo(tenant_id="curifor", producto="14 1495982",
                            glosa="MODULO AIR BAG", precio=10000.0))
    db.add(StockUnificado(tenant_id="curifor", producto="14 1495982",
                          sucursal_id="CD REPUESTOS", stock=6))
    db.commit()
    assert db.query(Sugerido).filter_by(
        producto="14 1495982", sucursal_id="LINDEROS").count() == 0

    fila = requerimiento_service.analizar(
        db, "LINDEROS", [{"producto": "14 1495982", "cantidad": 1}]
    )["lineas"][0]
    panel = requerimiento_service.detalle_producto(db, "14 1495982", "LINDEROS")

    assert fila["stock_cd"] == 6
    assert panel["stock"]["cd"] == 6
    assert fila["stock_cd"] == panel["stock"]["cd"]


def test_sin_dato_sigue_siendo_none_y_no_cero(db_session):
    """La otra mitad: donde de verdad no se sabe, tiene que venir None para que
    la pantalla pinte "—" y no un cero que se lee como "no hay"."""
    db = db_session
    db.add(ProductoCatalogo(tenant_id="curifor", producto="99 SIN DATO",
                            glosa="REPUESTO SIN NADA", precio=1000.0))
    db.commit()

    fila = requerimiento_service.analizar(
        db, "LINDEROS", [{"producto": "99 SIN DATO", "cantidad": 1}]
    )["lineas"][0]
    assert fila["stock_cd"] is None
