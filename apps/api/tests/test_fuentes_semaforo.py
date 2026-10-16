"""Semaforo de Fuentes de datos: un test por regla de §3.6.

`fuentes_service.semaforo` y `alertas_franja` son funciones puras: reciben el estado
que reporto el motor, la configuracion y la hora, y no leen la base ni el reloj. La
"foto de hoy" se prueba de punta a punta, por la API.
"""
import json
from datetime import date, datetime, timedelta, timezone

import pytest

from src.models import MotorCorrida
from src.services import fuentes_service as svc
from src.services.calendario import TZ_CHILE, a_chile, dias_habiles_entre, inicio_del_dia_chile

from .test_fuentes import CARPETAS, CATALOGO, FUENTES, URL, estado, fuentes_del_dia, listados, \
    mandar, sembrado

VIERNES = datetime(2026, 10, 16, 10, 0, tzinfo=TZ_CHILE)
CFG = {f["clave"]: f for f in FUENTES}
CARP = {c["clave"]: c for c in CARPETAS}


def _sem(clave, est, *, anterior=None, ahora=VIERNES, modo="prueba", cfg=None, **kw):
    return svc.semaforo(est, cfg or CFG[clave], anterior, ahora, catalogo=CATALOGO[clave],
                        modo=modo, carpetas=CARP, **kw)


def _hoy(clave, hora="09:34", dia="2026-10-16", **extra):
    e = estado(clave, dia, **extra)
    for a in e["archivos"]:
        a["modificado_en"] = f"{dia}T{hora}:00-03:00"
    return e


def _reglas(s):
    return [a["regla"] for a in s["alertas"]]


# --------------------------------------------------------------------------- #
# Calendario
# --------------------------------------------------------------------------- #
def test_dias_habiles_no_cuentan_el_fin_de_semana():
    assert dias_habiles_entre(date(2026, 10, 16), date(2026, 10, 19)) == 1   # viernes -> lunes
    assert dias_habiles_entre(date(2026, 10, 14), date(2026, 10, 16)) == 2
    assert dias_habiles_entre(date(2026, 10, 16), date(2026, 10, 16)) == 0


def test_a_las_22_de_chile_hoy_sigue_siendo_hoy():
    # 22:00 de Chile del viernes son las 01:00 UTC del sabado.
    ahora_utc = datetime(2026, 10, 17, 1, 0, tzinfo=timezone.utc)
    assert a_chile(ahora_utc).date() == date(2026, 10, 16)
    s = _sem("stock_bodegas", _hoy("stock_bodegas"), ahora=ahora_utc)
    assert s["edad_dias_habiles"] == 0
    assert s["regla"] == "al_dia"
    assert "de hoy a las 09:34" in s["texto"]
    assert inicio_del_dia_chile(date(2026, 10, 16)) == datetime(2026, 10, 16, 3, 0,
                                                                tzinfo=timezone.utc)


def test_el_lunes_no_cuenta_el_fin_de_semana():
    lunes = datetime(2026, 10, 19, 10, 0, tzinfo=TZ_CHILE)
    s = _sem("stock_bodegas", _hoy("stock_bodegas", dia="2026-10-16"), ahora=lunes)
    assert s["edad_dias_habiles"] == 1
    assert (s["nivel"], s["etiqueta"]) == ("verde", "Al día")
    assert "del viernes a las 09:34" in s["texto"]


# --------------------------------------------------------------------------- #
# Fuente: rojo
# --------------------------------------------------------------------------- #
def test_vencido():
    s = _sem("stock_bodegas_frontera", _hoy("stock_bodegas_frontera", dia="2026-10-13"))
    assert (s["nivel"], s["etiqueta"], s["regla"]) == ("rojo", "Vencido", "vencido")
    assert s["texto"].startswith("Vencido: stock_frontera.xlsx tiene 3 días hábiles y se espera "
                                 "cada 2. Mientras siga así, el sugerido no se publica.")
    assert "OneDrive esté sincronizado" in s["texto"]


def test_falta_una_obligatoria():
    falta = {"hecho": "falta", "archivos": []}
    s = _sem("seguimiento_curifor_nacional", falta, modo="activa")
    assert (s["nivel"], s["etiqueta"]) == ("rojo", "Falta")
    assert s["texto"] == ("Falta: no hay ningún archivo cuyo nombre contenga 'seguimiento' en "
                          "Bases de datos. El sugerido no se publica hasta que aparezca.")
    # En prueba (o sin configurar) la obligatoria todavia no frena: el texto lo dice.
    s = _sem("seguimiento_curifor_nacional", falta, modo="prueba")
    assert s["nivel"] == "rojo" and "con la configuración activa esto frenaría" in s["texto"]
    # Con subcarpeta, el texto la nombra como la ve la persona.
    cfg = dict(CFG["seguimiento_curifor_nacional"],
               ubicaciones=[{"carpeta": "bases_de_datos", "subcarpeta": "Seguimientos de compras",
                             "recursiva": False}])
    s = _sem("seguimiento_curifor_nacional", falta, cfg=cfg, modo="activa")
    assert "en Bases de datos › Seguimientos de compras." in s["texto"]


def test_carpeta_no_encontrada():
    s = _sem("stock_bodegas", {"hecho": "carpeta_no_encontrada", "archivos": []},
             listados={l["clave"]: l for l in listados(sin=("databi_datos",))},
             alias_pc="PC de la jefa", pc="PC-JEFA-01")
    # La primera ubicacion (Bases de datos) existe; la que falta es la de SharePoint.
    assert (s["nivel"], s["etiqueta"]) == ("rojo", "Carpeta no encontrada")
    assert s["texto"] == ("El PC de la jefa no tiene esta carpeta. Abre OneDrive, agrega el "
                          "acceso directo a 'Data BI › Datos' y, con clic derecho, elige "
                          "'Mantener siempre en este dispositivo'.")


@pytest.mark.parametrize("filas, anterior, rojo", [
    (0, None, True),            # 0 filas siempre
    (9000, 19883, True),        # menos del 60 % de la corrida anterior
    (11900, 19883, True),       # 59,8 %
    (12000, 19883, False),      # 60,4 %: pasa
    (19883, 19883, False),
])
def test_llego_vacio_o_incompleto(filas, anterior, rojo):
    ant = {"hecho": "encontrado", "filas": anterior} if anterior else None
    s = _sem("stock_bodegas", _hoy("stock_bodegas", filas=filas), anterior=ant, modo="activa")
    assert ("incompleto" in _reglas(s)) is rojo
    if rojo:
        assert s["nivel"] == "rojo" and s["etiqueta"] == "Llegó vacío o incompleto"
    if filas == 0:
        assert s["texto"].startswith("Stock bodegas Curifor llegó con 0 filas. No se publicó")


def test_la_caida_de_filas_solo_se_controla_donde_el_catalogo_lo_dice():
    # El mix no tiene frecuencia_max ni controla_filas: cambia de tamano en forma legitima.
    s = _sem("mix_reemplazos", _hoy("mix_reemplazos", filas=0))
    assert "incompleto" not in _reglas(s)
    # Si el motor lo declara, aplica.
    cat = dict(CATALOGO["mix_reemplazos"], controla_filas=True)
    s = svc.semaforo(_hoy("mix_reemplazos", filas=0), CFG["mix_reemplazos"], None, VIERNES,
                     catalogo=cat)
    assert "incompleto" in _reglas(s)


def test_texto_de_llego_vacio_con_la_corrida_anterior():
    s = _sem("stock_bodegas", _hoy("stock_bodegas", filas=0),
             anterior={"filas": 19883}, modo="activa")
    assert s["texto"] == ("Stock bodegas Curifor llegó con 0 filas (la corrida anterior traía "
                          "19.883). No se publicó para no calcular con datos incompletos. Vuelve "
                          "a generar el archivo (si lo deja el programa del ERP, córrelo de nuevo).")


def test_no_se_pudo_leer():
    e = _hoy("catalogo", hecho="error_lectura", mensaje="falta la hoja 'Lista sin duplicados'")
    s = _sem("catalogo", e)
    assert (s["nivel"], s["etiqueta"]) == ("rojo", "No se pudo leer")
    assert "falta la hoja 'Lista sin duplicados'" in s["texto"]


@pytest.mark.parametrize("dia, nivel, extra", [
    # Como lo manda el motor: el mes cerrado que uso y su venta total, en cero.
    (3, "amarillo", {"periodo_ultimo_mes": "202609", "total_mes_cerrado": 0}),
    (4, "rojo", {"periodo_ultimo_mes": "202609", "total_mes_cerrado": 0.0}),
    (16, "rojo", {"periodo_ultimo_mes": "202609", "total_mes_cerrado": 0}),
    # Un dato que quedo en un mes anterior al cerrado de hoy.
    (16, "rojo", {"periodo_ultimo_mes": "2026-08", "total_mes_cerrado": 5000}),
])
def test_ventas_sin_el_mes_cerrado(dia, nivel, extra):
    ahora = datetime(2026, 10, dia, 10, 0, tzinfo=TZ_CHILE)
    e = estado("ventas", "2026-10-01")
    e["extra"] = extra
    s = _sem("ventas", e, ahora=ahora)
    assert (s["nivel"], s["etiqueta"]) == (nivel, "Ventas sin el mes cerrado")
    assert s["texto"].startswith("El respaldo de ventas no trae septiembre: el sugerido saldría "
                                 "con ese mes en cero. Exporta el respaldo del año y vuelve a "
                                 "correr.")


def test_ventas_con_el_mes_cerrado_esta_en_verde():
    s = _sem("ventas", estado("ventas", "2026-10-01"))
    assert (s["nivel"], s["regla"]) == ("verde", "sin_plazo")
    assert s["texto"].startswith("Encontrado: 2 archivos (2025 (4).xlsx, 2026 (6).xlsx)")


# --------------------------------------------------------------------------- #
# Fuente: amarillo
# --------------------------------------------------------------------------- #
def test_atrasado_no_frena():
    e = _hoy("ventas_frontera", dia="2026-07-13")
    s = _sem("ventas_frontera", e)
    assert (s["nivel"], s["etiqueta"]) == ("amarillo", "Atrasado, no frena")
    assert s["texto"] == ("Atrasado: vtas frontera.xlsx tiene 69 días hábiles y se espera cada "
                          "35. No frena la publicación.")


def test_falta_una_que_no_frena_dice_el_efecto():
    s = _sem("precios_ford", {"hecho": "falta", "archivos": []})
    assert (s["nivel"], s["etiqueta"]) == ("amarillo", "Falta (no frena)")
    assert s["texto"] == ("Falta Lista de precios Ford. El sugerido se publica igual, pero no se "
                          "calcula el margen con precios Ford.")


def test_mismo_contenido_que_ayer_solo_si_se_espera_a_diario():
    s = _sem("stock_bodegas", _hoy("stock_bodegas", mismo_contenido_que_anterior=True))
    assert (s["nivel"], s["etiqueta"]) == ("amarillo", "Mismo contenido que ayer")
    assert s["texto"].startswith("Revisar: la fecha del archivo cambió, pero el contenido es "
                                 "idéntico al de ayer.")
    # Un seguimiento semanal puede repetir contenido sin que sea raro.
    s = _sem("seguimiento_frontera", _hoy("seguimiento_frontera", mismo_contenido_que_anterior=True))
    assert s["nivel"] == "verde"


def test_bajando_de_onedrive():
    s = _sem("stock_bodegas", _hoy("stock_bodegas", hecho="inestable"))
    assert (s["nivel"], s["etiqueta"]) == ("amarillo", "Bajando de OneDrive")


def test_abierto_en_excel():
    s = _sem("lista_erp", _hoy("lista_erp", abierto_en_excel=True))
    assert (s["nivel"], s["etiqueta"]) == ("amarillo", "Abierto en Excel")
    assert s["texto"] == ("Este archivo está abierto en Excel en el PC del motor: el programa del "
                          "ERP no puede actualizarlo. Ciérralo.")


def test_archivo_nuevo_en_la_carpeta():
    anterior = estado("ventas", "2026-10-15")
    e = estado("ventas", "2026-10-16")
    e["descartados"].append({"nombre": "Presupuesto 2026.xlsx",
                             "motivo": "no tiene forma de respaldo de venta"})
    s = _sem("ventas", e, anterior=anterior)
    assert (s["nivel"], s["etiqueta"]) == ("amarillo", "Archivo nuevo en la carpeta")
    assert "Presupuesto 2026.xlsx" in s["texto"]
    # El Motorcraft que se descarta todos los dias no es nuevo.
    assert "Motorcraft" not in s["texto"]


def test_cambio_de_carpeta():
    anterior = estado("stock_bodegas", "2026-10-15")
    anterior["archivos"][0]["carpeta"] = "bases_de_datos"
    s = _sem("stock_bodegas", _hoy("stock_bodegas"), anterior=anterior)
    assert (s["nivel"], s["etiqueta"]) == ("amarillo", "Cambió de carpeta")
    assert s["texto"] == ("El archivo ahora viene de Data BI › Datos (SharePoint del equipo) y en "
                          "la corrida anterior venía de Bases de datos. Revisa que sea el correcto.")


# --------------------------------------------------------------------------- #
# Fuente: verde, y la peor manda
# --------------------------------------------------------------------------- #
def test_al_dia():
    s = _sem("stock_bodegas", _hoy("stock_bodegas"))
    assert (s["nivel"], s["etiqueta"]) == ("verde", "Al día")
    assert s["texto"] == "Al día: Stock bodegas.xlsx, de hoy a las 09:34, 19.883 filas."


def test_encontrado_sin_plazo():
    s = _sem("precios_gildemeister", _hoy("precios_gildemeister", dia="2026-07-28"))
    assert (s["nivel"], s["etiqueta"]) == ("verde", "Encontrado, sin plazo")


def test_la_peor_regla_manda_y_las_demas_quedan_en_alertas():
    e = _hoy("stock_bodegas", dia="2026-10-12", abierto_en_excel=True)
    s = _sem("stock_bodegas", e)
    assert s["regla"] == "vencido"
    assert _reglas(s) == ["vencido", "abierto_en_excel"]


def test_sin_datos_y_desactivada():
    assert _sem("lista_erp", None)["nivel"] == "gris"
    cfg = dict(CFG["lista_erp"], activa=False)
    s = _sem("lista_erp", _hoy("lista_erp"), cfg=cfg)
    assert (s["nivel"], s["regla"]) == ("gris", "desactivada")


def test_la_prueba_dice_si_en_activa_frenaria():
    e = _hoy("seguimiento_frontera", prueba="falta")
    out = svc._texto_prueba(e["prueba"], obligatoria=True)
    assert out["frenaria"] is True
    assert out["texto"].endswith("En modo activa, esto frenaría la publicación.")
    # Como lo manda el motor: el archivo como objeto y el motivo en texto.
    out = svc._texto_prueba({
        "resultado": "difiere",
        "archivo": {"carpeta": "databi_datos", "ruta_relativa": "Motor/Stock bodegas.xlsx"},
        "frenaria": "Stock bodegas.xlsx: 3 dias habiles (se espera al dia cada 2)",
    }, obligatoria=True)
    assert out["archivo"] == "Stock bodegas.xlsx" and out["frenaria"] is True
    assert out["texto"] == ("La configuración de la plataforma tomaría Stock bodegas.xlsx, "
                            "distinto de lo que toma hoy. Revisa la fuente antes de activar. En "
                            "modo activa, esto frenaría la publicación (Stock bodegas.xlsx: 3 "
                            "dias habiles (se espera al dia cada 2)).")


# --------------------------------------------------------------------------- #
# Franja superior
# --------------------------------------------------------------------------- #
def _corrida(id, *, pc="PC-ABAST-01", tipo="oficial", resultado="ok", hora=None,
             config_origen="plataforma", reporte=None):
    hora = hora or datetime(2026, 10, 16, 9, 30, tzinfo=TZ_CHILE)
    return MotorCorrida(id=id, pc=pc, tipo=tipo, resultado=resultado, titular=True,
                        publico=resultado == "ok", iniciada_en=hora.astimezone(timezone.utc),
                        config_origen=config_origen, reporte=json.dumps(reporte or {}))


def _franja(ahora, corridas, *, modo="prueba", titular="PC-ABAST-01", alias="PC de la jefa"):
    oficiales = sorted([c for c in corridas if c.tipo == "oficial" and c.pc == titular],
                       key=lambda c: c.iniciada_en, reverse=True)
    return svc.alertas_franja(
        ultima_oficial=oficiales[0] if oficiales else None,
        corridas_hoy=[c for c in corridas if a_chile(c.iniciada_en).date() == ahora.date()],
        titular=titular, alias_titular=alias, modo=modo, ahora=ahora,
        alias_de={titular: alias},
    )


def test_a_las_11_sin_corrida_del_titular_no_corrio_hoy():
    martes = _corrida("c-martes", hora=datetime(2026, 10, 13, 9, 30, tzinfo=TZ_CHILE))
    jueves = datetime(2026, 10, 15, 11, 0, tzinfo=TZ_CHILE)
    a = _franja(jueves, [martes])
    assert [x["regla"] for x in a] == ["titular_no_corrio"]
    assert a[0]["nivel"] == "rojo" and a[0]["etiqueta"] == "El PC titular no corrió hoy"
    assert a[0]["texto"] == ("El PC de la jefa no corre desde el martes a las 09:30. Revisa que "
                             "esté prendido y con la sesión abierta.")
    # Antes de las 11:00 no avisa todavia.
    assert _franja(jueves.replace(hour=10, minute=59), [martes]) == []
    # El fin de semana no hay tarea.
    sabado = datetime(2026, 10, 17, 12, 0, tzinfo=TZ_CHILE)
    assert _franja(sabado, [_corrida("c-vie")]) == []


def test_una_corrida_de_otro_pc_o_de_prueba_no_cuenta_como_la_del_titular():
    hoy = datetime(2026, 10, 16, 11, 30, tzinfo=TZ_CHILE)
    a = _franja(hoy, [_corrida("c-jefa", pc="PC-JEFA-01"), _corrida("c-probar", tipo="probar")])
    assert "titular_no_corrio" in [x["regla"] for x in a]


def test_en_curso_por_mas_de_75_minutos_se_corto():
    c = _corrida("c-1", resultado="en_curso")
    a = _franja(datetime(2026, 10, 16, 10, 50, tzinfo=TZ_CHILE), [c])   # 80 minutos
    assert [x["regla"] for x in a] == ["cortada"]
    assert a[0]["etiqueta"] == "La última corrida se cortó"
    assert _franja(datetime(2026, 10, 16, 10, 0, tzinfo=TZ_CHILE), [c]) == []   # 30 minutos


def test_cortada():
    a = _franja(datetime(2026, 10, 16, 10, 0, tzinfo=TZ_CHILE),
                [_corrida("c-1", resultado="cortada")])
    assert [x["regla"] for x in a] == ["cortada"]


def test_corrio_con_la_configuracion_del_pc_solo_es_rojo_en_activa():
    c = _corrida("c-1", config_origen="env")
    ahora = datetime(2026, 10, 16, 10, 0, tzinfo=TZ_CHILE)
    a = _franja(ahora, [c], modo="activa")
    assert [(x["nivel"], x["etiqueta"]) for x in a] == [("rojo", "Corrió con la configuración del PC")]
    assert _franja(ahora, [c], modo="prueba") == []


def test_uso_la_configuracion_guardada():
    c = _corrida("c-1", config_origen="cache",
                 reporte={"cache_guardada_en": "2026-10-13T09:30:00-03:00"})
    a = _franja(datetime(2026, 10, 16, 10, 0, tzinfo=TZ_CHILE), [c])
    assert [(x["nivel"], x["etiqueta"]) for x in a] == [("amarillo", "Usó la configuración guardada")]
    assert "(guardada el martes a las 09:30)" in a[0]["texto"]


def test_hoy_corrieron_dos_pcs_y_onedrive_cerrado():
    ahora = datetime(2026, 10, 16, 10, 30, tzinfo=TZ_CHILE)
    titular = _corrida("c-1", reporte={"onedrive_corriendo": False})
    otro = _corrida("c-2", pc="PC-JEFA-01", resultado="no_titular",
                    hora=datetime(2026, 10, 16, 9, 31, tzinfo=TZ_CHILE))
    a = _franja(ahora, [titular, otro], titular="PC-ABAST-01", alias="PC del dueño actual")
    reglas = {x["regla"]: x for x in a}
    assert set(reglas) == {"dos_pcs", "onedrive_cerrado"}
    assert reglas["dos_pcs"]["etiqueta"] == "Hoy corrieron dos PCs"
    assert reglas["onedrive_cerrado"]["etiqueta"] == "OneDrive cerrado"
    assert "en el PC del dueño actual durante" in reglas["onedrive_cerrado"]["texto"]


# --------------------------------------------------------------------------- #
# La foto de hoy, de punta a punta
# --------------------------------------------------------------------------- #
def test_la_foto_de_hoy_deja_las_tres_requeridas_en_verde(client, db_session):
    """Dos carpetas con stock (compiten y gana Data BI, el mas nuevo) y el Motorcraft
    que se descarta todos los dias: nada de eso cambia el color."""
    sembrado(client)
    mandar(client, "c-ayer", iniciada_en="2026-10-15T09:30:00-03:00",
           fuentes=fuentes_del_dia("2026-10-15"), carpetas=listados("2026-10-15"))
    hoy = fuentes_del_dia("2026-10-16")
    hoy["ventas"]["archivos"] = [dict(a, modificado_en="2026-10-01T08:00:00-03:00")
                                 for a in hoy["ventas"]["archivos"]]
    mandar(client, "c-hoy", iniciada_en="2026-10-16T09:30:00-03:00", fuentes=hoy,
           carpetas=listados("2026-10-16"))

    panel = svc.panel(db_session, ahora=datetime(2026, 10, 16, 10, 30, tzinfo=TZ_CHILE))
    filas = {f["clave"]: f for f in panel["fuentes"]}
    for clave in ("stock_bodegas", "stock_bodegas_frontera", "ventas"):
        assert filas[clave]["nivel"] == "verde", (clave, filas[clave]["alertas"])
    assert filas["stock_bodegas"]["texto"] == ("Al día: Stock bodegas.xlsx, de hoy a las 09:34, "
                                               "19.883 filas.")
    assert filas["stock_bodegas"]["carpeta"] == "databi_datos"
    assert panel["franja"]["nivel"] == "verde" and panel["franja"]["alertas"] == []
    assert panel["dato_de_corrida"] is None
    # El detalle si muestra la competencia y el descartado de siempre (no "nuevo").
    d = client.get(f"{URL}/ventas").json()
    assert d["descartados"] == [{"nombre": "Motorcraft 2026.xlsx",
                                 "motivo": "no tiene forma de respaldo de venta", "nuevo": False}]


def test_si_el_titular_no_corrio_cada_fila_dice_de_que_corrida_es_el_dato(client, db_session):
    sembrado(client)
    mandar(client, "c-ayer", iniciada_en="2026-10-15T09:30:00-03:00",
           fuentes=fuentes_del_dia("2026-10-15"))
    panel = svc.panel(db_session, ahora=datetime(2026, 10, 16, 11, 5, tzinfo=TZ_CHILE))
    assert panel["franja"]["nivel"] == "rojo"
    assert panel["franja"]["alertas"][0]["etiqueta"] == "El PC titular no corrió hoy"
    assert panel["dato_de_corrida"] == "Dato de la corrida del 15-10 a las 09:30"
    assert all(f["dato_de"] == panel["dato_de_corrida"] for f in panel["fuentes"])


def test_en_prueba_el_panel_dice_que_tomaria_la_plataforma(client, db_session):
    sembrado(client)
    hoy = fuentes_del_dia("2026-10-16", prueba="coincide")
    hoy["seguimiento_frontera"]["prueba"] = {"resultado": "falta"}
    mandar(client, "c-hoy", iniciada_en="2026-10-16T09:30:00-03:00", fuentes=hoy,
           config_origen="plataforma", config_version=1)
    panel = svc.panel(db_session, ahora=datetime(2026, 10, 16, 10, 30, tzinfo=TZ_CHILE))
    filas = {f["clave"]: f for f in panel["fuentes"]}
    assert filas["stock_bodegas"]["prueba"]["resultado"] == "coincide"
    assert filas["seguimiento_frontera"]["prueba"]["frenaria"] is True
    assert panel["franja"]["ultima_corrida"]["resultado_texto"] == "Publicó"


def test_el_panel_responde_en_el_esquema_aunque_la_hora_sea_otra(client):
    """Por la API (hora real): la forma no depende del dia en que corra el test."""
    sembrado(client)
    mandar(client, "c-1", fuentes=fuentes_del_dia())
    r = client.get(URL)
    assert r.status_code == 200
    datos = r.json()
    assert datos["franja"]["nivel"] in ("rojo", "amarillo", "verde", "gris")
    assert len(datos["fuentes"]) == 13
    assert datos["ahora"]
    # La edad se recalcula con la hora real, nunca negativa.
    assert all((f["edad_dias_habiles"] or 0) >= 0 for f in datos["fuentes"])
    assert datetime.fromisoformat(datos["ahora"]).utcoffset() in (timedelta(hours=-3),
                                                                   timedelta(hours=-4))
