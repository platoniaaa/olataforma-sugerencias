"""Politica por cluster de Canal Digital: siempre 27 filas, valores de siembra y z coherente.

Lo que estos tests cuidan:

1. Que existan exactamente los 27 clusters (3 x 3 x 3), en orden, y que una politica
   incompleta no se pueda construir.
2. Que la siembra sea la del dueno (20-10-2026): formula 95/97/98 para Frecuencia A segun
   el Valor, 90/95/95 para B, contra pedido para C con Valor A o B y minimo fijo de 1
   para C con Valor C; y que la letra de Piezas no cambie nada.
3. Que el z sea coherente con el nivel de servicio (con la tolerancia de los valores
   redondeados del dueno) y que un z mal tipeado se detecte.
4. Que la politica sea inmutable y parametrizada por bodega.
"""
import dataclasses
import itertools
import random
from statistics import NormalDist

import pytest

from src.canal_digital import politica as pol
from src.canal_digital.politica import (
    CLUSTERS,
    FilaPolitica,
    Politica,
    PoliticaInvalida,
    aplicar_a_letras_de_piezas,
    con_parametros,
    politica_provisoria,
)

# (Frecuencia, Valor) -> (modo, nivel de servicio, z, minimo fijo): lo que dijo el dueno.
ESPERADO = {
    ("A", "A"): ("formula", 0.95, 1.65, None),
    ("A", "B"): ("formula", 0.97, 1.88, None),
    ("A", "C"): ("formula", 0.98, 2.05, None),
    ("B", "A"): ("formula", 0.90, 1.28, None),
    ("B", "B"): ("formula", 0.95, 1.65, None),
    ("B", "C"): ("formula", 0.95, 1.65, None),
    ("C", "A"): ("contra_pedido", None, None, None),
    ("C", "B"): ("contra_pedido", None, None, None),
    ("C", "C"): ("minimo_fijo", None, None, 1),
}


def _firma(fila):
    return (fila.modo, fila.nivel_servicio, fila.z, fila.minimo_fijo)


# --------------------------------------------------------------------------- 27 clusters


def test_hay_27_clusters_distintos_y_en_orden():
    assert len(CLUSTERS) == 27 == pol.N_CLUSTERS
    assert len(set(CLUSTERS)) == 27
    assert CLUSTERS[0] == "AAA" and CLUSTERS[1] == "AAB" and CLUSTERS[3] == "ABA"
    assert CLUSTERS[-1] == "CCC"
    assert list(CLUSTERS) == sorted(CLUSTERS)
    assert CLUSTERS == tuple("".join(t) for t in itertools.product("ABC", repeat=3))


def test_cluster_de_y_letras_de_son_inversas():
    for c in CLUSTERS:
        assert pol.cluster_de(*pol.letras_de(c)) == c


@pytest.mark.parametrize("letras", [("D", "A", "A"), ("A", "a", "A"), ("A", "A", ""), ("A", "A", "AA")])
def test_cluster_de_rechaza_letras_que_no_son_abc(letras):
    with pytest.raises(ValueError):
        pol.cluster_de(*letras)


@pytest.mark.parametrize("cluster", ["AB", "ABCD", "ABD", "aaa", ""])
def test_letras_de_rechaza_clusters_invalidos(cluster):
    with pytest.raises(ValueError):
        pol.letras_de(cluster)


# --------------------------------------------------------------------------- siembra


def test_la_siembra_trae_27_filas_validas_de_la_bodega_430():
    p = politica_provisoria()
    assert p.bodega == "430" == pol.BODEGA_CANAL_DIGITAL
    assert [f.cluster for f in p.filas] == list(CLUSTERS)
    assert {f.bodega for f in p.filas} == {"430"}
    assert p.validar() == []


@pytest.mark.parametrize("cluster", CLUSTERS)
def test_cada_cluster_tiene_los_valores_del_dueno(cluster):
    fila = politica_provisoria().fila(cluster)
    frecuencia, _, valor = cluster[0], cluster[1], cluster[2]
    assert _firma(fila) == ESPERADO[(frecuencia, valor)]


def test_la_letra_de_piezas_no_cambia_ningun_parametro():
    p = politica_provisoria()
    for f, v in itertools.product("ABC", repeat=2):
        firmas = {_firma(p.fila(f + piezas + v)) for piezas in "ABC"}
        assert len(firmas) == 1, f"Frecuencia {f} Valor {v} cambia con Piezas"
    # 9 combinaciones (Frecuencia, Valor) x 3 letras de Piezas = 27: 18 filas son copias.
    combinaciones = {(c[0], c[2]) for c in CLUSTERS}
    assert len(combinaciones) * 3 == 27 and len(combinaciones) * 2 == 18
    # Y de esas 9, tres comparten parametros (AA, BB y BC son 95% con z 1,65): 6 firmas distintas.
    assert len({_firma(f) for f in p.filas}) == 6


def test_reparto_de_modos_de_la_siembra():
    modos = [f.modo for f in politica_provisoria().filas]
    assert modos.count("formula") == 18
    assert modos.count("contra_pedido") == 6
    assert modos.count("minimo_fijo") == 3


def test_la_politica_esta_parametrizada_por_bodega():
    a, b = politica_provisoria("430"), politica_provisoria("500")
    assert {f.bodega for f in b.filas} == {"500"}
    assert [f.cluster for f in b.filas] == list(CLUSTERS)
    # Mismos valores de siembra, pero son politicas distintas e independientes.
    assert [_firma(f) for f in a.filas] == [_firma(f) for f in b.filas]
    editada = aplicar_a_letras_de_piezas(b, "AAA", nivel_servicio=0.9, z=1.28)
    assert _firma(a.fila("AAA")) == ESPERADO[("A", "A")]
    assert editada.fila("AAA").z == 1.28


# --------------------------------------------------------------------------- z coherente


def test_los_z_de_la_siembra_son_coherentes_con_el_nivel_de_servicio():
    for f in politica_provisoria().filas:
        if f.modo == "formula":
            exacto = NormalDist().inv_cdf(f.nivel_servicio)
            assert abs(f.z - exacto) <= pol.TOLERANCIA_Z, f.cluster


def test_la_tolerancia_deja_pasar_el_redondeo_del_dueno_y_frena_un_error_de_tipeo():
    base = politica_provisoria().fila("AAA")  # 95% -> 1,65 (exacto 1,6449)
    assert pol.problemas_fila(base) == []
    # 1,56 en vez de 1,65: dedos cruzados.
    malo = dataclasses.replace(base, z=1.56)
    assert len(pol.problemas_fila(malo)) == 1
    assert "1.56" in pol.problemas_fila(malo)[0]
    # z de otro nivel de servicio.
    otro = dataclasses.replace(base, z=2.05)
    assert pol.problemas_fila(otro)


def test_z_para_nivel_servicio():
    assert pol.z_para_nivel_servicio(0.95) == 1.64
    assert pol.z_para_nivel_servicio(0.95, decimales=3) == 1.645
    assert pol.z_para_nivel_servicio(0.5) == 0.0
    for malo in (0, 1, -0.1, 1.2):
        with pytest.raises(ValueError):
            pol.z_para_nivel_servicio(malo)


@pytest.mark.parametrize(
    "fila",
    [
        FilaPolitica("430", "AAA", "formula"),  # sin nivel ni z
        FilaPolitica("430", "AAA", "formula", 0.95),  # sin z
        FilaPolitica("430", "AAA", "formula", 1.0, 1.65),  # nivel fuera de rango
        FilaPolitica("430", "AAA", "formula", 0.0, 1.65),
        FilaPolitica("430", "AAA", "formula", 0.95, -1.65),  # z negativo
        FilaPolitica("430", "AAA", "formula", 0.95, 1.65, 1),  # el minimo fijo no aplica
        FilaPolitica("430", "CAA", "contra_pedido", 0.95, 1.65),  # contra pedido no usa z
        FilaPolitica("430", "CAA", "contra_pedido", minimo_fijo=1),
        FilaPolitica("430", "CCC", "minimo_fijo"),  # sin minimo
        FilaPolitica("430", "CCC", "minimo_fijo", minimo_fijo=0),
        FilaPolitica("430", "CCC", "minimo_fijo", minimo_fijo=-1),
        FilaPolitica("430", "CCC", "minimo_fijo", 0.95, 1.65, 1),  # el minimo fijo no usa z
        FilaPolitica("430", "AAA", "inventado"),  # modo desconocido
        FilaPolitica("430", "XYZ", "formula", 0.95, 1.65),  # cluster desconocido
    ],
)
def test_una_fila_mal_armada_se_detecta(fila):
    assert pol.problemas_fila(fila), fila


def test_validar_junta_los_problemas_de_todas_las_filas():
    p = politica_provisoria()
    mala1 = dataclasses.replace(p.fila("AAA"), z=1.0)
    mala2 = dataclasses.replace(p.fila("CCC"), minimo_fijo=None)
    q = p.reemplazar(mala1, mala2)  # construir NO falla: la pantalla necesita ver los errores
    problemas = q.validar()
    assert len(problemas) == 2
    assert any("AAA" in x for x in problemas) and any("CCC" in x for x in problemas)
    assert p.validar() == []  # la original sigue intacta


# --------------------------------------------------------------------------- siempre 27


def test_no_se_puede_construir_una_politica_incompleta():
    filas = politica_provisoria().filas
    with pytest.raises(PoliticaInvalida, match="26"):
        Politica("430", filas[:-1])
    with pytest.raises(PoliticaInvalida, match="faltan clusters: CCC"):
        Politica("430", filas[:-1])
    with pytest.raises(PoliticaInvalida):
        Politica("430", ())


def test_no_se_puede_construir_con_filas_repetidas_o_de_mas():
    filas = politica_provisoria().filas
    con_repetida = filas[:-1] + (filas[0],)  # 27 filas pero AAA dos veces y falta CCC
    with pytest.raises(PoliticaInvalida, match="repetidos: AAA"):
        Politica("430", con_repetida)
    with pytest.raises(PoliticaInvalida, match="28"):
        Politica("430", filas + (filas[0],))
    extra = FilaPolitica("430", "ZZZ", "contra_pedido")
    with pytest.raises(PoliticaInvalida, match="no existen"):
        Politica("430", filas[:-1] + (extra,))


def test_no_se_mezclan_bodegas():
    filas = list(politica_provisoria().filas)
    filas[5] = dataclasses.replace(filas[5], bodega="500")
    with pytest.raises(PoliticaInvalida, match="mezclan bodegas"):
        Politica("430", tuple(filas))
    with pytest.raises(PoliticaInvalida, match="bodega"):
        Politica("500", politica_provisoria("430").filas)


def test_las_filas_se_ordenan_aunque_lleguen_desordenadas():
    filas = list(politica_provisoria().filas)
    random.Random(7).shuffle(filas)
    p = Politica("430", tuple(filas))
    assert [f.cluster for f in p.filas] == list(CLUSTERS)


def test_fila_de_un_cluster_inexistente():
    with pytest.raises(KeyError):
        politica_provisoria().fila("ZZZ")


# --------------------------------------------------------------------------- inmutable


def test_la_politica_es_inmutable():
    p = politica_provisoria()
    with pytest.raises(dataclasses.FrozenInstanceError):
        p.bodega = "999"
    with pytest.raises(dataclasses.FrozenInstanceError):
        p.fila("AAA").z = 3.0
    assert isinstance(p.filas, tuple)


def test_reemplazar_devuelve_otra_politica_y_no_toca_la_original():
    p = politica_provisoria()
    antes = [_firma(f) for f in p.filas]
    q = p.reemplazar(dataclasses.replace(p.fila("BBB"), nivel_servicio=0.97, z=1.88))
    assert q is not p
    assert q.fila("BBB").z == 1.88
    assert p.fila("BBB").z == 1.65
    assert [_firma(f) for f in p.filas] == antes
    with pytest.raises(PoliticaInvalida):
        p.reemplazar(FilaPolitica("430", "ZZZ", "contra_pedido"))


# --------------------------------------------------------------------------- aplicar a las 3 letras de Piezas


def test_aplicar_a_las_3_letras_de_piezas_cambia_solo_esas_3_filas():
    p = politica_provisoria()
    q = aplicar_a_letras_de_piezas(p, "ABA", nivel_servicio=0.99, z=2.33)
    cambiadas = {c for c in CLUSTERS if _firma(q.fila(c)) != _firma(p.fila(c))}
    assert cambiadas == {"AAA", "ABA", "ACA"}
    for c in ("AAA", "ABA", "ACA"):
        f = q.fila(c)
        assert (f.modo, f.nivel_servicio, f.z) == ("formula", 0.99, 2.33)
        assert f.cluster == c and f.bodega == "430"
    assert q.validar() == []
    # Las otras 24 filas son exactamente las mismas.
    for c in set(CLUSTERS) - cambiadas:
        assert q.fila(c) == p.fila(c)


def test_aplicar_sin_cambios_copia_el_cluster_origen_a_sus_hermanos():
    p = politica_provisoria()
    p = p.reemplazar(dataclasses.replace(p.fila("BCB"), nivel_servicio=0.99, z=2.33))  # solo BCB cambia
    q = aplicar_a_letras_de_piezas(p, "BCB")
    assert [_firma(q.fila(c)) for c in ("BAB", "BBB", "BCB")] == [(("formula", 0.99, 2.33, None))] * 3


def test_aplicar_cambiando_de_modo_limpia_lo_que_ya_no_aplica():
    p = politica_provisoria()
    q = aplicar_a_letras_de_piezas(p, "ABA", modo="contra_pedido")
    for c in ("AAA", "ABA", "ACA"):
        f = q.fila(c)
        assert (f.modo, f.nivel_servicio, f.z, f.minimo_fijo) == ("contra_pedido", None, None, None)
    assert q.validar() == []
    r = aplicar_a_letras_de_piezas(q, "AAA", modo="minimo_fijo", minimo_fijo=2)
    assert [_firma(r.fila(c)) for c in ("AAA", "ABA", "ACA")] == [("minimo_fijo", None, None, 2)] * 3
    assert r.validar() == []


def test_aplicar_no_modifica_la_politica_original():
    p = politica_provisoria()
    antes = [_firma(f) for f in p.filas]
    aplicar_a_letras_de_piezas(p, "CCC", minimo_fijo=5)
    assert [_firma(f) for f in p.filas] == antes


def test_con_parametros_rechaza_campos_que_no_se_editan():
    f = politica_provisoria().fila("AAA")
    with pytest.raises(TypeError, match="cluster"):
        con_parametros(f, cluster="BBB")
    with pytest.raises(TypeError):
        aplicar_a_letras_de_piezas(politica_provisoria(), "AAA", bodega="500")


def test_con_parametros_pasando_a_formula_deja_pendiente_el_z():
    f = politica_provisoria().fila("CCC")  # minimo fijo
    g = con_parametros(f, modo="formula")
    assert g.modo == "formula" and g.minimo_fijo is None and g.z is None
    assert pol.problemas_fila(g)  # falta nivel de servicio y z: la pantalla lo avisa
    h = con_parametros(g, nivel_servicio=0.95, z=pol.z_para_nivel_servicio(0.95))
    assert pol.problemas_fila(h) == []
