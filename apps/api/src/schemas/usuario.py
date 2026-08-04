"""Schemas de administracion de usuarios.

La contrasena solo viaja de entrada, nunca de vuelta: `UsuarioOut` no la tiene
ni tiene el hash.
"""
from datetime import datetime

from pydantic import BaseModel, Field


class UsuarioCrear(BaseModel):
    """Crear o actualizar. Los campos en None no se tocan.

    Distinguir "no lo mandes" de "ponlo en false" importa: actualizar solo el
    nombre de alguien no puede convertirlo en no-admin de rebote.
    """

    email: str
    # Obligatoria al crear; al actualizar, en None deja la que tenia.
    password: str | None = None
    nombre: str | None = None
    es_admin: bool | None = None
    solo_lectura: bool | None = None
    es_vendedor: bool | None = None
    activo: bool | None = None
    # Sucursales que puede ver. Para un vendedor son ademas por las que puede
    # pedir. Lista vacia = ve todas (menos si es vendedor, que necesita una).
    sucursales: list[str] | None = None


class UsuarioOut(BaseModel):
    email: str
    nombre: str | None = None
    activo: bool = True
    es_admin: bool = False
    solo_lectura: bool = False
    es_vendedor: bool = False
    sucursales: list[str] = Field(default_factory=list)
    creado_en: datetime | None = None
