"""Bandeja de requerimientos: el vendedor arma el carro, el comprador lo resuelve.

Dos publicos en los mismos endpoints, separados por rol:

- **Vendedor** (`usuario.es_vendedor`): busca en la lista de precios, crea, y ve
  SOLO los suyos. Todo lo demas de la plataforma le da 403 (`requiere_comprador`).
- **Comprador**: ve todos, los revisa y los cierra. No puede crear: un
  requerimiento nace en la sucursal, si no el registro miente sobre quien pidio.

La pantalla de pegar lista (`routers/requerimiento.py`, en singular) sigue ahi
para lo que llegue por fuera de la plataforma; las dos comparten el analisis.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Usuario
from ..schemas import (
    ProductoBuscado,
    ProductoPegado,
    RequerimientoCreate,
    RequerimientoOut,
    RequerimientoUpdate,
    RequerimientosPage,
)
from ..services import auditoria_service, requerimiento_service
from ..services.auth import (
    es_vendedor,
    requiere_auth,
    requiere_comprador,
    requiere_vendedor,
    sucursales_del_vendedor,
)

router = APIRouter(prefix="/api/requerimientos", tags=["requerimientos"])


def _sucursal_a_usar(db: Session, email: str, pedida: str | None) -> str:
    """La sucursal por la que pide este vendedor. NUNCA la escribe el: sale del usuario.

    Con una sola sucursal asignada no hay nada que elegir. Con varias, tiene que
    ser una de las suyas. Sin ninguna, el usuario esta mal configurado y no puede
    pedir: dejarlo pedir por cualquiera seria peor que el correo que reemplaza.
    """
    suyas = sucursales_del_vendedor(email, db)
    usuario = db.get(Usuario, email)
    if usuario and usuario.es_admin and not suyas:
        # El admin prueba la vista sin tener sucursal asignada.
        if not pedida:
            raise HTTPException(status_code=400, detail="Elige la sucursal del requerimiento.")
        return pedida
    if not suyas:
        raise HTTPException(
            status_code=400,
            detail="Tu usuario no tiene sucursal asignada. Pídele a un administrador que te la configure.",
        )
    if not pedida:
        if len(suyas) == 1:
            return suyas[0]
        raise HTTPException(status_code=400, detail="Elige la sucursal del requerimiento.")
    if pedida not in suyas:
        raise HTTPException(status_code=403, detail=f"No puedes pedir por la sucursal {pedida}.")
    return pedida


@router.get("/mis-sucursales")
def mis_sucursales(email: str = Depends(requiere_auth), db: Session = Depends(get_db)) -> dict:
    """Sucursales por las que puede pedir el usuario, para no hacerlo escribirlas."""
    suyas = sucursales_del_vendedor(email, db)
    usuario = db.get(Usuario, email)
    return {
        "sucursales": suyas,
        "es_vendedor": bool(usuario and usuario.es_vendedor),
        "puede_elegir": len(suyas) > 1 or bool(usuario and usuario.es_admin and not suyas),
    }


@router.get("/buscar", response_model=list[ProductoBuscado])
def buscar(
    q: str = Query(..., min_length=2, description="Código o descripción"),
    sucursal_id: str | None = Query(None),
    limit: int = Query(25, ge=1, le=100),
    email: str = Depends(requiere_auth),
    db: Session = Depends(get_db),
):
    """Buscador del carro. Solo devuelve productos de la lista de precios de Curifor."""
    return requerimiento_service.buscar_productos(db, q, sucursal_id=sucursal_id, limit=limit)


@router.post("/pegar", response_model=list[ProductoPegado])
def pegar(
    payload: dict,
    email: str = Depends(requiere_auth),
    db: Session = Depends(get_db),
):
    """Lista pegada -> lineas del carro, sin escribir ningun codigo a mano.

    El vendedor muchas veces YA tiene la lista en un Excel o en un WhatsApp. Que
    tenga que buscar producto por producto seria hacerle mas trabajo del que
    hacia antes, y volveria al correo. Usa el mismo parseo que la pantalla del
    comprador (incluida la ambiguedad de "70 2723982"), y devuelve solo lo que
    existe en la lista de precios: lo que no existe no puede entrar al carro.
    """
    texto = str(payload.get("texto") or "")
    sucursal_id = payload.get("sucursal_id") or None
    lineas = requerimiento_service.parsear(db, texto)
    return requerimiento_service.desde_lista_pegada(db, lineas, sucursal_id=sucursal_id)


@router.get("", response_model=RequerimientosPage)
def listar(
    estado: list[str] = Query(default=[]),
    email: str = Depends(requiere_auth),
    db: Session = Depends(get_db),
):
    """La bandeja. El vendedor ve los suyos; el comprador, todos."""
    if es_vendedor(email, db):
        return requerimiento_service.listar_bandeja(db, email=email, estados=estado or None)
    return requerimiento_service.listar_bandeja(db, estados=estado or None)


@router.post("", response_model=RequerimientoOut, status_code=201)
def crear(
    payload: RequerimientoCreate,
    email: str = Depends(requiere_vendedor),
    db: Session = Depends(get_db),
):
    """Envia el carro. A partir de aca el requerimiento es de solo lectura para la sucursal."""
    sucursal = _sucursal_a_usar(db, email, payload.sucursal_id)
    usuario = db.get(Usuario, email)
    req = requerimiento_service.crear(
        db,
        sucursal_id=sucursal,
        email=email,
        nombre=usuario.nombre if usuario else None,
        lineas=[l.model_dump() for l in payload.lineas],
        nota=payload.nota,
    )
    auditoria_service.registrar(
        db,
        accion="requerimiento_creado",
        entidad="requerimiento",
        entidad_id=str(req.id),
        usuario_email=email,
        detalle=f"{sucursal}: {len(req.lineas)} líneas",
    )
    # Campanita del equipo de compras: la bandeja no se mira sola.
    auditoria_service.notificar(
        db,
        tipo="requerimiento_nuevo",
        titulo=f"Requerimiento #{req.id} de {req.nombre_sucursal or sucursal}",
        mensaje=(
            f"{req.creado_por_nombre or email} pidió {len(req.lineas)} "
            f"{'repuesto' if len(req.lineas) == 1 else 'repuestos'}."
            + (f" «{req.nota}»" if req.nota else "")
        ),
        creado_por_email=email,
        sucursal_id=sucursal,
    )
    db.commit()
    return requerimiento_service.detalle(db, req.id)


@router.get("/{req_id}", response_model=RequerimientoOut)
def detalle(
    req_id: int,
    email: str = Depends(requiere_auth),
    db: Session = Depends(get_db),
):
    """Detalle. Al comprador le llega ademas el analisis para decidir.

    Abrirlo deja acuse de recibo (`enviado` -> `en_revision`): el vendedor hoy no
    tiene forma de saber si su correo se leyo, y esa es medio la gracia.
    """
    req = requerimiento_service.obtener(db, req_id)
    vendedor = es_vendedor(email, db)
    if vendedor and req.creado_por != email:
        raise HTTPException(status_code=403, detail="Ese requerimiento no es tuyo.")
    if not vendedor:
        requerimiento_service.marcar_en_revision(db, req, email)
    return requerimiento_service.detalle(db, req_id, con_analisis=not vendedor)


@router.get("/producto/{producto:path}")
def contexto_producto(
    producto: str,
    sucursal_id: str | None = None,
    email: str = Depends(requiere_auth),
    db: Session = Depends(get_db),
) -> dict:
    """Contexto de un repuesto para el vendedor que esta armando su lista.

    Va suelto (sin req_id) a proposito: se consulta ANTES de crear el
    requerimiento, cuando la lista todavia se esta armando.

    La sucursal sale del USUARIO cuando es vendedor, no del parametro: si no, un
    vendedor podria mirar el consumo de una sucursal ajena cambiando la URL.

    Devuelve venta, stock de la red y transito, SIN costo ni margen.
    """
    if es_vendedor(email, db):
        sucursal = _sucursal_a_usar(db, email, sucursal_id)
    elif not sucursal_id:
        raise HTTPException(status_code=400, detail="Falta la sucursal.")
    else:
        sucursal = sucursal_id
    return requerimiento_service.contexto_para_vendedor(db, producto, sucursal)


@router.get("/{req_id}/producto/{producto:path}")
def detalle_producto(
    req_id: int,
    producto: str,
    email: str = Depends(requiere_comprador),
    db: Session = Depends(get_db),
) -> dict:
    """Consumo, transito, stock, modelo y margen de UNA linea del requerimiento.

    Va colgado del requerimiento (y no suelto por producto) porque la sucursal
    sale de ahi: el mismo repuesto se decide distinto en Linderos que en Curico.
    Solo comprador: es el contexto con el que se aprueba una compra.
    """
    req = requerimiento_service.obtener(db, req_id)
    return requerimiento_service.detalle_producto(db, producto, req.sucursal_id)


@router.patch("/{req_id}", response_model=RequerimientoOut)
def actualizar(
    req_id: int,
    payload: RequerimientoUpdate,
    email: str = Depends(requiere_comprador),
    db: Session = Depends(get_db),
):
    """Decision del comprador: cantidades aprobadas, nota y estado final."""
    salida = requerimiento_service.actualizar(
        db,
        req_id,
        email=email,
        estado=payload.estado,
        nota_comprador=payload.nota_comprador,
        cantidades=[c.model_dump() for c in payload.cantidades],
    )
    if payload.estado:
        auditoria_service.registrar(
            db,
            accion=f"requerimiento_{payload.estado}",
            entidad="requerimiento",
            entidad_id=str(req_id),
            usuario_email=email,
        )
        # Aviso PERSONAL al vendedor: el correo nunca le dijo en que quedo lo
        # que pidio; esta campanita es justamente esa respuesta.
        if payload.estado in ("procesado", "rechazado"):
            comprado = payload.estado == "procesado"
            auditoria_service.notificar(
                db,
                tipo=f"requerimiento_{payload.estado}",
                titulo=(
                    f"Tu requerimiento #{req_id} fue "
                    + ("comprado" if comprado else "rechazado")
                ),
                mensaje=salida.get("nota_comprador"),
                creado_por_email=email,
                para_email=salida.get("creado_por"),
            )
        db.commit()
    return salida
