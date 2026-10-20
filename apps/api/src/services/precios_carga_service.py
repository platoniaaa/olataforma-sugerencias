"""Editar la lista de precios en Excel: bajar el archivo, editarlo y volver a cargarlo.

El archivo "para editar" es la lista completa con tres columnas mas: Obs, Congelar,
No es producto, y una columna `Referencia` que NO se toca. Se pueden editar siete
columnas, y cada una hace lo mismo que su equivalente en la ficha del producto:

  Tipo, Procedencia  -> el tipo / la procedencia escritos a mano. Vacio = vuelve a
                        seguir al rubro / a la regla.
  Factor             -> factor propio del producto (margen fijo). Vacio = lo quita.
  Precio final       -> precio fijo. Vacio = lo quita.
  Obs                -> la observacion.
  Congelar, No es producto -> Si / No.

Todo lo demas (costo, stock, precio ERP, estado...) viene del ERP y del motor, y se
recalcula todos los dias: si se edita, no se carga.

## Por que existe la columna Referencia

Entre que se baja el archivo y se sube, la lista cambia sola: el motor recalcula los
precios cada dia y otras personas editan productos. Comparar el archivo contra lo
que hay hoy confundiria eso con ediciones y las revertiria en silencio. La
referencia guarda, por producto, los valores que tenia el archivo al bajarlo:

- Se carga solo lo que la persona CAMBIO respecto de esos valores, no lo que difiere
  de lo que hay hoy: un precio que el motor movio de noche no se vuelve precio fijo.
- Si las decisiones de un producto cambiaron despues de bajar el archivo (alguien
  lo edito en la ficha) y el archivo tambien lo edita, ese producto NO se carga y se
  avisa: pisarlo seria deshacer el trabajo de otra persona sin que nadie lo vea.

## Como se lee

`.csv` con el lector estandar y `.xlsx` con calamine: openpyxl tardaba 36 s en leer
40 mil filas en un PC, y mas en el plan gratis de Render. Si el archivo trae un solo
error no se carga nada; los productos que no estan, los que no traen referencia y
los conflictos se omiten y se listan.
"""
from __future__ import annotations

import codecs
import csv
import hashlib
import io
import math
import re
import unicodedata
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import insert, select

from ..config import get_settings
from ..models import AuditoriaLog, PrecioOverride, PrecioProducto
from . import auditoria_service, politica_precio_service as politica
from . import precios_service as ps

settings = get_settings()

SEP = "|"      # ASCII: sobrevive a cualquier pagina de codigos (cp850, cp1252, UTF-16...)
COL_REFERENCIA = "Referencia"
CAB_EXTRA = ["Obs", "Congelar", "No es producto", COL_REFERENCIA]

# (clave interna, encabezado del archivo), en el orden en que viajan en la referencia.
CAMPOS = (
    ("tipo", "Tipo"), ("procedencia", "Procedencia"), ("factor", "Factor"),
    ("precio", "Precio final"), ("obs", "Obs"), ("congelar", "Congelar"),
    ("no_producto", "No es producto"),
)
_ETIQUETA_CAMPO = {
    "tipo_manual": "Tipo", "procedencia_manual": "Procedencia", "margen_fijo": "Factor",
    "precio_fijo": "Precio fijo", "obs": "Obs", "congelar": "Congelar",
    "no_producto": "No es producto",
}
_CLAVE_POR_CAMPO_OV = {
    "tipo_manual": "tipo", "procedencia_manual": "procedencia", "margen_fijo": "factor",
    "precio_fijo": "precio_fijo", "obs": "obs", "congelar": "congelar",
    "no_producto": "no_producto",
}

MAX_BYTES = 30 * 1024 * 1024
MAX_FILAS = 250_000            # la lista real tiene ~40 mil: esto solo frena archivos con basura
# Celdas con TEXTO (filas x columnas; las vacias no cuentan): con 3 millones el pico medido
# fue de 479 MB, al borde de los 512 del plan gratis de Render. 2 millones dejan holgura y
# la lista real son ~1 millon (40 mil x 25). Un CSV de 240 mil filas x 41 columnas pasaba
# el tope de filas y de bytes, y ocupaba mas de 800 MB.
MAX_CELDAS = 2_000_000
MAX_DESCOMPRIMIDO = 100 * 1024 * 1024
# Texto seguido, sin una sola etiqueta, que se tolera en el XML de una hoja. Excel admite
# 32.767 caracteres por celda: una "cadena" de 100 MB cabia bajo el tope descomprimido y
# llevaba la memoria a 406 MB.
_TEXTO_MAXIMO = 1 << 20
# Un encabezado con tilde que SIEMPRE esta en el archivo bajado: con el se distingue la
# pagina de codigos en que Excel lo guardo (cp1252, cp850 de "CSV MS-DOS", mac_roman).
MARCA_CODIFICACION = "Descuento máximo"
# Cuantas decisiones puede QUITAR una carga antes de pedir confirmacion explicita. Una
# celda vacia quita la decision, y un .xlsx con celdas de error (#N/D, #REF!) las
# entrega vacias: sin este freno, un BUSCARV roto borraria precios fijos en silencio.
UMBRAL_QUITAS = 10
# Cuantos precios fijos o factores propios NUEVOS puede poner una carga antes de pedir
# confirmacion. Ordenar una sola columna (Precio final, Factor) deja cada precio en la fila
# de otro producto, y cada fila parece una edicion valida: son decenas de miles de precios
# fijos, y ninguna validacion por fila lo ve. Una carga de verdad no suele pasar de unos
# cientos.
UMBRAL_MASIVA = 200
TOPE_LISTA = 200            # errores o conflictos que se devuelven (el total va aparte)
TOPE_CODIGOS = 100
TOPE_CAMBIOS = 300
MAX_OBS = 500


class ErrorCarga(ValueError):
    """El archivo no se puede cargar. El mensaje es para la persona."""


# ------------------------------------------------------------------ canonico
def _norm(texto) -> str:
    """Un encabezado comparable: sin tildes, en minusculas y sin espacios de mas."""
    t = unicodedata.normalize("NFKD", str(texto or ""))
    t = "".join(c for c in t if not unicodedata.combining(c))
    return " ".join(t.casefold().split())


def _texto(v) -> str:
    """El valor de una celda como texto. Un codigo numerico no es "123.0", y un NUL
    (que Postgres no acepta en un texto) no pasa."""
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).replace("\x00", "")


def _c_texto(v) -> str:
    return " ".join(_texto(v).split())


def _h(texto: str) -> str:
    return hashlib.sha1(texto.encode("utf-8")).hexdigest()[:8]


_H_VACIO = _h("")
_FORMULA = ("=", "+", "-", "@", "\t", "\r")


def _proteger(texto: str) -> str:
    """Una celda que empieza con = + - @ la abre Excel como formula: "-5% convenio"
    sale #NOMBRE? y un "=HYPERLINK(...)" escrito por alguien se ejecuta. El apostrofe
    la deja como texto, y se quita al leer."""
    return "'" + texto if texto[:1] in _FORMULA else texto


def _sin_guarda(t: str) -> str:
    """Quita el apostrofe con que `_proteger` dejo una celda como texto."""
    if len(t) > 1 and t[0] == "'" and t[1] in "=+-@":
        return t[1:]
    return t


# Lo que Excel convierte en numero, porcentaje, fecha, hora o notacion cientifica al abrir
# un CSV: "0123" pasa a 123, "3/4" a 03-abr, "1E5" a 1,00E+05, y un telefono de 12 digitos
# a 5,69123E+11 (se pierden digitos). Un entero sin ceros a la izquierda de hasta 11
# digitos vuelve igual: no necesita guarda.
_PARECE_NUMERO = re.compile(
    r"[-+]?\$?\s*\d[\d.,]*\s*%?"                  # 0123, 1,5, 15%, $ 5.000, 569123456789
    r"|\d{1,4}[/-]\d{1,4}(?:[/-]\d{1,4})?"        # 3/4, 10-12, 1/2/2026
    r"|\d{1,2}:\d{2}(?::\d{2})?"                  # 12:30
    r"|[\d.,]+[eE][-+]?\d+")                      # 1E5
_NUMERO_LLANO = re.compile(r"0|[1-9]\d{0,10}")


def _pide_guarda_obs(t: str) -> bool:
    """La observacion necesita el apostrofe: Excel la leeria como formula o como
    numero/fecha. Recursivo en el apostrofe inicial, para que `_c_obs(_proteger_obs(x))`
    devuelva siempre `x` (una nota que ya empieza con apostrofe y se ve como numero)."""
    if t[:1] in _FORMULA:
        return True
    s = t.strip()
    if _PARECE_NUMERO.fullmatch(s) and not _NUMERO_LLANO.fullmatch(s):
        return True
    return t[:1] == "'" and _pide_guarda_obs(t[1:])


def _proteger_obs(texto: str) -> str:
    return "'" + texto if _pide_guarda_obs(texto) else texto


def _c_obs(v) -> str:
    t = _c_texto(v)
    if t[:1] == "'" and _pide_guarda_obs(t[1:]):
        return t[1:]
    return t


_FUERA_BMP = re.compile("[\U00010000-\U0010ffff]")


def _ansi(t: str, pagina: str = "cp1252") -> str:
    """El texto como queda al guardar como "CSV" de Excel (cp1252): lo que no cabe
    pasa a "?". Un emoji o una flecha en una nota se sobrescribian con "?" al abrir el
    archivo y guardarlo sin editar nada. Excel escribe un "?" por unidad UTF-16, asi que
    un emoji (fuera del plano basico, dos unidades) queda como "??"."""
    return _FUERA_BMP.sub("??", t).encode(pagina, errors="replace").decode(pagina)


def _c_obs_ansi(v, pagina: str = "cp1252") -> str:
    """La observacion como la deja Excel: el "?" entra ANTES de colapsar los espacios,
    porque un espacio fino (U+2009) no cabe en cp1252 y Excel lo escribe como "?"."""
    return _c_obs(_ansi(_texto(v), pagina))


# Las otras paginas de codigos en que Excel guarda un CSV: "CSV MS-DOS" y "CSV Macintosh".
# La Referencia solo trae la huella de cp1252; para estas dos se compara contra la nota
# que hay en la plataforma (ver `_ruido_de_pagina`).
_OTRAS_PAGINAS = ("cp850", "mac_roman")


def _ruido_de_pagina(archivo: str, obs) -> bool:
    """La nota del archivo es la de la plataforma tal como la deja Excel en cp850 o
    mac_roman: lo que esa pagina no tiene (€ – “ ” • ™ ...) paso a "?"."""
    return any(archivo == _c_obs_ansi(obs, p) for p in _OTRAS_PAGINAS)


def leer_numero(valor, entero: bool = False) -> float | None:
    """Un numero escrito como Excel en español lo deja: "1,78", "1.78", "17.800",
    "$ 17.800". None si esta vacio; ValueError si no es un numero.

    Con coma y punto a la vez, el ultimo es el decimal. Un punto solo es decimal
    ("1.78") salvo en un precio, donde "17.800" son miles: los precios son enteros."""
    if valor is None or isinstance(valor, bool):
        if valor is None:
            return None
        raise ValueError("no es un número")
    if isinstance(valor, (int, float)):
        n = float(valor)
    else:
        t = str(valor).strip().replace("$", "").replace(" ", "").replace(" ", "")
        if t == "":
            return None
        if t in ("-", "--", "—", "–"):
            return 0.0                    # el formato Contable de Excel escribe el cero asi
        if "," in t and "." in t:
            t = (t.replace(".", "").replace(",", ".") if t.rfind(",") > t.rfind(".")
                 else t.replace(",", ""))
        elif "," in t:
            t = (t.replace(",", "") if entero and re.fullmatch(r"\d{1,3}(,\d{3})+", t)
                 else t.replace(",", "."))
        elif "." in t and entero and re.fullmatch(r"\d{1,3}(\.\d{3})+", t):
            t = t.replace(".", "")
        try:
            n = float(t)
        except ValueError:
            raise ValueError(f'no entiendo "{valor}" como número') from None
    if not math.isfinite(n):
        raise ValueError("no es un número")
    return n


def _fmt_factor(n: float) -> str:
    return f"{round(n, 4):.4f}".rstrip("0").rstrip(".")


def _c_factor(v) -> str:
    n = leer_numero(v)
    return "" if n is None else _fmt_factor(n)


def _c_precio(v) -> str:
    n = leer_numero(v, entero=True)
    return "" if n is None else str(ps.redondear(n))


_SI = {"si", "s", "1", "x", "true", "verdadero", "yes", "y"}     # ya sin tildes
_NO = {"no", "n", "0", "false", "falso", ""}


def _c_bool(v) -> str:
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        v = int(v)
    t = _norm(_texto(v))
    if t in _SI:
        return "1"
    if t in _NO:
        return "0"
    raise ValueError(f'tiene que ser Sí o No, y dice "{_texto(v)}"')


def _canon(campo: str, valor) -> str:
    if campo == "tipo":
        return _sin_guarda(_c_texto(valor)).replace(SEP, "/")
    if campo == "procedencia":
        return _c_texto(valor).replace(SEP, "/")
    if campo == "obs":
        return _c_obs(valor)
    if campo == "factor":
        return _c_factor(valor)
    if campo == "precio":
        return _c_precio(valor)
    return _c_bool(valor)


_BOOL_VISIBLE = {"Sí": "1", "No": "0"}


def _canon_rapido(campo: str, valor, base: str) -> str:
    """`_canon`, con un atajo: casi todas las celdas de un archivo bajado estan como
    se bajaron, y normalizarlas una por una era el 80 % del tiempo de leer 40 mil
    filas. Si el texto de la celda es el de la referencia, esa es su forma canonica.
    Cualquier otra cosa (Excel reformateo un numero, hubo una edicion) pasa por
    `_canon` como siempre. La observacion viaja como huella: solo se atajan las vacias."""
    if isinstance(valor, str):
        t = valor.strip()
        if campo in ("factor", "precio"):
            if t == base or (t and t.replace(",", ".") == base):
                return base
        elif campo in ("congelar", "no_producto"):
            if _BOOL_VISIBLE.get(t) == base:
                return base
        elif campo == "obs":
            if t == "" and base == _H_VACIO:
                return ""
        elif t == base:
            return base
    return _canon(campo, valor)


def _igual(campo: str, valor: str, base: str, base_ansi: str = "") -> bool:
    """La celda de la persona (ya canonica) contra lo que traia la referencia.

    En la observacion `base` y `base_ansi` son huellas: el texto como se bajo y como
    queda al guardarlo como CSV en la pagina de codigos de Windows."""
    if campo == "obs":
        return _h(valor) in (base, base_ansi)
    if campo in ("tipo", "procedencia"):
        return valor.casefold() == base.casefold()
    return valor == base or (campo == "factor" and _redondeo_de_excel(valor, base))


def _redondeo_de_excel(valor: str, base: str) -> bool:
    """El factor del archivo es el de la referencia redondeado a 2 o 3 decimales.

    Excel con "disminuir decimales" guarda 1,1429 como 1,14 o 1,143: si lo unico que
    cambio es ese redondeo (mitad hacia arriba, como Excel y no como el round de Python),
    nadie edito el factor. Se compara con el valor ya canonico, sin ceros finales: 1,4993
    mostrado como "1,50" llega como "1.5". Costo conocido: escribir a proposito el valor
    redondeado tampoco se distingue; la vista previa cuenta esos casos."""
    if not valor or not base:
        return False
    try:
        v, b = Decimal(valor), Decimal(base)
        return any(v == b.quantize(Decimal(1).scaleb(-k), rounding=ROUND_HALF_UP) for k in (2, 3))
    except (ArithmeticError, ValueError):
        return False


def huella_decisiones(ov: dict | None) -> str:
    """Resume lo que las PERSONAS decidieron sobre un producto. Cambia cuando
    alguien edita la ficha, y solo entonces: el motor no escribe en esa tabla.

    El periodo de vigencia entra SOLO si el producto tiene alguna fecha: para los que no
    tienen -todos los de hoy- el valor es el mismo de siempre, y esta huella viaja en la
    Referencia de cada archivo ya descargado. Si cambiara, todos esos archivos darian
    conflicto en cada fila. Tampoco depende de la fecha de hoy: que un periodo venza no
    escribe en `precio_override`, y por lo tanto no mueve la huella."""
    o = ov or {}
    partes = [
        o.get("tipo_manual") or "", o.get("procedencia_manual") or "",
        "" if o.get("margen_fijo") is None else f"{float(o['margen_fijo']):.6f}",
        "" if o.get("precio_fijo") is None else f"{float(o['precio_fijo']):.2f}",
        "1" if o.get("congelar") else "0", "1" if o.get("no_producto") else "0",
        _c_texto(o.get("obs")),
    ]
    desde, hasta = ps._fecha(o.get("vigente_desde")), ps._fecha(o.get("vigente_hasta"))
    if desde is not None or hasta is not None:
        partes += [desde.isoformat() if desde else "", hasta.isoformat() if hasta else ""]
    return hashlib.sha1("\x1f".join(partes).encode("utf-8")).hexdigest()[:8]


def _valores_base(p, ov: dict | None) -> dict[str, str]:
    """Lo que mostraba el archivo para cada columna editable. La observacion va como
    huella: es texto libre (puede traer cualquier caracter) y solo hace falta saber
    si cambio."""
    o = ov or {}
    return {
        "tipo": _c_texto(p.tipo).replace(SEP, "/"),
        "procedencia": _c_texto(p.procedencia_final).replace(SEP, "/"),
        "factor": "" if p.factor is None else _fmt_factor(p.factor),
        "precio": "" if p.precio_final is None else str(ps.redondear(p.precio_final)),
        "obs": _h(_c_obs(o.get("obs"))),
        "congelar": "1" if o.get("congelar") else "0",
        "no_producto": "1" if o.get("no_producto") else "0",
    }


def referencia(codigo: str, p, ov: dict | None) -> str:
    """huella del codigo|tipo|procedencia|factor|precio|huella de la obs|la misma como
    la deja Excel (cp1252)|congelar|no es producto|huella de las decisiones.

    La del codigo ata la referencia a SU producto: una columna ordenada o pegada por
    separado la dejaba en otra fila, y los precios de esa fila se volvian precio fijo
    sin que nada avisara. Va PRIMERA, y es un hash: la celda no empieza nunca con un
    caracter que Excel lea como formula (el tipo, que es texto libre, podia)."""
    base = _valores_base(p, ov)
    partes = [base[c] for c, _ in CAMPOS]
    partes.insert(5, _h(_c_obs_ansi((ov or {}).get("obs"))))   # justo despues de la huella de la obs
    return SEP.join([_h(codigo)] + partes + [huella_decisiones(ov)])


def _leer_referencia(texto: str) -> tuple[dict[str, str], str, str, str]:
    """(base por campo, huella de decisiones, huella del codigo, obs como la deja Excel)."""
    partes = texto.split(SEP)
    if len(partes) != len(CAMPOS) + 3:
        raise ValueError("referencia dañada")
    codigo, resto, h2 = partes[0], partes[1:-1], partes[-1]
    obs_ansi = resto.pop(5)
    return {c: resto[i] for i, (c, _) in enumerate(CAMPOS)}, h2, codigo, obs_ansi


# ------------------------------------------------------------------ descarga
def _celda_factor(v) -> str:
    return "" if v is None else _fmt_factor(v).replace(".", ",")


def _si_no(v) -> str:
    return "Sí" if v else "No"


def csv_editable(db) -> tuple[bytes, int]:
    """La lista completa lista para editar: las mismas columnas que "Exportar
    completa" mas Obs, Congelar, No es producto y la Referencia.

    El factor sale con hasta 4 decimales: un margen fijo da 1,5385 y con 2 saldria
    1,54, que al subirlo pareceria una edicion."""
    tenant = settings.default_tenant_id
    campos = [getattr(PrecioProducto, k) for k, _ in ps.COLUMNAS_COMPLETA] + [PrecioProducto.codigo_erp]
    filas = db.execute(
        select(*campos).where(PrecioProducto.tenant_id == tenant).order_by(PrecioProducto.producto)
    ).all()
    ovs = ps._overrides(db)
    desc = politica.descuentos(db)
    claves = [k for k, _ in ps.COLUMNAS_COMPLETA]
    i = {k: n for n, k in enumerate(claves)}
    enteras = {"costo", "precio_erp", "precio_calculado", "precio_final", "stock", "stock_transito"}

    def _fila(f):
        interno = f[i["producto"]]
        ov = ovs.get(interno)
        celdas = [ps._celda_csv(k, v, k in enteras) for k, v in zip(claves, f)]
        if f[-1]:
            celdas[i["producto"]] = f[-1]
        celdas[i["factor"]] = _celda_factor(f[i["factor"]])
        # Mitad hacia arriba, como la referencia: `_celda_csv` usa el round de Python
        # y un precio fijo de 1234,5 saldria 1234 contra 1235 en la referencia, o
        # sea una "edicion" que nadie hizo.
        pf = f[i["precio_final"]]
        celdas[i["precio_final"]] = "" if pf is None else str(ps.redondear(pf))
        d = ps._descuento_de(desc, f[i["tipo"]], f[i["procedencia_final"]])
        celdas += ["" if d is None else str(int(d)),
                   "" if d is None else str(ps.descuento_para_erp(d))]
        # Texto libre que Excel podria abrir como formula: glosa, rubro y tipo (el tipo
        # escrito a mano en la ficha no se valida) ademas de la observacion.
        for clave in ("glosa", "rubro", "tipo"):
            celdas[i[clave]] = _proteger(celdas[i[clave]])
        p = _Valores(f[i["tipo"]], f[i["procedencia_final"]], f[i["factor"]], f[i["precio_final"]])
        celdas += [_proteger_obs((ov or {}).get("obs") or ""), _si_no((ov or {}).get("congelar")),
                   _si_no((ov or {}).get("no_producto")), referencia(interno, p, ov)]
        return celdas

    cab = [t for _, t in ps.COLUMNAS_COMPLETA] + ps.CAB_DESCUENTO + CAB_EXTRA
    return ps._a_csv(cab, (_fila(f) for f in filas)), len(filas)


@dataclass
class _Valores:
    """Lo minimo de un producto que necesita `referencia`."""
    tipo: str | None
    procedencia_final: str | None
    factor: float | None
    precio_final: float | None


# ------------------------------------------------------------------- lectura
_SI_CELDA = re.compile(r"(?:^|[;,\t\r\n])Sí(?=$|[;,\t\r\n])", re.M)


def _decodificar(contenido: bytes) -> str:
    """El archivo como texto. Excel lo guarda en UTF-8, en UTF-16 ("Texto Unicode") o
    en la pagina de codigos de Windows ("CSV"), y "CSV MS-DOS" y "CSV Macintosh" usan
    otras (cp850, mac_roman) que con tilde dan otro caracter: la letra "í" de "Sí"
    quedaba "¡" y la nota de un producto se sobrescribia con basura."""
    cabeza = contenido[:4096]
    if contenido[:2] in (codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE):
        try:
            return contenido.decode("utf-16")
        except UnicodeDecodeError:
            pass
    elif b"\x00" in cabeza:
        # UTF-16 sin BOM: en el texto latino, la mitad de los bytes es 0.
        pares, impares = cabeza[0::2].count(0), cabeza[1::2].count(0)
        for nombre, ceros in (("utf-16-le", impares), ("utf-16-be", pares)):
            if ceros > len(cabeza) // 4:
                try:
                    return contenido.decode(nombre)
                except UnicodeDecodeError:
                    break
        raise ErrorCarga("El archivo no parece un CSV de texto. Guárdalo desde Excel como CSV o como libro de Excel (.xlsx).")
    try:
        return contenido.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass
    # El encabezado "Descuento máximo" esta siempre: con la pagina de codigos correcta
    # se lee entero. Si no esta (borraron las columnas de descuento, que no se editan),
    # gana la pagina en que mas celdas dicen "Sí" (Congelar y No es producto): en otra
    # la "í" sale como "¡" o "’". Sin ninguna, cp1252, que es la de "CSV".
    mejor, mejor_n = None, 0
    for nombre in ("cp1252", "cp850", "mac_roman"):
        texto = contenido.decode(nombre, errors="replace")
        if MARCA_CODIFICACION in texto[:30000]:
            return texto
        n = len(_SI_CELDA.findall(texto))
        if n > mejor_n:
            mejor, mejor_n = texto, n
    return mejor if mejor is not None else contenido.decode("cp1252", errors="replace")


def _filas_csv(contenido: bytes) -> list[list]:
    texto = _decodificar(contenido)
    primera = next((ln for ln in texto[:8192].splitlines() if ln.strip()), "")
    sep = max((";", ",", "\t"), key=lambda c: (primera.count(c), c == ";"))
    filas: list[list] = []
    celdas = 0
    try:
        # newline="": el CSV de Mac termina las lineas con CR solo, y con el
        # StringIO por defecto el lector no lo separa y falla.
        for fila in csv.reader(io.StringIO(texto, newline=""), delimiter=sep):
            filas.append(fila)
            # Solo cuentan las celdas con texto: Excel escribe una linea ";;;;;" por cada
            # fila con formato debajo de los datos, y esas no ocupan memoria (comparten
            # el mismo str vacio).
            celdas += sum(1 for c in fila if c)
            if len(filas) > MAX_FILAS:
                raise ErrorCarga(f"El archivo tiene más de {_miles(MAX_FILAS)} filas. La lista tiene "
                                 "unas 40 mil: ¿quedaron filas de más al final?")
            if celdas > MAX_CELDAS:
                raise ErrorCarga(f"El archivo tiene más de {_miles(MAX_CELDAS)} celdas con contenido. "
                                 "La lista tiene unas 40 mil filas por 25 columnas: ¿quedaron filas o "
                                 "columnas de más? Bórralas y guarda de nuevo.")
    except csv.Error as e:
        raise ErrorCarga(
            f"No pude leer el archivo como CSV ({e}). Guárdalo desde Excel como CSV UTF-8 "
            "(delimitado por comas) o como libro de Excel (.xlsx) y súbelo de nuevo."
        ) from e
    return filas


def _columna_a_numero(letras: str) -> int:
    n = 0
    for c in letras:
        n = n * 26 + (ord(c) - 64)
    return n


def _primera_hoja(z: zipfile.ZipFile) -> str | None:
    """La ruta, dentro del zip, de la PRIMERA hoja del libro: la unica que se lee. Una
    hoja de apoyo grande en otro lado no tiene por que bloquear la carga."""
    try:
        libro = z.read("xl/workbook.xml").decode("utf-8", "ignore")
        rels = z.read("xl/_rels/workbook.xml.rels").decode("utf-8", "ignore")
    except KeyError:
        return None
    m = re.search(r'<sheet\b[^>]*?\br:id="([^"]+)"', libro)
    if not m:
        return None
    for etiqueta in re.findall(r"<Relationship\b[^>]*>", rels):
        if re.search(r'\bId="%s"' % re.escape(m.group(1)), etiqueta):
            t = re.search(r'\bTarget="([^"]+)"', etiqueta)
            if t:
                ruta = t.group(1).lstrip("/")
                return ruta if ruta.startswith("xl/") else "xl/" + ruta
    return None


_BLOQUE_XML = 1 << 20          # lo que se lee de la hoja por vez
# La forma que escriben Excel, openpyxl y xlsxwriter: `<c r="A1" ...>` con contenido (no
# se cierra sola, `<c r="E2" s="1"/>`, ni se abre y se cierra de inmediato, `<c r="E2"
# s="1"></c>`, como la deja openpyxl) y `<row r="N" ...>`. Se lee rapido, con un regex.
_CELDA = re.compile(r'<c r="([A-Z]{1,3})(\d{1,7})"[^>/]*>(?!</c>)')
_FILA = re.compile(r'<row r="(\d{1,7})"')
# Cualquier <c> o <row> que NO tiene esa forma: referencia dañada, atributos en otro orden,
# comillas simples, prefijo de espacio de nombres (`<x:c`, de librerias basadas en el SDK
# de Open XML), celdas sin referencia. calamine las lee todas, asi que desde el bloque en que
# aparece la primera se lee con `_escanear_general`, mas lento.
_ETIQUETA_RARA = re.compile(
    r'<(?:[A-Za-z_][\w.-]*:(?:c|row)(?=[\s/>])'                 # con prefijo: siempre
    r'|c(?=[\s/>])(?! r="[A-Z]{1,3}\d{1,7}")'                    # sin prefijo y sin la forma canonica
    r'|row(?=[\s/>])(?! r="\d{1,7}"))')
_ETIQUETA_HOJA = re.compile(r"<(?:[A-Za-z_][\w.-]*:)?(c|row)(?=[\s/>])([^>]*)>")
_ATRIBUTO_R = re.compile(r"""\br\s*=\s*(?:"([^"]*)"|'([^']*)')""")
_REFERENCIA = re.compile(r"([A-Z]{1,3})(\d{1,7})")
_CIERRE_CELDA = re.compile(r"</(?:[A-Za-z_][\w.-]*:)?c\s*>")
_COLA_XML = 512                # una etiqueta cortada por el borde del bloque se mira con el siguiente


def _referencia_danada() -> ErrorCarga:
    return ErrorCarga(
        "El archivo de Excel tiene celdas con una referencia dañada. Vuelve a guardarlo desde Excel, o como CSV.")


def _escanear_general(texto, limite, columnas, max_fila, max_col, fila_actual, col_actual):
    """Lo mismo que la via rapida, para etiquetas de cualquier forma. Una celda sin
    referencia ocupa el lugar que le toca en su fila (`<row r=`)."""
    for m in _ETIQUETA_HOJA.finditer(texto):
        if m.start() >= limite:
            break
        atributos = m.group(2)
        r = _ATRIBUTO_R.search(atributos)
        ref = None if r is None else (r.group(1) if r.group(1) is not None else r.group(2))
        if m.group(1) == "row":
            if ref is not None and not (ref.isdigit() and len(ref) <= 7):
                raise _referencia_danada()
            fila_actual = int(ref) if ref is not None else fila_actual + 1
            col_actual = 0
            continue
        if ref is not None:
            mr = _REFERENCIA.fullmatch(ref)
            if mr is None:
                # Una referencia asi (r="A99999999999999999999") hace que calamine pida
                # cientos de GB y ABORTE el proceso entero, sin excepcion.
                raise _referencia_danada()
            letras = mr.group(1)
            col = columnas.get(letras)
            if col is None:
                col = columnas[letras] = _columna_a_numero(letras)
            fila, col_actual = int(mr.group(2)), col
        else:
            fila, col_actual = fila_actual, col_actual + 1
        if atributos.rstrip().endswith("/") or _CIERRE_CELDA.match(texto, m.end()):
            continue                   # vacia: calamine tampoco la lee
        if fila > max_fila:
            max_fila = fila
        if col_actual > max_col:
            max_col = col_actual
    return max_fila, max_col, fila_actual, col_actual


def _escanear_hoja(f) -> tuple[int, int]:
    """(ultima fila, ultima columna) con CONTENIDO en la hoja, leyendo el XML por
    bloques. No se confia en la dimension declarada: falta en los archivos que
    escribe openpyxl en modo streaming, y una celda de mas la hace mentir. Las celdas
    vacias con formato no cuentan: calamine tampoco las lee, y formatear una columna
    entera dejaba el archivo sin poder subirse. Tampoco se acepta un texto enorme sin
    una sola etiqueta: Excel admite 32.767 caracteres por celda."""
    max_fila = max_col = 0
    fila_actual = col_actual = 0
    columnas: dict[str, int] = {}
    resto = ""
    corrida = 0                    # bytes seguidos sin una etiqueta
    lento = False
    while True:
        bloque = f.read(_BLOQUE_XML)
        final = not bloque
        primera = bloque.find(b"<")
        corrida += len(bloque) if primera < 0 else primera       # la corrida termina en la 1a etiqueta
        if corrida > _TEXTO_MAXIMO:
            raise ErrorCarga("El archivo de Excel tiene una celda con muchísimo texto (Excel admite hasta "
                             "32.767 caracteres por celda). Revísalo, o guárdalo como CSV.")
        if primera >= 0:
            corrida = len(bloque) - 1 - bloque.rfind(b"<")        # lo que sigue a la ultima
        texto = resto + bloque.decode("utf-8", "ignore")
        # Lo que queda cerca del final puede ser una etiqueta cortada: se mira con el
        # bloque siguiente. Solo cuenta lo que EMPIEZA antes del limite.
        limite = len(texto) if final else max(len(texto) - _COLA_XML, 0)
        if not lento:
            m = _ETIQUETA_RARA.search(texto)
            lento = m is not None and m.start() < limite
        if lento:
            max_fila, max_col, fila_actual, col_actual = _escanear_general(
                texto, limite, columnas, max_fila, max_col, fila_actual, col_actual)
        else:
            for m in _CELDA.finditer(texto):
                if m.start() >= limite:
                    break
                fila = int(m.group(2))
                if fila > max_fila:
                    max_fila = fila
                letras = m.group(1)
                col = columnas.get(letras)
                if col is None:
                    col = columnas[letras] = _columna_a_numero(letras)
                if col > max_col:
                    max_col = col
            i = texto.rfind('<row r="', 0, limite)       # por si el bloque siguiente es de la via lenta
            if i >= 0:
                fila_actual, col_actual = int(_FILA.match(texto, i).group(1)), 0
        if final:
            return max_fila, max_col
        resto = texto[limite:]


def _revisar_xlsx(contenido: bytes) -> None:
    """Antes de abrirlo: calamine arma la hoja entera en memoria, de A1 a la ultima
    celda con contenido. Un .xlsx de 26 KB con una letra en A1048576 (Ctrl+Flecha
    abajo y escribir, por accidente) pasaba de 1 GB y tumbaba la API; y cualquier
    error aca respondia 500."""
    mensaje = "No pude abrir el archivo de Excel. ¿Está dañado o protegido con contraseña?"
    try:
        z = zipfile.ZipFile(io.BytesIO(contenido))
        if sum(i.file_size for i in z.infolist()) > MAX_DESCOMPRIMIDO:
            raise ErrorCarga("El archivo de Excel es demasiado grande una vez descomprimido.")
        ruta = _primera_hoja(z)
        nombres = z.namelist()
        if ruta is None or ruta not in nombres:
            hojas = sorted((n for n in nombres if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n)),
                           key=lambda n: int(re.search(r"\d+", n.rsplit("/", 1)[1]).group()))
            ruta = hojas[0] if hojas else None
        if ruta is None:
            return
        with z.open(ruta) as f:
            filas, columnas = _escanear_hoja(f)
    except ErrorCarga:
        raise
    except Exception as exc:  # noqa: BLE001 - zip dañado, zlib, KeyError, OSError...
        raise ErrorCarga(mensaje) from exc
    if filas > MAX_FILAS or filas * columnas > MAX_CELDAS:
        raise ErrorCarga(
            f"La primera hoja tiene contenido hasta la fila {_miles(filas)} y la columna {columnas}, "
            "mucho más que la lista. Seguro hay celdas con algo escrito de más: selecciona las filas y "
            "columnas sobrantes, bórralas (Ctrl+Fin te lleva a la última celda usada) y guarda de nuevo.")


def _filas_xlsx(contenido: bytes) -> list[list]:
    try:
        from python_calamine import CalamineWorkbook
    except ImportError as exc:  # pragma: no cover - depende del despliegue
        raise ErrorCarga(
            "Este servidor todavía no puede leer archivos .xlsx. Guárdalo como CSV "
            "(Archivo → Guardar como → CSV) y súbelo de nuevo."
        ) from exc
    _revisar_xlsx(contenido)
    try:
        wb = CalamineWorkbook.from_filelike(io.BytesIO(contenido))
        # Una celda con error (#N/D, #REF!) llega vacia: por eso la carga pide
        # confirmacion cuando quita muchas decisiones (UMBRAL_QUITAS).
        return wb.get_sheet_by_index(0).to_python(skip_empty_area=False)
    except Exception as exc:  # noqa: BLE001 - un xlsx dañado puede fallar de muchas formas
        raise ErrorCarga("No pude abrir el archivo de Excel. ¿Está dañado o protegido con contraseña?") from exc


def leer_archivo(nombre: str, contenido: bytes) -> list[list]:
    if not contenido:
        raise ErrorCarga("El archivo está vacío.")
    if len(contenido) > MAX_BYTES:
        raise ErrorCarga("El archivo pesa más de 30 MB.")
    n = (nombre or "").lower()
    if n.endswith((".xlsx", ".xlsm")):
        return _filas_xlsx(contenido)
    if n.endswith((".csv", ".txt")):
        return _filas_csv(contenido)
    if n.endswith(".xls"):
        raise ErrorCarga("El formato .xls es antiguo. Guárdalo como .xlsx o como CSV y súbelo de nuevo.")
    raise ErrorCarga("El archivo tiene que ser .csv o .xlsx: el que bajaste con \"Descargar para editar\".")


_CLAVES = {"producto": "producto", "referencia": "referencia", "tipo": "tipo",
           "procedencia": "procedencia", "factor": "factor", "precio final": "precio",
           "obs": "obs", "congelar": "congelar", "no es producto": "no_producto"}
_NOMBRE_CLAVE = {"producto": "Producto", "referencia": COL_REFERENCIA,
                 **{c: t for c, t in CAMPOS}}


def _mapear(filas: list[list]) -> tuple[dict[str, int], int]:
    """(columnas por clave, indice de la fila de encabezados)."""
    for n, fila in enumerate(filas[:15]):
        celdas = [_norm(c) for c in fila]
        if "producto" in celdas and "referencia" in celdas:
            cols: dict[str, int] = {}
            for j, c in enumerate(celdas):
                clave = _CLAVES.get(c)
                if clave and clave not in cols:
                    cols[clave] = j
            faltan = [_NOMBRE_CLAVE[k] for k in _NOMBRE_CLAVE if k not in cols]
            if faltan:
                raise ErrorCarga(
                    f"Faltan las columnas: {', '.join(faltan)}. Descarga el archivo de nuevo con "
                    "\"Descargar para editar\" y no borres columnas."
                )
            return cols, n
    raise ErrorCarga(
        "No encuentro las columnas Producto y Referencia. Tiene que ser el archivo que bajaste con "
        "\"Descargar para editar\": sin la Referencia no sé qué cambiaste."
    )


# --------------------------------------------------------------------- plan
@dataclass
class _Plan:
    resumen: dict = field(default_factory=dict)
    cambios: list[dict] = field(default_factory=list)      # lo que se aplicaria, completo
    errores_total: int = 0


def _tipos_validos(db) -> dict[str, str]:
    """{tipo canonico: como se escribe en la politica}."""
    nombres = {f["tipo"] for f in politica.listar_factores(db)} | {politica.TIPO_SUGERIDO}
    # El texto del archivo pasa por `_canon`, que cambia "|" por "/": con la clave
    # igual, un tipo de la politica que llevara "|" nunca se podria elegir.
    return {politica.tipo_canonico(_norm(t.replace(SEP, "/"))): t for t in nombres}


# El unico error que puede venir de lo que OTRA persona dejo en la ficha y no del archivo:
# el archivo edita el factor y la otra persona puso un precio fijo, o al reves.
_ERROR_COMBINACION = (
    "Un producto no puede tener precio fijo y factor propio a la vez. Cambia solo uno de los "
    "dos, o deja vacía la celda del otro para quitárselo."
)


def _datos_override(ed: dict[str, str], ov: dict, tipos: dict[str, str]) -> tuple[dict, list[str]]:
    """De lo que la persona cambio en el archivo, lo que se le aplica al producto
    (mismos nombres que `guardar_override`) y los errores. Pura: no toca la base."""
    datos: dict = {}
    errs: list[str] = []

    if "tipo" in ed:
        t = ed["tipo"]
        if t == "":
            if ov.get("tipo_manual"):
                datos["tipo_manual"] = None
        else:
            canon = tipos.get(politica.tipo_canonico(_norm(t)))     # "Neumático" = "Neumatico"
            if canon is None:
                lista = ", ".join(sorted(tipos.values(), key=str.casefold))
                errs.append(f'Tipo: "{t}" no existe en la política. Los tipos son: {lista}.')
            elif (ov.get("tipo_manual") or "").casefold() != canon.casefold():
                datos["tipo_manual"] = canon

    if "procedencia" in ed:
        p = ed["procedencia"]
        if p == "":
            if ov.get("procedencia_manual"):
                datos["procedencia_manual"] = None
        else:
            norm = ps._norm_proc(p)
            if norm is None:
                errs.append(f'Procedencia: "{p}" no vale. Tiene que ser Nacional o Importado.')
            elif ov.get("procedencia_manual") != norm:
                datos["procedencia_manual"] = norm

    if "factor" in ed:
        f = ed["factor"]
        if f == "":
            if ov.get("margen_fijo") is not None:
                datos["margen_fijo"] = None
        else:
            v = float(f)
            if not 1.0 < v <= 10.0:
                errs.append(f"Factor: {f.replace('.', ',')} no vale. Tiene que ser mayor que 1 y hasta 10.")
            else:
                actual = ps.factor_desde_margen(ov.get("margen_fijo"))
                if actual is None or round(actual, 4) != round(v, 4):
                    # El margen que da exactamente ese factor: es sobre la venta.
                    datos["margen_fijo"] = round((1 - 1 / v) * 100, 8)

    if "precio" in ed:
        p = ed["precio"]
        if p == "":
            if ov.get("precio_fijo") is not None:
                datos["precio_fijo"] = None
        else:
            v = float(int(p))
            if v < 0:
                errs.append("Precio final: no puede ser negativo.")
            elif ov.get("precio_fijo") is None or float(ov["precio_fijo"]) != v:
                datos["precio_fijo"] = v

    if "obs" in ed:
        o = ed["obs"]
        if len(o) > MAX_OBS:
            errs.append(f"Obs: tiene {len(o)} caracteres y el máximo es {MAX_OBS}.")
        elif (o or None) != (_c_texto(ov.get("obs")) or None):
            datos["obs"] = o or None

    for clave, campo in (("congelar", "congelar"), ("no_producto", "no_producto")):
        if clave in ed and (ed[clave] == "1") != bool(ov.get(campo)):
            datos[campo] = ed[clave] == "1"

    # Precio fijo y factor propio no conviven: son dos respuestas para el mismo precio.
    fijo = datos["precio_fijo"] if "precio_fijo" in datos else ov.get("precio_fijo")
    margen = datos["margen_fijo"] if "margen_fijo" in datos else ov.get("margen_fijo")
    if not errs and fijo is not None and margen is not None:
        errs.append(_ERROR_COMBINACION)
    return datos, errs


def _miles(n) -> str:
    return f"{int(round(float(n))):,}".replace(",", ".")


def _describir(datos: dict, ov: dict, p) -> list[dict]:
    """Cada cambio como "antes -> despues", en el idioma de la persona."""
    campos = []
    for k, v in datos.items():
        if k == "tipo_manual":
            antes = ov.get("tipo_manual") or f"(el del rubro: {p.tipo or 'sin tipo'})"
            despues = v or "(vuelve a seguir al rubro)"
        elif k == "procedencia_manual":
            antes = ov.get("procedencia_manual") or f"(la de la regla: {p.procedencia_final or 'sin dato'})"
            despues = v or "(vuelve a la regla)"
        elif k == "margen_fijo":
            f_antes = ps.factor_desde_margen(ov.get("margen_fijo"))
            antes = _celda_factor(f_antes) if f_antes else f"(el de la política: {_celda_factor(p.factor) or '—'})"
            despues = "(vuelve al de la política)" if v is None else _celda_factor(ps.factor_desde_margen(v))
        elif k == "precio_fijo":
            antes = _miles(ov["precio_fijo"]) if ov.get("precio_fijo") is not None else "(sin precio fijo)"
            despues = "(sin precio fijo)" if v is None else _miles(v)
        elif k in ("congelar", "no_producto"):
            antes, despues = _si_no(ov.get(k)), _si_no(v)
        else:
            antes, despues = ov.get("obs") or "(vacía)", v or "(vacía)"
        campos.append({"campo": _ETIQUETA_CAMPO[k], "antes": antes, "despues": despues})
    return campos


def _override_despues(ov: dict, datos: dict, precio_vigente) -> dict:
    d = dict(ov)
    d.update(datos)
    if "congelar" in datos:
        d["congelado_precio"] = precio_vigente if datos["congelar"] and not ov.get("congelar") else (
            ov.get("congelado_precio") if datos["congelar"] else None)
    return d


_MENSAJE_CONFLICTO = (
    "Este producto cambió en la plataforma después de que bajaste el archivo (otra persona, o una "
    "carga tuya anterior). No se cargó: descarga el archivo de nuevo y repite el cambio.")


def _quita(campo: str, valor) -> bool:
    """El cambio le saca una decision al producto: la deja vacia, o pasa Si a No."""
    return valor is None or (campo in ("congelar", "no_producto") and valor is False)


def planificar(db, nombre: str, contenido: bytes) -> _Plan:
    """Lee el archivo y arma lo que se cargaria. No escribe nada."""
    filas = leer_archivo(nombre, contenido)
    try:
        cols, enc = _mapear(filas)
    except ErrorCarga as e:
        if nombre.lower().endswith((".xlsx", ".xlsm")) and str(e).startswith("No encuentro"):
            raise ErrorCarga(
                f"{e} Del libro de Excel solo se lee la primera hoja: si la de los datos no es la "
                "primera, muévela al principio y guarda de nuevo.") from e
        raise
    plan = _Plan()
    errores: list[dict] = []
    conflictos: list[dict] = []
    vistos: dict[str, int] = {}
    candidatos: dict[str, tuple[int, dict[str, str], str]] = {}
    sin_referencia: list[str] = []
    redondeados: list[str] = []
    leidas = sin_cambios = 0

    def celda(fila, clave):
        j = cols[clave]
        return fila[j] if j < len(fila) else ""

    for n, fila in enumerate(filas[enc + 1:], start=enc + 2):
        # Solo se recortan los bordes: los espacios de adentro son parte del codigo.
        # En produccion hay "19  FB5Z15201H" (dos espacios) y "19 FB5Z15201H" (uno):
        # son productos distintos, y colapsarlos los fundia en uno solo.
        codigo = _texto(celda(fila, "producto")).strip()
        if not codigo:
            continue
        leidas += 1
        if codigo in vistos:
            errores.append({"fila": n, "producto": codigo,
                            "mensaje": f"El código aparece repetido (también en la fila {vistos[codigo]})."})
            continue
        vistos[codigo] = n
        ref = _c_texto(celda(fila, "referencia"))
        if not ref:
            sin_referencia.append(codigo)
            continue
        try:
            base, h2, h_codigo, obs_ansi = _leer_referencia(ref)
        except ValueError:
            errores.append({"fila": n, "producto": codigo,
                            "mensaje": "La columna Referencia está dañada. Descarga el archivo de nuevo."})
            continue
        if h_codigo != _h(codigo):
            errores.append({"fila": n, "producto": codigo, "mensaje": (
                "La Referencia de esta fila es de otro producto: ¿ordenaste o pegaste columnas por "
                "separado? Descarga el archivo de nuevo y edítalo sin mover columnas sueltas.")})
            continue
        valores: dict[str, str] = {}
        malo = False
        for campo, titulo in CAMPOS:
            try:
                valores[campo] = _canon_rapido(campo, celda(fila, campo), base[campo])
            except ValueError as e:
                errores.append({"fila": n, "producto": codigo, "mensaje": f"{titulo}: {e}."})
                malo = True
        if malo:
            continue
        ed = {c: valores[c] for c, _ in CAMPOS if not _igual(c, valores[c], base[c], obs_ansi)}
        if "factor" not in ed and valores["factor"] != base["factor"]:
            redondeados.append(codigo)         # Excel mostro el factor con menos decimales
        if not ed:
            sin_cambios += 1
            continue
        candidatos[codigo] = (n, ed, h2)

    desconocidos: list[str] = []
    n_cambios: Counter = Counter()
    n_quitan: Counter = Counter()
    n_fijan: Counter = Counter()
    ejemplos_quitan: list[dict] = []
    suben = bajan = igual = nuevos = 0
    if candidatos:
        tenant = settings.default_tenant_id
        codigos = list(candidatos)
        cols_p = (*ps._COLUMNAS_REGLA, PrecioProducto.tipo, PrecioProducto.procedencia_final,
                  PrecioProducto.factor, PrecioProducto.precio_final)
        prods: dict[str, object] = {}
        for lote in ps._en_lotes(codigos):
            for r in db.execute(select(*cols_p).where(
                    PrecioProducto.tenant_id == tenant, PrecioProducto.producto.in_(lote))).all():
                prods[r.producto] = r
        ovs = ps._overrides(db, codigos)
        fact, rub = politica.factores(db), politica.rubros(db)
        tipos = _tipos_validos(db)

        for codigo, (n, ed, h2) in candidatos.items():
            p = prods.get(codigo)
            if p is None:
                desconocidos.append(codigo)
                continue
            ov = ovs.get(codigo) or {}
            if "obs" in ed and huella_decisiones(ov) == h2 and _ruido_de_pagina(ed["obs"], ov.get("obs")):
                # "CSV MS-DOS" o "Macintosh" cambiaron por "?" lo que su pagina de codigos no
                # tiene (€, comillas curvas, rayas...): la nota es la misma de la plataforma.
                ed = {k: v for k, v in ed.items() if k != "obs"}
                if not ed:
                    sin_cambios += 1
                    continue
            datos, errs = _datos_override(ed, ov, tipos)
            if errs and errs != [_ERROR_COMBINACION]:
                # Un error del propio archivo (tipo que no existe, factor fuera de rango)
                # bloquea la carga, lo haya editado otra persona o no.
                errores.extend({"fila": n, "producto": codigo, "mensaje": e} for e in errs)
                continue
            if huella_decisiones(ov) != h2 and (datos or errs):
                # Otra persona (o una carga anterior) edito este producto despues de
                # bajar el archivo, y el archivo lo edita tambien: se omite SOLO esta
                # fila. Un error de combinacion (precio fijo + factor propio) puede
                # venir de lo que el otro dejo y no del archivo: no bloquea las demas.
                conflictos.append({"fila": n, "producto": codigo, "mensaje": _MENSAJE_CONFLICTO})
                continue
            if errs:
                errores.extend({"fila": n, "producto": codigo, "mensaje": e} for e in errs)
                continue
            if not datos:
                # Lo que el archivo dice ya es lo que hay: p.ej. el mismo archivo subido
                # dos veces, o una carga cuya respuesta se perdio.
                sin_cambios += 1
                continue
            fila_regla = {k: getattr(p, k) for k in (
                "glosa", "rubro", "procedencia_maestro", "costo", "stock", "stock_transito",
                "ult_recep_importado", "ult_pe_nacional", "precio_sugerido")}
            despues = ps.calcular(fila_regla, _override_despues(ov, datos, p.precio_final), fact, rub)
            antes = p.precio_final
            pd = despues["precio_final"]
            if (antes is None) != (pd is None) or (antes is not None and abs(antes - pd) >= 0.5):
                a, d = antes or 0, pd or 0
                if a == 0 and d > 0:
                    nuevos += 1          # no tenia precio y ahora si
                elif d > a:
                    suben += 1
                else:
                    bajan += 1
            else:
                igual += 1
            for k, v in datos.items():
                n_cambios[_CLAVE_POR_CAMPO_OV[k]] += 1
                if _quita(k, v):
                    n_quitan[_CLAVE_POR_CAMPO_OV[k]] += 1
                    if len(ejemplos_quitan) < 20:
                        ejemplos_quitan.append({"producto": codigo, "campo": _ETIQUETA_CAMPO[k]})
                elif k in ("precio_fijo", "margen_fijo"):
                    n_fijan[_CLAVE_POR_CAMPO_OV[k]] += 1
            plan.cambios.append({
                "producto": codigo, "fila": n, "glosa": p.glosa, "datos": datos, "h2": h2, "ed": ed,
                "campos": _describir(datos, ov, p), "precio_antes": antes, "precio_despues": pd,
            })

    plan.errores_total = len(errores)
    plan.resumen = {
        "archivo": nombre, "filas": leidas, "sin_cambios": sin_cambios,
        "a_cambiar": len(plan.cambios), "por_campo": dict(n_cambios),
        "efecto": {"suben": suben, "bajan": bajan, "sin_cambio_de_precio": igual,
                   "con_precio_nuevo": nuevos},
        "quitan_total": sum(n_quitan.values()), "quitan": dict(n_quitan),
        "quitan_ejemplos": ejemplos_quitan, "umbral_quitas": UMBRAL_QUITAS,
        "fijan_total": sum(n_fijan.values()), "fijan": dict(n_fijan), "umbral_masiva": UMBRAL_MASIVA,
        "factor_redondeado_total": len(redondeados), "factor_redondeado": redondeados[:TOPE_CODIGOS],
        "errores": errores[:TOPE_LISTA], "errores_total": len(errores),
        "conflictos": conflictos[:TOPE_LISTA], "conflictos_total": len(conflictos),
        "desconocidos": desconocidos[:TOPE_CODIGOS], "desconocidos_total": len(desconocidos),
        "sin_referencia": sin_referencia[:TOPE_CODIGOS], "sin_referencia_total": len(sin_referencia),
        "cambios": [{k: c[k] for k in ("producto", "glosa", "campos", "precio_antes", "precio_despues")}
                    for c in plan.cambios[:TOPE_CAMBIOS]],
        "cambios_total": len(plan.cambios),
    }
    return plan


def vista_previa(db, nombre: str, contenido: bytes) -> dict:
    return planificar(db, nombre, contenido).resumen


# ------------------------------------------------------------------ aplicar
def aplicar(db, nombre: str, contenido: bytes, usuario: str | None,
            confirmar_quitas: bool = False, confirmar_masiva: bool = False) -> dict:
    """Carga los cambios del archivo, todos o ninguno. Si el archivo tiene errores
    no se carga nada. Recalcula SOLO los productos tocados, con la politica cargada
    una vez, y no genera "cambios sin revisar": son decisiones de una persona.

    Una celda vacia quita la decision, y un .xlsx con celdas de error (#N/D, #REF!)
    las entrega vacias: si la carga quita `UMBRAL_QUITAS` decisiones o mas, hace falta
    `confirmar_quitas`. Si pone mas de `UMBRAL_MASIVA` precios fijos o factores propios
    nuevos, hace falta `confirmar_masiva`."""
    plan = planificar(db, nombre, contenido)
    if plan.errores_total:
        uno = plan.errores_total == 1
        raise ErrorCarga(
            f"El archivo tiene {plan.errores_total} {'error' if uno else 'errores'}. No se cargó nada: "
            f"{'corrígelo' if uno else 'corrígelos'} y súbelo de nuevo.")
    r = plan.resumen
    if r["quitan_total"] >= UMBRAL_QUITAS and not confirmar_quitas:
        raise ErrorCarga(
            f"Esta carga quita {r['quitan_total']} decisiones (precios fijos, factores propios, tipos...). "
            "Confírmalo en la pantalla antes de cargar: si no era lo que querías, puede haber celdas con "
            "error (#N/D, #REF!) en el Excel.")
    if r["fijan_total"] > UMBRAL_MASIVA and not confirmar_masiva:
        raise ErrorCarga(
            f"Esta carga deja {_miles(r['fijan_total'])} precios fijos o factores propios nuevos. "
            "Confírmalo en la pantalla antes de cargar: si no era lo que querías, puede que se haya "
            "ordenado una sola columna del Excel y los valores quedaron en la fila de otro producto.")
    omitidos = {"conflictos": r["conflictos_total"], "desconocidos": r["desconocidos_total"],
                "sin_referencia": r["sin_referencia_total"]}
    if not plan.cambios:
        return {"aplicados": 0, "por_campo": {}, "precios_distintos": 0, "sin_cambios": r["sin_cambios"],
                "omitidos": omitidos}

    # La politica se lee ANTES de escribir: `politica.factores` atrapa cualquier error,
    # hace rollback y devuelve {}, y leida despues de los overrides se llevaba por
    # delante lo ya escrito y el codigo seguia, respondiendo 200 con la auditoria hecha.
    # `rub` tambien: sin los rubros, todo producto cuyo tipo sale del rubro quedaba sin
    # precio (SIN REVISION) y se confirmaba igual.
    fact, rub = politica.factores(db), politica.rubros(db)
    if not fact or not rub:
        raise ErrorCarga("No pude leer la política de precios. No se cargó nada: vuelve a intentarlo.")
    tipos = _tipos_validos(db)

    tenant = settings.default_tenant_id
    codigos = [c["producto"] for c in plan.cambios]
    prods: dict[str, PrecioProducto] = {}
    ovs: dict[str, PrecioOverride] = {}
    for lote in ps._en_lotes(codigos):
        # FOR UPDATE: entre comparar el archivo y escribir, otra persona podria editar
        # el mismo producto. SQLite lo ignora; Postgres bloquea la fila hasta el commit.
        for p in db.scalars(select(PrecioProducto).where(
                PrecioProducto.tenant_id == tenant, PrecioProducto.producto.in_(lote)).with_for_update()).all():
            prods[p.producto] = p
        for o in db.scalars(select(PrecioOverride).where(
                PrecioOverride.tenant_id == tenant, PrecioOverride.producto.in_(lote)).with_for_update()).all():
            ovs[o.producto] = o

    # Con las filas ya bloqueadas se vuelve a calcular lo que el archivo cambia contra lo
    # que hay AHORA: el plan se hizo antes, y en el medio pudo entrar otra carga (el
    # reintento de una respuesta perdida) o una edicion de la ficha.
    pendientes: list[dict] = []
    sin_cambios = r["sin_cambios"]
    for c in plan.cambios:
        cod = c["producto"]
        if cod not in prods:
            omitidos["desconocidos"] += 1
            continue
        o = ovs.get(cod)
        ov_actual = ps._override_dict(o) if o else {}
        datos, errs = _datos_override(c["ed"], ov_actual, tipos)
        if huella_decisiones(ov_actual) != c["h2"] and (datos or errs):
            omitidos["conflictos"] += 1
            continue
        if errs:
            omitidos["conflictos"] += 1
            continue
        if not datos:
            sin_cambios += 1               # ya estaba como dice el archivo
            continue
        pendientes.append({**c, "datos": datos})
    if not pendientes:
        db.rollback()
        return {"aplicados": 0, "por_campo": {}, "precios_distintos": 0, "sin_cambios": sin_cambios,
                "omitidos": omitidos}

    detalles: dict[str, str] = {}
    por_campo: Counter = Counter()
    for c in pendientes:
        cod = c["producto"]
        o = ovs.get(cod)
        if o is None:
            o = PrecioOverride(tenant_id=tenant, producto=cod)
            db.add(o)
            ovs[cod] = o
        detalles[cod] = "; ".join(ps._aplicar_override(o, prods[cod].precio_final, c["datos"], usuario))
        for k in c["datos"]:
            por_campo[_CLAVE_POR_CAMPO_OV[k]] += 1
    db.flush()

    distintos = 0
    obs_de: dict[str, str | None] = {}
    for c in pendientes:
        cod = c["producto"]
        p = prods[cod]
        antes = p.precio_final
        ps._recalcular_una(db, p, ps._override_dict(ovs[cod]), fact, rub)
        distintos += int((antes is None) != (p.precio_final is None)
                         or (antes is not None and abs(antes - p.precio_final) >= 0.5))
        obs_de[cod] = ovs[cod].obs

    aplicados = [c["producto"] for c in pendientes]
    filas_aud = [{
        "tenant_id": tenant, "accion": "precio_override", "entidad": "precio", "entidad_id": cod,
        "producto": cod, "usuario_email": usuario, "motivo": obs_de[cod],
        "detalle": f"{detalles[cod] or 'sin cambios'} (carga desde Excel)"[:1900],
    } for cod in aplicados]
    for i in range(0, len(filas_aud), 500):
        db.execute(insert(AuditoriaLog), filas_aud[i:i + 500])

    resumen_campos = ", ".join(f"{k}: {v}" for k, v in sorted(por_campo.items()))
    auditoria_service.registrar(
        db, accion="precios_carga_excel", entidad="precios", usuario_email=usuario,
        detalle=(f"{len(aplicados)} productos ({resumen_campos}); {distintos} cambiaron de precio; "
                 f"omitidos: {omitidos['conflictos']} conflictos, {omitidos['desconocidos']} desconocidos, "
                 f"{omitidos['sin_referencia']} sin referencia")[:1900],
    )
    auditoria_service.notificar(
        db, tipo="precios",
        titulo=f"Lista de precios: carga desde Excel de {usuario or 'alguien'}",
        mensaje=f"{len(aplicados)} productos actualizados ({resumen_campos}); {distintos} cambiaron de precio.",
        creado_por_email=usuario,
    )
    db.commit()
    return {"aplicados": len(aplicados), "por_campo": dict(por_campo), "precios_distintos": distintos,
            "sin_cambios": sin_cambios, "omitidos": omitidos}
