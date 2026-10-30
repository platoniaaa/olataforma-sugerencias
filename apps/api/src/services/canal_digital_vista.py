"""Canal Digital: de una `Corrida` a lo que muestran la API y las pantallas (diccionarios simples)."""
from __future__ import annotations

from fractions import Fraction

from ..canal_digital.clasificacion import (
    ESTADO_CLASIFICADO, ESTADO_NUEVO, ESTADO_SIN_MOVIMIENTO, ejecutar_validaciones, resumen_por_cluster,
)
from ..canal_digital.corrida import Corrida, ProductoCalculado
from ..canal_digital.paso_a_paso import explicar_producto

MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def etiqueta_periodo(periodo: str) -> str:
    return f"{MESES[int(periodo[4:]) - 1]}-{periodo[2:4]}"


def _f(x) -> float | None:
    return None if x is None else float(x)


def fila_producto(pc: ProductoCalculado, corrida: Corrida) -> dict:
    d, r = pc.datos, pc.reposicion
    c = corrida.clasificacion.producto(d.codigo)
    return {
        "producto": d.codigo, "descripcion": d.descripcion, "codigos_vendidos": d.codigos_vendidos,
        "estado": c.estado, "cluster": c.cluster, "frecuencia": c.letra_frecuencia,
        "piezas": c.clase_piezas, "valor": c.clase_valor, "meses_con_venta": c.meses_con_venta,
        "unidades_12m": _f(c.unidades_ventana), "valor_12m": _f(c.valor_ventana),
        "primera_venta": c.primera_venta.isoformat() if c.primera_venta else None,
        "modo": r.modo, "nivel_servicio": r.nivel_servicio, "z": r.z,
        "demanda_semanal": r.demanda_semanal, "sigma_semanal": r.sigma_semanal,
        "plazo_dias": d.plazo_dias, "plazo_semanas": r.lead_time_semanas, "plazo_origen": d.plazo_origen,
        "plazo_confianza": d.plazo_confianza, "proveedor": d.proveedor,
        "stock_seguridad": r.stock_seguridad, "nivel_objetivo": r.nivel_objetivo,
        "stock_disponible": d.stock_disponible, "stock_aparte": d.stock_aparte, "stock_cd": d.stock_cd,
        "transito": d.transito, "transito_cualquier_destino": d.transito_cualquier_destino,
        "comprometido": r.comprometido_rotulo, "posicion": r.posicion,
        "necesidad_bruta": r.sugerido_bruto, "minimo_compra": r.minimo_compra, "multiplo": r.multiplo,
        "sugerido": r.sugerido, "costo_actual": d.costo_actual, "sugerido_pesos": pc.sugerido_pesos,
        "costo_respaldo": d.costo_respaldo, "motivo": r.motivo, "avisos": list(r.banderas),
    }


def validaciones(corrida: Corrida) -> list[dict]:
    """Las validaciones de la clasificacion, listas para mostrar (las usan el resumen y la pestana Datos)."""
    res = corrida.clasificacion
    total_u = sum((p.unidades_ventana for p in res.productos), Fraction(0))
    return [
        {"nombre": v.nombre, "ok": v.ok, "detalle": v.detalle}
        for v in ejecutar_validaciones(res, total_unidades_universo=total_u)
    ]


def _aviso_aparte(aviso: dict) -> list[str]:
    """El aviso de las bodegas que van aparte, con los nombres de ESTA bodega (cada una tiene las suyas). Sin ninguna
    bodega aparte no hay nada que avisar."""
    aparte = aviso.get("bodegas_aparte") or []
    if not aparte:
        return []
    return [
        f"Se muestran aparte y no suman al disponible: {', '.join(aparte)}. "
        "Si la venta sale de ahi, el sugerido sale inflado."
    ]


def resumen(corrida: Corrida, aviso: dict) -> dict:
    res = corrida.clasificacion
    por_cluster: dict[str, dict] = {}
    for pc in corrida.productos:
        c = res.producto(pc.datos.codigo)
        if c.estado != ESTADO_CLASIFICADO:
            continue
        a = por_cluster.setdefault(c.cluster, {"piden": 0, "unidades_sugeridas": 0.0})
        if pc.reposicion.sugerido > 0:
            a["piden"] += 1
            a["unidades_sugeridas"] += pc.reposicion.sugerido
    sug = corrida.sugerido_pesos()
    clusters = []
    for r in resumen_por_cluster(res, sug):
        f = corrida.politica.fila(r.cluster)
        clusters.append({
            "cluster": r.cluster, "frecuencia": r.cluster[0], "piezas": r.cluster[1], "valor": r.cluster[2],
            "productos": r.n_productos, "unidades_12m": float(r.unidades), "pct_unidades": float(r.pct_unidades),
            "valor_12m": float(r.valor), "pct_valor": float(r.pct_valor),
            "modo": f.modo, "nivel_servicio": f.nivel_servicio, "z": f.z, "minimo_fijo": f.minimo_fijo,
            "productos_que_piden": por_cluster.get(r.cluster, {}).get("piden", 0),
            "unidades_sugeridas": por_cluster.get(r.cluster, {}).get("unidades_sugeridas", 0.0),
            "sugerido_pesos": float(r.sugerido_pesos or 0),
        })
    estados = {e: len(res.por_estado(e)) for e in (ESTADO_CLASIFICADO, ESTADO_NUEVO, ESTADO_SIN_MOVIMIENTO)}
    piden = [p for p in corrida.productos if p.reposicion.sugerido > 0]
    return {
        "aviso": aviso, "estados": estados, "clusters": clusters,
        "totales": {
            "productos": len(corrida.productos), "productos_que_piden": len(piden),
            "unidades_sugeridas": sum(p.reposicion.sugerido for p in piden),
            "sugerido_pesos": sum(p.sugerido_pesos for p in piden),
        },
        "validaciones": validaciones(corrida),
        "provisorio": [
            "La politica de los 27 clusters son los valores del brief, sin confirmar.",
            "El comprometido no existe en el ERP (se muestra 0 sin dato); minimo y multiplo van en 1 por defecto.",
            "Los traslados desde el CD no figuran en ningun reporte: la posicion es stock mas transito de OC a la bodega.",
            *_aviso_aparte(aviso),
        ],
    }


def paso_a_paso(corrida: Corrida, codigo: str, periodos: list[str]) -> list[dict] | None:
    pc = corrida.por_codigo().get(codigo)
    if pc is None:
        return None
    pasos = explicar_producto(
        corrida.clasificacion, codigo, pc.reposicion, pc.fila_politica,
        etiquetas_meses=[etiqueta_periodo(p) for p in periodos],
    )
    return [
        {"numero": p.numero, "titulo": p.titulo, "formula": p.formula, "numeros": p.numeros, "resultado": p.resultado}
        for p in pasos
    ]
