"""Politica de reposicion por cluster, parametrizada por bodega.

Un cluster es la sigla Frecuencia-Piezas-Valor (por ejemplo "ABC"): tres letras, cada
una A, B o C, y por eso siempre hay 27 (3 x 3 x 3). La politica dice, para cada uno,
como se calcula el sugerido:

  formula        S = D x (L + R) + z x sigma x raiz(L + R); se pide S - posicion.
  contra_pedido  el sugerido es 0 (solo se compra cuando el cliente lo pide).
  minimo_fijo    se pide `minimo_fijo` unidades solo cuando la posicion es 0 o menos.

Los valores de siembra (`politica_provisoria`) son los PROVISORIOS que dio el dueno
el 20-10-2026 y quedan pendientes de su OK. La letra de Piezas no cambia ningun
parametro: de las 27 filas, 18 son copias de otra con distinta letra de Piezas. Por
eso existe `aplicar_a_letras_de_piezas`, que la pantalla usara para editar una vez y
copiar a las tres.

Este modulo es PURO: sin base de datos ni red. La API lo usara para sembrar
`canal_digital_politica` y el script de Excel para leer los mismos valores.

La politica es inmutable: toda "edicion" devuelve una politica nueva y deja la
original intacta (la pantalla de vista previa compara las dos).
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from statistics import NormalDist
from typing import Iterable

LETRAS = ("A", "B", "C")

# Los 27 clusters en orden fijo: AAA, AAB, AAC, ABA ... CCC (Frecuencia, Piezas, Valor).
CLUSTERS = tuple(f + p + v for f in LETRAS for p in LETRAS for v in LETRAS)
N_CLUSTERS = len(CLUSTERS)

MODO_FORMULA = "formula"
MODO_CONTRA_PEDIDO = "contra_pedido"
MODO_MINIMO_FIJO = "minimo_fijo"
MODOS = (MODO_FORMULA, MODO_CONTRA_PEDIDO, MODO_MINIMO_FIJO)

BODEGA_CANAL_DIGITAL = "430"

# Los z del dueno estan redondeados a 2 decimales (95% -> 1,65 y no 1,6449; 98% -> 2,05
# y no 2,0537). La diferencia mas grande de la siembra es 0,0051; 0,01 deja pasar el
# redondeo a 2 decimales y frena un z mal tipeado (1,56 por 1,65 difiere 0,09).
TOLERANCIA_Z = 0.01


class PoliticaInvalida(ValueError):
    """La politica no tiene la forma exigida (no son exactamente los 27 clusters)."""


def cluster_de(frecuencia: str, piezas: str, valor: str) -> str:
    """'A', 'B', 'A' -> 'ABA'. Rechaza cualquier letra que no sea A, B o C."""
    for nombre, letra in (("frecuencia", frecuencia), ("piezas", piezas), ("valor", valor)):
        if letra not in LETRAS:
            raise ValueError(f"letra de {nombre} invalida: {letra!r} (debe ser A, B o C)")
    return frecuencia + piezas + valor


def letras_de(cluster: str) -> tuple[str, str, str]:
    """'ABC' -> ('A', 'B', 'C') = (frecuencia, piezas, valor)."""
    if cluster not in CLUSTERS:
        raise ValueError(f"cluster invalido: {cluster!r}")
    return cluster[0], cluster[1], cluster[2]


def z_para_nivel_servicio(nivel_servicio: float, decimales: int = 2) -> float:
    """z de la normal estandar para un nivel de servicio (0,95 -> 1,64 con 2 decimales).

    Ayuda para la pantalla: si la persona escribe 97% y deja el z vacio, se propone
    este. La siembra del dueno usa sus propios z (1,65 para 95%), no este redondeo.
    """
    if not 0 < nivel_servicio < 1:
        raise ValueError("el nivel de servicio debe estar entre 0 y 1 (sin incluirlos)")
    return round(NormalDist().inv_cdf(nivel_servicio), decimales)


@dataclass(frozen=True)
class FilaPolitica:
    """Una fila de la politica: como se repone un cluster en una bodega.

    Solo se llenan los campos que usa el modo; los demas van en None:
      formula        -> nivel_servicio y z
      contra_pedido  -> ninguno
      minimo_fijo    -> minimo_fijo
    `nivel_servicio` va como fraccion (0,95) y `z` es el multiplicador de la formula.
    """

    bodega: str
    cluster: str
    modo: str
    nivel_servicio: float | None = None
    z: float | None = None
    minimo_fijo: float | None = None

    @property
    def frecuencia(self) -> str:
        return self.cluster[0]

    @property
    def piezas(self) -> str:
        return self.cluster[1]

    @property
    def valor(self) -> str:
        return self.cluster[2]


def problemas_fila(fila: FilaPolitica) -> list[str]:
    """Todo lo que esta mal en una fila, en frases para mostrar. Lista vacia = fila valida."""
    problemas: list[str] = []
    cl = fila.cluster
    if cl not in CLUSTERS:
        problemas.append(f"{cl!r}: no es un cluster valido (tres letras A, B o C)")
        return problemas
    if fila.modo not in MODOS:
        problemas.append(f"{cl}: modo {fila.modo!r} desconocido (debe ser uno de {', '.join(MODOS)})")
        return problemas

    if fila.modo == MODO_FORMULA:
        if fila.nivel_servicio is None or fila.z is None:
            problemas.append(f"{cl}: el modo formula necesita nivel de servicio y z")
        else:
            if not 0 < fila.nivel_servicio < 1:
                problemas.append(
                    f"{cl}: el nivel de servicio debe estar entre 0 y 1 (sin incluirlos), "
                    f"llego {fila.nivel_servicio}"
                )
            elif fila.z < 0:
                problemas.append(f"{cl}: z no puede ser negativo (llego {fila.z})")
            else:
                esperado = NormalDist().inv_cdf(fila.nivel_servicio)
                if abs(fila.z - esperado) > TOLERANCIA_Z:
                    problemas.append(
                        f"{cl}: z={fila.z} no corresponde a un nivel de servicio de "
                        f"{fila.nivel_servicio:.0%} (le toca {esperado:.2f}, "
                        f"tolerancia {TOLERANCIA_Z})"
                    )
        if fila.minimo_fijo is not None:
            problemas.append(f"{cl}: el minimo fijo no aplica al modo formula")
    elif fila.modo == MODO_CONTRA_PEDIDO:
        if fila.nivel_servicio is not None or fila.z is not None or fila.minimo_fijo is not None:
            problemas.append(f"{cl}: contra pedido no usa nivel de servicio, z ni minimo fijo")
    else:  # minimo_fijo
        if fila.minimo_fijo is None or fila.minimo_fijo <= 0:
            problemas.append(f"{cl}: el modo minimo fijo necesita un minimo mayor que 0")
        if fila.nivel_servicio is not None or fila.z is not None:
            problemas.append(f"{cl}: el modo minimo fijo no usa nivel de servicio ni z")
    return problemas


def problemas_estructura(filas: Iterable[FilaPolitica]) -> list[str]:
    """Que haya exactamente los 27 clusters, una sola vez cada uno, de una sola bodega."""
    filas = list(filas)
    problemas: list[str] = []
    vistos: dict[str, int] = {}
    for f in filas:
        vistos[f.cluster] = vistos.get(f.cluster, 0) + 1
    repetidos = sorted(c for c, n in vistos.items() if n > 1)
    faltan = [c for c in CLUSTERS if c not in vistos]
    sobran = sorted(c for c in vistos if c not in CLUSTERS)
    if len(filas) != N_CLUSTERS:
        problemas.append(f"debe haber {N_CLUSTERS} filas y hay {len(filas)}")
    if repetidos:
        problemas.append("clusters repetidos: " + ", ".join(repetidos))
    if faltan:
        problemas.append("faltan clusters: " + ", ".join(faltan))
    if sobran:
        problemas.append("clusters que no existen: " + ", ".join(sobran))
    bodegas = sorted({f.bodega for f in filas})
    if len(bodegas) > 1:
        problemas.append("las filas mezclan bodegas: " + ", ".join(bodegas))
    return problemas


def validar_filas(filas: Iterable[FilaPolitica]) -> list[str]:
    """Estructura (27 filas) mas cada fila (modo, nivel de servicio, z). Vacia = todo bien."""
    filas = list(filas)
    return problemas_estructura(filas) + [p for f in filas for p in problemas_fila(f)]


@dataclass(frozen=True)
class Politica:
    """Las 27 filas de una bodega, siempre completas y en el orden AAA ... CCC.

    El constructor falla (`PoliticaInvalida`) si no son exactamente 27 clusters
    distintos de una sola bodega: una politica incompleta no puede existir. Los
    valores (z incoherente, modo sin parametros) NO hacen fallar al constructor para
    que la pantalla pueda armar una vista previa y mostrar los errores; se consultan
    con `validar()`.
    """

    bodega: str
    filas: tuple[FilaPolitica, ...]

    def __post_init__(self):
        filas = tuple(self.filas)
        problemas = problemas_estructura(filas)
        if not problemas and filas and filas[0].bodega != self.bodega:
            problemas.append(
                f"las filas son de la bodega {filas[0].bodega!r} y la politica de {self.bodega!r}"
            )
        if problemas:
            raise PoliticaInvalida("; ".join(problemas))
        orden = {c: i for i, c in enumerate(CLUSTERS)}
        object.__setattr__(self, "filas", tuple(sorted(filas, key=lambda f: orden[f.cluster])))

    def fila(self, cluster: str) -> FilaPolitica:
        for f in self.filas:
            if f.cluster == cluster:
                return f
        raise KeyError(cluster)

    def por_cluster(self) -> dict[str, FilaPolitica]:
        return {f.cluster: f for f in self.filas}

    def validar(self) -> list[str]:
        """Problemas de valores (z incoherente, parametros que faltan). Vacia = valida."""
        return validar_filas(self.filas)

    def reemplazar(self, *nuevas: FilaPolitica) -> "Politica":
        """Politica nueva con esas filas cambiadas (por cluster); la original no se toca."""
        por = self.por_cluster()
        for n in nuevas:
            if n.cluster not in por:
                raise PoliticaInvalida(f"cluster que no existe: {n.cluster!r}")
            por[n.cluster] = n
        return Politica(self.bodega, tuple(por.values()))


def con_parametros(fila: FilaPolitica, **cambios) -> FilaPolitica:
    """Copia de `fila` con los cambios dados (modo, nivel_servicio, z, minimo_fijo).

    Deja en None los campos que el modo resultante no usa, para que cambiar de modo
    no arrastre un z viejo a un cluster contra pedido. No valida los valores: eso es
    de `problemas_fila`.
    """
    permitidos = {"modo", "nivel_servicio", "z", "minimo_fijo"}
    desconocidos = set(cambios) - permitidos
    if desconocidos:
        raise TypeError("parametros que no se pueden cambiar: " + ", ".join(sorted(desconocidos)))
    nueva = replace(fila, **cambios)
    if nueva.modo == MODO_FORMULA:
        return replace(nueva, minimo_fijo=None)
    if nueva.modo == MODO_MINIMO_FIJO:
        return replace(nueva, nivel_servicio=None, z=None)
    return replace(nueva, nivel_servicio=None, z=None, minimo_fijo=None)


def aplicar_a_letras_de_piezas(politica: Politica, cluster: str, **cambios) -> Politica:
    """Copia los parametros de `cluster` (con `cambios` opcionales) a sus 3 letras de Piezas.

    Ejemplo: aplicar_a_letras_de_piezas(p, "ABA", nivel_servicio=0.9, z=1.28). El
    cluster es Frecuencia-Piezas-Valor, asi que "ABA" es Frecuencia A, Piezas B,
    Valor A, y el cambio llega a "AAA", "ABA" y "ACA": las tres letras de Piezas con
    la misma Frecuencia y el mismo Valor. Las otras 24 filas no cambian.
    """
    frecuencia, _, valor = letras_de(cluster)
    base = con_parametros(politica.fila(cluster), **cambios)
    nuevas = [
        replace(
            base,
            cluster=cluster_de(frecuencia, piezas, valor),
        )
        for piezas in LETRAS
    ]
    return politica.reemplazar(*nuevas)


# (Frecuencia, Valor) -> (modo, nivel_servicio, z, minimo_fijo). Valores PROVISORIOS del
# dueno, 20-10-2026. La letra de Piezas no entra: aplica igual a A, B y C.
_PROVISORIO: dict[tuple[str, str], tuple[str, float | None, float | None, float | None]] = {
    ("A", "A"): (MODO_FORMULA, 0.95, 1.65, None),
    ("A", "B"): (MODO_FORMULA, 0.97, 1.88, None),
    ("A", "C"): (MODO_FORMULA, 0.98, 2.05, None),
    ("B", "A"): (MODO_FORMULA, 0.90, 1.28, None),
    ("B", "B"): (MODO_FORMULA, 0.95, 1.65, None),
    ("B", "C"): (MODO_FORMULA, 0.95, 1.65, None),
    ("C", "A"): (MODO_CONTRA_PEDIDO, None, None, None),
    ("C", "B"): (MODO_CONTRA_PEDIDO, None, None, None),
    ("C", "C"): (MODO_MINIMO_FIJO, None, None, 1),
}


def filas_provisorias(bodega: str = BODEGA_CANAL_DIGITAL) -> list[FilaPolitica]:
    """Las 27 filas de siembra para una bodega (lo que se inserta la primera vez)."""
    filas = []
    for cluster in CLUSTERS:
        frecuencia, _, valor = letras_de(cluster)
        modo, nivel, z, minimo = _PROVISORIO[(frecuencia, valor)]
        filas.append(FilaPolitica(bodega, cluster, modo, nivel, z, minimo))
    return filas


def politica_provisoria(bodega: str = BODEGA_CANAL_DIGITAL) -> Politica:
    """La politica sembrada con los valores provisorios del dueno, para `bodega`."""
    return Politica(bodega, tuple(filas_provisorias(bodega)))
