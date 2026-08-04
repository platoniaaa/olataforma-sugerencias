"""Administracion de usuarios. Solo admin.

Hasta ahora los usuarios se creaban con acceso directo a la base: no habia
endpoint ni script en el repo. Eso dejo la plataforma en una situacion incomoda
-la vista de vendedor quedo desplegada pero inerte, porque no habia forma de
crear un vendedor sin la cadena de conexion de Supabase, que vive solo en el
panel de Render-.

Con esto la administracion de usuarios es parte de la plataforma, igual que la
carga de la lista InStock.

Que NO hace, a proposito:

- No devuelve el hash de la contrasena en ninguna respuesta.
- No borra usuarios: los desactiva. Un usuario borrado se lleva por delante la
  trazabilidad de todo lo que creo (sugerencias, requerimientos, auditoria).
- No deja que un admin se quite a si mismo el admin ni se desactive: es la forma
  clasica de quedarse sin ningun administrador y sin manera de volver a entrar.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Usuario
from ..schemas import UsuarioCrear, UsuarioOut
from ..services import auditoria_service
from ..services.auth import hash_password, requiere_admin

router = APIRouter(prefix="/api/admin/usuarios", tags=["usuarios"])

# Suficiente para que no sea trivial y sin exigir un gestor de contrasenas a un
# vendedor de sucursal que entra desde el mesón.
LARGO_MINIMO_CLAVE = 8


def _a_out(u: Usuario) -> dict:
    import json

    try:
        sucursales = json.loads(u.sucursales_permitidas) if u.sucursales_permitidas else []
    except (ValueError, TypeError):
        sucursales = []
    return {
        "email": u.email,
        "nombre": u.nombre,
        "activo": u.activo,
        "es_admin": u.es_admin,
        "solo_lectura": u.solo_lectura,
        "es_vendedor": bool(getattr(u, "es_vendedor", False)),
        "sucursales": [str(s) for s in sucursales if s],
        "creado_en": u.creado_en,
    }


@router.get("", response_model=list[UsuarioOut])
def listar(db: Session = Depends(get_db)):
    """Quienes tienen acceso y con que rol. Nunca incluye la contrasena."""
    filas = db.scalars(select(Usuario).order_by(Usuario.email)).all()
    return [_a_out(u) for u in filas]


@router.post("", response_model=UsuarioOut)
def crear_o_actualizar(
    payload: UsuarioCrear,
    email_admin: str = Depends(requiere_admin),
    db: Session = Depends(get_db),
):
    """Crea el usuario, o actualiza el que ya exista con ese correo.

    Es idempotente por correo a proposito: volver a mandar el mismo usuario
    corrige sus datos en vez de fallar con un "ya existe" que obligaria a mirar
    la base para saber que hay.
    """
    import json

    email = (payload.email or "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="El correo no es válido.")

    # Las validaciones que dependen de QUIEN llama van ANTES de tocar nada. Si se
    # hacen despues, el objeto queda mutado en la sesion aunque la peticion
    # termine en 400: no se persiste, pero es una bomba esperando a que alguien
    # agregue un commit mas arriba.
    if email == email_admin.strip().lower():
        if payload.es_admin is False:
            raise HTTPException(
                status_code=400, detail="No puedes quitarte a ti mismo el permiso de admin."
            )
        if payload.activo is False:
            raise HTTPException(status_code=400, detail="No puedes desactivarte a ti mismo.")

    usuario = db.get(Usuario, email)
    nuevo = usuario is None

    if nuevo:
        if not payload.password:
            raise HTTPException(
                status_code=400, detail="Un usuario nuevo necesita una contraseña."
            )
        usuario = Usuario(email=email, password_hash="")
        db.add(usuario)

    if payload.password:
        if len(payload.password) < LARGO_MINIMO_CLAVE:
            raise HTTPException(
                status_code=400,
                detail=f"La contraseña tiene que tener al menos {LARGO_MINIMO_CLAVE} caracteres.",
            )
        usuario.password_hash = hash_password(payload.password)

    if payload.nombre is not None:
        usuario.nombre = payload.nombre.strip() or None
    if payload.es_admin is not None:
        usuario.es_admin = payload.es_admin
    if payload.solo_lectura is not None:
        usuario.solo_lectura = payload.solo_lectura
    if payload.es_vendedor is not None:
        usuario.es_vendedor = payload.es_vendedor
    if payload.activo is not None:
        usuario.activo = payload.activo
    if payload.sucursales is not None:
        sucursales = [s.strip() for s in payload.sucursales if s and s.strip()]
        usuario.sucursales_permitidas = json.dumps(sucursales) if sucursales else None

    # Un vendedor sin sucursal no puede pedir por ninguna: el backend lo rechaza
    # al crear el requerimiento. Mejor no dejar crear el usuario asi que
    # descubrirlo cuando el vendedor ya esta adentro y no puede hacer nada.
    if usuario.es_vendedor and not usuario.sucursales_permitidas:
        # `expunge` en el alta y `rollback` en la edicion: en los dos casos la
        # sesion tiene que quedar como estaba antes de esta peticion.
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="Un vendedor necesita al menos una sucursal asignada.",
        )

    auditoria_service.registrar(
        db,
        accion="usuario_creado" if nuevo else "usuario_actualizado",
        entidad="usuario",
        entidad_id=email,
        usuario_email=email_admin,
        detalle=(
            f"vendedor={usuario.es_vendedor} admin={usuario.es_admin} "
            f"activo={usuario.activo}"
        ),
    )
    db.commit()
    db.refresh(usuario)
    return _a_out(usuario)


@router.post("/{email}/desactivar", response_model=UsuarioOut)
def desactivar(
    email: str,
    email_admin: str = Depends(requiere_admin),
    db: Session = Depends(get_db),
):
    """Le quita el acceso sin borrarlo.

    Borrarlo se llevaria por delante la trazabilidad de todo lo que creo: quien
    cargo cada sugerencia, quien mando cada requerimiento.
    """
    email = email.strip().lower()
    if email == email_admin.strip().lower():
        raise HTTPException(status_code=400, detail="No puedes desactivarte a ti mismo.")
    usuario = db.get(Usuario, email)
    if not usuario:
        raise HTTPException(status_code=404, detail="Ese usuario no existe.")
    usuario.activo = False
    auditoria_service.registrar(
        db,
        accion="usuario_desactivado",
        entidad="usuario",
        entidad_id=email,
        usuario_email=email_admin,
    )
    db.commit()
    db.refresh(usuario)
    return _a_out(usuario)
