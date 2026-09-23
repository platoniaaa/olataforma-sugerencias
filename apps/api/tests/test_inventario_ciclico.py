"""Tests del modulo Inventario ciclico."""
import io
import json

import pytest
from openpyxl import Workbook

from src.main import app
from src.models import IcRol, StockUnificado, Usuario
from src.services.auth import hash_password, requiere_auth

SEMANA = "2026-09-23"  # miercoles -> se guarda como lunes 2026-09-21
CABECERA = ["Producto", "Descripcion", "Sucursal", "Clasif ABC", "Cantidad", "Costo", "Requiere evidencia"]


def _xlsx(filas, cabecera=CABECERA) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(cabecera)
    for f in filas:
        ws.append(f)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _cargar(client, filas, semana=SEMANA, nombre="carga.xlsx", contenido=None):
    data = contenido if contenido is not None else _xlsx(filas)
    return client.post(
        f"/api/inventario-ciclico/carga?semana={semana}",
        files={"archivo": (nombre, data, "application/octet-stream")},
    )


FILAS_OK = [
    ["P-A", "Filtro aceite", "LINDEROS", "A", 10, 1000, "No"],
    ["P-B", "Pastilla freno", "Linderos", "B", 5, 20000, "Si"],
    ["P-C", "Ampolleta", "linderos", "C", 3, 500, ""],
    ["P-D", "Tapa valvula", "LINDEROS", "D", 0, 300, None],
]


@pytest.fixture()
def como():
    """Cambia el usuario logueado dentro de un test."""

    def _como(email):
        app.dependency_overrides[requiere_auth] = lambda: email

    yield _como
    app.dependency_overrides[requiere_auth] = lambda: "test@curifor.com"


@pytest.fixture()
def bodega(db_session):
    db_session.add(Usuario(email="bodega@curifor.com", password_hash=hash_password("x"), nombre="Bodega"))
    db_session.add(IcRol(email="bodega@curifor.com", rol="bodega", sucursales=json.dumps(["LINDEROS"])))
    db_session.commit()
    return "bodega@curifor.com"


def _items(client, **params):
    r = client.get("/api/inventario-ciclico/items", params={"semana": SEMANA, **params})
    assert r.status_code == 200, r.text
    return {i["producto"]: i for i in r.json()}


# --------------------------- carga --------------------------- #
def test_carga_guarda_la_semana_en_su_lunes(client):
    r = _cargar(client, FILAS_OK)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["semana"] == "2026-09-21"
    assert body["insertados"] == 4
    assert body["sucursales"] == ["LINDEROS"]
    items = _items(client)
    assert items["P-B"]["requiere_evidencia"] is True
    assert items["P-A"]["requiere_evidencia"] is False
    assert items["P-A"]["estado"] == "pendiente"


def test_carga_acepta_csv_con_punto_y_coma_y_numeros_chilenos(client):
    csv = "Producto;Sucursal;Clasif ABC;Cantidad;Costo\nX1;Talca 2;A;1.200;$ 12.500,5\n"
    r = _cargar(client, None, nombre="carga.csv", contenido=csv.encode("utf-8"))
    assert r.status_code == 200, r.text
    item = _items(client)["X1"]
    assert item["sucursal_id"] == "TALCA (2)"
    assert item["cantidad_sistema"] == 1200
    assert item["costo_unitario"] == 12500.5


def test_carga_con_errores_no_guarda_nada(client):
    filas = FILAS_OK + [
        ["P-E", "x", "CD REPUESTOS", "A", 1, 1, ""],
        ["P-F", "x", "NARNIA", "A", 1, 1, ""],
        ["P-G", "x", "LINDEROS", "Z", "mucho", 1, ""],
    ]
    r = _cargar(client, filas)
    assert r.status_code == 400
    errores = r.json()["detail"]["errores"]
    assert any("Fila 6" in e and "CD" in e for e in errores)
    assert any("Fila 7" in e and "NARNIA" in e for e in errores)
    assert any("Fila 8" in e and "clase" in e and "cantidad" in e for e in errores)
    assert _items(client) == {}


def test_carga_sin_columnas_obligatorias(client):
    r = _cargar(client, None, contenido=_xlsx([["P", "LINDEROS"]], cabecera=["Producto", "Sucursal"]))
    assert r.status_code == 400
    assert "Faltan columnas" in r.json()["detail"]["errores"][0]


def test_avisa_si_falta_una_clase_y_si_queda_bajo_la_cuota(client, db_session):
    for n in range(60):
        db_session.add(StockUnificado(producto=f"S{n}", sucursal_id="LINDEROS", stock=2))
    db_session.commit()
    r = _cargar(client, FILAS_OK[:2])
    avisos = r.json()["avisos"]
    assert any("clase C, D" in a for a in avisos)
    # 60 productos / 15 semanas que quedan desde el 21-sep = 4 por semana; hay 2.
    assert any("al menos 4 por semana" in a for a in avisos)


def test_recarga_conserva_lo_contado_y_reemplaza_lo_pendiente(client):
    _cargar(client, FILAS_OK)
    items = _items(client)
    client.patch(f"/api/inventario-ciclico/items/{items['P-A']['id']}", json={"cantidad_contada": 9})

    nuevas = [
        ["P-A", "Filtro aceite", "LINDEROS", "A", 999, 1, ""],  # contado: no se toca
        ["P-C", "Ampolleta", "LINDEROS", "C", 7, 500, ""],      # pendiente: se actualiza
        ["P-Z", "Nuevo", "LINDEROS", "D", 1, 1, ""],            # nuevo
    ]
    body = _cargar(client, nuevas).json()
    assert (body["insertados"], body["actualizados"], body["conservados"], body["eliminados"]) == (1, 1, 1, 2)
    items = _items(client)
    assert set(items) == {"P-A", "P-C", "P-Z"}
    assert items["P-A"]["cantidad_sistema"] == 10
    assert items["P-A"]["cantidad_contada"] == 9
    assert items["P-C"]["cantidad_sistema"] == 7


def test_plantilla_se_descarga(client):
    r = client.get("/api/inventario-ciclico/plantilla")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/vnd.openxmlformats")


# --------------------------- conteo --------------------------- #
def test_conteo_calcula_diferencia_y_estado(client):
    _cargar(client, FILAS_OK)
    item = _items(client)["P-A"]
    r = client.patch(
        f"/api/inventario-ciclico/items/{item['id']}",
        json={"cantidad_contada": 8, "observacion": "  2 cajas rotas  "},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["diferencia"] == -2
    assert body["diferencia_valor"] == -2000
    assert body["estado"] == "con_diferencia"
    assert body["observacion"] == "2 cajas rotas"
    assert body["contado_por"] == "test@curifor.com"


def test_producto_con_evidencia_no_queda_contado_sin_ella(client):
    _cargar(client, FILAS_OK)
    item = _items(client)["P-B"]
    url = f"/api/inventario-ciclico/items/{item['id']}"
    assert client.patch(url, json={"cantidad_contada": 5}).json()["estado"] == "falta_evidencia"

    r = client.post(f"{url}/evidencias", files={"archivo": ("foto.jpg", b"\xff\xd8jpeg", "image/jpeg")})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["estado"] == "sin_diferencia"
    ev = body["evidencias"][0]
    foto = client.get(f"/api/inventario-ciclico/evidencias/{ev['id']}")
    assert foto.content == b"\xff\xd8jpeg"
    assert foto.headers["content-type"] == "image/jpeg"


def test_evidencia_rechaza_tipo_y_tamano(client):
    _cargar(client, FILAS_OK)
    url = f"/api/inventario-ciclico/items/{_items(client)['P-B']['id']}/evidencias"
    assert client.post(url, files={"archivo": ("a.exe", b"MZ", "application/x-msdownload")}).status_code == 400
    grande = b"0" * (4 * 1024 * 1024 + 1)
    assert client.post(url, files={"archivo": ("a.jpg", grande, "image/jpeg")}).status_code == 400


# --------------------------- permisos --------------------------- #
def test_sin_rol_no_entra(client, como):
    como("noadmin@curifor.com")
    assert client.get("/api/inventario-ciclico/yo").json()["rol"] is None
    assert client.get("/api/inventario-ciclico/resumen").status_code == 403


def test_bodega_cuenta_solo_su_sucursal_y_no_carga(client, como, bodega):
    _cargar(client, FILAS_OK + [["P-T", "x", "TALCA", "A", 1, 1, ""]])
    otra = _items(client)["P-T"]

    como(bodega)
    assert client.get("/api/inventario-ciclico/yo").json() == {"rol": "bodega", "sucursales": ["LINDEROS"]}
    mios = _items(client)
    assert "P-T" not in mios and "P-A" in mios
    assert client.patch(f"/api/inventario-ciclico/items/{mios['P-A']['id']}", json={"cantidad_contada": 10}).status_code == 200
    assert client.patch(f"/api/inventario-ciclico/items/{otra['id']}", json={"cantidad_contada": 1}).status_code == 404
    assert client.patch(
        f"/api/inventario-ciclico/items/{mios['P-A']['id']}", json={"requiere_evidencia": True}
    ).status_code == 403
    assert _cargar(client, FILAS_OK).status_code == 403


def test_rol_admin_sin_ser_admin_de_la_plataforma(client, como, db_session):
    db_session.add(IcRol(email="noadmin@curifor.com", rol="admin"))
    db_session.commit()
    como("noadmin@curifor.com")
    assert _cargar(client, FILAS_OK).status_code == 200


# --------------------------- seguimiento --------------------------- #
def test_resumen_por_sucursal(client, db_session):
    for n in range(10):
        db_session.add(StockUnificado(producto=f"S{n}", sucursal_id="LINDEROS", stock=1))
    db_session.commit()
    _cargar(client, FILAS_OK)
    items = _items(client)
    client.patch(f"/api/inventario-ciclico/items/{items['P-A']['id']}", json={"cantidad_contada": 12})
    client.patch(f"/api/inventario-ciclico/items/{items['P-C']['id']}", json={"cantidad_contada": 1})
    client.patch(f"/api/inventario-ciclico/items/{items['P-B']['id']}", json={"cantidad_contada": 5})

    (fila,) = client.get("/api/inventario-ciclico/resumen", params={"semana": SEMANA}).json()
    assert fila["sucursal_id"] == "LINDEROS"
    assert (fila["asignados"], fila["contados"], fila["pendientes"]) == (4, 3, 1)
    assert fila["falta_evidencia"] == 1
    assert fila["con_diferencia"] == 2
    assert fila["diferencia_sobrante"] == 2000
    assert fila["diferencia_faltante"] == -1000
    assert fila["clases_faltantes"] == []
    assert fila["productos_con_stock"] == 10
    assert fila["contados_en_el_ano"] == 3
    assert client.get("/api/inventario-ciclico/semanas").json() == ["2026-09-21"]


# --------------------------- permisos del modulo --------------------------- #
def test_admin_asigna_bodega_y_bodega_no_ve_permisos(client, como, db_session):
    db_session.add(Usuario(email="nueva@curifor.com", password_hash=hash_password("x")))
    db_session.commit()
    r = client.put("/api/inventario-ciclico/roles/Nueva@curifor.com", json={"rol": "bodega", "sucursales": ["CURICO"]})
    assert r.status_code == 200, r.text
    assert r.json() == {
        "email": "nueva@curifor.com", "rol": "bodega", "sucursales": ["CURICO"],
        "nombre": None, "tiene_usuario": True,
    }
    assert client.put("/api/inventario-ciclico/roles/x@y.cl", json={"rol": "bodega", "sucursales": ["CD REPUESTOS"]}).status_code == 400
    assert client.put("/api/inventario-ciclico/roles/x@y.cl", json={"rol": "jefe"}).status_code == 422
    assert "CD REPUESTOS" not in client.get("/api/inventario-ciclico/sucursales").json()

    como("nueva@curifor.com")
    assert client.get("/api/inventario-ciclico/yo").json() == {"rol": "bodega", "sucursales": ["CURICO"]}
    assert client.get("/api/inventario-ciclico/roles").status_code == 403

    como("test@curifor.com")
    assert client.delete("/api/inventario-ciclico/roles/nueva@curifor.com").status_code == 204
    como("nueva@curifor.com")
    assert client.get("/api/inventario-ciclico/yo").json()["rol"] is None
