"""Clasificacion de Canal Digital: frecuencia, Pareto, NUEVO / SIN MOVIMIENTO y validaciones.

Lo que estos tests cuidan:

1. Frecuencia = meses con neto > 0, con sus bordes (12, 8 | 7, 5 | 4, 1 | 0).
2. El Pareto decide la letra por el acumulado ANTES del producto: el ejemplo del dueno
   (78% antes, 83% con el producto = A) y los bordes exactos de 80% y 95%.
3. Que el resultado no dependa del orden de entrada (empates incluidos) y que los
   acumulados cierren en exactamente 100% (aritmetica de fracciones).
4. NUEVO (primera venta hace menos de 6 meses) y SIN MOVIMIENTO fuera de la base.
5. Que los 27 clusters esten siempre en el resumen, vacios o no.
6. Las validaciones: detectan lo que deben detectar, no solo pasan.
7. Que ninguna funcion modifique sus entradas.
"""
import copy
import dataclasses
import random
from datetime import date, datetime
from decimal import Decimal
from fractions import Fraction

import pytest

from src.canal_digital import clasificacion as cl
from src.canal_digital.clasificacion import (
    ESTADO_CLASIFICADO,
    ESTADO_NUEVO,
    ESTADO_SIN_MOVIMIENTO,
    ParametrosClasificacion,
    VentaProducto,
    clasificar,
    resumen_por_cluster,
)
from src.canal_digital.politica import CLUSTERS

REF = date(2026, 10, 1)  # ventana oct-2025 a sep-2026
ANTIGUA = date(2024, 3, 1)  # vende hace mas de 6 meses: no es NUEVO


def venta(codigo, unidades=None, valor=None, primera=ANTIGUA, meses=12):
    """Producto con la lista de unidades por mes (rellena con ceros hasta 12 meses)."""
    unidades = list(unidades or [])
    unidades += [0] * (meses - len(unidades))
    valor = list(valor) if valor is not None else [u * 1000 for u in unidades]
    valor += [0] * (meses - len(valor))
    return VentaProducto(codigo, unidades, valor, primera)


def con_peso(codigo, peso, valor=None):
    """Producto que vende `peso` unidades en un solo mes (frecuencia C, una unidad = $1000)."""
    return venta(codigo, [peso], [peso * 1000 if valor is None else valor])


def por_codigo(res):
    return {p.codigo: p for p in res.productos}


# --------------------------------------------------------------------------- frecuencia


@pytest.mark.parametrize(
    "meses, letra",
    [(12, "A"), (11, "A"), (8, "A"), (7, "B"), (6, "B"), (5, "B"), (4, "C"), (2, "C"), (1, "C")],
)
def test_frecuencia_cuenta_meses_con_venta_neta(meses, letra):
    res = clasificar([venta("X", [1] * meses)], REF)
    p = res.producto("X")
    assert p.meses_con_venta == meses
    assert p.letra_frecuencia == letra
    assert p.estado == ESTADO_CLASIFICADO
    assert p.cluster.startswith(letra)


def test_cero_meses_es_sin_movimiento_y_queda_fuera_de_los_clusters():
    res = clasificar([venta("X", []), venta("Y", [3])], REF)
    x = res.producto("X")
    assert x.estado == ESTADO_SIN_MOVIMIENTO
    assert x.meses_con_venta == 0
    assert x.cluster is None and x.letra_frecuencia is None
    assert x.clase_piezas is None and x.ranking_piezas is None and x.pct_acum_unidades is None


def test_un_mes_neto_cero_o_negativo_no_cuenta_como_mes_con_venta():
    # 3 meses con venta, uno en cero y dos con mas devoluciones que ventas.
    p = clasificar([venta("X", [5, 0, -2, 4, -1, 9])], REF).producto("X")
    assert p.meses_con_venta == 3
    assert p.unidades_ventana == 15  # 5 + 0 - 2 + 4 - 1 + 9: la suma es neta, con signo


def test_un_producto_cuyo_unico_mes_positivo_se_compensa_sigue_siendo_clasificado_con_peso_cero():
    # +3 y -5: frecuencia 1, neto total -2. Peso 0 en el Pareto, pero no desaparece.
    res = clasificar([venta("X", [3, -5]), venta("Y", [10])], REF)
    x = res.producto("X")
    assert x.estado == ESTADO_CLASIFICADO and x.unidades_ventana == -2
    assert x.pct_unidades == 0
    assert res.total_unidades_base == 10  # el negativo no resta de la base
    assert x.clase_piezas == "C"  # va al final del ranking, con acumulado 100% antes
    assert cl.contar_estados(res).datos["clasificados_con_neto_no_positivo"] == 1


# --------------------------------------------------------------------------- Pareto: acumulado ANTES


def test_ejemplo_del_dueno_78_antes_y_83_con_el_producto_es_A():
    # Pesos que suman 100 para que el peso sea el porcentaje: 50, 28, 5, 4, 3, 2, 2, 2, 2, 2.
    pesos = [50, 28, 5, 4, 3, 2, 2, 2, 2, 2]
    res = clasificar([con_peso(f"P{i:02d}", w) for i, w in enumerate(pesos)], REF)
    p5 = res.producto("P02")  # el de peso 5: lugar 3
    assert p5.ranking_piezas == 3
    assert p5.acum_antes_unidades == Fraction(78, 100)
    assert p5.pct_acum_unidades == Fraction(83, 100)
    assert p5.clase_piezas == "A"  # entro mientras el acumulado aun no pasaba el 80%
    # El siguiente parte desde 83%: ya no es A.
    p4 = res.producto("P03")
    assert p4.acum_antes_unidades == Fraction(83, 100)
    assert p4.clase_piezas == "B"
    # Lo mismo en valor (cada unidad vale $1000, misma proporcion).
    assert p5.clase_valor == "A" and p5.acum_antes_valor == Fraction(78, 100)


def test_el_corte_es_estricto_80_antes_es_B_y_95_antes_es_C():
    res = clasificar([con_peso("P1", 80), con_peso("P2", 15), con_peso("P3", 5)], REF)
    assert [res.producto(c).clase_piezas for c in ("P1", "P2", "P3")] == ["A", "B", "C"]
    # P2 parte exactamente en 80% -> no es "menor que 80%" -> B.
    assert res.producto("P2").acum_antes_unidades == Fraction(80, 100)
    # P3 parte exactamente en 95% -> no es "menor que 95%" -> C.
    assert res.producto("P3").acum_antes_unidades == Fraction(95, 100)


def test_un_producto_que_justo_no_pasa_el_corte_sigue_siendo_A():
    # 79 antes de P2: aun es menor que 80% aunque P2 llegue a 99%.
    res = clasificar([con_peso("P1", 79), con_peso("P2", 20), con_peso("P3", 1)], REF)
    assert [res.producto(c).clase_piezas for c in ("P1", "P2", "P3")] == ["A", "A", "C"]
    assert res.producto("P2").pct_acum_unidades == Fraction(99, 100)


def test_un_unico_producto_es_A_con_100_por_ciento():
    res = clasificar([con_peso("SOLO", 7)], REF)
    p = res.producto("SOLO")
    assert (p.clase_piezas, p.clase_valor) == ("A", "A")
    assert p.pct_unidades == p.pct_acum_unidades == 1
    assert p.cluster == "CAA"  # frecuencia 1 mes = C


def test_el_pareto_de_piezas_y_el_de_valor_son_independientes():
    # X vende mucho pero barato; Y vende poco pero caro. Frecuencia identica.
    x = venta("X", [100] * 12, [1000] * 12)  # 1.200 unidades, $12.000
    y = venta("Y", [10] * 12, [100000] * 12)  # 120 unidades, $1.200.000
    z = venta("Z", [5], [5000])  # 5 unidades, $5.000 (1 mes)
    res = clasificar([x, y, z], REF)
    px, py, pz = res.producto("X"), res.producto("Y"), res.producto("Z")
    # Piezas: X 1.200 de 1.325 (90,6%) es A; Y parte en 90,6% (menor que 95%) es B; Z parte en 99,6% es C.
    assert (px.clase_piezas, py.clase_piezas, pz.clase_piezas) == ("A", "B", "C")
    # Valor: Y es casi todo el valor (A); X parte en 98,6% y Z en 99,6%: los dos son C.
    assert (px.clase_valor, py.clase_valor, pz.clase_valor) == ("C", "A", "C")
    assert (px.cluster, py.cluster, pz.cluster) == ("AAC", "ABA", "CCC")


def test_el_cluster_es_frecuencia_piezas_valor_en_ese_orden():
    # Frecuencia B (5 meses), piezas A, valor C: "BAC".
    big_u = venta("U", [100] * 5, [10] * 5)  # muchas unidades, poco valor
    big_v = venta("V", [1] * 12, [1_000_000] * 12)  # pocas unidades, mucho valor
    res = clasificar([big_u, big_v], REF)
    assert res.producto("U").cluster == "BAC"  # 5 meses = B; casi todas las unidades = A; casi nada de valor = C
    assert res.producto("V").cluster == "ACA"  # 12 meses = A; casi sin unidades = C; casi todo el valor = A


def test_la_base_del_pareto_son_solo_los_productos_clasificables():
    # Un NUEVO gigante y un SIN MOVIMIENTO no deben comerse el porcentaje de los demas.
    res = clasificar(
        [
            con_peso("A1", 60),
            con_peso("A2", 40),
            venta("NUEVO1", [10_000], primera=date(2026, 8, 1)),
            venta("SINMOV", []),
        ],
        REF,
    )
    assert res.n_base == 2
    assert res.total_unidades_base == 100
    assert res.producto("A1").pct_unidades == Fraction(60, 100)
    assert res.producto("A2").pct_acum_unidades == 1
    assert res.producto("NUEVO1").pct_unidades is None


def test_porcentajes_con_numeros_decimales_no_arrastran_error_de_punto_flotante():
    # 0,1 + 0,2 en float es 0,30000000000000004; aqui debe ser 3/10 exacto.
    p = clasificar([venta("X", [1], [0.1, 0.2])], REF).producto("X")
    assert p.valor_ventana == Fraction(3, 10)
    # Un monto con decimales (costo de la planilla) se lee como se ve en la celda.
    q = clasificar([venta("Y", [1], [4339.95])], REF).producto("Y")
    assert q.valor_ventana == Fraction(433995, 100)
    r = clasificar([venta("Z", [1], [Decimal("12.5")])], REF).producto("Z")
    assert r.valor_ventana == Fraction(25, 2)


def test_un_corte_con_decimales_decide_con_exactitud():
    # 33,3 + 33,3 + 33,4: el acumulado de los dos primeros es 66,6 y el del tercero parte en 66,6.
    pesos = [Decimal("33.3"), Decimal("33.3"), Decimal("33.4")]
    prods = [venta(f"P{i}", [1], [w]) for i, w in enumerate(pesos)]
    res = clasificar(prods, REF, ParametrosClasificacion(corte_a_pct=Decimal("66.6"), corte_b_pct=90))
    por = res.producto
    # orden por valor: P2 (33,4) primero; antes 0 -> A; P0 antes 33,4 -> A; P1 antes 66,7 -> no < 66,6 -> B
    assert por("P2").clase_valor == "A" and por("P0").clase_valor == "A" and por("P1").clase_valor == "B"


# --------------------------------------------------------------------------- empates y orden de entrada


def test_el_desempate_es_mayor_valor_y_luego_codigo():
    # Mismas unidades; distinto valor: el de mas valor va primero en el ranking de piezas.
    a = venta("A", [10], [100])
    b = venta("B", [10], [900])
    c = venta("C", [10], [500])
    res = clasificar([a, b, c], REF)
    assert [res.producto(k).ranking_piezas for k in ("A", "B", "C")] == [3, 1, 2]
    # Mismas unidades y mismo valor: manda el codigo (ascendente).
    d = venta("Z9", [10], [100])
    e = venta("Z1", [10], [100])
    res2 = clasificar([d, e], REF)
    assert res2.producto("Z1").ranking_piezas == 1 and res2.producto("Z9").ranking_piezas == 2
    assert res2.producto("Z1").ranking_valor == 1 and res2.producto("Z9").ranking_valor == 2


def _datos_sinteticos(n=300, semilla=42):
    rnd = random.Random(semilla)
    productos = []
    for i in range(n):
        unidades = [rnd.choice([0, 0, 0, 1, 2, 5, 20, 80]) for _ in range(12)]
        precio = rnd.choice([500, 1200, 4900, 25_000, 180_000])
        valor = [u * precio for u in unidades]
        primera = date(2024, 1, 1) if rnd.random() < 0.9 else date(2026, rnd.randint(1, 9), rnd.randint(1, 28))
        productos.append(VentaProducto(f"{rnd.randint(10, 29)} {i:06d}", unidades, valor, primera))
    return productos


def _firma(res):
    return {
        p.codigo: (p.estado, p.cluster, p.ranking_piezas, p.ranking_valor, p.pct_acum_unidades, p.pct_acum_valor)
        for p in res.productos
    }


def test_el_resultado_no_depende_del_orden_de_entrada():
    productos = _datos_sinteticos()
    # Metemos empates a proposito: 20 productos con exactamente los mismos numeros.
    for i in range(20):
        productos.append(VentaProducto(f"99 EMPATE{i:02d}", [3] * 12, [3000] * 12, ANTIGUA))
    base = _firma(clasificar(productos, REF))
    rnd = random.Random(1)
    for _ in range(5):
        barajado = list(productos)
        rnd.shuffle(barajado)
        assert _firma(clasificar(barajado, REF)) == base


def test_dos_corridas_iguales_dan_el_mismo_resultado():
    productos = _datos_sinteticos()
    assert clasificar(productos, REF) == clasificar(productos, REF)


# --------------------------------------------------------------------------- acumulados y validaciones


def test_los_acumulados_cierran_exactamente_en_100_por_ciento():
    res = clasificar(_datos_sinteticos(), REF)
    base = res.por_estado(ESTADO_CLASIFICADO)
    assert len(base) > 100
    assert sum(p.pct_unidades for p in base) == 1
    assert sum(p.pct_valor for p in base) == 1
    ultimo_u = max(base, key=lambda p: p.ranking_piezas)
    ultimo_v = max(base, key=lambda p: p.ranking_valor)
    assert ultimo_u.pct_acum_unidades == 1 and ultimo_v.pct_acum_valor == 1
    v = cl.validar_acumulados(res)
    assert v.ok, v.detalle


def test_validar_acumulados_detecta_un_acumulado_roto():
    res = clasificar([con_peso("P1", 60), con_peso("P2", 40)], REF)
    roto = dataclasses.replace(res.producto("P2"), pct_acum_unidades=Fraction(9, 10))
    productos = (res.producto("P1"), roto)
    mal = dataclasses.replace(res, productos=productos, _indice={p.codigo: p for p in productos})
    v = cl.validar_acumulados(mal)
    assert not v.ok and "piezas" in v.detalle


def test_validar_acumulados_falla_si_la_base_no_tiene_ventas_y_pasa_si_esta_vacia():
    # Dos productos con mes positivo pero neto total 0: la base suma 0 y no hay porcentajes.
    res = clasificar([venta("X", [1, -1]), venta("Y", [2, -2])], REF)
    assert res.total_unidades_base == 0
    assert not cl.validar_acumulados(res).ok
    vacio = clasificar([], REF)
    assert cl.validar_acumulados(vacio).ok


def test_particion_de_unidades_unidades_clasificadas_mas_nuevo_mas_sin_movimiento():
    productos = [
        con_peso("OK1", 50),
        con_peso("OK2", 30),
        venta("NUEVO1", [7], primera=date(2026, 7, 1)),
        venta("SINMOV", [0]),
        venta("DEVOL", [0, -4]),  # sin movimiento con devoluciones: resta unidades del universo
    ]
    res = clasificar(productos, REF)
    v = cl.validar_particion_unidades(res)
    assert v.ok
    assert v.datos[ESTADO_CLASIFICADO] == 80 and v.datos[ESTADO_NUEVO] == 7 and v.datos[ESTADO_SIN_MOVIMIENTO] == -4
    # Con el total de la fuente (el Excel): 50 + 30 + 7 - 4 = 83.
    assert cl.validar_particion_unidades(res, 83).ok
    # Si la fuente dice otra cosa, se perdieron o sobraron unidades: debe fallar.
    assert not cl.validar_particion_unidades(res, 84).ok
    assert not cl.validar_particion_unidades(res, Fraction(1665, 20)).ok


def test_proporciones_80_15_5_reporta_la_desviacion():
    res = clasificar(_datos_sinteticos(), REF)
    v = cl.validar_proporciones(res)
    assert v.ok, v.detalle
    assert v.datos["objetivo_pct"] == {"A": 80.0, "B": 15.0, "C": 5.0}
    assert set(v.datos["real_pct_piezas"]) == {"A", "B", "C"}
    assert abs(sum(v.datos["real_pct_piezas"].values()) - 100) < 0.01
    assert "pp" in v.detalle
    # Con un solo producto A es 100% (desviacion 20 pp): con tolerancia de 10 falla y lo dice.
    solo = clasificar([con_peso("SOLO", 5)], REF)
    malo = cl.validar_proporciones(solo)
    assert not malo.ok
    assert malo.datos["desviacion_maxima_pp"] == 20.0
    assert cl.validar_proporciones(solo, tolerancia_pp=25).ok


def test_contar_estados_cuenta_nuevo_y_sin_movimiento():
    productos = [
        con_peso("OK1", 10),
        con_peso("OK2", 5),
        venta("N1", [1], primera=date(2026, 5, 1)),
        venta("N2", [1, 1], primera=date(2026, 9, 15)),
        venta("N3", [1], primera=date(2026, 6, 30)),
        venta("S1", []),
        venta("S2", [0, 0]),
    ]
    v = cl.contar_estados(clasificar(productos, REF))
    assert v.ok  # informativa
    assert v.datos[ESTADO_CLASIFICADO]["productos"] == 2
    assert v.datos[ESTADO_NUEVO]["productos"] == 3
    assert v.datos[ESTADO_SIN_MOVIMIENTO]["productos"] == 2
    assert "NUEVO: 3" in v.detalle and "SIN MOVIMIENTO: 2" in v.detalle


def test_ningun_hijo_suelto_falla_si_hay_un_codigo_con_padre_vigente():
    mapa = {"17 2499389": "19 CC1Z9365E", "19 CC1Z9365E": "19 CC1Z9365E"}
    ok = cl.validar_sin_hijos_sueltos(["19 CC1Z9365E", "20 OTRO"], mapa)
    assert ok.ok
    malo = cl.validar_sin_hijos_sueltos(["19 CC1Z9365E", "17 2499389", "20 OTRO"], mapa)
    assert not malo.ok
    assert malo.datos["cantidad"] == 1
    assert "17 2499389 -> 19 CC1Z9365E" in malo.detalle
    # Un grupo ambiguo publicado queda suelto a proposito y no cuenta como falla.
    excusado = cl.validar_sin_hijos_sueltos(["17 2499389"], mapa, ambiguos=["17 2499389"])
    assert excusado.ok


def test_el_resumen_de_27_celdas_suma_el_total_de_productos():
    res = clasificar(_datos_sinteticos(), REF)
    resumen = resumen_por_cluster(res)
    v = cl.validar_27_clusters(res, resumen)
    assert v.ok, v.detalle
    # Si una celda pierde un producto, la validacion lo ve.
    rota = list(resumen)
    primero_con_datos = next(i for i, r in enumerate(rota) if r.n_productos)
    rota[primero_con_datos] = dataclasses.replace(rota[primero_con_datos], n_productos=rota[primero_con_datos].n_productos - 1)
    assert not cl.validar_27_clusters(res, rota).ok
    # Y si faltan clusters.
    assert not cl.validar_27_clusters(res, resumen[:-1]).ok


def test_ejecutar_validaciones_arma_la_lista_completa_y_exigir_para_si_algo_falla():
    productos = [con_peso("OK1", 70), con_peso("OK2", 30), venta("N1", [2], primera=date(2026, 8, 1))]
    res = clasificar(productos, REF)
    vals = cl.ejecutar_validaciones(res, mapa_padre={"OK2": "OK1"}, total_unidades_universo=102, tolerancia_pp=30)
    nombres = [v.nombre for v in vals]
    assert len(nombres) == 6 and len(set(nombres)) == 6
    fallidas = [v.nombre for v in vals if not v.ok]
    assert fallidas == ["Ningun codigo con padre vigente aparece suelto"]  # OK2 es hijo de OK1
    with pytest.raises(cl.ValidacionFallida, match="padre vigente"):
        cl.exigir(vals)
    # Sin el mapa de padres y con tolerancia holgada todo pasa y exigir no lanza.
    cl.exigir(cl.ejecutar_validaciones(res, total_unidades_universo=102, tolerancia_pp=30))


# --------------------------------------------------------------------------- NUEVO y SIN MOVIMIENTO


@pytest.mark.parametrize(
    "primera, esperado",
    [
        (date(2026, 4, 1), ESTADO_CLASIFICADO),  # exactamente 6 meses: ya no es "menos de 6"
        (date(2026, 4, 2), ESTADO_NUEVO),  # un dia menos de 6 meses
        (date(2026, 9, 30), ESTADO_NUEVO),
        (date(2026, 3, 31), ESTADO_CLASIFICADO),
        (date(2024, 1, 15), ESTADO_CLASIFICADO),
        (None, ESTADO_CLASIFICADO),  # sin fecha conocida: no hay evidencia de que sea nuevo
    ],
)
def test_nuevo_es_primera_venta_hace_menos_de_6_meses(primera, esperado):
    res = clasificar([venta("X", [4, 4, 4], primera=primera), con_peso("Y", 1)], REF)
    assert res.producto("X").estado == esperado


def test_nuevo_no_se_clasifica_pero_conserva_su_frecuencia_informativa():
    res = clasificar([venta("N", [0, 0, 0, 0, 0, 0, 3, 3, 3, 3, 3, 3], primera=date(2026, 4, 15))], REF)
    n = res.producto("N")
    assert n.estado == ESTADO_NUEVO
    assert n.letra_frecuencia == "B"  # 6 meses
    assert n.cluster is None and n.clase_piezas is None and n.ranking_valor is None
    assert res.n_base == 0
    assert resumen_por_cluster(res)[0].n_productos == 0


def test_el_plazo_de_nuevo_es_un_parametro():
    p = venta("X", [3], primera=date(2026, 2, 1))  # 8 meses
    assert clasificar([p], REF).producto("X").estado == ESTADO_CLASIFICADO
    assert clasificar([p], REF, ParametrosClasificacion(nuevo_meses=9)).producto("X").estado == ESTADO_NUEVO
    assert clasificar([p], REF, ParametrosClasificacion(nuevo_meses=0)).producto("X").estado == ESTADO_CLASIFICADO


def test_sin_movimiento_gana_sobre_nuevo_si_no_hay_ventas_netas():
    # Vendio y devolvio todo dentro de cada mes (neto 0 en todos): no hay ventas netas que clasificar.
    res = clasificar([venta("X", [0, -2], primera=date(2026, 9, 1))], REF)
    assert res.producto("X").estado == ESTADO_SIN_MOVIMIENTO


def test_fecha_de_referencia_y_primera_venta_aceptan_datetime():
    res = clasificar([venta("X", [1], primera=datetime(2026, 8, 1, 14, 30))], datetime(2026, 10, 1, 9, 0))
    assert res.producto("X").estado == ESTADO_NUEVO
    assert res.fecha_referencia == REF


def test_restar_meses_ajusta_el_dia_al_ultimo_del_mes():
    from src.canal_digital.numeros import restar_meses

    assert restar_meses(date(2026, 10, 1), 6) == date(2026, 4, 1)
    assert restar_meses(date(2026, 8, 31), 6) == date(2026, 2, 28)
    assert restar_meses(date(2028, 8, 31), 6) == date(2028, 2, 29)  # bisiesto
    assert restar_meses(date(2026, 3, 15), 6) == date(2025, 9, 15)  # cruza de anio


# --------------------------------------------------------------------------- los 27 clusters


def test_el_resumen_trae_siempre_los_27_clusters_aunque_este_vacio():
    vacio = resumen_por_cluster(clasificar([], REF))
    assert [r.cluster for r in vacio] == list(CLUSTERS)
    assert len(vacio) == 27
    assert all(r.n_productos == 0 and r.unidades == 0 and r.pct_unidades == 0 for r in vacio)
    assert all(r.sugerido_pesos is None for r in vacio)


def test_el_resumen_con_un_solo_producto_tiene_26_clusters_vacios():
    res = clasificar([venta("X", [1] * 12)], REF)
    resumen = resumen_por_cluster(res)
    ocupados = [r for r in resumen if r.n_productos]
    assert [r.cluster for r in ocupados] == ["AAA"]
    assert ocupados[0].pct_unidades == 1 and ocupados[0].pct_valor == 1
    assert len(resumen) == 27


def test_el_resumen_suma_porcentajes_100_y_productos_totales():
    res = clasificar(_datos_sinteticos(), REF)
    resumen = resumen_por_cluster(res)
    assert sum(r.n_productos for r in resumen) == res.n_base
    assert sum(r.pct_unidades for r in resumen) == 1
    assert sum(r.pct_valor for r in resumen) == 1
    assert sum(r.unidades for r in resumen) == res.total_unidades_base
    assert sum(r.valor for r in resumen) == res.total_valor_base


def test_el_resumen_suma_el_sugerido_en_pesos_solo_si_se_entrega():
    res = clasificar(
        [venta("X", [5] * 12), venta("Y", [4] * 12), con_peso("Z", 1)], REF
    )
    resumen = {r.cluster: r for r in resumen_por_cluster(res, {"X": 1000, "Y": 2500.5, "Z": 300})}
    # X (5 x 12 = 60 u.) e Y (4 x 12 = 48 u.) son A en todo; Z (1 mes) es frecuencia C.
    assert [res.producto(c).cluster for c in "XYZ"] == ["AAA", "AAA", "CCC"]
    assert resumen["AAA"].sugerido_pesos == Fraction(7001, 2)  # 1.000 + 2.500,5
    assert resumen["CCC"].sugerido_pesos == 300
    assert sum(r.sugerido_pesos for r in resumen.values()) == Fraction(7601, 2)
    # Un producto sin monto cuenta 0, y los clusters vacios quedan en 0 (no None) si se entrego el mapa.
    parcial = {r.cluster: r.sugerido_pesos for r in resumen_por_cluster(res, {"X": 10})}
    assert sum(parcial.values()) == 10
    assert parcial["BBB"] == 0
    # Sin mapa: None, para no mostrar un 0 que parezca dato.
    assert all(r.sugerido_pesos is None for r in resumen_por_cluster(res))


# --------------------------------------------------------------------------- entradas invalidas


def test_codigo_repetido_es_un_error_de_armado():
    with pytest.raises(ValueError, match="repetido"):
        clasificar([con_peso("X", 1), con_peso("X", 2)], REF)


@pytest.mark.parametrize("meses", [0, 11, 13])
def test_la_serie_debe_tener_un_valor_por_mes_de_la_ventana(meses):
    malo = VentaProducto("X", [1] * meses, [1000] * meses, ANTIGUA)
    with pytest.raises(ValueError, match="12 meses"):
        clasificar([malo], REF)
    # Tambien si solo una de las dos series viene cortada.
    media = VentaProducto("X", [1] * 12, [1000] * meses, ANTIGUA)
    with pytest.raises(ValueError):
        clasificar([media], REF)


@pytest.mark.parametrize("malo", [float("nan"), float("inf"), "12", None, True])
def test_un_dato_que_no_es_una_cantidad_para_el_calculo(malo):
    with pytest.raises((ValueError, TypeError)):
        clasificar([VentaProducto("X", [malo] + [0] * 11, [0] * 12, ANTIGUA)], REF)


def test_la_ventana_puede_ser_de_otro_largo_si_se_ajustan_los_minimos():
    p = ParametrosClasificacion(ventana_meses=6, frecuencia_a_min=4, frecuencia_b_min=2)
    res = clasificar([venta("X", [1] * 4, meses=6), venta("Y", [1] * 2, meses=6), venta("Z", [1], meses=6)], REF, p)
    assert [res.producto(c).letra_frecuencia for c in "XYZ"] == ["A", "B", "C"]
    with pytest.raises(ValueError):
        clasificar([venta("X", [1])], REF, p)  # 12 meses en una ventana de 6


@pytest.mark.parametrize(
    "kwargs",
    [
        {"ventana_meses": 0},
        {"nuevo_meses": -1},
        {"corte_a_pct": 95, "corte_b_pct": 80},
        {"corte_a_pct": 0},
        {"corte_b_pct": 101},
        {"frecuencia_a_min": 5, "frecuencia_b_min": 5},
        {"frecuencia_a_min": 13},
        {"frecuencia_b_min": 0},
    ],
)
def test_parametros_incoherentes_se_rechazan(kwargs):
    with pytest.raises(ValueError):
        ParametrosClasificacion(**kwargs)


def test_cambiar_los_cortes_cambia_las_letras():
    prods = [con_peso("P1", 60), con_peso("P2", 30), con_peso("P3", 10)]
    normal = clasificar(prods, REF)
    assert [normal.producto(c).clase_piezas for c in ("P1", "P2", "P3")] == ["A", "A", "B"]
    estrecho = clasificar(prods, REF, ParametrosClasificacion(corte_a_pct=50, corte_b_pct=80))
    assert [estrecho.producto(c).clase_piezas for c in ("P1", "P2", "P3")] == ["A", "B", "C"]


# --------------------------------------------------------------------------- no modifica sus entradas


def test_ninguna_funcion_modifica_sus_entradas():
    productos = _datos_sinteticos(80)
    copia = copy.deepcopy(productos)
    mapa = {"17 000001": "19 000099"}
    mapa_copia = copy.deepcopy(mapa)
    sugerido = {productos[0].codigo: 1500}
    sugerido_copia = copy.deepcopy(sugerido)
    ambiguos = ["17 000001"]
    ambiguos_copia = list(ambiguos)

    res = clasificar(productos, REF)
    resumen = resumen_por_cluster(res, sugerido)
    cl.ejecutar_validaciones(res, mapa_padre=mapa, ambiguos=ambiguos, total_unidades_universo=1)
    cl.validar_27_clusters(res, resumen)

    assert productos == copia
    assert [p.codigo for p in productos] == [p.codigo for p in copia]  # ni siquiera se reordena
    assert mapa == mapa_copia and sugerido == sugerido_copia and ambiguos == ambiguos_copia


def test_los_resultados_son_inmutables():
    res = clasificar([con_peso("X", 1)], REF)
    with pytest.raises(dataclasses.FrozenInstanceError):
        res.producto("X").cluster = "AAA"
    with pytest.raises(dataclasses.FrozenInstanceError):
        res.n_base = 99
    assert isinstance(res.productos, tuple)
    assert isinstance(res.producto("X").unidades_mes, tuple)


def test_el_resultado_conserva_el_orden_de_entrada():
    productos = [con_peso(c, i + 1) for i, c in enumerate(["Z", "B", "M", "A"])]
    res = clasificar(productos, REF)
    assert [p.codigo for p in res.productos] == ["Z", "B", "M", "A"]


# --------------------------------------------------------------------------- los 27 se alcanzan


def _repartir(total, meses_con_venta):
    """`total` repartido en `meses_con_venta` meses (el resto en el ultimo); el resto de los 12 en cero."""
    base = total // meses_con_venta
    lista = [base] * meses_con_venta
    lista[-1] += total - base * meses_con_venta
    return lista + [0] * (12 - meses_con_venta)


def test_los_27_clusters_se_alcanzan_con_un_producto_en_cada_uno():
    """Un producto por cluster, armado para que cada letra salga por su propio camino.

    Cada letra de Piezas y de Valor tiene 9 productos con pesos 10.000 (A), 1.700 (B) y 500 (C):
    el total es 109.800, el noveno A parte en 80.000 (72,9%, menor que 80%), el primer B parte
    en 90.000 (82,0%) y el noveno B en 103.600 (94,4%, menor que 95%), y el primer C parte en
    105.300 (95,9%). Asi la letra no depende del orden de los empates dentro de cada grupo.
    """
    peso = {"A": 10_000, "B": 1_700, "C": 500}
    meses = {"A": 12, "B": 6, "C": 2}
    productos = []
    for cluster in CLUSTERS:
        f, p, v = cluster
        productos.append(
            VentaProducto(
                f"{cluster} 000",
                _repartir(peso[p], meses[f]),
                _repartir(peso[v] * 1000, meses[f]),
                ANTIGUA,
            )
        )
    res = clasificar(productos, REF)
    assert res.n_base == 27
    for cluster in CLUSTERS:
        p = res.producto(f"{cluster} 000")
        assert p.estado == ESTADO_CLASIFICADO
        assert (p.letra_frecuencia, p.clase_piezas, p.clase_valor) == tuple(cluster), cluster
        assert p.cluster == cluster
    resumen = resumen_por_cluster(res)
    assert [r.cluster for r in resumen] == list(CLUSTERS)
    assert all(r.n_productos == 1 for r in resumen)
    assert cl.validar_27_clusters(res, resumen).ok
    assert cl.validar_acumulados(res).ok


def test_cada_cluster_alcanzado_tiene_su_fila_de_politica():
    from src.canal_digital.politica import politica_provisoria

    politica = politica_provisoria()
    for cluster in CLUSTERS:
        assert politica.fila(cluster).cluster == cluster
