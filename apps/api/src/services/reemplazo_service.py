"""Reemplazos de FORD: los publica el motor, los consulta el comprador.

Ver `models/reemplazo_ford.py` para que guarda y por que.
"""
from __future__ import annotations

from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import ReemplazoFord

settings = get_settings()

_LOTE = 1000


def _texto(v) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def reemplazar(db: Session, filas: list[dict]) -> dict:
    """Reemplaza la foto de reemplazos con la que acaba de calcular el motor.

    Cada fila: producto, reemplazado_por, reemplazado_por_ford, cadena,
    reemplaza_a (lista o texto), sucesor_confirmado, agrupado, aviso.
    """
    tenant = settings.default_tenant_id
    validas: list[dict] = []
    for f in filas:
        prod = _texto(f.get("producto"))
        if not prod:
            continue
        reemplaza_a = f.get("reemplaza_a")
        if isinstance(reemplaza_a, (list, tuple)):
            reemplaza_a = "; ".join(str(x).strip() for x in reemplaza_a if str(x).strip())
        # Una fila sin reemplazo en ninguna direccion no dice nada.
        if not _texto(f.get("reemplazado_por")) and not _texto(f.get("reemplazado_por_ford")) \
                and not _texto(reemplaza_a):
            continue
        validas.append({
            "tenant_id": tenant,
            "producto": prod,
            "reemplazado_por": _texto(f.get("reemplazado_por")),
            "reemplazado_por_ford": _texto(f.get("reemplazado_por_ford")),
            "cadena": _texto(f.get("cadena")),
            "reemplaza_a": _texto(reemplaza_a),
            "sucesor_confirmado": bool(f.get("sucesor_confirmado")),
            "agrupado": bool(f.get("agrupado")),
            "aviso": _texto(f.get("aviso")),
            "extraido_en": _texto(f.get("extraido_en")),
        })

    # Mismo criterio que el transito y el stock: una tanda vacia NO borra lo que
    # hay. Es mejor mostrar la foto anterior que decirle al comprador "este codigo
    # no tiene reemplazo" porque una corrida del motor fallo.
    if not validas:
        return {"filas_cargadas": 0, "ignoradas": len(filas), "reemplazo": False}

    db.execute(delete(ReemplazoFord).where(ReemplazoFord.tenant_id == tenant))
    for i in range(0, len(validas), _LOTE):
        db.execute(insert(ReemplazoFord), validas[i : i + _LOTE])
    db.commit()
    return {
        "filas_cargadas": len(validas),
        "ignoradas": len(filas) - len(validas),
        "reemplazo": True,
    }


def _fila(r: ReemplazoFord) -> dict:
    return {
        "producto": r.producto,
        "reemplazado_por": r.reemplazado_por,
        "reemplazado_por_ford": r.reemplazado_por_ford,
        "cadena": r.cadena,
        "reemplaza_a": [x.strip() for x in (r.reemplaza_a or "").split(";") if x.strip()],
        "sucesor_confirmado": bool(r.sucesor_confirmado),
        "agrupado": bool(r.agrupado),
        "aviso": r.aviso,
        "extraido_en": r.extraido_en,
    }


def por_producto(db: Session, productos: set[str]) -> dict[str, dict]:
    """{producto: fila} para los codigos pedidos.

    Tolerante a que la tabla no exista todavia: mientras el motor no corra una vez
    con el cambio, las pantallas no muestran reemplazo en vez de reventar.
    """
    if not productos:
        return {}
    try:
        filas = db.scalars(
            select(ReemplazoFord).where(ReemplazoFord.producto.in_(productos))
        ).all()
        return {r.producto: _fila(r) for r in filas}
    except Exception:  # noqa: BLE001 - tabla ausente antes de la primera corrida
        db.rollback()
        return {}


def de_producto(db: Session, producto: str) -> dict | None:
    """El reemplazo de UN producto, o None si no tiene."""
    return por_producto(db, {producto}).get(producto)


def miembros_del_grupo(db: Session, producto: str) -> list[str]:
    """Todos los codigos del grupo de reemplazos de `producto`, vigente primero.

    Entrando por CUALQUIER miembro devuelve el grupo entero, y esa es la razon de
    ser de la funcion. Con los equivalentes del mix ya paso lo contrario: el motor
    escribe la lista solo en la fila del master, asi que entrando por otro miembro
    parecia que el producto no tenia reemplazos (ver
    `catalogo_service.py::_reemplazos`, que existe por eso).

    Aca hay dos direcciones que mirar:
      - la fila del propio codigo, si esta dado de baja (`reemplazado_por`)
      - la fila del vigente, que lista en `reemplaza_a` a todos los que reemplazo

    Devuelve [] cuando el codigo no tiene reemplazos: la pantalla no muestra nada
    en vez de una tabla de una sola fila, que no dice nada.
    """
    fila = de_producto(db, producto)
    if not fila:
        return []
    # El vigente del grupo: el que este codigo apunta, o el codigo mismo si ya
    # es el vigente.
    vigente = fila.get("reemplazado_por") or producto
    grupo = {producto, vigente}
    # Los predecesores viven en la fila del vigente, no en la del viejo.
    fila_vigente = de_producto(db, vigente) if vigente != producto else fila
    if fila_vigente:
        grupo.update(fila_vigente.get("reemplaza_a") or [])
    grupo.discard("")
    # El vigente primero; el resto alfabetico, para que dos cargas de la misma
    # ficha muestren la tabla en el mismo orden.
    otros = sorted(c for c in grupo if c != vigente)
    return [vigente, *otros]
