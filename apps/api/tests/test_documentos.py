"""Tests del modulo Documentos: enlaces a archivos que viven en SharePoint."""


def test_documentos_crear_y_listar(client):
    r = client.post("/api/documentos", json={
        "titulo": "Ventas 2024",
        "url": "https://curifor.sharepoint.com/respaldoBBDD/2024.xlsx",
        "categoria": "Ventas historicas",
        "descripcion": "Ano completo",
    })
    assert r.status_code == 201
    doc = r.json()
    assert doc["titulo"] == "Ventas 2024"
    assert doc["activo"] is True

    items = client.get("/api/documentos").json()
    assert [d["id"] for d in items] == [doc["id"]]


def test_documentos_url_invalida_rechazada(client):
    """javascript: en un href seria ejecucion de codigo en el navegador del usuario."""
    r = client.post("/api/documentos", json={
        "titulo": "Malicioso", "url": "javascript:alert(1)",
    })
    assert r.status_code == 422
    assert client.get("/api/documentos").json() == []


def test_documentos_ocultos_no_se_listan_por_defecto(client):
    doc = client.post("/api/documentos", json={
        "titulo": "Borrador", "url": "https://curifor.sharepoint.com/x.xlsx",
    }).json()
    assert client.patch(f"/api/documentos/{doc['id']}", json={"activo": False}).status_code == 200
    assert client.get("/api/documentos").json() == []
    assert len(client.get("/api/documentos?incluir_inactivos=true").json()) == 1


def test_documentos_orden_por_categoria_y_orden(client):
    for titulo, categoria, orden in [
        ("Ventas 2023", "Ventas historicas", 2),
        ("Ventas 2024", "Ventas historicas", 1),
        ("Stock bodegas", "Stock", 0),
    ]:
        client.post("/api/documentos", json={
            "titulo": titulo, "url": "https://curifor.sharepoint.com/x.xlsx",
            "categoria": categoria, "orden": orden,
        })
    titulos = [d["titulo"] for d in client.get("/api/documentos").json()]
    # Categoria alfabetica; dentro de cada una, por el campo orden.
    assert titulos == ["Stock bodegas", "Ventas 2024", "Ventas 2023"]


def test_documentos_apertura_queda_en_auditoria(client):
    doc = client.post("/api/documentos", json={
        "titulo": "Ventas 2024", "url": "https://curifor.sharepoint.com/2024.xlsx",
    }).json()
    assert client.post(f"/api/documentos/{doc['id']}/apertura").status_code == 204
    acciones = [it["accion"] for it in client.get("/api/auditoria").json()["items"]]
    assert "documento_abierto" in acciones


def test_documentos_no_admin_no_puede_crear(client):
    from src.main import app
    from src.services.auth import requiere_auth

    app.dependency_overrides[requiere_auth] = lambda: "noadmin@curifor.com"
    try:
        r = client.post("/api/documentos", json={
            "titulo": "X", "url": "https://curifor.sharepoint.com/x.xlsx",
        })
        assert r.status_code == 403
        # ...pero si puede verlos: la lista es para todo usuario autenticado.
        assert client.get("/api/documentos").status_code == 200
    finally:
        app.dependency_overrides[requiere_auth] = lambda: "test@curifor.com"


def test_documentos_eliminar(client):
    doc = client.post("/api/documentos", json={
        "titulo": "Temporal", "url": "https://curifor.sharepoint.com/tmp.xlsx",
    }).json()
    assert client.request("DELETE", f"/api/documentos/{doc['id']}").status_code == 204
    assert client.get("/api/documentos").json() == []
    assert client.request("DELETE", f"/api/documentos/{doc['id']}").status_code == 404
