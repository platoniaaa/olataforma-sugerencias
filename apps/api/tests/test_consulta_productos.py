"""Consulta de productos del vendedor: ve el producto, sus reemplazos y sus ventas, SIN costo.

Lo que importa probar aquí es lo que NO debe salir. El catálogo de Abastecimiento
trae el costo, el stock mínimo y máximo y la clasificación de stock; un vendedor de
sucursal no debe verlos, y no basta con esconder la columna en la pantalla: el dato no
puede viajar al navegador (se vería en las herramientas del desarrollador).
"""
import json

import pytest

from src.main import app
from src.models import ProductoCatalogo, StockUnificado, Usuario, VentaHistorica
from src.services import reemplazo_service
from src.services.auth import hash_password, requiere_auth

CODIGO = "19 SZ6Z3B437B"
PROHIBIDOS = ("costo", "stock_minimo", "stock_maximo", "clasificacion_stock", "tipo_repuesto")


@pytest.fixture()
def datos(db_session):
    """Un vendedor de Linderos y dos productos con costo, mínimos y ventas."""
    db_session.add(Usuario(
        email="vendedor@curifor.com", password_hash=hash_password("123456"),
        nombre="Vendedor Linderos", es_vendedor=True,
        sucursales_permitidas=json.dumps(["LINDEROS"]),
    ))
    db_session.add_all([
        ProductoCatalogo(
            tenant_id="curifor", producto=CODIGO, glosa="TERMINAL DE DIRECCION",
            familia="DIRECCION", procedencia="IMPORTADO", categoria="SUSPENSION",
            precio=45000.0, costo=21000.0, stock_minimo=2, stock_maximo=9,
            clasificacion_stock="A", tipo_repuesto="ORIGINAL", unidad="UN",
            stock_total=7, reemplazo="19 SZ6Z3B437C, 19 SZ6Z3B437D",
        ),
        ProductoCatalogo(
            tenant_id="curifor", producto="70 2723982", glosa="FILTRO DE ACEITE",
            familia="FILTROS", precio=8500.0, costo=3100.0, stock_total=0,
        ),
    ])
    db_session.add_all([
        StockUnificado(tenant_id="curifor", producto=CODIGO, sucursal_id="LINDEROS",
                       bodega="LINDEROS", stock=3),
        StockUnificado(tenant_id="curifor", producto=CODIGO, sucursal_id="CURICO",
                       bodega="CURICO", stock=4),
    ])
    db_session.add_all([
        VentaHistorica(tenant_id="curifor", periodo="202509", producto=CODIGO,
                       sucursal="LINDEROS", cantidad=5.0, neto=250000.0),
        VentaHistorica(tenant_id="curifor", periodo="202510", producto=CODIGO,
                       sucursal="CURICO", cantidad=2.0, neto=100000.0),
    ])
    db_session.commit()
    return db_session


@pytest.fixture()
def como_vendedor(datos):
    """Las llamadas del test las hace el vendedor y no el usuario genérico."""
    app.dependency_overrides[requiere_auth] = lambda: "vendedor@curifor.com"
    yield
    # `client` limpia todos los overrides al terminar.


def _sin_prohibidos(texto: str):
    for campo in PROHIBIDOS:
        assert f'"{campo}"' not in texto, f"salió {campo} en la respuesta del vendedor"


def test_la_lista_trae_precio_pero_no_costo(client, como_vendedor):
    r = client.get("/api/consulta/productos")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    fila = next(x for x in body["items"] if x["producto"] == CODIGO)
    assert fila["precio"] == 45000.0
    assert fila["glosa"] == "TERMINAL DE DIRECCION"
    assert fila["reemplazo"] == "19 SZ6Z3B437C, 19 SZ6Z3B437D"
    _sin_prohibidos(r.text)


def test_el_detalle_trae_stock_de_todas_las_sucursales_y_no_trae_costo(client, como_vendedor):
    r = client.get(f"/api/consulta/productos/{CODIGO}")
    assert r.status_code == 200
    d = r.json()
    assert d["precio"] == 45000.0
    assert {s["sucursal_id"] for s in d["stock_por_sucursal"]} == {"LINDEROS", "CURICO"}
    assert d["stock_total"] == 7
    _sin_prohibidos(r.text)


def test_el_detalle_trae_el_reemplazo_de_ford(client, como_vendedor, datos):
    reemplazo_service.reemplazar(datos, [{
        "producto": CODIGO, "reemplazado_por": "19 SZ6Z3B437C",
        "reemplazado_por_ford": "SZ6Z/3B437/C/", "cadena": "SZ6Z/3B437/B/ > SZ6Z/3B437/C/",
        "reemplaza_a": [], "sucesor_confirmado": True, "agrupado": True, "aviso": None,
    }])
    rf = client.get(f"/api/consulta/productos/{CODIGO}").json()["reemplazo_ford"]
    assert rf["reemplazado_por"] == "19 SZ6Z3B437C"
    assert rf["agrupado"] is True


def test_las_ventas_son_de_todas_las_sucursales_y_solo_unidades(client, como_vendedor):
    r = client.get(f"/api/consulta/productos/{CODIGO}/ventas")
    assert r.status_code == 200
    d = r.json()
    assert d["total_general"] == 7.0
    assert {m["mes"] for m in d["meses_general"]} == {"202509", "202510"}
    # Solo cantidades: ni el monto vendido (neto) ni el costo viajan.
    assert "neto" not in r.text and "costo" not in r.text


def test_el_grupo_de_reemplazos_responde_vacio_si_no_hay_grupo(client, como_vendedor):
    r = client.get("/api/consulta/productos/70 2723982/grupo-ventas")
    assert r.status_code == 200
    assert r.json()["miembros"] == []


def test_buscar_por_codigo_o_descripcion(client, como_vendedor):
    por_codigo = client.get("/api/consulta/productos", params={"q": "SZ6Z"}).json()
    assert [x["producto"] for x in por_codigo["items"]] == [CODIGO]
    por_glosa = client.get("/api/consulta/productos", params={"q": "filtro"}).json()
    assert [x["producto"] for x in por_glosa["items"]] == ["70 2723982"]


def test_solo_con_stock(client, como_vendedor):
    r = client.get("/api/consulta/productos", params={"con_stock": "true"}).json()
    assert [x["producto"] for x in r["items"]] == [CODIGO]


def test_un_producto_que_no_existe_da_404(client, como_vendedor):
    assert client.get("/api/consulta/productos/NO EXISTE").status_code == 404


def test_el_limite_de_la_lista_tiene_tope(client, como_vendedor):
    assert client.get("/api/consulta/productos", params={"limit": 5000}).status_code == 422


def test_el_vendedor_sigue_bloqueado_en_el_catalogo_de_abastecimiento(client, como_vendedor):
    """La consulta abre solo esta ruta: el catálogo (con costo) sigue cerrado."""
    assert client.get("/api/catalogo").status_code == 403
    assert client.get(f"/api/catalogo/{CODIGO}").status_code == 403


def test_sin_sesion_no_se_ve_nada(client, datos):
    app.dependency_overrides.pop(requiere_auth, None)
    for ruta in ("/api/consulta/productos", f"/api/consulta/productos/{CODIGO}",
                 f"/api/consulta/productos/{CODIGO}/ventas"):
        assert client.get(ruta).status_code == 401, ruta
