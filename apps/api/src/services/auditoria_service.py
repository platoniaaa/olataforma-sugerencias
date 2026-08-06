"""Helpers para registrar eventos en `auditoria_log` y disparar notificaciones in-app.

Pensado para que los endpoints solo llamen `registrar(...)` y opcionalmente `notificar(...)`
en un par de lineas. No interrumpe el flujo principal si falla (los logs no deben
romper la accion del usuario).
"""
from __future__ import annotations

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import AuditoriaLog, Notificacion

settings = get_settings()


def registrar(
    db: Session,
    *,
    accion: str,
    entidad: str,
    entidad_id: str | None = None,
    usuario_email: str | None = None,
    producto: str | None = None,
    sucursal_id: str | None = None,
    unidades: int | None = None,
    dias_inventario: int | None = None,
    motivo: str | None = None,
    detalle: str | None = None,
) -> AuditoriaLog | None:
    try:
        log = AuditoriaLog(
            tenant_id=settings.default_tenant_id,
            accion=accion,
            entidad=entidad,
            entidad_id=entidad_id,
            usuario_email=usuario_email,
            producto=producto,
            sucursal_id=sucursal_id,
            unidades=unidades,
            dias_inventario=dias_inventario,
            motivo=motivo,
            detalle=detalle,
        )
        # SAVEPOINT: si el INSERT falla (tabla vieja, columna que falta tras un
        # deploy), el error queda CONTENIDO. Sin esto la sesion queda en
        # pending-rollback y el db.commit() del endpoint revienta con un 500
        # DESPUES de que la accion principal ya se guardo: el usuario ve un error,
        # reintenta, y termina con un requerimiento duplicado. Un db.rollback()
        # a secas tampoco sirve: se llevaria por delante lo que el endpoint
        # todavia no commitea.
        with db.begin_nested():
            db.add(log)
        return log
    except Exception:
        # Auditoria no debe romper la accion principal.
        return None


def notificar(
    db: Session,
    *,
    tipo: str,
    titulo: str,
    mensaje: str | None = None,
    creado_por_email: str | None = None,
    producto: str | None = None,
    sucursal_id: str | None = None,
    para_email: str | None = None,
) -> Notificacion | None:
    try:
        n = Notificacion(
            tenant_id=settings.default_tenant_id,
            tipo=tipo,
            titulo=titulo,
            mensaje=mensaje,
            creado_por_email=creado_por_email,
            producto=producto,
            sucursal_id=sucursal_id,
            para_email=para_email,
            vistas_por="",
        )
        # Mismo SAVEPOINT que en `registrar`, y por la misma razon.
        with db.begin_nested():
            db.add(n)
        return n
    except Exception:
        return None


def listar_auditoria(
    db: Session,
    *,
    accion: str | None = None,
    excluir_acciones: list[str] | None = None,
    solo_de: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[AuditoriaLog], int]:
    """Pagina del log. `solo_de` limita a lo que hizo ESE usuario.

    Lo usa el vendedor de sucursal: la auditoria del equipo de compras -quien
    cargo que, quien creo o borro sugerencias, quien edito usuarios- no es asunto
    suyo, y hasta ahora la veia completa.
    """
    base = select(AuditoriaLog).where(
        AuditoriaLog.tenant_id == settings.default_tenant_id
    )
    if accion is not None:
        base = base.where(AuditoriaLog.accion == accion)
    if excluir_acciones:
        base = base.where(AuditoriaLog.accion.not_in(excluir_acciones))
    if solo_de:
        base = base.where(AuditoriaLog.usuario_email == solo_de)
    # COUNT en la base. Antes se traian TODAS las filas a memoria solo para
    # contarlas (`len(db.scalars(base).all())`): el log crece sin techo y esa
    # consulta se paga entera en cada carga de la pantalla.
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = list(
        db.scalars(
            base.order_by(desc(AuditoriaLog.creado_en)).offset(offset).limit(limit)
        ).all()
    )
    return rows, total


def _visibles_para(usuario_email: str, solo_personales: bool):
    """Filtro de visibilidad: lo del equipo + lo dirigido a MI.

    `solo_personales` es para el vendedor de sucursal: a el no le interesan los
    avisos del equipo de compras (sugerencias creadas, cargas), solo los suyos.
    """
    from sqlalchemy import or_

    if solo_personales:
        return Notificacion.para_email == usuario_email
    return or_(Notificacion.para_email.is_(None), Notificacion.para_email == usuario_email)


def listar_notificaciones(
    db: Session, *, usuario_email: str, solo_no_leidas: bool = False, limit: int = 50,
    solo_personales: bool = False,
) -> list[Notificacion]:
    rows = list(
        db.scalars(
            select(Notificacion)
            .where(
                Notificacion.tenant_id == settings.default_tenant_id,
                _visibles_para(usuario_email, solo_personales),
            )
            .order_by(desc(Notificacion.creado_en))
            .limit(limit if not solo_no_leidas else limit * 3)
        ).all()
    )
    if solo_no_leidas:
        rows = [n for n in rows if usuario_email not in _vistas_set(n.vistas_por)][:limit]
    return rows


def contar_no_leidas(db: Session, *, usuario_email: str, solo_personales: bool = False) -> int:
    rows = list(
        db.scalars(
            select(Notificacion).where(
                Notificacion.tenant_id == settings.default_tenant_id,
                _visibles_para(usuario_email, solo_personales),
            )
        ).all()
    )
    return sum(1 for n in rows if usuario_email not in _vistas_set(n.vistas_por))


def marcar_leidas(db: Session, *, usuario_email: str, ids: list[str] | None = None) -> int:
    """Marca como leida(s) por el usuario. Si ids=None, marca todas."""
    stmt = select(Notificacion).where(
        Notificacion.tenant_id == settings.default_tenant_id
    )
    if ids:
        stmt = stmt.where(Notificacion.id.in_(ids))
    n_actualizadas = 0
    for n in db.scalars(stmt).all():
        vistos = _vistas_set(n.vistas_por)
        if usuario_email not in vistos:
            vistos.add(usuario_email)
            n.vistas_por = ",".join(sorted(vistos))
            n_actualizadas += 1
    db.commit()
    return n_actualizadas


def _vistas_set(csv: str | None) -> set[str]:
    if not csv:
        return set()
    return {e.strip() for e in csv.split(",") if e.strip()}
