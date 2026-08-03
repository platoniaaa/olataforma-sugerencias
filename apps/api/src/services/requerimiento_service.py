"""Requerimiento de sucursal: pegar una lista de codigos y decidir rapido.

El vendedor de una sucursal le manda al comprador una lista de repuestos con sus
cantidades. Antes de la plataforma el comprador la pegaba en un Excel que le
llenaba solo el contexto (stock, frecuencia de venta, reemplazo) y le armaba el
archivo para subir al portal del proveedor. Esto reemplaza ese Excel.

La idea de diseno es POKA-YOKE: que el error no pueda ocurrir, en vez de avisarlo.

- Se pega como venga. Tabulacion, coma, punto y coma o espacios; con encabezado o
  sin el; con cantidad o sin ella. No hay formato que aprenderse.
- El codigo de Curifor trae un rubro con espacio ("70 2723982") y ademas hay
  codigos que son puros numeros, asi que "codigo espacio numero" es ambiguo. En
  vez de adivinar con una regla, se pregunta al catalogo cual de las dos lecturas
  existe de verdad.
- La sucursal se elige UNA vez, no por linea.
- Lo que no se puede comprar no se puede seleccionar.

Estados de una linea:
  `en_sugerido`   el modelo ya lo pide en esa sucursal: hay frecuencia y clase.
  `sin_venta_local` existe, pero nunca se vendio en esa sucursal en 12 meses. No
                  es un error: es la respuesta. Si se vende en otra, se muestra.
  `no_existe`     no esta en ninguna parte. Error de tipeo.
"""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import ProductoCatalogo, Sugerido
from . import sugerido_service

# Separadores explicitos: cuando aparece uno, la lectura es inequivoca.
_SEPARADORES = re.compile(r"[\t;,|]")
# Cantidad: entero o decimal, con separador de miles opcional.
_NUMERO = re.compile(r"^\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?$|^\d+(?:[.,]\d+)?$")

# Palabras que delatan una fila de encabezado pegada sin querer.
_ENCABEZADOS = {"codigo", "código", "producto", "sku", "cantidad", "cant", "cant.",
                "descripcion", "descripción", "item", "linea", "línea"}


def _a_numero(s: str) -> float | None:
    s = s.strip()
    if not _NUMERO.match(s):
        return None
    # "1.234" son mil doscientos treinta y cuatro; "1,5" es uno coma cinco.
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif s.count(".") == 1 and len(s.split(".")[1]) == 3:
        s = s.replace(".", "")
    elif s.count(",") == 1 and len(s.split(",")[1]) == 3:
        s = s.replace(",", "")
    else:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _candidatos(linea: str) -> list[tuple[str, float | None]]:
    """Lecturas posibles de una linea, de la mas confiable a la menos.

    Con separador explicito hay una sola. Con espacios hay dos: que el ultimo
    token sea la cantidad, o que sea parte del codigo ("70 2723982").
    """
    linea = linea.strip()
    if not linea:
        return []
    if _SEPARADORES.search(linea):
        partes = [p.strip() for p in _SEPARADORES.split(linea) if p.strip()]
        if not partes:
            return []
        if len(partes) == 1:
            return [(partes[0], None)]
        # El codigo es la primera parte; la cantidad, la primera que sea numero.
        cantidad = next((_a_numero(p) for p in partes[1:] if _a_numero(p) is not None), None)
        return [(partes[0], cantidad)]

    tokens = linea.split()
    if len(tokens) == 1:
        return [(tokens[0], None)]
    ultimo = _a_numero(tokens[-1])
    lecturas: list[tuple[str, float | None]] = []
    if ultimo is not None:
        # Lectura A: el ultimo token es la cantidad.
        lecturas.append((" ".join(tokens[:-1]), ultimo))
    # Lectura B: toda la linea es el codigo (caso "70 2723982").
    lecturas.append((linea, None))
    return lecturas


def parsear(db: Session, texto: str) -> list[dict]:
    """Texto pegado -> lineas (producto, cantidad), resolviendo la ambiguedad.

    Se hace en dos pasadas: primero se juntan TODAS las lecturas posibles y se
    pregunta al catalogo cuales existen, y despues se elige. Asi el desempate lo
    decide el dato y no una regla que va a fallar con el proximo codigo raro.
    """
    lineas_texto = [l for l in (texto or "").splitlines() if l.strip()]
    por_linea = [_candidatos(l) for l in lineas_texto]

    posibles = {c for cands in por_linea for c, _ in cands}
    existentes = _cuales_existen(db, posibles)

    salida: list[dict] = []
    for texto_linea, cands in zip(lineas_texto, por_linea):
        if not cands:
            continue
        if texto_linea.strip().lower().split()[0] in _ENCABEZADOS and not any(
            c in existentes for c, _ in cands
        ):
            continue  # fila de encabezado pegada sin querer
        elegido = next((c for c in cands if c[0] in existentes), cands[0])
        salida.append({
            "producto": elegido[0].strip(),
            "cantidad": elegido[1],
            "texto_original": texto_linea.strip(),
        })
    return salida


def _cuales_existen(db: Session, codigos: set[str]) -> set[str]:
    """De una lista de codigos candidatos, cuales existen en Curifor."""
    codigos = {c for c in codigos if c}
    if not codigos:
        return set()
    encontrados: set[str] = set()
    for modelo, col in ((Sugerido, Sugerido.producto), (ProductoCatalogo, ProductoCatalogo.producto)):
        try:
            encontrados |= {
                p for (p,) in db.execute(select(col).where(col.in_(codigos)).distinct()).all()
            }
        except Exception:  # noqa: BLE001 - una tabla ausente no puede voltear el parseo
            db.rollback()
    return encontrados


def _frecuencia_otras_sucursales(db: Session, productos: set[str], sucursal_id: str) -> dict:
    """Para los que no se venden en la sucursal pedida: donde SI se venden.

    Devuelve, por producto, la sucursal con mas meses de venta en 12m. Es lo que
    convierte un "no hay dato" en algo accionable: "aca nunca, en Curico 7 de 12".
    """
    if not productos:
        return {}
    filas = db.execute(
        select(
            Sugerido.producto, Sugerido.sucursal_id, Sugerido.nombre_sucursal,
            Sugerido.meses_con_venta_12m, Sugerido.clasificacion_abc,
        ).where(
            Sugerido.producto.in_(productos),
            Sugerido.sucursal_id != sucursal_id,
            Sugerido.meses_con_venta_12m.isnot(None),
            Sugerido.meses_con_venta_12m > 0,
        )
    ).all()
    mejor: dict[str, dict] = {}
    for prod, suc, nombre, m12, abc in filas:
        actual = mejor.get(prod)
        if actual is None or (m12 or 0) > actual["meses_con_venta_12m"]:
            mejor[prod] = {
                "sucursal_id": suc,
                "nombre_sucursal": nombre or suc,
                "meses_con_venta_12m": m12 or 0,
                "clasificacion_abc": abc,
            }
    return mejor


def _stock_nacional(db: Session, productos: set[str]) -> dict[str, float]:
    """Stock total del producto en TODA la empresa (todas las bodegas)."""
    if not productos:
        return {}
    from ..models import StockUnificado

    try:
        filas = db.execute(
            select(StockUnificado.producto, func.sum(StockUnificado.stock))
            .where(StockUnificado.producto.in_(productos))
            .group_by(StockUnificado.producto)
        ).all()
        return {p: float(t or 0) for p, t in filas}
    except Exception:  # noqa: BLE001 - tabla ausente en un deploy nuevo
        db.rollback()
        return {}


def analizar(db: Session, sucursal_id: str, lineas: list[dict]) -> dict:
    """Enriquece cada linea con lo necesario para decidir comprar o no."""
    if not lineas:
        return {"lineas": [], "resumen": {"total": 0, "en_sugerido": 0,
                                          "sin_venta_local": 0, "no_existe": 0,
                                          "duplicados": 0}}

    productos = [str(l.get("producto") or "").strip() for l in lineas]
    pares = [(p, sucursal_id) for p in productos]
    contexto = sugerido_service.contexto_de_pares(db, pares)

    # Fila propia del sugerido (la que trae frecuencia y clase de ESTA sucursal).
    propias = {
        (s.producto, s.sucursal_id): s
        for s in sugerido_service._filas_de_pares(db, set(pares))
    }
    existen = _cuales_existen(db, set(productos))
    sin_local = {p for p in productos if (p, sucursal_id) not in propias and p in existen}
    otras = _frecuencia_otras_sucursales(db, sin_local, sucursal_id)
    nacional = _stock_nacional(db, set(productos))

    vistos: dict[str, int] = {}
    salida: list[dict] = []
    for i, (linea, ctx) in enumerate(zip(lineas, contexto)):
        prod = productos[i]
        propia = propias.get((prod, sucursal_id))
        if prod not in existen:
            estado = "no_existe"
        elif propia is not None:
            estado = "en_sugerido"
        else:
            estado = "sin_venta_local"

        vistos[prod] = vistos.get(prod, 0) + 1
        fila: dict[str, Any] = {
            "producto": prod,
            "texto_original": linea.get("texto_original"),
            "cantidad": linea.get("cantidad"),
            "estado": estado,
            "duplicado": vistos[prod] > 1,
            "descripcion": ctx.get("descripcion"),
            "proveedor": ctx.get("proveedor"),
            "costo_unitario": ctx.get("costo_unitario"),
            "reemplazos": ctx.get("reemplazos"),
            "nombre_sucursal": ctx.get("nombre_sucursal"),
            # Stock: el de la sucursal sale del mismo camino que la grilla.
            "stock_sucursal": ctx.get("stock_activo_suc"),
            "stock_nacional": nacional.get(prod),
            # Frecuencia de ESTA sucursal (solo si el modelo la tiene).
            "meses_con_venta_3m": propia.meses_con_venta_3m if propia else None,
            "meses_con_venta_6m": propia.meses_con_venta_6m if propia else None,
            "meses_con_venta_12m": propia.meses_con_venta_12m if propia else None,
            "clasificacion_abc": (propia.clasificacion_abc if propia
                                  else ctx.get("clasificacion_abc")),
            "stock_cd": propia.stock_en_cd if propia else None,
            "total_sugerido_suc": propia.total_sugerido_suc if propia else None,
            # Cuando no se vende aca, donde SI se vende.
            "frecuencia_otra_sucursal": otras.get(prod),
        }
        salida.append(fila)

    return {
        "lineas": salida,
        "resumen": {
            "total": len(salida),
            "en_sugerido": sum(1 for f in salida if f["estado"] == "en_sugerido"),
            "sin_venta_local": sum(1 for f in salida if f["estado"] == "sin_venta_local"),
            "no_existe": sum(1 for f in salida if f["estado"] == "no_existe"),
            "duplicados": sum(1 for f in salida if f["duplicado"]),
        },
    }
