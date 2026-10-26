"""Canal Digital: reposicion semanal de la bodega 430 (y otras bodegas del canal).

Lectura para Abastecimiento (resumen por cluster, productos, paso a paso, politica); edicion de la
politica con validacion; y la publicacion de la venta semanal, que hace el motor como admin.
"""
import csv
import datetime as dt
import io
import time

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..canal_digital.politica import CLUSTERS, MODOS, FilaPolitica, Politica, PoliticaInvalida
from ..canal_digital.ventas_semanales import normalizar_codigo
from ..db import get_db
from ..services import auditoria_service
from ..services import canal_digital_calculo as calculo
from ..services import canal_digital_service as svc
from ..services import canal_digital_vista as vista
from ..services.auth import requiere_admin, requiere_escritura

router = APIRouter(prefix="/api/canal-digital", tags=["canal digital"])

# Calcular toca varias tablas; las pantallas piden resumen, productos y paso a paso seguidos. Se guarda el
# ultimo resultado un rato y se descarta apenas cambia la politica o llegan ventas nuevas.
_TTL_SEGUNDOS = 120
_cache: dict[str, tuple[float, object, dict]] = {}


def _hoy() -> dt.date:
    return dt.date.today()


def _invalidar() -> None:
    _cache.clear()


def _corrida(db: Session, bodega: str):
    ahora = time.monotonic()
    clave = f"{bodega}:{_hoy().isoformat()}"
    hit = _cache.get(clave)
    if hit and ahora - hit[0] < _TTL_SEGUNDOS:
        return hit[1], hit[2]
    try:
        corrida, aviso = calculo.calcular(db, bodega, _hoy())
    except PoliticaInvalida as e:
        raise HTTPException(status_code=409, detail=f"La politica de la bodega {bodega} no es valida: {e}")
    _cache[clave] = (ahora, corrida, aviso)
    return corrida, aviso


@router.get("/meta")
def meta(bodega: str = "430", db: Session = Depends(get_db)) -> dict:
    """Que venta semanal hay cargada para la bodega."""
    return svc.meta_ventas(db, bodega)


@router.get("/resumen")
def resumen(bodega: str = "430", db: Session = Depends(get_db)) -> dict:
    """Los 27 clusters, los totales, las validaciones y lo que sigue siendo provisorio."""
    corrida, aviso = _corrida(db, bodega)
    return vista.resumen(corrida, aviso)


@router.get("/productos")
def productos(
    bodega: str = "430",
    cluster: str | None = Query(None, description="AAA a CCC"),
    estado: str | None = Query(None, description="CLASIFICADO, NUEVO o SIN MOVIMIENTO"),
    q: str | None = Query(None, description="Parte del codigo o de la descripcion"),
    solo_pide: bool = Query(False, description="Solo los que hoy tienen sugerido"),
    limit: int = Query(500, ge=1, le=5000),
    db: Session = Depends(get_db),
) -> dict:
    corrida, aviso = _corrida(db, bodega)
    return {"total": 0, **_filtrar(corrida, cluster, estado, q, solo_pide, limit), "aviso": aviso}


def _filtrar(corrida, cluster, estado, q, solo_pide, limit) -> dict:
    filas = []
    texto = (q or "").strip().upper()
    for pc in corrida.productos:
        f = vista.fila_producto(pc, corrida)
        if cluster and f["cluster"] != cluster.upper():
            continue
        if estado and f["estado"] != estado.upper():
            continue
        if solo_pide and not f["sugerido"]:
            continue
        if texto and texto not in f["producto"].upper() and texto not in (f["descripcion"] or "").upper():
            continue
        filas.append(f)
    filas.sort(key=lambda f: (-(f["unidades_12m"] or 0), f["producto"]))
    return {"total": len(filas), "items": filas[:limit]}


@router.get("/productos/export-csv")
def export_csv(
    bodega: str = "430", cluster: str | None = None, estado: str | None = None, q: str | None = None,
    solo_pide: bool = False, db: Session = Depends(get_db),
):
    corrida, _ = _corrida(db, bodega)
    datos = _filtrar(corrida, cluster, estado, q, solo_pide, 100_000)["items"]
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    cols = list(datos[0].keys()) if datos else ["producto"]
    w.writerow(cols)
    for f in datos:
        w.writerow([",".join(v) if isinstance(v, list) else ("" if v is None else v) for v in f.values()])
    return StreamingResponse(
        iter([buf.getvalue().encode("utf-8-sig")]), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="canal_digital_{bodega}.csv"'},
    )


@router.get("/producto/paso-a-paso")
def paso_a_paso(producto: str, bodega: str = "430", db: Session = Depends(get_db)) -> dict:
    """El recorrido de un producto con sus numeros. El codigo va en la query porque lleva espacios."""
    corrida, aviso = _corrida(db, bodega)
    pasos = vista.paso_a_paso(corrida, normalizar_codigo(producto) or "", calculo.ventana(_hoy())["periodos"])
    if pasos is None:
        raise HTTPException(status_code=404, detail="Ese producto no esta en la corrida de la bodega")
    return {"producto": producto, "pasos": pasos}


def _politica_json(p: Politica) -> dict:
    return {
        "bodega": p.bodega, "modos": list(MODOS), "problemas": p.validar(),
        "filas": [
            {"cluster": f.cluster, "modo": f.modo, "nivel_servicio": f.nivel_servicio, "z": f.z,
             "minimo_fijo": f.minimo_fijo}
            for f in p.filas
        ],
    }


@router.get("/politica")
def get_politica(bodega: str = "430", db: Session = Depends(get_db)) -> dict:
    svc.asegurar_bodega(db, bodega)
    return _politica_json(svc.leer_politica(db, bodega))


@router.put("/politica")
def put_politica(
    payload: dict, bodega: str = "430", db: Session = Depends(get_db), email: str = Depends(requiere_escritura),
) -> dict:
    """Reemplaza las 27 filas de la politica. Se valida completa antes de guardar: si algo esta mal no se guarda nada."""
    filas = payload.get("filas")
    if not isinstance(filas, list):
        raise HTTPException(status_code=400, detail="Falta la lista 'filas'")
    try:
        nuevas = [
            FilaPolitica(bodega, str(f["cluster"]).upper(), str(f["modo"]), f.get("nivel_servicio"), f.get("z"),
                         f.get("minimo_fijo"))
            for f in filas
        ]
        politica = Politica(bodega, tuple(nuevas))
    except (KeyError, PoliticaInvalida, TypeError) as e:
        raise HTTPException(status_code=400, detail=f"Politica incompleta o mal formada: {e}")
    problemas = politica.validar()
    if problemas:
        raise HTTPException(status_code=400, detail={"mensaje": "La politica tiene errores", "problemas": problemas})
    svc.asegurar_bodega(db, bodega)
    svc.guardar_politica(db, bodega, politica, email)
    auditoria_service.registrar(
        db, accion="canal_digital_politica", entidad="canal_digital", entidad_id=bodega, usuario_email=email,
        detalle=f"Politica de la bodega {bodega}: {len(CLUSTERS)} filas",
    )
    db.commit()
    _invalidar()
    return _politica_json(svc.leer_politica(db, bodega))


@router.post("/ventas", dependencies=[Depends(requiere_admin)])
def publicar_ventas(payload: dict, db: Session = Depends(get_db)) -> dict:
    """El motor publica la venta semanal del canal. Reemplaza SOLO los periodos que vienen.

    payload: {"bodega": "430", "filas": [{producto, semana, periodo, unid_brutas,
    unid_devueltas, valor_costo, unid_liquidacion, n_lineas}]}
    """
    filas = payload.get("filas")
    if not isinstance(filas, list):
        raise HTTPException(status_code=400, detail="Falta la lista 'filas'")
    bodega = str(payload.get("bodega") or "430").strip()
    svc.asegurar_bodega(db, bodega)
    resumen_carga = svc.reemplazar_ventas(db, bodega, filas)
    _invalidar()
    return resumen_carga
