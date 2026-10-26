"""El paso a paso de un producto: de sus ventas al sugerido, en frases que se leen solas.

Sirve para que el dueno (y quien audite) siga UN producto de punta a punta con sus
numeros reales: cada paso trae la formula, los numeros puestos en ella y el resultado.
No calcula nada nuevo: solo cuenta lo que ya calcularon `clasificar` y
`calcular_reposicion`, de modo que si el texto y la planilla discrepan, el error esta
en el calculo y no en la explicacion.

Funcion PURA: no modifica lo que recibe. Los numeros salen en formato chileno
(punto de mil, coma decimal).
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Sequence

from .clasificacion import (
    ESTADO_CLASIFICADO,
    ESTADO_NUEVO,
    ESTADO_SIN_MOVIMIENTO,
    ClasificacionProducto,
    ResultadoClasificacion,
)
from .numeros import restar_meses
from .politica import MODO_CONTRA_PEDIDO, MODO_FORMULA, MODO_MINIMO_FIJO, FilaPolitica
from .reposicion import (
    BANDERA_COMPROMETIDO_SIN_DATO,
    BANDERA_HISTORIA_CORTA,
    BANDERA_MINIMO_POR_DEFECTO,
    BANDERA_MUESTRA_INSUFICIENTE,
    BANDERA_MULTIPLO_POR_DEFECTO,
    ResultadoReposicion,
)


def num(valor, decimales: int = 2) -> str:
    """Numero en formato chileno: 1234.5 -> '1.234,5'; 12.3456 -> '12,35'.

    Redondea a `decimales` y quita los ceros que sobran: un entero no lleva decimales.
    """
    if isinstance(valor, Fraction):
        valor = float(valor)
    if float(valor).is_integer():
        texto = f"{int(valor):,}"
    else:
        texto = f"{valor:,.{decimales}f}"
        if "." in texto:
            texto = texto.rstrip("0").rstrip(".")
        if texto == "-0":  # -0,001 redondeado a 2 decimales
            texto = "0"
    return texto.replace(",", "\0").replace(".", ",").replace("\0", ".")


def pct(fraccion: Fraction, decimales: int = 1) -> str:
    """Fraccion 0-1 como porcentaje: Fraction(78, 100) -> '78,0%'."""
    return f"{float(fraccion) * 100:.{decimales}f}".replace(".", ",") + "%"


def _u(valor) -> str:
    """'1 unidad' o '12 unidades' (el singular solo para exactamente 1)."""
    return "1 unidad" if float(valor) == 1 else f"{num(valor)} unidades"


def pesos(valor) -> str:
    """Monto en pesos: 1234567 -> '$ 1.234.567'."""
    return "$ " + num(round(float(valor)), 0)


@dataclass(frozen=True)
class Paso:
    """Un paso del recorrido: que se hace (titulo), con que formula, con que numeros y que da."""

    numero: int
    titulo: str
    formula: str
    numeros: str
    resultado: str

    def texto(self) -> str:
        return (
            f"Paso {self.numero}. {self.titulo}\n"
            f"  Fórmula: {self.formula}\n"
            f"  Con los números: {self.numeros}\n"
            f"  Resultado: {self.resultado}"
        )


def texto_completo(pasos: Sequence[Paso]) -> str:
    """Todos los pasos como un solo texto, separados por una linea en blanco."""
    return "\n\n".join(p.texto() for p in pasos)


def _meses(clasif: ClasificacionProducto, etiquetas: Sequence[str] | None) -> str:
    n = len(clasif.unidades_mes)
    if etiquetas is None:
        etiquetas = [f"mes {i}" for i in range(1, n + 1)]
    elif len(etiquetas) != n:
        raise ValueError(f"se esperaban {n} etiquetas de mes y llegaron {len(etiquetas)}")
    return "; ".join(f"{e}: {num(u)}" for e, u in zip(etiquetas, clasif.unidades_mes))


def _textos_pareto(
    metrica: str,
    total_base,
    n_base: int,
    corte_a,
    corte_b,
    lugar: int,
    valor,
    participacion: Fraction,
    acumulado_con: Fraction,
    clase: str,
    formato,
) -> tuple[str, str, str]:
    """(formula, numeros, resultado) de un Pareto; el acumulado ANTES es el que decide la letra."""
    antes = acumulado_con - participacion
    ca, cb = num(float(corte_a), 1), num(float(corte_b), 1)
    if clase == "A":
        razon = f"{pct(antes)} es menor que {ca}%"
    elif clase == "B":
        razon = f"{pct(antes)} no es menor que {ca}%, pero sí menor que {cb}%"
    else:
        razon = f"{pct(antes)} no es menor que {cb}%"
    return (
        f"Se ordenan los {n_base} productos clasificables de mayor a menor {metrica}. "
        f"La letra se decide por el acumulado ANTES del producto: A si es menor que {ca}%, "
        f"B si es menor que {cb}%, C el resto.",
        f"{metrica.capitalize()} del producto en la ventana: {formato(valor)} de {formato(total_base)} "
        f"en total. Lugar {lugar} de {n_base}. Aporta {pct(participacion)}. "
        f"Acumulado antes de él: {pct(antes)}; con él: {pct(acumulado_con)}.",
        f"Letra {clase}, porque {razon}.",
    )


def explicar_producto(
    clasificacion: ResultadoClasificacion,
    codigo: str,
    reposicion: ResultadoReposicion,
    fila_politica: FilaPolitica | None,
    *,
    etiquetas_meses: Sequence[str] | None = None,
) -> list[Paso]:
    """Los pasos de un producto, en el orden en que se calculan.

    `clasificacion` es el resultado de `clasificar` (trae los totales del Pareto),
    `reposicion` el de `calcular_reposicion` para el mismo codigo y `fila_politica` la
    fila de su cluster (None si es NUEVO o SIN MOVIMIENTO). `etiquetas_meses`
    (opcional) son los nombres de los meses de la ventana, del mas antiguo al mas
    reciente, por ejemplo ["oct-25", ..., "sep-26"].
    """
    if reposicion.codigo != codigo:
        raise ValueError(
            f"el resultado de reposicion es de {reposicion.codigo!r} y no de {codigo!r}"
        )
    c = clasificacion.producto(codigo)
    prm = clasificacion.parametros
    pasos: list[Paso] = []

    def agregar(titulo, formula, numeros, resultado):
        pasos.append(Paso(len(pasos) + 1, titulo, formula, numeros, resultado))

    # 1. Frecuencia
    agregar(
        "Frecuencia de venta",
        f"Frecuencia = meses con venta neta mayor que 0 en los últimos {prm.ventana_meses} meses. "
        f"A: {prm.frecuencia_a_min} a {prm.ventana_meses}; B: {prm.frecuencia_b_min} a "
        f"{prm.frecuencia_a_min - 1}; C: 1 a {prm.frecuencia_b_min - 1}; 0 = SIN MOVIMIENTO.",
        f"Unidades netas por mes: {_meses(c, etiquetas_meses)}. "
        f"Meses con neto mayor que 0: {c.meses_con_venta} de {prm.ventana_meses}.",
        "SIN MOVIMIENTO: no vendió nada neto en la ventana, queda fuera de los clusters."
        if c.estado == ESTADO_SIN_MOVIMIENTO
        else f"Frecuencia {c.letra_frecuencia}.",
    )

    # 2. Producto nuevo
    limite = restar_meses(clasificacion.fecha_referencia, prm.nuevo_meses)
    if c.estado == ESTADO_SIN_MOVIMIENTO:
        agregar(
            "Producto nuevo",
            f"NUEVO si la primera venta en la empresa es posterior al {limite.isoformat()} "
            f"(menos de {prm.nuevo_meses} meses al {clasificacion.fecha_referencia.isoformat()}).",
            "No se evalúa: el producto no tiene ventas netas en la ventana.",
            "No aplica.",
        )
    else:
        primera = c.primera_venta.isoformat() if c.primera_venta else "no se conoce"
        agregar(
            "Producto nuevo",
            f"NUEVO si la primera venta en la empresa es posterior al {limite.isoformat()} "
            f"(menos de {prm.nuevo_meses} meses al {clasificacion.fecha_referencia.isoformat()}).",
            f"Primera venta en la empresa: {primera}.",
            "NUEVO: no se clasifica todavía, le falta historia." if c.estado == ESTADO_NUEVO
            else "No es nuevo: se clasifica.",
        )

    # Productos sin cluster: aqui termina el recorrido.
    if c.estado != ESTADO_CLASIFICADO:
        agregar(
            "Sugerido",
            "Sin cluster no hay política: el sugerido es 0.",
            f"Estado: {c.estado}.",
            "Sugerido: 0 unidades.",
        )
        return pasos

    # 3 y 4. Pareto de piezas y de valor
    agregar(
        "Pareto de piezas",
        *_textos_pareto(
            "unidades vendidas", clasificacion.total_unidades_base, clasificacion.n_base,
            prm.corte_a_pct, prm.corte_b_pct,
            c.ranking_piezas, c.unidades_ventana, c.pct_unidades, c.pct_acum_unidades,
            c.clase_piezas, num,
        ),
    )
    agregar(
        "Pareto de valor",
        *_textos_pareto(
            "valor vendido", clasificacion.total_valor_base, clasificacion.n_base,
            prm.corte_a_pct, prm.corte_b_pct,
            c.ranking_valor, c.valor_ventana, c.pct_valor, c.pct_acum_valor,
            c.clase_valor, pesos,
        ),
    )

    # 5. Cluster y politica
    if fila_politica is None:
        raise ValueError(f"{codigo!r}: un producto clasificado necesita su fila de política")
    if fila_politica.modo == MODO_FORMULA:
        politica_txt = (
            f"modo fórmula, nivel de servicio {pct(fila_politica.nivel_servicio, 0)}, "
            f"z = {num(fila_politica.z)}"
        )
    elif fila_politica.modo == MODO_CONTRA_PEDIDO:
        politica_txt = "modo contra pedido (no se repone por pronóstico: el sugerido es 0)"
    else:
        politica_txt = (
            f"modo mínimo fijo de {num(fila_politica.minimo_fijo)} "
            "(se pide solo cuando la posición es 0 o menos)"
        )
    agregar(
        "Cluster y política",
        "Cluster = letra de Frecuencia + letra de Piezas + letra de Valor; la política "
        "de la bodega dice cómo se repone ese cluster.",
        f"{c.letra_frecuencia} + {c.clase_piezas} + {c.clase_valor}.",
        f"Cluster {c.cluster}: {politica_txt}.",
    )

    r = reposicion
    # 6 y 7. Demanda y variabilidad (se muestran siempre; en contra pedido y minimo fijo son referencia)
    historia = (
        f" Ojo: solo hay {r.semanas_usadas} semanas de historia (menos de la ventana completa)."
        if BANDERA_HISTORIA_CORTA in r.banderas
        else ""
    )
    agregar(
        "Demanda semanal (D)",
        "D = suma de las unidades netas de las semanas / número de semanas.",
        f"{num(r.suma_serie)} unidades / {r.semanas_usadas} semanas.{historia}",
        f"D = {num(r.demanda_semanal)} unidades por semana.",
    )
    criterio = "muestral (divide por n - 1)" if r.ddof == 1 else f"con ddof = {r.ddof}"
    sigma_txt = f"sigma = {num(r.sigma_semanal)} unidades por semana."
    if BANDERA_MUESTRA_INSUFICIENTE in r.banderas:
        sigma_txt += " No se puede estimar con tan pocas semanas: se usa 0."
    agregar(
        "Variabilidad semanal (sigma)",
        f"sigma = raíz( suma de (unidades de la semana - D)² / (n - {r.ddof}) ), "
        f"desviación estándar {criterio}.",
        f"n = {r.semanas_usadas} semanas, D = {num(r.demanda_semanal)}.",
        sigma_txt,
    )

    # 8. Plazos
    agregar(
        "Plazos (L y R)",
        "L = lead time del proveedor en semanas (días / 7); R = semanas entre revisiones; "
        "la reposición debe cubrir L + R.",
        f"L = {num(r.lead_time_semanas)} semanas ({r.origen_lead_time}); "
        f"R = {num(r.r_semanas)} semana(s).",
        f"L + R = {num(r.horizonte_semanas)} semanas.",
    )

    if fila_politica.modo == MODO_FORMULA:
        agregar(
            "Stock de seguridad (SS)",
            "SS = z × sigma × raíz(L + R).",
            f"{num(r.z)} × {num(r.sigma_semanal)} × raíz({num(r.horizonte_semanas)}).",
            f"SS = {_u(r.stock_seguridad)}.",
        )
        agregar(
            "Nivel objetivo (S)",
            "S = D × (L + R) + SS.",
            f"{num(r.demanda_semanal)} × {num(r.horizonte_semanas)} + {num(r.stock_seguridad)}.",
            f"S = {_u(r.nivel_objetivo)}.",
        )

    comprometido_txt = f"{num(r.comprometido)}"
    if BANDERA_COMPROMETIDO_SIN_DATO in r.banderas:
        comprometido_txt += " (sin dato: se asume 0)"
    agregar(
        "Posición de inventario",
        "Posición = stock disponible + en tránsito - comprometido.",
        f"{num(r.stock_disponible)} + {num(r.en_transito)} - {comprometido_txt}.",
        f"Posición = {_u(r.posicion)}.",
    )

    if fila_politica.modo == MODO_FORMULA:
        agregar(
            "Necesidad",
            "Necesidad = mayor entre 0 y (S - posición).",
            f"S - posición = {num(r.nivel_objetivo)} - {num(r.posicion)} = "
            f"{num(r.nivel_objetivo - r.posicion)}.",
            f"Necesidad = {_u(r.sugerido_bruto)}.",
        )
    elif fila_politica.modo == MODO_MINIMO_FIJO:
        agregar(
            "Necesidad",
            "Mínimo fijo: se pide el mínimo solo si la posición es 0 o menos.",
            f"Posición = {num(r.posicion)}; mínimo fijo = {num(r.minimo_fijo)}.",
            f"Necesidad = {_u(r.sugerido_bruto)}.",
        )
    else:
        agregar(
            "Necesidad",
            "Contra pedido: no se repone por pronóstico.",
            f"Posición = {num(r.posicion)}.",
            "Necesidad = 0 unidades.",
        )

    # Redondeo
    por_defecto = " (por defecto, sin dato cargado)"
    minimo_txt = num(r.minimo_compra) + (por_defecto if BANDERA_MINIMO_POR_DEFECTO in r.banderas else "")
    multiplo_txt = num(r.multiplo) + (por_defecto if BANDERA_MULTIPLO_POR_DEFECTO in r.banderas else "")
    agregar(
        "Redondeo a mínimo y múltiplo",
        "Se pide el menor múltiplo que sea mayor o igual que el mayor entre la necesidad y el "
        "mínimo de compra; si no hay necesidad, 0.",
        f"Necesidad {num(r.sugerido_bruto)}; mínimo de compra {minimo_txt}; múltiplo {multiplo_txt}.",
        f"{_u(r.sugerido)}.",
    )

    agregar(
        "Sugerido",
        "Sugerido = cantidad redondeada del paso anterior.",
        f"Motivo: {r.motivo}.",
        f"Sugerido: {_u(r.sugerido)}.",
    )
    return pasos
