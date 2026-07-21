"""Tests del cierre del loop: marcar lineas del sugerido como pedidas."""
from datetime import datetime, timedelta, timezone

from src.models import LineaPedida
from src.services import pedidos_service


def test_registrar_y_listar(client):
    r = client.post("/api/compras/pedidos", json={
        "producto": "20 BXO5W30AA", "sucursal_id": "LINDEROS",
        "unidades": 10, "n_oc": "0000005758",
    })
    assert r.status_code == 201
    items = client.get("/api/compras/pedidos").json()["items"]
    assert len(items) == 1
    assert items[0]["n_oc"] == "0000005758"
    assert items[0]["creado_por"] == "test@curifor.com"


def test_el_sugerido_muestra_lo_ya_pedido(client, db_session):
    """La grilla tiene que avisar que esa linea ya se pidio."""
    client.post("/api/compras/pedidos", json={
        "producto": "20 BXO5W30AA", "sucursal_id": "LINDEROS", "unidades": 7,
    })
    items = client.get("/api/sugerido?q=20 BXO5W30AA&solo_pedir=false").json()["items"]
    fila = next(i for i in items if i["producto"] == "20 BXO5W30AA")
    assert fila["unidades_pedidas"] == 7


def test_lo_recibido_deja_de_contar(client, db_session):
    r = client.post("/api/compras/pedidos", json={
        "producto": "20 BXO5W30AA", "sucursal_id": "LINDEROS", "unidades": 7,
    }).json()
    client.post(f"/api/compras/pedidos/{r['id']}/recibida")

    pedidos = pedidos_service.pedido_por_par(db_session)
    assert ("20 BXO5W30AA", "LINDEROS") not in pedidos


def test_un_pedido_viejo_no_tapa_una_necesidad_de_hoy(db_session):
    """Pasada la ventana, el sugerido vuelve a pedirlo: la OC se perdio o ya llego."""
    db_session.add(LineaPedida(
        tenant_id="curifor", producto="P1", sucursal_id="LINDEROS", unidades=50,
        creado_en=datetime.now(timezone.utc) - timedelta(days=pedidos_service.DIAS_VIGENCIA + 5),
    ))
    db_session.commit()
    assert ("P1", "LINDEROS") not in pedidos_service.pedido_por_par(db_session)


def test_suma_varios_pedidos_del_mismo_par(client, db_session):
    for u in (3, 4):
        client.post("/api/compras/pedidos", json={
            "producto": "P1", "sucursal_id": "LINDEROS", "unidades": u,
        })
    assert pedidos_service.pedido_por_par(db_session)[("P1", "LINDEROS")] == 7


def test_eliminar(client):
    r = client.post("/api/compras/pedidos", json={
        "producto": "P1", "sucursal_id": "LINDEROS", "unidades": 3,
    }).json()
    assert client.request("DELETE", f"/api/compras/pedidos/{r['id']}").status_code == 204
    assert client.get("/api/compras/pedidos").json()["items"] == []


def test_usuario_solo_lectura_no_puede_registrar(client, db_session):
    from src.main import app
    from src.models import Usuario
    from src.services.auth import hash_password, requiere_auth

    db_session.add(Usuario(
        email="lector@x.com", password_hash=hash_password("x"), solo_lectura=True,
    ))
    db_session.commit()

    app.dependency_overrides[requiere_auth] = lambda: "lector@x.com"
    try:
        r = client.post("/api/compras/pedidos", json={
            "producto": "P1", "sucursal_id": "LINDEROS", "unidades": 3,
        })
        assert r.status_code == 403
    finally:
        app.dependency_overrides[requiere_auth] = lambda: "test@curifor.com"


def test_exportable_a_excel():
    from src.services.excel_export import LABELS

    assert "unidades_pedidas" in LABELS
