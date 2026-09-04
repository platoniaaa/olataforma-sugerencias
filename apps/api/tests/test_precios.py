"""Modulo de precios: la regla, la carga, los overrides y la exportacion."""
from datetime import date

import pytest
from fastapi.testclient import TestClient

from src.db import get_db
from src.main import app
from src.models import PrecioProducto, StockUnificado
from src.services import precios_service as svc
from src.services.auth import requiere_auth

FACT = {("liviano", "nacional"): 1.78, ("liviano", "importado"): 1.89,
        ("pesado", "nacional"): 2.16, ("pesado", "importado"): 2.30,
        ("neumatico", "nacional"): 1.33, ("neumatico", "importado"): 1.33}
RUB = {"71": {"tipo": "Liviano", "procedencia_forzada": None},
       "13": {"tipo": "Pesado", "procedencia_forzada": None},
       "86": {"tipo": "Liviano", "procedencia_forzada": "Nacional"},
       "95": {"tipo": "Sugerido", "procedencia_forzada": None}}


def _fila(**kw):
    base = {"glosa": "AMORTIGUADOR", "rubro": "71", "procedencia_maestro": "NACIONAL",
            "costo": 10000, "stock": 5, "stock_transito": 0,
            "ult_recep_importado": None, "ult_pe_nacional": None, "precio_sugerido": None}
    base.update(kw)
    return base


# ------------------------------------------------------------------ la regla
def test_costo_por_factor_nacional():
    r = svc.calcular(_fila(), None, FACT, RUB)
    assert r["tipo"] == "Liviano" and r["tipo_origen"] == "rubro"
    assert r["procedencia_final"] == "Nacional" and r["procedencia_origen"] == "maestro"
    assert r["factor"] == 1.78
    assert r["precio_calculado"] == 17800 and r["precio_final"] == 17800
    assert r["estado"] == "OK"


def test_compras_deciden_procedencia_gana_la_mas_reciente():
    r = svc.calcular(_fila(ult_recep_importado=date(2026, 6, 1), ult_pe_nacional=date(2026, 3, 1)), None, FACT, RUB)
    assert r["procedencia_final"] == "Importado" and r["procedencia_origen"] == "compras"
    assert r["precio_final"] == round(10000 * 1.89)
    r = svc.calcular(_fila(ult_recep_importado=date(2026, 1, 1), ult_pe_nacional=date(2026, 3, 1)), None, FACT, RUB)
    assert r["procedencia_final"] == "Nacional"


def test_rubro_forzado_gana_a_compras():
    r = svc.calcular(_fila(rubro="86", ult_recep_importado=date(2026, 6, 1)), None, FACT, RUB)
    assert r["procedencia_final"] == "Nacional" and r["procedencia_origen"] == "rubro"


def test_glosa_neu_es_neumatico_aunque_el_rubro_diga_otra_cosa():
    r = svc.calcular(_fila(glosa="NEUMATICO 265/70 R16"), None, FACT, RUB)
    assert r["tipo"] == "Neumatico" and r["tipo_origen"] == "glosa"
    assert r["precio_final"] == round(10000 * 1.33)
    # "SENSOR PRESION NEUMATICO" no empieza con NEU: sigue siendo del rubro.
    assert svc.calcular(_fila(glosa="SENSOR PRESION NEUMATICO"), None, FACT, RUB)["tipo"] == "Liviano"


def test_sin_stock_es_precio_cero_salvo_transito():
    assert svc.calcular(_fila(stock=0), None, FACT, RUB)["precio_final"] == 0
    assert svc.calcular(_fila(stock=0), None, FACT, RUB)["estado"] == "SIN STOCK"
    r = svc.calcular(_fila(stock=0, stock_transito=3), None, FACT, RUB)
    assert r["precio_final"] == 17800 and r["estado"] == "OK"


def test_sugerido_toma_la_lista_del_proveedor():
    r = svc.calcular(_fila(rubro="95", precio_sugerido=12345.6), None, FACT, RUB)
    assert r["estado"] == "SUGERIDO" and r["precio_final"] == 12346
    r = svc.calcular(_fila(rubro="95", precio_sugerido=None), None, FACT, RUB)
    assert r["estado"] == "SIN REVISION" and r["precio_final"] is None


def test_sin_procedencia_ni_factor_queda_sin_revision():
    r = svc.calcular(_fila(procedencia_maestro=""), None, FACT, RUB)
    assert r["procedencia_final"] == "SIN REVISION" and r["estado"] == "SIN REVISION"
    assert r["precio_final"] is None


def test_precio_fijo_gana_a_todo_incluso_sin_stock():
    r = svc.calcular(_fila(stock=0), {"precio_fijo": 990}, FACT, RUB)
    assert r["precio_final"] == 990 and r["estado"] == "FIJO"
    assert r["precio_calculado"] == 0  # la regla se sigue calculando, para verla


def test_congelado_ignora_el_costo_nuevo():
    ov = {"congelar": True, "congelado_precio": 17800}
    r = svc.calcular(_fila(costo=99999), ov, FACT, RUB)
    assert r["precio_final"] == 17800 and r["estado"] == "CONGELADO"
    assert r["precio_calculado"] == round(99999 * 1.78)


def test_no_producto_no_lleva_precio_y_manual_cambia_factor():
    assert svc.calcular(_fila(), {"no_producto": True}, FACT, RUB)["precio_final"] is None
    # Sin stock manda antes que "no es producto", como el .exe: sale en 0.
    r = svc.calcular(_fila(stock=0), {"no_producto": True}, FACT, RUB)
    assert r["precio_final"] == 0 and r["estado"] == "SIN STOCK"
    r = svc.calcular(_fila(), {"tipo_manual": "Pesado", "procedencia_manual": "Importado"}, FACT, RUB)
    assert r["factor"] == 2.30 and r["tipo_origen"] == "manual" and r["procedencia_origen"] == "manual"


def test_redondea_como_excel_la_mitad_hacia_arriba():
    # 54.115 x 2,30 = 124.464,5: Excel da 124.465; el round de Python daba 124.464.
    r = svc.calcular(_fila(rubro="13", procedencia_maestro="IMPORTADO", costo=54115), None, FACT, RUB)
    assert r["precio_final"] == 124465
    assert svc.redondear(2.5) == 3 and svc.redondear(3.5) == 4 and svc.redondear(2.4) == 2


def test_alias_de_tipo_encuentra_el_factor():
    fact = {**FACT, ("bateria", "nacional"): 1.33}
    rub = {**RUB, "58": {"tipo": "Baterias", "procedencia_forzada": None}}
    r = svc.calcular(_fila(rubro="58"), None, fact, rub)
    assert r["factor"] == 1.33 and r["estado"] == "OK"


# ------------------------------------------------------------- carga + API
LISTA = [
    {"producto": "71 AAA1", "glosa": "AMORT DEL", "rubro": "71", "tipo": "Liviano",
     "procedencia_maestro": "NACIONAL", "procedencia_final": "Nacional", "costo": 10000,
     "precio_erp": 15000, "stock": 5, "stock_proyectado": 0, "obs_precio": "", "precio_fijo": "",
     "congelar": "0", "ultima_venta": "2026-05-01"},
    {"producto": "13 BBB2", "glosa": "FILTRO", "rubro": "13", "tipo": "Pesado",
     "procedencia_maestro": "IMPORTADO", "procedencia_final": "Importado", "costo": 5000,
     "precio_erp": 11500, "stock": 0, "stock_proyectado": 0, "obs_precio": "piso", "precio_fijo": "990",
     "congelar": "0"},
    {"producto": "71 CCC3", "glosa": "BUJIA", "rubro": "71", "tipo": "Pesado",   # tipo a mano en el Excel
     "procedencia_maestro": "NACIONAL", "procedencia_final": "Nacional", "costo": 1000,
     "precio_erp": 2000, "stock": 2, "stock_proyectado": 0, "obs_precio": "", "precio_fijo": "",
     "congelar": "x", "precio_optimo_excel": 2160},
]
POLITICA = [{"tipo": t.capitalize(), "procedencia": p.capitalize(), "factor": f} for (t, p), f in FACT.items()]
RUBROS = [{"rubro": r, "tipo": v["tipo"], "procedencia_forzada": v["procedencia_forzada"]} for r, v in RUB.items()]


@pytest.fixture()
def lista_cargada(db_session):
    from src.services import politica_precio_service as pol
    pol.sembrar(db_session, POLITICA, RUBROS)
    svc.cargar_maestro(db_session, LISTA, reemplazar=True, usuario="test@curifor.com")
    svc.conservar_clasificacion_excel(db_session, "test@curifor.com")
    return db_session


def test_carga_ignora_precio_fijo_sin_obs_y_siembra_procedencia_vacia(db_session):
    from src.services import politica_precio_service as pol
    # "Valvoline;;1.3": un factor para las dos procedencias.
    r = pol.sembrar(db_session, POLITICA + [{"tipo": "Valvoline", "procedencia": "", "factor": "1.3"}], RUBROS)
    assert r["factores"] == len(POLITICA) + 2
    assert pol.factores(db_session)[("valvoline", "importado")] == 1.3
    # Precio fijo sin Obs: la formula del Excel lo ignora, la carga tambien.
    r = svc.cargar_maestro(db_session, [dict(LISTA[1], obs_precio="", precio_fijo="990")], reemplazar=True, usuario="x")
    assert r["precio_fijo_sin_obs_ignorado"] == 1 and r["overrides"] == 0


def test_carga_crea_filas_overrides_y_rescata_lo_manual(lista_cargada):
    db = lista_cargada
    filas = {p.producto: p for p in db.query(PrecioProducto).all()}
    assert set(filas) == {"71 AAA1", "13 BBB2", "71 CCC3"}
    ovs = svc._overrides(db)
    assert ovs["13 BBB2"]["precio_fijo"] == 990 and ovs["13 BBB2"]["obs"] == "piso"
    assert ovs["71 CCC3"]["congelar"] and ovs["71 CCC3"]["congelado_precio"] == 2160
    # 71 CCC3 decia Pesado en el Excel y el rubro 71 es Liviano: se rescata como manual.
    assert ovs["71 CCC3"]["tipo_manual"] == "Pesado"
    assert "71 AAA1" not in ovs


def test_recalculo_aplica_reglas_y_es_idempotente(lista_cargada):
    db = lista_cargada
    r = svc.recalcular(db, usuario="test@curifor.com")
    assert r["productos"] == 3
    f = {p.producto: p for p in db.query(PrecioProducto).all()}
    assert f["71 AAA1"].precio_final == 17800 and f["71 AAA1"].estado == "OK"
    assert f["13 BBB2"].precio_final == 990 and f["13 BBB2"].estado == "FIJO"
    assert f["71 CCC3"].precio_final == 2160 and f["71 CCC3"].estado == "CONGELADO"
    assert f["71 CCC3"].factor == 2.16  # Pesado/Nacional por el tipo manual
    # Segunda corrida sin novedades: cero cambios.
    assert svc.recalcular(db, usuario="test@curifor.com")["cambios"] == 0


def test_recalculo_detecta_cambio_de_stock_y_lo_anota(lista_cargada):
    db = lista_cargada
    svc.recalcular(db)
    db.add(StockUnificado(tenant_id="curifor", producto="71 AAA1", bodega="B1", sucursal_id="LINDEROS", stock=0))
    db.commit()
    r = svc.recalcular(db)
    assert r["por_campo"]["stock"] == 1 and r["por_campo"]["precio"] == 1
    p = db.query(PrecioProducto).filter_by(producto="71 AAA1").one()
    assert p.precio_final == 0 and p.estado == "SIN STOCK" and p.cambios_pendientes == 2
    d = svc.detalle(db, "71 AAA1")
    assert {c["campo"] for c in d["cambios"]} == {"stock", "precio"}


def test_api_listar_filtrar_y_detalle(client, lista_cargada):
    svc.recalcular(lista_cargada)
    r = client.get("/api/precios", params={"estado": "FIJO"})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1 and body["items"][0]["producto"] == "13 BBB2"
    assert body["items"][0]["precio_fijo"] == 990
    det = client.get("/api/precios/13 BBB2").json()
    assert det["estado"] == "FIJO"
    # La ficha trae su historia. Sin el schema de detalle FastAPI recortaba estas
    # dos listas y la pantalla se caia al abrir un producto.
    assert isinstance(det["cambios"], list) and isinstance(det["envios"], list)
    assert client.get("/api/precios/filtros").json()["rubros"] == ["13", "71"]
    assert client.get("/api/precios/resumen").json()["productos"] == 3


def test_api_override_congela_y_descongela(client, lista_cargada):
    svc.recalcular(lista_cargada)
    r = client.put("/api/precios/71 AAA1/override", json={"congelar": True, "obs": "campania"})
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "CONGELADO" and r.json()["congelado_precio"] == 17800
    # Sube el costo: el precio no se mueve.
    p = lista_cargada.query(PrecioProducto).filter_by(producto="71 AAA1").one()
    p.costo = 50000
    lista_cargada.commit()
    svc.recalcular(lista_cargada, refrescar_insumos=False)
    assert client.get("/api/precios/71 AAA1").json()["precio_final"] == 17800
    r = client.delete("/api/precios/71 AAA1/override")
    assert r.json()["estado"] == "OK" and r.json()["precio_final"] == round(50000 * 1.78)


def test_api_crear_producto_manual_sobrevive_recarga(client, lista_cargada):
    r = client.post("/api/precios", json={"producto": "71 NUEVO1", "glosa": "PIEZA NUEVA",
                                          "costo": 3000, "stock": 1, "precio_fijo": 7990})
    assert r.status_code == 201, r.text
    assert r.json()["origen"] == "manual" and r.json()["precio_final"] == 7990
    svc.cargar_maestro(lista_cargada, LISTA, reemplazar=True, usuario="x")
    assert client.get("/api/precios/71 NUEVO1").status_code == 200


def test_exportar_erp_y_solo_diferencias(client, lista_cargada):
    svc.recalcular(lista_cargada)
    r = client.get("/api/precios/exportar")
    assert r.status_code == 200 and r.headers["X-Filas"] == "3"
    assert r.headers["content-type"].startswith("application/vnd.openxmlformats")
    # Nada cambio: el delta viene vacio.
    r = client.get("/api/precios/exportar", params={"solo_diferencias": True})
    assert r.headers["X-Filas"] == "0"
    # Se congela uno en otro precio: solo ese sale.
    client.put("/api/precios/71 AAA1/override", json={"precio_fijo": 20000})
    r = client.get("/api/precios/exportar", params={"solo_diferencias": True})
    assert r.headers["X-Filas"] == "1"
    assert client.get("/api/precios/resumen").json()["pendientes_envio"] == 0


def test_politica_solo_admin_y_recalcula(client, lista_cargada, db_session):
    svc.recalcular(lista_cargada)
    r = client.put("/api/precios/politica/factores",
                   json={"filas": [{"tipo": "Liviano", "procedencia": "Nacional", "factor": 2.0}]})
    assert r.status_code == 200, r.text
    assert client.get("/api/precios/71 AAA1").json()["precio_final"] == 20000
    # Un factor <= 1 vende bajo el costo: se rechaza.
    r = client.put("/api/precios/politica/factores",
                   json={"filas": [{"tipo": "Liviano", "procedencia": "Nacional", "factor": 1.0}]})
    assert r.status_code == 422

    # El no-admin no puede tocar la politica ni un precio (no esta en EMAILS_PRECIOS).
    app.dependency_overrides[requiere_auth] = lambda: "noadmin@curifor.com"
    try:
        with TestClient(app) as c2:
            assert c2.put("/api/precios/politica/factores", json={"filas": []}).status_code == 403
            assert c2.put("/api/precios/71 AAA1/override", json={"congelar": True}).status_code == 403
            assert c2.get("/api/precios").status_code == 200  # ver, si puede
    finally:
        app.dependency_overrides[requiere_auth] = lambda: "test@curifor.com"
