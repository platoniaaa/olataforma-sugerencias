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
    # La foto de stock arranca igual que el Excel para que la primera corrida no
    # anote nada y el test mida solo lo que viene despues. Desde que la tabla
    # tiene datos, no estar en ella significa no tener: por eso "13 BBB2" -que en
    # el Excel viene en 0- se deja fuera, igual que en produccion, donde el motor
    # publica `stock_unificado` sin filas en cero.
    for cod, u in (("71 AAA1", 5), ("71 CCC3", 2)):
        db.add(StockUnificado(tenant_id="curifor", producto=cod, bodega="B1",
                              sucursal_id="LINDEROS", stock=u))
    db.commit()
    assert svc.recalcular(db)["cambios"] == 0
    db.query(StockUnificado).filter_by(producto="71 AAA1").one().stock = 0
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


def test_el_costo_viene_del_motor_no_del_catalogo_viejo(client, lista_cargada, en_catalogo):
    from src.models import DimProducto
    db = lista_cargada
    svc.recalcular(db)
    # El catalogo (CSV de carga unica) trae otro costo: NO se usa.
    en_catalogo("71 AAA1", costo=99999)
    svc.recalcular(db)
    assert db.query(PrecioProducto).filter_by(producto="71 AAA1").one().costo == 10000
    # Lo que publica el motor con el sugerido (dim_producto) SI manda.
    db.add(DimProducto(producto="71 AAA1", tenant_id="curifor", costo_unitario=12000))
    db.commit()
    r = svc.recalcular(db)
    p = db.query(PrecioProducto).filter_by(producto="71 AAA1").one()
    assert p.costo == 12000 and p.precio_final == round(12000 * 1.78) and r["por_campo"]["costo"] == 1
    # Y el costo publicado aparte (Excel de stock, todos los productos) tambien.
    r = client.post("/api/admin/precios/costos", json={"filas": [
        {"producto": "13 BBB2", "costo": 7000}, {"producto": "13 BBB2 no existe", "costo": 1},
        {"producto": "71 CCC3", "costo": ""},
    ]})
    assert r.status_code == 200 and r.json() == {"actualizados": 1, "ignorados": 2}
    assert db.query(PrecioProducto).filter_by(producto="13 BBB2").one().costo == 7000


def test_eliminar_saca_productos_pero_respeta_el_precio_fijo(client, lista_cargada):
    db = lista_cargada
    svc.recalcular(db)
    # 13 BBB2 tiene precio fijo puesto a mano: su override sobrevive al borrado.
    r = client.post("/api/admin/precios/eliminar",
                    json={"productos": ["71 AAA1", "13 BBB2", "71 NO EXISTE"]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["eliminados"] == 2 and body["no_estaban"] == 1
    assert body["overrides_conservados"] == 1 and body["conservados"] == ["13 BBB2"]
    assert client.get("/api/precios").json()["total"] == 1          # queda 71 CCC3
    assert client.get("/api/precios/71 AAA1").status_code == 404
    ovs = svc._overrides(db)
    assert "13 BBB2" in ovs and ovs["13 BBB2"]["precio_fijo"] == 990
    # Un recalculo despues del borrado no revive nada.
    assert svc.recalcular(db)["productos"] == 1


def test_el_equipo_de_precios_puede_editar_sin_ser_admin(db_session):
    # Van por defecto en el codigo (como Calibracion); EMAILS_PRECIOS en Render solo sobreescribe.
    from src.services import auth
    for email in ("fmora@curifor.com", "hgarcia@curifor.com", "mramos@curifor.com", "asalinas@curifor.com"):
        assert auth.puede_precios(email, db_session), email
    assert not auth.puede_precios("noadmin@curifor.com", db_session)
    assert auth.puede_precios("test@curifor.com", db_session)  # admin, sin estar en la lista


def test_pendientes_de_envio_se_cuentan_en_sql_y_coinciden(client, lista_cargada):
    """El contador de `resumen` tiene que dar lo mismo que la lista del export.

    Se cuenta en SQL porque materializar las 40 mil filas en cada carga de la
    pantalla hacia que Render cortara la request con un 500."""
    db = lista_cargada
    svc.recalcular(db)
    assert svc.contar_diferencias(db) == len(svc._diferencias(db)) == 3
    assert client.get("/api/precios/resumen").json()["pendientes_envio"] == 3
    # Se exporta todo: deja de haber pendientes.
    client.get("/api/precios/exportar")
    assert svc.contar_diferencias(db) == len(svc._diferencias(db)) == 0
    # Cambia un precio: vuelve a haber uno solo.
    client.put("/api/precios/71 AAA1/override", json={"precio_fijo": 12345})
    assert svc.contar_diferencias(db) == len(svc._diferencias(db)) == 1
    # Y si cambia solo el costo, tambien cuenta (el ERP recibe costo).
    client.get("/api/precios/exportar")
    p = db.query(PrecioProducto).filter_by(producto="13 BBB2").one()
    p.costo = (p.costo or 0) + 500
    db.commit()
    assert svc.contar_diferencias(db) == len(svc._diferencias(db)) == 1


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


# --- Sacar un producto de la lista ----------------------------------------------
#
# `eliminar` ya existia pero solo se llegaba por la ruta de admin y por lotes,
# pensada para la depuracion del maestro. Quien mantiene la lista necesita sacar
# UN codigo desde la pantalla, con el mismo permiso con que lo crea.


def _producto(db, codigo="71 PARA-BORRAR", **extra):
    from src.models import PrecioProducto

    datos = {"tenant_id": "curifor", "producto": codigo, "glosa": "REPUESTO",
             "rubro": "71", "costo": 1000.0, "stock": 5.0, "origen": "maestro"}
    datos.update(extra)
    p = PrecioProducto(**datos)
    db.add(p)
    db.commit()
    return p


def test_saca_un_producto_de_la_lista(db_session, client):
    from src.models import PrecioProducto

    _producto(db_session)

    r = client.delete("/api/precios/71 PARA-BORRAR")

    assert r.status_code == 200, r.text
    assert r.json()["eliminados"] == 1
    assert db_session.query(PrecioProducto).filter_by(producto="71 PARA-BORRAR").first() is None


def test_un_codigo_que_no_esta_da_404(db_session, client):
    assert client.delete("/api/precios/71 NO-EXISTE").status_code == 404


def test_el_precio_fijo_sobrevive_al_borrado(db_session, client):
    """Es una decision de una persona: si el producto vuelve, la decision vuelve
    con el. Borrarla seria irreversible y nadie la escribio dos veces."""
    from src.models import PrecioOverride, PrecioProducto

    _producto(db_session)
    db_session.add(PrecioOverride(tenant_id="curifor", producto="71 PARA-BORRAR",
                                  precio_fijo=9990.0, obs="lo pidio el jefe"))
    db_session.commit()

    r = client.delete("/api/precios/71 PARA-BORRAR")

    assert r.status_code == 200
    assert r.json()["overrides_conservados"] == 1
    assert db_session.query(PrecioProducto).filter_by(producto="71 PARA-BORRAR").first() is None
    ov = db_session.query(PrecioOverride).filter_by(producto="71 PARA-BORRAR").first()
    assert ov is not None and ov.precio_fijo == 9990.0


def test_el_override_de_pura_clasificacion_se_va_con_el_producto(db_session, client):
    """No es una decision de precio: es lo que dedujo la carga. Dejarlo seria
    basura que reaparece si el codigo vuelve por otro motivo."""
    from src.models import PrecioOverride

    _producto(db_session)
    db_session.add(PrecioOverride(tenant_id="curifor", producto="71 PARA-BORRAR",
                                  tipo_manual="Liviano"))
    db_session.commit()

    r = client.delete("/api/precios/71 PARA-BORRAR")

    assert r.json()["overrides_eliminados"] == 1
    assert db_session.query(PrecioOverride).filter_by(producto="71 PARA-BORRAR").first() is None


def test_un_codigo_con_barra_se_puede_borrar(db_session, client):
    """Los codigos llevan "/" adentro (`80 PR/51822`). Sin `:path` en la ruta, el
    servidor decodifica el %2F antes de enrutar y no calza con nada."""
    from src.models import PrecioProducto

    _producto(db_session, codigo="80 PR/51822")

    r = client.delete("/api/precios/80 PR/51822")

    assert r.status_code == 200, r.text
    assert db_session.query(PrecioProducto).filter_by(producto="80 PR/51822").first() is None


def test_borrar_no_toca_el_resto_de_la_lista(db_session, client):
    from src.models import PrecioProducto

    _producto(db_session, codigo="71 UNO")
    _producto(db_session, codigo="71 DOS")

    client.delete("/api/precios/71 UNO")

    assert db_session.query(PrecioProducto).filter_by(producto="71 DOS").first() is not None
