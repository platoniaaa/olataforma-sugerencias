"""Regla pura de la venta semanal del canal: universo, signo, mes, semana, devoluciones y excepciones."""
import datetime as dt

from src.canal_digital.ventas_semanales import (
    LineaVenta, agregar, indice_originales, lunes_de, normalizar_codigo, normalizar_numero,
)


def L(fecha, producto="P1", cantidad=1.0, tipo_docto="FA-ELECTR REPTO", numero="1", tipo_venta="VTA ML",
      costo=100.0, periodo=None, doc_ref="", nro_doc_ref=""):
    f = dt.date.fromisoformat(fecha)
    return LineaVenta(periodo or f"{f.year}{f.month:02d}", tipo_docto, numero, f, tipo_venta, producto,
                      cantidad, costo, doc_ref, nro_doc_ref)


def test_normaliza_codigos_y_numeros():
    assert normalizar_codigo("  20 bxo5w30aa  ") == "20 BXO5W30AA"
    assert normalizar_codigo("15 MXD1454M ") == "15 MXD1454M"
    assert normalizar_codigo("   ") is None and normalizar_codigo(None) is None
    assert normalizar_numero(835066.0) == "835066"
    assert normalizar_numero("007720") == "7720"


def test_la_semana_va_de_lunes_a_domingo():
    assert lunes_de(dt.date(2026, 9, 30)) == dt.date(2026, 9, 28)  # miercoles
    assert lunes_de(dt.date(2026, 9, 27)) == dt.date(2026, 9, 21)  # domingo
    assert lunes_de(dt.date(2026, 9, 28)) == dt.date(2026, 9, 28)  # lunes


def test_solo_entran_los_tipos_de_venta_del_canal_en_cualquier_local():
    r = agregar([L("2026-09-01", tipo_venta="VTA ML"), L("2026-09-01", tipo_venta="VTA CNT"),
                 L("2026-09-01", tipo_venta="VTA SHOPIFY")])
    assert r.unidades_netas == 2
    assert r.estadisticas["lineas_canal"] == 2


def test_una_nota_de_credito_resta_aunque_traiga_cantidad_positiva():
    venta = L("2026-09-01", cantidad=6, numero="10", costo=50)
    nc = L("2026-09-10", cantidad=6, tipo_docto="NC-ELECTR REPTO", numero="99", costo=-50,
           doc_ref="FA-ELECTR REPTO", nro_doc_ref="10")
    r = agregar([venta, nc], originales=indice_originales([venta, nc], ["VTA ML"]))
    assert r.unidades_netas == 0
    assert sum(f.valor_costo for f in r.filas) == 0  # el signo se aplica una sola vez


def test_la_devolucion_cuenta_en_la_semana_de_la_venta_y_en_el_mes_de_su_nota():
    venta = L("2026-08-26", cantidad=4, numero="10")       # semana del 24-ago, periodo 202608
    nc = L("2026-09-03", cantidad=4, tipo_docto="NC-ELECTR REPTO", numero="99",
           doc_ref="FA-ELECTR REPTO", nro_doc_ref="10")
    r = agregar([venta, nc], originales=indice_originales([venta, nc], ["VTA ML"]))
    por = {(f.semana, f.periodo): f for f in r.filas}
    assert por[("2026-08-24", "202608")].unid_brutas == 4          # la venta
    assert por[("2026-08-24", "202609")].unid_devueltas == 4       # semana de la venta, mes de la nota
    assert len(por) == 2


def test_devolucion_sin_original_o_con_original_posterior_cuenta_en_la_semana_de_su_nota():
    nc1 = L("2026-09-03", cantidad=1, tipo_docto="NC-ELECTR REPTO", numero="98",
            doc_ref="FA-ELECTR REPTO", nro_doc_ref="77")
    futura = L("2026-09-20", numero="55")
    nc2 = L("2026-09-03", cantidad=1, tipo_docto="NC-ELECTR REPTO", numero="97",
            doc_ref="FA-ELECTR REPTO", nro_doc_ref="55")
    r = agregar([nc1, nc2, futura], originales=indice_originales([futura], ["VTA ML"]))
    assert r.estadisticas["devoluciones_sin_original"] == 1
    assert r.estadisticas["devoluciones_con_original_posterior"] == 1
    assert {f.semana for f in r.filas if f.unid_devueltas} == {"2026-08-31"}


def test_liquidaciones_cuentan_como_venta_pero_quedan_marcadas():
    r = agregar([L("2026-09-01", cantidad=5, tipo_docto="LIQ FACT-REPUESTOS")])
    assert r.unidades_netas == 5 and r.filas[0].unid_liquidacion == 5


def test_tipos_de_documento_que_no_son_venta_y_productos_sin_ficha_se_omiten_y_se_cuentan():
    r = agregar([L("2026-09-01", tipo_docto="SALIDA ACCESORIOS"), L("2026-09-01", producto="CUP000492"),
                 L("2026-09-01")])
    assert r.unidades_netas == 1
    assert r.estadisticas["omitidas_tipo_documento"] == 1
    assert r.estadisticas["omitidas_producto_sin_ficha"] == 1


def test_una_venta_con_cantidad_negativa_resta_sola():
    r = agregar([L("2026-09-01", cantidad=3), L("2026-09-02", cantidad=-1, costo=10)])
    assert r.unidades_netas == 2
    assert sum(f.unid_devueltas for f in r.filas) == 1


def test_limitar_a_periodos_y_suma_por_clave():
    r = agregar([L("2026-09-01", cantidad=2), L("2026-09-02", cantidad=3), L("2026-08-01")],
                periodos=["202609"])
    assert len(r.filas) == 1 and r.filas[0].unid_brutas == 5 and r.filas[0].n_lineas == 2
