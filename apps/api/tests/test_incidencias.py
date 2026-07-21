"""Tests de la mesa de incidencias."""


def _crear(client, titulo="El sugerido no cuadra", **kw):
    payload = {"titulo": titulo, **kw}
    return client.post("/api/incidencias", json=payload)


def test_crear_guarda_el_contexto(client):
    r = _crear(
        client,
        descripcion="Dice 13 pero el stock optimo es 14",
        producto="20 BXO5W30AA",
        sucursal_id="LINDEROS",
        pantalla="/producto/20 BXO5W30AA",
    )
    assert r.status_code == 201
    inc = r.json()
    assert inc["estado"] == "abierta"
    assert inc["producto"] == "20 BXO5W30AA"
    assert inc["sucursal_id"] == "LINDEROS"
    assert inc["reportado_por"] == "test@curifor.com"


def test_titulo_vacio_rechazado(client):
    assert _crear(client, titulo="   ").status_code == 422


def test_usuario_solo_ve_sus_reportes_y_el_admin_ve_todos(client, db_session):
    from src.main import app
    from src.models import Usuario
    from src.services.auth import hash_password, requiere_auth

    db_session.add(Usuario(email="juan@x.com", password_hash=hash_password("x")))
    db_session.commit()

    _crear(client, titulo="Reporte del admin")
    app.dependency_overrides[requiere_auth] = lambda: "juan@x.com"
    try:
        _crear(client, titulo="Reporte de juan")
        mios = client.get("/api/incidencias").json()["items"]
        assert [i["titulo"] for i in mios] == ["Reporte de juan"]
    finally:
        app.dependency_overrides[requiere_auth] = lambda: "test@curifor.com"

    # El admin ve los dos.
    titulos = {i["titulo"] for i in client.get("/api/incidencias").json()["items"]}
    assert titulos == {"Reporte del admin", "Reporte de juan"}


def test_no_admin_no_puede_gestionar(client, db_session):
    from src.main import app
    from src.models import Usuario
    from src.services.auth import hash_password, requiere_auth

    db_session.add(Usuario(email="juan@x.com", password_hash=hash_password("x")))
    db_session.commit()
    inc = _crear(client).json()

    app.dependency_overrides[requiere_auth] = lambda: "juan@x.com"
    try:
        r = client.patch(f"/api/incidencias/{inc['id']}", json={"estado": "resuelta"})
        assert r.status_code == 403
    finally:
        app.dependency_overrides[requiere_auth] = lambda: "test@curifor.com"


def test_resolver_notifica_al_que_reporto(client):
    """El reporte no puede ser un buzon sin fondo: al cerrarlo se avisa."""
    inc = _crear(client, titulo="Stock erroneo").json()
    r = client.patch(
        f"/api/incidencias/{inc['id']}",
        json={"estado": "resuelta", "respuesta": "Era el archivo de origen, ya se corrigio"},
    )
    assert r.status_code == 200
    assert r.json()["resuelto_por"] == "test@curifor.com"
    assert r.json()["respuesta"].startswith("Era el archivo")

    titulos = [n["titulo"] for n in client.get("/api/notificaciones").json()["items"]]
    assert any("Stock erroneo" in t for t in titulos)


def test_estado_invalido_rechazado(client):
    inc = _crear(client).json()
    r = client.patch(f"/api/incidencias/{inc['id']}", json={"estado": "inventado"})
    assert r.status_code == 422


def test_filtrar_por_estado(client):
    a = _crear(client, titulo="Sigue abierta").json()
    b = _crear(client, titulo="Se cierra").json()
    client.patch(f"/api/incidencias/{b['id']}", json={"estado": "resuelta"})

    abiertas = client.get("/api/incidencias?estado=abierta").json()
    assert [i["id"] for i in abiertas["items"]] == [a["id"]]
    assert abiertas["abiertas"] == 1


def test_incidencia_inexistente_da_404(client):
    assert client.patch("/api/incidencias/no-existe", json={"estado": "resuelta"}).status_code == 404


def test_queda_en_auditoria(client):
    _crear(client, titulo="Algo raro en el CD")
    acciones = [it["accion"] for it in client.get("/api/auditoria").json()["items"]]
    assert "incidencia_creada" in acciones
