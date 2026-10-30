"""Consulta de productos del vendedor: ve el producto, sus reemplazos y sus ventas, SIN costo.

Lo que importa probar aquí es lo que NO debe salir. El catálogo de Abastecimiento
trae el costo, el stock mínimo y máximo y la clasificación de stock; un vendedor de
sucursal no debe verlos, y no basta con esconder la columna en la pantalla: el dato no
puede viajar al navegador (se vería en las herramientas del desarrollador).
"""
import json

import pytest

from src.main import app
from src.models import ProductoCatalogo, StockTransito, StockUnificado, Usuario, VentaHistorica
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


# --- Filtro de ventas por sucursal ------------------------------------------------------------

VIGENTE = "19 SZ6Z3B437C"


@pytest.fixture()
def con_sucursales(datos, como_vendedor):
    """Más ventas: la misma sucursal escrita de dos formas, otra más y una fuera de los 12 meses.
    Además el código tiene un reemplazo vigente que también vendió y tiene stock."""
    datos.add_all([
        # LINDEROS viene del Excel con y sin el código del ERP, a veces en el mismo archivo.
        VentaHistorica(tenant_id="curifor", periodo="202510", producto=CODIGO,
                       sucursal="02 LINDEROS", cantidad=3.0, neto=150000.0),
        VentaHistorica(tenant_id="curifor", periodo="202508", producto=CODIGO,
                       sucursal="TALCA", cantidad=4.0, neto=200000.0),
        # Fuera de la ventana de 12 meses: no es una opción del filtro.
        VentaHistorica(tenant_id="curifor", periodo="202201", producto=CODIGO,
                       sucursal="PLACILLA", cantidad=9.0, neto=450000.0),
        VentaHistorica(tenant_id="curifor", periodo="202510", producto=VIGENTE,
                       sucursal="LINDEROS", cantidad=6.0, neto=300000.0),
        VentaHistorica(tenant_id="curifor", periodo="202510", producto=VIGENTE,
                       sucursal="CURICO", cantidad=1.0, neto=50000.0),
        ProductoCatalogo(tenant_id="curifor", producto=VIGENTE, glosa="TERMINAL NUEVO", precio=52000.0),
        StockUnificado(tenant_id="curifor", producto=VIGENTE, sucursal_id="LINDEROS", bodega="LINDEROS", stock=10),
        StockUnificado(tenant_id="curifor", producto=VIGENTE, sucursal_id="CURICO", bodega="CURICO", stock=5),
    ])
    datos.commit()
    reemplazo_service.reemplazar(datos, [{
        "producto": CODIGO, "reemplazado_por": VIGENTE, "reemplazado_por_ford": "SZ6Z/3B437/C/",
        "cadena": None, "reemplaza_a": [], "sucesor_confirmado": True, "agrupado": True, "aviso": None,
    }])
    return datos


def test_el_filtro_ofrece_una_opcion_por_sucursal_y_solo_las_de_los_ultimos_12_meses(client, con_sucursales):
    r = client.get(f"/api/consulta/productos/{CODIGO}/sucursales")
    assert r.status_code == 200
    # "02 LINDEROS" y "LINDEROS" son una sola; PLACILLA vendió hace años y no aparece; y entra
    # CURICO, que solo vendió el reemplazo vigente? No: vendió el propio código (202510).
    assert r.json()["sucursales"] == ["CURICO", "LINDEROS", "TALCA"]


def test_las_ventas_de_una_sucursal_suman_todas_las_formas_de_escribirla(client, con_sucursales):
    r = client.get(f"/api/consulta/productos/{CODIGO}/ventas", params={"sucursal_id": "LINDEROS"})
    assert r.status_code == 200
    d = r.json()
    assert {m["mes"]: m["cantidad"] for m in d["meses_sucursal"]} == {"202509": 5.0, "202510": 3.0}
    assert d["total_sucursal"] == 8.0
    # La serie del total no se toca: sigue siendo la de todas las sucursales.
    assert d["total_general"] > d["total_sucursal"]
    assert "neto" not in r.text and "costo" not in r.text


@pytest.mark.parametrize("escrito", ["linderos", "02 LINDEROS", " Linderos "])
def test_el_nombre_de_la_sucursal_se_reconoce_con_o_sin_codigo_y_en_cualquier_caso(client, con_sucursales, escrito):
    r = client.get(f"/api/consulta/productos/{CODIGO}/ventas", params={"sucursal_id": escrito})
    assert r.json()["total_sucursal"] == 8.0


def test_una_sucursal_que_no_vendio_responde_en_cero_sin_error(client, con_sucursales):
    r = client.get(f"/api/consulta/productos/{CODIGO}/ventas", params={"sucursal_id": "NO EXISTE"})
    assert r.status_code == 200
    d = r.json()
    assert d["meses_sucursal"] == [] and d["total_sucursal"] == 0


def test_el_grupo_de_reemplazos_filtra_venta_y_stock_por_sucursal(client, con_sucursales):
    todas = client.get(f"/api/consulta/productos/{CODIGO}/grupo-ventas").json()
    assert todas["sucursal"] is None
    por = {m["producto"]: m for m in todas["miembros"]}
    assert por[VIGENTE]["stock"] == 15 and por[CODIGO]["stock"] == 7

    d = client.get(f"/api/consulta/productos/{CODIGO}/grupo-ventas", params={"sucursal_id": "LINDEROS"}).json()
    assert d["sucursal"] == "LINDEROS"
    por = {m["producto"]: m for m in d["miembros"]}
    assert por[VIGENTE]["venta_12m"] == 6.0 and por[VIGENTE]["stock"] == 10
    assert por[CODIGO]["venta_12m"] == 8.0 and por[CODIGO]["stock"] == 3
    assert d["total_stock"] == 13
    _sin_prohibidos(json.dumps(d))


def test_sin_filtro_las_ventas_siguen_igual(client, con_sucursales):
    """El parámetro es opcional: sin él, la respuesta es la de siempre."""
    d = client.get(f"/api/consulta/productos/{CODIGO}/ventas").json()
    assert d["sucursal_id"] == "" and d["meses_sucursal"] == [] and d["total_sucursal"] == 0


# --- Unidades en tránsito: para que el vendedor no pida de más ---------------------------------


@pytest.fixture()
def con_transito(con_sucursales):
    """Vienen 10 a Curicó (también hay stock ahí), 6 a Talca (que no tiene stock) y 3 a Linderos,
    escrita con el código del ERP. El reemplazo vigente tiene 4 en camino a Linderos."""
    from datetime import date

    con_sucursales.add_all([
        StockTransito(tenant_id="curifor", producto=CODIGO, sucursal_id="CURICO", cantidad=10.0,
                      pedido_desde=date(2026, 9, 1), origen="CURIFOR"),
        StockTransito(tenant_id="curifor", producto=CODIGO, sucursal_id="TALCA", cantidad=6.0,
                      pedido_desde=date(2026, 6, 12), origen="CURIFOR"),
        StockTransito(tenant_id="curifor", producto=CODIGO, sucursal_id="02 LINDEROS", cantidad=3.0,
                      pedido_desde=None, origen="CURIFOR"),
        StockTransito(tenant_id="curifor", producto=VIGENTE, sucursal_id="LINDEROS", cantidad=4.0,
                      pedido_desde=date(2026, 10, 5), origen="CURIFOR"),
    ])
    con_sucursales.commit()
    return con_sucursales


def test_el_detalle_trae_el_transito_por_sucursal_de_mayor_a_menor_y_su_total(client, con_transito):
    d = client.get(f"/api/consulta/productos/{CODIGO}").json()
    assert [(t["sucursal_id"], t["cantidad"]) for t in d["transito_por_sucursal"]] == [
        ("CURICO", 10.0), ("TALCA", 6.0), ("02 LINDEROS", 3.0)]
    assert d["en_transito"] == 19.0
    por = {t["sucursal_id"]: t["pedido_desde"] for t in d["transito_por_sucursal"]}
    assert por["TALCA"] == "2026-06-12" and por["02 LINDEROS"] is None
    # Incluye a Talca, que no tiene stock: es justo la sucursal a la que no hay que pedir más.
    assert "TALCA" not in {s["sucursal_id"] for s in d["stock_por_sucursal"]}
    # El origen de la OC (CURIFOR / FRONTERA) no sale.
    assert "origen" not in json.dumps(d["transito_por_sucursal"])
    _sin_prohibidos(json.dumps(d))


def test_la_lista_muestra_lo_que_viene_en_camino_de_cada_producto(client, con_transito):
    items = {x["producto"]: x for x in client.get("/api/consulta/productos").json()["items"]}
    assert items[CODIGO]["en_transito"] == 19.0
    assert items["70 2723982"]["en_transito"] == 0.0


def test_el_grupo_de_reemplazos_trae_el_transito_de_cada_codigo(client, con_transito):
    d = client.get(f"/api/consulta/productos/{CODIGO}/grupo-ventas").json()
    por = {m["producto"]: m["transito"] for m in d["miembros"]}
    assert por == {CODIGO: 19.0, VIGENTE: 4.0}


def test_el_transito_del_grupo_se_filtra_por_sucursal_aunque_venga_con_codigo(client, con_transito):
    d = client.get(f"/api/consulta/productos/{CODIGO}/grupo-ventas", params={"sucursal_id": "LINDEROS"}).json()
    por = {m["producto"]: m["transito"] for m in d["miembros"]}
    assert por == {CODIGO: 3.0, VIGENTE: 4.0}


def test_un_producto_sin_transito_responde_vacio_y_en_cero(client, con_sucursales):
    d = client.get(f"/api/consulta/productos/{CODIGO}").json()
    assert d["transito_por_sucursal"] == [] and d["en_transito"] == 0


# --- Lo que la revision encontro: el chat, el stock que se puede prometer y la ventana de 12 meses ---


def test_el_vendedor_no_pasa_del_gate_del_asistente_de_chat(client, como_vendedor):
    """Las herramientas del chat devuelven costo y proveedor: el vendedor no puede usarlo."""
    r = client.post("/api/chat", json={"pregunta": "cual es el costo del 19 SZ6Z3B437B"})
    assert r.status_code == 403


def test_abastecimiento_si_pasa_del_gate_del_asistente_de_chat(client, datos):
    """Sin Gemini configurado responde 503/502, pero no 403: el gate solo cierra al vendedor."""
    r = client.post("/api/chat", json={"pregunta": "hola"})
    assert r.status_code != 403


@pytest.fixture()
def con_bodegas_no_vendibles(con_sucursales):
    """Lo que el ERP mezcla con el stock: Danados (NODISP), una bodega de Frontera y un producto
    que solo tiene stock en Danados. Un vendedor no puede prometerle eso a un cliente."""
    from src.models.bodega_tipo import NODISP, REAL, BodegaTipo
    from src.services import precios_service

    db = con_sucursales
    for bodega, tipo in (("DAÑADOS", NODISP), ("LINDEROS", REAL), ("CURICO", REAL)):
        db.add(BodegaTipo(tenant_id="curifor", bodega=bodega,
                          clave=precios_service.clave_bodega(bodega), tipo=tipo))
    db.add_all([
        StockUnificado(tenant_id="curifor", producto=CODIGO, sucursal_id=None, bodega="DAÑADOS", stock=40),
        StockUnificado(tenant_id="curifor", producto=CODIGO, sucursal_id="CURICO", bodega="CURICO FRONTERA",
                       stock=25, origen="FRONTERA"),
        # Saldo negativo: no es stock.
        StockUnificado(tenant_id="curifor", producto=CODIGO, sucursal_id="TALCA", bodega="TALCA", stock=-2),
        StockUnificado(tenant_id="curifor", producto=VIGENTE, sucursal_id=None, bodega="DAÑADOS", stock=8),
        StockUnificado(tenant_id="curifor", producto="70 2723982", sucursal_id=None, bodega="DAÑADOS", stock=12),
    ])
    db.commit()
    return db


def test_el_detalle_no_cuenta_danados_ni_frontera_ni_saldos_negativos(client, con_bodegas_no_vendibles):
    d = client.get(f"/api/consulta/productos/{CODIGO}").json()
    assert {s["bodega"] for s in d["stock_por_sucursal"]} == {"LINDEROS", "CURICO"}
    assert d["stock_total"] == 7
    assert "DAÑADOS" not in json.dumps(d, ensure_ascii=False)


def test_la_lista_no_cuenta_danados_ni_frontera(client, con_bodegas_no_vendibles):
    items = {x["producto"]: x for x in client.get("/api/consulta/productos").json()["items"]}
    assert items[CODIGO]["stock_total"] == 7
    # Solo tiene stock en Danados: para el vendedor no tiene stock.
    assert items["70 2723982"]["stock_total"] == 0


def test_el_grupo_de_reemplazos_no_suma_danados(client, con_bodegas_no_vendibles):
    d = client.get(f"/api/consulta/productos/{CODIGO}/grupo-ventas").json()
    por = {m["producto"]: m["stock"] for m in d["miembros"]}
    assert por == {CODIGO: 7, VIGENTE: 15}
    assert d["total_stock"] == 22


def test_solo_con_stock_usa_el_stock_vivo_y_no_la_foto_del_maestro(client, como_vendedor, datos):
    """El maestro trae un `stock_total` viejo: VIVO tiene stock hoy y el maestro dice 0; VIEJO al revés."""
    datos.add_all([
        ProductoCatalogo(tenant_id="curifor", producto="VIVO", glosa="TIENE STOCK HOY", stock_total=0),
        ProductoCatalogo(tenant_id="curifor", producto="VIEJO", glosa="YA NO TIENE", stock_total=9),
        StockUnificado(tenant_id="curifor", producto="VIVO", sucursal_id="LINDEROS", bodega="LINDEROS", stock=5),
    ])
    datos.commit()
    r = client.get("/api/consulta/productos", params={"con_stock": "true"}).json()
    codigos = {x["producto"] for x in r["items"]}
    assert "VIVO" in codigos and "VIEJO" not in codigos
    assert r["total"] == len(r["items"])
    # La fila muestra el mismo stock con el que se filtro.
    assert next(x for x in r["items"] if x["producto"] == "VIVO")["stock_total"] == 5


def test_solo_con_stock_no_deja_pasar_lo_que_solo_esta_en_danados(client, con_bodegas_no_vendibles):
    r = client.get("/api/consulta/productos", params={"con_stock": "true"}).json()
    assert "70 2723982" not in {x["producto"] for x in r["items"]}


def test_el_transito_de_frontera_no_se_le_muestra_al_vendedor(client, con_transito):
    con_transito.add(StockTransito(tenant_id="curifor", producto=CODIGO, sucursal_id="OVALLE",
                                   cantidad=9.0, pedido_desde=None, origen="FRONTERA"))
    con_transito.commit()
    d = client.get(f"/api/consulta/productos/{CODIGO}").json()
    assert "OVALLE" not in {t["sucursal_id"] for t in d["transito_por_sucursal"]}
    assert d["en_transito"] == 19.0
    items = {x["producto"]: x for x in client.get("/api/consulta/productos").json()["items"]}
    assert items[CODIGO]["en_transito"] == 19.0
    g = client.get(f"/api/consulta/productos/{CODIGO}/grupo-ventas").json()
    assert {m["producto"]: m["transito"] for m in g["miembros"]}[CODIGO] == 19.0


def test_el_grupo_de_reemplazos_no_manda_el_texto_del_sugerido_de_compras(client, con_sucursales):
    r = client.get(f"/api/consulta/productos/{CODIGO}/grupo-ventas")
    assert "motivo_fuera" not in r.text


@pytest.fixture()
def con_venta_fuera_de_ventana(con_sucursales):
    """PLACILLA vendio hace años (fuera de los 12 meses) y tambien este mes: es opcion del filtro."""
    con_sucursales.add_all([
        VentaHistorica(tenant_id="curifor", periodo="202510", producto=CODIGO,
                       sucursal="PLACILLA", cantidad=2.0, neto=100000.0),
    ])
    con_sucursales.commit()
    return con_sucursales


def test_las_ventas_del_vendedor_son_solo_los_12_meses_de_la_ventana(client, con_venta_fuera_de_ventana):
    """Antes eran las ultimas 12 FILAS con venta: los 9 de 2022 arrastraban un mes viejo al grafico y
    a los promedios, y no coincidian con el historial de reemplazos de la misma pantalla."""
    d = client.get(f"/api/consulta/productos/{CODIGO}/ventas", params={"sucursal_id": "PLACILLA"}).json()
    assert [(m["mes"], m["cantidad"]) for m in d["meses_sucursal"]] == [("202510", 2.0)]
    assert d["total_sucursal"] == 2.0
    assert "202201" not in {m["mes"] for m in d["meses_general"]}
    # Sin filtro, el total tambien se queda en la ventana.
    g = client.get(f"/api/consulta/productos/{CODIGO}/ventas").json()
    assert "202201" not in {m["mes"] for m in g["meses_general"]}


def test_el_grafico_de_abastecimiento_no_cambia(con_venta_fuera_de_ventana):
    """El cambio de la ventana es solo para la vista del vendedor: el sugerido sigue con las ultimas
    12 filas, como siempre."""
    from src.services import sugerido_service

    antes = sugerido_service.ventas_12m(con_venta_fuera_de_ventana, CODIGO)
    assert "202201" in {m["mes"] for m in antes["meses_general"]}
