"""Autenticacion simple (email + contrasena) sin dependencias externas.

- Hash de contrasena con PBKDF2-HMAC-SHA256 (stdlib `hashlib`), con salt por usuario.
- Token de sesion firmado con HMAC-SHA256 (estilo JWT HS256), con expiracion.

Sin paquetes nuevos -> cero riesgo de instalacion en local o en la nube.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

from fastapi import Depends, Header, HTTPException

from ..config import get_settings
from ..db import get_db

settings = get_settings()

_PBKDF2_ITER = 200_000


# --------------------------- contrasenas --------------------------- #
def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ITER)
    return base64.b64encode(salt).decode() + "$" + base64.b64encode(dk).decode()


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_b64, dk_b64 = stored.split("$")
        salt = base64.b64decode(salt_b64)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ITER)
        return hmac.compare_digest(base64.b64encode(dk).decode(), dk_b64)
    except Exception:
        return False


# --------------------------- tokens --------------------------- #
def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def crear_token(email: str) -> str:
    payload = {"sub": email, "exp": int(time.time()) + settings.token_horas * 3600}
    body = _b64(json.dumps(payload).encode())
    sig = _b64(hmac.new(settings.auth_secret.encode(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def verificar_token(token: str) -> str | None:
    try:
        body, sig = token.split(".")
        esperado = _b64(
            hmac.new(settings.auth_secret.encode(), body.encode(), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(sig, esperado):
            return None
        payload = json.loads(_unb64(body))
        if payload.get("exp", 0) < time.time():
            return None
        return payload.get("sub")
    except Exception:
        return None


# --------------------------- dependencia FastAPI --------------------------- #
def requiere_auth(authorization: str | None = Header(default=None)) -> str:
    """Valida el header Authorization: Bearer <token>. Devuelve el email."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="No autenticado")
    email = verificar_token(authorization[7:])
    if not email:
        raise HTTPException(status_code=401, detail="Sesion invalida o expirada")
    return email


def requiere_admin(email: str = Depends(requiere_auth), db=Depends(get_db)) -> str:
    """Bloquea endpoints reservados a admin. Devuelve el email si es admin."""
    from ..models import Usuario  # import local para evitar ciclo

    user = db.get(Usuario, email)
    if not user or not user.es_admin:
        raise HTTPException(status_code=403, detail="Requiere permisos de admin")
    return email


def requiere_escritura(email: str = Depends(requiere_auth), db=Depends(get_db)) -> str:
    """Bloquea operaciones de escritura para usuarios de solo lectura. Devuelve el email.

    Se usa en los endpoints que crean/editan/borran (ej. sugerencias manuales): un
    usuario `solo_lectura` puede ver todo pero no modificar nada."""
    from ..models import Usuario  # import local para evitar ciclo

    user = db.get(Usuario, email)
    if user and user.solo_lectura:
        raise HTTPException(
            status_code=403,
            detail="Tu usuario es de solo lectura: no puede crear ni modificar sugerencias.",
        )
    return email


def sucursales_permitidas(email: str = Depends(requiere_auth), db=Depends(get_db)) -> list[str] | None:
    """Sucursales (sucursal_id) que el usuario puede ver, o None si ve TODAS.

    Se inyecta en los endpoints del sugerido/compras para restringir por sucursal.
    Un valor vacío o mal formado se trata como sin restricción (ve todas)."""
    from ..models import Usuario  # import local para evitar ciclo

    user = db.get(Usuario, email)
    if not user or not user.sucursales_permitidas:
        return None
    try:
        vals = json.loads(user.sucursales_permitidas)
    except (ValueError, TypeError):
        return None
    vals = [str(v) for v in vals if v] if isinstance(vals, list) else []
    return vals or None


# --------------------------- vendedor de sucursal --------------------------- #
def es_vendedor(email: str, db) -> bool:
    """True si el usuario es un vendedor de sucursal (no de abastecimiento)."""
    from ..models import Usuario  # import local para evitar ciclo

    user = db.get(Usuario, email)
    return bool(user and getattr(user, "es_vendedor", False))


def requiere_vendedor(email: str = Depends(requiere_auth), db=Depends(get_db)) -> str:
    """Endpoints que solo tienen sentido para un vendedor (armar su requerimiento).

    El admin tambien pasa: si no, nadie podria probar la vista sin crearse un
    usuario aparte.
    """
    from ..models import Usuario  # import local para evitar ciclo

    user = db.get(Usuario, email)
    if user and (user.es_vendedor or user.es_admin):
        return email
    raise HTTPException(status_code=403, detail="Solo para vendedores de sucursal")


def requiere_comprador(email: str = Depends(requiere_auth), db=Depends(get_db)) -> str:
    """Bloquea al vendedor en todo lo que es de abastecimiento.

    El vendedor entra a la misma plataforma que el comprador, asi que esconder el
    menu no alcanza: la URL sigue existiendo. Este es el gate de verdad.
    """
    if es_vendedor(email, db):
        raise HTTPException(
            status_code=403,
            detail="Tu usuario es de sucursal: solo puede crear y ver requerimientos.",
        )
    return email


def sucursales_del_vendedor(email: str, db) -> list[str]:
    """Sucursales por las que un vendedor puede pedir.

    Sale de `sucursales_permitidas`: el vendedor NUNCA escribe su sucursal, se la
    da el usuario. Un vendedor sin sucursales asignadas esta mal configurado y no
    puede pedir por ninguna (mejor eso que dejarlo pedir por todas).
    """
    from ..models import Usuario  # import local para evitar ciclo

    user = db.get(Usuario, email)
    if not user or not user.sucursales_permitidas:
        return []
    try:
        vals = json.loads(user.sucursales_permitidas)
    except (ValueError, TypeError):
        return []
    return [str(v) for v in vals if v] if isinstance(vals, list) else []


def requiere_ver_accesos(email: str = Depends(requiere_auth), db=Depends(get_db)) -> str:
    """Autoriza la vista de accesos (quien entro y cuando): admin o email en la lista."""
    from ..models import Usuario  # import local para evitar ciclo

    user = db.get(Usuario, email)
    if user and user.es_admin:
        return email
    if email.lower() in settings.emails_ver_accesos_set:
        return email
    raise HTTPException(status_code=403, detail="No autorizado para ver accesos")


def puede_calibrar(email: str, db) -> bool:
    """True si el email puede entrar a Calibracion: admin o en EMAILS_CALIBRACION.

    Se usa tanto para el gate real (`requiere_calibracion`) como para informarle al
    frontend si mostrar la seccion, y asi la lista no se duplica en el cliente."""
    from ..models import Usuario  # import local para evitar ciclo

    user = db.get(Usuario, email)
    if user and user.es_admin:
        return True
    return (email or "").lower() in settings.emails_calibracion_set


def requiere_calibracion(email: str = Depends(requiere_auth), db=Depends(get_db)) -> str:
    """Autoriza Calibracion: admin o email en EMAILS_CALIBRACION."""
    if puede_calibrar(email, db):
        return email
    raise HTTPException(status_code=403, detail="No autorizado para calibrar el modelo")


def puede_actualizar(email: str, db) -> bool:
    """True si el email puede pedir "Actualizar ahora": admin o en EMAILS_ACTUALIZAR.

    Recalcular republica el sugerido de todas las sucursales, asi que no lo puede
    disparar cualquiera. Se separa de `es_admin` a proposito: quien mantiene los Excel
    al dia no tiene por que administrar la plataforma (ni al reves)."""
    from ..models import Usuario  # import local para evitar ciclo

    user = db.get(Usuario, email)
    if user and user.es_admin:
        return True
    return (email or "").lower() in settings.emails_actualizar_set


def requiere_actualizar(email: str = Depends(requiere_auth), db=Depends(get_db)) -> str:
    """Autoriza pedir una actualizacion: admin o email en EMAILS_ACTUALIZAR."""
    if puede_actualizar(email, db):
        return email
    raise HTTPException(
        status_code=403, detail="No autorizado para actualizar los datos de la plataforma"
    )


def puede_precios(email: str, db) -> bool:
    """True si el email puede editar la lista de precios: admin o en EMAILS_PRECIOS.

    Editar un precio (fijarlo, congelarlo, crear un producto) es trabajo de
    quien mantiene la lista, no del admin de la plataforma. Mismo esquema que
    Calibracion; la politica de factores sigue siendo de admin."""
    from ..models import Usuario  # import local para evitar ciclo

    user = db.get(Usuario, email)
    if user and user.es_admin:
        return True
    return (email or "").lower() in settings.emails_precios_set


def requiere_precios(email: str = Depends(requiere_auth), db=Depends(get_db)) -> str:
    """Autoriza editar la lista de precios: admin o email en EMAILS_PRECIOS."""
    if puede_precios(email, db):
        return email
    raise HTTPException(status_code=403, detail="No autorizado para editar la lista de precios")
