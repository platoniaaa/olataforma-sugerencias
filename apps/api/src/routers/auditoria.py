"""Endpoints de auditoria (log de acciones) y notificaciones in-app."""
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import AuditoriaLog
from ..schemas import (
    AuditoriaLogOut,
    AuditoriaPage,
    MarcarLeidasRequest,
    NotificacionesResponse,
    NotificacionOut,
)
from ..services import auditoria_service
from ..services.auth import requiere_auth, requiere_ver_accesos

router = APIRouter(tags=["auditoria"])
settings = get_settings()


def _dias_habiles_entre(desde: date, hasta: date) -> int:
    """Dias habiles transcurridos entre dos fechas (sabados y domingos no cuentan).

    Se cuenta en dias HABILES y no en horas porque la tarea corre de lunes a
    viernes: contando horas, todos los lunes avisaria que los datos son "de hace
    3 dias" cuando en realidad la ultima corrida fue la que correspondia. Un aviso
    que se equivoca todos los lunes es un aviso que nadie mira.
    """
    if hasta <= desde:
        return 0
    dias = 0
    cursor = desde
    while cursor < hasta:
        cursor += timedelta(days=1)
        if cursor.weekday() < 5:  # 0=lunes .. 4=viernes
            dias += 1
    return dias


# A partir de cuantos dias habiles sin cargar se considera desactualizado. Con 2
# se avisa recien cuando se perdio una corrida completa: el dia siguiente a una
# carga normal da 1 y no molesta.
DIAS_HABILES_PARA_AVISAR = 2


@router.get("/api/ultima-sincronizacion")
def ultima_sync(db: Session = Depends(get_db)):
    """Timestamp de la ultima carga del sugerido, sea cual sea su origen.

    Acepta el sello nuevo del motor (`datos_sincronizados`) y el historico del
    Power BI (`powerbi_sincronizado`), y devuelve el mas reciente. Asi la etiqueta
    "Datos actualizados" refleja la carga real y no queda pegada en la ultima
    corrida del BI.

    Devuelve ademas `desactualizado`: la tarea diaria puede fallar —o no llegar a
    correr— sin que nadie se entere, y el equipo sigue comprando sobre datos
    viejos. Paso del 31-jul al 03-ago-2026: dos dias habiles con el sugerido
    congelado en la foto del 30-jul. El aviso se calcula aca, del lado del
    servidor, para que no dependa de que el job que fallo alcance a avisar.
    """
    log = db.scalars(
        select(AuditoriaLog)
        .where(
            AuditoriaLog.tenant_id == settings.default_tenant_id,
            AuditoriaLog.accion.in_(("datos_sincronizados", "powerbi_sincronizado")),
        )
        .order_by(desc(AuditoriaLog.creado_en))
        .limit(1)
    ).first()
    if not log:
        return {"creado_en": None, "detalle": None,
                "dias_habiles": None, "desactualizado": False}
    dias = _dias_habiles_entre(log.creado_en.date(), datetime.now(timezone.utc).date())
    return {
        "creado_en": log.creado_en,
        "detalle": log.detalle,
        "dias_habiles": dias,
        "desactualizado": dias >= DIAS_HABILES_PARA_AVISAR,
    }


@router.get("/api/auditoria", response_model=AuditoriaPage)
def listar(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    # Los accesos (login) van en su propia vista, restringida. No mezclarlos aca.
    rows, total = auditoria_service.listar_auditoria(
        db, excluir_acciones=["login"], limit=limit, offset=offset
    )
    return AuditoriaPage(
        items=[AuditoriaLogOut.model_validate(r) for r in rows],
        total=total, limit=limit, offset=offset,
    )


@router.get("/api/auditoria/accesos", response_model=AuditoriaPage)
def listar_accesos(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _email: str = Depends(requiere_ver_accesos),
):
    """Quien inicio sesion y a que hora. Solo admin o emails autorizados."""
    rows, total = auditoria_service.listar_auditoria(
        db, accion="login", limit=limit, offset=offset
    )
    return AuditoriaPage(
        items=[AuditoriaLogOut.model_validate(r) for r in rows],
        total=total, limit=limit, offset=offset,
    )


@router.get("/api/notificaciones", response_model=NotificacionesResponse)
def listar_notificaciones(
    solo_no_leidas: bool = Query(False),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    email: str = Depends(requiere_auth),
):
    rows = auditoria_service.listar_notificaciones(
        db, usuario_email=email, solo_no_leidas=solo_no_leidas, limit=limit
    )
    no_leidas = auditoria_service.contar_no_leidas(db, usuario_email=email)
    items: list[NotificacionOut] = []
    for n in rows:
        vistos = {e.strip() for e in (n.vistas_por or "").split(",") if e.strip()}
        items.append(
            NotificacionOut(
                id=n.id, tipo=n.tipo, titulo=n.titulo, mensaje=n.mensaje,
                creado_por_email=n.creado_por_email, producto=n.producto,
                sucursal_id=n.sucursal_id, creado_en=n.creado_en,
                leida=email in vistos,
            )
        )
    return NotificacionesResponse(items=items, no_leidas=no_leidas)


@router.post("/api/notificaciones/marcar-leidas")
def marcar_leidas(
    payload: MarcarLeidasRequest,
    db: Session = Depends(get_db),
    email: str = Depends(requiere_auth),
):
    n = auditoria_service.marcar_leidas(db, usuario_email=email, ids=payload.ids)
    return {"actualizadas": n}
