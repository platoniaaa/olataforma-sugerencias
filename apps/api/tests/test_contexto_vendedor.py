"""Contexto de un repuesto para el vendedor que arma su lista.

Al armar el requerimiento el vendedor solo veia codigo, descripcion, precio y el
stock de su sucursal. No tenia forma de saber si el repuesto se vende, si hay
unidades en otra sucursal (que se resuelve con un traslado y no con una compra),
ni si ya viene en camino.

Lo que NO ve: costo y margen. El vendedor pide, no compra; el costo es
informacion de negociacion con el proveedor.
"""
from src.services import requerimiento_service

RUTA = "/api/requerimientos/producto"


def test_devuelve_la_venta_y_el_stock_de_la_red(db_session):
    d = requerimiento_service.contexto_para_vendedor(db_session, "P1", "LINDEROS")
    assert d["producto"] == "P1"
    assert "consumo" in d
    assert isinstance(d["consumo_12m_sucursal"], (int, float))
    assert "por_sucursal" in d["stock"]


def test_no_expone_costo_ni_margen(db_session):
    """El vendedor pide; el costo es informacion de compra."""
    d = requerimiento_service.contexto_para_vendedor(db_session, "P1", "LINDEROS")
    plano = str(d)
    assert "costo" not in plano
    assert "margen" not in plano
    assert "modelo" not in d


def test_sin_producto_avisa(db_session):
    import pytest
    from fastapi import HTTPException

    with pytest.raises(HTTPException):
        requerimiento_service.contexto_para_vendedor(db_session, "  ", "LINDEROS")


# --- El endpoint -----------------------------------------------------------------

def test_la_ruta_no_choca_con_la_del_detalle_por_requerimiento(client):
    """`/producto/X` y `/{req_id}/producto/X` conviven: la primera no puede
    terminar interpretando "producto" como el id de un requerimiento."""
    r = client.get(f"{RUTA}/P1", params={"sucursal_id": "LINDEROS"})
    assert r.status_code == 200, r.text
    assert r.json()["producto"] == "P1"


def test_el_codigo_con_espacios_viaja_entero(client):
    """Los codigos de Curifor traen espacios: la ruta es :path por eso."""
    r = client.get(f"{RUTA}/14 2C4Z7C522AA", params={"sucursal_id": "LINDEROS"})
    assert r.status_code == 200
    assert r.json()["producto"] == "14 2C4Z7C522AA"


def test_un_comprador_sin_sucursal_recibe_un_error_claro(client):
    r = client.get(f"{RUTA}/P1")
    assert r.status_code == 400
    assert "sucursal" in r.json()["detail"].lower()
