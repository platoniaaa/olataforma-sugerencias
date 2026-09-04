"""La politica de precios como dato: factores por (tipo, procedencia) y tipo por rubro.

Leer es barato y se hace en cada recalculo; escribir es raro, es de admin y
queda en la auditoria. `sembrar` existe para la primera carga: trae la hoja
Politica y la hoja Rubros del Excel y no toca nada si las tablas ya tienen algo.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import PoliticaPrecio, PoliticaRubro
from . import auditoria_service

settings = get_settings()

NACIONAL = "Nacional"
IMPORTADO = "Importado"
SIN_REVISION = "SIN REVISION"
PROCEDENCIAS = (NACIONAL, IMPORTADO)

# El tipo que NO calcula costo x factor: toma la lista del proveedor.
TIPO_SUGERIDO = "Sugerido"


def _now() -> datetime:
    return datetime.now(timezone.utc)


# El Excel escribe el mismo tipo de varias formas ("Bateria" en la hoja Politica,
# "Baterias" en la columna Tipo). Sin esto la clave no calza y la fila cae en
# SIN REVISION aunque el factor exista.
_ALIAS = {
    "baterias": "bateria",
    "neumaticos": "neumatico",
    "lubricantes": "lubricante",
}


def tipo_canonico(tipo: str | None) -> str:
    t = (tipo or "").strip().lower()
    return _ALIAS.get(t, t)


def _clave(tipo: str | None, procedencia: str | None) -> tuple[str, str]:
    return (tipo_canonico(tipo), (procedencia or "").strip().lower())


def factores(db: Session) -> dict[tuple[str, str], float]:
    """{(tipo, procedencia) en minusculas: factor}. Vacio si la tabla no existe."""
    try:
        filas = db.execute(
            select(PoliticaPrecio.tipo, PoliticaPrecio.procedencia, PoliticaPrecio.factor)
            .where(PoliticaPrecio.tenant_id == settings.default_tenant_id)
        ).all()
    except Exception:  # noqa: BLE001 - tabla ausente en un despliegue viejo
        db.rollback()
        return {}
    return {_clave(t, p): float(f) for t, p, f in filas if f is not None}


def rubros(db: Session) -> dict[str, dict]:
    """{rubro: {"tipo", "procedencia_forzada"}}."""
    try:
        filas = db.execute(
            select(PoliticaRubro.rubro, PoliticaRubro.tipo, PoliticaRubro.procedencia_forzada)
            .where(PoliticaRubro.tenant_id == settings.default_tenant_id)
        ).all()
    except Exception:  # noqa: BLE001
        db.rollback()
        return {}
    return {
        (r or "").strip(): {
            "tipo": (t or "").strip() or None,
            "procedencia_forzada": (p or "").strip() or None,
        }
        for r, t, p in filas
        if (r or "").strip()
    }


def listar_factores(db: Session) -> list[dict]:
    filas = db.scalars(
        select(PoliticaPrecio)
        .where(PoliticaPrecio.tenant_id == settings.default_tenant_id)
        .order_by(PoliticaPrecio.tipo, PoliticaPrecio.procedencia)
    ).all()
    return [
        {
            "tipo": f.tipo, "procedencia": f.procedencia, "factor": f.factor,
            "descuento_max": f.descuento_max, "margen_post": f.margen_post,
            "actualizado_por": f.actualizado_por,
            "actualizado_en": f.actualizado_en.isoformat() if f.actualizado_en else None,
        }
        for f in filas
    ]


def listar_rubros(db: Session) -> list[dict]:
    filas = db.scalars(
        select(PoliticaRubro)
        .where(PoliticaRubro.tenant_id == settings.default_tenant_id)
    ).all()
    # Orden numerico del rubro ("5" antes que "10"); lo no numerico al final.
    filas = sorted(filas, key=lambda f: (0, int(f.rubro)) if f.rubro.isdigit() else (1, 0))
    return [
        {
            "rubro": f.rubro, "tipo": f.tipo, "procedencia_forzada": f.procedencia_forzada,
            "actualizado_por": f.actualizado_por,
            "actualizado_en": f.actualizado_en.isoformat() if f.actualizado_en else None,
        }
        for f in filas
    ]


def guardar_factores(db: Session, filas: list[dict], usuario: str | None) -> dict:
    """Upsert por (tipo, procedencia). Un factor <= 1 vende bajo el costo: se rechaza."""
    tenant = settings.default_tenant_id
    cambios: list[str] = []
    for f in filas:
        tipo = (f.get("tipo") or "").strip()
        proc = (f.get("procedencia") or "").strip()
        if not tipo or proc not in PROCEDENCIAS:
            raise ValueError(f"Fila invalida: tipo={tipo!r} procedencia={proc!r}")
        factor = float(f.get("factor") or 0)
        if not (1.0 < factor <= 10.0):
            raise ValueError(f"Factor fuera de rango para {tipo}/{proc}: {factor}")
        actual = db.scalars(
            select(PoliticaPrecio).where(
                PoliticaPrecio.tenant_id == tenant,
                PoliticaPrecio.tipo == tipo,
                PoliticaPrecio.procedencia == proc,
            )
        ).first()
        if actual is None:
            actual = PoliticaPrecio(tenant_id=tenant, tipo=tipo, procedencia=proc, factor=factor)
            db.add(actual)
            cambios.append(f"{tipo}/{proc}: nuevo {factor}")
        elif abs((actual.factor or 0) - factor) > 1e-9:
            cambios.append(f"{tipo}/{proc}: {actual.factor} -> {factor}")
        actual.factor = factor
        actual.descuento_max = f.get("descuento_max")
        actual.margen_post = f.get("margen_post")
        actual.actualizado_por = usuario
        actual.actualizado_en = _now()
    if cambios:
        auditoria_service.registrar(
            db, accion="politica_precio_editada", entidad="politica_precio",
            usuario_email=usuario, detalle="; ".join(cambios)[:2000],
        )
    db.commit()
    return {"guardados": len(filas), "cambios": cambios}


def guardar_rubros(db: Session, filas: list[dict], usuario: str | None) -> dict:
    tenant = settings.default_tenant_id
    cambios: list[str] = []
    for f in filas:
        rubro = str(f.get("rubro") or "").strip()
        if not rubro:
            raise ValueError("Fila sin rubro")
        tipo = (f.get("tipo") or "").strip() or None
        proc = (f.get("procedencia_forzada") or "").strip() or None
        if proc and proc not in PROCEDENCIAS:
            raise ValueError(f"Procedencia forzada invalida para el rubro {rubro}: {proc}")
        actual = db.scalars(
            select(PoliticaRubro).where(
                PoliticaRubro.tenant_id == tenant, PoliticaRubro.rubro == rubro,
            )
        ).first()
        if actual is None:
            actual = PoliticaRubro(tenant_id=tenant, rubro=rubro)
            db.add(actual)
            cambios.append(f"rubro {rubro}: nuevo ({tipo}, {proc})")
        elif actual.tipo != tipo or actual.procedencia_forzada != proc:
            cambios.append(f"rubro {rubro}: ({actual.tipo}, {actual.procedencia_forzada}) -> ({tipo}, {proc})")
        actual.tipo = tipo
        actual.procedencia_forzada = proc
        actual.actualizado_por = usuario
        actual.actualizado_en = _now()
    if cambios:
        auditoria_service.registrar(
            db, accion="politica_rubro_editada", entidad="politica_rubro",
            usuario_email=usuario, detalle="; ".join(cambios)[:2000],
        )
    db.commit()
    return {"guardados": len(filas), "cambios": cambios}


def sembrar(db: Session, factores_: list[dict], rubros_: list[dict], usuario: str | None = None,
            reemplazar: bool = False) -> dict:
    """Primera carga desde el Excel. Si ya hay datos no toca nada, salvo `reemplazar`."""
    tenant = settings.default_tenant_id
    hay = db.scalar(select(PoliticaPrecio.id).where(PoliticaPrecio.tenant_id == tenant).limit(1))
    if hay and not reemplazar:
        return {"sembrado": False, "motivo": "la politica ya tiene datos"}
    if reemplazar:
        db.execute(delete(PoliticaPrecio).where(PoliticaPrecio.tenant_id == tenant))
        db.execute(delete(PoliticaRubro).where(PoliticaRubro.tenant_id == tenant))
        db.flush()
    n_f = n_r = 0
    for f in factores_:
        tipo = (f.get("tipo") or "").strip()
        # "nacional" y "Nacional" son lo mismo; el Excel trae las dos.
        proc = (f.get("procedencia") or "").strip().capitalize()
        try:
            factor = float(str(f.get("factor") or "").replace(",", "."))
        except ValueError:
            continue
        if not tipo or factor <= 0:
            continue
        # Un tipo con un solo factor para las dos procedencias viene con la
        # procedencia vacia en el Excel (Valvoline, Lubricante, Motorcraft): se
        # guarda como dos filas iguales, que es como lo lee el calculo.
        procs = PROCEDENCIAS if not proc else (proc,)
        if proc and proc not in PROCEDENCIAS:
            continue
        for p_ in procs:
            db.add(PoliticaPrecio(
                tenant_id=tenant, tipo=tipo, procedencia=p_, factor=factor,
                descuento_max=_num(f.get("descuento_max")), margen_post=_num(f.get("margen_post")),
                actualizado_por=usuario,
            ))
            n_f += 1
    for r in rubros_:
        rubro = str(r.get("rubro") or "").strip()
        if not rubro:
            continue
        db.add(PoliticaRubro(
            tenant_id=tenant, rubro=rubro,
            tipo=(r.get("tipo") or "").strip() or None,
            procedencia_forzada=(r.get("procedencia_forzada") or "").strip() or None,
            actualizado_por=usuario,
        ))
        n_r += 1
    db.commit()
    return {"sembrado": True, "factores": n_f, "rubros": n_r}


def _num(v) -> float | None:
    if v in (None, ""):
        return None
    try:
        return float(str(v).replace(",", "."))
    except ValueError:
        return None
