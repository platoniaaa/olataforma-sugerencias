"""El paso a paso de un producto de Canal Digital: tres productos de clusters distintos.

Lo que estos tests cuidan:

1. Que cada paso traiga formula, numeros reales y resultado, y que los numeros del
   texto sean los de un calculo independiente (no solo los que devolvio el codigo).
2. Que se recorran las tres ramas de la politica (formula, contra pedido, minimo fijo)
   y los productos sin cluster (NUEVO, SIN MOVIMIENTO).
3. Que el texto avise lo que esta provisorio: comprometido sin dato, minimo y multiplo
   por defecto.
4. Que no modifique sus entradas.
"""
import copy
import dataclasses
import statistics
from datetime import date
from fractions import Fraction

import pytest

from src.canal_digital import paso_a_paso as pp
from src.canal_digital.clasificacion import (
    ESTADO_CLASIFICADO,
    ESTADO_NUEVO,
    ESTADO_SIN_MOVIMIENTO,
    VentaProducto,
    clasificar,
)
from src.canal_digital.politica import politica_provisoria
from src.canal_digital.reposicion import EntradaReposicion, calcular_reposicion

REF = date(2026, 10, 1)
ANTIGUA = date(2024, 3, 1)
POLITICA = politica_provisoria()
MESES = ["oct-25", "nov-25", "dic-25", "ene-26", "feb-26", "mar-26",
         "abr-26", "may-26", "jun-26", "jul-26", "ago-26", "sep-26"]


def _venta(codigo, unidades, valor, primera=ANTIGUA):
    u = list(unidades) + [0] * (12 - len(unidades))
    v = list(valor) + [0] * (12 - len(valor))
    return VentaProducto(codigo, u, v, primera)


# Cuatro productos con clusters distintos (se calcularon a mano):
#   X  1.200 u. y $12.000, 12 meses       -> AAC (formula, 98%)
#   Y    120 u. y $1.200.000, 12 meses    -> ABA (formula, 95%)
#   W      6 u. y $600.000, 2 meses       -> CCA (contra pedido)
#   Z      5 u. y $5.000, 1 mes           -> CCC (minimo fijo de 1)
# Mas un NUEVO (N) y un SIN MOVIMIENTO (S) que no entran al Pareto.
VENTAS = [
    _venta("X", [100] * 12, [1000] * 12),
    _venta("Y", [10] * 12, [100_000] * 12),
    _venta("W", [3, 3], [300_000, 300_000]),
    _venta("Z", [5], [5000]),
    _venta("N", [2], [2000], primera=date(2026, 8, 1)),
    _venta("S", [0], [0]),
]
SERIE_X = [20, 26] * 26  # D = 23, sigma muestral = sqrt(52 * 9 / 51)
SERIE_W = [0, 0, 3, 0, 3] + [0] * 47
SERIE_Z = [0] * 51 + [5]


@pytest.fixture(scope="module")
def clasif():
    return clasificar(VENTAS, REF)


def _repo(clasif, codigo, serie, **kw):
    c = clasif.producto(codigo)
    entrada = EntradaReposicion(
        codigo=codigo, unidades_semana=serie, lead_time_semanas=kw.pop("lead", 2),
        origen_lead_time=kw.pop("origen", "últimas 5 recepciones del proveedor"),
        stock_disponible=kw.pop("disponible", 0), en_transito=kw.pop("transito", 0), **kw,
    )
    fila = POLITICA.fila(c.cluster) if c.cluster else None
    return calcular_reposicion(entrada, fila, estado=c.estado), fila


def _coma(x, dec=2):
    """Como lo escribe el paso a paso: coma decimal y sin ceros que sobran (2,5 y no 2,50)."""
    return f"{x:.{dec}f}".rstrip("0").rstrip(".").replace(".", ",")


def test_los_cuatro_productos_caen_en_los_clusters_esperados(clasif):
    assert [clasif.producto(c).cluster for c in "XYWZ"] == ["AAC", "ABA", "CCA", "CCC"]
    assert clasif.producto("N").estado == ESTADO_NUEVO
    assert clasif.producto("S").estado == ESTADO_SIN_MOVIMIENTO
    assert clasif.n_base == 4


# --------------------------------------------------------------------------- X: rama de formula


def test_producto_con_formula_recorre_todos_los_pasos_con_sus_numeros(clasif):
    repo, fila = _repo(clasif, "X", SERIE_X, disponible=40, transito=10)
    pasos = pp.explicar_producto(clasif, "X", repo, fila, etiquetas_meses=MESES)
    titulos = [p.titulo for p in pasos]
    assert titulos == [
        "Frecuencia de venta", "Producto nuevo", "Pareto de piezas", "Pareto de valor",
        "Cluster y política", "Demanda semanal (D)", "Variabilidad semanal (sigma)", "Plazos (L y R)",
        "Stock de seguridad (SS)", "Nivel objetivo (S)", "Posición de inventario", "Necesidad",
        "Redondeo a mínimo y múltiplo", "Sugerido",
    ]
    assert [p.numero for p in pasos] == list(range(1, 15))
    for p in pasos:
        assert p.formula and p.numeros and p.resultado, p.titulo

    por = {p.titulo: p for p in pasos}
    # Calculo independiente de lo que debe aparecer.
    sigma = statistics.stdev(SERIE_X)
    ss = 2.05 * sigma * 3 ** 0.5
    s = 23 * 3 + ss
    bruto = s - 50
    assert "oct-25: 100" in por["Frecuencia de venta"].numeros and "sep-26: 100" in por["Frecuencia de venta"].numeros
    assert "12 de 12" in por["Frecuencia de venta"].numeros
    assert por["Frecuencia de venta"].resultado == "Frecuencia A."
    assert "Lugar 1 de 4" in por["Pareto de piezas"].numeros
    assert "1.200" in por["Pareto de piezas"].numeros and "1.331" in por["Pareto de piezas"].numeros
    assert "Aporta 90,2%" in por["Pareto de piezas"].numeros  # 1200 / 1331
    assert por["Pareto de piezas"].resultado.startswith("Letra A, porque 0,0% es menor que 80%")
    assert "Lugar 3 de 4" in por["Pareto de valor"].numeros  # Y y W venden mas valor
    assert "$ 12.000" in por["Pareto de valor"].numeros and "$ 1.817.000" in por["Pareto de valor"].numeros
    assert "Letra C" in por["Pareto de valor"].resultado
    assert "no es menor que 95%" in por["Pareto de valor"].resultado  # 98,6% antes
    assert por["Cluster y política"].numeros == "A + A + C."
    assert "Cluster AAC" in por["Cluster y política"].resultado
    assert "nivel de servicio 98%" in por["Cluster y política"].resultado
    assert "z = 2,05" in por["Cluster y política"].resultado
    assert por["Demanda semanal (D)"].resultado == "D = 23 unidades por semana."
    assert "1.196 unidades / 52 semanas" in por["Demanda semanal (D)"].numeros
    assert f"sigma = {_coma(sigma)} unidades por semana" in por["Variabilidad semanal (sigma)"].resultado
    assert "muestral" in por["Variabilidad semanal (sigma)"].formula
    assert "últimas 5 recepciones del proveedor" in por["Plazos (L y R)"].numeros
    assert por["Plazos (L y R)"].resultado == "L + R = 3 semanas."
    assert f"SS = {_coma(ss)} unidades." == por["Stock de seguridad (SS)"].resultado
    assert por["Stock de seguridad (SS)"].numeros.startswith("2,05 × ")
    assert f"S = {_coma(s)} unidades." == por["Nivel objetivo (S)"].resultado
    assert "40 + 10 - 0 (sin dato: se asume 0)" in por["Posición de inventario"].numeros
    assert por["Posición de inventario"].resultado == "Posición = 50 unidades."
    assert por["Necesidad"].resultado == f"Necesidad = {_coma(bruto)} unidades."
    assert "por defecto, sin dato cargado" in por["Redondeo a mínimo y múltiplo"].numeros
    assert por["Redondeo a mínimo y múltiplo"].resultado == "30 unidades."
    assert por["Sugerido"].resultado == "Sugerido: 30 unidades."
    assert repo.sugerido == 30 and bruto == pytest.approx(29.756, abs=1e-3)


def test_el_paso_a_paso_con_dato_de_comprometido_y_minimo_no_dice_sin_dato(clasif):
    repo, fila = _repo(clasif, "X", SERIE_X, disponible=40, transito=10, comprometido=5, minimo_compra=10, multiplo=12)
    texto = pp.texto_completo(pp.explicar_producto(clasif, "X", repo, fila))
    assert "40 + 10 - 5." in texto
    assert "sin dato" not in texto
    assert "mínimo de compra 10; múltiplo 12." in texto
    assert "Sugerido: 36 unidades." in texto  # S = 79,76; posicion 45; faltan 34,76 -> 36 (multiplo de 12)


def test_sin_nombres_de_mes_usa_mes_1_a_mes_12(clasif):
    repo, fila = _repo(clasif, "X", SERIE_X)
    pasos = pp.explicar_producto(clasif, "X", repo, fila)
    assert "mes 1: 100" in pasos[0].numeros and "mes 12: 100" in pasos[0].numeros


def test_historia_corta_y_muestra_insuficiente_se_avisan(clasif):
    repo, fila = _repo(clasif, "X", [20, 26] * 5)
    texto = pp.texto_completo(pp.explicar_producto(clasif, "X", repo, fila))
    assert "solo hay 10 semanas de historia" in texto
    repo1, fila1 = _repo(clasif, "X", [9])
    assert "No se puede estimar con tan pocas semanas" in pp.texto_completo(
        pp.explicar_producto(clasif, "X", repo1, fila1)
    )


# --------------------------------------------------------------------------- W: contra pedido


def test_contra_pedido_explica_que_no_se_repone_y_no_calcula_ss_ni_s(clasif):
    repo, fila = _repo(clasif, "W", SERIE_W, disponible=2)
    pasos = pp.explicar_producto(clasif, "W", repo, fila, etiquetas_meses=MESES)
    por = {p.titulo: p for p in pasos}
    assert "Stock de seguridad (SS)" not in por and "Nivel objetivo (S)" not in por
    assert "Cluster CCA" in por["Cluster y política"].resultado
    assert "contra pedido" in por["Cluster y política"].resultado
    assert por["Cluster y política"].numeros == "C + C + A."
    assert "Letra A, porque" in por["Pareto de valor"].resultado  # parte en 66,0%: menor que 80%
    assert "Lugar 2 de 4" in por["Pareto de valor"].numeros
    assert "2 de 12" in por["Frecuencia de venta"].numeros
    assert por["Demanda semanal (D)"].resultado == f"D = {_coma(6 / 52)} unidades por semana."
    assert por["Necesidad"].resultado == "Necesidad = 0 unidades."
    assert "Contra pedido" in por["Necesidad"].formula
    assert pasos[-1].resultado == "Sugerido: 0 unidades."
    assert "CONTRA_PEDIDO" in pasos[-1].numeros


# --------------------------------------------------------------------------- Z: minimo fijo


def test_minimo_fijo_pide_el_minimo_cuando_la_posicion_es_cero(clasif):
    repo, fila = _repo(clasif, "Z", SERIE_Z, disponible=0)
    pasos = pp.explicar_producto(clasif, "Z", repo, fila)
    por = {p.titulo: p for p in pasos}
    assert "Cluster CCC" in por["Cluster y política"].resultado
    assert "mínimo fijo de 1" in por["Cluster y política"].resultado
    assert "Stock de seguridad (SS)" not in por
    assert por["Posición de inventario"].resultado == "Posición = 0 unidades."
    assert "Posición = 0; mínimo fijo = 1." == por["Necesidad"].numeros
    assert por["Necesidad"].resultado == "Necesidad = 1 unidad."  # singular
    assert pasos[-1].resultado == "Sugerido: 1 unidad."
    assert "MINIMO_FIJO_PIDE" in pasos[-1].numeros


def test_minimo_fijo_con_stock_no_pide(clasif):
    repo, fila = _repo(clasif, "Z", SERIE_Z, disponible=3)
    pasos = pp.explicar_producto(clasif, "Z", repo, fila)
    assert pasos[-1].resultado == "Sugerido: 0 unidades."
    assert "MINIMO_FIJO_CUBIERTO" in pasos[-1].numeros


# --------------------------------------------------------------------------- sin cluster


def test_producto_nuevo_termina_en_el_paso_dos_con_sugerido_cero(clasif):
    repo, fila = _repo(clasif, "N", [1] * 20)
    assert fila is None
    pasos = pp.explicar_producto(clasif, "N", repo, fila)
    assert [p.titulo for p in pasos] == ["Frecuencia de venta", "Producto nuevo", "Sugerido"]
    assert "posterior al 2026-04-01" in pasos[1].formula
    assert "Primera venta en la empresa: 2026-08-01." == pasos[1].numeros
    assert pasos[1].resultado.startswith("NUEVO")
    assert pasos[2].resultado == "Sugerido: 0 unidades."


def test_producto_sin_movimiento_termina_en_el_paso_dos(clasif):
    repo, fila = _repo(clasif, "S", [0] * 52)
    pasos = pp.explicar_producto(clasif, "S", repo, fila)
    assert [p.titulo for p in pasos] == ["Frecuencia de venta", "Producto nuevo", "Sugerido"]
    assert pasos[0].resultado.startswith("SIN MOVIMIENTO")
    assert "0 de 12" in pasos[0].numeros
    assert pasos[1].resultado == "No aplica."
    assert "SIN MOVIMIENTO" in pasos[2].numeros


# --------------------------------------------------------------------------- errores y formato


def test_el_resultado_de_otro_producto_es_un_error(clasif):
    repo, fila = _repo(clasif, "X", SERIE_X)
    with pytest.raises(ValueError, match="'X'"):
        pp.explicar_producto(clasif, "Y", repo, fila)


def test_un_clasificado_sin_fila_de_politica_es_un_error(clasif):
    repo, _ = _repo(clasif, "X", SERIE_X)
    with pytest.raises(ValueError, match="política"):
        pp.explicar_producto(clasif, "X", repo, None)


def test_las_etiquetas_de_mes_deben_ser_12(clasif):
    repo, fila = _repo(clasif, "X", SERIE_X)
    with pytest.raises(ValueError, match="12 etiquetas"):
        pp.explicar_producto(clasif, "X", repo, fila, etiquetas_meses=MESES[:-1])
    ajeno = dataclasses.replace(repo, codigo="NO EXISTE")  # el codigo no esta en la clasificacion
    with pytest.raises(KeyError):
        pp.explicar_producto(clasif, "NO EXISTE", ajeno, fila)


def test_texto_completo_numera_y_separa_los_pasos(clasif):
    repo, fila = _repo(clasif, "X", SERIE_X)
    pasos = pp.explicar_producto(clasif, "X", repo, fila)
    texto = pp.texto_completo(pasos)
    for n in range(1, len(pasos) + 1):
        assert f"Paso {n}. " in texto
    assert texto.count("Fórmula:") == texto.count("Con los números:") == texto.count("Resultado:") == len(pasos)
    assert "\n\n" in texto
    assert pasos[0].texto().startswith("Paso 1. Frecuencia de venta\n  Fórmula: ")


def test_formato_chileno_de_numeros():
    assert pp.num(1234.5) == "1.234,5"
    assert pp.num(1234567) == "1.234.567"
    assert pp.num(12.3456) == "12,35"
    assert pp.num(12.3456, 3) == "12,346"
    assert pp.num(0) == "0" and pp.num(30.0) == "30"
    assert pp.num(-2.5) == "-2,5"
    assert pp.num(Fraction(5, 2)) == "2,5"
    assert pp.num(-0.001) == "0" and pp.num(29.9999) == "30"
    assert pp.pct(Fraction(78, 100)) == "78,0%"
    assert pp.pct(Fraction(1, 3), 2) == "33,33%"
    assert pp.pct(Fraction(95, 100), 0) == "95%"
    assert pp.pesos(1234567.4) == "$ 1.234.567"
    assert pp._u(1) == "1 unidad" and pp._u(0) == "0 unidades" and pp._u(2.5) == "2,5 unidades"


def test_no_modifica_sus_entradas(clasif):
    repo, fila = _repo(clasif, "X", SERIE_X)
    clasif_antes = copy.deepcopy(clasif)
    repo_antes = copy.deepcopy(repo)
    fila_antes = copy.deepcopy(fila)
    etiquetas = list(MESES)
    pp.explicar_producto(clasif, "X", repo, fila, etiquetas_meses=etiquetas)
    assert clasif == clasif_antes and repo == repo_antes and fila == fila_antes
    assert etiquetas == MESES
    assert clasif.producto("X").estado == ESTADO_CLASIFICADO
