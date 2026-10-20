"""Vigencia (2/2): el barrido que aplica los vencimientos, los filtros, el resumen y el
archivo del ERP.

El paso anterior dejo la regla (`calcular` ignora precio fijo, margen fijo y congelar
fuera del periodo) pero el vencimiento solo llegaba al precio en el proximo recalculo,
que es cuando alguien aprieta un boton. Este paso lo lleva al precio sin esperar:

1. `aplicar_vigencias` recalcula SOLO los productos cuyo estado esperado difiere del
   marcador `vigencia_aplicada`, deja UNA auditoria y UNA notificacion, y no escribe
   NADA si no hay candidatos (recalcular siempre deja una fila de auditoria, aunque de
   0 cambios: por eso se corta antes).
2. Corre solo, al leer: el resumen, la lista y cualquier descarga. Un fallo del barrido no
   rompe la lectura; solo el archivo del ERP se niega a salir con vencimientos sin aplicar.
3. Nunca escribe `precio_override`: eso es de las personas.
4. 'Hoy' es el de Chile, tambien en los nombres de archivo.
"""
import csv
import inspect
import io
import threading
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.models import AuditoriaLog, Notificacion, PrecioCambio, PrecioEnvio, PrecioOverride, PrecioProducto
from src.services import calendario
from src.services import precios_service as svc
from src.services.auth import requiere_auth

from .test_precios import lista_cargada  # noqa: F401  (fixture)
from .test_precios_vigencia import HOY, _dias, _override, _precio, guardar, lista, reloj  # noqa: F401

ADMIN = "/api/admin/precios/vigencias/aplicar"


# ------------------------------------------------------------------ ayudas
def _nuevo(db, codigo, costo=10000.0, stock=5.0):
    """Un producto de la regla (costo 10.000, Liviano Nacional): 17.800."""
    db.add(PrecioProducto(
        tenant_id="curifor", producto=codigo, glosa="REPUESTO", rubro="71",
        procedencia_maestro="NACIONAL", costo=costo, stock=stock, stock_transito=0.0,
        origen="maestro"))
    db.commit()
    svc.recalcular(db, refrescar_insumos=False, productos=[codigo])
    return codigo


def _fijo(db, codigo, hasta=None, desde=None, precio=990):
    """Lo que hace una persona desde la ficha: un precio fijo con su periodo."""
    datos = {"precio_fijo": precio}
    if desde is not None:
        datos["vigente_desde"] = desde
    if hasta is not None:
        datos["vigente_hasta"] = hasta
    return guardar(db, datos, producto=codigo)


def _filas(db):
    """Cuantas filas hay de cada cosa que un barrido podria escribir."""
    db.expire_all()
    return {
        "vigencias": db.query(AuditoriaLog).filter_by(accion="precios_vigencias").count(),
        "auditoria": db.query(AuditoriaLog).count(),
        "notificaciones": db.query(Notificacion).count(),
        "cambios": db.query(PrecioCambio).count(),
    }


def _csv(r):
    assert r.status_code == 200, r.text
    return list(csv.reader(io.StringIO(r.content.decode("utf-8-sig")), delimiter=";"))


def _como_no_admin(client):
    app.dependency_overrides[requiere_auth] = lambda: "noadmin@curifor.com"


def _boom(*a, **k):
    raise RuntimeError("el barrido fallo")


# ============================================================ 1. el barrido
def test_sin_candidatos_devuelve_ceros_y_no_escribe_nada(lista, reloj):
    _fijo(lista, "71 AAA1", hasta=_dias(30))
    antes = _filas(lista)
    cambio = {p.producto: p.actualizado_en for p in lista.query(PrecioProducto).all()}

    r = svc.aplicar_vigencias(lista)

    assert (r["pendientes"], r["vencieron"], r["comenzaron"], r["recalculados"],
            r["precios_cambiados"], r["omitido"]) == (0, 0, 0, 0, 0, False)
    assert (r["con_periodo"], r["al_dia"], r["hoy"], r["ejemplos"]) == (1, 1, "2026-10-20", [])
    assert _filas(lista) == antes                       # ni auditoria ni notificacion
    lista.expire_all()
    assert {p.producto: p.actualizado_en for p in lista.query(PrecioProducto).all()} == cambio


def test_un_fijo_vencido_vuelve_a_la_regla_y_la_segunda_corrida_no_escribe_nada(lista, reloj):
    _fijo(lista, "71 AAA1", hasta=_dias(2))
    assert _precio(lista, "71 AAA1").precio_final == 990
    reloj(_dias(3))                                       # el Hasta paso ayer
    antes = _filas(lista)

    r = svc.aplicar_vigencias(lista)

    assert (r["con_periodo"], r["al_dia"], r["pendientes"]) == (1, 0, 1)
    assert (r["vencieron"], r["comenzaron"], r["recalculados"], r["precios_cambiados"]) == (1, 0, 1, 1)
    p = _precio(lista, "71 AAA1")
    assert (p.precio_final, p.estado, p.vigencia_aplicada) == (17800, "OK", "vencida")
    despues = _filas(lista)
    assert despues["vigencias"] == antes["vigencias"] + 1       # UNA auditoria propia
    assert despues["notificaciones"] == antes["notificaciones"] + 1     # y UNA notificacion
    cambios = lista.query(PrecioCambio).filter_by(producto="71 AAA1", campo="precio").all()
    assert [(c.antes, c.despues) for c in cambios] == [("990", "17800")]

    # La segunda corrida seguida: ceros y NINGUNA fila nueva.
    r2 = svc.aplicar_vigencias(lista)
    assert (r2["pendientes"], r2["vencieron"], r2["recalculados"], r2["precios_cambiados"]) == (0, 0, 0, 0)
    assert (r2["con_periodo"], r2["al_dia"]) == (1, 1)
    assert _filas(lista) == despues


def test_una_decision_programada_que_empieza_toma_efecto(lista, reloj):
    _fijo(lista, "71 AAA1", desde=_dias(3))
    p = _precio(lista, "71 AAA1")
    assert (p.precio_final, p.vigencia_aplicada) == (17800, "programada")      # todavia no rige
    reloj(_dias(3))                                       # el Desde es hoy: rige

    r = svc.aplicar_vigencias(lista)

    assert (r["comenzaron"], r["vencieron"], r["recalculados"], r["precios_cambiados"]) == (1, 0, 1, 1)
    p = _precio(lista, "71 AAA1")
    assert (p.precio_final, p.estado, p.vigencia_aplicada) == (990, "FIJO", "vigente")
    c = lista.query(PrecioCambio).filter_by(producto="71 AAA1", campo="precio").one()
    assert (c.antes, c.despues) == ("17800", "990")


def test_el_atraso_de_varios_dias_pasa_de_programada_a_vencida_de_un_salto(lista, reloj):
    _fijo(lista, "71 AAA1", desde=_dias(3), hasta=_dias(5))
    assert _precio(lista, "71 AAA1").vigencia_aplicada == "programada"
    reloj(_dias(40))                          # nadie abrio la lista en 5 semanas

    r = svc.aplicar_vigencias(lista)

    assert (r["vencieron"], r["comenzaron"], r["recalculados"]) == (1, 0, 1)
    p = _precio(lista, "71 AAA1")
    assert (p.vigencia_aplicada, p.precio_final, p.estado) == ("vencida", 17800, "OK")
    assert lista.query(PrecioCambio).count() == 0       # nunca rigio: el precio no se movio


def test_solo_toca_a_los_candidatos(lista, reloj):
    _nuevo(lista, "71 VIG1")
    _fijo(lista, "71 VIG1", hasta=_dias(30))              # con periodo, pero sigue vigente
    _fijo(lista, "71 AAA1", hasta=_dias(2))
    reloj(_dias(3))
    antes = {p.producto: p.actualizado_en for p in lista.query(PrecioProducto).all()}

    svc.aplicar_vigencias(lista)

    lista.expire_all()
    despues = {p.producto: p.actualizado_en for p in lista.query(PrecioProducto).all()}
    assert despues["71 AAA1"] != antes["71 AAA1"]
    for intacto in ("13 BBB2", "71 CCC3", "71 VIG1"):            # sin periodo, y con periodo vigente
        assert despues[intacto] == antes[intacto], intacto


def test_respeta_el_limite_y_la_siguiente_corrida_completa_el_resto(lista, reloj):
    codigos = [_nuevo(lista, f"71 LIM{n}") for n in range(1, 6)]
    for c in codigos:
        _fijo(lista, c, hasta=_dias(2))
    reloj(_dias(3))

    r1 = svc.aplicar_vigencias(lista, limite=2)
    assert (r1["pendientes"], r1["recalculados"], r1["vencieron"]) == (5, 2, 2)
    marcadores = {c: _precio(lista, c).vigencia_aplicada for c in codigos}
    assert marcadores == {"71 LIM1": "vencida", "71 LIM2": "vencida", "71 LIM3": "vigente",
                          "71 LIM4": "vigente", "71 LIM5": "vigente"}     # siempre en orden de codigo

    r2 = svc.aplicar_vigencias(lista, limite=2)
    assert (r2["pendientes"], r2["recalculados"]) == (3, 2)
    r3 = svc.aplicar_vigencias(lista, limite=2)
    assert (r3["pendientes"], r3["recalculados"]) == (1, 1)
    r4 = svc.aplicar_vigencias(lista, limite=2)
    assert (r4["pendientes"], r4["recalculados"]) == (0, 0)
    assert {_precio(lista, c).precio_final for c in codigos} == {17800}


def test_un_marcador_huerfano_se_limpia(lista, reloj):
    """El marcador dice 'vigente' pero el producto ya no tiene periodo (alguien le quito la
    decision por un camino que no recalculo): se limpia y el precio no se mueve."""
    p = _precio(lista, "71 CCC3")
    p.vigencia_aplicada = "vigente"
    lista.commit()

    r = svc.aplicar_vigencias(lista)

    assert (r["pendientes"], r["recalculados"], r["vencieron"], r["comenzaron"]) == (1, 1, 0, 0)
    p = _precio(lista, "71 CCC3")
    assert (p.vigencia_aplicada, p.precio_final, p.estado) == (None, 2160, "CONGELADO")
    assert lista.query(PrecioCambio).count() == 0
    assert svc.aplicar_vigencias(lista)["pendientes"] == 0


def test_un_periodo_sin_decision_tampoco_deja_un_marcador_colgando(lista, reloj):
    """Fechas guardadas sin ninguna de las tres decisiones no gobiernan nada."""
    _poner_fechas_sin_decision(lista, "71 AAA1")
    p = _precio(lista, "71 AAA1")
    p.vigencia_aplicada = "vencida"
    lista.commit()

    r = svc.aplicar_vigencias(lista)

    assert (r["con_periodo"], r["pendientes"], r["recalculados"]) == (0, 1, 1)
    assert _precio(lista, "71 AAA1").vigencia_aplicada is None


def _poner_fechas_sin_decision(db, producto):
    db.add(PrecioOverride(tenant_id="curifor", producto=producto, obs="x",
                          vigente_desde=_dias(-5), vigente_hasta=_dias(-1)))
    db.commit()


def test_previsualizar_cuenta_pero_no_escribe(lista, reloj):
    _fijo(lista, "71 AAA1", hasta=_dias(2))
    reloj(_dias(3))
    antes = _filas(lista)

    r = svc.aplicar_vigencias(lista, previsualizar=True)

    assert r["previsualizar"] is True
    assert (r["pendientes"], r["vencieron"], r["precios_cambiados"], r["recalculados"]) == (1, 1, 1, 0)
    e = r["ejemplos"][0]
    assert (e["producto"], e["vigencia_antes"], e["vigencia_despues"]) == ("71 AAA1", "vigente", "vencida")
    assert (e["precio_antes"], e["precio_despues"]) == (990, 17800)
    p = _precio(lista, "71 AAA1")
    assert (p.precio_final, p.vigencia_aplicada) == (990, "vigente")
    assert _filas(lista) == antes


def test_un_vencimiento_cuyo_precio_coincide_con_la_regla_no_deja_fila_de_cambio(lista, reloj):
    _fijo(lista, "71 AAA1", hasta=_dias(2), precio=17800)         # el fijo era justo el de la regla
    reloj(_dias(3))
    antes = _filas(lista)

    r = svc.aplicar_vigencias(lista)

    assert (r["vencieron"], r["recalculados"], r["precios_cambiados"]) == (1, 1, 0)
    p = _precio(lista, "71 AAA1")
    assert (p.estado, p.vigencia_aplicada, p.precio_final) == ("OK", "vencida", 17800)
    despues = _filas(lista)
    assert despues["cambios"] == antes["cambios"]                 # el precio no cambio: sin fila
    assert despues["notificaciones"] == antes["notificaciones"]   # y sin aviso a la campanita
    assert despues["vigencias"] == antes["vigencias"] + 1         # pero la auditoria si queda


def test_n_vencimientos_con_precio_distinto_dejan_exactamente_n_filas_de_precio(lista, reloj):
    codigos = [_nuevo(lista, f"71 NNN{n}") for n in range(1, 7)]
    for c in codigos:
        _fijo(lista, c, hasta=_dias(2))
    reloj(_dias(3))
    antes = _filas(lista)

    r = svc.aplicar_vigencias(lista)

    assert (r["vencieron"], r["precios_cambiados"]) == (6, 6)
    lista.expire_all()
    filas = lista.query(PrecioCambio).filter(PrecioCambio.producto.in_(codigos)).all()
    assert sorted((f.producto, f.campo) for f in filas) == [(c, "precio") for c in codigos]
    despues = _filas(lista)
    assert despues["cambios"] == antes["cambios"] + 6
    assert despues["vigencias"] == antes["vigencias"] + 1        # UNA auditoria para los seis
    assert despues["notificaciones"] == antes["notificaciones"] + 1


def test_el_titulo_de_la_notificacion_cuenta_lo_que_volvio_y_lo_que_empezo(lista, reloj):
    _nuevo(lista, "71 TIT1")
    _nuevo(lista, "71 TIT2")
    _nuevo(lista, "71 TIT3")
    _fijo(lista, "71 TIT1", hasta=_dias(2))
    _fijo(lista, "71 TIT2", hasta=_dias(2))
    _fijo(lista, "71 TIT3", desde=_dias(3))
    reloj(_dias(3))

    svc.aplicar_vigencias(lista)

    lista.expire_all()
    n = lista.query(Notificacion).filter(Notificacion.titulo.like("Vigencias de precios%")).one()
    assert n.titulo == "Vigencias de precios: 2 volvieron a la regla, 1 empezó"
    assert n.tipo == "precios" and n.creado_por_email == "vigencias"

    assert svc._titulo_vigencias(1, 0) == "Vigencias de precios: 1 volvió a la regla"
    assert svc._titulo_vigencias(0, 3) == "Vigencias de precios: 3 empezaron"
    assert svc._titulo_vigencias(0, 0) == "Vigencias de precios: periodos reajustados"


def test_el_barrido_nunca_modifica_precio_override(lista, reloj):
    for n in range(1, 4):
        _fijo(lista, _nuevo(lista, f"71 OVR{n}"), hasta=_dias(2))
    _fijo(lista, "71 AAA1", desde=_dias(3))
    reloj(_dias(3))

    def foto():
        lista.expire_all()
        return [(o.producto, o.precio_fijo, o.margen_fijo, o.congelar, o.congelado_precio,
                 o.vigente_desde, o.vigente_hasta, o.obs, o.editado_por, o.editado_en)
                for o in lista.query(PrecioOverride).order_by(PrecioOverride.producto).all()]

    antes = foto()
    r = svc.aplicar_vigencias(lista)
    assert r["recalculados"] == 4

    assert foto() == antes                    # ni siquiera editado_por / editado_en


def test_con_el_candado_ocupado_se_omite_y_no_escribe(lista, reloj):
    _fijo(lista, "71 AAA1", hasta=_dias(2))
    reloj(_dias(3))
    antes = _filas(lista)

    assert svc._CANDADO_BARRIDO.acquire(blocking=False)
    try:
        r = svc.aplicar_vigencias(lista)
    finally:
        svc._CANDADO_BARRIDO.release()

    assert (r["omitido"], r["recalculados"], r["vencieron"]) == (True, 0, 0)
    assert r["pendientes"] == 1                                  # dice cuantos quedan
    assert _precio(lista, "71 AAA1").precio_final == 990
    assert _filas(lista) == antes

    assert svc.aplicar_vigencias(lista)["omitido"] is False       # libre: ahora si
    assert _precio(lista, "71 AAA1").precio_final == 17800


def test_sin_candidatos_ni_toca_el_candado_ni_espera(lista, reloj):
    """El candado es solo para escribir: una lectura sin nada que aplicar no espera a un
    barrido ajeno (la pantalla pide el resumen y la lista casi a la vez)."""
    assert svc._CANDADO_BARRIDO.acquire(blocking=False)
    try:
        r = svc.aplicar_vigencias(lista, espera_s=1)
    finally:
        svc._CANDADO_BARRIDO.release()

    assert (r["omitido"], r["pendientes"], r["recalculados"]) == (False, 0, 0)


def test_espera_el_candado_y_sigue_cuando_se_libera(lista, reloj):
    _fijo(lista, "71 AAA1", hasta=_dias(2))
    reloj(_dias(3))
    svc._CANDADO_BARRIDO.acquire()
    soltar = threading.Timer(0.3, svc._CANDADO_BARRIDO.release)
    soltar.start()
    try:
        r = svc.aplicar_vigencias(lista, espera_s=5)
    finally:
        soltar.join()

    assert (r["omitido"], r["recalculados"]) == (False, 1)
    assert _precio(lista, "71 AAA1").precio_final == 17800


def test_relee_los_candidatos_con_el_candado_tomado(lista, reloj, monkeypatch):
    """Mientras esperaba el candado, otro barrido hizo el trabajo: no se recalcula dos veces."""
    _fijo(lista, "71 AAA1", hasta=_dias(2))
    reloj(_dias(3))
    real = svc._candidatos_vigencia
    llamadas = []

    def con_otro_barrido_en_medio(db, hoy):
        llamadas.append(1)
        if len(llamadas) == 2:                  # la lectura con el candado puesto
            svc.recalcular(db, usuario="otro", refrescar_insumos=False, productos=["71 AAA1"],
                           accion="precios_vigencias")
        return real(db, hoy)

    monkeypatch.setattr(svc, "_candidatos_vigencia", con_otro_barrido_en_medio)

    r = svc.aplicar_vigencias(lista)

    assert len(llamadas) == 2
    assert (r["pendientes"], r["recalculados"], r["omitido"]) == (0, 0, False)
    assert _filas(lista)["vigencias"] == 1                       # solo la del otro


def test_el_candado_se_suelta_aunque_el_recalculo_falle(lista, reloj, monkeypatch):
    _fijo(lista, "71 AAA1", hasta=_dias(2))
    reloj(_dias(3))
    monkeypatch.setattr(svc, "recalcular", _boom)

    with pytest.raises(RuntimeError):
        svc.aplicar_vigencias(lista)

    assert svc._CANDADO_BARRIDO.acquire(blocking=False)
    svc._CANDADO_BARRIDO.release()


def test_los_ejemplos_son_a_lo_mas_20(lista, reloj):
    codigos = [_nuevo(lista, f"71 EJ{n:02d}") for n in range(22)]
    for c in codigos:
        _fijo(lista, c, hasta=_dias(2))
    reloj(_dias(3))

    r = svc.aplicar_vigencias(lista)

    assert (r["pendientes"], r["recalculados"]) == (22, 22)
    assert len(r["ejemplos"]) == 20
    assert r["ejemplos"][0]["producto"] == "71 EJ00"


def test_el_barrido_usa_el_dia_de_chile(lista, monkeypatch):
    """31-10 a las 23:30 en Chile ya es 1 de noviembre en UTC: el Hasta del 31 todavia rige."""
    ahora = {"t": datetime(2026, 10, 20, 10, 0, tzinfo=calendario.TZ_CHILE)}
    monkeypatch.setattr(calendario, "ahora_chile", lambda: ahora["t"])
    _fijo(lista, "71 AAA1", hasta=datetime(2026, 10, 31).date())

    ahora["t"] = datetime(2026, 10, 31, 23, 30, tzinfo=calendario.TZ_CHILE)
    assert ahora["t"].astimezone(timezone.utc).date().isoformat() == "2026-11-01"
    r = svc.aplicar_vigencias(lista)
    assert (r["hoy"], r["pendientes"]) == ("2026-10-31", 0)

    ahora["t"] = datetime(2026, 11, 1, 0, 5, tzinfo=calendario.TZ_CHILE)
    r = svc.aplicar_vigencias(lista)
    assert (r["hoy"], r["pendientes"], r["vencieron"]) == ("2026-11-01", 1, 1)


# ============================================ 2. recalcular: mismo resultado
def test_recalcular_completo_y_dirigido_dan_el_mismo_precio_y_marcador(lista, reloj):
    for c in ("71 XXX1", "71 YYY1"):
        _fijo(lista, _nuevo(lista, c), hasta=_dias(2))
    reloj(_dias(3))

    svc.recalcular(lista, refrescar_insumos=False, productos=["71 XXX1"])       # dirigido
    svc.recalcular(lista, refrescar_insumos=False)                              # completo

    def valores(c):
        p = _precio(lista, c)
        return (p.precio_final, p.precio_calculado, p.estado, p.factor, p.vigencia_aplicada)

    assert valores("71 XXX1") == valores("71 YYY1") == (17800, 17800, "OK", 1.78, "vencida")


def test_recalcular_sin_los_argumentos_nuevos_deja_lo_de_siempre(lista):
    p = _precio(lista, "71 AAA1")
    p.costo = 20000
    lista.commit()

    r = svc.recalcular(lista, usuario="ana@curifor.com", refrescar_insumos=False)

    assert r["precios_distintos"] == 1
    lista.expire_all()
    assert lista.query(AuditoriaLog).filter_by(accion="precios_recalculados").count() == 2   # el de la fixture
    n = lista.query(Notificacion).one()
    assert n.titulo == "Lista de precios recalculada: 1 cambios en 1 productos"


def test_recalcular_con_accion_y_titulo_deja_su_propio_rastro(lista):
    p = _precio(lista, "71 AAA1")
    p.costo = 20000
    lista.commit()

    svc.recalcular(lista, usuario="ana@curifor.com", refrescar_insumos=False, productos=["71 AAA1"],
                   accion="precios_vigencias", titulo="Vigencias de precios: 1 volvió a la regla")

    lista.expire_all()
    assert lista.query(AuditoriaLog).filter_by(accion="precios_vigencias").count() == 1
    assert lista.query(AuditoriaLog).filter_by(accion="precios_recalculados").count() == 1   # solo el de la fixture
    assert lista.query(Notificacion).one().titulo == "Vigencias de precios: 1 volvió a la regla"


# ============================================== 3. lectura: el barrido perezoso
def test_el_resumen_aplica_el_barrido_sube_los_pendientes_y_trae_el_bloque_vigencias(client, lista, reloj):
    _fijo(lista, "71 AAA1", hasta=_dias(2))
    client.get("/api/precios/exportar")                  # el dia 0 se envia todo, el fijo a 990
    r = client.get("/api/precios/resumen").json()
    assert r["pendientes_envio"] == 0
    assert r["vigencias"] == {"hoy": "2026-10-20", "vigentes": 1, "programadas": 0, "vencidas": 0,
                              "vencen_7_dias": 1, "por_aplicar": 0}
    reloj(_dias(3))

    r = client.get("/api/precios/resumen").json()

    assert r["pendientes_envio"] == 1                    # vuelve a la regla y el ERP no lo sabe
    assert r["vigencias"] == {"hoy": "2026-10-23", "vigentes": 0, "programadas": 0, "vencidas": 1,
                              "vencen_7_dias": 0, "por_aplicar": 0}
    assert r["por_estado"].get("FIJO") == 1              # solo 13 BBB2, el permanente


def test_la_lista_aplica_el_barrido_antes_de_leer(client, lista, reloj):
    _fijo(lista, "71 AAA1", hasta=_dias(2))
    reloj(_dias(3))

    items = {i["producto"]: i for i in client.get("/api/precios").json()["items"]}

    f = items["71 AAA1"]
    assert (f["precio_final"], f["estado"], f["vigencia"]) == (17800, "OK", "vencida")
    assert f["precio_fijo"] == 990                       # la decision sigue guardada, para renovarla


def test_exportar_erp_sin_barrido_previo_trae_el_precio_de_la_regla_y_registra_el_envio(client, lista, reloj):
    _fijo(lista, "71 AAA1", hasta=_dias(2))
    assert {f[0]: f[1] for f in _csv(client.get("/api/precios/exportar"))[1:]}["71 AAA1"] == "990"
    reloj(_dias(3))                                      # nadie abrio el resumen ni la lista

    r = client.get("/api/precios/exportar", params={"solo_diferencias": True})

    filas = _csv(r)
    assert filas[0] == ["SKU", "Precio_Optimo", "Descuento"]
    assert [f[:2] for f in filas[1:]] == [["71 AAA1", "17800"]]       # no el 990 vencido
    assert r.headers["X-Filas"] == "1"
    assert lista.query(PrecioEnvio).filter_by(producto="71 AAA1").count() == 2
    assert client.get("/api/precios/resumen").json()["pendientes_envio"] == 0


@pytest.mark.parametrize("formato", ["completa", "editable"])
def test_la_lista_completa_y_la_editable_traen_el_precio_de_la_regla(client, lista, reloj, formato):
    _fijo(lista, "71 AAA1", hasta=_dias(2))
    reloj(_dias(3))

    filas = _csv(client.get("/api/precios/exportar", params={"formato": formato}))

    fila = dict(zip(filas[0], next(f for f in filas[1:] if f[0] == "71 AAA1")))
    assert (fila["Precio final"], fila["Estado"]) == ("17800", "OK")


def test_un_barrido_que_falla_no_rompe_la_lectura(client, lista, reloj, monkeypatch):
    _fijo(lista, "71 AAA1", hasta=_dias(2))
    reloj(_dias(3))
    monkeypatch.setattr(svc, "aplicar_vigencias", _boom)

    r = client.get("/api/precios/resumen")
    assert r.status_code == 200
    assert r.json()["vigencias"]["por_aplicar"] == 1     # y lo dice: hay un vencimiento sin aplicar
    assert client.get("/api/precios").status_code == 200
    for formato in ("completa", "editable"):
        assert client.get("/api/precios/exportar", params={"formato": formato}).status_code == 200


def test_el_archivo_del_erp_no_sale_con_un_vencimiento_sin_aplicar(client, lista, reloj, monkeypatch):
    """El archivo del ERP es donde un precio de campana vencido hace dano: si el barrido no
    pudo dejar la lista al dia, no se baja (503, que la web reintenta) ni se registra un envio."""
    _fijo(lista, "71 AAA1", hasta=_dias(2))
    reloj(_dias(3))
    monkeypatch.setattr(svc, "aplicar_vigencias", _boom)

    r = client.get("/api/precios/exportar")

    assert r.status_code == 503
    assert "vencimientos" in r.json()["detail"]
    assert lista.query(PrecioEnvio).count() == 0


def test_el_archivo_del_erp_sale_igual_si_el_barrido_falla_pero_no_habia_nada_que_aplicar(
        client, lista, reloj, monkeypatch):
    monkeypatch.setattr(svc, "aplicar_vigencias", _boom)

    assert client.get("/api/precios/exportar").status_code == 200


def test_el_tope_de_las_pantallas_deja_el_resto_por_aplicar_y_la_descarga_no_tiene_tope(
        client, lista, reloj, monkeypatch):
    monkeypatch.setattr(svc, "LIMITE_BARRIDO_PANTALLA", 2)
    codigos = [_nuevo(lista, f"71 TOP{n}") for n in range(1, 6)]
    for c in codigos:
        _fijo(lista, c, hasta=_dias(2))
    reloj(_dias(3))

    v = client.get("/api/precios/resumen").json()["vigencias"]
    assert (v["vencidas"], v["vigentes"], v["por_aplicar"]) == (2, 3, 3)
    v = client.get("/api/precios/resumen").json()["vigencias"]
    assert (v["vencidas"], v["por_aplicar"]) == (4, 1)

    assert client.get("/api/precios/exportar").status_code == 200       # sin tope
    assert svc.vigencias_por_aplicar(lista) == 0
    assert {_precio(lista, c).precio_final for c in codigos} == {17800}


def test_los_nombres_de_archivo_llevan_la_fecha_de_chile(lista, monkeypatch):
    """A las 23:30 del 31-10 en Chile, en UTC ya es noviembre."""
    monkeypatch.setattr(calendario, "ahora_chile",
                        lambda: datetime(2026, 10, 31, 23, 30, tzinfo=calendario.TZ_CHILE))

    nombres = {
        formato: svc.exportar(lista, solo_diferencias=False, registrar=False, usuario=None,
                              formato=formato)[1]
        for formato in ("erp", "completa", "editable")
    }

    assert nombres == {"erp": "precios_completa_20261031.csv",
                       "completa": "lista_precios_completa_2026-10-31.csv",
                       "editable": "lista_precios_para_editar_2026-10-31.csv"}
    assert svc.exportar(lista, solo_diferencias=True, registrar=False, usuario=None)[1] \
        == "precios_diferencias_20261031.csv"


def test_las_consultas_del_barrido_compilan_en_postgres():
    """Los tests corren en SQLite y produccion en Postgres: una consulta que solo SQLite
    acepta se descubre en produccion (06-10-2026). Se compila contra el dialecto real."""
    from datetime import date as _date

    from sqlalchemy import func, select
    from sqlalchemy.dialects import postgresql

    def sql(consulta):
        return str(consulta.compile(dialect=postgresql.dialect()))

    candidatos = sql(svc._consulta_candidatos_vigencia("curifor"))
    assert "LEFT OUTER JOIN precio_override" in candidatos
    assert "vigencia_aplicada IS NOT NULL" in candidatos and "vigente_desde IS NOT NULL" in candidatos

    vence = sql(select(func.count()).select_from(PrecioProducto)
                .where(svc._cond_vence_pronto(_date(2026, 10, 20))))
    assert "precio_override.vigente_hasta >=" in vence and "precio_override.vigente_hasta <=" in vence

    class F:                                    # los filtros de la lista, con las cuatro opciones
        vigencia = ["programada", "vigente", "vencida", "vence_7d"]

    assert "vigencia_aplicada IN" in sql(svc._filtrar(select(PrecioProducto), F))


def test_el_barrido_y_la_descarga_no_usan_la_fecha_del_servidor():
    """Render corre en UTC: la fecha del servidor adelanta el dia 3 horas."""
    import re

    prohibido = re.compile(r"date\.today\(|datetime\.today\(|utcnow|\.date\(\)")
    for f in (svc.aplicar_vigencias, svc._candidatos_vigencia, svc._barrido_perezoso,
              svc._simular_vigencias, svc.vigencias_por_aplicar, svc._resumen_vigencias,
              svc._cond_vence_pronto, svc._filtrar, svc.resumen, svc.exportar):
        assert not prohibido.search(inspect.getsource(f)), f"{f.__name__} usa la fecha del servidor"


# ========================================================= 4. filtros y resumen
@pytest.fixture()
def escenario(lista, reloj):
    """Al dia +2: A, C, E, F, G vigentes; B programada; D vencida. Vencen en 7 dias (hoy..hoy+7):
    A (Hasta +3), E (+9 = hoy+7) y G (+2 = hoy); F (+10 = hoy+8) no."""
    for c, kw in {
        "71 AAA1": {"hasta": _dias(3)},
        "71 VB": {"desde": _dias(30)},
        "71 VC": {"hasta": _dias(60)},
        "71 VD": {"hasta": _dias(1)},
        "71 VE": {"hasta": _dias(9)},
        "71 VF": {"hasta": _dias(10)},
        "71 VG": {"hasta": _dias(2)},
    }.items():
        if c != "71 AAA1":
            _nuevo(lista, c)
        _fijo(lista, c, **kw)
    reloj(_dias(2))
    return lista


def _codigos(client, **params):
    r = client.get("/api/precios", params=params)
    assert r.status_code == 200, r.text
    return {i["producto"] for i in r.json()["items"]}


def test_filtro_por_estado_de_vigencia(client, escenario):
    assert _codigos(client, vigencia="vigente") == {"71 AAA1", "71 VC", "71 VE", "71 VF", "71 VG"}
    assert _codigos(client, vigencia="programada") == {"71 VB"}
    assert _codigos(client, vigencia="vencida") == {"71 VD"}
    assert _codigos(client, vigencia=["vencida", "programada"]) == {"71 VB", "71 VD"}


def test_filtro_vence_en_7_dias_incluye_hoy_y_hoy_mas_siete(client, escenario):
    assert _codigos(client, vigencia="vence_7d") == {"71 AAA1", "71 VE", "71 VG"}
    # Se puede combinar con un estado: es una union.
    assert _codigos(client, vigencia=["vence_7d", "programada"]) == {"71 AAA1", "71 VE", "71 VG", "71 VB"}


def test_el_filtro_de_vigencia_se_combina_con_los_demas(client, escenario):
    assert _codigos(client, vigencia="vigente", estado="FIJO") == {"71 AAA1", "71 VC", "71 VE", "71 VF", "71 VG"}
    assert _codigos(client, vigencia="vencida", estado="FIJO") == set()
    assert _codigos(client, vigencia="vencida", estado="OK") == {"71 VD"}


def test_un_valor_de_vigencia_que_no_existe_da_422(client, escenario):
    r = client.get("/api/precios", params={"vigencia": "vencido"})
    assert r.status_code == 422
    assert "vigente" in r.json()["detail"] and "vence_7d" in r.json()["detail"]


def test_el_resumen_cuenta_cada_estado_y_los_que_vencen_pronto(client, escenario):
    v = client.get("/api/precios/resumen").json()["vigencias"]

    assert v == {"hoy": "2026-10-22", "vigentes": 5, "programadas": 1, "vencidas": 1,
                 "vencen_7_dias": 3, "por_aplicar": 0}


def test_el_resumen_sin_periodos_trae_el_bloque_en_ceros(client, lista, reloj):
    v = client.get("/api/precios/resumen").json()["vigencias"]

    assert v == {"hoy": "2026-10-20", "vigentes": 0, "programadas": 0, "vencidas": 0,
                 "vencen_7_dias": 0, "por_aplicar": 0}


# =========================================================== 5. el endpoint admin
def test_admin_sin_sesion_da_401():
    with TestClient(app) as c:
        assert c.post(ADMIN).status_code == 401


def test_admin_si_no_es_admin_da_403(client, lista, reloj):
    _fijo(lista, "71 AAA1", hasta=_dias(2))
    reloj(_dias(3))
    _como_no_admin(client)

    assert client.post(ADMIN).status_code == 403
    assert client.post(ADMIN, json={"previsualizar": True}).status_code == 403
    assert _precio(lista, "71 AAA1").precio_final == 990        # no hizo nada


def test_admin_aplica_y_la_segunda_llamada_va_en_ceros(client, lista, reloj):
    _fijo(lista, "71 AAA1", hasta=_dias(2))
    reloj(_dias(3))

    r = client.post(ADMIN)                                # el cuerpo es opcional

    assert r.status_code == 200, r.text
    d = r.json()
    assert set(d) == {"hoy", "con_periodo", "al_dia", "pendientes", "vencieron", "comenzaron",
                      "recalculados", "precios_cambiados", "omitido", "previsualizar", "ejemplos"}
    assert (d["hoy"], d["con_periodo"], d["al_dia"], d["pendientes"]) == ("2026-10-23", 1, 0, 1)
    assert (d["vencieron"], d["comenzaron"], d["recalculados"], d["precios_cambiados"]) == (1, 0, 1, 1)
    assert (d["omitido"], d["previsualizar"]) == (False, False)
    assert d["ejemplos"][0]["producto"] == "71 AAA1"
    assert _precio(lista, "71 AAA1").precio_final == 17800
    # Queda a nombre de quien lo pidio.
    a = lista.query(AuditoriaLog).filter_by(accion="precios_vigencias").one()
    assert a.usuario_email == "test@curifor.com"

    antes = _filas(lista)
    d2 = client.post(ADMIN, json={}).json()
    assert (d2["pendientes"], d2["vencieron"], d2["comenzaron"], d2["recalculados"],
            d2["precios_cambiados"], d2["omitido"]) == (0, 0, 0, 0, 0, False)
    assert (d2["con_periodo"], d2["al_dia"]) == (1, 1)
    assert _filas(lista) == antes                          # y no escribio ninguna fila


def test_admin_previsualizar_no_escribe(client, lista, reloj):
    _fijo(lista, "71 AAA1", hasta=_dias(2))
    reloj(_dias(3))
    antes = _filas(lista)

    d = client.post(ADMIN, json={"previsualizar": True}).json()

    assert (d["previsualizar"], d["pendientes"], d["precios_cambiados"], d["recalculados"]) == (True, 1, 1, 0)
    assert _precio(lista, "71 AAA1").precio_final == 990
    assert _filas(lista) == antes


def test_admin_rechaza_campos_que_no_conoce(client, lista):
    assert client.post(ADMIN, json={"previsualisar": True}).status_code == 422


def test_admin_responde_omitido_si_hay_otro_barrido_en_curso(client, lista, reloj):
    _fijo(lista, "71 AAA1", hasta=_dias(2))
    reloj(_dias(3))

    assert svc._CANDADO_BARRIDO.acquire(blocking=False)
    try:
        d = client.post(ADMIN).json()
    finally:
        svc._CANDADO_BARRIDO.release()

    assert (d["omitido"], d["recalculados"], d["pendientes"]) == (True, 0, 1)
    assert _precio(lista, "71 AAA1").precio_final == 990


# ---- Revision final: el barrido no corre en medio de un recalculo hecho a mano ----

def test_el_barrido_se_salta_mientras_corre_un_recalculo_a_mano(lista, reloj, monkeypatch):
    """Antes el recalculo completo no tomaba el candado: el barrido de una lectura corria en
    medio, y el recalculo volvia a anotar en precio_cambio lo que el barrido ya habia anotado."""
    _fijo(lista, "71 AAA1", hasta=_dias(2))
    reloj(_dias(3))
    en_medio = []

    def recalculo_con_una_lectura_en_medio(db, **kw):
        en_medio.append(svc.aplicar_vigencias(db, espera_s=0.5))     # lo que haria otra persona
        return {"productos": 0}

    monkeypatch.setattr(svc, "recalcular", recalculo_con_una_lectura_en_medio)

    svc.recalcular_a_solas(lista, usuario="a@x.cl", refrescar_insumos=False)

    assert en_medio[0]["omitido"] is True and en_medio[0]["recalculados"] == 0
    assert _filas(lista)["vigencias"] == 0
    assert not svc._RECALCULO_A_SOLAS.is_set()
    assert svc._CANDADO_BARRIDO.acquire(blocking=False)         # y el candado se soltó
    svc._CANDADO_BARRIDO.release()


def test_el_recalculo_a_mano_espera_a_un_barrido_en_curso(lista, reloj):
    reloj(_dias(3))
    svc._CANDADO_BARRIDO.acquire()
    soltar = threading.Timer(0.3, svc._CANDADO_BARRIDO.release)
    soltar.start()
    try:
        r = svc.recalcular_a_solas(lista, usuario="a@x.cl", refrescar_insumos=False)
    finally:
        soltar.join()

    assert r["productos"] >= 1


def test_el_candado_del_recalculo_a_mano_se_suelta_si_falla(lista, monkeypatch):
    monkeypatch.setattr(svc, "recalcular", _boom)

    with pytest.raises(RuntimeError):
        svc.recalcular_a_solas(lista)

    assert not svc._RECALCULO_A_SOLAS.is_set()
    assert svc._CANDADO_BARRIDO.acquire(blocking=False)
    svc._CANDADO_BARRIDO.release()


def test_el_boton_recalcular_pasa_por_el_candado(client, lista, monkeypatch):
    vistos = []

    def espia(db, **kw):
        vistos.append(svc._RECALCULO_A_SOLAS.is_set())
        return {"productos": 0}

    monkeypatch.setattr(svc, "recalcular", espia)

    r = client.post("/api/precios/recalcular?refrescar_insumos=false")

    assert r.status_code == 200, r.text
    assert vistos == [True]
