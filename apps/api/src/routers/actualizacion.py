"""Boton "Actualizar ahora": buzon entre la web y el PC que tiene los Excel.

El calculo del sugerido necesita los Excel de "Bases de datos", que viven en un PC de
la empresa, no en el servidor. Asi que la web no puede recalcular: solo puede DEJAR
PEDIDO que alguien lo haga. Este router es ese buzon.

    web  --POST /solicitar-->  [fila pendiente]  <--GET /pendiente--  agente (PC)
    web  <--GET /estado-----   [ok | error]      <--POST /terminar--  agente (PC)

El agente es un programa instalado en ese PC que pregunta cada minuto si hay algo
pendiente. No es una persona y no tiene login: se identifica con la cabecera
'X-Agente-Secret' (mismo criterio que el router de cron).

Por el mismo buzon pasan dos tipos de pedido (columna `tipo`):

- `recalcular`: correr el motor y publicar. Es el boton "Actualizar ahora" y el valor
  por defecto (la web vieja no manda cuerpo).
- `actualizar_motor`: que ese PC baje la ultima version del motor desde GitHub. No
  recalcula nada. Solo admin: cambia el programa que calcula para todo el equipo.

Nunca hay dos pedidos vivos a la vez, de ningun tipo: actualizar el motor mientras
corre un calculo cambiaria el programa a mitad de camino.

Reemplaza al esquema anterior, que abria el protocolo `sugerido://` del navegador: eso
solo funcionaba sentado en el PC del administrador y con una ventana de PowerShell a la
vista. Con el buzon, el boton sirve desde cualquier equipo o telefono.
"""
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Body, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import AuditoriaLog, SolicitudActualizacion, Usuario
from ..models.solicitud_actualizacion import (
    ACTIVOS,
    ACTUALIZAR_MOTOR,
    EN_CURSO,
    ERROR,
    EXPIRADA,
    OK,
    PENDIENTE,
    RECALCULAR,
)
from ..services import auditoria_service
from ..services.auth import puede_actualizar, requiere_actualizar, requiere_auth
from ..services.calendario import a_chile

router = APIRouter(prefix="/api/actualizacion", tags=["actualizacion"])
settings = get_settings()

# Si nadie la toma en este plazo, el PC que calcula esta apagado (o el agente caido).
# El agente pregunta cada minuto: 5 min es margen de sobra sin dejar a nadie esperando.
ESPERA_MAX_MIN = 5
# Pasado este plazo sin noticias de una solicitud tomada, algo se corto (se cerro la
# sesion de Windows, se apago el PC a mitad de camino) y no volvera a avisar.
# - recalcular: el motor tarda 22 a 35 min (medido en las corridas de octubre). Con
#   los 20 min de antes, una corrida sana se daba por muerta a la mitad, y la tarjeta
#   decia "nunca termino de avisar" mientras el motor seguia publicando.
# - actualizar_motor: un git fetch + merge, y a lo mas reinstalar dependencias.
CORRIDA_MAX_MIN = {RECALCULAR: 75, ACTUALIZAR_MOTOR: 15}

# Textos que llegan tal cual a la pantalla.
DURACION_TEXTO = {
    RECALCULAR: "Tarda entre 25 y 40 minutos",
    ACTUALIZAR_MOTOR: "Tarda 1 a 2 minutos",
}


def _verificar_agente(secret: str | None) -> None:
    if not settings.agente_secret or secret != settings.agente_secret:
        raise HTTPException(status_code=403, detail="No autorizado")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    """SQLite devuelve las fechas sin zona horaria; Postgres con ella. Sin esto, la
    comparacion de plazos revienta con 'can't compare naive and aware datetimes'."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _tipo(s: SolicitudActualizacion) -> str:
    return s.tipo or RECALCULAR


def _caducar(db: Session) -> None:
    """Cierra las solicitudes que quedaron colgadas.

    Sin esto una solicitud hecha con el PC apagado se queda "pendiente" para siempre:
    la tarjeta giraria sin fin y ademas bloquearia los intentos siguientes."""
    ahora = _now()
    cambios = False
    activas = db.scalars(
        select(SolicitudActualizacion).where(
            SolicitudActualizacion.tenant_id == settings.default_tenant_id,
            SolicitudActualizacion.estado.in_(ACTIVOS),
        )
    ).all()
    for s in activas:
        motor = _tipo(s) == ACTUALIZAR_MOTOR
        if s.estado == PENDIENTE:
            creado = _aware(s.creado_en) or ahora
            if ahora - creado > timedelta(minutes=ESPERA_MAX_MIN):
                s.estado = EXPIRADA
                s.terminado_en = ahora
                s.mensaje = (
                    "Nadie tomó la solicitud. El computador del motor está apagado, sin "
                    "conexión o sin sesión iniciada."
                    if motor else
                    "Nadie tomó la solicitud. El computador donde se calcula el "
                    "sugerido está apagado, sin conexión o sin sesión iniciada."
                )
                cambios = True
        elif s.estado == EN_CURSO:
            tomado = _aware(s.tomado_en) or _aware(s.creado_en) or ahora
            plazo = CORRIDA_MAX_MIN.get(_tipo(s), CORRIDA_MAX_MIN[RECALCULAR])
            if ahora - tomado > timedelta(minutes=plazo):
                s.estado = ERROR
                s.terminado_en = ahora
                s.mensaje = (
                    f"La actualización del motor empezó pero no avisó cómo terminó en "
                    f"{plazo} minutos. Revisa el computador del motor."
                    if motor else
                    f"El recálculo empezó pero no avisó cómo terminó en {plazo} minutos "
                    "(normalmente tarda entre 25 y 40). Revisa el computador donde se "
                    "calcula el sugerido."
                )
                cambios = True
    if cambios:
        db.commit()


def _ultima(db: Session) -> SolicitudActualizacion | None:
    return db.scalars(
        select(SolicitudActualizacion)
        .where(SolicitudActualizacion.tenant_id == settings.default_tenant_id)
        .order_by(desc(SolicitudActualizacion.creado_en))
        .limit(1)
    ).first()


def _vivas(db: Session) -> list[SolicitudActualizacion]:
    """Las solicitudes pendientes o en curso, la mas antigua primero."""
    return list(
        db.scalars(
            select(SolicitudActualizacion)
            .where(
                SolicitudActualizacion.tenant_id == settings.default_tenant_id,
                SolicitudActualizacion.estado.in_(ACTIVOS),
            )
            .order_by(SolicitudActualizacion.creado_en, SolicitudActualizacion.id)
        ).all()
    )


def _ultima_sincronizacion(db: Session) -> datetime | None:
    log = db.scalars(
        select(AuditoriaLog)
        .where(
            AuditoriaLog.tenant_id == settings.default_tenant_id,
            AuditoriaLog.accion.in_(("datos_sincronizados", "powerbi_sincronizado")),
        )
        .order_by(desc(AuditoriaLog.creado_en))
        .limit(1)
    ).first()
    return log.creado_en if log else None


def _payload(db: Session, s: SolicitudActualizacion | None, email: str) -> dict:
    return {
        "id": s.id if s else None,
        "tipo": _tipo(s) if s else None,
        "estado": s.estado if s else None,
        "mensaje": s.mensaje if s else None,
        "version": s.version if s else None,
        "solicitado_por": s.solicitado_por if s else None,
        "creado_en": s.creado_en if s else None,
        "terminado_en": s.terminado_en if s else None,
        "ultima_sincronizacion": _ultima_sincronizacion(db),
        "puede_actualizar": puede_actualizar(email, db),
    }


def _ocupado(viva: SolicitudActualizacion) -> str:
    """Por que no se acepta otra solicitud: lo que dice la pantalla con el 409."""
    hora = a_chile(viva.creado_en).strftime("%H:%M") if viva.creado_en else None
    if _tipo(viva) == ACTUALIZAR_MOTOR:
        que, pedido = "una actualización del motor", "pedida"
    else:
        que, pedido = "un recálculo", "pedido"
    desde = f" ({pedido} a las {hora})" if hora else ""
    estado = "esperando al computador del motor" if viva.estado == PENDIENTE else "en curso"
    return (
        f"Ya hay {que} {estado}{desde}. {DURACION_TEXTO[_tipo(viva)]}: espera a que "
        "termine para pedir otra cosa."
    )


# ------------------------------- lado de la web ------------------------------- #
class SolicitarRequest(BaseModel):
    tipo: Literal["recalcular", "actualizar_motor"] = RECALCULAR


@router.get("/estado")
def estado(db: Session = Depends(get_db), email: str = Depends(requiere_auth)) -> dict:
    """Como va la ultima solicitud. Lo consulta la tarjeta de la web cada pocos
    segundos mientras hay una en curso. Lo puede ver cualquier usuario: saber si los
    datos se estan recalculando no es informacion reservada."""
    _caducar(db)
    return _payload(db, _ultima(db), email)


@router.post("/solicitar")
def solicitar(
    payload: SolicitarRequest | None = Body(default=None),
    db: Session = Depends(get_db),
    email: str = Depends(requiere_actualizar),
) -> dict:
    """Deja pedida una actualizacion. No recalcula nada aca: eso lo hace el agente.

    Sin cuerpo es "recalcular" (la web de antes no manda nada). "actualizar_motor"
    exige admin. Si ya hay una solicitud viva, de cualquier tipo, responde 409: dos
    corridas del motor encoladas publicarian dos veces, y actualizar el motor mientras
    calcula le cambiaria el programa a mitad de camino."""
    tipo = payload.tipo if payload else RECALCULAR
    if tipo == ACTUALIZAR_MOTOR:
        user = db.get(Usuario, email)
        if not user or not user.es_admin or not user.activo:
            raise HTTPException(
                status_code=403,
                detail="Actualizar el motor es solo para administradores.",
            )

    _caducar(db)
    vivas = _vivas(db)
    if vivas:
        raise HTTPException(status_code=409, detail=_ocupado(vivas[0]))

    s = SolicitudActualizacion(
        tenant_id=settings.default_tenant_id, estado=PENDIENTE, tipo=tipo,
        solicitado_por=email,
    )
    db.add(s)
    try:
        db.commit()
    except IntegrityError:
        # Dos clics casi simultaneos pueden pasar los dos el control de arriba (cada
        # pedido corre en su hilo). La base admite una sola viva (indice
        # ux_solicitud_viva): la que guarda segunda recibe el mismo 409 que habria
        # recibido un segundo despues.
        db.rollback()
        vivas = _vivas(db)
        raise HTTPException(
            status_code=409,
            detail=_ocupado(vivas[0]) if vivas else (
                "Otra persona pidió algo al computador del motor en este mismo momento. "
                "Revisa el estado y vuelve a intentar si hace falta."
            ),
        )

    auditoria_service.registrar(
        db,
        accion=(
            "actualizacion_motor_solicitada" if tipo == ACTUALIZAR_MOTOR
            else "actualizacion_solicitada"
        ),
        entidad="sistema",
        usuario_email=email,
        detalle=(
            "Pidio actualizar el motor del PC titular desde la web"
            if tipo == ACTUALIZAR_MOTOR
            else "Pidio actualizar los datos desde la web"
        ),
    )
    db.commit()
    db.refresh(s)
    return {**_payload(db, s, email), "ya_en_curso": False}


# ------------------------------ lado del agente ------------------------------- #
class TerminarRequest(BaseModel):
    id: str
    ok: bool
    mensaje: str | None = None
    # "<sha corto> <rama>" del motor que quedo instalado (lo manda actualizar_motor).
    version: str | None = None


@router.get("/pendiente")
def pendiente(
    agente: str | None = None,
    x_agente_secret: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    """El agente pregunta si hay trabajo. Si lo hay, se lo lleva marcado 'en_curso'.

    La marca se hace con un UPDATE condicionado al estado: si dos agentes preguntan a
    la vez, solo uno se la lleva y el otro ve que no queda nada. (No se usa FOR UPDATE
    porque los tests corren sobre SQLite, que no lo soporta.)"""
    _verificar_agente(x_agente_secret)
    _caducar(db)
    s = db.scalars(
        select(SolicitudActualizacion)
        .where(
            SolicitudActualizacion.tenant_id == settings.default_tenant_id,
            SolicitudActualizacion.estado == PENDIENTE,
        )
        .order_by(SolicitudActualizacion.creado_en)
        .limit(1)
    ).first()
    if not s:
        return {"hay": False}

    res = db.execute(
        update(SolicitudActualizacion)
        .where(
            SolicitudActualizacion.id == s.id,
            SolicitudActualizacion.estado == PENDIENTE,
        )
        .values(estado=EN_CURSO, tomado_en=_now(), agente=agente)
    )
    db.commit()
    if not res.rowcount:
        return {"hay": False}  # se la llevo otro agente entremedio
    return {"hay": True, "id": s.id, "tipo": _tipo(s), "solicitado_por": s.solicitado_por}


@router.post("/terminar")
def terminar(
    payload: TerminarRequest,
    x_agente_secret: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    """El agente reporta como le fue. El mensaje se muestra tal cual en la web, asi
    que conviene que venga en lenguaje de usuario y no un traceback."""
    _verificar_agente(x_agente_secret)
    s = db.get(SolicitudActualizacion, payload.id)
    if not s:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    s.estado = OK if payload.ok else ERROR
    s.terminado_en = _now()
    s.mensaje = payload.mensaje
    if payload.version is not None:
        s.version = payload.version.strip()[:200] or None
    db.commit()
    return {"id": s.id, "estado": s.estado}
