"""Carga masiva de sugerencias manuales pegando una lista.

La masiva que ya existia trabaja por FILTROS: se elige un criterio y un numero, y
se aplica igual a todos los pares que cumplen. Sirve para "a todos los A de
Linderos, 30 dias", pero no para una lista armada a mano donde cada linea lleva
lo suyo. Eso es lo que resuelve este modulo.

Formato esperado (lo que sale de copiar un rango de Excel, separado por TAB):

    producto        sucursal    unidades    dias    mantener
    25 DG9Z8100A    LINDEROS    5
    20 BXO5W30BA    CURICO                  30
    13 C5TS7600B3   TALCA                           12

Las tres columnas de cantidad son excluyentes por linea. Si una trae mas de una,
manda `mantener` > `dias` > `unidades`: es el MISMO orden que aplica el modal por
filtros, para no tener dos reglas que explicar (decision de Ignacio Calderon,
09-08-2026).

El encabezado es opcional: si la primera linea trae nombres conocidos se usa para
mapear las columnas (asi da igual el orden en que esten), y si no, se asume el
orden de arriba.
"""
from __future__ import annotations

import re
import unicodedata

# Excel pega con TAB. Se aceptan los otros por si alguien arma la lista a mano.
_SEPARADORES = re.compile(r"[\t;|]")

# Nombre de columna -> campo. Se compara sin tildes, en minuscula y sin espacios.
_ALIAS = {
    "producto": "producto", "codigo": "producto", "sku": "producto",
    "item": "producto", "repuesto": "producto",
    "sucursal": "sucursal", "sucursalid": "sucursal", "local": "sucursal",
    "tienda": "sucursal", "bodega": "sucursal",
    "unidades": "unidades", "cantidad": "unidades", "cant": "unidades",
    "u": "unidades", "qty": "unidades",
    "dias": "dias", "diasinventario": "dias", "cobertura": "dias",
    "diasdecobertura": "dias", "diascobertura": "dias",
    "mantener": "mantener", "mantenerstock": "mantener", "stockobjetivo": "mantener",
    "objetivo": "mantener", "nivel": "mantener", "nivelobjetivo": "mantener",
}

_ORDEN_POR_DEFECTO = ["producto", "sucursal", "unidades", "dias", "mantener"]


def _normalizar(s: str) -> str:
    """'Días de cobertura' -> 'diasdecobertura'."""
    sin_tilde = "".join(
        c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"[^a-z0-9]", "", sin_tilde.lower())


def _entero(s: str) -> int | None:
    """Entero tolerante: acepta '1.234', '1,234' y vacio. None si no es numero.

    Solo enteros: ni las unidades, ni los dias, ni un nivel de stock admiten
    medias unidades, y aceptar 2,5 obligaria a decidir si redondea para arriba o
    para abajo en cada uno.
    """
    s = (s or "").strip().replace(".", "").replace(",", "")
    if not s or not s.lstrip("-").isdigit():
        return None
    return int(s)


def _mapa_columnas(partes: list[str]) -> dict[str, int] | None:
    """Si la fila es un encabezado conocido, devuelve {campo: indice}."""
    mapa: dict[str, int] = {}
    for i, p in enumerate(partes):
        campo = _ALIAS.get(_normalizar(p))
        if campo and campo not in mapa:
            mapa[campo] = i
    # Producto solo no basta: "25 DG9Z8100A" en la primera celda no es encabezado.
    return mapa if "producto" in mapa and len(mapa) >= 2 else None


def parsear(texto: str) -> dict:
    """Texto pegado -> {filas, errores, encabezado_detectado}.

    Cada fila valida: {producto, sucursal, unidades, dias, mantener, criterio}.
    `criterio` ya viene resuelto ('mantener' | 'dias' | 'unidades'), asi que quien
    la use no tiene que repetir la regla de prioridad.

    Los errores no abortan la carga: se devuelven con su numero de linea para que
    la vista previa los muestre y el usuario decida. Una lista de 200 lineas con 3
    malas no puede obligar a empezar de nuevo.
    """
    filas: list[dict] = []
    errores: list[dict] = []
    lineas = [l for l in (texto or "").splitlines()]
    mapa: dict[str, int] | None = None
    encabezado = False

    for n, linea in enumerate(lineas, start=1):
        if not linea.strip():
            continue
        partes = [p.strip() for p in _SEPARADORES.split(linea)]
        # Sin separador explicito no se puede saber donde termina el codigo: los
        # de Curifor traen espacios adentro ("70 2723982").
        if len(partes) < 2:
            errores.append({
                "linea": n, "texto": linea.strip(),
                "error": "La línea no trae columnas separadas. Pega desde Excel o "
                         "separa con tabulaciones, punto y coma o barra.",
            })
            continue

        if mapa is None and not filas:
            detectado = _mapa_columnas(partes)
            if detectado:
                mapa, encabezado = detectado, True
                continue
            mapa = {c: i for i, c in enumerate(_ORDEN_POR_DEFECTO)}

        def col(campo: str) -> str:
            i = (mapa or {}).get(campo)
            return partes[i] if i is not None and i < len(partes) else ""

        producto = col("producto").strip()
        sucursal = col("sucursal").strip()
        if not producto:
            errores.append({"linea": n, "texto": linea.strip(),
                            "error": "Falta el código del producto."})
            continue
        if not sucursal:
            errores.append({"linea": n, "texto": linea.strip(),
                            "error": "Falta la sucursal."})
            continue

        unidades = _entero(col("unidades"))
        dias = _entero(col("dias"))
        mantener = _entero(col("mantener"))

        # Prioridad: mantener > dias > unidades.
        if mantener is not None and mantener > 0:
            criterio = "mantener"
        elif dias is not None and dias > 0:
            criterio = "dias"
        elif unidades is not None and unidades > 0:
            criterio = "unidades"
        else:
            errores.append({
                "linea": n, "texto": linea.strip(),
                "error": "Falta la cantidad: pon unidades, días o mantener stock "
                         "(un número mayor que cero).",
            })
            continue

        filas.append({
            "producto": producto,
            "sucursal": sucursal,
            "unidades": unidades if criterio == "unidades" else None,
            "dias": dias if criterio == "dias" else None,
            "mantener": mantener if criterio == "mantener" else None,
            "criterio": criterio,
        })

    return {"filas": filas, "errores": errores, "encabezado_detectado": encabezado}
