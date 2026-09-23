"""Inventario ciclico: carga semanal, conteo en bodega y seguimiento de diferencias.

Admin (jefatura) carga los lunes y ve todo. Bodega cuenta, comenta y sube evidencia
solo en sus sucursales. Los permisos salen de `ic_rol` (ver services/inventario_ciclico_service).
"""
from __future__ import annotations

import io
import json
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response, StreamingResponse
from openpyxl import Workbook
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import IcEvidencia, IcItem, IcRol, Usuario
from ..services import auditoria_service
from ..services import inventario_ciclico_service as svc
from ..services.auth import requiere_auth

router = APIRouter(prefix="/api/inventario-ciclico", tags=["inventario-ciclico"])


# --------------------------- esquemas --------------------------- #
class YoOut(BaseModel):
    rol: str | None
    sucursales: list[str] | None


class EvidenciaOut(BaseModel):
    id: str
    nombre: str
    content_type: str
    tamano: int
    subido_por: str | None
    subido_en: datetime


class ItemOut(BaseModel):
    id: str
    semana: date
    sucursal_id: str
    producto: str
    descripcion: str | None
    clase: str
    cantidad_sistema: float
    costo_unitario: float
    requiere_evidencia: bool
    cantidad_contada: float | None
    observacion: str | None
    contado_por: str | None
    contado_en: datetime | None
    diferencia: float | None
    diferencia_valor: float | None
    estado: str
    evidencias: list[EvidenciaOut]


class ItemUpdate(BaseModel):
    cantidad_contada: float | None = Field(default=None, ge=0)
    observacion: str | None = Field(default=None, max_length=2000)
    requiere_evidencia: bool | None = None


class ResumenSucursal(BaseModel):
    sucursal_id: str
    asignados: int
    contados: int
    pendientes: int
    falta_evidencia: int
    con_diferencia: int
    diferencia_unidades: float
    diferencia_sobrante: float
    diferencia_faltante: float
    clases_faltantes: list[str]
    cuota_sugerida: int
    productos_con_stock: int
    contados_en_el_ano: int


class CargaOut(BaseModel):
    semana: date
    sucursales: list[str]
    insertados: int
    actualizados: int
    conservados: int
    eliminados: int
    avisos: list[str]


class RolOut(BaseModel):
    email: str
    rol: str
    sucursales: list[str] | None
    nombre: str | None
    tiene_usuario: bool


class RolIn(BaseModel):
    rol: str = Field(pattern="^(admin|bodega)$")
    sucursales: list[str] | None = None


# --------------------------- dependencias --------------------------- #
def _acceso(email: str = Depends(requiere_auth), db: Session = Depends(get_db)) -> svc.Acceso:
    acc = svc.acceso(db, email)
    if acc.rol is None:
        raise HTTPException(status_code=403, detail="No tienes acceso al inventario cíclico")
    return acc


def _admin(acc: svc.Acceso = Depends(_acceso)) -> svc.Acceso:
    if not acc.es_admin:
        raise HTTPException(status_code=403, detail="Solo el administrador de inventario puede hacer esto")
    return acc


def _item_visible(db: Session, item_id: str, acc: svc.Acceso) -> IcItem:
    item = db.get(IcItem, item_id)
    if item is None or not acc.ve(item.sucursal_id):
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    return item


def _item_out(item: IcItem, evidencias: list) -> ItemOut:
    dif = None if item.cantidad_contada is None else item.cantidad_contada - item.cantidad_sistema
    return ItemOut(
        id=item.id, semana=item.semana, sucursal_id=item.sucursal_id, producto=item.producto,
        descripcion=item.descripcion, clase=item.clase, cantidad_sistema=item.cantidad_sistema,
        costo_unitario=item.costo_unitario, requiere_evidencia=item.requiere_evidencia,
        cantidad_contada=item.cantidad_contada, observacion=item.observacion,
        contado_por=item.contado_por, contado_en=item.contado_en,
        diferencia=dif, diferencia_valor=None if dif is None else dif * item.costo_unitario,
        estado=svc.estado(item, len(evidencias)),
        evidencias=[
            EvidenciaOut(
                id=e.id, nombre=e.nombre, content_type=e.content_type, tamano=e.tamano,
                subido_por=e.subido_por, subido_en=e.subido_en,
            )
            for e in evidencias
        ],
    )


def _evidencias_por_item(db: Session, item_ids: list[str]) -> dict[str, list]:
    if not item_ids:
        return {}
    # Sin cargar `contenido`: solo metadatos.
    rows = db.execute(
        select(
            IcEvidencia.id, IcEvidencia.item_id, IcEvidencia.nombre, IcEvidencia.content_type,
            IcEvidencia.tamano, IcEvidencia.subido_por, IcEvidencia.subido_en,
        ).where(IcEvidencia.item_id.in_(item_ids)).order_by(IcEvidencia.subido_en)
    ).all()
    out: dict[str, list] = {}
    for r in rows:
        out.setdefault(r.item_id, []).append(r)
    return out


def _semana_o_actual(db: Session, acc: svc.Acceso, semana: date | None) -> date:
    if semana is not None:
        return svc.lunes_de(semana)
    hay = svc.semanas(db, acc)
    return hay[0] if hay else svc.lunes_de(date.today())


# --------------------------- endpoints --------------------------- #
@router.get("/yo", response_model=YoOut)
def yo(email: str = Depends(requiere_auth), db: Session = Depends(get_db)):
    acc = svc.acceso(db, email)
    return YoOut(rol=acc.rol, sucursales=acc.sucursales)


@router.get("/semanas", response_model=list[date])
def listar_semanas(acc: svc.Acceso = Depends(_acceso), db: Session = Depends(get_db)):
    return svc.semanas(db, acc)


@router.get("/resumen", response_model=list[ResumenSucursal])
def resumen(
    semana: date | None = Query(None, description="Cualquier dia de la semana; se usa su lunes"),
    acc: svc.Acceso = Depends(_acceso),
    db: Session = Depends(get_db),
):
    return svc.resumen(db, _semana_o_actual(db, acc, semana), acc)


@router.get("/items", response_model=list[ItemOut])
def listar_items(
    semana: date | None = Query(None),
    sucursal: str | None = Query(None),
    acc: svc.Acceso = Depends(_acceso),
    db: Session = Depends(get_db),
):
    items = svc.items_de_semana(db, _semana_o_actual(db, acc, semana), acc, sucursal)
    evid = _evidencias_por_item(db, [i.id for i in items])
    return [_item_out(i, evid.get(i.id, [])) for i in items]


@router.patch("/items/{item_id}", response_model=ItemOut)
def actualizar_item(
    item_id: str,
    payload: ItemUpdate,
    acc: svc.Acceso = Depends(_acceso),
    db: Session = Depends(get_db),
):
    item = _item_visible(db, item_id, acc)
    cambios = payload.model_dump(exclude_unset=True)
    if "requiere_evidencia" in cambios:
        if not acc.es_admin:
            raise HTTPException(status_code=403, detail="Solo el administrador marca qué requiere evidencia")
        item.requiere_evidencia = bool(cambios["requiere_evidencia"])
    if "cantidad_contada" in cambios:
        anterior = item.cantidad_contada
        item.cantidad_contada = cambios["cantidad_contada"]
        if item.cantidad_contada is None:
            item.contado_por = item.contado_en = None
        else:
            item.contado_por = acc.email
            item.contado_en = datetime.now(timezone.utc)
        auditoria_service.registrar(
            db, accion="inventario_conteo", entidad="ic_item", entidad_id=item.id,
            usuario_email=acc.email, producto=item.producto, sucursal_id=item.sucursal_id,
            detalle=f"{anterior} -> {item.cantidad_contada} (sistema {item.cantidad_sistema})",
        )
    if "observacion" in cambios:
        item.observacion = (cambios["observacion"] or "").strip() or None
    db.commit()
    db.refresh(item)
    return _item_out(item, _evidencias_por_item(db, [item.id]).get(item.id, []))


@router.post("/items/{item_id}/evidencias", response_model=ItemOut, status_code=201)
async def subir_evidencia(
    item_id: str,
    archivo: UploadFile = File(...),
    acc: svc.Acceso = Depends(_acceso),
    db: Session = Depends(get_db),
):
    item = _item_visible(db, item_id, acc)
    tipo = (archivo.content_type or "").lower()
    if tipo not in svc.TIPOS_EVIDENCIA:
        raise HTTPException(status_code=400, detail="Solo se aceptan fotos (JPG, PNG, WEBP, HEIC) o PDF")
    contenido = await archivo.read()
    if not contenido:
        raise HTTPException(status_code=400, detail="El archivo está vacío")
    if len(contenido) > svc.MAX_EVIDENCIA_BYTES:
        raise HTTPException(status_code=400, detail="El archivo pesa más de 4 MB")
    db.add(IcEvidencia(
        item_id=item.id, nombre=archivo.filename or "evidencia", content_type=tipo,
        tamano=len(contenido), contenido=contenido, subido_por=acc.email,
    ))
    auditoria_service.registrar(
        db, accion="inventario_evidencia", entidad="ic_item", entidad_id=item.id,
        usuario_email=acc.email, producto=item.producto, sucursal_id=item.sucursal_id,
        detalle=archivo.filename,
    )
    db.commit()
    return _item_out(item, _evidencias_por_item(db, [item.id]).get(item.id, []))


@router.get("/evidencias/{evidencia_id}")
def ver_evidencia(
    evidencia_id: str, acc: svc.Acceso = Depends(_acceso), db: Session = Depends(get_db)
):
    ev = db.get(IcEvidencia, evidencia_id)
    if ev is None:
        raise HTTPException(status_code=404, detail="Evidencia no encontrada")
    _item_visible(db, ev.item_id, acc)
    return Response(
        content=ev.contenido, media_type=ev.content_type,
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.delete("/evidencias/{evidencia_id}", status_code=204)
def borrar_evidencia(
    evidencia_id: str, acc: svc.Acceso = Depends(_acceso), db: Session = Depends(get_db)
):
    ev = db.get(IcEvidencia, evidencia_id)
    if ev is None:
        raise HTTPException(status_code=404, detail="Evidencia no encontrada")
    _item_visible(db, ev.item_id, acc)
    if not acc.es_admin and ev.subido_por != acc.email:
        raise HTTPException(status_code=403, detail="Solo puedes borrar evidencias que subiste tú")
    db.delete(ev)
    db.commit()
    return Response(status_code=204)


@router.get("/plantilla")
def plantilla(acc: svc.Acceso = Depends(_admin)):
    wb = Workbook()
    ws = wb.active
    ws.title = "Inventario"
    ws.append(list(svc.COLUMNAS_PLANTILLA))
    ws.append(["20 BXO5W30AA", "ACEITE 5W30 LITRO FORD", "LINDEROS", "A", 12, 5000, "No"])
    for col, ancho in zip("ABCDEFG", (18, 40, 16, 12, 10, 12, 20)):
        ws.column_dimensions[col].width = ancho
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="plantilla_inventario_ciclico.xlsx"'},
    )


@router.post("/carga", response_model=CargaOut)
async def cargar(
    semana: date = Query(..., description="Cualquier dia de la semana; se usa su lunes"),
    archivo: UploadFile = File(...),
    acc: svc.Acceso = Depends(_admin),
    db: Session = Depends(get_db),
):
    contenido = await archivo.read()
    lectura = svc.leer_archivo(db, archivo.filename or "", contenido)
    if lectura.errores:
        # Nada se guarda si hay una sola fila mala: se corrige el Excel y se vuelve a subir.
        raise HTTPException(status_code=400, detail={"errores": lectura.errores[:200]})
    lunes = svc.lunes_de(semana)
    res = svc.cargar_semana(db, lunes, lectura.filas, acc.email)
    auditoria_service.registrar(
        db, accion="inventario_carga", entidad="ic_item", usuario_email=acc.email,
        detalle=f"semana {lunes.isoformat()}: {len(lectura.filas)} filas",
    )
    db.commit()
    return res


# --------------------------- permisos del modulo --------------------------- #
@router.get("/sucursales", response_model=list[str])
def sucursales(acc: svc.Acceso = Depends(_admin)):
    return list(svc.SUCURSALES_INVENTARIO)


@router.get("/roles", response_model=list[RolOut])
def listar_roles(acc: svc.Acceso = Depends(_admin), db: Session = Depends(get_db)):
    filas = db.scalars(select(IcRol).order_by(IcRol.rol, IcRol.email)).all()
    out = []
    for f in filas:
        u = db.get(Usuario, f.email)
        out.append(RolOut(
            email=f.email, rol=f.rol, sucursales=svc._lista_json(f.sucursales),
            nombre=u.nombre if u else None, tiene_usuario=u is not None,
        ))
    return out


@router.put("/roles/{email}", response_model=RolOut)
def guardar_rol(
    email: str, payload: RolIn, acc: svc.Acceso = Depends(_admin), db: Session = Depends(get_db)
):
    email = email.strip().lower()
    if "@" not in email:
        raise HTTPException(status_code=400, detail="Email no valido")
    validas = set(svc.SUCURSALES_INVENTARIO)
    sucs = sorted({s for s in (payload.sucursales or []) if s})
    if any(s not in validas for s in sucs):
        raise HTTPException(status_code=400, detail="Sucursal no valida")
    fila = db.get(IcRol, email) or IcRol(email=email)
    fila.rol = payload.rol
    fila.sucursales = json.dumps(sucs) if sucs and payload.rol == "bodega" else None
    db.add(fila)
    auditoria_service.registrar(
        db, accion="inventario_rol", entidad="ic_rol", entidad_id=email, usuario_email=acc.email,
        detalle=f"{payload.rol} {', '.join(sucs) or 'todas'}",
    )
    db.commit()
    u = db.get(Usuario, email)
    return RolOut(
        email=email, rol=fila.rol, sucursales=svc._lista_json(fila.sucursales),
        nombre=u.nombre if u else None, tiene_usuario=u is not None,
    )


@router.delete("/roles/{email}", status_code=204)
def quitar_rol(email: str, acc: svc.Acceso = Depends(_admin), db: Session = Depends(get_db)):
    fila = db.get(IcRol, email.strip().lower())
    if fila is not None:
        db.delete(fila)
        auditoria_service.registrar(
            db, accion="inventario_rol", entidad="ic_rol", entidad_id=fila.email,
            usuario_email=acc.email, detalle="quitado",
        )
        db.commit()
    return Response(status_code=204)
