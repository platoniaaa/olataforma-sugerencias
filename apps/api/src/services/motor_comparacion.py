"""Compara el sugerido del motor propio contra el que esta vivo (Power BI).

El motor corre en la maquina del usuario, produce un CSV con EL MISMO contrato
que la extraccion del Power BI y lo manda aca. Esto lo parsea con el mismo lector
de siempre, lo contrasta contra la tabla `sugerido` y guarda un reporte.

**No escribe una sola fila en `sugerido`.** Es la garantia de que probar el motor
no puede alterar lo que ven los compradores: hasta que la paridad se sostenga,
la unica fuente sigue siendo el Power BI.
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import ComparacionMotor, Sugerido
from . import excel_loader

settings = get_settings()

# Columnas que definen si el motor "acerto". Son las que mueven una decision de
# compra; el resto (descripciones, nombres) no cambia lo que se pide.
COLUMNAS_COMPARADAS = (
    "total_sugerido_suc",
    "sugerido_compra_neto",
    "sugerido_traslado",
    "stock_activo_suc",
    "stock_en_transito_suc",
    "stock_en_cd",
    "punto_de_pedido",
    "stock_seguridad",
    "demanda_diaria",
    "lead_time_dias",
    "clasificacion_abc",
    "proveedor",
    "pedir",
)

# Tolerancia para numeros: media unidad absorbe diferencias de redondeo entre
# DAX y Python sin tapar un error real de calculo.
TOLERANCIA = 0.5
# Cuantas divergencias se guardan para diagnosticar (no hace falta el listado entero).
MAX_EJEMPLOS = 50


def _igual(a: Any, b: Any) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        # "Sin dato" y "cero" son el MISMO hecho de negocio: el modelo deja la
        # medida en blanco cuando no hay nada y el motor emite 0. Tratarlos como
        # distintos inflaba las diferencias al 100% en columnas como el transito
        # (18.910 filas en blanco contra 25.205 ceros) y tapaba las reales.
        otro = b if a is None else a
        return isinstance(otro, (int, float)) and not isinstance(otro, bool) and float(otro) == 0
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) <= TOLERANCIA
    return str(a).strip().lower() == str(b).strip().lower()


def comparar(db: Session, contenido: bytes, filename: str = "motor.csv") -> dict:
    """Parsea el CSV/Excel del motor y lo contrasta contra la tabla `sugerido`."""
    name = (filename or "").lower()
    if name.endswith(".csv"):
        headers, data = excel_loader._rows_from_csv(contenido)
    elif name.endswith((".xlsx", ".xlsm")):
        headers, data = excel_loader._rows_from_xlsx(contenido)
    else:
        raise ValueError("Formato no soportado. Usa .xlsx o .csv")

    registros = [dict(zip(headers, raw)) for raw in data]
    filas_motor, _detectadas, _ignoradas = excel_loader.procesar_registros(registros)
    if not filas_motor:
        raise ValueError("El archivo del motor no trae filas validas.")

    motor: dict[tuple[str, str], dict] = {}
    for f in filas_motor:
        p, s = f.get("producto"), f.get("sucursal_id")
        if p and s:
            motor[(str(p), str(s))] = f

    columnas = [getattr(Sugerido, c) for c in COLUMNAS_COMPARADAS]
    bi_rows = db.execute(
        select(Sugerido.producto, Sugerido.sucursal_id, *columnas).where(
            Sugerido.tenant_id == settings.default_tenant_id
        )
    ).all()
    bi = {
        (str(r.producto), str(r.sucursal_id)): {c: getattr(r, c) for c in COLUMNAS_COMPARADAS}
        for r in bi_rows
    }

    comunes = motor.keys() & bi.keys()
    solo_motor = motor.keys() - bi.keys()
    solo_bi = bi.keys() - motor.keys()

    por_columna = {c: {"iguales": 0, "distintas": 0} for c in COLUMNAS_COMPARADAS}
    ejemplos: list[dict] = []
    filas_identicas = 0

    for clave in comunes:
        fm, fb = motor[clave], bi[clave]
        difs = {}
        for c in COLUMNAS_COMPARADAS:
            if _igual(fm.get(c), fb.get(c)):
                por_columna[c]["iguales"] += 1
            else:
                por_columna[c]["distintas"] += 1
                difs[c] = {"motor": fm.get(c), "bi": fb.get(c)}
        if difs:
            if len(ejemplos) < MAX_EJEMPLOS:
                ejemplos.append(
                    {"producto": clave[0], "sucursal_id": clave[1], "diferencias": difs}
                )
        else:
            filas_identicas += 1

    paridad = round(filas_identicas / len(comunes) * 100, 2) if comunes else 0.0
    # Las divergencias mas caras primero: sirve mas revisar un sugerido de 400
    # unidades que uno de 1.
    ejemplos.sort(
        key=lambda e: abs(
            float(e["diferencias"].get("total_sugerido_suc", {}).get("motor") or 0)
            - float(e["diferencias"].get("total_sugerido_suc", {}).get("bi") or 0)
        ),
        reverse=True,
    )

    return {
        "filas_motor": len(motor),
        "filas_bi": len(bi),
        "filas_comunes": len(comunes),
        "filas_solo_motor": len(solo_motor),
        "filas_solo_bi": len(solo_bi),
        "filas_identicas": filas_identicas,
        "paridad_pct": paridad,
        "por_columna": por_columna,
        "ejemplos": ejemplos,
        "ejemplos_solo_motor": sorted(f"{p} / {s}" for p, s in solo_motor)[:20],
        "ejemplos_solo_bi": sorted(f"{p} / {s}" for p, s in solo_bi)[:20],
    }


def guardar(db: Session, resultado: dict, usuario_email: str | None = None) -> ComparacionMotor:
    rep = ComparacionMotor(
        tenant_id=settings.default_tenant_id,
        filas_motor=resultado["filas_motor"],
        filas_bi=resultado["filas_bi"],
        filas_comunes=resultado["filas_comunes"],
        filas_solo_motor=resultado["filas_solo_motor"],
        filas_solo_bi=resultado["filas_solo_bi"],
        paridad_pct=resultado["paridad_pct"],
        detalle=json.dumps(
            {
                "por_columna": resultado["por_columna"],
                "ejemplos": resultado["ejemplos"],
                "ejemplos_solo_motor": resultado["ejemplos_solo_motor"],
                "ejemplos_solo_bi": resultado["ejemplos_solo_bi"],
            },
            ensure_ascii=False,
            default=str,
        ),
        ejecutado_por=usuario_email,
    )
    db.add(rep)
    db.commit()
    db.refresh(rep)
    return rep


def ultimas(db: Session, limit: int = 10) -> list[dict]:
    """Historial de comparaciones, la mas reciente primero."""
    rows = db.scalars(
        select(ComparacionMotor)
        .where(ComparacionMotor.tenant_id == settings.default_tenant_id)
        .order_by(desc(ComparacionMotor.creado_en))
        .limit(limit)
    ).all()
    salida = []
    for r in rows:
        salida.append({
            "id": r.id,
            "creado_en": r.creado_en,
            "filas_motor": r.filas_motor,
            "filas_bi": r.filas_bi,
            "filas_comunes": r.filas_comunes,
            "filas_solo_motor": r.filas_solo_motor,
            "filas_solo_bi": r.filas_solo_bi,
            "paridad_pct": r.paridad_pct,
            "ejecutado_por": r.ejecutado_por,
            "detalle": json.loads(r.detalle) if r.detalle else None,
        })
    return salida
