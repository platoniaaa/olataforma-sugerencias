"""La lista de precios: verla, decidir sobre un precio, crear productos y exportar al ERP.

Permisos, en dos niveles y por endpoint (el router se monta con el gate de
Abastecimiento, asi que el vendedor de sucursal no entra a nada de esto):

- **Ver y exportar**: cualquiera de Abastecimiento.
- **Editar un precio** (fijo, congelar, tipo, procedencia, crear producto,
  marcar cambios vistos, recalcular): admin o email en `EMAILS_PRECIOS`. Es el
  mismo esquema de Calibracion: quien mantiene la lista no tiene por que
  administrar la plataforma.
- **La politica** (factores y rubros): el mismo permiso que editar un precio.
  Un factor mueve miles de precios de una, mucho mas que un precio fijo, pero
  quien mantiene la lista es quien sabe cuando hay que moverlo. El freno es la
  trazabilidad, no el permiso: cada cambio queda en la auditoria con el usuario
  y el valor anterior.

No va bajo /api/admin por la misma razon tecnica que Calibracion: las
dependencias del include se ejecutan siempre y no se pueden excluir por endpoint.
"""
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..schemas.precios import (
    FactoresIn,
    OverrideIn,
    PoliticaIn,
    PrecioDetalleOut,
    PrecioFiltros,
    PrecioPage,
    PrecioRow,
    ProductoNuevoIn,
    RubrosIn,
    VistosIn,
)
from ..services import operacion_pesada
from ..services import politica_precio_service as politica
from ..services import precios_carga_service as carga
from ..services import precios_service
from ..services.auth import requiere_precios

router = APIRouter(prefix="/api/precios", tags=["precios"])

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _filtros(
    q: str | None = Query(None, description="Busca en codigo o glosa"),
    rubro: list[str] = Query(default=[]),
    tipo: list[str] = Query(default=[]),
    procedencia: list[str] = Query(default=[]),
    estado: list[str] = Query(default=[]),
    origen: str | None = Query(None, description="maestro | manual"),
    con_cambios: bool = Query(False, description="Solo productos con cambios sin revisar"),
    con_stock: bool = Query(False),
) -> PrecioFiltros:
    return PrecioFiltros(
        q=q, rubro=rubro, tipo=tipo, procedencia=procedencia, estado=estado,
        origen=origen, con_cambios=con_cambios, con_stock=con_stock,
    )


# ------------------------------------------------------------------ lectura
@router.get("", response_model=PrecioPage)
def listar(
    f: PrecioFiltros = Depends(_filtros),
    page: int = Query(1, ge=1),
    limit: int = Query(200, ge=1, le=2000),
    sort: str | None = Query(None, description="columna, con '-' adelante para descendente"),
    db: Session = Depends(get_db),
) -> PrecioPage:
    items, total = precios_service.listar(db, f, page=page, limit=limit, sort=sort)
    return PrecioPage(items=[PrecioRow.model_validate(i) for i in items], total=total, page=page, limit=limit)


@router.get("/filtros")
def filtros(db: Session = Depends(get_db)) -> dict:
    return precios_service.opciones_filtros(db)


@router.get("/resumen")
def resumen(db: Session = Depends(get_db)) -> dict:
    return precios_service.resumen(db)


@router.get("/bodegas")
def bodegas(db: Session = Depends(get_db)) -> list[dict]:
    """Que bodegas cuentan para el stock de la lista y cuales no."""
    return precios_service.bodegas_tipo(db)


@router.get("/politica/factores")
def factores(db: Session = Depends(get_db)) -> list[dict]:
    return politica.listar_factores(db)


@router.get("/politica/rubros")
def rubros(db: Session = Depends(get_db)) -> list[dict]:
    return politica.listar_rubros(db)


@router.get("/exportar")
def exportar(
    solo_diferencias: bool = Query(False, description="Solo lo que cambio desde el ultimo envio"),
    formato: str = Query("erp", pattern="^(erp|completa|editable)$"),
    registrar: bool = Query(True, description="Anotar este envio para el proximo delta"),
    lote: str | None = Query(
        None, pattern=r"^[0-9a-fA-F-]{8,64}$",
        description="Identificador de la descarga. Si ya se registro, devuelve el mismo archivo",
    ),
    db: Session = Depends(get_db),
    email: str = Depends(requiere_precios),
):
    """El archivo para bajar. `erp` es el Excel de 3 columnas que el ERP acepta
    (SKU | Precio_Optimo | Descuento); `completa` es la lista entera en CSV, para
    revisar: en Excel tardaba 83 s y el navegador cortaba la descarga.

    Sube el proceso 190 a 230 MB: no se arma durante la carga del sugerido ni junto
    a otra descarga grande (services/operacion_pesada.py). Si le toca esperar de
    mas responde 503, que la web reintenta sola (`reqConReintentos`)."""
    with operacion_pesada.descarga_pesada():
        contenido, nombre, n = precios_service.exportar(
            db, solo_diferencias=solo_diferencias, registrar=registrar and formato == "erp",
            usuario=email, formato=formato, lote_id=lote,
        )
    tipo = "text/csv; charset=utf-8" if nombre.endswith(".csv") else _XLSX
    return StreamingResponse(
        iter([contenido]), media_type=tipo,
        headers={"Content-Disposition": f'attachment; filename="{nombre}"', "X-Filas": str(n)},
    )


# Va ANTES del catch-all {producto:path}, si no FastAPI lo lee como un producto.
@router.get("/{producto:path}", response_model=PrecioDetalleOut)
def detalle(producto: str, db: Session = Depends(get_db)) -> dict:
    d = precios_service.detalle(db, producto)
    if not d:
        raise HTTPException(status_code=404, detail="El producto no esta en la lista de precios")
    return d


# ----------------------------------------------------------------- escritura
@router.post("/recalcular")
def recalcular(
    refrescar_insumos: bool = Query(True),
    db: Session = Depends(get_db),
    email: str = Depends(requiere_precios),
) -> dict:
    """Recalcula toda la lista con el stock, costo y compras que tiene la plataforma."""
    return precios_service.recalcular(db, usuario=email, refrescar_insumos=refrescar_insumos)


@router.post("/cambios/vistos")
def marcar_vistos(
    payload: VistosIn, db: Session = Depends(get_db), email: str = Depends(requiere_precios),
) -> dict:
    return precios_service.marcar_vistos(db, payload.productos, email)


@router.post("", status_code=201, response_model=PrecioRow)
def crear(
    payload: ProductoNuevoIn, db: Session = Depends(get_db), email: str = Depends(requiere_precios),
) -> dict:
    """Un producto nuevo, creado desde la plataforma. Sale en el proximo envio al ERP."""
    try:
        return precios_service.crear_producto(db, payload.model_dump(), email)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.put("/{producto:path}/override", response_model=PrecioRow)
def guardar_override(
    producto: str, payload: OverrideIn,
    db: Session = Depends(get_db), email: str = Depends(requiere_precios),
) -> dict:
    """Precio fijo, congelar, tipo o procedencia a mano. Solo se tocan los campos que vienen."""
    datos = payload.model_dump(exclude_unset=True)
    if not datos:
        raise HTTPException(status_code=422, detail="No viene ningun campo para cambiar")
    try:
        return precios_service.guardar_override(db, producto, datos, email)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.delete("/{producto:path}/override", response_model=PrecioRow)
def quitar_override(
    producto: str, db: Session = Depends(get_db), email: str = Depends(requiere_precios),
) -> dict:
    """Vuelve el producto a la regla: sin precio fijo, sin congelar, sin clasificacion manual."""
    try:
        return precios_service.quitar_override(db, producto, email)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


# ------------------------------------------------------------------ politica
@router.delete("/{producto:path}", status_code=200)
def eliminar(
    producto: str, db: Session = Depends(get_db), email: str = Depends(requiere_precios),
) -> dict:
    """Saca UN producto de la lista de precios.

    No lo da de baja en el ERP: solo deja de tener precio calculado aca y de
    salir en la exportacion. Vuelve si alguien recarga el maestro.

    Reusa `precios_service.eliminar`, que ya conserva el override cuando trae un
    precio fijo o un congelado: es una decision de una persona y borrarla seria
    irreversible. Si el producto vuelve, la decision vuelve con el.

    Va DESPUES de `/{producto}/override` en el archivo: FastAPI resuelve por
    orden y `{producto:path}` es codicioso, asi que declarado antes se comeria
    esa ruta.
    """
    # Desde la pantalla es una decision de persona sobre ese producto: queda
    # protegido y el feed semanal del ERP no lo vuelve a crear.
    r = precios_service.eliminar(db, [producto], email, proteger=True,
                                 motivo="sacado desde la pantalla")
    if not r["eliminados"]:
        raise HTTPException(status_code=404, detail=f"{producto} no esta en la lista de precios")
    return r


@router.put("/politica/factores")
def guardar_factores(
    payload: FactoresIn, db: Session = Depends(get_db), email: str = Depends(requiere_precios),
) -> dict:
    try:
        r = politica.guardar_factores(db, [f.model_dump() for f in payload.filas], email)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    # Un factor nuevo cambia precios: se recalcula con los insumos que ya hay.
    r["recalculo"] = precios_service.recalcular(db, usuario=email, refrescar_insumos=False)
    return r


@router.put("/politica/rubros")
def guardar_rubros(
    payload: RubrosIn, db: Session = Depends(get_db), email: str = Depends(requiere_precios),
) -> dict:
    try:
        r = politica.guardar_rubros(db, [f.model_dump() for f in payload.filas], email)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    r["recalculo"] = precios_service.recalcular(db, usuario=email, refrescar_insumos=False)
    return r


@router.post("/politica/vista-previa")
def vista_previa_politica(
    payload: PoliticaIn, db: Session = Depends(get_db), email: str = Depends(requiere_precios),
) -> dict:
    """Cuantos precios cambiarian con este cambio de politica. No guarda nada."""
    return precios_service.vista_previa_politica(
        db, [f.model_dump() for f in payload.factores], [r.model_dump() for r in payload.rubros],
        payload.seguir_al_rubro,
    )


@router.put("/politica")
def guardar_politica(
    payload: PoliticaIn, db: Session = Depends(get_db), email: str = Depends(requiere_precios),
) -> dict:
    """Guarda factores (incluidos tipos nuevos), rubros y "seguir al rubro" JUNTOS
    y recalcula una sola vez.

    Con los dos botones de antes, crear un tipo y asignarselo a un rubro eran dos
    recalculos de ~5 minutos, y si el segundo fallaba el tipo quedaba creado sin
    uso. Si algo no pasa la validacion, no se guarda nada.

    Se recalculan SOLO los productos que el cambio puede mover, calculados antes
    de guardar contra la politica de hoy: el rubro 35 son ~1.500 de ~40 mil. Un
    tipo que ningun producto usa o un descuento no mueven precios y no recalculan.

    La politica y los precios recalculados se confirman JUNTOS. Antes la politica
    se confirmaba y despues se recalculaba: si el recalculo fallaba (corte de
    Render), la politica quedaba guardada con los precios viejos, y el reintento
    ya no encontraba nada que recalcular porque comparaba contra la politica
    guardada. Hasta el recalculo completo del motor, al dia siguiente.
    """
    factores = [f.model_dump() for f in payload.factores]
    rubros = [r.model_dump() for r in payload.rubros]
    afectados = precios_service.productos_afectados(db, factores, rubros, payload.seguir_al_rubro)
    try:
        rf = politica.guardar_factores(db, factores, email, commit=False)
        rr = politica.guardar_rubros(db, rubros, email, commit=False)
        rs = precios_service.seguir_al_rubro(db, payload.seguir_al_rubro, email)
        # La sesion no hace autoflush: sin esto el recalculo leeria la politica vieja.
        db.flush()
        recalculo = (precios_service.recalcular(db, usuario=email, refrescar_insumos=False,
                                                productos=afectados)
                     if afectados else None)
        db.commit()
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception:
        db.rollback()
        raise
    return {"factores": rf["cambios"], "rubros": rr["cambios"], "seguir_al_rubro": rs,
            "recalculo": recalculo}


# --------------------------------------------------- editar la lista en Excel
def _leer_subida(archivo: UploadFile) -> bytes:
    """El archivo subido, con tope: un cuerpo sin limite agotaria la memoria de Render."""
    contenido = archivo.file.read(carga.MAX_BYTES + 1)
    return contenido


@router.post("/carga/vista-previa")
def carga_vista_previa(
    archivo: UploadFile = File(...), db: Session = Depends(get_db),
    email: str = Depends(requiere_precios),
) -> dict:
    """Lee el archivo editado y dice que cambiaria, sin guardar nada.

    Es `def` y no `async def`: leer 40 mil filas es trabajo de CPU, y en una
    corrutina bloquearia a todos los demas mientras tanto."""
    try:
        return carga.vista_previa(db, archivo.filename or "", _leer_subida(archivo))
    except carga.ErrorCarga as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.post("/carga")
def carga_aplicar(
    archivo: UploadFile = File(...), confirmar_quitas: bool = Form(False),
    confirmar_masiva: bool = Form(False),
    db: Session = Depends(get_db), email: str = Depends(requiere_precios),
) -> dict:
    """Carga los cambios del archivo editado: todos o ninguno. Vuelve a leer el
    archivo y a compararlo contra lo que hay AHORA, asi lo que se aplica es lo que
    dice el archivo y no una vista previa vieja."""
    try:
        return carga.aplicar(db, archivo.filename or "", _leer_subida(archivo), email,
                            confirmar_quitas=confirmar_quitas, confirmar_masiva=confirmar_masiva)
    except carga.ErrorCarga as e:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception:
        db.rollback()
        raise
