"""Endpoints de autenticacion: login y datos del usuario actual."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Usuario
from ..services import auth, auditoria_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    token: str
    email: str
    nombre: str | None = None
    es_admin: bool = False
    solo_lectura: bool = False
    puede_calibrar: bool = False
    puede_actualizar: bool = False
    # Puede editar la lista de precios (fijar, congelar, crear productos).
    puede_precios: bool = False
    # Vendedor de sucursal: la interfaz se recorta a armar y seguir requerimientos.
    es_vendedor: bool = False
    # Sus sucursales, para no preguntarselas al armar el carro.
    sucursales: list[str] = []


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    email = payload.email.strip().lower()
    usuario = db.get(Usuario, email)
    if not usuario or not usuario.activo or not auth.verify_password(payload.password, usuario.password_hash):
        raise HTTPException(status_code=401, detail="Correo o contraseña incorrectos")
    # Registrar el acceso para la vista de auditoria (quien entro y a que hora).
    auditoria_service.registrar(
        db, accion="login", entidad="sesion", usuario_email=email,
        detalle=usuario.nombre,
    )
    db.commit()
    return LoginResponse(
        token=auth.crear_token(email), email=email, nombre=usuario.nombre,
        es_admin=usuario.es_admin, solo_lectura=usuario.solo_lectura,
        puede_calibrar=auth.puede_calibrar(email, db),
        puede_actualizar=auth.puede_actualizar(email, db),
        puede_precios=auth.puede_precios(email, db),
        es_vendedor=bool(getattr(usuario, "es_vendedor", False)),
        sucursales=auth.sucursales_del_vendedor(email, db),
    )


@router.get("/me")
def me(email: str = Depends(auth.requiere_auth), db: Session = Depends(get_db)):
    usuario = db.get(Usuario, email)
    return {
        "email": email,
        "nombre": usuario.nombre if usuario else None,
        "es_admin": bool(usuario and usuario.es_admin),
        "solo_lectura": bool(usuario and usuario.solo_lectura),
        "puede_calibrar": auth.puede_calibrar(email, db),
        "puede_actualizar": auth.puede_actualizar(email, db),
        "puede_precios": auth.puede_precios(email, db),
        "es_vendedor": bool(usuario and getattr(usuario, "es_vendedor", False)),
        "sucursales": auth.sucursales_del_vendedor(email, db),
    }
