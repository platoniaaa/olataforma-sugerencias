"""Reposicion semanal de un producto: cuanto pedir hoy.

Revision periodica con stock de seguridad (politica R, S). Todo en SEMANAS calendario.
Funcion PURA: sin base de datos, y no modifica lo que recibe. Devuelve todos los
numeros intermedios para poder auditarlos paso a paso.

  D      demanda semanal = promedio de las semanas de la serie (52, de lunes a domingo,
         netas de devoluciones).
  sigma  desviacion estandar de esas semanas. CRITERIO: MUESTRAL (divide por n - 1),
         parametro `ddof` (1 muestral, 0 poblacional). Se eligio muestral porque las 52
         semanas son una muestra de la demanda y no toda la demanda; con 52 datos la
         diferencia entre ambas es de 1%.
  L      lead time en semanas (puede ser fraccional: 5 dias = 5/7 de semana).
  R      periodo de revision, 1 semana.
  SS     stock de seguridad = z x sigma x raiz(L + R)
  S      nivel objetivo = D x (L + R) + SS
  posicion = disponible + en transito - comprometido
  sugerido = max(0, S - posicion), redondeado hacia arriba al multiplo, y como minimo
             el minimo de compra cuando es mayor que 0.

Modos de la politica (ver `politica.py`):
  formula        lo de arriba.
  contra_pedido  sugerido 0. D y sigma se calculan igual (para mostrar), SS y S no aplican.
  minimo_fijo    pide el minimo fijo solo cuando la posicion es 0 o menos. SS y S no aplican.
  Un producto NUEVO o SIN MOVIMIENTO no tiene cluster ni politica: sugerido 0 con su marca.

Redondeo: la cantidad final es el menor multiplo de `multiplo` que sea mayor o igual
que max(necesidad, minimo de compra). Si el minimo no es multiplo del multiplo
(minimo 10, multiplo 6), sube al siguiente multiplo (12): se cumplen las dos
restricciones del proveedor a la vez. Las diferencias de punto flotante menores a 1e-9
no suben un escalon (una necesidad de 12,0000000001 pide 12, no 13).

Minimo y multiplo por defecto: 1 y 1, con la bandera `valor_por_defecto`. No hay fuente
de datos para ellos todavia; la pantalla debe mostrar el aviso.
Comprometido: no existe como dato; si no se entrega vale 0 y el resultado lo rotula.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction
from typing import Sequence

from .clasificacion import ESTADO_CLASIFICADO, ESTADO_NUEVO, ESTADO_SIN_MOVIMIENTO
from .numeros import a_fraccion, limpio
from .politica import MODO_CONTRA_PEDIDO, MODO_FORMULA, MODO_MINIMO_FIJO, FilaPolitica

# Por que el sugerido es el que es.
MOTIVO_FORMULA_PIDE = "FORMULA_PIDE"
MOTIVO_FORMULA_CUBIERTO = "FORMULA_CUBIERTO"
MOTIVO_CONTRA_PEDIDO = "CONTRA_PEDIDO"
MOTIVO_MINIMO_FIJO_PIDE = "MINIMO_FIJO_PIDE"
MOTIVO_MINIMO_FIJO_CUBIERTO = "MINIMO_FIJO_CUBIERTO"
MOTIVO_NUEVO = "NUEVO"
MOTIVO_SIN_MOVIMIENTO = "SIN_MOVIMIENTO"

# Banderas informativas.
BANDERA_HISTORIA_CORTA = "HISTORIA_CORTA"
BANDERA_MUESTRA_INSUFICIENTE = "MUESTRA_INSUFICIENTE"
BANDERA_MINIMO_POR_DEFECTO = "MINIMO_POR_DEFECTO"
BANDERA_MULTIPLO_POR_DEFECTO = "MULTIPLO_POR_DEFECTO"
BANDERA_COMPROMETIDO_SIN_DATO = "COMPROMETIDO_SIN_DATO"

ROTULO_COMPROMETIDO_SIN_DATO = "0 (sin dato: el ERP no informa reservas)"

# Diferencias de punto flotante por debajo de esto no cuentan como "sobra un poco".
EPSILON = 1e-9


@dataclass(frozen=True)
class ParametrosReposicion:
    """r_semanas = 1; ddof = 1 (sigma muestral); semanas_ventana = 52 (marca la historia corta)."""

    r_semanas: float = 1
    ddof: int = 1
    semanas_ventana: int = 52

    def __post_init__(self):
        if self.r_semanas < 0:
            raise ValueError("el periodo de revision no puede ser negativo")
        if self.ddof < 0:
            raise ValueError("ddof no puede ser negativo")
        if self.semanas_ventana < 1:
            raise ValueError("la ventana debe tener al menos 1 semana")


@dataclass(frozen=True)
class EntradaReposicion:
    """Lo que hace falta saber de un producto padre para decidir cuanto pedir.

    `unidades_semana`: unidades NETAS por semana, de la mas antigua a la mas reciente
    (52 semanas; si el producto tiene menos historia, las que tenga desde su primera
    venta). `origen_lead_time` es un texto libre que se muestra ("ultimas 5 recepciones
    del proveedor", "respaldo del motor, 3 dias"). `comprometido`, `minimo_compra` y
    `multiplo` en None significan "sin dato": comprometido 0, minimo 1 y multiplo 1.
    """

    codigo: str
    unidades_semana: Sequence
    lead_time_semanas: float
    origen_lead_time: str
    stock_disponible: float
    en_transito: float = 0
    comprometido: float | None = None
    minimo_compra: float | None = None
    multiplo: float | None = None


@dataclass(frozen=True)
class ResultadoReposicion:
    """Todos los intermedios del calculo de un producto.

    Los nombres de la formula: demanda_semanal = D, sigma_semanal = sigma,
    stock_seguridad = SS, nivel_objetivo = S. `stock_seguridad` y `nivel_objetivo`
    son None cuando el modo no los usa (contra pedido, minimo fijo, NUEVO, SIN MOVIMIENTO).
    """

    codigo: str
    estado: str
    cluster: str | None
    modo: str | None
    motivo: str
    banderas: tuple[str, ...]
    semanas_usadas: int
    suma_serie: float
    demanda_semanal: float
    ddof: int
    sigma_semanal: float
    lead_time_semanas: float
    origen_lead_time: str
    r_semanas: float
    horizonte_semanas: float
    nivel_servicio: float | None
    z: float | None
    stock_seguridad: float | None
    nivel_objetivo: float | None
    stock_disponible: float
    en_transito: float
    comprometido: float
    comprometido_rotulo: str
    posicion: float
    sugerido_bruto: float
    minimo_compra: float
    multiplo: float
    valor_por_defecto: bool
    minimo_fijo: float | None
    sugerido: float


def techo_a_multiplo(valor: float, multiplo: float):
    """Menor multiplo de `multiplo` mayor o igual que `valor` (con la tolerancia de EPSILON)."""
    if multiplo <= 0:
        raise ValueError("el multiplo debe ser mayor que 0")
    cociente = valor / multiplo
    entero = round(cociente)
    if abs(cociente - entero) <= EPSILON * max(1.0, abs(cociente)):
        pasos = entero
    else:
        pasos = math.ceil(cociente)
    return limpio(pasos * multiplo)


def redondear_compra(necesidad: float, minimo_compra: float, multiplo: float):
    """Cantidad a pedir para una necesidad: 0 si no hay necesidad; si hay, el menor multiplo
    que cubre max(necesidad, minimo de compra)."""
    if necesidad <= EPSILON:
        return 0
    return techo_a_multiplo(max(necesidad, minimo_compra), multiplo)


def media_y_sigma(serie: Sequence, ddof: int = 1) -> tuple[float, float, bool]:
    """(media, sigma, muestra_suficiente) de una serie, calculados con fracciones exactas.

    sigma = raiz( suma((x - media)^2) / (n - ddof) ). Con una serie constante la suma
    es exactamente 0 y sigma es 0.0 (no 1e-16). Si n - ddof <= 0 (una sola semana con
    ddof 1) sigma no se puede estimar: devuelve 0.0 y muestra_suficiente False.
    No modifica `serie`.
    """
    datos = [a_fraccion(x) for x in serie]
    n = len(datos)
    if n == 0:
        raise ValueError("la serie semanal esta vacia")
    media = sum(datos, Fraction(0)) / n
    grados = n - ddof
    if grados <= 0:
        return float(media), 0.0, False
    varianza = sum(((x - media) ** 2 for x in datos), Fraction(0)) / grados
    return float(media), math.sqrt(varianza), True


def calcular_reposicion(
    entrada: EntradaReposicion,
    fila_politica: FilaPolitica | None,
    *,
    cluster: str | None = None,
    estado: str = ESTADO_CLASIFICADO,
    parametros: ParametrosReposicion | None = None,
) -> ResultadoReposicion:
    """Calcula el sugerido de un producto con la fila de politica de su cluster.

    `fila_politica` es None solo para NUEVO y SIN MOVIMIENTO (`estado`), que no tienen
    cluster: se calculan D y sigma para mostrar y el sugerido es 0 con su marca. Para
    un CLASIFICADO la fila es obligatoria.
    """
    parametros = parametros or ParametrosReposicion()
    if estado == ESTADO_CLASIFICADO and fila_politica is None:
        raise ValueError(f"{entrada.codigo!r}: un producto CLASIFICADO necesita su fila de politica")
    if estado not in (ESTADO_CLASIFICADO, ESTADO_NUEVO, ESTADO_SIN_MOVIMIENTO):
        raise ValueError(f"estado desconocido: {estado!r}")

    lead = float(a_fraccion(entrada.lead_time_semanas))
    if lead < 0:
        raise ValueError(f"{entrada.codigo!r}: el lead time no puede ser negativo")
    r = float(a_fraccion(parametros.r_semanas))
    horizonte = lead + r

    serie = [a_fraccion(x) for x in entrada.unidades_semana]
    d, sigma, suficiente = media_y_sigma(serie, parametros.ddof)
    n = len(serie)

    banderas: list[str] = []
    if n < parametros.semanas_ventana:
        banderas.append(BANDERA_HISTORIA_CORTA)
    if not suficiente:
        banderas.append(BANDERA_MUESTRA_INSUFICIENTE)

    # Minimo, multiplo y comprometido: sin dato -> valor por defecto, siempre a la vista.
    if entrada.minimo_compra is None:
        minimo_compra, min_defecto = 1, True
        banderas.append(BANDERA_MINIMO_POR_DEFECTO)
    else:
        minimo_compra, min_defecto = limpio(a_fraccion(entrada.minimo_compra)), False
        if minimo_compra < 0:
            raise ValueError(f"{entrada.codigo!r}: el minimo de compra no puede ser negativo")
    if entrada.multiplo is None:
        multiplo, mul_defecto = 1, True
        banderas.append(BANDERA_MULTIPLO_POR_DEFECTO)
    else:
        multiplo, mul_defecto = limpio(a_fraccion(entrada.multiplo)), False
        if multiplo <= 0:
            raise ValueError(f"{entrada.codigo!r}: el multiplo debe ser mayor que 0")
    if entrada.comprometido is None:
        comprometido, rotulo = 0.0, ROTULO_COMPROMETIDO_SIN_DATO
        banderas.append(BANDERA_COMPROMETIDO_SIN_DATO)
    else:
        comprometido, rotulo = float(a_fraccion(entrada.comprometido)), "dato del ERP"

    disponible = float(a_fraccion(entrada.stock_disponible))
    transito = float(a_fraccion(entrada.en_transito))
    posicion = disponible + transito - comprometido

    nivel_servicio = z = ss = s = minimo_fijo = None
    modo = None
    if estado != ESTADO_CLASIFICADO:
        motivo = MOTIVO_NUEVO if estado == ESTADO_NUEVO else MOTIVO_SIN_MOVIMIENTO
        bruto, sugerido = 0.0, 0
    else:
        modo = fila_politica.modo
        if cluster is None:
            cluster = fila_politica.cluster
        if modo == MODO_FORMULA:
            if fila_politica.z is None:
                raise ValueError(f"{entrada.codigo!r}: la politica {fila_politica.cluster} no trae z")
            nivel_servicio, z = fila_politica.nivel_servicio, float(fila_politica.z)
            ss = z * sigma * math.sqrt(horizonte)
            s = d * horizonte + ss
            bruto = max(0.0, s - posicion)
            sugerido = redondear_compra(bruto, minimo_compra, multiplo)
            motivo = MOTIVO_FORMULA_PIDE if sugerido > 0 else MOTIVO_FORMULA_CUBIERTO
        elif modo == MODO_CONTRA_PEDIDO:
            bruto, sugerido = 0.0, 0
            motivo = MOTIVO_CONTRA_PEDIDO
        elif modo == MODO_MINIMO_FIJO:
            if fila_politica.minimo_fijo is None:
                raise ValueError(
                    f"{entrada.codigo!r}: la politica {fila_politica.cluster} no trae minimo fijo"
                )
            minimo_fijo = fila_politica.minimo_fijo
            bruto = float(minimo_fijo) if posicion <= 0 else 0.0
            sugerido = redondear_compra(bruto, minimo_compra, multiplo)
            motivo = MOTIVO_MINIMO_FIJO_PIDE if sugerido > 0 else MOTIVO_MINIMO_FIJO_CUBIERTO
        else:
            raise ValueError(f"modo de politica desconocido: {modo!r}")

    return ResultadoReposicion(
        codigo=entrada.codigo,
        estado=estado,
        cluster=cluster,
        modo=modo,
        motivo=motivo,
        banderas=tuple(banderas),
        semanas_usadas=n,
        suma_serie=float(sum(serie, Fraction(0))),
        demanda_semanal=d,
        ddof=parametros.ddof,
        sigma_semanal=sigma,
        lead_time_semanas=lead,
        origen_lead_time=entrada.origen_lead_time,
        r_semanas=r,
        horizonte_semanas=horizonte,
        nivel_servicio=nivel_servicio,
        z=z,
        stock_seguridad=ss,
        nivel_objetivo=s,
        stock_disponible=disponible,
        en_transito=transito,
        comprometido=comprometido,
        comprometido_rotulo=rotulo,
        posicion=posicion,
        sugerido_bruto=bruto,
        minimo_compra=minimo_compra,
        multiplo=multiplo,
        valor_por_defecto=min_defecto or mul_defecto,
        minimo_fijo=minimo_fijo,
        sugerido=sugerido,
    )
