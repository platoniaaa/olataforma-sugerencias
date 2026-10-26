"""API de lectura y de politica de Canal Digital."""
import datetime as dt

import pytest

from src.models import CanalDigitalPolitica, PrecioProducto, StockUnificado
from src.routers import canal_digital as router_cd
from src.services import canal_digital_calculo as calc
from src.services import canal_digital_service as svc

HOY = dt.date(2026, 10, 26)
ANCLA = dt.date(2026, 10, 1)


@pytest.fixture(autouse=True)
def _fijar_hoy(monkeypatch):
    monkeypatch.setattr(router_cd, "_hoy", lambda: HOY)
    router_cd._invalidar()
    yield
    router_cd._invalidar()


def _filas(producto, por_semana):
    out = []
    for semana in calc.ventana(ANCLA)["semanas"]:
        f = dt.date.fromisoformat(semana)
        out.append({"producto": producto, "semana": semana, "periodo": f"{f.year}{f.month:02d}",
                    "unid_brutas": por_semana, "unid_devueltas": 0, "valor_costo": 100.0 * por_semana,
                    "unid_liquidacion": 0, "n_lineas": 1})
    return out


@pytest.fixture()
def con_datos(db_session):
    db = db_session
    svc.asegurar_bodega(db, "430")
    svc.reemplazar_ventas(db, "430", _filas("20 ALTO", 20) + _filas("20 MEDIO", 5) + _filas("20 BAJO", 1))
    for p, c in (("20 ALTO", 1000), ("20 MEDIO", 500), ("20 BAJO", 100)):
        db.add(PrecioProducto(tenant_id="curifor", producto=p, glosa=f"GLOSA {p}", costo=c))
    db.add(StockUnificado(tenant_id="curifor", producto="20 ALTO", bodega="BODEGA ML", stock=10))
    db.commit()


def test_resumen_trae_27_clusters_totales_y_validaciones(client, con_datos):
    r = client.get("/api/canal-digital/resumen").json()
    assert [c["cluster"] for c in r["clusters"]][:3] == ["AAA", "AAB", "AAC"] and len(r["clusters"]) == 27
    assert r["estados"]["CLASIFICADO"] == 3 and r["totales"]["productos"] == 3
    assert r["totales"]["productos_que_piden"] >= 1 and r["totales"]["sugerido_pesos"] > 0
    # con 3 productos las proporciones 80/15/5 no tienen sentido: las demas validaciones si deben pasar
    malas = [v["nombre"] for v in r["validaciones"] if not v["ok"]]
    assert malas == ["Proporciones por clase cerca de 80/15/5"], malas
    assert r["provisorio"] and r["aviso"]["ultimo_mes_con_ventas"] == "202609"


def test_productos_filtra_y_ordena_por_ventas(client, con_datos):
    r = client.get("/api/canal-digital/productos").json()
    assert [i["producto"] for i in r["items"]] == ["20 ALTO", "20 MEDIO", "20 BAJO"]
    assert r["items"][0]["stock_disponible"] == 10 and r["items"][0]["descripcion"] == "GLOSA 20 ALTO"
    uno = client.get("/api/canal-digital/productos", params={"q": "medio"}).json()
    assert [i["producto"] for i in uno["items"]] == ["20 MEDIO"] and uno["total"] == 1
    piden = client.get("/api/canal-digital/productos", params={"solo_pide": True}).json()
    assert all(i["sugerido"] > 0 for i in piden["items"])
    nuevo = client.get("/api/canal-digital/productos", params={"estado": "NUEVO"}).json()
    assert nuevo["items"] == []


def test_el_listado_se_puede_ordenar_por_valor_a_pedir(client, con_datos):
    r = client.get("/api/canal-digital/productos", params={"solo_pide": True, "orden": "sugerido"}).json()
    valores = [i["sugerido_pesos"] for i in r["items"]]
    assert valores == sorted(valores, reverse=True) and valores[0] > 0
    assert client.get("/api/canal-digital/productos", params={"orden": "raro"}).status_code == 400


def test_paso_a_paso_de_un_producto_y_404(client, con_datos):
    r = client.get("/api/canal-digital/producto/paso-a-paso", params={"producto": "20 alto"}).json()
    assert r["pasos"][0]["titulo"] == "Frecuencia de venta" and len(r["pasos"]) >= 8
    assert client.get("/api/canal-digital/producto/paso-a-paso", params={"producto": "NO EXISTE"}).status_code == 404


def test_export_csv_lleva_encabezado_y_filas(client, con_datos):
    r = client.get("/api/canal-digital/productos/export-csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    lineas = r.content.decode("utf-8-sig").strip().splitlines()
    assert lineas[0].startswith("producto;descripcion") and len(lineas) == 4


def test_leer_la_politica_trae_los_27_clusters_con_sus_modos(client, db_session):
    r = client.get("/api/canal-digital/politica").json()
    assert len(r["filas"]) == 27 and r["problemas"] == [] and "formula" in r["modos"]


def _politica_json(client):
    return client.get("/api/canal-digital/politica").json()["filas"]


def test_guardar_la_politica_cambia_el_resultado_y_deja_rastro(client, con_datos, db_session):
    antes = client.get("/api/canal-digital/resumen").json()["totales"]["sugerido_pesos"]
    filas = _politica_json(client)
    for f in filas:  # todo contra pedido: ya no se sugiere nada
        f.update(modo="contra_pedido", nivel_servicio=None, z=None, minimo_fijo=None)
    r = client.put("/api/canal-digital/politica", json={"filas": filas})
    assert r.status_code == 200, r.text
    despues = client.get("/api/canal-digital/resumen").json()["totales"]
    assert antes > 0 and despues["sugerido_pesos"] == 0 and despues["productos_que_piden"] == 0
    assert db_session.query(CanalDigitalPolitica).filter_by(modo="contra_pedido").count() == 27
    assert db_session.query(CanalDigitalPolitica).first().actualizado_por == "test@curifor.com"


def test_una_politica_con_errores_no_se_guarda(client, db_session):
    svc.asegurar_bodega(db_session, "430")
    filas = _politica_json(client)
    filas[0].update(modo="formula", nivel_servicio=0.95, z=9.9)  # z que no corresponde al nivel de servicio
    r = client.put("/api/canal-digital/politica", json={"filas": filas})
    assert r.status_code == 400 and r.json()["detail"]["problemas"]
    assert _politica_json(client)[0]["z"] != 9.9
    # incompleta
    assert client.put("/api/canal-digital/politica", json={"filas": filas[:5]}).status_code == 400
    assert client.put("/api/canal-digital/politica", json={}).status_code == 400


def test_publicar_ventas_nuevas_invalida_el_resultado_guardado(client, con_datos):
    a = client.get("/api/canal-digital/productos").json()["total"]
    from src.main import app
    from src.services.auth import requiere_admin
    app.dependency_overrides[requiere_admin] = lambda: "motor"
    client.post("/api/canal-digital/ventas", json={"bodega": "430", "filas": _filas("20 OTRO", 3)})
    # la carga reemplaza los periodos que trae: si el resultado guardado no se descartara, seguirian los 3 de antes
    despues = client.get("/api/canal-digital/productos").json()
    assert a == 3 and despues["total"] == 1 and despues["items"][0]["producto"] == "20 OTRO"
