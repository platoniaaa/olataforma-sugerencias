"""Lineas de documento del canal: POST /api/canal-digital/lineas y el recalculo completo de la venta semanal."""
import csv
import datetime as dt
import importlib.util
import itertools
import json
import math
import os
import pathlib
import threading

import pytest
from sqlalchemy import event

from src.main import app
from src.models import AuditoriaLog, CanalDigitalBodega, CanalDigitalLinea, CanalDigitalVenta
from src.routers import canal_digital as router_cd
from src.services import canal_digital_service as svc
from src.canal_digital.ventas_semanales import LineaVenta, agregar, indice_originales
from src.services.auth import requiere_admin


def lin(fecha="2026-10-14", producto="P1", cantidad=1.0, tipo_docto="FA-ELECTR REPTO", numero="1",
        tipo_venta="VTA ML", costo=100.0, periodo=None, doc_ref="", nro_doc_ref=""):
    return {
        "periodo": periodo or fecha[:4] + fecha[5:7], "tipo_docto": tipo_docto, "numero": numero, "fecha": fecha,
        "tipo_venta": tipo_venta, "producto": producto, "cantidad": cantidad, "costo_neto": costo,
        "doc_ref": doc_ref, "nro_doc_ref": nro_doc_ref,
    }


def nc(fecha, ref, cantidad=1.0, producto="P1", numero="99", costo=-100.0, doc_ref="FA-ELECTR REPTO"):
    return lin(fecha, producto, cantidad, "NC-ELECTR REPTO", numero, costo=costo, doc_ref=doc_ref, nro_doc_ref=ref)


def _ventas(db):
    """La venta guardada como {(producto, semana, periodo): (brutas, devueltas, valor, liquidacion, n)}."""
    db.expire_all()
    return {
        (v.producto, v.semana, v.periodo): (v.unid_brutas, v.unid_devueltas, v.valor_costo, v.unid_liquidacion, v.n_lineas)
        for v in db.query(CanalDigitalVenta).all()
    }


def _lineas(db):
    db.expire_all()
    return sorted(
        (l.bodega, l.periodo, l.tipo_docto, l.numero, l.fecha, l.tipo_venta, l.producto, l.cantidad, l.costo_neto,
         l.doc_ref, l.nro_doc_ref)
        for l in db.query(CanalDigitalLinea).all()
    )


# ---------------------------------------------------------------- normalizacion y validacion

def test_el_servidor_normaliza_producto_numero_y_textos(db_session):
    r = svc.reemplazar_lineas(db_session, "430", [
        lin(producto="  20 bxo5w30aa  ", numero="007720"),
        lin(producto="20  BXO5W30AA", numero=835066.0, periodo=202610),
        lin(numero="835066.0", nro_doc_ref="0012.0", doc_ref=" BOLETA-REPUESTOS "),
    ])
    assert r["lineas_cargadas"] == 3 and r["lineas_ignoradas"] == 0 and r["periodos"] == ["202610"]
    por = {(l.producto, l.numero): l for l in db_session.query(CanalDigitalLinea).all()}
    assert set(por) == {("20 BXO5W30AA", "7720"), ("20 BXO5W30AA", "835066"), ("P1", "835066")}
    otra = por[("P1", "835066")]
    assert otra.nro_doc_ref == "12" and otra.doc_ref == "BOLETA-REPUESTOS"
    assert all(l.tenant_id == "curifor" and l.bodega == "430" for l in por.values())


def test_solo_entran_los_tipos_de_venta_de_la_bodega(db_session):
    r = svc.reemplazar_lineas(db_session, "430", [
        lin(tipo_venta="VTA ML"), lin(tipo_venta="VTA SHOPIFY", numero="2"), lin(tipo_venta="VTA CNT", numero="3"),
        lin(tipo_venta="", numero="4"), lin(tipo_venta="vta ml", numero="5"),
    ])
    assert r["lineas_cargadas"] == 2 and r["lineas_ignoradas"] == 3
    assert r["estadisticas"]["ignoradas_tipo_venta"] == 3 and r["estadisticas"]["ignoradas_invalidas"] == 0
    assert {l.tipo_venta for l in db_session.query(CanalDigitalLinea).all()} == {"VTA ML", "VTA SHOPIFY"}


MALAS = [
    lin(periodo="2026-10"), lin(periodo="202613"), lin(periodo="202600"), {**lin(), "periodo": ""},
    lin(fecha="09-10-2026", periodo="202610"), lin(fecha="2026-02-30", periodo="202602"),
    lin(fecha="", periodo="202610"), lin(fecha="20261009", periodo="202610"),
    lin(producto=""), lin(producto="   "), lin(tipo_docto=""),
    lin(cantidad=None), lin(cantidad="abc"), lin(cantidad=float("nan")), lin(cantidad=float("inf")),
    lin(cantidad=True), "no es un dict", None, 7,
    # los que antes pasaban la validacion y reventaban despues, o se guardaban con un periodo no ASCII
    lin(periodo="20261²"),  # superindice: isdigit() lo acepta, int() lanza
    lin(periodo="٢٠٢٦١١"),  # digitos arabes
    lin(periodo="２０２６１０"),  # digitos de ancho completo
    lin(fecha="2026-10- 9", periodo="202610"), lin(fecha="２０２６-10-09", periodo="202610"),
    lin(fecha="2026-W41-3", periodo="202610"), lin(cantidad=10 ** 400),
    {k: v for k, v in lin().items() if k != "costo_neto"},  # sin el campo: es una deriva del contrato, no un blanco
]


@pytest.mark.parametrize("mala", MALAS, ids=[str(i) for i in range(len(MALAS))])
def test_una_linea_mal_formada_se_ignora_y_no_se_carga_a_medias(db_session, mala):
    r = svc.reemplazar_lineas(db_session, "430", [lin(numero="1"), mala])
    assert r["lineas_cargadas"] == 1 and r["lineas_ignoradas"] == 1
    assert r["estadisticas"]["ignoradas_invalidas"] == 1
    assert db_session.query(CanalDigitalLinea).count() == 1


def test_numeros_como_texto_y_costo_ausente_si_valen(db_session):
    r = svc.reemplazar_lineas(db_session, "430", [lin(cantidad="3", costo="5600.5"), lin(numero="2", costo=None)])
    assert r["lineas_cargadas"] == 2
    por = {l.numero: l for l in db_session.query(CanalDigitalLinea).all()}
    assert por["1"].cantidad == 3.0 and por["1"].costo_neto == 5600.5 and por["2"].costo_neto == 0.0


def test_un_costo_que_no_sirve_no_pierde_las_unidades(db_session):
    """Un Costo Neto en blanco que pandas manda como NaN (o texto, o infinito) vale 0: la venta no se descarta."""
    r = svc.reemplazar_lineas(db_session, "430", [
        lin(numero="1", cantidad=3, costo=float("nan")), lin(numero="2", costo=float("inf")), lin(numero="3", costo="x"),
        lin(numero="4", costo=""), lin(numero="5", costo=None), lin(numero="6", costo=100.0),
    ])
    assert r["lineas_cargadas"] == 6 and r["lineas_ignoradas"] == 0
    assert r["estadisticas"]["ignoradas_invalidas"] == 0 and r["estadisticas"]["costo_en_cero"] == 5
    por = {l.numero: l.costo_neto for l in db_session.query(CanalDigitalLinea).all()}
    assert por == {"1": 0.0, "2": 0.0, "3": 0.0, "4": 0.0, "5": 0.0, "6": 100.0}
    assert _ventas(db_session)[("P1", "2026-10-12", "202610")][:3] == (8.0, 0.0, 100.0)  # 3+1+1+1+1+1 unidades


def test_un_nan_en_el_json_del_envio_tampoco_pierde_la_linea(client, db_session):
    app.dependency_overrides[requiere_admin] = lambda: "motor"
    cuerpo = json.dumps({"bodega": "430", "lineas": [lin(cantidad=3, costo=float("nan"))]})  # json.dumps escribe NaN
    r = client.post("/api/canal-digital/lineas", content=cuerpo, headers={"Content-Type": "application/json"})
    assert r.status_code == 200, r.text
    assert r.json()["lineas_cargadas"] == 1 and r.json()["lineas_ignoradas"] == 0
    assert _ventas(db_session)[("P1", "2026-10-12", "202610")][0] == 3.0


@pytest.mark.parametrize("fecha", ["2026-10-14T00:00:00", "2026-10-14 00:00:00", "2026-10-14T00:00:00.000Z"])
def test_una_fecha_con_hora_se_acepta_y_se_guarda_solo_la_fecha(db_session, fecha):
    r = svc.reemplazar_lineas(db_session, "430", [lin(fecha=fecha, periodo="202610")])
    assert r["lineas_cargadas"] == 1 and r["lineas_ignoradas"] == 0
    assert db_session.query(CanalDigitalLinea).one().fecha == "2026-10-14"
    assert list(_ventas(db_session)) == [("P1", "2026-10-12", "202610")]


def test_un_periodo_como_texto_con_punto_cero_se_acepta(db_session):
    r = svc.reemplazar_lineas(db_session, "430", [lin(periodo="202610.0"), lin(numero="2", periodo=202610.0)])
    assert r["lineas_cargadas"] == 2 and r["periodos"] == ["202610"]
    assert {l.periodo for l in db_session.query(CanalDigitalLinea).all()} == {"202610"}


def test_si_todas_las_lineas_son_invalidas_el_endpoint_responde_422_y_dice_que_campo(client, db_session):
    app.dependency_overrides[requiere_admin] = lambda: "motor"
    svc.reemplazar_lineas(db_session, "430", [lin(numero="1")])
    antes = (_lineas(db_session), _ventas(db_session))
    # el motor renombro un campo del contrato: ninguna linea sirve
    mala ={k: v for k, v in lin().items() if k != "cantidad"}
    r = client.post("/api/canal-digital/lineas", json={"bodega": "430", "lineas": [mala, mala]})
    assert r.status_code == 422, r.text
    detalle = r.json()["detail"]
    assert detalle["estadisticas"]["invalida_campo:cantidad"] == 2 and detalle["estadisticas"]["ignoradas_invalidas"] == 2
    assert (_lineas(db_session), _ventas(db_session)) == antes
    # un envio vacio, o que solo trae otros tipos de venta, sigue siendo un 200 sin cambios
    assert client.post("/api/canal-digital/lineas", json={"lineas": []}).status_code == 200
    assert client.post("/api/canal-digital/lineas", json={"lineas": [lin(tipo_venta="VTA CNT")]}).status_code == 200
    # y si solo algunas son invalidas, entra lo que sirve y la respuesta lo cuenta por campo
    r = client.post("/api/canal-digital/lineas", json={"lineas": [lin(numero="2"), mala]})
    assert r.status_code == 200 and r.json()["lineas_ignoradas"] == 1
    assert r.json()["estadisticas"]["invalida_campo:cantidad"] == 1


# ---------------------------------------------------------------- reemplazo por periodo

def test_reemplaza_solo_los_periodos_que_vienen(db_session):
    svc.reemplazar_lineas(db_session, "430", [lin("2026-09-10", numero="1", cantidad=2), lin("2026-10-14", numero="2")])
    r = svc.reemplazar_lineas(db_session, "430", [lin("2026-10-15", numero="3", cantidad=7)])
    assert r["periodos"] == ["202610"]
    por = {(l.periodo, l.numero): l.cantidad for l in db_session.query(CanalDigitalLinea).all()}
    assert por == {("202609", "1"): 2.0, ("202610", "3"): 7.0}
    venta = _ventas(db_session)
    assert venta == {("P1", "2026-09-07", "202609"): (2.0, 0.0, 200.0, 0.0, 1),
                     ("P1", "2026-10-12", "202610"): (7.0, 0.0, 700.0, 0.0, 1)}


def test_un_envio_vacio_o_sin_lineas_validas_no_borra_nada(db_session):
    svc.reemplazar_lineas(db_session, "430", [lin("2026-10-14", numero="1")])
    antes = (_lineas(db_session), _ventas(db_session))
    assert svc.reemplazar_lineas(db_session, "430", [])["lineas_cargadas"] == 0
    # el periodo viene, pero ninguna de sus lineas sirve (mal formada u otro tipo de venta): no se toca
    r = svc.reemplazar_lineas(db_session, "430", [lin(periodo="202610", producto=""), lin(tipo_venta="VTA CNT")])
    assert r["lineas_cargadas"] == 0 and r["lineas_ignoradas"] == 2 and r["periodos"] == []
    assert r["filas_venta"] == 1
    assert (_lineas(db_session), _ventas(db_session)) == antes


def test_no_mezcla_bodegas(db_session):
    svc.reemplazar_lineas(db_session, "430", [lin(numero="1")])
    svc.reemplazar_lineas(db_session, "999", [lin(numero="2", cantidad=5)])
    assert {l.bodega for l in db_session.query(CanalDigitalLinea).all()} == {"430", "999"}
    # reemplazar el mismo periodo en otra bodega no borra el de la primera
    svc.reemplazar_lineas(db_session, "999", [lin(numero="3", cantidad=6)])
    assert db_session.query(CanalDigitalLinea).filter_by(bodega="430").count() == 1
    ventas = {v.bodega: v.unid_brutas for v in db_session.query(CanalDigitalVenta).all()}
    assert ventas == {"430": 1.0, "999": 6.0}


def test_lineas_repetidas_en_el_origen_se_conservan(db_session):
    r = svc.reemplazar_lineas(db_session, "430", [lin(cantidad=2), lin(cantidad=2)])
    assert r["lineas_cargadas"] == 2 and db_session.query(CanalDigitalLinea).count() == 2
    assert _ventas(db_session) == {("P1", "2026-10-12", "202610"): (4.0, 0.0, 400.0, 0.0, 2)}
    # enviar de nuevo el mismo mes reemplaza: no se duplica
    svc.reemplazar_lineas(db_session, "430", [lin(cantidad=2), lin(cantidad=2)])
    assert db_session.query(CanalDigitalLinea).count() == 2
    assert _ventas(db_session)[("P1", "2026-10-12", "202610")][0] == 4.0


# ---------------------------------------------------------------- recalculo completo

@pytest.mark.parametrize("orden", ["venta primero", "devolucion primero"])
def test_una_devolucion_de_un_mes_anula_la_venta_de_otro_mes(db_session, orden):
    venta = [lin("2026-10-14", numero="10", cantidad=4, costo=50.0)]          # miercoles: semana del 12-oct
    devolucion = [nc("2026-11-03", ref="10", cantidad=4, numero="99", costo=-50.0)]
    envios = [venta, devolucion] if orden == "venta primero" else [devolucion, venta]
    for e in envios:
        svc.reemplazar_lineas(db_session, "430", e)
    # la venta cuenta en octubre, la devolucion en noviembre pero en la semana de la venta que anula
    assert _ventas(db_session) == {
        ("P1", "2026-10-12", "202610"): (4.0, 0.0, 200.0, 0.0, 1),
        ("P1", "2026-10-12", "202611"): (0.0, 4.0, -200.0, 0.0, 1),
    }


def test_la_devolucion_sin_original_cuenta_en_la_semana_de_su_nota_y_se_cuenta(db_session):
    r = svc.reemplazar_lineas(db_session, "430", [nc("2026-11-03", ref="777", cantidad=1)])
    assert r["estadisticas"]["devoluciones_sin_original"] == 1
    assert list(_ventas(db_session)) == [("P1", "2026-11-02", "202611")]


def test_el_recalculo_vuelve_a_ubicar_la_devolucion_cuando_llega_el_original(db_session):
    r1 = svc.reemplazar_lineas(db_session, "430", [nc("2026-11-03", ref="10", cantidad=4)])
    assert r1["estadisticas"]["devoluciones_sin_original"] == 1
    assert list(_ventas(db_session)) == [("P1", "2026-11-02", "202611")]
    r2 = svc.reemplazar_lineas(db_session, "430", [lin("2026-10-14", numero="10", cantidad=4)])
    assert r2["estadisticas"].get("devoluciones_sin_original", 0) == 0
    assert set(_ventas(db_session)) == {("P1", "2026-10-12", "202610"), ("P1", "2026-10-12", "202611")}


def test_la_respuesta_trae_los_totales_y_las_estadisticas_de_todo_lo_guardado(db_session):
    svc.reemplazar_lineas(db_session, "430", [lin("2026-09-10", numero="1", tipo_docto="SALIDA ACCESORIOS")])
    r = svc.reemplazar_lineas(db_session, "430", [lin("2026-10-14", numero="2"), lin("2026-10-15", numero="3")])
    assert r["lineas_cargadas"] == 2 and r["periodos"] == ["202610"] and r["filas_venta"] == 1
    est = r["estadisticas"]
    assert est["lineas_canal"] == 3 and est["omitidas_tipo_documento"] == 1  # de todas las guardadas, no solo las nuevas
    assert est["filas_recalculadas"] == 1 and est["filas_conservadas_sin_lineas"] == 0


def test_tipos_de_venta_distintos_por_bodega(db_session):
    svc.asegurar_bodega(db_session, "999")
    db_session.query(CanalDigitalBodega).filter_by(bodega="999").one().tipos_venta = "VTA ML"
    db_session.commit()
    envio = [lin(numero="1", tipo_venta="VTA ML", cantidad=2), lin(numero="2", tipo_venta="VTA PARIS", cantidad=3)]
    r430 = svc.reemplazar_lineas(db_session, "430", envio)
    r999 = svc.reemplazar_lineas(db_session, "999", envio)
    assert (r430["lineas_cargadas"], r999["lineas_cargadas"]) == (2, 1)
    por = {v.bodega: v.unid_brutas for v in db_session.query(CanalDigitalVenta).all()}
    assert por == {"430": 5.0, "999": 2.0}


def test_recalcular_con_otros_tipos_de_venta_usa_los_guardados(db_session):
    svc.reemplazar_lineas(db_session, "430", [lin(numero="1", tipo_venta="VTA ML", cantidad=2),
                                             lin(numero="2", tipo_venta="VTA PARIS", cantidad=3)])
    db_session.query(CanalDigitalBodega).filter_by(bodega="430").one().tipos_venta = "VTA PARIS"
    db_session.commit()
    r = svc.recalcular_ventas(db_session, "430")
    assert r["filas_venta"] == 1 and _ventas(db_session)[("P1", "2026-10-12", "202610")][0] == 3.0
    assert db_session.query(CanalDigitalLinea).count() == 2  # las lineas no se tocan


def test_recalcular_deja_la_venta_de_periodos_sin_lineas_salvo_que_se_pida_todo(db_session):
    # un periodo cargado antes con la ruta /ventas (filas ya agregadas) y otro con lineas
    svc.reemplazar_ventas(db_session, "430", [
        {"producto": "VIEJO", "semana": "2026-08-24", "periodo": "202608", "unid_brutas": 9, "unid_devueltas": 0,
         "valor_costo": 90, "unid_liquidacion": 0, "n_lineas": 3}])
    r = svc.reemplazar_lineas(db_session, "430", [lin("2026-10-14")])
    assert r["filas_venta"] == 2 and r["estadisticas"]["filas_conservadas_sin_lineas"] == 1
    assert ("VIEJO", "2026-08-24", "202608") in _ventas(db_session)
    r = svc.recalcular_ventas(db_session, "430", conservar_sin_lineas=False)
    assert list(_ventas(db_session)) == [("P1", "2026-10-12", "202610")] and r["filas_venta"] == 1


# ---------------------------------------------------------------- que mes hay de cada cosa (/meta)

def test_meta_dice_hasta_que_mes_hay_lineas_aunque_la_venta_venga_de_la_ruta_vieja(client, db_session):
    app.dependency_overrides[requiere_admin] = lambda: "motor"
    vacio = client.get("/api/canal-digital/meta").json()
    assert (vacio["n_lineas"], vacio["lineas_periodo_desde"], vacio["lineas_periodo_hasta"]) == (0, None, None)
    # octubre llego como venta ya agregada (ruta /ventas): hay venta hasta 202610 pero ninguna linea
    fila = {"producto": "P1", "semana": "2026-10-12", "periodo": "202610", "unid_brutas": 5, "unid_devueltas": 0,
            "valor_costo": 500, "unid_liquidacion": 0, "n_lineas": 2}
    assert client.post("/api/canal-digital/ventas", json={"bodega": "430", "filas": [fila]}).status_code == 200
    m = client.get("/api/canal-digital/meta").json()
    assert m["periodo_hasta"] == "202610"  # la venta
    assert (m["n_lineas"], m["lineas_periodo_desde"], m["lineas_periodo_hasta"]) == (0, None, None)  # las lineas
    client.post("/api/canal-digital/lineas", json={"lineas": [lin("2026-08-10", numero="1"), lin("2026-09-10", numero="2"),
                                                              lin("2026-09-11", numero="3")]})
    m = client.get("/api/canal-digital/meta").json()
    assert m["periodo_hasta"] == "202610"
    assert (m["n_lineas"], m["lineas_periodo_desde"], m["lineas_periodo_hasta"]) == (3, "202608", "202609")
    # otra bodega no mezcla
    otra = client.get("/api/canal-digital/meta?bodega=999").json()
    assert (otra["n_lineas"], otra["lineas_periodo_hasta"]) == (0, None)


# ---------------------------------------------------------------- un envio no pisa en silencio lo cargado

def test_la_respuesta_dice_cuantas_lineas_tenia_cada_periodo_antes_y_despues(db_session):
    r = svc.reemplazar_lineas(db_session, "430", [lin("2026-09-10", numero="1"), lin("2026-09-11", numero="2")])
    assert r["reemplazo"] == {"202609": {"antes": 0, "despues": 2}}
    r = svc.reemplazar_lineas(db_session, "430", [lin("2026-09-12", numero="3"), lin("2026-10-14", numero="4")])
    assert r["reemplazo"] == {"202609": {"antes": 2, "despues": 1}, "202610": {"antes": 0, "despues": 1}}
    assert svc.reemplazar_lineas(db_session, "430", [])["reemplazo"] == {}


def _mes_grande(db_session, n=30):
    svc.reemplazar_lineas(db_session, "430", [lin("2026-09-10", numero=str(i), producto=f"P{i}") for i in range(n)])


def test_una_linea_rezagada_no_borra_un_mes_completo_sin_forzar(db_session):
    _mes_grande(db_session)
    antes = (_lineas(db_session), _ventas(db_session))
    with pytest.raises(svc.ConflictoCarga) as e:
        svc.reemplazar_lineas(db_session, "430", [lin("2026-09-30", numero="999"), lin("2026-10-14", numero="1000")])
    assert e.value.detalle["periodos"] == {"202609": {"antes": 30, "despues": 1}}
    assert (_lineas(db_session), _ventas(db_session)) == antes  # ni el mes sospechoso ni el nuevo
    # con forzar el reemplazo se hace, y queda dicho en la respuesta
    r = svc.reemplazar_lineas(db_session, "430", [lin("2026-09-30", numero="999")], forzar=True)
    assert r["reemplazo"] == {"202609": {"antes": 30, "despues": 1}}
    assert db_session.query(CanalDigitalLinea).count() == 1


def test_reenviar_el_mes_completo_o_con_pocas_menos_lineas_no_es_sospechoso(db_session):
    _mes_grande(db_session)
    r = svc.reemplazar_lineas(db_session, "430", [lin("2026-09-10", numero=str(i), producto=f"P{i}") for i in range(16)])
    assert r["reemplazo"] == {"202609": {"antes": 30, "despues": 16}}  # justo la mitad o mas: pasa
    # un mes chico no dispara la guarda: 3 lineas a 1 es ruido, no un accidente
    svc.reemplazar_lineas(db_session, "430", [lin("2026-08-10", numero=str(i)) for i in range(3)])
    assert svc.reemplazar_lineas(db_session, "430", [lin("2026-08-10", numero="9")])["lineas_cargadas"] == 1


def test_el_endpoint_responde_409_con_el_detalle_y_acepta_forzar_y_deja_auditoria(client, db_session):
    app.dependency_overrides[requiere_admin] = lambda: "motor"
    _mes_grande(db_session)
    r = client.post("/api/canal-digital/lineas", json={"lineas": [lin("2026-09-30", numero="999")]})
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["periodos"] == {"202609": {"antes": 30, "despues": 1}}
    assert db_session.query(AuditoriaLog).filter_by(accion="canal_digital_lineas").count() == 0
    r = client.post("/api/canal-digital/lineas", json={"lineas": [lin("2026-09-30", numero="999")], "forzar": True})
    assert r.status_code == 200 and r.json()["reemplazo"] == {"202609": {"antes": 30, "despues": 1}}
    log = db_session.query(AuditoriaLog).filter_by(accion="canal_digital_lineas").one()
    assert (log.entidad, log.entidad_id, log.usuario_email) == ("canal_digital", "430", "motor")
    assert "202609 (30 -> 1)" in log.detalle and "1 lineas" in log.detalle
    # "forzar" tiene que ser el booleano true, no cualquier cosa que parezca verdadera
    _mes_grande(db_session)
    assert client.post("/api/canal-digital/lineas",
                       json={"lineas": [lin("2026-09-30", numero="9")], "forzar": "true"}).status_code == 409


def test_la_ruta_vieja_de_ventas_no_pisa_un_periodo_que_ya_tiene_lineas(client, db_session):
    app.dependency_overrides[requiere_admin] = lambda: "motor"
    client.post("/api/canal-digital/lineas", json={"lineas": [lin("2026-10-14", cantidad=3)]})
    fila = {"producto": "P1", "semana": "2026-10-12", "periodo": "202610", "unid_brutas": 50, "unid_devueltas": 0,
            "valor_costo": 5000, "unid_liquidacion": 0, "n_lineas": 1}
    otra = {**fila, "semana": "2026-09-14", "periodo": "202609"}
    antes = _ventas(db_session)
    r = client.post("/api/canal-digital/ventas", json={"bodega": "430", "filas": [otra, fila]})
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["periodos_con_lineas"] == ["202610"]
    assert _ventas(db_session) == antes  # ni siquiera el periodo que si se podia cargar
    # un periodo sin lineas sigue entrando, y el siguiente /lineas no lo toca
    assert client.post("/api/canal-digital/ventas", json={"bodega": "430", "filas": [otra]}).status_code == 200
    client.post("/api/canal-digital/lineas", json={"lineas": [lin("2026-10-15", numero="2", cantidad=4)]})
    assert _ventas(db_session)[("P1", "2026-09-14", "202609")][0] == 50.0


# ---------------------------------------------------------------- cuanto se escribe en cada envio

def _contar_viajes(db_session):
    """Cuenta los viajes que un INSERT en las tablas de lineas y de venta le cuesta al driver: un `executemany` con
    lista de filas es un viaje POR FILA en pg8000; un INSERT de varias filas con RETURNING (insertmanyvalues) es uno."""
    visto = {"viajes": 0, "inserts": 0}

    def _antes(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith(("INSERT INTO CANAL_DIGITAL_LINEA", "INSERT INTO CANAL_DIGITAL_VENTA")):
            visto["inserts"] += 1
            visto["viajes"] += len(parameters) if isinstance(parameters, list) else 1

    engine = db_session.get_bind()
    event.listen(engine, "before_cursor_execute", _antes)
    return visto, lambda: event.remove(engine, "before_cursor_execute", _antes)


def test_los_inserts_no_van_fila_por_fila(db_session):
    """En Postgres con pg8000 un executemany sin RETURNING es un viaje a la base por fila."""
    visto, quitar = _contar_viajes(db_session)
    try:
        lineas = [lin("2026-10-14", numero=str(i), producto=f"P{i}") for i in range(2500)]
        r = svc.reemplazar_lineas(db_session, "430", lineas)
    finally:
        quitar()
    assert r["lineas_cargadas"] == 2500 and r["filas_venta"] == 2500
    assert 0 < visto["viajes"] < 25, visto  # por lotes de varias filas, no uno por fila (antes: 5.000)


def test_un_envio_solo_escribe_lo_que_cambio_de_la_venta(db_session):
    mes_viejo = [lin("2026-09-10", numero=str(i), producto=f"P{i}") for i in range(400)]
    mes_nuevo = [lin("2026-10-14", numero=str(i), producto=f"P{i}") for i in range(400)]
    svc.reemplazar_lineas(db_session, "430", mes_viejo)
    r = svc.reemplazar_lineas(db_session, "430", mes_nuevo)
    est = r["estadisticas"]
    assert r["filas_venta"] == 800 and est["filas_recalculadas"] == 800
    assert est["filas_escritas"] == 400 and est["filas_sin_cambio"] == 400  # septiembre no se reescribe
    ids = {(v.producto, v.periodo): v.id for v in db_session.query(CanalDigitalVenta).all()}
    # reenviar el mismo mes no cambia nada
    r = svc.reemplazar_lineas(db_session, "430", mes_nuevo)
    assert r["estadisticas"]["filas_escritas"] == 0 and r["estadisticas"]["filas_sin_cambio"] == 800
    assert {(v.producto, v.periodo): v.id for v in db_session.query(CanalDigitalVenta).all()} == ids
    # una linea cambiada de octubre reescribe una sola fila; la que desaparece se borra
    cambiado = [lin("2026-10-14", numero="0", producto="P0", cantidad=9)] + mes_nuevo[2:]
    r = svc.reemplazar_lineas(db_session, "430", cambiado)
    assert r["estadisticas"]["filas_escritas"] == 1 and r["filas_venta"] == 799
    venta = _ventas(db_session)
    assert venta[("P0", "2026-10-12", "202610")][0] == 9.0 and ("P1", "2026-10-12", "202610") not in venta
    assert len({k for k in venta if k[2] == "202609"}) == 400


def test_la_devolucion_de_un_mes_nuevo_mueve_solo_la_fila_de_la_semana_que_anula(db_session):
    svc.reemplazar_lineas(db_session, "430", [lin("2026-10-14", numero="10", cantidad=4),
                                              lin("2026-10-15", numero="11", producto="P2")])
    r = svc.reemplazar_lineas(db_session, "430", [nc("2026-11-03", ref="10", cantidad=4)])
    assert r["estadisticas"]["filas_escritas"] == 1 and r["estadisticas"]["filas_sin_cambio"] == 2
    assert _ventas(db_session) == {
        ("P1", "2026-10-12", "202610"): (4.0, 0.0, 400.0, 0.0, 1),
        ("P2", "2026-10-12", "202610"): (1.0, 0.0, 100.0, 0.0, 1),
        ("P1", "2026-10-12", "202611"): (0.0, 4.0, -400.0, 0.0, 1),
    }


# ---------------------------------------------------------------- un envio a la vez

def test_dos_envios_a_la_vez_se_ponen_en_fila(db_session):
    """El reintento del motor sobre un envio que sigue en curso espera al primero en vez de pisarlo."""
    terminado = threading.Event()

    def envio():
        svc.reemplazar_lineas(db_session, "430", [lin()])
        terminado.set()

    with svc.CARGA_CANAL_DIGITAL:  # alguien esta cargando
        hilo = threading.Thread(target=envio)
        hilo.start()
        assert not terminado.wait(0.3)
    assert terminado.wait(10)
    hilo.join()
    assert db_session.query(CanalDigitalLinea).count() == 1


# ---------------------------------------------------------------- atomicidad

def _boom(*a, **k):
    raise RuntimeError("falla simulada")


@pytest.mark.parametrize("donde", ["agregar", "_contar_ventas"])
def test_si_el_recalculo_falla_no_queda_nada_a_medias(db_session, monkeypatch, donde):
    svc.reemplazar_lineas(db_session, "430", [lin("2026-09-10", numero="1"), lin("2026-10-14", numero="2", cantidad=3)])
    antes = (_lineas(db_session), _ventas(db_session))
    monkeypatch.setattr(svc, donde, _boom)  # "_contar_ventas" falla despues de borrar e insertar lineas y venta
    with pytest.raises(RuntimeError):
        svc.reemplazar_lineas(db_session, "430", [lin("2026-10-14", numero="2", cantidad=9), lin("2026-11-02", numero="5")])
    monkeypatch.undo()
    assert (_lineas(db_session), _ventas(db_session)) == antes  # ni el mes reemplazado ni el nuevo
    # y la tabla sigue sirviendo: la misma carga, sin falla, funciona
    r = svc.reemplazar_lineas(db_session, "430", [lin("2026-10-14", numero="2", cantidad=9)])
    assert r["lineas_cargadas"] == 1 and _ventas(db_session)[("P1", "2026-10-12", "202610")][0] == 9.0


def test_recalcular_ventas_tambien_es_todo_o_nada(db_session, monkeypatch):
    svc.reemplazar_lineas(db_session, "430", [lin("2026-10-14", cantidad=3)])
    antes = _ventas(db_session)
    monkeypatch.setattr(svc, "_contar_ventas", _boom)
    with pytest.raises(RuntimeError):
        svc.recalcular_ventas(db_session, "430", conservar_sin_lineas=False)
    monkeypatch.undo()
    assert _ventas(db_session) == antes


# ---------------------------------------------------------------- endpoint

def test_endpoint_de_lineas_carga_y_meta_lo_ve(client, db_session):
    app.dependency_overrides[requiere_admin] = lambda: "motor"
    r = client.post("/api/canal-digital/lineas", json={"bodega": "430", "lineas": [
        lin("2026-10-14", numero="1", cantidad=3), lin("2026-10-15", numero="2", producto="P2"),
        lin(tipo_venta="VTA CNT"),
    ]})
    assert r.status_code == 200, r.text
    j = r.json()
    assert (j["lineas_cargadas"], j["lineas_ignoradas"], j["periodos"], j["filas_venta"]) == (2, 1, ["202610"], 2)
    assert set(j) == {"lineas_cargadas", "lineas_ignoradas", "periodos", "reemplazo", "filas_venta", "estadisticas"}
    m = client.get("/api/canal-digital/meta").json()
    assert m["filas"] == 2 and m["productos"] == 2 and m["periodo_hasta"] == "202610"


def test_endpoint_de_lineas_pide_la_lista_y_usa_430_por_defecto(client, db_session):
    app.dependency_overrides[requiere_admin] = lambda: "motor"
    assert client.post("/api/canal-digital/lineas", json={"bodega": "430"}).status_code == 400
    assert client.post("/api/canal-digital/lineas", json={"lineas": "x"}).status_code == 400
    r = client.post("/api/canal-digital/lineas", json={"lineas": [lin()]})
    assert r.status_code == 200 and db_session.query(CanalDigitalLinea).one().bodega == "430"


def test_endpoint_de_lineas_exige_admin(client, db_session):
    from src.models import Usuario

    db_session.get(Usuario, "test@curifor.com").es_admin = False
    db_session.commit()
    r = client.post("/api/canal-digital/lineas", json={"lineas": [lin()]})
    assert r.status_code == 403
    assert db_session.query(CanalDigitalLinea).count() == 0


def test_endpoint_de_lineas_invalida_el_resultado_guardado(client, db_session):
    app.dependency_overrides[requiere_admin] = lambda: "motor"
    router_cd._cache["430:2026-10-26"] = (0.0, object(), {})
    assert client.post("/api/canal-digital/lineas", json={"lineas": [lin()]}).status_code == 200
    assert router_cd._cache == {}


def test_la_ruta_de_ventas_sigue_funcionando(client, db_session):
    app.dependency_overrides[requiere_admin] = lambda: "motor"
    fila = {"producto": "P1", "semana": "2026-09-21", "periodo": "202609", "unid_brutas": 5, "unid_devueltas": 1,
            "valor_costo": 400, "unid_liquidacion": 0, "n_lineas": 2}
    r = client.post("/api/canal-digital/ventas", json={"bodega": "430", "filas": [fila]})
    assert r.status_code == 200 and r.json() == {"filas_cargadas": 1, "ignoradas": 0, "periodos": ["202609"]}
    assert db_session.query(CanalDigitalLinea).count() == 0  # /ventas no toca las lineas
    # y convive con /lineas: el mes cargado por /ventas queda mientras no tenga lineas
    client.post("/api/canal-digital/lineas", json={"lineas": [lin("2026-10-14")]})
    assert set(_ventas(db_session)) == {("P1", "2026-09-21", "202609"), ("P1", "2026-10-12", "202610")}
    assert client.post("/api/canal-digital/ventas", json={"filas": "x"}).status_code == 400


# ---------------------------------------------------------------- script cargador (--publicar-lineas)

@pytest.fixture()
def script():
    ruta = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "canal_digital_cargar_ventas.py"
    spec = importlib.util.spec_from_file_location("canal_digital_cargar_ventas", ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _lineas_del_erp():
    """Lo que leeria el cargador de los Excel: una venta de octubre, su devolucion de noviembre y una venta de noviembre."""
    f = dt.date.fromisoformat
    return [
        LineaVenta("202610", "FA-ELECTR REPTO", "835066", f("2026-10-14"), "VTA ML", "20 BXO5W30AA", 3.0, 5600.5),
        LineaVenta("202610", "BOLETA-REPUESTOS", "7720", f("2026-10-20"), "VTA SHOPIFY", "P2", 2.0, 100.0),
        LineaVenta("202611", "NC-ELECTR REPTO", "55", f("2026-11-03"), "VTA ML", "20 BXO5W30AA", 1.0, -5600.5,
                   "FA-ELECTR REPTO", "835066"),
        LineaVenta("202611", "FA-ELECTR REPTO", "835100", f("2026-11-04"), "VTA ML", "20 BXO5W30AA", 2.0, 5700.0),
    ]


def test_el_script_arma_un_envio_por_mes_con_los_nombres_del_contrato(script):
    por_mes = script.lineas_por_mes(_lineas_del_erp() + [
        LineaVenta("None", "FA-ELECTR REPTO", "1", dt.date(2026, 10, 1), "VTA ML", "P9", 1.0, 1.0)])
    assert list(por_mes) == ["202610", "202611"]
    assert [len(v) for v in por_mes.values()] == [2, 2]
    assert por_mes["202610"][0] == {
        "periodo": "202610", "tipo_docto": "FA-ELECTR REPTO", "numero": "835066", "fecha": "2026-10-14",
        "tipo_venta": "VTA ML", "producto": "20 BXO5W30AA", "cantidad": 3.0, "costo_neto": 5600.5,
        "doc_ref": "", "nro_doc_ref": "",
    }
    assert list(script.lineas_por_mes(_lineas_del_erp(), desde_periodo="202611")) == ["202611"]


def test_el_script_publica_y_la_plataforma_arma_lo_mismo_que_la_regla_local(client, db_session, script, monkeypatch):
    app.dependency_overrides[requiere_admin] = lambda: "motor"
    envios = []

    def _sin_red(ruta, cuerpo):  # el envio va al endpoint de prueba: nunca a la red
        envios.append((ruta, cuerpo))
        r = client.post(ruta, json=cuerpo)
        assert r.status_code == 200, r.text
        return r.json()

    monkeypatch.setattr(script, "_enviar", _sin_red)
    lineas = _lineas_del_erp()
    respuestas = script.publicar_lineas(script.lineas_por_mes(lineas), "430")
    assert [r["periodos"] for r in respuestas] == [["202610"], ["202611"]]
    assert [(ruta, c["bodega"], {l["periodo"] for l in c["lineas"]}) for ruta, c in envios] == [
        ("/api/canal-digital/lineas", "430", {"202610"}), ("/api/canal-digital/lineas", "430", {"202611"})]
    local = agregar(lineas, ("VTA ML", "VTA SHOPIFY"), indice_originales(lineas, ("VTA ML", "VTA SHOPIFY")))
    esperado = {(f.producto, f.semana, f.periodo): (f.unid_brutas, f.unid_devueltas, f.valor_costo,
                                                    f.unid_liquidacion, f.n_lineas) for f in local.filas}
    guardado = _ventas(db_session)
    assert guardado == {k: pytest.approx(v) for k, v in esperado.items()}
    # la devolucion de noviembre quedo en la semana de la venta de octubre
    assert ("20 BXO5W30AA", "2026-10-12", "202611") in guardado


def test_el_script_avisa_cuantas_lineas_dejo_fuera_por_no_tener_periodo(script, capsys):
    sin = [LineaVenta(p, "FA-ELECTR REPTO", "1", dt.date(2026, 10, 1), "VTA ML", "P9", 1.0, 1.0)
           for p in ("None", "", "2026-10", "٢٠٢٦١١")]
    por_mes = script.lineas_por_mes(_lineas_del_erp() + sin)
    assert list(por_mes) == ["202610", "202611"] and [len(v) for v in por_mes.values()] == [2, 2]
    assert "4 lineas sin periodo YYYYMM" in capsys.readouterr().err
    script.lineas_por_mes(_lineas_del_erp())
    assert capsys.readouterr().err == ""


def _respuesta(cargadas, ignoradas, **est):
    return {"lineas_cargadas": cargadas, "lineas_ignoradas": ignoradas, "periodos": [], "reemplazo": {},
            "filas_venta": 0, "estadisticas": {"ignoradas_invalidas": 0, "ignoradas_tipo_venta": 0, **est}}


@pytest.mark.parametrize("respuesta", [
    _respuesta(3, 1, ignoradas_invalidas=1, **{"invalida_campo:fecha": 1}),  # una linea mal formada
    _respuesta(0, 4, ignoradas_tipo_venta=4),  # el servidor no reconocio ninguna como del canal
])
def test_el_script_se_detiene_si_la_plataforma_ignora_lineas_que_el_envio_si_traia(script, monkeypatch, respuesta):
    enviados = []
    monkeypatch.setattr(script, "_enviar", lambda ruta, cuerpo: enviados.append(cuerpo) or respuesta)
    with pytest.raises(SystemExit) as e:
        script.publicar_lineas(script.lineas_por_mes(_lineas_del_erp()), "430")
    assert "202610" in str(e.value) and "corrige el origen" in str(e.value)
    assert len(enviados) == 1  # no sigue con noviembre


def test_el_script_sigue_si_no_se_ignoro_nada(script, monkeypatch):
    monkeypatch.setattr(script, "_enviar", lambda ruta, cuerpo: _respuesta(len(cuerpo["lineas"]), 0))
    assert len(script.publicar_lineas(script.lineas_por_mes(_lineas_del_erp()), "430")) == 2


def test_el_script_no_sale_a_la_red_sin_las_variables_de_entorno(script, monkeypatch):
    monkeypatch.delenv("CANAL_DIGITAL_API", raising=False)
    monkeypatch.delenv("CANAL_DIGITAL_TOKEN", raising=False)
    with pytest.raises(SystemExit):
        script.publicar_lineas(script.lineas_por_mes(_lineas_del_erp()), "430")


# ---------------------------------------------------------------- equivalencia con la venta ya agregada

EPS = 1e-6


def _piezas(b, d, liq, n):
    """Cantidades de un grupo (venta S, liquidacion LS, nota N, nota de liquidacion NL) que dan esas
    unidades en el menor numero de lineas, repartidas luego hasta llegar a `n` lineas. -> (piezas, minimo)."""
    ls0, nl0 = max(liq, 0.0), max(-liq, 0.0)
    s0, n0 = b - ls0, d - nl0
    if s0 < -EPS or n0 < -EPS:
        raise ValueError(f"fila imposible: brutas {b}, devueltas {d}, liquidacion {liq}")
    mejor = None
    for t in (0.0, min(s0, n0)):  # una liquidacion que se anula con otra suma lo mismo a las dos columnas
        p = [x for x in ([["LS", ls0 + t], ["NL", nl0 + t], ["S", s0 - t], ["N", n0 - t]]) if x[1] > EPS]
        if mejor is None or len(p) < len(mejor):
            mejor = p
    minimo = len(mejor)
    while len(mejor) < n:
        mejor.sort(key=lambda x: -x[1])
        if mejor and mejor[0][1] > EPS:
            tipo, q = mejor[0]
            a, b2 = (q - 1.0, 1.0) if q >= 2 else (q / 2, q / 2)
            mejor[0] = [tipo, a]
            mejor.append([tipo, b2])
        else:
            mejor.append(["S", 0.0])
    return mejor, minimo


def _costos(b, d, v):
    """(costo unitario de lo que suma, costo unitario de lo que resta) con la regla |costo| x unidades netas."""
    if d == 0:
        return (v / b if b else 0.0), 0.0
    if b == 0:
        return 0.0, -v / d
    if b != d and v / (b - d) >= 0:
        return v / (b - d), v / (b - d)
    cn = max(0.0, -v / d)
    return (v + cn * d) / b, cn


TIPO_DOCTO = {"S": "FA-ELECTR REPTO", "LS": "LIQ FACT-REPUESTOS", "N": "NC-ELECTR REPTO", "NL": "NC LIQ FACT"}


def reconstruir_lineas(filas):
    """Lineas del ERP inventadas que, pasadas por la plataforma, deben dar de vuelta `filas` (venta ya agregada).

    Las ventas van el lunes de su semana y las notas el domingo, apuntando a una venta de esa misma semana (de
    otro periodo si existe) o a un documento que no existe. -> ({periodo: [lineas]}, [filas que no caben en n_lineas]).
    """
    seq = itertools.count(1)
    armadas = []
    primera: dict[tuple, str] = {}  # (producto, semana, tipo S/LS) -> numero de su primera venta
    no_caben = []
    for f in filas:
        b, d, v = float(f["unid_brutas"]), float(f["unid_devueltas"]), float(f["valor_costo"])
        liq, n = float(f["unid_liquidacion"]), int(f["n_lineas"])
        piezas, minimo = _piezas(b, d, liq, n)
        if minimo > n:
            no_caben.append((f["producto"], f["semana"], f["periodo"]))
        cp, cn = _costos(b, d, v)
        for p in piezas:
            p.append(str(next(seq)))
            if p[0] in ("S", "LS"):
                primera.setdefault((f["producto"], f["semana"], p[0]), p[2])
        armadas.append((f, piezas, cp, cn))
    por_periodo: dict[str, list[dict]] = {}
    for i, (f, piezas, cp, cn) in enumerate(armadas):
        lunes = dt.date.fromisoformat(f["semana"])
        for tipo, q, numero in piezas:
            if tipo in ("S", "LS"):
                fecha, costo, ref, nro_ref = lunes, cp, "", ""
            else:
                original = "S" if tipo == "N" else "LS"
                nro_ref = primera.get((f["producto"], f["semana"], original), "no-existe-" + numero)
                fecha, costo, ref = lunes + dt.timedelta(days=6), -cn, TIPO_DOCTO[original]
            por_periodo.setdefault(f["periodo"], []).append(lin(
                fecha.isoformat(), f["producto"], q, TIPO_DOCTO[tipo], numero, costo=costo, periodo=f["periodo"],
                doc_ref=ref, nro_doc_ref=nro_ref))
        if i % 40 == 0:  # ruido que la regla debe dejar fuera: otro tipo de venta y un documento que no es venta
            por_periodo[f["periodo"]].append(lin(lunes.isoformat(), f["producto"], 99, numero="r1", tipo_venta="VTA CNT",
                                                 periodo=f["periodo"]))
            por_periodo[f["periodo"]].append(lin(lunes.isoformat(), f["producto"], 99, "SALIDA ACCESORIOS", "r2",
                                                 periodo=f["periodo"]))
    return dict(sorted(por_periodo.items())), no_caben


def _enviar_por_mes(client, por_periodo):
    for periodo, lineas in por_periodo.items():
        r = client.post("/api/canal-digital/lineas", json={"bodega": "430", "lineas": lineas})
        assert r.status_code == 200, r.text
        assert r.json()["periodos"] == [periodo]


def _comparar(db, filas, no_caben=()):
    """La venta guardada es la de `filas`, columna por columna (n_lineas se exige salvo en `no_caben`)."""
    esperado = {(f["producto"], f["semana"], f["periodo"]): f for f in filas}
    guardado = _ventas(db)
    assert set(guardado) == set(esperado)
    for k, f in esperado.items():
        b, d, v, liq, n = guardado[k]
        assert b == pytest.approx(float(f["unid_brutas"]), abs=EPS), k
        assert d == pytest.approx(float(f["unid_devueltas"]), abs=EPS), k
        assert v == pytest.approx(float(f["valor_costo"]), rel=1e-9, abs=EPS), k
        assert liq == pytest.approx(float(f["unid_liquidacion"]), abs=EPS), k
        if k not in set(no_caben):
            assert n == int(f["n_lineas"]), k


FILAS_MUESTRA = [
    # venta de agosto en dos lineas y su devolucion de septiembre (otro periodo, misma semana de la venta)
    {"producto": "P1", "semana": "2026-08-24", "periodo": "202608", "unid_brutas": 5, "unid_devueltas": 0,
     "valor_costo": 500, "unid_liquidacion": 0, "n_lineas": 2},
    {"producto": "P1", "semana": "2026-08-24", "periodo": "202609", "unid_brutas": 0, "unid_devueltas": 2,
     "valor_costo": -200, "unid_liquidacion": 0, "n_lineas": 1},
    # liquidacion; nota de liquidacion sin original
    {"producto": "P2", "semana": "2026-09-07", "periodo": "202609", "unid_brutas": 3, "unid_devueltas": 0,
     "valor_costo": 900, "unid_liquidacion": 3, "n_lineas": 1},
    {"producto": "P2", "semana": "2026-09-14", "periodo": "202609", "unid_brutas": 0, "unid_devueltas": 1,
     "valor_costo": -300, "unid_liquidacion": -1, "n_lineas": 1},
    # venta y nota de liquidacion en una misma semana (2 lineas)
    {"producto": "P3", "semana": "2026-09-14", "periodo": "202609", "unid_brutas": 6, "unid_devueltas": 2,
     "valor_costo": 400, "unid_liquidacion": 4, "n_lineas": 2},
    # la nota se costeo distinto que la venta
    {"producto": "P4", "semana": "2026-09-21", "periodo": "202609", "unid_brutas": 3, "unid_devueltas": 1,
     "valor_costo": -50, "unid_liquidacion": 0, "n_lineas": 3},
    {"producto": "P5", "semana": "2026-09-21", "periodo": "202610", "unid_brutas": 1, "unid_devueltas": 1,
     "valor_costo": 40, "unid_liquidacion": 0, "n_lineas": 2},
]


def test_las_lineas_reconstruidas_dan_de_vuelta_la_venta_agregada(client, db_session):
    app.dependency_overrides[requiere_admin] = lambda: "motor"
    por_periodo, no_caben = reconstruir_lineas(FILAS_MUESTRA)
    assert no_caben == []
    _enviar_por_mes(client, por_periodo)
    _comparar(db_session, FILAS_MUESTRA)


def test_el_orden_de_los_meses_no_cambia_el_resultado(client, db_session):
    app.dependency_overrides[requiere_admin] = lambda: "motor"
    por_periodo, _ = reconstruir_lineas(FILAS_MUESTRA)
    _enviar_por_mes(client, dict(reversed(list(por_periodo.items()))))
    _comparar(db_session, FILAS_MUESTRA)


@pytest.mark.skipif(not os.environ.get("CANAL_DIGITAL_CSV_REAL"),
                    reason="define CANAL_DIGITAL_CSV_REAL con la ruta del CSV de venta semanal generado con la misma regla")
def test_equivalencia_con_el_csv_de_venta_semanal_real(client, db_session):
    """No lee los Excel: parte de las filas ya agregadas, arma las lineas que las producirian, las sube mes a mes
    por el endpoint y exige que la plataforma devuelva exactamente esas filas."""
    app.dependency_overrides[requiere_admin] = lambda: "motor"
    with open(os.environ["CANAL_DIGITAL_CSV_REAL"], newline="", encoding="utf-8") as fh:
        filas = list(csv.DictReader(fh))
    assert len(filas) > 1000
    por_periodo, no_caben = reconstruir_lineas(filas)
    _enviar_por_mes(client, por_periodo)
    _comparar(db_session, filas, no_caben)
    est = svc.recalcular_ventas(db_session, "430", conservar_sin_lineas=False)["estadisticas"]
    _comparar(db_session, filas, no_caben)  # un recalculo completo sobre lo guardado no cambia nada
    print(f"\nfilas {len(filas)}, lineas {sum(len(v) for v in por_periodo.values())}, "
          f"filas que no caben en n_lineas {len(no_caben)}, estadisticas {est}")
    assert math.isclose(sum(float(f['unid_brutas']) - float(f['unid_devueltas']) for f in filas),
                        sum(v[0] - v[1] for v in _ventas(db_session).values()), abs_tol=1e-6)
