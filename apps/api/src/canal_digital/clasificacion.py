"""Clasificacion de productos del canal en clusters Frecuencia-Piezas-Valor.

Entra, por producto PADRE, lo que vendio en los ultimos 12 meses cerrados (unidades y
valor por mes, ya netos de devoluciones) y la fecha de su primera venta en toda la
empresa. Sale, por producto, su estado y su cluster. Funciones PURAS: sin base de
datos, sin polars ni pandas, y ninguna modifica lo que recibe.

Reglas (plan del 20-10-2026, decisiones del dueno):

  Estado
    SIN MOVIMIENTO  ningun mes con neto > 0 en la ventana. Fuera de los clusters.
    NUEVO           su primera venta en la empresa fue hace MENOS de `nuevo_meses`
                    (6). No se clasifica: aun no tiene historia para ser A o B.
    CLASIFICADO     el resto.
  Frecuencia (F)    meses con neto > 0: A de 8 a 12, B de 5 a 7, C de 1 a 4.
  Piezas (P)        Pareto de unidades.  Valor (V)  Pareto de valor.
    Orden descendente por la metrica; desempate por mayor valor y luego por codigo
    (asi dos corridas con los mismos datos dan el mismo resultado). La letra se
    decide por el acumulado ANTES del producto: A si es menor que 80%, B si es menor
    que 95%, C el resto. Por eso un producto que parte en 78% y termina en 83% es A:
    entro mientras el acumulado aun no pasaba el corte.
    La base del Pareto son solo los productos CLASIFICADOS (no NUEVO ni SIN MOVIMIENTO).
  Cluster           F + P + V, por ejemplo "ABC". Los 27 existen siempre en el resumen,
                    tengan o no productos.

Aritmetica: unidades y valores se convierten a `Fraction` exacta y los porcentajes se
comparan multiplicando en cruz (acumulado x 100 < corte x total). No hay floats en
ninguna decision.

Caso raro: un producto con meses positivos pero neto total <= 0 en la ventana
(devoluciones de ventas anteriores) cuenta como peso 0 en el Pareto y en el resumen;
sigue siendo CLASIFICADO porque su frecuencia es mayor que 0.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from fractions import Fraction
from typing import Iterable, Mapping, Sequence

from .numeros import a_fecha, a_fraccion, restar_meses
from .politica import CLUSTERS, LETRAS, cluster_de

ESTADO_CLASIFICADO = "CLASIFICADO"
ESTADO_NUEVO = "NUEVO"
ESTADO_SIN_MOVIMIENTO = "SIN MOVIMIENTO"
ESTADOS = (ESTADO_CLASIFICADO, ESTADO_NUEVO, ESTADO_SIN_MOVIMIENTO)

CERO = Fraction(0)
UNO = Fraction(1)


@dataclass(frozen=True)
class ParametrosClasificacion:
    """Parametros de la clasificacion. Los defectos son los del plan (ventana 12, nuevo 6, 80/95).

    `corte_a_pct` y `corte_b_pct` van en porcentaje (80 y 95). Los minimos de
    frecuencia (8 y 5) son para una ventana de 12 meses; si se cambia la ventana hay
    que cambiarlos tambien.
    """

    ventana_meses: int = 12
    nuevo_meses: int = 6
    corte_a_pct: float = 80
    corte_b_pct: float = 95
    frecuencia_a_min: int = 8
    frecuencia_b_min: int = 5

    def __post_init__(self):
        if self.ventana_meses < 1:
            raise ValueError("la ventana debe tener al menos 1 mes")
        if self.nuevo_meses < 0:
            raise ValueError("nuevo_meses no puede ser negativo")
        if not 0 < a_fraccion(self.corte_a_pct) < a_fraccion(self.corte_b_pct) <= 100:
            raise ValueError("los cortes deben cumplir 0 < corte A < corte B <= 100")
        if not 1 <= self.frecuencia_b_min < self.frecuencia_a_min <= self.ventana_meses:
            raise ValueError("las frecuencias deben cumplir 1 <= minimo B < minimo A <= ventana")


@dataclass(frozen=True)
class VentaProducto:
    """Lo que vendio un producto padre: la entrada de `clasificar`.

    `unidades_mes` y `valor_mes` tienen un elemento por mes de la ventana, del mas
    antiguo al mas reciente, ya NETOS de devoluciones (un mes puede ser negativo si
    hubo mas notas de credito que ventas). `primera_venta` es la primera venta del
    producto en TODA la empresa, no solo en el canal; None si no se conoce.
    """

    codigo: str
    unidades_mes: Sequence
    valor_mes: Sequence
    primera_venta: date | None = None


@dataclass(frozen=True)
class ClasificacionProducto:
    """El resultado para un producto. Los porcentajes son `Fraction` exactas (0 a 1)."""

    codigo: str
    estado: str
    meses_con_venta: int
    unidades_mes: tuple[Fraction, ...]
    valor_mes: tuple[Fraction, ...]
    unidades_ventana: Fraction
    valor_ventana: Fraction
    primera_venta: date | None
    letra_frecuencia: str | None = None
    clase_piezas: str | None = None
    clase_valor: str | None = None
    ranking_piezas: int | None = None
    ranking_valor: int | None = None
    pct_unidades: Fraction | None = None
    pct_acum_unidades: Fraction | None = None
    pct_valor: Fraction | None = None
    pct_acum_valor: Fraction | None = None
    cluster: str | None = None

    @property
    def acum_antes_unidades(self) -> Fraction | None:
        """Acumulado de unidades ANTES de este producto: lo que decide su letra de Piezas."""
        if self.pct_acum_unidades is None:
            return None
        return self.pct_acum_unidades - self.pct_unidades

    @property
    def acum_antes_valor(self) -> Fraction | None:
        if self.pct_acum_valor is None:
            return None
        return self.pct_acum_valor - self.pct_valor


@dataclass(frozen=True)
class ResultadoClasificacion:
    """Todos los productos clasificados, en el orden en que entraron, mas los totales de la base."""

    productos: tuple[ClasificacionProducto, ...]
    parametros: ParametrosClasificacion
    fecha_referencia: date
    n_base: int
    total_unidades_base: Fraction
    total_valor_base: Fraction
    _indice: Mapping[str, ClasificacionProducto] = field(
        repr=False, compare=False, default_factory=dict
    )

    def producto(self, codigo: str) -> ClasificacionProducto:
        return self._indice[codigo]

    def por_estado(self, estado: str) -> tuple[ClasificacionProducto, ...]:
        return tuple(p for p in self.productos if p.estado == estado)


def _letra_frecuencia(meses: int, parametros: ParametrosClasificacion) -> str | None:
    if meses >= parametros.frecuencia_a_min:
        return "A"
    if meses >= parametros.frecuencia_b_min:
        return "B"
    if meses >= 1:
        return "C"
    return None


def _pareto(
    pesos: dict[str, Fraction],
    desempate: dict[str, Fraction],
    corte_a_pct: Fraction,
    corte_b_pct: Fraction,
) -> dict[str, tuple[int, str, Fraction, Fraction]]:
    """Pareto de una metrica. Devuelve codigo -> (ranking, clase, pct, pct_acumulado).

    Orden: peso descendente, luego `desempate` descendente, luego codigo ascendente.
    La clase sale del acumulado ANTES del producto (cruzando en vez de dividir):
      A si antes x 100 < corte_a x total;  B si < corte_b x total;  C el resto.
    Con total 0 (nadie con peso) no hay porcentajes: todos C con 0%.
    """
    total = sum(pesos.values(), CERO)
    orden = sorted(pesos, key=lambda c: (-pesos[c], -desempate[c], c))
    salida: dict[str, tuple[int, str, Fraction, Fraction]] = {}
    acumulado = CERO
    for lugar, codigo in enumerate(orden, start=1):
        antes = acumulado
        acumulado += pesos[codigo]
        if total == 0:
            salida[codigo] = (lugar, "C", CERO, CERO)
            continue
        if antes * 100 < corte_a_pct * total:
            clase = "A"
        elif antes * 100 < corte_b_pct * total:
            clase = "B"
        else:
            clase = "C"
        salida[codigo] = (lugar, clase, pesos[codigo] / total, acumulado / total)
    return salida


def _peso(valor: Fraction) -> Fraction:
    return valor if valor > 0 else CERO


def clasificar(
    productos: Iterable[VentaProducto],
    fecha_referencia: date,
    parametros: ParametrosClasificacion | None = None,
) -> ResultadoClasificacion:
    """Clasifica todos los productos. No modifica `productos`.

    `fecha_referencia` es el primer dia despues de la ventana (para oct-2025 a
    sep-2026, el 2026-10-01): un producto es NUEVO si su primera venta es posterior
    a `fecha_referencia` menos `nuevo_meses` meses (2026-04-01). Una primera venta
    exactamente hace 6 meses ya NO es nueva ("menos de 6 meses").

    Falla (ValueError) si un codigo viene repetido o una serie no tiene un valor por
    mes de la ventana: un producto duplicado o cortado es un error de armado, no algo
    que se arregle en silencio.
    """
    parametros = parametros or ParametrosClasificacion()
    fecha_referencia = a_fecha(fecha_referencia)
    limite_nuevo = restar_meses(fecha_referencia, parametros.nuevo_meses)
    corte_a = a_fraccion(parametros.corte_a_pct)
    corte_b = a_fraccion(parametros.corte_b_pct)

    vistos: set[str] = set()
    preparados = []  # (codigo, estado, meses, unidades, valores, u_total, v_total, primera, letra)
    for p in productos:
        if p.codigo in vistos:
            raise ValueError(f"codigo repetido en la entrada: {p.codigo!r}")
        vistos.add(p.codigo)
        unidades = tuple(a_fraccion(x) for x in p.unidades_mes)
        valores = tuple(a_fraccion(x) for x in p.valor_mes)
        if len(unidades) != parametros.ventana_meses or len(valores) != parametros.ventana_meses:
            raise ValueError(
                f"{p.codigo!r}: se esperaban {parametros.ventana_meses} meses y llegaron "
                f"{len(unidades)} de unidades y {len(valores)} de valor"
            )
        primera = a_fecha(p.primera_venta) if p.primera_venta is not None else None
        meses = sum(1 for u in unidades if u > 0)
        if meses == 0:
            estado = ESTADO_SIN_MOVIMIENTO
        elif primera is not None and primera > limite_nuevo:
            estado = ESTADO_NUEVO
        else:
            estado = ESTADO_CLASIFICADO
        preparados.append(
            (p.codigo, estado, meses, unidades, valores, sum(unidades, CERO), sum(valores, CERO), primera)
        )

    base = [x for x in preparados if x[1] == ESTADO_CLASIFICADO]
    pesos_u = {x[0]: _peso(x[5]) for x in base}
    pesos_v = {x[0]: _peso(x[6]) for x in base}
    pareto_u = _pareto(pesos_u, pesos_v, corte_a, corte_b)
    # Pareto de valor: el desempate "mayor valor" ya es la metrica, asi que queda el codigo.
    pareto_v = _pareto(pesos_v, {c: CERO for c in pesos_v}, corte_a, corte_b)

    resultado = []
    for codigo, estado, meses, unidades, valores, u_total, v_total, primera in preparados:
        letra_f = _letra_frecuencia(meses, parametros)
        if estado == ESTADO_CLASIFICADO:
            r_u, clase_p, pct_u, acum_u = pareto_u[codigo]
            r_v, clase_v, pct_v, acum_v = pareto_v[codigo]
            resultado.append(
                ClasificacionProducto(
                    codigo=codigo, estado=estado, meses_con_venta=meses,
                    unidades_mes=unidades, valor_mes=valores,
                    unidades_ventana=u_total, valor_ventana=v_total, primera_venta=primera,
                    letra_frecuencia=letra_f, clase_piezas=clase_p, clase_valor=clase_v,
                    ranking_piezas=r_u, ranking_valor=r_v,
                    pct_unidades=pct_u, pct_acum_unidades=acum_u,
                    pct_valor=pct_v, pct_acum_valor=acum_v,
                    cluster=cluster_de(letra_f, clase_p, clase_v),
                )
            )
        else:
            resultado.append(
                ClasificacionProducto(
                    codigo=codigo, estado=estado, meses_con_venta=meses,
                    unidades_mes=unidades, valor_mes=valores,
                    unidades_ventana=u_total, valor_ventana=v_total, primera_venta=primera,
                    letra_frecuencia=letra_f if estado == ESTADO_NUEVO else None,
                )
            )

    productos_t = tuple(resultado)
    return ResultadoClasificacion(
        productos=productos_t,
        parametros=parametros,
        fecha_referencia=fecha_referencia,
        n_base=len(base),
        total_unidades_base=sum(pesos_u.values(), CERO),
        total_valor_base=sum(pesos_v.values(), CERO),
        _indice={p.codigo: p for p in productos_t},
    )


@dataclass(frozen=True)
class ResumenCluster:
    """Una fila del resumen por cluster. Los porcentajes son sobre la base clasificada."""

    cluster: str
    n_productos: int
    unidades: Fraction
    valor: Fraction
    pct_unidades: Fraction
    pct_valor: Fraction
    sugerido_pesos: Fraction | None


def resumen_por_cluster(
    resultado: ResultadoClasificacion,
    sugerido_pesos: Mapping[str, object] | None = None,
) -> tuple[ResumenCluster, ...]:
    """Los 27 clusters, SIEMPRE, en el orden AAA ... CCC, aunque alguno quede vacio.

    `sugerido_pesos` (opcional): codigo -> monto del sugerido en $. Si se entrega, cada
    cluster suma el de sus productos (un producto sin monto cuenta 0); si no, la
    columna queda en None para no mostrar un 0 que parezca dato.
    """
    acum = {c: [0, CERO, CERO, CERO] for c in CLUSTERS}  # n, unidades, valor, $
    for p in resultado.productos:
        if p.estado != ESTADO_CLASIFICADO:
            continue
        a = acum[p.cluster]
        a[0] += 1
        a[1] += _peso(p.unidades_ventana)
        a[2] += _peso(p.valor_ventana)
        if sugerido_pesos is not None and p.codigo in sugerido_pesos:
            a[3] += a_fraccion(sugerido_pesos[p.codigo])
    tu, tv = resultado.total_unidades_base, resultado.total_valor_base
    return tuple(
        ResumenCluster(
            cluster=c,
            n_productos=acum[c][0],
            unidades=acum[c][1],
            valor=acum[c][2],
            pct_unidades=acum[c][1] / tu if tu else CERO,
            pct_valor=acum[c][2] / tv if tv else CERO,
            sugerido_pesos=acum[c][3] if sugerido_pesos is not None else None,
        )
        for c in CLUSTERS
    )


# --------------------------------------------------------------------------------------
# Validaciones. Cada una devuelve una `Validacion`; ninguna lanza por un dato malo (la
# pantalla las muestra todas). `exigir` convierte las que fallaron en una excepcion.
# --------------------------------------------------------------------------------------


class ValidacionFallida(Exception):
    """Alguna validacion no paso (se usa en scripts que deben parar)."""


@dataclass(frozen=True)
class Validacion:
    nombre: str
    ok: bool
    detalle: str
    datos: Mapping[str, object] = field(default_factory=dict)


def exigir(validaciones: Iterable[Validacion]) -> None:
    """Lanza `ValidacionFallida` con el nombre y el detalle de las que no pasaron."""
    malas = [v for v in validaciones if not v.ok]
    if malas:
        raise ValidacionFallida("; ".join(f"{v.nombre}: {v.detalle}" for v in malas))


def validar_acumulados(resultado: ResultadoClasificacion) -> Validacion:
    """Los acumulados de piezas y de valor cierran en 100% (con fracciones exactas).

    Comprueba, por metrica: los porcentajes suman exactamente 1, el acumulado nunca
    baja al avanzar en el ranking y el ultimo es exactamente 1. Sin productos
    clasificables no hay nada que cerrar y pasa. Con productos pero base sin ventas
    (total 0) falla: no se puede calcular ningun porcentaje.
    """
    base = resultado.por_estado(ESTADO_CLASIFICADO)
    nombre = "Los acumulados cierran en 100%"
    if not base:
        return Validacion(nombre, True, "no hay productos clasificables")
    problemas = []
    for etiqueta, ranking, pct, acum in (
        ("piezas", "ranking_piezas", "pct_unidades", "pct_acum_unidades"),
        ("valor", "ranking_valor", "pct_valor", "pct_acum_valor"),
    ):
        ordenados = sorted(base, key=lambda p: getattr(p, ranking))
        suma = sum((getattr(p, pct) for p in ordenados), CERO)
        ultimo = getattr(ordenados[-1], acum)
        sube = all(
            getattr(a, acum) <= getattr(b, acum) for a, b in zip(ordenados, ordenados[1:])
        )
        if suma != UNO:
            problemas.append(f"{etiqueta}: los porcentajes suman {float(suma):.6f} y no 1")
        if ultimo != UNO:
            problemas.append(f"{etiqueta}: el ultimo acumulado es {float(ultimo):.6f} y no 1")
        if not sube:
            problemas.append(f"{etiqueta}: el acumulado baja en algun punto del ranking")
    if problemas:
        return Validacion(nombre, False, "; ".join(problemas))
    return Validacion(nombre, True, f"piezas y valor cierran en 100% con {len(base)} productos")


def _participacion_por_clase(base, metrica: str, pct: str) -> dict[str, Fraction]:
    clase_attr = "clase_piezas" if metrica == "piezas" else "clase_valor"
    salida = {c: CERO for c in LETRAS}
    for p in base:
        salida[getattr(p, clase_attr)] += getattr(p, pct)
    return salida


def validar_proporciones(
    resultado: ResultadoClasificacion, tolerancia_pp: float = 10
) -> Validacion:
    """% de unidades y de valor por clase cerca de 80/15/5, con la desviacion a la vista.

    El objetivo sale de los cortes: A = corte A, B = corte B - corte A, C = 100 - corte B.
    `tolerancia_pp` son puntos porcentuales sobre la peor desviacion. Ojo: esta
    validacion se cumple casi por definicion (la regla ya parte el Pareto en esos
    cortes), asi que NO detecta datos malos; las de acumulados y de particion si.
    """
    nombre = "Proporciones por clase cerca de 80/15/5"
    base = resultado.por_estado(ESTADO_CLASIFICADO)
    if not base or resultado.total_unidades_base == 0 or resultado.total_valor_base == 0:
        return Validacion(nombre, True, "sin base clasificable para medir")
    ca = a_fraccion(resultado.parametros.corte_a_pct)
    cb = a_fraccion(resultado.parametros.corte_b_pct)
    objetivo = {"A": ca, "B": cb - ca, "C": 100 - cb}
    datos: dict[str, object] = {"objetivo_pct": {k: float(v) for k, v in objetivo.items()}}
    peor = CERO
    partes = []
    for metrica, pct in (("piezas", "pct_unidades"), ("valor", "pct_valor")):
        part = _participacion_por_clase(base, metrica, pct)
        real = {k: v * 100 for k, v in part.items()}
        desv = {k: real[k] - objetivo[k] for k in LETRAS}
        datos[f"real_pct_{metrica}"] = {k: round(float(v), 2) for k, v in real.items()}
        datos[f"desviacion_pp_{metrica}"] = {k: round(float(v), 2) for k, v in desv.items()}
        peor = max([peor] + [abs(v) for v in desv.values()])
        partes.append(
            f"{metrica}: "
            + " / ".join(f"{k} {float(real[k]):.1f}%" for k in LETRAS)
        )
    datos["desviacion_maxima_pp"] = round(float(peor), 2)
    ok = peor <= a_fraccion(tolerancia_pp)
    detalle = "; ".join(partes) + (
        f" (peor desviacion {float(peor):.1f} pp, tolerancia {tolerancia_pp} pp)"
    )
    return Validacion(nombre, ok, detalle, datos)


def contar_estados(resultado: ResultadoClasificacion) -> Validacion:
    """Cuantos productos hay en cada estado, con SIN MOVIMIENTO y NUEVO a la vista.

    Es informativa: siempre ok.
    """
    datos: dict[str, object] = {}
    partes = []
    for estado in ESTADOS:
        grupo = resultado.por_estado(estado)
        unidades = sum((p.unidades_ventana for p in grupo), CERO)
        datos[estado] = {"productos": len(grupo), "unidades": float(unidades)}
        partes.append(f"{estado}: {len(grupo)}")
    negativos = sum(
        1
        for p in resultado.por_estado(ESTADO_CLASIFICADO)
        if p.unidades_ventana <= 0 or p.valor_ventana <= 0
    )
    datos["clasificados_con_neto_no_positivo"] = negativos
    if negativos:
        partes.append(f"clasificados con neto total <= 0 (peso 0): {negativos}")
    return Validacion("Conteo por estado", True, "; ".join(partes), datos)


def validar_particion_unidades(
    resultado: ResultadoClasificacion, total_unidades_universo: object | None = None
) -> Validacion:
    """Unidades clasificadas + NUEVO + SIN MOVIMIENTO = unidades netas del universo.

    Sin `total_unidades_universo` solo comprueba que la suma de los tres grupos sea la
    de todos los productos (cada uno cae en un grupo, ninguno se pierde ni se cuenta
    dos veces). Con el total del Excel, comprueba que la clasificacion no perdio
    unidades respecto de la fuente: ESA es la prueba que detecta datos perdidos.
    """
    nombre = "Clasificadas + NUEVO + SIN MOVIMIENTO = total del universo"
    por_grupo = {
        e: sum((p.unidades_ventana for p in resultado.por_estado(e)), CERO) for e in ESTADOS
    }
    suma_grupos = sum(por_grupo.values(), CERO)
    suma_todos = sum((p.unidades_ventana for p in resultado.productos), CERO)
    esperado = a_fraccion(total_unidades_universo) if total_unidades_universo is not None else suma_todos
    ok = suma_grupos == esperado == suma_todos
    datos = {e: float(v) for e, v in por_grupo.items()}
    datos["total_esperado"] = float(esperado)
    datos["suma_grupos"] = float(suma_grupos)
    detalle = (
        f"clasificadas {float(por_grupo[ESTADO_CLASIFICADO]):g} + NUEVO {float(por_grupo[ESTADO_NUEVO]):g} "
        f"+ SIN MOVIMIENTO {float(por_grupo[ESTADO_SIN_MOVIMIENTO]):g} = {float(suma_grupos):g}; "
        f"esperado {float(esperado):g}"
    )
    return Validacion(nombre, ok, detalle, datos)


def validar_27_clusters(
    resultado: ResultadoClasificacion, resumen: Sequence[ResumenCluster] | None = None
) -> Validacion:
    """Las 27 celdas estan y suman el total de productos (y 100% de unidades y de valor)."""
    nombre = "Las 27 celdas suman el total de productos"
    resumen = tuple(resumen) if resumen is not None else resumen_por_cluster(resultado)
    problemas = []
    if tuple(r.cluster for r in resumen) != CLUSTERS:
        problemas.append("el resumen no trae exactamente los 27 clusters en orden")
    n_base = len(resultado.por_estado(ESTADO_CLASIFICADO))
    suma_n = sum(r.n_productos for r in resumen)
    if suma_n != n_base:
        problemas.append(f"las celdas suman {suma_n} productos y hay {n_base} clasificados")
    if n_base and resultado.total_unidades_base and sum((r.pct_unidades for r in resumen), CERO) != UNO:
        problemas.append("los % de unidades por cluster no suman 100%")
    if n_base and resultado.total_valor_base and sum((r.pct_valor for r in resumen), CERO) != UNO:
        problemas.append("los % de valor por cluster no suman 100%")
    vacios = sum(1 for r in resumen if r.n_productos == 0)
    if problemas:
        return Validacion(nombre, False, "; ".join(problemas))
    detalle = f"{suma_n} productos en 27 clusters ({vacios} vacios)"
    return Validacion(nombre, True, detalle, {"vacios": vacios})


def validar_sin_hijos_sueltos(
    codigos: Iterable[str],
    mapa_padre: Mapping[str, str],
    ambiguos: Iterable[str] = (),
    maximo_ejemplos: int = 20,
) -> Validacion:
    """Ningun codigo con padre vigente aparece suelto en la lista.

    `mapa_padre`: codigo -> codigo padre. Un HIJO es un codigo cuyo padre es otro; si
    aparece en la lista, sus ventas no se consolidaron (quedaron repartidas entre el
    viejo y el vigente y el producto sale mas chico de lo que es). Un codigo que no
    esta en el mapa es su propio padre. `ambiguos` son los codigos de los grupos que
    el motor deja sueltos a proposito (publicados en una lista) y no cuentan como falla.
    """
    nombre = "Ningun codigo con padre vigente aparece suelto"
    excusados = set(ambiguos)
    hijos = sorted(
        c for c in codigos if mapa_padre.get(c, c) != c and c not in excusados
    )
    if not hijos:
        return Validacion(nombre, True, "todos los codigos son padres o no tienen reemplazo")
    ejemplos = [f"{c} -> {mapa_padre[c]}" for c in hijos[:maximo_ejemplos]]
    return Validacion(
        nombre,
        False,
        f"{len(hijos)} codigos son hijos de otro y aparecen sueltos: " + "; ".join(ejemplos),
        {"cantidad": len(hijos), "ejemplos": ejemplos},
    )


def ejecutar_validaciones(
    resultado: ResultadoClasificacion,
    *,
    mapa_padre: Mapping[str, str] | None = None,
    ambiguos: Iterable[str] = (),
    total_unidades_universo: object | None = None,
    tolerancia_pp: float = 10,
) -> list[Validacion]:
    """Todas las validaciones de la clasificacion, en el orden en que se muestran."""
    validaciones = [
        validar_acumulados(resultado),
        validar_particion_unidades(resultado, total_unidades_universo),
        validar_27_clusters(resultado),
        validar_proporciones(resultado, tolerancia_pp),
        contar_estados(resultado),
    ]
    if mapa_padre is not None:
        validaciones.append(
            validar_sin_hijos_sueltos((p.codigo for p in resultado.productos), mapa_padre, ambiguos)
        )
    return validaciones
