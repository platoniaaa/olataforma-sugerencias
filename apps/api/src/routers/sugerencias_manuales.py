"""Endpoints CRUD de las sugerencias manuales."""
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

# Zona horaria del negocio: el vencimiento se ancla a la medianoche de Chile.
# Si se anclara a UTC, el ultimo dia se recortaria 3-4 horas (la sugerencia
# dejaria de sumar a las 20:00-21:00 hora chilena del propio dia elegido).
TZ_CHILE = ZoneInfo("America/Santiago")


def _expira_en(fecha_limite: date | None) -> datetime | None:
    """Convierte la fecha limite (inclusive) en el instante de vencimiento.

    La sugerencia vive todo el dia elegido (hora de Chile) y vence al comenzar
    el dia siguiente. None si no se pidio fecha limite."""
    if not fecha_limite:
        return None
    if fecha_limite < datetime.now(TZ_CHILE).date():
        raise HTTPException(status_code=422, detail="La fecha limite ya paso.")
    if fecha_limite.year > 2100:
        raise HTTPException(status_code=422, detail="Fecha limite demasiado lejana.")
    inicio = datetime(
        fecha_limite.year, fecha_limite.month, fecha_limite.day, tzinfo=TZ_CHILE
    )
    return (inicio + timedelta(days=1)).astimezone(timezone.utc)

from ..config import get_settings
from ..db import get_db
from ..models import SugerenciaManual
from ..schemas import (
    LineaManualPegada,
    RecurrenteCreate,
    RecurrenteOut,
    SugerenciaManualCreate,
    SugerenciaManualMasiva,
    SugerenciaManualMasivaResultado,
    SugerenciaManualOut,
    SugerenciaManualPegada,
    SugerenciaManualPegadaResultado,
    SugerenciaManualUpdate,
)
from ..services import (
    auditoria_service,
    carga_manual_service,
    detalle_sugerencia_service,
    excel_export,
    recurrentes_service,
    sugerido_service,
)
from ..services.auth import requiere_escritura


def _recurrente_out(rec) -> RecurrenteOut:
    return RecurrenteOut(
        id=rec.id, modo=rec.modo, resumen=recurrentes_service.resumen(rec),
        unidades=rec.unidades, dias_inventario=rec.dias_inventario,
        stock_objetivo=rec.stock_objetivo,
        motivo=rec.motivo, cada_dias=rec.cada_dias,
        proxima_ejecucion=rec.proxima_ejecucion, fecha_fin=rec.fecha_fin,
        activa=rec.activa, ultima_ejecucion=rec.ultima_ejecucion,
    )

router = APIRouter(prefix="/api/sugerencias-manuales", tags=["sugerencias manuales"])
settings = get_settings()


def _n(x: float) -> str:
    """Numero corto: sin decimales cuando es entero (5 y no 5.0)."""
    return f"{x:.0f}" if float(x).is_integer() else f"{x:.1f}"


def _validar_producto(db: Session, producto: str) -> None:
    """Rechaza codigos que no existen ni en el sugerido ni en el catalogo maestro.

    El campo Producto del modal es texto libre (el autocomplete es una ayuda, no una
    obligacion), asi que un codigo mal tipeado se guardaba igual. Despues no hay de
    donde sacar descripcion, costo ni proveedor: la fila aparece entera en blanco en
    la grilla y en el Excel, y no hay forma de saber que producto era. Mejor no
    dejarla entrar."""
    if not sugerido_service.producto_existe(db, producto):
        raise HTTPException(
            status_code=422,
            detail=(
                f"El codigo '{producto}' no existe en el catalogo ni en el sugerido. "
                "Revisalo y eligelo de la lista que aparece al escribir."
            ),
        )


def _desglose(d: dict) -> str:
    """Texto con las partes que cubren el nivel, omitiendo las que estan en cero.

    Nombra las bodegas: decir "hay 3" sin decir donde deja al usuario sin forma de
    comprobarlo (el producto puede ni siquiera aparecer en la grilla)."""
    bodegas = d.get("bodegas") or []
    detalle_bodegas = (
        " (" + ", ".join(f"{b['bodega']}: {_n(b['stock'])}" for b in bodegas[:4]) + ")"
        if bodegas
        else ""
    )
    partes = [f"{_n(d['stock'])} en stock{detalle_bodegas}"]
    if d["transito"]:
        partes.append(f"{_n(d['transito'])} en transito")
    if d["sugerido_sistema"]:
        partes.append(f"{_n(d['sugerido_sistema'])} que ya sugiere el sistema")
    return " + ".join(partes) + f" = {_n(d['cubierto'])} u"


# --------------------------------------------------------------------------- #
# Detalle de una sugerencia: que productos toca y cuanto aporta cada uno.
# Va ANTES del catch-all `/{id}` de mas abajo, si no FastAPI enruta "detalle"
# como si fuera el id de una sugerencia.
# --------------------------------------------------------------------------- #
@router.get("/detalle/{tipo}/{id_}/excel")
def detalle_a_excel(tipo: str, id_: str, db: Session = Depends(get_db)):
    """La misma lista del detalle, en Excel, para mandarsela a alguien."""
    from fastapi.responses import StreamingResponse

    d = detalle_sugerencia_service.detalle(db, tipo, id_)
    columnas = [
        "producto", "descripcion", "nombre_sucursal", "clasificacion_abc", "proveedor",
        "stock_actual", "stock_transito", "sugerido_modelo", "aporta",
        "total_con_sugerencia", "costo_unitario", "valor_aporte_clp",
        "estado", "motivo_sin_efecto",
    ]
    contenido = excel_export.generar_excel(d["lineas"], columnas)
    nombre = f"sugerencia_{tipo}_{_sanear(id_)}.xlsx"
    return StreamingResponse(
        iter([contenido]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{nombre}"',
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )


def _sanear(texto: str) -> str:
    """Id usable en un nombre de archivo."""
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in texto)[:40]


@router.get("/detalle/{tipo}/{id_}")
def detalle_sugerencia(tipo: str, id_: str, db: Session = Depends(get_db)) -> dict:
    """Cabecera + lineas de una sugerencia (`unica`, `lote`, `recurrente`, `instock`)."""
    return detalle_sugerencia_service.detalle(db, tipo, id_)


@router.patch("/recurrentes/{id}/activa")
def pausar_recurrente(
    id: str,
    payload: dict,
    db: Session = Depends(get_db),
    email: str = Depends(requiere_escritura),
) -> dict:
    """Pausa o reactiva una regla recurrente sin borrarla.

    Antes la unica accion era eliminar: para suspenderla un mes habia que borrarla
    y recrearla, perdiendo el historial y el motivo original.
    """
    activa = bool(payload.get("activa"))
    r = detalle_sugerencia_service.pausar(db, id, activa, usuario_email=email)
    auditoria_service.registrar(
        db,
        accion="recurrente_reactivada" if activa else "recurrente_pausada",
        entidad="sugerencia_recurrente",
        entidad_id=id,
        usuario_email=email,
    )
    db.commit()
    return r


@router.get("/previsualizar-objetivo")
def previsualizar_objetivo(
    producto: str = Query(...),
    sucursal_id: str = Query(...),
    stock_objetivo: int = Query(..., gt=0),
    db: Session = Depends(get_db),
):
    """Que pasaria si se pide mantener ese nivel, ANTES de guardar.

    Devuelve el desglose para que la pantalla explique de donde sale el numero en
    vez de mostrar un total que el usuario tiene que creer."""
    d = sugerido_service.detalle_objetivo(db, producto, sucursal_id, stock_objetivo)
    return {**d, "desglose": _desglose(d)}


@router.get("/previsualizar-dias")
def previsualizar_dias(
    producto: str = Query(...),
    sucursal_id: str = Query(...),
    dias: int = Query(..., gt=0),
    db: Session = Depends(get_db),
):
    """Que pasaria al pedir esos dias de inventario, ANTES de guardar.

    Mismo contrato que la vista previa del modo objetivo. El caso sin demanda se
    responde 200 con `sin_demanda`: es informacion util para la pantalla, no un
    error, y asi el usuario lo ve al tipear en vez de al guardar."""
    d = sugerido_service.detalle_dias(db, producto, sucursal_id, dias)
    if d is None:
        return {"sin_demanda": True, "dias": dias}
    return {**d, "sin_demanda": False, "desglose": _desglose(d)}


@router.get("", response_model=list[SugerenciaManualOut])
def listar(
    producto: str | None = Query(None),
    sucursal_id: str | None = Query(None),
    incluir_archivadas: bool = Query(False, description="Incluir las de ciclos anteriores"),
    solo_unicas: bool = Query(
        False,
        description="Solo sugerencias unicas (no instancias generadas por una regla recurrente)",
    ),
    db: Session = Depends(get_db),
):
    stmt = select(SugerenciaManual)
    if producto:
        stmt = stmt.where(SugerenciaManual.producto == producto)
    if sucursal_id:
        stmt = stmt.where(SugerenciaManual.sucursal_id == sucursal_id)
    if not incluir_archivadas:
        stmt = stmt.where(SugerenciaManual.archivada.is_(False))
    if solo_unicas:
        stmt = stmt.where(SugerenciaManual.recurrente_id.is_(None))
    stmt = stmt.order_by(SugerenciaManual.creado_en.desc())
    filas = list(db.scalars(stmt).all())
    return _con_contexto(db, filas)


def _con_contexto(db: Session, filas: list[SugerenciaManual]) -> list[SugerenciaManualOut]:
    """Agrega a cada sugerencia los datos del producto para poder leer la lista.

    Sin esto la pantalla muestra el codigo pelado y hay que ir al catalogo a ver
    que repuesto es, en que sucursal esta y cuanto cuesta. El contexto sale del
    mismo camino que llena la grilla del sugerido, asi los dos dicen lo mismo.
    """
    if not filas:
        return []
    ctx = sugerido_service.contexto_de_pares(
        db,
        [(f.producto, f.sucursal_id) for f in filas],
        [float(f.unidades) for f in filas],
    )
    salida: list[SugerenciaManualOut] = []
    for f, c in zip(filas, ctx):
        out = SugerenciaManualOut.model_validate(f)
        out.descripcion = c.get("descripcion")
        out.nombre_sucursal = c.get("nombre_sucursal")
        out.marca = c.get("filtro1_final")
        out.proveedor = c.get("proveedor")
        out.costo_unitario = c.get("costo_unitario")
        out.valor_clp = c.get("total_valor_sugerido_clp")
        out.stock_actual = c.get("stock_activo_suc")
        salida.append(out)
    return salida


@router.post("", response_model=SugerenciaManualOut, status_code=201)
def crear(
    payload: SugerenciaManualCreate,
    db: Session = Depends(get_db),
    email: str = Depends(requiere_escritura),
):
    _validar_producto(db, payload.producto)
    if payload.dias_inventario:
        d = sugerido_service.detalle_dias(
            db, payload.producto, payload.sucursal_id, payload.dias_inventario
        )
        if d is None:
            raise HTTPException(
                status_code=400,
                detail="Sin demanda diaria para este producto/sucursal. Usa modo 'unidades'.",
            )
        unidades = d["faltante"]
        if unidades == 0:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Los {payload.dias_inventario} dias ({d['objetivo']} u) ya estan "
                    f"cubiertos: {_desglose(d)}, alcanza para "
                    f"{_n(d['dias_cubiertos'])} dias. Hoy no hay nada que pedir."
                ),
            )
    elif payload.stock_objetivo:
        # Funciona aunque el producto no este en el sugerido de esa sucursal: ahi
        # el stock sale de las bodegas y se pide el nivel completo si no hay nada.
        d = sugerido_service.detalle_objetivo(
            db, payload.producto, payload.sucursal_id, payload.stock_objetivo
        )
        unidades = d["faltante"]
        if unidades == 0:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"El nivel de {payload.stock_objetivo} u ya esta cubierto: "
                    f"{_desglose(d)}. Hoy no hay nada que pedir. Marca "
                    "'Repetir periodicamente' para dejarlo como regla y que se "
                    "reponga solo cuando el stock baje."
                ),
            )
    elif payload.unidades:
        unidades = payload.unidades
    else:
        raise HTTPException(
            status_code=400, detail="Falta unidades, dias_inventario o stock_objetivo."
        )
    s = SugerenciaManual(
        producto=payload.producto,
        sucursal_id=payload.sucursal_id,
        unidades=unidades,
        motivo=payload.motivo,
        creado_por=email,
        tenant_id=settings.default_tenant_id,
        expira_en=_expira_en(payload.expira_en),
        dias_inventario=payload.dias_inventario,
        stock_objetivo=payload.stock_objetivo,
    )
    db.add(s)
    db.flush()
    auditoria_service.registrar(
        db, accion="creada", entidad="sugerencia_manual", entidad_id=s.id,
        usuario_email=email, producto=s.producto, sucursal_id=s.sucursal_id,
        unidades=unidades, dias_inventario=payload.dias_inventario, motivo=payload.motivo,
        detalle=(
            f"Mantener {payload.stock_objetivo} u en stock" if payload.stock_objetivo else None
        ),
    )
    auditoria_service.notificar(
        db, tipo="sugerencia_creada",
        titulo=f"{email.split('@')[0]} sugirio {s.producto}",
        mensaje=f"+{unidades} u en {s.sucursal_id}"
        + (f". Motivo: {s.motivo}" if s.motivo else ""),
        creado_por_email=email, producto=s.producto, sucursal_id=s.sucursal_id,
    )
    db.commit()
    db.refresh(s)
    return s


@router.post("/masiva", response_model=SugerenciaManualMasivaResultado, status_code=201)
def crear_masiva(
    payload: SugerenciaManualMasiva,
    db: Session = Depends(get_db),
    email: str = Depends(requiere_escritura),
):
    """Crea una sugerencia manual para cada producto x sucursal que cumple los filtros.

    Modo 'dias_inventario': calcula lo que falta para cubrir esos dias segun la
    demanda_diaria del BI; quedan omitidos los pares sin demanda y los que ya tienen
    esos dias cubiertos. Modo 'unidades': mismo numero para todos.

    Todas las filas creadas en esta llamada comparten un mismo `lote_id` (UUID4)
    para poder borrarlas juntas despues con DELETE /lote/{lote_id}.
    """
    import uuid as _uuid_mod

    pares = sugerido_service.pares_filtrados(db, payload.filtros)
    omitidas = 0
    nuevas: list[SugerenciaManual] = []
    lote_id = str(_uuid_mod.uuid4())
    expira_en = _expira_en(payload.expira_en)
    if payload.dias_inventario or payload.stock_objetivo:
        if payload.stock_objetivo:
            # Omitidos aca = productos que YA estan en el nivel pedido (no falta nada).
            mapa = sugerido_service.unidades_objetivo_por_par(db, pares, payload.stock_objetivo)
        # Por dias: omitidos = sin demanda diaria o con esos dias ya cubiertos.
        else:
            mapa = sugerido_service.unidades_por_par(db, pares, payload.dias_inventario)
        for par in pares:
            u = mapa.get(par)
            if u is None:
                omitidas += 1
                continue
            nuevas.append(
                SugerenciaManual(
                    producto=par[0], sucursal_id=par[1], unidades=u,
                    motivo=payload.motivo, creado_por=email,
                    tenant_id=settings.default_tenant_id,
                    lote_id=lote_id, expira_en=expira_en,
                    dias_inventario=payload.dias_inventario,
                    stock_objetivo=payload.stock_objetivo,
                )
            )
    elif payload.unidades:
        nuevas = [
            SugerenciaManual(
                producto=p, sucursal_id=s, unidades=payload.unidades,
                motivo=payload.motivo, creado_por=email,
                tenant_id=settings.default_tenant_id,
                lote_id=lote_id, expira_en=expira_en,
            )
            for p, s in pares
        ]
    else:
        raise HTTPException(
            status_code=400, detail="Falta unidades, dias_inventario o stock_objetivo."
        )
    db.add_all(nuevas)
    db.flush()
    # Ya trae el signo: ni dias ni objetivo "suman N", los dos completan un nivel.
    cantidad_str = (
        f"cubrir {payload.dias_inventario} dias de inventario" if payload.dias_inventario
        else f"mantener {payload.stock_objetivo} u en stock" if payload.stock_objetivo
        else f"+{payload.unidades} u"
    )
    auditoria_service.registrar(
        db, accion="masiva_creada", entidad="sugerencia_manual",
        entidad_id=lote_id,
        usuario_email=email, unidades=payload.unidades,
        dias_inventario=payload.dias_inventario, motivo=payload.motivo,
        detalle=f"Masiva: {len(nuevas)} pares, {omitidas} omitidos, {cantidad_str} (lote {lote_id[:8]})",
    )
    razon_omitidas = (
        "ya estaban en nivel" if payload.stock_objetivo else "sin demanda o ya cubiertos"
    )
    auditoria_service.notificar(
        db, tipo="masiva_creada",
        titulo=f"{email.split('@')[0]} cargo {len(nuevas)} sugerencias",
        mensaje=f"{cantidad_str} por producto"
        + (f". Motivo: {payload.motivo}" if payload.motivo else "")
        + (f". {omitidas} omitidos ({razon_omitidas})." if omitidas else ""),
        creado_por_email=email,
    )
    db.commit()
    # Si no se creo ninguna (todas omitidas), no devolver lote_id que apunta a nada.
    lote_id_resp = lote_id if nuevas else None
    return SugerenciaManualMasivaResultado(
        creadas=len(nuevas), omitidas=omitidas, lote_id=lote_id_resp
    )


@router.post("/pegada", response_model=SugerenciaManualPegadaResultado)
def crear_pegada(
    payload: SugerenciaManualPegada,
    db: Session = Depends(get_db),
    email: str = Depends(requiere_escritura),
):
    """Crea sugerencias desde una lista pegada, con una cantidad por linea.

    La otra masiva aplica UN criterio a todos los pares de un filtro; esta acepta
    un Excel armado a mano donde cada linea lleva lo suyo (unidades, dias o nivel
    a mantener). Si una linea trae mas de uno manda `mantener` > `dias` >
    `unidades`, el mismo orden del modal por filtros.

    Con `previsualizar=True` no escribe nada y devuelve lo que se crearia, ya
    calculado: es una lista hecha a mano, conviene verla antes de guardarla.
    """
    import uuid as _uuid_mod

    leido = carga_manual_service.parsear(payload.texto)
    filas = leido["filas"]
    if not filas:
        return SugerenciaManualPegadaResultado(
            errores=leido["errores"],
            encabezado_detectado=leido["encabezado_detectado"],
        )

    # Los criterios "dias" y "mantener" necesitan la demanda y el stock del par,
    # que se resuelven en bloque para no hacer una query por linea.
    por_criterio: dict[str, list[tuple[str, str]]] = {}
    for f in filas:
        por_criterio.setdefault(f["criterio"], []).append((f["producto"], f["sucursal"]))

    calculado: dict[tuple[str, str, str], int] = {}
    for crit, pares in por_criterio.items():
        if crit == "unidades":
            continue
        # Cada linea puede pedir un numero distinto de dias/nivel, asi que se
        # agrupa por valor: los que piden lo mismo se resuelven en una query.
        por_valor: dict[int, list[tuple[str, str]]] = {}
        for f in filas:
            if f["criterio"] != crit:
                continue
            por_valor.setdefault(f[crit], []).append((f["producto"], f["sucursal"]))
        for valor, ps in por_valor.items():
            mapa = (
                sugerido_service.unidades_objetivo_por_par(db, ps, valor)
                if crit == "mantener"
                else sugerido_service.unidades_por_par(db, ps, valor)
            )
            for par, u in mapa.items():
                calculado[(crit, par[0], par[1])] = u

    lote_id = str(_uuid_mod.uuid4())
    expira_en = _expira_en(payload.expira_en)
    salida: list[LineaManualPegada] = []
    nuevas: list[SugerenciaManual] = []

    for f in filas:
        crit = f["criterio"]
        par = (f["producto"], f["sucursal"])
        if crit == "unidades":
            u, motivo_omision = f["unidades"], None
        else:
            u = calculado.get((crit, *par))
            motivo_omision = (
                None if u is not None
                else "Ya está en el nivel pedido." if crit == "mantener"
                else "Sin demanda para calcular los días, o ya están cubiertos."
            )
        salida.append(LineaManualPegada(**f, unidades_resultantes=u,
                                        omitida_porque=motivo_omision))
        if u is None:
            continue
        nuevas.append(
            SugerenciaManual(
                producto=f["producto"], sucursal_id=f["sucursal"], unidades=u,
                motivo=payload.motivo, creado_por=email,
                tenant_id=settings.default_tenant_id,
                lote_id=lote_id, expira_en=expira_en,
                dias_inventario=f["dias"], stock_objetivo=f["mantener"],
            )
        )

    omitidas = len(filas) - len(nuevas)
    if payload.previsualizar:
        return SugerenciaManualPegadaResultado(
            creadas=0, omitidas=omitidas, lineas=salida,
            errores=leido["errores"],
            encabezado_detectado=leido["encabezado_detectado"],
        )

    db.add_all(nuevas)
    db.flush()
    auditoria_service.registrar(
        db, accion="masiva_creada", entidad="sugerencia_manual", entidad_id=lote_id,
        usuario_email=email, motivo=payload.motivo,
        detalle=f"Lista pegada: {len(nuevas)} lineas, {omitidas} omitidas, "
                f"{len(leido['errores'])} con error (lote {lote_id[:8]})",
    )
    auditoria_service.notificar(
        db, tipo="masiva_creada",
        titulo=f"{email.split('@')[0]} pego {len(nuevas)} sugerencias",
        mensaje="Cada línea con su propia cantidad"
        + (f". Motivo: {payload.motivo}" if payload.motivo else "")
        + (f". {omitidas} omitidas." if omitidas else ""),
        creado_por_email=email,
    )
    db.commit()
    return SugerenciaManualPegadaResultado(
        creadas=len(nuevas), omitidas=omitidas,
        lote_id=lote_id if nuevas else None,
        errores=leido["errores"],
        encabezado_detectado=leido["encabezado_detectado"],
    )


@router.post("/recurrentes", response_model=RecurrenteOut, status_code=201)
def crear_recurrente(
    payload: RecurrenteCreate,
    db: Session = Depends(get_db),
    email: str = Depends(requiere_escritura),
):
    """Crea una regla recurrente y la aplica de inmediato (primera instancia)."""
    if payload.modo == "individual" and not (payload.producto and payload.sucursal_id):
        raise HTTPException(status_code=400, detail="Falta producto o sucursal.")
    if payload.modo == "individual":
        # Una recurrente crea una manual nueva cada N dias: un codigo invalido aca
        # fabricaria una fila en blanco por ciclo, para siempre.
        _validar_producto(db, payload.producto)
    if not payload.unidades and not payload.dias_inventario and not payload.stock_objetivo:
        raise HTTPException(
            status_code=400, detail="Falta unidades, dias_inventario o stock_objetivo."
        )
    rec = recurrentes_service.crear(db, payload, usuario_email=email)
    return _recurrente_out(rec)


@router.get("/recurrentes", response_model=list[RecurrenteOut])
def listar_recurrentes(
    incluir_inactivas: bool = Query(False), db: Session = Depends(get_db)
):
    return [_recurrente_out(r) for r in recurrentes_service.listar(db, incluir_inactivas)]


@router.delete("/recurrentes/{id}", status_code=204)
def eliminar_recurrente(
    id: str,
    db: Session = Depends(get_db),
    email: str = Depends(requiere_escritura),
):
    rec = recurrentes_service.eliminar(db, id, usuario_email=email)
    if not rec:
        raise HTTPException(status_code=404, detail="Recurrencia no encontrada")


@router.delete("/lote/{lote_id}")
def eliminar_lote(
    lote_id: str,
    db: Session = Depends(get_db),
    email: str = Depends(requiere_escritura),
):
    """Elimina todas las sugerencias creadas en una misma carga masiva.

    Solo borra filas con `recurrente_id` NULL (no toca instancias de reglas
    recurrentes). Si el lote no existe o esta vacio, devuelve 404.
    """
    # Tomamos info representativa (motivo, unidades, etc.) antes de borrar para
    # el log y la notificacion.
    filas = list(
        db.scalars(
            select(SugerenciaManual).where(
                SugerenciaManual.lote_id == lote_id,
                SugerenciaManual.recurrente_id.is_(None),
            )
        ).all()
    )
    if not filas:
        raise HTTPException(status_code=404, detail="Lote no encontrado")
    motivo = filas[0].motivo
    n = len(filas)
    for f in filas:
        db.delete(f)
    auditoria_service.registrar(
        db, accion="lote_eliminado", entidad="sugerencia_manual",
        entidad_id=lote_id, usuario_email=email, motivo=motivo,
        detalle=f"Carga masiva eliminada: {n} sugerencias (lote {lote_id[:8]})",
    )
    auditoria_service.notificar(
        db, tipo="lote_eliminado",
        titulo=f"{email.split('@')[0]} elimino una carga masiva",
        mensaje=f"{n} sugerencias eliminadas"
        + (f". Motivo original: {motivo}" if motivo else ""),
        creado_por_email=email,
    )
    db.commit()
    return {"eliminadas": n}


@router.patch("/{id}", response_model=SugerenciaManualOut)
def actualizar(
    id: str,
    payload: SugerenciaManualUpdate,
    db: Session = Depends(get_db),
    email: str = Depends(requiere_escritura),
):
    s = db.get(SugerenciaManual, id)
    if not s:
        raise HTTPException(status_code=404, detail="Sugerencia no encontrada")
    data = payload.model_dump(exclude_unset=True)
    unidades_antes = s.unidades
    cambios = []
    for k, v in data.items():
        antes = getattr(s, k)
        if antes != v:
            cambios.append(f"{k}: {antes} -> {v}")
        setattr(s, k, v)
    if cambios:
        auditoria_service.registrar(
            db, accion="modificada", entidad="sugerencia_manual", entidad_id=s.id,
            usuario_email=email, producto=s.producto, sucursal_id=s.sucursal_id,
            unidades=s.unidades, motivo=s.motivo, detalle="; ".join(cambios),
        )
        if "unidades" in data and unidades_antes != s.unidades:
            auditoria_service.notificar(
                db, tipo="sugerencia_modificada",
                titulo=f"{email.split('@')[0]} ajusto {s.producto}",
                mensaje=f"{s.sucursal_id}: {unidades_antes} -> {s.unidades} u",
                creado_por_email=email, producto=s.producto, sucursal_id=s.sucursal_id,
            )
    db.commit()
    db.refresh(s)
    return s


@router.delete("/{id}", status_code=204)
def eliminar(
    id: str,
    db: Session = Depends(get_db),
    email: str = Depends(requiere_escritura),
):
    s = db.get(SugerenciaManual, id)
    if not s:
        raise HTTPException(status_code=404, detail="Sugerencia no encontrada")
    snap = {
        "id": s.id, "producto": s.producto, "sucursal_id": s.sucursal_id,
        "unidades": s.unidades, "motivo": s.motivo,
    }
    db.delete(s)
    auditoria_service.registrar(
        db, accion="eliminada", entidad="sugerencia_manual", entidad_id=snap["id"],
        usuario_email=email, producto=snap["producto"], sucursal_id=snap["sucursal_id"],
        unidades=snap["unidades"], motivo=snap["motivo"],
    )
    auditoria_service.notificar(
        db, tipo="sugerencia_eliminada",
        titulo=f"{email.split('@')[0]} elimino sugerencia de {snap['producto']}",
        mensaje=f"{snap['sucursal_id']}: -{snap['unidades']} u",
        creado_por_email=email, producto=snap["producto"], sucursal_id=snap["sucursal_id"],
    )
    db.commit()
