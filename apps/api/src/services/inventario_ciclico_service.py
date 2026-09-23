"""Logica del modulo Inventario ciclico.

Reglas que vienen de jefatura (correo de mramos):
- En un ano se cuenta todo lo que hay en cada bodega -> cantidad semanal sugerida
  por sucursal = productos con stock aun no contados en el ano / semanas que quedan.
- Cada semana se cuenta al menos un producto de cada clase A, B, C y D.
- Los lunes se carga producto, descripcion, sucursal, clase ABC, cantidad y costo.
- Algunos productos requieren evidencia del conteo.
- Bodega puede dejar una observacion.
- El CD no entra.

Las dos primeras reglas solo avisan: quien carga decide si sigue.
"""
from __future__ import annotations

import json
import math
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, distinct, func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import DimSucursal, IcEvidencia, IcItem, IcRol, StockUnificado, Usuario
from .excel_loader import _norm, _rows_from_csv, _rows_from_xlsx

settings = get_settings()

CLASES = ("A", "B", "C", "D")
CD = "CD REPUESTOS"
# Sucursales que existen en el stock del motor. dim_sucursal puede traer otras.
SUCURSALES_CONOCIDAS = (
    "LINDEROS", "CURICO", "TALCA", "TALCA (2)", "RANCAGUA", "CHILLAN",
    "CHILLAN VIEJO", "BRASIL 18", "PLACILLA", "DIEZ DE JULIO (2)", CD,
)

# Tope por archivo de evidencia. El backend corre serverless (limite ~4.5 MB por request).
MAX_EVIDENCIA_BYTES = 4 * 1024 * 1024
TIPOS_EVIDENCIA = ("image/jpeg", "image/png", "image/webp", "image/heic", "application/pdf")

COLUMNAS_PLANTILLA = (
    "Producto", "Descripcion", "Sucursal", "Clasif ABC", "Cantidad", "Costo",
    "Requiere evidencia",
)

HEADER_ALIASES = {
    "producto": "producto",
    "codigo": "producto",
    "codigo_producto": "producto",
    "descripcion": "descripcion",
    "glosa": "descripcion",
    "sucursal": "sucursal",
    "sucursal_id": "sucursal",
    "bodega": "sucursal",
    "clasif_abc": "clase",
    "clasificacion_abc": "clase",
    "clasif": "clase",
    "clase": "clase",
    "abc": "clase",
    "cantidad": "cantidad",
    "stock": "cantidad",
    "cantidad_sistema": "cantidad",
    "costo": "costo",
    "costo_unitario": "costo",
    "requiere_evidencia": "requiere_evidencia",
    "evidencia": "requiere_evidencia",
}
OBLIGATORIAS = ("producto", "sucursal", "clase", "cantidad", "costo")


# --------------------------- permisos --------------------------- #
@dataclass
class Acceso:
    email: str
    rol: str | None  # "admin" | "bodega" | None
    sucursales: list[str] | None  # None = todas

    @property
    def es_admin(self) -> bool:
        return self.rol == "admin"

    def ve(self, sucursal_id: str) -> bool:
        return self.sucursales is None or sucursal_id in self.sucursales


def acceso(db: Session, email: str) -> Acceso:
    fila = db.get(IcRol, email)
    usuario = db.get(Usuario, email)
    if usuario is not None and not usuario.activo:
        return Acceso(email, None, [])
    if (usuario and usuario.es_admin) or (fila and fila.rol == "admin"):
        return Acceso(email, "admin", None)
    if fila and fila.rol == "bodega":
        return Acceso(email, "bodega", _lista_json(fila.sucursales))
    return Acceso(email, None, [])


def _lista_json(valor: str | None) -> list[str] | None:
    if not valor:
        return None
    try:
        vals = json.loads(valor)
    except (ValueError, TypeError):
        return None
    vals = [str(v) for v in vals if v] if isinstance(vals, list) else []
    return vals or None


# --------------------------- semanas --------------------------- #
def lunes_de(d: date) -> date:
    return d - timedelta(days=d.weekday())


def semanas_restantes(semana: date) -> int:
    """Semanas del ano desde `semana` (incluida) hasta el 31-dic."""
    fin = date(semana.year, 12, 31)
    return max(1, (fin - semana).days // 7 + 1)


# --------------------------- sucursales --------------------------- #
def _clave(s: str) -> str:
    s = "".join(c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c))
    s = re.sub(r"[()]", " ", s.upper())
    return re.sub(r"\s+", " ", s).strip()


def mapa_sucursales(db: Session) -> dict[str, str]:
    """clave normalizada -> sucursal_id. Acepta el id o el nombre ("Talca 2" = "TALCA (2)")."""
    mapa: dict[str, str] = {_clave(s): s for s in SUCURSALES_CONOCIDAS}
    for s in db.scalars(select(DimSucursal)).all():
        mapa.setdefault(_clave(s.sucursal_id), s.sucursal_id)
        if s.nombre:
            mapa.setdefault(_clave(s.nombre), s.sucursal_id)
    mapa["CD"] = CD
    return mapa


# --------------------------- parseo --------------------------- #
def _numero(valor: Any) -> float | None:
    if valor is None:
        return None
    if isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    s = str(valor).strip().replace("$", "").replace(" ", "")
    if not s:
        return None
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    elif re.fullmatch(r"-?\d{1,3}(\.\d{3})+", s):
        s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


def _si(valor: Any) -> bool:
    if isinstance(valor, bool):
        return valor
    return _norm(str(valor or "")) in ("si", "s", "x", "1", "true", "yes", "verdadero")


def _texto(valor: Any) -> str:
    if valor is None:
        return ""
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
    return str(valor).strip()


@dataclass
class ResultadoLectura:
    filas: list[dict[str, Any]] = field(default_factory=list)
    errores: list[str] = field(default_factory=list)


def leer_archivo(db: Session, nombre: str, contenido: bytes) -> ResultadoLectura:
    res = ResultadoLectura()
    try:
        if nombre.lower().endswith(".csv"):
            headers, data = _rows_from_csv(contenido)
        else:
            headers, data = _rows_from_xlsx(contenido)
    except Exception:
        res.errores.append("No se pudo leer el archivo. Sube un Excel (.xlsx) o un CSV.")
        return res

    columnas: dict[str, int] = {}
    for i, h in enumerate(headers):
        campo = HEADER_ALIASES.get(_norm(h))
        if campo and campo not in columnas:
            columnas[campo] = i
    faltan = [c for c in OBLIGATORIAS if c not in columnas]
    if faltan:
        res.errores.append(
            "Faltan columnas: " + ", ".join(faltan)
            + ". Usa la plantilla (Producto, Descripcion, Sucursal, Clasif ABC, Cantidad, Costo)."
        )
        return res

    sucursales = mapa_sucursales(db)
    vistos: set[tuple[str, str]] = set()

    def celda(fila: list[Any], campo: str) -> Any:
        i = columnas.get(campo)
        return fila[i] if i is not None and i < len(fila) else None

    for n, fila in enumerate(data, start=2):
        if not any(v not in (None, "") for v in fila):
            continue
        errores: list[str] = []
        producto = _texto(celda(fila, "producto"))
        if not producto:
            errores.append("falta el producto")
        suc_txt = _texto(celda(fila, "sucursal"))
        sucursal_id = sucursales.get(_clave(suc_txt))
        if not suc_txt:
            errores.append("falta la sucursal")
        elif sucursal_id is None:
            errores.append(f"sucursal \"{suc_txt}\" no existe")
        elif sucursal_id == CD:
            errores.append("el CD no entra en el inventario ciclico")
        clase = _texto(celda(fila, "clase")).upper()
        if clase not in CLASES:
            errores.append(f"clase \"{clase or 'vacia'}\" no es A, B, C o D")
        cantidad = _numero(celda(fila, "cantidad"))
        if cantidad is None:
            errores.append("cantidad no es un numero")
        costo = _numero(celda(fila, "costo"))
        if costo is None:
            errores.append("costo no es un numero")
        if producto and sucursal_id:
            if (sucursal_id, producto) in vistos:
                errores.append("producto repetido para la misma sucursal")
            vistos.add((sucursal_id, producto))
        if errores:
            res.errores.append(f"Fila {n}: " + "; ".join(errores))
            continue
        res.filas.append({
            "producto": producto,
            "descripcion": _texto(celda(fila, "descripcion")) or None,
            "sucursal_id": sucursal_id,
            "clase": clase,
            "cantidad_sistema": cantidad,
            "costo_unitario": costo,
            "requiere_evidencia": _si(celda(fila, "requiere_evidencia")),
        })
    if not res.filas and not res.errores:
        res.errores.append("El archivo no trae filas.")
    return res


# --------------------------- carga --------------------------- #
def productos_con_stock(db: Session) -> dict[str, int]:
    """sucursal_id -> productos distintos con stock > 0 (stock que publica el motor)."""
    rows = db.execute(
        select(StockUnificado.sucursal_id, func.count(distinct(StockUnificado.producto)))
        .where(StockUnificado.tenant_id == settings.default_tenant_id)
        .where(StockUnificado.stock > 0)
        .group_by(StockUnificado.sucursal_id)
    ).all()
    return {s: int(n) for s, n in rows if s}


def contados_en_el_ano(db: Session, semana: date, antes_de: bool) -> dict[str, int]:
    """sucursal_id -> productos distintos contados en el ano de `semana`.

    antes_de=True cuenta solo semanas anteriores (para calcular lo que queda)."""
    desde = date(semana.year, 1, 1)
    hasta = semana - timedelta(days=1) if antes_de else date(semana.year, 12, 31)
    rows = db.execute(
        select(IcItem.sucursal_id, func.count(distinct(IcItem.producto)))
        .where(IcItem.tenant_id == settings.default_tenant_id)
        .where(IcItem.semana >= desde, IcItem.semana <= hasta)
        .where(IcItem.cantidad_contada.is_not(None))
        .group_by(IcItem.sucursal_id)
    ).all()
    return {s: int(n) for s, n in rows}


def cuota_semanal(con_stock: int, ya_contados: int, semana: date) -> int:
    pendientes = max(0, con_stock - ya_contados)
    return math.ceil(pendientes / semanas_restantes(semana)) if pendientes else 0


def avisos_de_reglas(db: Session, semana: date, sucursales: list[str]) -> list[str]:
    avisos: list[str] = []
    con_stock = productos_con_stock(db)
    previos = contados_en_el_ano(db, semana, antes_de=True)
    for suc in sorted(sucursales):
        items = db.scalars(
            select(IcItem).where(
                IcItem.tenant_id == settings.default_tenant_id,
                IcItem.semana == semana,
                IcItem.sucursal_id == suc,
            )
        ).all()
        presentes = {i.clase for i in items}
        faltan = [c for c in CLASES if c not in presentes]
        if faltan:
            avisos.append(f"{suc}: falta al menos un producto de clase {', '.join(faltan)}.")
        cuota = cuota_semanal(con_stock.get(suc, 0), previos.get(suc, 0), semana)
        if len(items) < cuota:
            avisos.append(
                f"{suc}: {len(items)} productos asignados; para contar toda la bodega en el ano "
                f"se sugieren al menos {cuota} por semana."
            )
    return avisos


def cargar_semana(db: Session, semana: date, filas: list[dict[str, Any]], email: str) -> dict[str, Any]:
    """Guarda la asignacion. Nunca toca lo ya contado.

    Por cada sucursal que viene en el archivo, lo no contado que no viene se borra
    (el archivo nuevo reemplaza la lista). Lo contado se conserva tal cual."""
    tenant = settings.default_tenant_id
    sucursales = sorted({f["sucursal_id"] for f in filas})
    existentes = {
        (i.sucursal_id, i.producto): i
        for i in db.scalars(
            select(IcItem).where(
                IcItem.tenant_id == tenant,
                IcItem.semana == semana,
                IcItem.sucursal_id.in_(sucursales),
            )
        ).all()
    }
    nuevas_claves = {(f["sucursal_id"], f["producto"]) for f in filas}
    insertados = actualizados = conservados = eliminados = 0

    borrar = [
        i.id for k, i in existentes.items()
        if k not in nuevas_claves and i.cantidad_contada is None
    ]
    if borrar:
        db.execute(delete(IcEvidencia).where(IcEvidencia.item_id.in_(borrar)))
        db.execute(delete(IcItem).where(IcItem.id.in_(borrar)))
        eliminados = len(borrar)

    ahora = datetime.now(timezone.utc)
    for f in filas:
        item = existentes.get((f["sucursal_id"], f["producto"]))
        if item is None:
            db.add(IcItem(tenant_id=tenant, semana=semana, cargado_por=email, cargado_en=ahora, **f))
            insertados += 1
        elif item.cantidad_contada is not None:
            conservados += 1
        else:
            for k, v in f.items():
                setattr(item, k, v)
            item.cargado_por = email
            item.cargado_en = ahora
            actualizados += 1
    db.flush()
    return {
        "semana": semana.isoformat(),
        "sucursales": sucursales,
        "insertados": insertados,
        "actualizados": actualizados,
        "conservados": conservados,
        "eliminados": eliminados,
        "avisos": avisos_de_reglas(db, semana, sucursales),
    }


# --------------------------- consulta --------------------------- #
def estado(item: IcItem, n_evidencias: int) -> str:
    if item.cantidad_contada is None:
        return "pendiente"
    if item.requiere_evidencia and n_evidencias == 0:
        return "falta_evidencia"
    if item.cantidad_contada != item.cantidad_sistema:
        return "con_diferencia"
    return "sin_diferencia"


def conteo_evidencias(db: Session, item_ids: list[str]) -> dict[str, int]:
    if not item_ids:
        return {}
    rows = db.execute(
        select(IcEvidencia.item_id, func.count())
        .where(IcEvidencia.item_id.in_(item_ids))
        .group_by(IcEvidencia.item_id)
    ).all()
    return {i: int(n) for i, n in rows}


def items_de_semana(db: Session, semana: date, acc: Acceso, sucursal: str | None = None) -> list[IcItem]:
    stmt = select(IcItem).where(
        IcItem.tenant_id == settings.default_tenant_id, IcItem.semana == semana
    )
    if sucursal:
        stmt = stmt.where(IcItem.sucursal_id == sucursal)
    if acc.sucursales is not None:
        stmt = stmt.where(IcItem.sucursal_id.in_(acc.sucursales))
    return list(db.scalars(stmt.order_by(IcItem.sucursal_id, IcItem.clase, IcItem.producto)).all())


def semanas(db: Session, acc: Acceso) -> list[date]:
    stmt = select(distinct(IcItem.semana)).where(IcItem.tenant_id == settings.default_tenant_id)
    if acc.sucursales is not None:
        stmt = stmt.where(IcItem.sucursal_id.in_(acc.sucursales))
    return sorted(db.scalars(stmt).all(), reverse=True)


def resumen(db: Session, semana: date, acc: Acceso) -> list[dict[str, Any]]:
    items = items_de_semana(db, semana, acc)
    evid = conteo_evidencias(db, [i.id for i in items])
    con_stock = productos_con_stock(db)
    previos = contados_en_el_ano(db, semana, antes_de=True)
    en_el_ano = contados_en_el_ano(db, semana, antes_de=False)

    por_suc: dict[str, list[IcItem]] = {}
    for i in items:
        por_suc.setdefault(i.sucursal_id, []).append(i)

    out = []
    for suc, lista in sorted(por_suc.items()):
        estados = [estado(i, evid.get(i.id, 0)) for i in lista]
        contados = [i for i in lista if i.cantidad_contada is not None]
        difs = [(i.cantidad_contada - i.cantidad_sistema) * i.costo_unitario for i in contados]
        presentes = {i.clase for i in lista}
        total_stock = con_stock.get(suc, 0)
        out.append({
            "sucursal_id": suc,
            "asignados": len(lista),
            "contados": len(contados),
            "pendientes": estados.count("pendiente"),
            "falta_evidencia": estados.count("falta_evidencia"),
            "con_diferencia": estados.count("con_diferencia"),
            "diferencia_unidades": sum(i.cantidad_contada - i.cantidad_sistema for i in contados),
            "diferencia_sobrante": sum(d for d in difs if d > 0),
            "diferencia_faltante": sum(d for d in difs if d < 0),
            "clases_faltantes": [c for c in CLASES if c not in presentes],
            "cuota_sugerida": cuota_semanal(total_stock, previos.get(suc, 0), semana),
            "productos_con_stock": total_stock,
            "contados_en_el_ano": en_el_ano.get(suc, 0),
        })
    return out
