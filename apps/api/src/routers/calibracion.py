"""Calibracion del modelo: los parametros del sugerido y el lead time calculado.

Va en su propio router (y NO bajo /api/admin) porque su permiso es distinto: lo
puede usar quien sea admin **o** este en la lista de autorizados
(`EMAILS_CALIBRACION`), pensado para Abastecimiento, que es dueno del modelo
aunque no administre la plataforma.

El motivo tecnico de separarlo: en FastAPI las dependencias declaradas al montar
un router se ejecutan SIEMPRE y no se pueden excluir por endpoint. Como
`/api/admin/*` se monta con `requiere_admin`, un endpoint de calibracion ahi
dentro seria admin-only por construccion.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..schemas import ConfigModeloUpdate
from ..services import config_modelo_service, lead_time_service
from ..services.auth import requiere_auth

router = APIRouter(prefix="/api/calibracion", tags=["calibracion"])


@router.get("/config-modelo")
def get_config_modelo(db: Session = Depends(get_db)) -> dict:
    """Parametros calibrables vigentes (o los defaults si nunca se editaron)."""
    return config_modelo_service.vigente(db)


@router.put("/config-modelo")
def put_config_modelo(
    cambios: ConfigModeloUpdate,
    email: str = Depends(requiere_auth),
    db: Session = Depends(get_db),
) -> dict:
    """Aplica cambios a la configuracion (crea una version nueva)."""
    datos = cambios.model_dump(exclude_none=True)
    nota = datos.pop("nota", None)
    try:
        return config_modelo_service.actualizar(db, datos, usuario=email, nota=nota)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/config-modelo/historial")
def get_config_modelo_historial(db: Session = Depends(get_db)) -> list[dict]:
    """Versiones anteriores de la configuracion (para ver el historial y revertir)."""
    return config_modelo_service.historial(db)


@router.post("/config-modelo/revertir/{version_id}")
def revertir_config_modelo(
    version_id: str,
    email: str = Depends(requiere_auth),
    db: Session = Depends(get_db),
) -> dict:
    """Vuelve a una version anterior insertando una copia (no borra historial)."""
    try:
        return config_modelo_service.revertir(db, version_id, usuario=email)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/lead-time-proveedor")
def get_lead_time(
    buscar: str | None = None,
    solo_global: bool = False,
    limite: int = 200,
    db: Session = Depends(get_db),
) -> dict:
    """Lead time calculado por el motor, con buscador (proveedor o sucursal)."""
    return lead_time_service.listar(
        db, buscar=buscar, solo_global=solo_global, limite=min(limite, 500)
    )
