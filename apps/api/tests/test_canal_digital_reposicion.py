"""Reposicion semanal de Canal Digital: D, sigma, SS, S, posicion y sugerido.

Lo que estos tests cuidan:

1. Que la formula sea la del plan: SS = z x sigma x raiz(L + R); S = D x (L + R) + SS;
   sugerido = max(0, S - posicion) redondeado al multiplo y al minimo de compra.
2. Que sigma sea la desviacion MUESTRAL (n - 1) por defecto, exacta en series constantes
   (0, no 1e-16) y sin pedir una unidad de mas por ruido de punto flotante.
3. Que los tres modos de politica (formula, contra pedido, minimo fijo) hagan lo que dicen
   en los 27 clusters, y que NUEVO y SIN MOVIMIENTO den 0 con su marca.
4. Que minimo, multiplo y comprometido sin dato se rotulen como valor por defecto.
5. Que ninguna funcion modifique sus entradas y que se devuelvan todos los intermedios.
Los valores esperados se calculan en cada test con `statistics` y `math`, no con el codigo
probado.
"""
import copy
import dataclasses
import math
import random
import statistics
from fractions import Fraction

import pytest

from src.canal_digital import reposicion as rp
from src.canal_digital.clasificacion import ESTADO_NUEVO, ESTADO_SIN_MOVIMIENTO
from src.canal_digital.politica import CLUSTERS, politica_provisoria
from src.canal_digital.reposicion import (
    EntradaReposicion,
    ParametrosReposicion,
    calcular_reposicion,
    media_y_sigma,
    redondear_compra,
    techo_a_multiplo,
)

POLITICA = politica_provisoria()
FILA_FORMULA = POLITICA.fila("AAA")  # 95%, z = 1,65
FILA_CONTRA_PEDIDO = POLITICA.fila("CAA")
FILA_MINIMO_FIJO = POLITICA.fila("CCC")  # minimo fijo de 1


def entrada(serie=None, lead=2, disponible=0, transito=0, comprometido=None, minimo=None, multiplo=None,
            codigo="P1"):
    return EntradaReposicion(
        codigo=codigo,
        unidades_semana=[10] * 52 if serie is None else serie,
        lead_time_semanas=lead,
        origen_lead_time="prueba",
        stock_disponible=disponible,
        en_transito=transito,
        comprometido=comprometido,
        minimo_compra=minimo,
        multiplo=multiplo,
    )


# --------------------------------------------------------------------------- la formula


def test_serie_constante_no_tiene_variabilidad_y_pide_exactamente_la_demanda_del_horizonte():
    r = calcular_reposicion(entrada([10] * 52, lead=2), FILA_FORMULA)
    assert r.demanda_semanal == 10
    assert r.sigma_semanal == 0.0  # exacto: no 1e-16
    assert r.horizonte_semanas == 3  # L = 2 + R = 1
    assert r.stock_seguridad == 0.0
    assert r.nivel_objetivo == 30
    assert r.posicion == 0
    assert r.sugerido_bruto == 30
    assert r.sugerido == 30
    assert r.motivo == rp.MOTIVO_FORMULA_PIDE
    assert r.modo == "formula" and r.cluster == "AAA"


def test_la_posicion_descuenta_el_stock_y_el_transito():
    r = calcular_reposicion(entrada([10] * 52, lead=2, disponible=12, transito=8), FILA_FORMULA)
    assert r.posicion == 20
    assert r.sugerido == 10  # 30 - 20


def test_formula_completa_con_variabilidad_contra_calculo_independiente():
    serie = [0, 10] * 26  # media 5, desviacion muestral sqrt(1300/51)
    lead, z = 2.5, 1.65
    r = calcular_reposicion(
        entrada(serie, lead=lead, disponible=20, transito=5, comprometido=3), FILA_FORMULA
    )
    d = statistics.mean(serie)
    sigma = statistics.stdev(serie)
    ss = z * sigma * math.sqrt(lead + 1)
    s = d * (lead + 1) + ss
    posicion = 20 + 5 - 3
    assert r.demanda_semanal == pytest.approx(d, rel=1e-12)
    assert r.sigma_semanal == pytest.approx(sigma, rel=1e-12)
    assert r.sigma_semanal == pytest.approx(math.sqrt(1300 / 51), rel=1e-12)
    assert r.z == 1.65 and r.nivel_servicio == 0.95
    assert r.stock_seguridad == pytest.approx(ss, rel=1e-12)
    assert r.nivel_objetivo == pytest.approx(s, rel=1e-12)
    assert r.posicion == posicion
    assert r.sugerido_bruto == pytest.approx(s - posicion, rel=1e-12)
    assert r.sugerido == math.ceil(s - posicion - 1e-9) == 12
    assert r.horizonte_semanas == 3.5


def test_sigma_es_muestral_por_defecto_y_poblacional_si_se_pide():
    serie = [0, 10] * 26
    muestral = calcular_reposicion(entrada(serie), FILA_FORMULA)
    poblacional = calcular_reposicion(entrada(serie), FILA_FORMULA, parametros=ParametrosReposicion(ddof=0))
    assert muestral.ddof == 1 and poblacional.ddof == 0
    assert muestral.sigma_semanal == pytest.approx(statistics.stdev(serie), rel=1e-12)
    assert poblacional.sigma_semanal == pytest.approx(statistics.pstdev(serie), rel=1e-12)
    assert poblacional.sigma_semanal < muestral.sigma_semanal
    assert poblacional.stock_seguridad < muestral.stock_seguridad


def test_con_una_muestra_constante_sigma_es_cero_exacto_aunque_sean_decimales():
    for constante in (3, 0, 0.1, 7.35, Fraction(1, 3)):
        r = calcular_reposicion(entrada([constante] * 52), FILA_FORMULA)
        assert r.sigma_semanal == 0.0, constante
        assert r.stock_seguridad == 0.0, constante
    assert calcular_reposicion(entrada([0.1] * 52), FILA_FORMULA).demanda_semanal == 0.1


def test_lead_time_fraccional_cinco_dias_son_cinco_septimos_de_semana():
    serie = [4, 6] * 26
    r = calcular_reposicion(entrada(serie, lead=Fraction(5, 7)), FILA_FORMULA)
    horizonte = 5 / 7 + 1
    assert r.lead_time_semanas == pytest.approx(5 / 7, rel=1e-15)
    assert r.horizonte_semanas == pytest.approx(horizonte, rel=1e-15)
    esperado_s = 5 * horizonte + 1.65 * statistics.stdev(serie) * math.sqrt(horizonte)
    assert r.nivel_objetivo == pytest.approx(esperado_s, rel=1e-12)
    # Otra forma de decir lo mismo: 5 dias / 7.
    assert calcular_reposicion(entrada(serie, lead=5 / 7), FILA_FORMULA).nivel_objetivo == pytest.approx(
        esperado_s, rel=1e-12
    )


def test_lead_time_cero_solo_cubre_la_revision():
    r = calcular_reposicion(entrada([10] * 52, lead=0), FILA_FORMULA)
    assert r.horizonte_semanas == 1 and r.nivel_objetivo == 10 and r.sugerido == 10


def test_el_periodo_de_revision_es_un_parametro():
    r = calcular_reposicion(entrada([10] * 52, lead=2), FILA_FORMULA, parametros=ParametrosReposicion(r_semanas=2))
    assert r.r_semanas == 2 and r.horizonte_semanas == 4 and r.sugerido == 40


def test_demanda_intermitente_pocas_semanas_con_venta():
    # 3 semanas con 20 unidades y 49 en cero: D chica, sigma mas grande que D.
    serie = [0] * 52
    for semana in (5, 23, 41):
        serie[semana] = 20
    r = calcular_reposicion(entrada(serie, lead=3, disponible=1), FILA_FORMULA)
    d = 60 / 52
    sigma = statistics.stdev(serie)
    assert r.demanda_semanal == pytest.approx(d, rel=1e-12)
    assert sigma > d and r.sigma_semanal == pytest.approx(sigma, rel=1e-12)
    s = d * 4 + 1.65 * sigma * math.sqrt(4)
    assert r.nivel_objetivo == pytest.approx(s, rel=1e-12)
    # El stock de seguridad domina: la mayor parte de S es colchon, no demanda media.
    assert r.stock_seguridad > d * 4
    assert r.sugerido == math.ceil(s - 1)


def test_serie_de_ceros_no_pide_nada():
    r = calcular_reposicion(entrada([0] * 52), FILA_FORMULA)
    assert (r.demanda_semanal, r.sigma_semanal, r.nivel_objetivo, r.sugerido) == (0, 0.0, 0, 0)
    assert r.motivo == rp.MOTIVO_FORMULA_CUBIERTO


def test_cubierto_por_el_stock_no_pide():
    r = calcular_reposicion(entrada([10] * 52, lead=2, disponible=25, transito=5), FILA_FORMULA)
    assert r.posicion == 30 == r.nivel_objetivo
    assert r.sugerido_bruto == 0 and r.sugerido == 0
    assert r.motivo == rp.MOTIVO_FORMULA_CUBIERTO
    sobra = calcular_reposicion(entrada([10] * 52, lead=2, disponible=100), FILA_FORMULA)
    assert sobra.sugerido_bruto == 0 and sobra.sugerido == 0  # nunca negativo


def test_stock_negativo_del_erp_aumenta_la_necesidad():
    r = calcular_reposicion(entrada([10] * 52, lead=2, disponible=-4), FILA_FORMULA)
    assert r.posicion == -4 and r.sugerido == 34


def test_sin_ruido_de_punto_flotante_no_se_pide_una_unidad_de_mas():
    # S = 0,1 x 3 = 0,30000000000000004 en float; con posicion 0,3 sobra 5e-17, no 1 unidad.
    r = calcular_reposicion(entrada([0.1] * 52, lead=2, disponible=0.3), FILA_FORMULA)
    assert r.sugerido_bruto < 1e-9
    assert r.sugerido == 0


# --------------------------------------------------------------------------- redondeo a minimo y multiplo


@pytest.mark.parametrize(
    "necesidad, minimo, multiplo, esperado",
    [
        (7, 10, 6, 12),  # el minimo (10) no es multiplo de 6: sube a 12, cumple las dos reglas
        (7.2, 1, 6, 12),  # hacia arriba al multiplo
        (6, 1, 6, 6),  # justo un multiplo
        (0.2, 1, 1, 1),  # una fraccion de unidad sube al minimo
        (12.0000000001, 1, 1, 12),  # ruido de punto flotante: no sube un escalon
        (12, 1, 1, 12),
        (12.5, 1, 1, 13),
        (0, 5, 6, 0),  # sin necesidad no se pide ni el minimo
        (1e-12, 5, 6, 0),
        (-3, 5, 6, 0),
        (13, 12, 12, 24),
        (3, 20, 12, 24),  # minimo 20 y multiplo 12: 24
        (5, 1, 0.5, 5),
        (5.2, 1, 0.5, 5.5),
        (1, 0, 1, 1),  # minimo 0 es valido: manda la necesidad
    ],
)
def test_redondeo_hacia_arriba_al_multiplo_y_como_minimo_el_minimo_de_compra(necesidad, minimo, multiplo, esperado):
    assert redondear_compra(necesidad, minimo, multiplo) == pytest.approx(esperado, rel=1e-12)


def test_techo_a_multiplo_rechaza_un_multiplo_que_no_es_positivo():
    for malo in (0, -1):
        with pytest.raises(ValueError):
            techo_a_multiplo(5, malo)


def test_el_sugerido_final_respeta_minimo_y_multiplo():
    # D = 10, L = 2 -> S = 30; con 23 en mano faltan 7. Minimo 10, multiplo 6 -> 12.
    r = calcular_reposicion(entrada([10] * 52, lead=2, disponible=23, minimo=10, multiplo=6), FILA_FORMULA)
    assert r.sugerido_bruto == 7
    assert (r.minimo_compra, r.multiplo) == (10, 6)
    assert r.sugerido == 12
    # Sin necesidad no pide el minimo.
    sin = calcular_reposicion(entrada([10] * 52, lead=2, disponible=30, minimo=10, multiplo=6), FILA_FORMULA)
    assert sin.sugerido == 0


def test_resultados_enteros_salen_como_enteros():
    r = calcular_reposicion(entrada([10] * 52, lead=2), FILA_FORMULA)
    assert isinstance(r.sugerido, int) and isinstance(r.multiplo, int) and isinstance(r.minimo_compra, int)


# --------------------------------------------------------------------------- valores por defecto y comprometido


def test_minimo_y_multiplo_sin_dato_son_1_y_1_con_bandera():
    r = calcular_reposicion(entrada(), FILA_FORMULA)
    assert (r.minimo_compra, r.multiplo) == (1, 1)
    assert r.valor_por_defecto is True
    assert rp.BANDERA_MINIMO_POR_DEFECTO in r.banderas and rp.BANDERA_MULTIPLO_POR_DEFECTO in r.banderas


def test_la_bandera_de_valor_por_defecto_distingue_cual_falta():
    solo_minimo = calcular_reposicion(entrada(minimo=4), FILA_FORMULA)
    assert solo_minimo.valor_por_defecto is True
    assert rp.BANDERA_MINIMO_POR_DEFECTO not in solo_minimo.banderas
    assert rp.BANDERA_MULTIPLO_POR_DEFECTO in solo_minimo.banderas
    ambos = calcular_reposicion(entrada(minimo=4, multiplo=2), FILA_FORMULA)
    assert ambos.valor_por_defecto is False
    assert rp.BANDERA_MINIMO_POR_DEFECTO not in ambos.banderas
    assert rp.BANDERA_MULTIPLO_POR_DEFECTO not in ambos.banderas


def test_comprometido_sin_dato_es_cero_y_esta_rotulado():
    r = calcular_reposicion(entrada(disponible=10, transito=5), FILA_FORMULA)
    assert r.comprometido == 0
    assert "sin dato" in r.comprometido_rotulo
    assert rp.BANDERA_COMPROMETIDO_SIN_DATO in r.banderas
    assert r.posicion == 15


def test_comprometido_con_dato_resta_de_la_posicion():
    r = calcular_reposicion(entrada(disponible=10, transito=5, comprometido=4), FILA_FORMULA)
    assert r.comprometido == 4 and r.posicion == 11
    assert rp.BANDERA_COMPROMETIDO_SIN_DATO not in r.banderas
    assert "sin dato" not in r.comprometido_rotulo
    # Un comprometido de 0 informado por el ERP NO es "sin dato".
    cero = calcular_reposicion(entrada(comprometido=0), FILA_FORMULA)
    assert rp.BANDERA_COMPROMETIDO_SIN_DATO not in cero.banderas


# --------------------------------------------------------------------------- los tres modos


def test_contra_pedido_no_sugiere_nada_pero_muestra_d_y_sigma():
    r = calcular_reposicion(entrada([0, 8] * 26, lead=3), FILA_CONTRA_PEDIDO)
    assert r.modo == "contra_pedido" and r.motivo == rp.MOTIVO_CONTRA_PEDIDO
    assert r.sugerido == 0 and r.sugerido_bruto == 0
    assert r.demanda_semanal == 4 and r.sigma_semanal > 0
    assert r.z is None and r.nivel_servicio is None
    assert r.stock_seguridad is None and r.nivel_objetivo is None  # no aplican


@pytest.mark.parametrize(
    "disponible, transito, comprometido, esperado, motivo",
    [
        (0, 0, None, 1, rp.MOTIVO_MINIMO_FIJO_PIDE),  # posicion 0
        (0, 0, 3, 1, rp.MOTIVO_MINIMO_FIJO_PIDE),  # posicion negativa (reservado sin stock)
        (2, 0, 5, 1, rp.MOTIVO_MINIMO_FIJO_PIDE),
        (1, 0, None, 0, rp.MOTIVO_MINIMO_FIJO_CUBIERTO),  # posicion 1: no pide
        (0, 1, None, 0, rp.MOTIVO_MINIMO_FIJO_CUBIERTO),  # lo que viene en camino cuenta
        (5, 5, None, 0, rp.MOTIVO_MINIMO_FIJO_CUBIERTO),
    ],
)
def test_minimo_fijo_solo_pide_cuando_la_posicion_es_cero_o_menos(disponible, transito, comprometido, esperado, motivo):
    r = calcular_reposicion(
        entrada([0, 0, 2] * 17 + [0], disponible=disponible, transito=transito, comprometido=comprometido),
        FILA_MINIMO_FIJO,
    )
    assert r.modo == "minimo_fijo" and r.minimo_fijo == 1
    assert r.sugerido == esperado
    assert r.motivo == motivo
    assert r.stock_seguridad is None and r.nivel_objetivo is None


def test_minimo_fijo_tambien_pasa_por_el_minimo_de_compra_y_el_multiplo():
    # Pide 1, pero el proveedor vende de a 6: el minimo posible es 6.
    r = calcular_reposicion(entrada([0, 0, 2] * 17 + [0], multiplo=6), FILA_MINIMO_FIJO)
    assert r.sugerido == 6
    # Y con minimo de compra 4 y multiplo 1, el menor pedido posible es 4.
    r2 = calcular_reposicion(entrada([0, 0, 2] * 17 + [0], minimo=4), FILA_MINIMO_FIJO)
    assert r2.sugerido == 4


def test_minimo_fijo_mayor_que_uno_se_respeta():
    fila = dataclasses.replace(FILA_MINIMO_FIJO, minimo_fijo=3)
    assert calcular_reposicion(entrada(disponible=0), fila).sugerido == 3
    assert calcular_reposicion(entrada(disponible=1), fila).sugerido == 0


def test_cada_uno_de_los_27_clusters_aplica_su_modo():
    for cluster in CLUSTERS:
        fila = POLITICA.fila(cluster)
        r = calcular_reposicion(entrada([10] * 52, lead=2, disponible=0), fila)
        assert r.cluster == cluster and r.modo == fila.modo
        if fila.modo == "formula":
            assert r.sugerido == 30 and r.z == fila.z, cluster
        elif fila.modo == "contra_pedido":
            assert r.sugerido == 0, cluster
        else:
            assert r.sugerido == 1, cluster
        # Con stock de sobra ninguno pide nada.
        lleno = calcular_reposicion(entrada([10] * 52, lead=2, disponible=500), fila)
        assert lleno.sugerido == 0, cluster


def test_un_z_mayor_da_mas_stock_de_seguridad():
    serie = [0, 10] * 26
    bajo = calcular_reposicion(entrada(serie), POLITICA.fila("BAA"))  # 90%, z 1,28
    medio = calcular_reposicion(entrada(serie), POLITICA.fila("AAA"))  # 95%, z 1,65
    alto = calcular_reposicion(entrada(serie), POLITICA.fila("AAC"))  # 98%, z 2,05
    assert bajo.stock_seguridad < medio.stock_seguridad < alto.stock_seguridad
    assert bajo.sugerido <= medio.sugerido <= alto.sugerido


# --------------------------------------------------------------------------- NUEVO y SIN MOVIMIENTO


@pytest.mark.parametrize(
    "estado, motivo", [(ESTADO_NUEVO, rp.MOTIVO_NUEVO), (ESTADO_SIN_MOVIMIENTO, rp.MOTIVO_SIN_MOVIMIENTO)]
)
def test_nuevo_y_sin_movimiento_dan_cero_con_su_marca(estado, motivo):
    r = calcular_reposicion(entrada([3] * 52, disponible=0), None, estado=estado)
    assert r.sugerido == 0 and r.sugerido_bruto == 0
    assert r.motivo == motivo and r.estado == estado
    assert r.cluster is None and r.modo is None and r.z is None
    assert r.stock_seguridad is None and r.nivel_objetivo is None
    assert r.demanda_semanal == 3  # igual se calcula D para mostrar


def test_nuevo_ignora_la_fila_si_se_la_pasan_por_error():
    r = calcular_reposicion(entrada(), FILA_FORMULA, estado=ESTADO_NUEVO)
    assert r.sugerido == 0 and r.motivo == rp.MOTIVO_NUEVO and r.z is None


def test_un_clasificado_sin_politica_es_un_error():
    with pytest.raises(ValueError, match="politica"):
        calcular_reposicion(entrada(), None)
    with pytest.raises(ValueError, match="estado"):
        calcular_reposicion(entrada(), FILA_FORMULA, estado="OTRO")


# --------------------------------------------------------------------------- historia corta y datos invalidos


def test_historia_corta_se_marca_y_usa_las_semanas_que_hay():
    r = calcular_reposicion(entrada([6] * 20), FILA_FORMULA)
    assert r.semanas_usadas == 20
    assert rp.BANDERA_HISTORIA_CORTA in r.banderas
    assert r.demanda_semanal == 6
    completa = calcular_reposicion(entrada([6] * 52), FILA_FORMULA)
    assert rp.BANDERA_HISTORIA_CORTA not in completa.banderas and completa.semanas_usadas == 52


def test_una_sola_semana_no_permite_estimar_sigma():
    r = calcular_reposicion(entrada([9]), FILA_FORMULA)
    assert r.sigma_semanal == 0.0
    assert rp.BANDERA_MUESTRA_INSUFICIENTE in r.banderas
    assert r.demanda_semanal == 9
    # Con sigma poblacional una semana si "se puede" (da 0 de verdad).
    pob = calcular_reposicion(entrada([9]), FILA_FORMULA, parametros=ParametrosReposicion(ddof=0))
    assert rp.BANDERA_MUESTRA_INSUFICIENTE not in pob.banderas


def test_media_y_sigma_coinciden_con_statistics():
    rnd = random.Random(2026)
    for _ in range(20):
        serie = [rnd.choice([0, 0, 1, 2, 5, 13, 40]) for _ in range(rnd.randint(2, 60))]
        media, sigma, ok = media_y_sigma(serie)
        assert ok
        assert media == pytest.approx(statistics.mean(serie), rel=1e-12, abs=1e-12)
        assert sigma == pytest.approx(statistics.stdev(serie), rel=1e-12, abs=1e-12)
        assert media_y_sigma(serie, ddof=0)[1] == pytest.approx(statistics.pstdev(serie), rel=1e-12, abs=1e-12)


@pytest.mark.parametrize(
    "kwargs, error",
    [
        ({"serie": []}, "vacia"),
        ({"lead": -1}, "negativo"),
        ({"multiplo": 0}, "multiplo"),
        ({"multiplo": -2}, "multiplo"),
        ({"minimo": -1}, "negativo"),
    ],
)
def test_datos_invalidos_paran_el_calculo(kwargs, error):
    with pytest.raises(ValueError, match=error):
        calcular_reposicion(entrada(**kwargs), FILA_FORMULA)


def test_una_serie_con_nan_o_texto_para_el_calculo():
    with pytest.raises(ValueError):
        calcular_reposicion(entrada([1, float("nan")] * 26), FILA_FORMULA)
    with pytest.raises(TypeError):
        calcular_reposicion(entrada(["3"] * 52), FILA_FORMULA)
    with pytest.raises(TypeError):
        calcular_reposicion(entrada(disponible=None), FILA_FORMULA)


@pytest.mark.parametrize("kwargs", [{"r_semanas": -1}, {"ddof": -1}, {"semanas_ventana": 0}])
def test_parametros_de_reposicion_incoherentes(kwargs):
    with pytest.raises(ValueError):
        ParametrosReposicion(**kwargs)


def test_una_politica_de_formula_sin_z_es_un_error_claro():
    rota = dataclasses.replace(FILA_FORMULA, z=None)
    with pytest.raises(ValueError, match="z"):
        calcular_reposicion(entrada(), rota)
    sin_minimo = dataclasses.replace(FILA_MINIMO_FIJO, minimo_fijo=None)
    with pytest.raises(ValueError, match="minimo"):
        calcular_reposicion(entrada(), sin_minimo)
    with pytest.raises(ValueError, match="modo"):
        calcular_reposicion(entrada(), dataclasses.replace(FILA_FORMULA, modo="otro"))


# --------------------------------------------------------------------------- auditoria e inmutabilidad


def test_devuelve_todos_los_intermedios_para_auditar():
    r = calcular_reposicion(entrada([0, 10] * 26, lead=2, disponible=3, transito=2, comprometido=1), FILA_FORMULA)
    nombres = {f.name for f in dataclasses.fields(r)}
    for esperado in (
        "demanda_semanal", "sigma_semanal", "ddof", "lead_time_semanas", "origen_lead_time", "r_semanas",
        "horizonte_semanas", "z", "nivel_servicio", "stock_seguridad", "nivel_objetivo", "stock_disponible",
        "en_transito", "comprometido", "comprometido_rotulo", "posicion", "sugerido_bruto", "minimo_compra",
        "multiplo", "valor_por_defecto", "sugerido", "motivo", "banderas", "semanas_usadas", "suma_serie",
    ):
        assert esperado in nombres, esperado
    for numerico in (
        r.demanda_semanal, r.sigma_semanal, r.stock_seguridad, r.nivel_objetivo, r.posicion, r.sugerido_bruto
    ):
        assert numerico is not None
    assert r.suma_serie == 260 and r.semanas_usadas == 52
    assert r.origen_lead_time == "prueba"
    assert (r.stock_disponible, r.en_transito, r.comprometido) == (3, 2, 1)


def test_ninguna_funcion_modifica_sus_entradas():
    serie = [0, 10, 3, 7] * 13
    copia_serie = list(serie)
    e = entrada(serie, disponible=4)
    copia_entrada = copy.deepcopy(e)
    fila_antes = copy.deepcopy(FILA_FORMULA)
    politica_antes = copy.deepcopy(POLITICA)
    parametros = ParametrosReposicion()
    parametros_antes = copy.deepcopy(parametros)

    calcular_reposicion(e, FILA_FORMULA, parametros=parametros)
    media_y_sigma(serie)
    redondear_compra(7, 10, 6)

    assert serie == copia_serie
    assert e == copia_entrada
    assert FILA_FORMULA == fila_antes and POLITICA == politica_antes and parametros == parametros_antes


def test_la_serie_puede_ser_una_tupla_y_el_resultado_es_el_mismo():
    serie = [0, 10, 3, 7] * 13
    assert calcular_reposicion(entrada(serie), FILA_FORMULA) == calcular_reposicion(entrada(tuple(serie)), FILA_FORMULA)


def test_resultado_y_entrada_son_inmutables():
    r = calcular_reposicion(entrada(), FILA_FORMULA)
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.sugerido = 99
    with pytest.raises(dataclasses.FrozenInstanceError):
        entrada().stock_disponible = 5
    assert isinstance(r.banderas, tuple)


def test_dos_corridas_iguales_dan_el_mismo_resultado():
    serie = [random.Random(3).choice([0, 1, 4, 9]) for _ in range(52)]
    assert calcular_reposicion(entrada(serie, lead=1.5), FILA_FORMULA) == calcular_reposicion(
        entrada(serie, lead=1.5), FILA_FORMULA
    )
