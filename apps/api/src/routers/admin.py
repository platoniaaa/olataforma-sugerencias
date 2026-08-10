"""Endpoints de administracion: carga del sugerido (Excel/CSV o desde Power BI)."""
import subprocess

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..services import (
    auditoria_service,
    config_modelo_service,
    excel_loader,
    lead_time_service,
    motor_comparacion,
    powerbi_desktop_loader,
    powerbi_loader,
    reemplazo_service,
    stock_service,
    transito_service,
    ventas_historicas_service,
)
from ..services.auth import requiere_admin

router = APIRouter(prefix="/api/admin", tags=["admin"])
settings = get_settings()


@router.get("/config-modelo")
def get_config_modelo(db: Session = Depends(get_db)) -> dict:
    """Parametros calibrables vigentes. Lo usa EL MOTOR (que entra como admin).

    La web usa /api/calibracion/config-modelo, que ademas admite a Abastecimiento.
    Se mantiene esta ruta para no obligar a desplegar los dos repos a la vez.
    """
    return config_modelo_service.vigente(db)


@router.post("/lead-time-proveedor")
def publicar_lead_time(
    payload: dict,
    db: Session = Depends(get_db),
) -> dict:
    """El motor publica el lead time que calculo (reemplaza la foto vigente). Admin.

    payload: {"filas": [{proveedor, sucursal_id|None, lead_time_dias, n_muestras}]}
    """
    filas = payload.get("filas")
    if not isinstance(filas, list):
        raise HTTPException(status_code=400, detail="Falta la lista 'filas'")
    return lead_time_service.reemplazar(db, filas)


@router.post("/stock-unificado")
def publicar_stock_unificado(
    payload: dict,
    db: Session = Depends(get_db),
) -> dict:
    """El motor publica el stock por producto-bodega (reemplaza la foto vigente). Admin.

    payload: {"filas": [{producto, bodega, sucursal_id, stock, origen}]}

    Lo alimenta el Excel de "Stock bodegas" que el motor ya lee para calcular el
    sugerido. Antes esta tabla venia del Power BI Desktop; al retirarlo, el stock
    del catalogo quedo congelado.
    """
    filas = payload.get("filas")
    if not isinstance(filas, list):
        raise HTTPException(status_code=400, detail="Falta la lista 'filas'")
    resumen = stock_service.reemplazar(db, filas)
    if resumen["reemplazo"]:
        auditoria_service.registrar(
            db,
            accion="stock_publicado",
            entidad="sistema",
            detalle=f"Stock unificado: {resumen['filas_cargadas']} filas",
        )
        db.commit()
    return resumen


@router.post("/stock-transito")
def publicar_stock_transito(
    payload: dict,
    db: Session = Depends(get_db),
) -> dict:
    """El motor publica el transito vigente de TODO el catalogo (reemplaza la foto).

    payload: {"filas": [{producto, sucursal_id, cantidad, pedido_desde}]}

    Hasta ahora el transito solo existia pegado a las filas del sugerido, que es
    un subconjunto chico del catalogo. El comprador que revisa un requerimiento
    de sucursal no podia ver si el repuesto ya venia en camino, y podia comprar
    de nuevo algo ya pedido.
    """
    filas = payload.get("filas")
    if not isinstance(filas, list):
        raise HTTPException(status_code=400, detail="Falta la lista 'filas'")
    resumen = transito_service.reemplazar(db, filas)
    if resumen["reemplazo"]:
        auditoria_service.registrar(
            db,
            accion="transito_publicado",
            entidad="sistema",
            detalle=f"Stock en transito: {resumen['filas_cargadas']} filas",
        )
        db.commit()
    return resumen


@router.post("/reemplazos-ford")
def publicar_reemplazos_ford(
    payload: dict,
    db: Session = Depends(get_db),
) -> dict:
    """El motor publica la cadena de reemplazo de FORD (reemplaza la foto).

    payload: {"filas": [{producto, reemplazado_por, reemplazado_por_ford, cadena,
                         reemplaza_a, sucesor_confirmado, agrupado, aviso}]}

    Solo llega lo que toca a productos que Curifor tiene. La agrupacion de stock
    y demanda la hace el motor; esta tabla es para AVISARLE al comprador que el
    codigo que le pidieron esta descontinuado y cual es el vigente.
    """
    filas = payload.get("filas")
    if not isinstance(filas, list):
        raise HTTPException(status_code=400, detail="Falta la lista 'filas'")
    resumen = reemplazo_service.reemplazar(db, filas)
    if resumen["reemplazo"]:
        auditoria_service.registrar(
            db,
            accion="reemplazos_publicados",
            entidad="sistema",
            detalle=f"Reemplazos FORD: {resumen['filas_cargadas']} filas",
        )
        db.commit()
    return resumen


@router.post("/ventas-historicas")
def publicar_ventas_historicas(
    payload: dict,
    db: Session = Depends(get_db),
) -> dict:
    """El motor publica los meses de venta que a la plataforma le faltan.

    payload: {"filas": [{periodo, producto, sucursal, cantidad, neto, n_lineas}]}

    Reemplaza SOLO los periodos que vienen. Hasta ahora esta tabla se cargaba con
    un job manual conectado directo a la base: el mes que se pegaba en el respaldo
    de Ventas no llegaba nunca a la plataforma salvo que alguien se acordara, y la
    columna "Venta 12m" y el grafico de consumo se quedaban atras sin avisar.
    """
    filas = payload.get("filas")
    if not isinstance(filas, list):
        raise HTTPException(status_code=400, detail="Falta la lista 'filas'")
    resumen = ventas_historicas_service.reemplazar_periodos(db, filas)
    if resumen["filas_cargadas"]:
        auditoria_service.registrar(
            db,
            accion="ventas_publicadas",
            entidad="sistema",
            detalle=(
                f"Venta historica: {resumen['filas_cargadas']} filas, "
                f"periodos {', '.join(resumen['periodos'])}"
            ),
        )
        db.commit()
    return resumen


@router.post("/cargar-instock")
def cargar_instock(db: Session = Depends(get_db)) -> dict:
    """Carga la lista InStock (repuestos de pauta) desde el CSV que viene desplegado.

    La lista sale de las pautas del fabricante y vive en `src/data/pautas_instock.csv`,
    versionado con el codigo. El cruce part number -> codigo del ERP se resuelve
    contra ESTA base, asi que hay que correrlo donde estan los datos.

    Existe este endpoint porque hasta ahora la unica forma de cargarla era un
    script de consola conectado directo a la base: la regla quedo desplegada en
    produccion pero con la tabla vacia durante semanas, pidiendo cero unidades sin
    que nadie lo notara. Con esto se recarga desde la plataforma cada vez que
    cambien las pautas.

    Reemplaza la lista completa (no acumula), igual que el resto de las cargas.
    """
    from ..jobs import cargar_instock as job

    try:
        pautas = job._leer_csv(job.DEFAULT_PATH)
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    r = job.cargar_en(db, pautas)
    # Las claves con "_" son contexto para imprimir en consola, no para la API.
    salida = {k: v for k, v in r.items() if not k.startswith("_")}
    auditoria_service.registrar(
        db,
        accion="instock_cargado",
        entidad="sistema",
        detalle=f"InStock: {r['productos']} repuestos marcados, {r['sin_codigo']} sin codigo",
    )
    db.commit()
    return salida


@router.post("/cargar-sugerido")
async def cargar_sugerido(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Recibe el Excel/CSV exportado del Power BI y reemplaza la tabla `sugerido`."""
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="El archivo esta vacio")
    try:
        resumen = excel_loader.cargar_sugerido(db, file.filename or "", content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    # Sello de "datos actualizados": lo lee la etiqueta de la web. Antes solo lo
    # dejaba el job del Power BI, asi que con el motor la fecha quedaba congelada
    # en la ultima corrida del BI aunque los datos fueran de hoy.
    auditoria_service.registrar(
        db,
        accion="datos_sincronizados",
        entidad="sistema",
        detalle=f"Sugerido cargado: {resumen.get('filas_cargadas')} filas",
    )
    db.commit()
    return resumen


@router.post("/motor/comparar")
async def comparar_motor(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    email: str = Depends(requiere_admin),
):
    """Contrasta el sugerido que produjo el motor propio contra el vivo (Power BI).

    NO escribe en `sugerido`: solo compara y guarda el reporte. Asi se puede
    validar el motor todos los dias sin exponer a los compradores a sus datos."""
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="El archivo esta vacio")
    try:
        resultado = motor_comparacion.comparar(db, content, file.filename or "motor.csv")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    motor_comparacion.guardar(db, resultado, usuario_email=email)
    return resultado


@router.get("/motor/comparaciones")
def comparaciones_motor(
    limit: int = 10,
    db: Session = Depends(get_db),
    _email: str = Depends(requiere_admin),
):
    """Historial de comparaciones motor vs Power BI (la mas reciente primero)."""
    return {"items": motor_comparacion.ultimas(db, limit=limit)}


@router.get("/powerbi/estado")
def powerbi_estado() -> dict:
    """Indica si la sincronizacion automatica con Power BI esta configurada."""
    return {"configurado": settings.powerbi_configurado}


@router.post("/cargar-desde-powerbi")
def cargar_desde_powerbi(db: Session = Depends(get_db)):
    """Trae la tabla del sugerido directo desde Power BI (API) y reemplaza el snapshot."""
    if not settings.powerbi_configurado:
        raise HTTPException(
            status_code=503,
            detail="Power BI no esta configurado. Define las variables POWERBI_* en .env",
        )
    try:
        return powerbi_loader.sync(db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except (RuntimeError, httpx.HTTPError) as e:
        raise HTTPException(status_code=502, detail=f"Error consultando Power BI: {e}") from e


@router.post("/cargar-desde-powerbi-desktop")
def cargar_desde_powerbi_desktop(db: Session = Depends(get_db)):
    """Lee el sugerido desde un Power BI Desktop ABIERTO en este equipo y lo carga."""
    try:
        return powerbi_desktop_loader.sync_desktop(db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except subprocess.TimeoutExpired as e:
        raise HTTPException(status_code=504, detail="Power BI Desktop no respondio a tiempo.") from e
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
