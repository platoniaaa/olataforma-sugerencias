"""Canal Digital: reposicion semanal de la bodega 430 (y otras bodegas del canal).

Lectura para Abastecimiento (resumen por cluster, productos, paso a paso, politica, datos); edicion de la
politica y de los parametros de cada bodega con validacion; alta de bodegas (admin); y la publicacion de la venta
semanal, que hace el motor como admin.
"""
import csv
import datetime as dt
import io
import time

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..canal_digital.politica import BODEGA_CANAL_DIGITAL, CLUSTERS, MODOS, FilaPolitica, Politica, PoliticaInvalida
from ..canal_digital.ventas_semanales import TIPOS_VENTA_DEFECTO, normalizar_codigo
from ..db import get_db
from ..services import auditoria_service
from ..services import canal_digital_bodegas as bodegas_cd
from ..services import canal_digital_calculo as calculo
from ..services import canal_digital_datos as datos_cd
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


def _exigir_bodega(db: Session, bodega: str) -> None:
    """Una lectura no crea bodegas: solo la por defecto se siembra sola; cualquier otra debe existir ya."""
    if bodega != BODEGA_CANAL_DIGITAL and not svc.existe_bodega(db, bodega):
        raise HTTPException(status_code=404, detail=f"La bodega {bodega} no existe")


def _bodega_del_envio(db: Session, payload: dict) -> str:
    """La bodega de un envio del motor, con el mismo codigo que usa el alta (mayusculas, 1 a 12 letras o numeros).

    Un envio no crea bodegas: las crea un admin con POST /bodegas. Solo la por defecto se siembra sola."""
    crudo = str(payload.get("bodega") or BODEGA_CANAL_DIGITAL)
    codigo = bodegas_cd.normalizar_codigo_bodega(crudo)
    if codigo is None:
        raise HTTPException(
            status_code=400,
            detail=f"El codigo de bodega {crudo.strip()[:30]!r} no sirve: son de 1 a 12 letras o numeros, sin espacios ni signos",
        )
    _exigir_bodega(db, codigo)
    return codigo


@router.get("/meta")
def meta(bodega: str = "430", db: Session = Depends(get_db)) -> dict:
    """Que venta semanal y que lineas del ERP hay cargadas para la bodega.

    `periodo_hasta` es el ultimo mes con venta; `lineas_periodo_hasta` el ultimo con lineas. Quien sube lineas
    (el motor) decide con las segundas: un mes con venta cargada por /ventas puede no tener lineas.
    """
    _exigir_bodega(db, bodega)
    return svc.meta_ventas(db, bodega)


@router.get("/datos")
def datos(bodega: str = "430", db: Session = Depends(get_db)) -> dict:
    """De donde sale lo que se calcula y si esta al dia: venta por mes, cobertura de datos, fuentes y validaciones.

    Solo lectura y chico: se arma al momento con la corrida en cache, sin tablas ni historial propios. Una bodega
    que no existe responde 404 y no se crea (la 430 si se siembra sola, como en el resto de las pantallas).
    """
    _exigir_bodega(db, bodega)
    corrida, aviso = _corrida(db, bodega)
    return datos_cd.armar(db, bodega, corrida, aviso)


@router.get("/resumen")
def resumen(bodega: str = "430", db: Session = Depends(get_db)) -> dict:
    """Los 27 clusters, los totales, las validaciones y lo que sigue siendo provisorio."""
    _exigir_bodega(db, bodega)
    corrida, aviso = _corrida(db, bodega)
    return vista.resumen(corrida, aviso)


@router.get("/productos")
def productos(
    bodega: str = "430",
    cluster: str | None = Query(None, description="AAA a CCC"),
    estado: str | None = Query(None, description="CLASIFICADO, NUEVO o SIN MOVIMIENTO"),
    q: str | None = Query(None, description="Parte del codigo o de la descripcion"),
    solo_pide: bool = Query(False, description="Solo los que hoy tienen sugerido"),
    orden: str = Query("ventas", description="ventas (mayor venta primero) o sugerido (mayor valor a pedir primero)"),
    limit: int = Query(500, ge=1, le=5000),
    db: Session = Depends(get_db),
) -> dict:
    if orden not in ("ventas", "sugerido"):
        raise HTTPException(status_code=400, detail="orden debe ser 'ventas' o 'sugerido'")
    _exigir_bodega(db, bodega)
    corrida, aviso = _corrida(db, bodega)
    return {"total": 0, **_filtrar(corrida, cluster, estado, q, solo_pide, limit, orden), "aviso": aviso}


def _filtrar(corrida, cluster, estado, q, solo_pide, limit, orden="ventas") -> dict:
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
    if orden == "sugerido":
        filas.sort(key=lambda f: (-(f["sugerido_pesos"] or 0), -(f["sugerido"] or 0), f["producto"]))
    else:
        filas.sort(key=lambda f: (-(f["unidades_12m"] or 0), f["producto"]))
    return {"total": len(filas), "items": filas[:limit]}


@router.get("/productos/export-csv")
def export_csv(
    bodega: str = "430", cluster: str | None = None, estado: str | None = None, q: str | None = None,
    solo_pide: bool = False, orden: str = "ventas", db: Session = Depends(get_db),
):
    _exigir_bodega(db, bodega)
    corrida, _ = _corrida(db, bodega)
    datos = _filtrar(corrida, cluster, estado, q, solo_pide, 100_000, "sugerido" if orden == "sugerido" else "ventas")["items"]
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
    _exigir_bodega(db, bodega)
    corrida, aviso = _corrida(db, bodega)
    pasos = vista.paso_a_paso(corrida, normalizar_codigo(producto) or "", aviso["periodos_ventana"])
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
    _exigir_bodega(db, bodega)
    if bodega == BODEGA_CANAL_DIGITAL:  # solo la por defecto se siembra al primer uso
        svc.asegurar_bodega(db, bodega)
    try:
        return _politica_json(svc.leer_politica(db, bodega))
    except PoliticaInvalida as e:
        raise HTTPException(status_code=409, detail=f"La politica de la bodega {bodega} no es valida: {e}")


@router.put("/politica")
def put_politica(
    payload: dict, bodega: str = "430", db: Session = Depends(get_db), email: str = Depends(requiere_escritura),
) -> dict:
    """Reemplaza las 27 filas de la politica. Se valida completa antes de guardar: si algo esta mal no se guarda nada."""
    _exigir_bodega(db, bodega)
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


@router.get("/bodegas")
def get_bodegas(db: Session = Depends(get_db)) -> dict:
    """Las bodegas del canal con sus parametros (la por defecto primero) y los tipos de venta que se sugieren.

    Es una lectura: solo siembra la bodega por defecto si falta, una vez. Chica: una fila por bodega.
    """
    return {"bodegas": bodegas_cd.listar(db), "tipos_venta_sugeridos": list(TIPOS_VENTA_DEFECTO)}


def _problemas_400(e: bodegas_cd.ParametrosInvalidos) -> HTTPException:
    return HTTPException(
        status_code=400, detail={"mensaje": "Hay parámetros que no se pueden guardar", "problemas": e.problemas}
    )


def _detalle_cambios(cambios: dict) -> str:
    def _v(x):
        if isinstance(x, list):
            return "[" + ", ".join(x) + "]"
        return f"{x:g}" if isinstance(x, float) else str(x)

    texto = "; ".join(f"{k} {_v(a)} -> {_v(d)}" for k, (a, d) in cambios.items())
    return texto if len(texto) <= 900 else texto[:899] + "…"


@router.put("/bodegas/{bodega}")
def put_bodega(
    bodega: str, payload: dict, db: Session = Depends(get_db), email: str = Depends(requiere_escritura),
) -> dict:
    """Cambia los parametros de una bodega. Se valida todo antes de guardar: si algo esta mal no se guarda nada.

    Editables: nombre, activa, tipos_venta, r_semanas, nuevo_meses, corte_a_pct, corte_b_pct, gestion_dias,
    bodegas_stock, bodegas_aparte, bodegas_informativas (solo los que vienen; el resto queda igual). La ventana
    es de 12 meses y no se cambia. Cambiar los tipos de venta no toca la venta guardada: la proxima carga de lineas
    la rearma con los tipos nuevos en todos los meses (ver `avisos`).
    Responde la bodega ya guardada mas `cambios` (los campos que cambiaron) y `avisos`.
    """
    try:
        guardada, cambios, avisos = bodegas_cd.actualizar(db, bodega, payload, email)
    except bodegas_cd.BodegaNoExiste:
        raise HTTPException(status_code=404, detail=f"La bodega {bodega} no existe")
    except bodegas_cd.ParametrosInvalidos as e:
        raise _problemas_400(e)
    if cambios:
        auditoria_service.registrar(
            db, accion="canal_digital_bodega", entidad="canal_digital", entidad_id=bodega, usuario_email=email,
            detalle=f"Parametros de la bodega {bodega}: {_detalle_cambios(cambios)}",
        )
    db.commit()
    if cambios:
        _invalidar()
    return {**guardada, "cambios": list(cambios), "avisos": avisos}


@router.post("/bodegas", status_code=201)
def post_bodega(payload: dict, db: Session = Depends(get_db), email: str = Depends(requiere_admin)) -> dict:
    """Crea una bodega nueva: {"bodega": "<codigo>", "nombre": "..."}. Solo admin.

    Codigo de 1 a 12 letras o numeros, unico (409 si ya existe). Nace con los parametros de siembra y las 27 filas
    de la politica provisoria. No se borra: se desactiva con `activa: false`.
    """
    try:
        nueva = bodegas_cd.crear(db, payload)
    except bodegas_cd.ParametrosInvalidos as e:
        raise _problemas_400(e)
    except bodegas_cd.BodegaYaExiste as e:
        raise HTTPException(status_code=409, detail=f"La bodega {e} ya existe")
    auditoria_service.registrar(
        db, accion="canal_digital_bodega_nueva", entidad="canal_digital", entidad_id=nueva["bodega"],
        usuario_email=email, detalle=f"Bodega {nueva['bodega']} creada: {nueva['nombre']}",
    )
    db.commit()
    return nueva


@router.post("/ventas", dependencies=[Depends(requiere_admin)])
def publicar_ventas(payload: dict, db: Session = Depends(get_db)) -> dict:
    """Ruta heredada: el motor publica la venta semanal ya agregada. Reemplaza SOLO los periodos que vienen.

    Un periodo que ya tiene lineas (ver /lineas) queda gobernado por ellas: se responde 409 y no se carga nada.

    payload: {"bodega": "430", "filas": [{producto, semana, periodo, unid_brutas,
    unid_devueltas, valor_costo, unid_liquidacion, n_lineas}]}

    La bodega debe existir (404 si no): se crea con POST /bodegas. Solo la 430 se siembra sola.
    """
    filas = payload.get("filas")
    if not isinstance(filas, list):
        raise HTTPException(status_code=400, detail="Falta la lista 'filas'")
    bodega = _bodega_del_envio(db, payload)
    svc.asegurar_bodega(db, bodega)
    try:
        resumen_carga = svc.reemplazar_ventas(db, bodega, filas)
    except svc.ConflictoCarga as e:
        raise HTTPException(status_code=409, detail=e.detalle)
    _invalidar()
    return resumen_carga


@router.post("/lineas")
def publicar_lineas(
    payload: dict, db: Session = Depends(get_db), email: str = Depends(requiere_admin),
) -> dict:
    """El motor publica las lineas de documento del canal (un mes por envio) y la plataforma arma la venta semanal.

    Reemplaza SOLO los periodos que vienen y recalcula la venta de la bodega con todas las lineas guardadas,
    para que una devolucion de un mes encuentre su venta de otro mes. Todo o nada. Un periodo cargado antes por
    /ventas y despues por aca queda gobernado por las lineas.

    payload: {"bodega": "430", "lineas": [{periodo, tipo_docto, numero, fecha, tipo_venta, producto, cantidad,
    costo_neto, doc_ref, nro_doc_ref}], "forzar": false}

    La bodega debe existir (404 si no; 400 si el codigo no sirve): se crea con POST /bodegas. Solo la 430 se siembra
    sola. Solo entran las lineas de los tipos de venta de la bodega (ver GET /bodegas).

    Respuestas distintas de 200:
      409  el envio dejaria un periodo con menos de la mitad de sus lineas (parece un envio parcial); con
           "forzar": true se carga igual.
      422  ninguna linea sirvio (un campo renombrado, un formato nuevo): el detalle dice que campo fallo.
    Con algunas lineas invalidas se carga lo que sirve y la respuesta las cuenta (`estadisticas`).
    """
    lineas = payload.get("lineas")
    if not isinstance(lineas, list):
        raise HTTPException(status_code=400, detail="Falta la lista 'lineas'")
    bodega = _bodega_del_envio(db, payload)
    try:
        resumen_carga = svc.reemplazar_lineas(db, bodega, lineas, forzar=payload.get("forzar") is True)
    except svc.ConflictoCarga as e:
        raise HTTPException(status_code=409, detail=e.detalle)
    est = resumen_carga["estadisticas"]
    if resumen_carga["lineas_cargadas"] == 0 and est["ignoradas_invalidas"]:
        raise HTTPException(status_code=422, detail={
            "mensaje": f"Ninguna de las {len(lineas)} lineas sirvio: revisa los nombres y formatos de los campos. "
                       "No se cargo nada.",
            "estadisticas": est,
        })
    if resumen_carga["lineas_cargadas"]:
        periodos = ", ".join(f"{p} ({r['antes']} -> {r['despues']})" for p, r in resumen_carga["reemplazo"].items())
        auditoria_service.registrar(
            db, accion="canal_digital_lineas", entidad="canal_digital", entidad_id=bodega, usuario_email=email,
            detalle=f"Lineas del canal {bodega}: {resumen_carga['lineas_cargadas']} lineas, periodos {periodos}",
        )
        db.commit()
    _invalidar()
    return resumen_carga
