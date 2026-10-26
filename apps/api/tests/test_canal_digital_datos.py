"""Pestana Datos de Canal Digital: venta por mes, cobertura de datos, fuentes y que leerla no escriba nada."""
import datetime as dt
from types import SimpleNamespace

import pytest
from sqlalchemy import event

from src.canal_digital.corrida import DatosProducto
from src.models import (
    CanalDigitalBodega, CanalDigitalLinea, CanalDigitalPolitica, CanalDigitalVenta, LeadTimeProveedorSucursal,
    PrecioProducto, ProveedorProducto, StockTransito, StockUnificado, Sugerido,
)
from src.routers import canal_digital as router_cd
from src.services import canal_digital_calculo as calc
from src.services import canal_digital_datos as datos
from src.services import canal_digital_service as svc

HOY = dt.date(2026, 10, 26)
ANCLA = dt.date(2026, 10, 1)
TABLAS = (CanalDigitalBodega, CanalDigitalPolitica, CanalDigitalVenta, CanalDigitalLinea)


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


def _conteos(db):
    return {t.__tablename__: db.query(t).count() for t in TABLAS}


@pytest.fixture()
def con_datos(db_session):
    """Tres productos con venta hasta sep-2026 y, entre todos, cada caso de cobertura una vez."""
    db = db_session
    svc.asegurar_bodega(db, "430")
    svc.reemplazar_ventas(
        db, "430", _filas("20 ALTO", 20) + _filas("20 VIEJO", 2) + _filas("20 MEDIO", 5) + _filas("20 BAJO", 1)
    )
    # 20 VIEJO es un codigo que reemplaza 20 ALTO: su venta se funde bajo el vigente (3 productos, no 4)
    db.add(Sugerido(tenant_id="curifor", producto="20 ALTO", sucursal_id="LINDEROS", reemplazos="20 VIEJO"))
    for p, c in (("20 ALTO", 1000), ("20 MEDIO", 500)):  # 20 BAJO no tiene costo
        db.add(PrecioProducto(tenant_id="curifor", producto=p, glosa=f"GLOSA {p}", costo=c))
    db.add_all([
        StockUnificado(tenant_id="curifor", producto="20 ALTO", bodega="BODEGA ML", stock=10),
        StockUnificado(tenant_id="curifor", producto="20 ALTO", bodega="BODEGA ML-FULL", stock=3),
    ])  # 20 MEDIO tiene costo pero ningun stock; 20 BAJO ni lo uno ni lo otro
    db.add_all([
        ProveedorProducto(tenant_id="curifor", producto="20 ALTO", proveedor="PROV A"),
        ProveedorProducto(tenant_id="curifor", producto="20 MEDIO", proveedor="PROV B"),
        LeadTimeProveedorSucursal(tenant_id="curifor", proveedor="PROV A", sucursal_id=None,
                                  lead_time_dias=6.0, n_muestras=12),
        LeadTimeProveedorSucursal(tenant_id="curifor", proveedor="PROV B", sucursal_id=None,
                                  lead_time_dias=9.0, n_muestras=2),
    ])
    db.add_all([
        StockTransito(tenant_id="curifor", producto="20 ALTO", sucursal_id="SUC430", cantidad=7),
        StockTransito(tenant_id="curifor", producto="20 ALTO", sucursal_id="LINDEROS", cantidad=40),
        StockTransito(tenant_id="curifor", producto="20 MEDIO", sucursal_id="LINDEROS", cantidad=5),
    ])
    db.commit()


def _producto(**kw) -> SimpleNamespace:
    """Un producto de la corrida con solo lo que la cobertura mira."""
    base = dict(codigo="X", plazo_confianza=calc.CONFIANZA_PLAZO_MUESTRAS_OK, costo_actual=100.0,
                costo_respaldo=calc.COSTO_CON_STOCK, stock_disponible=0.0, stock_aparte=0.0, transito=0.0,
                transito_cualquier_destino=0.0)
    return SimpleNamespace(datos=DatosProducto(**{**base, **kw}))


# --- cobertura: pura, con productos inventados ---------------------------------------------------------------

def test_cobertura_cuenta_cada_dato_de_la_corrida():
    corrida = SimpleNamespace(productos=(
        _producto(codigo="A", stock_disponible=5, stock_aparte=2, transito=7, transito_cualquier_destino=47),
        _producto(codigo="B", plazo_confianza=calc.CONFIANZA_PLAZO_POCAS_MUESTRAS, costo_actual=None,
                  costo_respaldo=calc.COSTO_SIN_COSTO, transito=0, transito_cualquier_destino=3),
        _producto(codigo="C", plazo_confianza=calc.CONFIANZA_PLAZO_SIN_PROVEEDOR,
                  costo_respaldo=calc.COSTO_SIN_RESPALDO_STOCK),
        _producto(codigo="D", plazo_confianza=calc.CONFIANZA_PLAZO_SIN_PROVEEDOR, stock_disponible=-4),
    ))
    assert datos.cobertura(corrida) == {
        "productos": 4,
        "con_proveedor": 2, "sin_proveedor": 2, "proveedor_menos_5_muestras": 1,
        "con_costo": 3, "sin_costo": 1, "costo_sin_respaldo_stock": 1,
        "con_stock_bodega": 1, "sin_stock_bodega": 3, "con_stock_aparte": 1,
        "con_transito_a_la_bodega": 1, "con_transito_otro_destino": 2,
    }


def test_cobertura_de_una_corrida_sin_productos_es_todo_cero():
    cob = datos.cobertura(SimpleNamespace(productos=()))
    assert set(cob.values()) == {0}


def test_el_transito_solo_a_la_bodega_no_cuenta_como_otro_destino():
    corrida = SimpleNamespace(productos=(_producto(transito=7, transito_cualquier_destino=7),))
    cob = datos.cobertura(corrida)
    assert cob["con_transito_a_la_bodega"] == 1 and cob["con_transito_otro_destino"] == 0


# --- venta por mes --------------------------------------------------------------------------------------------

def _venta(periodo, producto, brutas, devueltas=0.0, lineas=1, semana="2025-01-06"):
    return CanalDigitalVenta(
        tenant_id="curifor", bodega="430", producto=producto, semana=semana, periodo=periodo,
        unid_brutas=brutas, unid_devueltas=devueltas, valor_costo=0.0, unid_liquidacion=0.0, n_lineas=lineas,
    )


def test_la_venta_por_mes_trae_14_periodos_como_maximo_del_mas_reciente_al_mas_antiguo(db_session):
    periodos = [f"{2025 + (m // 12)}{m % 12 + 1:02d}" for m in range(20)]  # 202501 .. 202608
    for i, p in enumerate(periodos):
        db_session.add(_venta(p, "20 A", brutas=10 + i, devueltas=2, lineas=3))
        db_session.add(_venta(p, "20 B", brutas=5, devueltas=0, lineas=1, semana="2025-01-13"))
    otra = _venta("202607", "20 A", brutas=999, lineas=9)
    otra.bodega = "OTRA"  # la venta de otra bodega no cuenta
    db_session.add(otra)
    db_session.commit()

    meses = datos.ventas_por_mes(db_session, "430")

    assert len(meses) == 14
    assert [m["periodo"] for m in meses] == sorted(periodos, reverse=True)[:14]
    ultimo = meses[0]  # 202608 es el indice 19: 10+19 brutas y 5 de la otra fila, menos 2 devueltas
    assert ultimo == {"periodo": "202608", "unidades_netas": 29 + 5 - 2, "unidades_devueltas": 2, "lineas": 4}


def test_la_venta_por_mes_se_calcula_con_una_sola_consulta(db_session):
    for m in range(1, 13):
        db_session.add(_venta(f"2025{m:02d}", "20 A", 10))
        db_session.add(_venta(f"2025{m:02d}", "20 B", 10, semana="2025-01-13"))
    db_session.commit()
    sentencias = []
    motor = db_session.get_bind()

    def _registrar(conn, cursor, statement, parameters, context, executemany):
        sentencias.append(statement)

    event.listen(motor, "before_cursor_execute", _registrar)
    try:
        meses = datos.ventas_por_mes(db_session, "430")
    finally:
        event.remove(motor, "before_cursor_execute", _registrar)
    assert len(meses) == 12 and len(sentencias) == 1
    assert "GROUP BY" in sentencias[0].upper()


def test_un_mes_cargado_sin_lineas_se_ve_con_cero_lineas(db_session):
    db_session.add(_venta("202609", "20 A", 10, lineas=0))
    db_session.commit()
    assert datos.ventas_por_mes(db_session, "430") == [
        {"periodo": "202609", "unidades_netas": 10, "unidades_devueltas": 0, "lineas": 0}
    ]


def test_sin_venta_cargada_la_tabla_de_meses_esta_vacia(db_session):
    assert datos.ventas_por_mes(db_session, "430") == []


# --- fuentes: el estado que se ve en cada tarjeta ------------------------------------------------------------

def _cob(**kw):
    base = {"productos": 100, "con_proveedor": 100, "sin_proveedor": 0, "proveedor_menos_5_muestras": 0,
            "con_costo": 100, "sin_costo": 0, "costo_sin_respaldo_stock": 0, "con_stock_bodega": 60,
            "sin_stock_bodega": 40, "con_stock_aparte": 5, "con_transito_a_la_bodega": 10,
            "con_transito_otro_destino": 4}
    return {**base, **kw}


def _ventas(**kw):
    base = {"ultimo_periodo_cargado": "202609", "meses_sin_cargar": 0, "periodo_desde": "202501", "filas": 7000,
            "productos": 700, "lineas": 12000, "lineas_periodo_hasta": "202609", "por_mes": []}
    return {**base, **kw}


def _fuentes(cob=None, ventas=None, aviso=None, agrupados=3, plazos=None):
    out = datos.fuentes(cob or _cob(), ventas or _ventas(), aviso or {"codigos_en_dos_grupos": 0}, agrupados, plazos)
    return {f["nombre"]: f for f in out}


def test_hay_una_linea_por_fuente_en_el_orden_acordado():
    assert list(_fuentes()) == [
        "Ventas del canal", "Stock de la bodega", "Plazos de entrega", "Costos", "Grupos de reemplazo", "Tránsito",
    ]


def test_todo_en_orden_deja_las_fuentes_en_ok():
    f = _fuentes()
    assert {x["estado"] for x in f.values()} == {"ok"}
    assert f["Ventas del canal"]["detalle"].startswith("Al día: cargada hasta 09-2026")


@pytest.mark.parametrize("faltan,texto", [(1, "Faltan 1 mes cerrado"), (3, "Faltan 3 meses cerrados")])
def test_la_venta_atrasada_dice_cuantos_meses_cerrados_faltan(faltan, texto):
    f = _fuentes(ventas=_ventas(meses_sin_cargar=faltan))["Ventas del canal"]
    assert f["estado"] == "aviso" and texto in f["detalle"] and "09-2026" in f["detalle"]


def test_sin_venta_cargada_es_falta():
    f = _fuentes(ventas=_ventas(ultimo_periodo_cargado=None, meses_sin_cargar=None, lineas=0))["Ventas del canal"]
    assert f["estado"] == "falta" and "Todavía no hay" in f["detalle"]


def test_los_plazos_distinguen_sin_proveedor_pocas_muestras_y_ninguno():
    aviso = _fuentes(cob=_cob(con_proveedor=72, sin_proveedor=28, proveedor_menos_5_muestras=5),
                     plazos=dt.date(2026, 10, 20))["Plazos de entrega"]
    assert aviso["estado"] == "aviso"
    assert "28 de 100 productos sin proveedor: usan 3 días de respaldo" in aviso["detalle"]
    assert "20-10-2026" in aviso["detalle"]
    ninguno = _fuentes(cob=_cob(con_proveedor=0, sin_proveedor=100))["Plazos de entrega"]
    assert ninguno["estado"] == "falta"


def test_costos_sin_costo_o_sin_respaldo_avisan_y_sin_ningun_costo_falta():
    assert _fuentes(cob=_cob(con_costo=90, sin_costo=10))["Costos"]["estado"] == "aviso"
    assert _fuentes(cob=_cob(costo_sin_respaldo_stock=7))["Costos"]["estado"] == "aviso"
    assert _fuentes(cob=_cob(con_costo=0, sin_costo=100))["Costos"]["estado"] == "falta"


def test_sin_nada_de_stock_en_la_bodega_es_falta():
    f = _fuentes(cob=_cob(con_stock_bodega=0, sin_stock_bodega=100))["Stock de la bodega"]
    assert f["estado"] == "falta"


def test_codigos_en_dos_grupos_son_un_aviso():
    f = _fuentes(aviso={"codigos_en_dos_grupos": 2})["Grupos de reemplazo"]
    assert f["estado"] == "aviso" and "2 códigos figuran en dos grupos" in f["detalle"]


def test_sin_pedidos_en_camino_a_la_bodega_es_aviso_y_nombra_los_de_otro_destino():
    f = _fuentes(cob=_cob(con_transito_a_la_bodega=0, con_transito_otro_destino=4))["Tránsito"]
    assert f["estado"] == "aviso" and "4 tienen pedidos en camino a otro destino" in f["detalle"]


def test_sin_productos_las_fuentes_derivadas_avisan_en_vez_de_dar_ok():
    f = _fuentes(cob=_cob(productos=0, con_proveedor=0, con_costo=0, con_stock_bodega=0, sin_stock_bodega=0,
                          con_transito_a_la_bodega=0, con_transito_otro_destino=0, con_stock_aparte=0))
    assert [f[n]["estado"] for n in ("Stock de la bodega", "Plazos de entrega", "Costos", "Grupos de reemplazo",
                                      "Tránsito")] == ["aviso"] * 5


def test_como_cargar_son_entre_3_y_5_pasos_y_nombran_el_script():
    pasos = datos.COMO_CARGAR
    assert 3 <= len(pasos) <= 5
    assert any("canal_digital_cargar_ventas.py" in p and "--publicar-lineas" in p for p in pasos)


# --- la ruta -------------------------------------------------------------------------------------------------

def test_datos_arma_ventas_cobertura_fuentes_validaciones_y_como_cargar(client, con_datos):
    r = client.get("/api/canal-digital/datos")
    assert r.status_code == 200, r.text
    d = r.json()
    assert list(d) == ["ventas", "cobertura", "fuentes", "validaciones", "como_cargar"]

    v = d["ventas"]
    assert v["ultimo_periodo_cargado"] == "202609" and v["meses_sin_cargar"] == 0
    assert v["periodo_desde"] == "202509" and v["lineas"] == 0 and v["lineas_periodo_hasta"] is None
    assert v["filas"] == 4 * 52 and v["productos"] == 4  # 20 VIEJO sigue siendo un codigo de venta aparte
    assert [m["periodo"] for m in v["por_mes"]][0] == "202609" and len(v["por_mes"]) <= 14
    assert sum(m["lineas"] for m in v["por_mes"]) == 4 * 52  # n_lineas=1 por fila, 13 meses o menos
    assert all(m["unidades_devueltas"] == 0 for m in v["por_mes"])

    assert d["cobertura"] == {
        "productos": 3,
        "con_proveedor": 2, "sin_proveedor": 1, "proveedor_menos_5_muestras": 1,
        "con_costo": 2, "sin_costo": 1, "costo_sin_respaldo_stock": 1,
        "con_stock_bodega": 1, "sin_stock_bodega": 2, "con_stock_aparte": 1,
        "con_transito_a_la_bodega": 1, "con_transito_otro_destino": 2,
    }
    estados = {f["nombre"]: f["estado"] for f in d["fuentes"]}
    assert estados == {
        "Ventas del canal": "ok", "Stock de la bodega": "ok", "Plazos de entrega": "aviso", "Costos": "aviso",
        "Grupos de reemplazo": "ok", "Tránsito": "ok",
    }
    assert 3 <= len(d["como_cargar"]) <= 5


def test_la_cobertura_y_las_validaciones_coinciden_con_las_del_resumen(client, con_datos):
    d = client.get("/api/canal-digital/datos").json()
    resumen = client.get("/api/canal-digital/resumen").json()
    assert d["cobertura"]["sin_proveedor"] == resumen["aviso"]["sin_proveedor"]
    assert d["cobertura"]["productos"] == resumen["totales"]["productos"]
    assert d["validaciones"] == resumen["validaciones"] and len(d["validaciones"]) >= 5


def test_la_venta_atrasada_se_ve_en_la_fuente_de_ventas(client, con_datos, monkeypatch):
    monkeypatch.setattr(router_cd, "_hoy", lambda: dt.date(2026, 12, 15))  # sep cargado; faltan oct y nov
    router_cd._invalidar()
    d = client.get("/api/canal-digital/datos").json()
    assert d["ventas"]["meses_sin_cargar"] == 2
    ventas = d["fuentes"][0]
    assert ventas["nombre"] == "Ventas del canal" and ventas["estado"] == "aviso" and "Faltan 2 meses cerrados" in ventas["detalle"]


def test_una_bodega_sin_venta_responde_con_las_fuentes_en_falta_o_aviso(client, db_session):
    svc.asegurar_bodega(db_session, "431")
    r = client.get("/api/canal-digital/datos", params={"bodega": "431"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ventas"]["por_mes"] == [] and d["ventas"]["ultimo_periodo_cargado"] is None
    assert d["fuentes"][0]["estado"] == "falta"
    assert d["cobertura"]["productos"] == 0


def test_la_430_sin_ningun_dato_tambien_responde(client, db_session):
    r = client.get("/api/canal-digital/datos")
    assert r.status_code == 200, r.text
    assert r.json()["ventas"]["filas"] == 0 and r.json()["fuentes"][0]["estado"] == "falta"


def test_una_bodega_que_no_existe_da_404_y_no_se_crea(client, db_session):
    antes = _conteos(db_session)
    r = client.get("/api/canal-digital/datos", params={"bodega": "999"})
    assert r.status_code == 404 and "999" in r.json()["detail"]
    assert _conteos(db_session) == antes
    assert db_session.query(CanalDigitalBodega).filter_by(bodega="999").count() == 0
    assert db_session.query(CanalDigitalPolitica).filter_by(bodega="999").count() == 0
    # repetirlo no cambia nada: sigue sin existir
    assert client.get("/api/canal-digital/datos", params={"bodega": "999"}).status_code == 404


def test_leer_datos_no_escribe_nada_en_la_base(client, con_datos, db_session):
    antes = _conteos(db_session)
    escrituras = []
    motor = db_session.get_bind()

    def _registrar(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().split(None, 1)[0].upper() in ("INSERT", "UPDATE", "DELETE"):
            escrituras.append(statement)

    event.listen(motor, "before_cursor_execute", _registrar)
    try:
        r = client.get("/api/canal-digital/datos")
    finally:
        event.remove(motor, "before_cursor_execute", _registrar)
    assert r.status_code == 200, r.text
    assert escrituras == []
    assert _conteos(db_session) == antes
