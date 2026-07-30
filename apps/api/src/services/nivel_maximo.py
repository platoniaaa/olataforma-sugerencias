"""Reposicion al nivel maximo: que un SKU bajo su maximo se reponga SIEMPRE.

El problema que resuelve
------------------------
El modelo calcula un nivel de reposicion (`demanda diaria x (ciclo + lead time) +
stock de seguridad`) y pide la diferencia contra lo que ya hay. Pero esa diferencia
venia **redondeada**, y en un catalogo de baja rotacion casi siempre da menos de
media unidad: un SKU con nivel 1,42 y stock 1 necesita 0,42 -> redondeaba a 0 ->
"no compres". En el snapshot del 30-jul-2026 habia **11.953 filas** asi: bajo su
maximo y sugiriendo cero.

Ejemplo real (`13 C5TS7600B3`, Linderos, clase A):

    demanda diaria 0,053 · lead time 3 d · stock seguridad 1
    nivel = 0,053 x (5 + 3) + 1 = 1,42 · stock 1
    antes:  REDONDEO(1,42 - 1) = REDONDEO(0,42) = 0   -> no pedia nada
    ahora:  TECHO(1,42) - 1    = 2 - 1          = 1   -> pide 1

Las dos ideas del cambio
------------------------
1. **El nivel maximo es un entero.** "Mi maximo son 2 unidades", no 1,42. Es como
   piensa el comprador y ademas es auditable: se guarda en la columna
   `nivel_maximo` para poder leer "tengo 1 de 2, por eso pide 1".
2. **El faltante se pide completo**, sin umbral y sin redondeo que lo anule.

Se aplica como PISO
-------------------
`sugerido = max(sugerido del motor, nivel maximo - stock - transito)`. Nunca baja
un sugerido existente. Es deliberado: hay filas (demanda consolidada del CD,
aceites en mL) donde el motor llega a un numero mas alto por caminos que esta
reconstruccion no reproduce, y bajarlas seria dejar de comprar algo que si hace
falta. La regla solo puede agregar.

Alcance
-------
Lo controla `clases_que_reponen` en Configuracion:

- `"AB"` (default): solo clases de rotacion, mirando la clase local **o** la
  agregada. ~1.700 filas y ~$110M sobre el snapshot de jul-2026.
- `"ABCD"`: todas. Son ~12.300 filas y >$378M, porque para una clase D el nivel
  teorico es una fraccion de unidad y el techo lo convierte en 1: en la practica
  es "tener 1 unidad de todo", no "reponer al maximo". Por eso no es el default.

Ademas exige `demanda_diaria > 0`: sin demanda no hay nivel que mantener.
"""
from __future__ import annotations

import math
from typing import Any

CD = "CD REPUESTOS"
CLASES_ROTACION = {"A", "B"}


def _num(v: Any) -> float:
    """Valor numerico tolerante: None, "" y basura entran como 0."""
    if v is None or v == "":
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _es_si(v: Any) -> bool:
    return str(v or "").strip().lower() in ("si", "sí")


def _clase(fila: dict) -> str:
    return str(fila.get("clasificacion_abc") or "").strip().upper()


def _clase_agregada(fila: dict) -> str:
    return str(fila.get("clasificacion_abc_agregada") or "").strip().upper()


def _aplica_a(fila: dict, clases: str) -> bool:
    """La fila entra en la regla segun el parametro `clases_que_reponen`.

    Con "AB" basta con que la clase local **o** la agregada sea A/B: un repuesto
    que en la sucursal se mueve poco (D local) pero que la empresa vende harto
    (A agregada) se abastece igual via CD, y dejarlo fuera seria incoherente con
    como el modelo decide a quien le compra.
    """
    if clases == "ABCD":
        return True
    return _clase(fila) in CLASES_ROTACION or _clase_agregada(fila) in CLASES_ROTACION


def nivel_de(fila: dict, config: dict) -> int | None:
    """Nivel maximo entero de la fila. None si no hay demanda que sostener.

    El ciclo de orden depende de si la sucursal se abastece del CD o le compra
    directo al proveedor (hoy ambos son 5 dias, pero son dos perillas distintas
    en Configuracion y pueden separarse de nuevo).
    """
    dd = _num(fila.get("demanda_diaria"))
    if dd <= 0:
        return None
    lt = fila.get("lt_efectivo")
    if lt is None or lt == "":
        lt = fila.get("lead_time_dias")
    lt_num = (
        _num(lt) if lt is not None and lt != "" else float(config["lead_time_fallback_dias"])
    )
    co = (
        config["ciclo_orden_dias_cd"]
        if _es_si(fila.get("abastece_cd"))
        else config["ciclo_orden_dias"]
    )
    ss = _num(fila.get("stock_seguridad"))
    return max(0, math.ceil(dd * (co + lt_num) + ss))


def _prioridad(fila: dict) -> float:
    """Prioridad de reparto del CD. Sin prioridad -> al final de la fila."""
    p = fila.get("prioridad_cd")
    return _num(p) if p is not None and p != "" else math.inf


def _recalcular_cadena_cd(filas: list[dict]) -> None:
    """Rehace traslado / compra neta / comprar en el CD de UN producto.

    Hay que rehacerla entera y no solo la fila que cambio: el stock del CD se
    reparte por ranking de prioridad, asi que si una sucursal pide mas, a las de
    prioridad mas baja les queda menos disponible y su traslado cambia aunque su
    propio sugerido no se haya movido.
    """
    con_cd = sorted([f for f in filas if _es_si(f.get("abastece_cd"))], key=_prioridad)
    directas = [f for f in filas if not _es_si(f.get("abastece_cd"))]

    # Las que compran directo no tienen traslado: la compra neta es todo el sugerido.
    for f in directas:
        f["sugerido_traslado"] = None
        f["sugerido_compra_neto"] = _num(f.get("sugerido_suc"))

    if not con_cd:
        return

    stock_cd = max((_num(f.get("stock_en_cd")) for f in con_cd), default=0.0)
    acumulado = 0.0
    for f in con_cd:
        mio = _num(f.get("sugerido_suc"))
        # Disponible = lo que queda del CD despues de las sucursales que van antes.
        disponible = max(stock_cd - acumulado, 0.0)
        traslado = min(mio, disponible) if mio > 0 and stock_cd > 0 else 0.0
        acumulado += mio
        f["sugerido_traslado"] = float(int(traslado)) if traslado > 0 else None
        f["sugerido_compra_neto"] = mio - float(int(traslado))
        # El CD tiene que reponerse cuando la demanda acumulada hasta esta
        # sucursal (inclusive) supera lo que tiene en bodega.
        f["comprar_en_el_cd"] = "Si" if stock_cd <= 0 or acumulado > stock_cd else "No"


def _escribir_sugerido(fila: dict, sugerido: float) -> None:
    """Deja el sugerido y todo lo que se deriva de el en la fila."""
    fila["sugerido_suc"] = sugerido
    fila["total_sugerido_suc"] = sugerido
    costo = _num(fila.get("costo_unitario"))
    fila["total_valor_sugerido_clp"] = sugerido * costo if costo and sugerido > 0 else None
    fila["pedir"] = "Si" if sugerido > 0 else "No"
    fila["pedir_flag"] = fila["pedir"]


def aplicar(filas: list[dict], config: dict) -> dict:
    """Repone al nivel maximo sobre las filas ya mapeadas de la carga.

    Muta `filas` in-place y devuelve un resumen para el log y la auditoria de la
    carga. `config` es lo que entrega `config_modelo_service.vigente()`.

    Escribe `nivel_maximo` en TODAS las filas con demanda, aunque la regla este
    apagada o la fila quede fuera por su clase: es informacion util por si sola
    (deja ver a que nivel apunta cada SKU) y no cambia ninguna decision.
    """
    resumen = {
        "activa": bool(config.get("reponer_a_maximo")),
        "clases": str(config.get("clases_que_reponen") or "AB"),
        "filas_evaluadas": 0,
        "filas_nuevas": 0,      # sugerian 0 y ahora piden algo
        "filas_que_suben": 0,   # ya sugerian y ahora piden mas
        "unidades_extra": 0.0,
        "clp_extra": 0.0,
    }
    if not filas:
        return resumen

    clases = resumen["clases"]
    activa = resumen["activa"]
    productos_tocados: set[str] = set()

    for fila in filas:
        nivel = nivel_de(fila, config)
        if nivel is None:
            continue
        fila["nivel_maximo"] = nivel
        resumen["filas_evaluadas"] += 1
        if not activa or not _aplica_a(fila, clases):
            continue

        actual = _num(fila.get("total_sugerido_suc"))
        cubierto = _num(fila.get("stock_activo_suc")) + _num(fila.get("stock_en_transito_suc"))
        faltante = max(0.0, nivel - cubierto)
        # Piso: la regla solo agrega, nunca recorta lo que el motor ya pedia.
        if faltante <= actual:
            continue

        extra = faltante - actual
        resumen["filas_nuevas" if actual <= 0 else "filas_que_suben"] += 1
        resumen["unidades_extra"] += extra
        resumen["clp_extra"] += extra * _num(fila.get("costo_unitario"))
        _escribir_sugerido(fila, faltante)
        if fila.get("producto"):
            productos_tocados.add(str(fila["producto"]))

    # La cadena del CD se rehace solo en los productos que efectivamente cambiaron:
    # en el resto se conservan tal cual los numeros del motor.
    if productos_tocados:
        por_producto: dict[str, list[dict]] = {}
        for fila in filas:
            p = str(fila.get("producto") or "")
            if p in productos_tocados:
                por_producto.setdefault(p, []).append(fila)
        for grupo in por_producto.values():
            _recalcular_cadena_cd(grupo)

    resumen["unidades_extra"] = round(resumen["unidades_extra"], 2)
    resumen["clp_extra"] = round(resumen["clp_extra"])
    return resumen
