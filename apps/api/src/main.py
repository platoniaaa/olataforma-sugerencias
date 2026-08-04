"""Punto de entrada de la API FastAPI.

Levantar con:
    uvicorn src.main:app --reload --port 8000
"""
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .db import create_all
from .routers import (
    actualizacion,
    admin,
    auditoria,
    auth,
    calibracion,
    catalogo,
    chat,
    compras,
    cron,
    health,
    incidencias,
    instock,
    inventario,
    productos,
    requerimiento,
    requerimientos,
    sugerencias_manuales,
    sugerido,
    usuarios,
    ventas_historicas,
)
from .services.auth import (
    requiere_admin,
    requiere_auth,
    requiere_calibracion,
    requiere_comprador,
)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Crea las tablas si no existen (Fase 0; en Fase 1+ se usa Alembic).
    # En Vercel (serverless) o si el create_all falla por timeout en Render free,
    # NO debe romper el arranque: las tablas existentes siguen funcionando y las
    # nuevas se pueden crear despues con un script local apuntando a la DB.
    import os
    import traceback

    if not os.environ.get("VERCEL"):
        try:
            create_all()
        except Exception as e:
            print(f"[lifespan] create_all fallo (continuando): {e}")
            traceback.print_exc()
    yield


app = FastAPI(
    title="Sugerido de Compras API",
    description="Backend de la plataforma de sugerido de reposicion (Fase 0). Cliente cero: Curifor S.A.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    # Sin login/cookies en esta etapa; False permite usar CORS_ORIGINS="*" sin problemas.
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Publicos:
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(cron.router)  # protegido por secreto propio (X-Cron-Secret)
# Mezcla endpoints de usuario y del agente que corre el motor (X-Agente-Secret), asi
# que el gate va por endpoint y no en el include: el agente no tiene login.
app.include_router(actualizacion.router)

# Protegidos (requieren sesion):
_protegido = [Depends(requiere_auth)]
# Solo Abastecimiento: el vendedor de sucursal entra a la MISMA plataforma, asi que
# esconderle el menu no alcanza (la URL sigue existiendo). Este es el gate real.
_abastecimiento = [Depends(requiere_comprador)]
app.include_router(sugerido.router, dependencies=_abastecimiento)
app.include_router(productos.router, dependencies=_abastecimiento)
app.include_router(sugerencias_manuales.router, dependencies=_abastecimiento)
app.include_router(instock.router, dependencies=_abastecimiento)
app.include_router(compras.router, dependencies=_abastecimiento)
app.include_router(requerimiento.router, dependencies=_abastecimiento)
# Bandeja de requerimientos: la comparten vendedor y comprador (el rol se resuelve
# dentro, porque cada uno ve una cosa distinta del mismo dato).
app.include_router(requerimientos.router, dependencies=_protegido)
app.include_router(catalogo.router, dependencies=_abastecimiento)
app.include_router(auditoria.router, dependencies=_protegido)
app.include_router(ventas_historicas.router, dependencies=_abastecimiento)
app.include_router(inventario.router, dependencies=_abastecimiento)
# Incidencias: todos reportan y ven lo suyo; gestionar exige admin en el endpoint.
app.include_router(incidencias.router, dependencies=_protegido)
# Admin: requiere flag es_admin (no solo estar logueado).
app.include_router(admin.router, dependencies=[Depends(requiere_admin)])
# Usuarios: crear/editar/desactivar. Cada endpoint valida admin por su cuenta
# para poder saber QUIEN lo hizo y dejarlo en la auditoria.
app.include_router(usuarios.router, dependencies=[Depends(requiere_admin)])
# Calibracion NO va bajo /api/admin: su permiso es admin O autorizado (Abastecimiento).
app.include_router(calibracion.router, dependencies=[Depends(requiere_calibracion)])
# Chatbot: disponible para todo usuario autenticado.
app.include_router(chat.router, dependencies=_protegido)


@app.get("/", include_in_schema=False)
def root():
    return {"servicio": "sugerido-api", "docs": "/docs"}
