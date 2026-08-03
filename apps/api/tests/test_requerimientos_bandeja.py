"""Bandeja de requerimientos: el vendedor arma el carro, el comprador lo resuelve.

Lo que se prueba acá es el poka-yoke, o sea: que las cosas que no deben poder
pasar, no puedan pasar. Un vendedor pidiendo por otra sucursal, un código que no
existe entrando a la base, una cantidad en cero, un rechazo sin motivo, o alguien
de sucursal entrando al sugerido.
"""
import json

import pytest

from src.models import ProductoCatalogo, Requerimiento, StockUnificado, Usuario
from src.services.auth import hash_password, requiere_auth
from src.main import app


@pytest.fixture()
def vendedor(db_session):
    """Un vendedor de Linderos y un par de productos en la lista de precios."""
    db_session.add(Usuario(
        email="vendedor@curifor.com", password_hash=hash_password("123456"),
        nombre="Vendedor Linderos", es_vendedor=True,
        sucursales_permitidas=json.dumps(["LINDEROS"]),
    ))
    db_session.add(Usuario(
        email="vendedor2@curifor.com", password_hash=hash_password("123456"),
        nombre="Vendedor Curicó", es_vendedor=True,
        sucursales_permitidas=json.dumps(["CURICO"]),
    ))
    db_session.add_all([
        ProductoCatalogo(tenant_id="curifor", producto="19 SZ6Z3B437B",
                         glosa="TERMINAL DE DIRECCION", precio=45000.0, familia="DIRECCION"),
        ProductoCatalogo(tenant_id="curifor", producto="70 2723982",
                         glosa="FILTRO DE ACEITE", precio=8500.0),
    ])
    db_session.add(StockUnificado(tenant_id="curifor", producto="19 SZ6Z3B437B",
                                  sucursal_id="LINDEROS", stock=3))
    db_session.commit()
    return db_session


def _como(email: str):
    """Cambia el usuario de la sesión de prueba."""
    app.dependency_overrides[requiere_auth] = lambda: email


# --- Buscador: la única puerta de entrada al carro ---------------------------

def test_el_buscador_encuentra_por_codigo_y_por_descripcion(client, vendedor):
    _como("vendedor@curifor.com")
    por_codigo = client.get("/api/requerimientos/buscar?q=SZ6Z3B437B").json()
    por_texto = client.get("/api/requerimientos/buscar?q=terminal").json()
    assert [p["producto"] for p in por_codigo] == ["19 SZ6Z3B437B"]
    assert [p["producto"] for p in por_texto] == ["19 SZ6Z3B437B"]


def test_el_buscador_trae_el_stock_de_la_sucursal(client, vendedor):
    _como("vendedor@curifor.com")
    r = client.get("/api/requerimientos/buscar?q=SZ6Z3B437B&sucursal_id=LINDEROS").json()
    assert r[0]["stock_sucursal"] == 3
    assert r[0]["precio"] == 45000.0


def test_un_codigo_que_no_existe_no_devuelve_nada(client, vendedor):
    """Si no está en la lista de precios no se puede agregar. Ese es todo el punto."""
    _como("vendedor@curifor.com")
    assert client.get("/api/requerimientos/buscar?q=NOEXISTE").json() == []


# --- Crear: lo que la pantalla impide, el servidor también -------------------

def test_el_vendedor_no_escribe_su_sucursal(client, vendedor):
    """Con una sola sucursal asignada, no manda sucursal y se le pone la suya."""
    _como("vendedor@curifor.com")
    r = client.post("/api/requerimientos", json={
        "lineas": [{"producto": "19 SZ6Z3B437B", "cantidad": 2}],
    })
    assert r.status_code == 201
    assert r.json()["sucursal_id"] == "LINDEROS"


def test_no_puede_pedir_por_una_sucursal_ajena(client, vendedor):
    _como("vendedor@curifor.com")
    r = client.post("/api/requerimientos", json={
        "sucursal_id": "CURICO",
        "lineas": [{"producto": "19 SZ6Z3B437B", "cantidad": 1}],
    })
    assert r.status_code == 403


def test_un_codigo_inventado_no_entra_a_la_base(client, vendedor):
    _como("vendedor@curifor.com")
    r = client.post("/api/requerimientos", json={
        "lineas": [{"producto": "CODIGO-FALSO", "cantidad": 1}],
    })
    assert r.status_code == 400
    assert "lista de precios" in r.json()["detail"]


def test_cantidad_en_cero_se_rechaza(client, vendedor):
    _como("vendedor@curifor.com")
    r = client.post("/api/requerimientos", json={
        "lineas": [{"producto": "19 SZ6Z3B437B", "cantidad": 0}],
    })
    assert r.status_code == 422


def test_un_requerimiento_vacio_se_rechaza(client, vendedor):
    _como("vendedor@curifor.com")
    assert client.post("/api/requerimientos", json={"lineas": []}).status_code == 400


def test_el_mismo_producto_dos_veces_se_suma_en_una_linea(client, vendedor):
    """Dos líneas iguales serían un problema que el comprador tendría que interpretar."""
    _como("vendedor@curifor.com")
    r = client.post("/api/requerimientos", json={
        "lineas": [
            {"producto": "19 SZ6Z3B437B", "cantidad": 2},
            {"producto": "19 SZ6Z3B437B", "cantidad": 3},
        ],
    }).json()
    assert len(r["lineas"]) == 1
    assert r["lineas"][0]["cantidad_pedida"] == 5


def test_guarda_la_foto_del_precio(client, vendedor, db_session):
    """La lista de precios se recarga a diario; sin la foto el vendedor vería otro precio."""
    _como("vendedor@curifor.com")
    r = client.post("/api/requerimientos", json={
        "lineas": [{"producto": "19 SZ6Z3B437B", "cantidad": 2}],
    }).json()
    assert r["lineas"][0]["precio_lista"] == 45000.0
    assert r["total_estimado"] == 90000.0
    # El precio cambia después: el requerimiento conserva el que se vio.
    db_session.query(ProductoCatalogo).filter_by(producto="19 SZ6Z3B437B").update(
        {"precio": 99999.0}
    )
    db_session.commit()
    assert client.get(f"/api/requerimientos/{r['id']}").json()["lineas"][0]["precio_lista"] == 45000.0


def test_el_comprador_no_puede_crear_requerimientos(client, vendedor):
    """Un requerimiento nace en la sucursal; si no, el registro miente sobre quién pidió."""
    _como("test@curifor.com")  # admin/comprador de la fixture base
    r = client.post("/api/requerimientos", json={
        "sucursal_id": "LINDEROS",
        "lineas": [{"producto": "19 SZ6Z3B437B", "cantidad": 1}],
    })
    # El admin sí pasa (necesita poder probar la vista); un comprador normal no.
    assert r.status_code == 201
    _como("noadmin@curifor.com")
    assert client.post("/api/requerimientos", json={
        "sucursal_id": "LINDEROS",
        "lineas": [{"producto": "19 SZ6Z3B437B", "cantidad": 1}],
    }).status_code == 403


# --- Bandeja: cada uno ve lo que le toca ------------------------------------

def test_el_vendedor_solo_ve_los_suyos(client, vendedor):
    _como("vendedor@curifor.com")
    client.post("/api/requerimientos", json={"lineas": [{"producto": "70 2723982", "cantidad": 1}]})
    _como("vendedor2@curifor.com")
    client.post("/api/requerimientos", json={"lineas": [{"producto": "70 2723982", "cantidad": 9}]})

    _como("vendedor@curifor.com")
    mios = client.get("/api/requerimientos").json()
    assert mios["total"] == 1
    assert mios["items"][0]["sucursal_id"] == "LINDEROS"

    _como("test@curifor.com")
    assert client.get("/api/requerimientos").json()["total"] == 2


def test_un_vendedor_no_puede_abrir_el_requerimiento_de_otro(client, vendedor):
    _como("vendedor2@curifor.com")
    ajeno = client.post(
        "/api/requerimientos", json={"lineas": [{"producto": "70 2723982", "cantidad": 1}]}
    ).json()["id"]
    _como("vendedor@curifor.com")
    assert client.get(f"/api/requerimientos/{ajeno}").status_code == 403


def test_abrirlo_deja_acuse_de_recibo(client, vendedor):
    """El vendedor hoy no sabe si su correo se leyó. Esa es media la gracia."""
    _como("vendedor@curifor.com")
    rid = client.post(
        "/api/requerimientos", json={"lineas": [{"producto": "70 2723982", "cantidad": 1}]}
    ).json()["id"]
    assert client.get(f"/api/requerimientos/{rid}").json()["estado"] == "enviado"

    _como("test@curifor.com")
    assert client.get(f"/api/requerimientos/{rid}").json()["estado"] == "en_revision"

    _como("vendedor@curifor.com")
    assert client.get(f"/api/requerimientos/{rid}").json()["estado"] == "en_revision"


def test_al_comprador_le_llega_el_analisis_y_al_vendedor_no(client, vendedor):
    """El contexto para decidir es del comprador; el vendedor ve lo que pidió."""
    _como("vendedor@curifor.com")
    rid = client.post(
        "/api/requerimientos", json={"lineas": [{"producto": "19 SZ6Z3B437B", "cantidad": 1}]}
    ).json()["id"]
    assert client.get(f"/api/requerimientos/{rid}").json()["lineas"][0]["analisis"] is None

    _como("test@curifor.com")
    analisis = client.get(f"/api/requerimientos/{rid}").json()["lineas"][0]["analisis"]
    assert analisis is not None
    assert analisis["estado"] in {"en_sugerido", "sin_venta_local", "no_existe"}


# --- Resolver: lo que decide el comprador -----------------------------------

def _crear(client, producto="19 SZ6Z3B437B", cantidad=5) -> int:
    _como("vendedor@curifor.com")
    return client.post(
        "/api/requerimientos", json={"lineas": [{"producto": producto, "cantidad": cantidad}]}
    ).json()["id"]


def test_el_comprador_recorta_la_cantidad(client, vendedor):
    rid = _crear(client)
    _como("test@curifor.com")
    linea = client.get(f"/api/requerimientos/{rid}").json()["lineas"][0]
    r = client.patch(f"/api/requerimientos/{rid}", json={
        "cantidades": [{"linea_id": linea["id"], "cantidad": 2}],
    }).json()
    assert r["lineas"][0]["cantidad_pedida"] == 5
    assert r["lineas"][0]["cantidad_aprobada"] == 2


def test_rechazar_sin_motivo_no_se_puede(client, vendedor):
    """Un "no" sin motivo obliga al vendedor a preguntar por correo."""
    rid = _crear(client)
    _como("test@curifor.com")
    r = client.patch(f"/api/requerimientos/{rid}", json={"estado": "rechazado"})
    assert r.status_code == 400
    assert "por qué" in r.json()["detail"]

    ok = client.patch(f"/api/requerimientos/{rid}", json={
        "estado": "rechazado", "nota_comprador": "Se resuelve con traslado desde el CD.",
    })
    assert ok.status_code == 200
    assert ok.json()["estado"] == "rechazado"


def test_un_requerimiento_cerrado_no_se_modifica(client, vendedor):
    rid = _crear(client)
    _como("test@curifor.com")
    client.patch(f"/api/requerimientos/{rid}", json={"estado": "procesado"})
    r = client.patch(f"/api/requerimientos/{rid}", json={"estado": "rechazado",
                                                        "nota_comprador": "me arrepentí"})
    assert r.status_code == 409


def test_un_estado_inventado_se_rechaza(client, vendedor):
    rid = _crear(client)
    _como("test@curifor.com")
    assert client.patch(f"/api/requerimientos/{rid}",
                        json={"estado": "casi_listo"}).status_code == 400


def test_el_vendedor_no_puede_resolver_su_propio_requerimiento(client, vendedor):
    rid = _crear(client)
    _como("vendedor@curifor.com")
    r = client.patch(f"/api/requerimientos/{rid}", json={"estado": "procesado"})
    assert r.status_code == 403


# --- El vendedor no entra a abastecimiento ----------------------------------

@pytest.mark.parametrize("ruta", [
    "/api/sugerido", "/api/compras/carros", "/api/catalogo",
    "/api/sugerencias-manuales", "/api/inventario/salud",
])
def test_el_vendedor_recibe_403_en_todo_lo_de_abastecimiento(client, vendedor, ruta):
    """Esconder el menú no alcanza: la URL sigue existiendo."""
    _como("vendedor@curifor.com")
    assert client.get(ruta).status_code == 403


def test_el_comprador_si_entra(client, vendedor):
    _como("test@curifor.com")
    assert client.get("/api/sugerido").status_code == 200


# --- Pegar la lista ---------------------------------------------------------

def test_pegar_resuelve_contra_la_lista_de_precios(client, vendedor):
    _como("vendedor@curifor.com")
    r = client.post("/api/requerimientos/pegar", json={
        "texto": "19 SZ6Z3B437B\t4\nNO-EXISTE\t2",
        "sucursal_id": "LINDEROS",
    }).json()
    por_codigo = {f["producto"]: f for f in r}
    assert por_codigo["19 SZ6Z3B437B"]["encontrado"] is True
    assert por_codigo["19 SZ6Z3B437B"]["cantidad"] == 4
    assert por_codigo["19 SZ6Z3B437B"]["precio"] == 45000.0
    # Lo que no existe vuelve marcado, no desaparece en silencio.
    assert por_codigo["NO-EXISTE"]["encontrado"] is False


def test_pegar_resuelve_el_codigo_ambiguo(client, vendedor):
    """`70 2723982` es UN código, no el producto 70 con cantidad 2.723.982."""
    _como("vendedor@curifor.com")
    r = client.post("/api/requerimientos/pegar", json={"texto": "70 2723982 6"}).json()
    assert r[0]["producto"] == "70 2723982"
    assert r[0]["cantidad"] == 6
    assert r[0]["encontrado"] is True
