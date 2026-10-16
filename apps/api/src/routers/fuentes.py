"""Fuentes de datos: de donde saca el motor cada archivo (`/api/admin/fuentes`).

Solo admin: se monta en `main.py` con `requiere_admin`, igual que `/api/admin/*`.
El motor entra con su usuario admin y el mismo token de siempre; no hace falta un
secreto nuevo.

Las rutas fijas (`config`, `reporte`, `corridas`, `carpetas`, `pcs`, `titular`,
`modo`, `sembrar`, `revertir`) van declaradas ANTES de `/{clave}`: FastAPI prueba
las rutas en orden, y esas palabras estan prohibidas como clave de fuente.

Errores: el servicio lanza `ValueError` (422, con el texto en espanol para la
persona), `ConflictoFuentes` (409: otro admin guardo antes, ya hay configuracion,
o no se cumple la condicion para activar) y `NoEncontrado` (404).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from pydantic import ValidationError
from sqlalchemy.orm import Session

from ..db import get_db
from ..schemas.fuentes import (
    AliasPcIn,
    ArchivosCarpetaOut,
    CorridasOut,
    CrearCarpetaIn,
    EditarCarpetaIn,
    FuenteDetalleOut,
    GuardadoOut,
    GuardarFuenteIn,
    ModoIn,
    PanelOut,
    ReporteIn,
    ReporteOut,
    RevertirIn,
    SembrarIn,
    TitularIn,
    VistaPreviaIn,
    VistaPreviaOut,
)
from ..services import fuentes_service as svc
from ..services.auth import requiere_admin

router = APIRouter(prefix="/api/admin/fuentes", tags=["fuentes"])

# Un reporte normal pesa pocos KB (hoy hay 35 archivos en Bases de datos y 8 en Data
# BI, y el listado tiene tope de 500 por carpeta). Sobre esto algo anda mal.
TOPE_REPORTE_BYTES = 2 * 1024 * 1024


def _ejecutar(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except svc.ConflictoFuentes as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except svc.NoEncontrado as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


# --------------------------- lo que usa el motor --------------------------- #
@router.get("/config")
def get_config(db: Session = Depends(get_db)) -> dict:
    """Configuracion vigente para el motor. Sin configuracion: `{"modo": "sin_configurar"}`."""
    return svc.config_para_motor(db)


@router.post("/reporte", response_model=ReporteOut)
async def post_reporte(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Depends(requiere_admin),
):
    """Reporte de inicio o de fin de una corrida (upsert por `id`). Sobre 2 MB, 413."""
    cuerpo = await request.body()
    if len(cuerpo) > TOPE_REPORTE_BYTES:
        raise HTTPException(
            status_code=413,
            detail="El reporte pasa de 2 MB: no se guardó. Revisa el listado de carpetas.",
        )
    try:
        datos = ReporteIn.model_validate_json(cuerpo)
    except ValidationError as e:
        raise HTTPException(
            status_code=422,
            detail=jsonable_encoder(e.errors(include_url=False, include_context=False)),
        ) from e
    return _ejecutar(svc.registrar_reporte, db, datos, usuario=email)


# --------------------------- lo que lee la pantalla --------------------------- #
@router.get("", response_model=PanelOut)
def get_panel(db: Session = Depends(get_db)):
    """Panel de `/cargar/fuentes`: franja, semaforo por fuente, carpetas por PC y modo."""
    return svc.panel(db)


@router.get("/corridas", response_model=CorridasOut)
def get_corridas(limit: int = Query(30, ge=1, le=200), db: Session = Depends(get_db)):
    return {"items": svc.corridas(db, limite=limit)}


@router.get("/carpetas/{clave}/archivos", response_model=ArchivosCarpetaOut)
def get_archivos_carpeta(clave: str, pc: str | None = None, db: Session = Depends(get_db)):
    """Ultimo listado de esa carpeta en ese PC (por defecto el titular)."""
    return svc.archivos_de_carpeta(db, clave, pc)


# --------------------------- escrituras --------------------------- #
@router.post("/carpetas", response_model=GuardadoOut)
def post_carpeta(datos: CrearCarpetaIn, db: Session = Depends(get_db),
                 email: str = Depends(requiere_admin)):
    return _ejecutar(svc.crear_carpeta, db, datos.carpeta.model_dump(), nota=datos.nota,
                     base_version=datos.base_version, usuario=email)


@router.put("/carpetas/{clave}", response_model=GuardadoOut)
def put_carpeta(clave: str, datos: EditarCarpetaIn, db: Session = Depends(get_db),
                email: str = Depends(requiere_admin)):
    return _ejecutar(svc.editar_carpeta, db, clave, datos.cambios, nota=datos.nota,
                     base_version=datos.base_version, usuario=email)


@router.put("/pcs/{hostname}", response_model=GuardadoOut)
def put_pc(hostname: str, datos: AliasPcIn, db: Session = Depends(get_db),
           email: str = Depends(requiere_admin)):
    """Nombre del PC para mostrar ("PC de la jefa")."""
    return _ejecutar(svc.cambiar_alias, db, hostname, datos.alias, nota=datos.nota,
                     base_version=datos.base_version, usuario=email)


@router.post("/titular", response_model=GuardadoOut)
def post_titular(datos: TitularIn, db: Session = Depends(get_db),
                 email: str = Depends(requiere_admin)):
    return _ejecutar(svc.cambiar_titular, db, datos.pc, nota=datos.nota,
                     base_version=datos.base_version, usuario=email)


@router.post("/modo", response_model=GuardadoOut)
def post_modo(datos: ModoIn, db: Session = Depends(get_db),
              email: str = Depends(requiere_admin)):
    """Prueba <-> activa. Activar sin la condicion: 409 con el motivo."""
    return _ejecutar(svc.cambiar_modo, db, datos.modo, nota=datos.nota,
                     base_version=datos.base_version, usuario=email)


@router.post("/sembrar", response_model=GuardadoOut)
def post_sembrar(datos: SembrarIn, db: Session = Depends(get_db),
                 email: str = Depends(requiere_admin)):
    """Copia la configuracion que uso esa corrida. Con configuracion ya hecha: 409."""
    return _ejecutar(svc.sembrar, db, datos.corrida_id, usuario=email, nota=datos.nota)


@router.post("/revertir/{version}", response_model=GuardadoOut)
def post_revertir(version: int, datos: RevertirIn | None = None, db: Session = Depends(get_db),
                  email: str = Depends(requiere_admin)):
    datos = datos or RevertirIn()
    return _ejecutar(svc.revertir, db, version, usuario=email, nota=datos.nota,
                     base_version=datos.base_version, clave=datos.clave)


# --------------------------- una fuente (despues de las rutas fijas) ------------ #
@router.get("/{clave}", response_model=FuenteDetalleOut)
def get_fuente(clave: str, db: Session = Depends(get_db)):
    return _ejecutar(svc.detalle_fuente, db, clave)


@router.post("/{clave}/vista-previa", response_model=VistaPreviaOut)
def post_vista_previa(clave: str, datos: VistaPreviaIn, db: Session = Depends(get_db)):
    """Que archivo tomaria el motor con estos cambios. No guarda nada."""
    return _ejecutar(svc.vista_previa, db, clave, datos.cambios)


@router.put("/{clave}", response_model=GuardadoOut)
def put_fuente(clave: str, datos: GuardarFuenteIn, db: Session = Depends(get_db),
               email: str = Depends(requiere_admin)):
    """Guarda los cambios de una fuente. `base_version` vieja: 409."""
    return _ejecutar(svc.guardar_fuente, db, clave, datos.cambios, nota=datos.nota,
                     base_version=datos.base_version, usuario=email)
