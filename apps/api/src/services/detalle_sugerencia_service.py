"""Detalle de una sugerencia manual: que productos toca y cuanto aporta cada uno.

La pantalla de sugerencias listaba el titular ("mantener 2 u", "65 repuestos") sin
forma de ver que hay adentro. Con reglas que abarcan decenas de productos eso deja
al comprador sin poder responder la unica pregunta que importa: **esto esta
sirviendo o es peso muerto**.

Y no es una pregunta retorica. Al activar la regla InStock en produccion, de las
262 lineas que toca en las sucursales con taller, 97 no agregan ni una unidad: el
stock, el transito o el sugerido del modelo ya cubren el minimo. Sin este detalle
esas 97 se ven exactamente igual que las 165 que si aportan.

Cuatro tipos de sugerencia, un mismo formato de salida:

  `unica`       una sugerencia suelta, un producto.
  `lote`        una carga masiva; todas las filas comparten `lote_id`.
  `recurrente`  una regla periodica + las instancias que tiene vigentes hoy.
  `instock`     la regla del sistema (repuestos de pauta). Solo lectura.

El aporte se calcula distinto segun el tipo, y la diferencia es real:

- Las **manuales son aditivas**: sus unidades se suman al sugerido del modelo
  siempre. Ahi lo util no es "cuanto aporta" (siempre aporta todo) sino el
  contraste: el modelo ya pide 5 y esta sugerencia agrega 2.
- **InStock completa hasta un minimo**: descuenta stock, transito y lo que el
  modelo ya pide, asi que su aporte puede ser cero. Ahi "no aporta" es literal.
"""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import (
    AuditoriaLog,
    RepuestoInstock,
    SugerenciaManual,
    SugerenciaRecurrente,
)
from . import instock_service, recurrentes_service, sugerido_service

settings = get_settings()

TIPOS = ("unica", "lote", "recurrente", "instock")

# Estado de cada linea del detalle.
APORTA = "aporta"          # agrega unidades a la compra
SIN_EFECTO = "sin_efecto"  # esta activa pero no agrega nada (ya cubierto)
NO_APLICA = "no_aplica"    # la regla no rige en esa sucursal


def _fila_base(par: tuple[str, str], ctx: dict) -> dict:
    producto, sucursal = par
    return {
        "producto": producto,
        "sucursal_id": sucursal,
        "nombre_sucursal": ctx.get("nombre_sucursal") or sucursal,
        "descripcion": ctx.get("descripcion"),
        "proveedor": ctx.get("proveedor"),
        "clasificacion_abc": ctx.get("clasificacion_abc"),
        "costo_unitario": ctx.get("costo_unitario"),
        "stock_actual": ctx.get("stock_activo_suc"),
        "stock_transito": ctx.get("stock_en_transito_suc"),
    }


def _lineas_de_manuales(db: Session, filas: list[SugerenciaManual]) -> list[dict]:
    """Una linea por sugerencia manual, con lo que el modelo pide por su lado.

    Las manuales son aditivas, asi que `aporta` es siempre sus unidades. El dato
    que sirve para decidir si sigue teniendo sentido es `sugerido_modelo`: si el
    modelo ya pide de sobra, la manual quedo redundante aunque tecnicamente sume.
    """
    if not filas:
        return []
    pares = [(f.producto, f.sucursal_id) for f in filas]
    contexto = sugerido_service.contexto_de_pares(db, pares)
    # Lo que el modelo pide POR SU CUENTA (sin las manuales ya sumadas).
    del_modelo = {
        (s.producto, s.sucursal_id): float(s.total_sugerido_suc or 0)
        for s in sugerido_service._filas_de_pares(db, set(pares))
    }

    salida: list[dict] = []
    for f, ctx in zip(filas, contexto):
        par = (f.producto, f.sucursal_id)
        aporta = float(f.unidades or 0)
        modelo = del_modelo.get(par)
        costo = ctx.get("costo_unitario")
        linea = _fila_base(par, ctx)
        linea.update({
            "id": f.id,
            "sugerido_modelo": modelo,
            "aporta": aporta,
            "total_con_sugerencia": (modelo or 0) + aporta,
            "valor_aporte_clp": aporta * float(costo) if costo else None,
            "estado": APORTA if aporta > 0 else SIN_EFECTO,
            "motivo_sin_efecto": None if aporta > 0 else "la sugerencia quedo en cero unidades",
            # Contexto de la sugerencia misma.
            "motivo": f.motivo,
            "creado_por": f.creado_por,
            "creado_en": f.creado_en,
            "expira_en": f.expira_en,
            "dias_inventario": f.dias_inventario,
            "stock_objetivo": f.stock_objetivo,
            # Solo el modelo del BI ya cubre lo que se pidio a mano.
            "redundante": bool(modelo is not None and aporta and modelo >= aporta),
        })
        salida.append(linea)
    return salida


def _lineas_instock(db: Session) -> list[dict]:
    """Una linea por (repuesto de pauta x sucursal con taller), con el faltante real.

    Se recorre TODAS las sucursales con taller, no solo donde hay fila en el
    sugerido: el caso tipico de la regla es justamente el repuesto clase D con
    stock 0 que el modelo no pide.
    """
    catalogo = instock_service.catalogo(db)
    if not catalogo:
        return []
    productos = sorted(catalogo)
    sucursales = list(instock_service.SUCURSALES_INSTOCK)
    pares = [(p, s) for p in productos for s in sucursales]
    contexto = sugerido_service.contexto_de_pares(db, pares)
    del_modelo = {
        (s.producto, s.sucursal_id): float(s.total_sugerido_suc or 0)
        for s in sugerido_service._filas_de_pares(db, set(pares))
    }
    # Datos de la pauta (marca, modelos, operacion) para poder auditar el origen.
    pauta = {
        r.producto: r
        for r in db.scalars(
            select(RepuestoInstock).where(RepuestoInstock.activo.is_(True))
        ).all()
    }

    salida: list[dict] = []
    for par, ctx in zip(pares, contexto):
        producto, sucursal = par
        info = catalogo[producto]
        minimo = int(info.get("minimo") or instock_service.MINIMO_DEFECTO)
        modelo = del_modelo.get(par)
        stock = ctx.get("stock_activo_suc")
        transito = ctx.get("stock_en_transito_suc")
        faltan = instock_service.faltante(minimo, stock, transito, modelo)
        costo = ctx.get("costo_unitario")
        r = pauta.get(producto)

        if faltan > 0:
            estado, motivo = APORTA, None
        else:
            cubierto = (stock or 0) + (transito or 0) + (modelo or 0)
            partes = []
            if stock:
                partes.append(f"{stock:g} en bodega")
            if transito:
                partes.append(f"{transito:g} en tránsito")
            if modelo:
                partes.append(f"{modelo:g} que ya pide el modelo")
            estado = SIN_EFECTO
            motivo = (
                f"ya cubierto: {' + '.join(partes)} = {cubierto:g}, sobre el mínimo de {minimo}"
                if partes else f"el mínimo de {minimo} ya está cubierto"
            )

        linea = _fila_base(par, ctx)
        linea.update({
            "id": f"{producto}|{sucursal}",
            "sugerido_modelo": modelo,
            "aporta": float(faltan),
            "total_con_sugerencia": (modelo or 0) + faltan,
            "valor_aporte_clp": faltan * float(costo) if costo else None,
            "estado": estado,
            "motivo_sin_efecto": motivo,
            "minimo": minimo,
            "marca": r.marca if r else None,
            "modelos": r.modelos if r else info.get("modelos"),
            "operacion": r.operacion if r else None,
            "part_number": r.part_number if r else None,
            "redundante": False,
        })
        salida.append(linea)
    return salida


def _pautas_sin_codigo(db: Session) -> list[dict]:
    """Part numbers de la pauta que NO existen en el maestro, asi que no se marcan.

    Se recalcula al vuelo contra el CSV desplegado en vez de guardarse: si alguien
    recarga el catalogo y el codigo aparece, la lista se corrige sola. Que estos
    queden invisibles es como la regla entera estuvo semanas sin cargar.
    """
    try:
        from ..jobs import cargar_instock as job

        pautas = job._leer_csv(job.DEFAULT_PATH)
        indice = job._indice_de_codigos(db)
    except Exception:  # noqa: BLE001 - el detalle no se cae por no encontrar el CSV
        db.rollback()
        return []
    return [
        {
            "part_number": (f.get("part_number") or "").strip(),
            "marca": f.get("marca"),
            "modelos": f.get("modelos"),
            "operacion": f.get("operacion"),
        }
        for f in pautas
        if not indice.get(job._norm((f.get("part_number") or "").strip()))
    ]


def _totales(lineas: list[dict]) -> dict:
    aportan = [l for l in lineas if l["estado"] == APORTA]
    return {
        "n_lineas": len(lineas),
        "n_aportan": len(aportan),
        "n_sin_efecto": sum(1 for l in lineas if l["estado"] == SIN_EFECTO),
        "unidades": sum(l["aporta"] for l in aportan),
        "valor_clp": sum(l["valor_aporte_clp"] or 0 for l in aportan),
        "n_productos": len({l["producto"] for l in lineas}),
        "n_sucursales": len({l["sucursal_id"] for l in lineas}),
    }


def _historial(db: Session, entidad: str, entidad_id: str, limite: int = 20) -> list[dict]:
    """Ultimas acciones registradas sobre esta sugerencia.

    Sale de la auditoria, que ya guarda cada creacion, disparo y borrado. Responde
    lo que hoy no se puede saber mirando la tarjeta: si la regla se sigue
    ejecutando o quedo muerta hace meses.
    """
    try:
        filas = db.scalars(
            select(AuditoriaLog)
            .where(AuditoriaLog.entidad == entidad, AuditoriaLog.entidad_id == entidad_id)
            .order_by(AuditoriaLog.creado_en.desc())
            .limit(limite)
        ).all()
    except Exception:  # noqa: BLE001
        db.rollback()
        return []
    return [
        {
            "creado_en": a.creado_en,
            "accion": a.accion,
            "usuario_email": a.usuario_email,
            "detalle": a.detalle,
        }
        for a in filas
    ]


def detalle(db: Session, tipo: str, id_: str) -> dict:
    """Cabecera + lineas de una sugerencia, cualquiera sea su tipo."""
    if tipo not in TIPOS:
        raise HTTPException(status_code=400, detail=f"Tipo desconocido: {tipo}")

    if tipo == "instock":
        lineas = _lineas_instock(db)
        resumen = instock_service.resumen(db)
        return {
            "tipo": tipo,
            "id": "instock",
            "titulo": "InStock · repuestos de pauta",
            "subtitulo": (
                f"{resumen['n_repuestos']} repuestos de las pautas de mantención nunca "
                f"bajan de {resumen['minimo']} unidades en las sucursales con taller."
            ),
            "editable": False,
            "activa": resumen["activo"],
            "motivo": None,
            "creado_por": None,
            "creado_en": None,
            "totales": _totales(lineas),
            "lineas": lineas,
            "pautas_sin_codigo": _pautas_sin_codigo(db),
            "historial": _historial_instock(db),
        }

    if tipo == "unica":
        fila = db.get(SugerenciaManual, id_)
        if not fila or fila.archivada:
            raise HTTPException(status_code=404, detail="Esa sugerencia no existe.")
        lineas = _lineas_de_manuales(db, [fila])
        return {
            "tipo": tipo,
            "id": id_,
            "titulo": f"{fila.producto} · {fila.sucursal_id}",
            "subtitulo": fila.motivo or "Sugerencia manual",
            "editable": True,
            "activa": True,
            "motivo": fila.motivo,
            "creado_por": fila.creado_por,
            "creado_en": fila.creado_en,
            "expira_en": fila.expira_en,
            "totales": _totales(lineas),
            "lineas": lineas,
            "historial": _historial(db, "sugerencia_manual", id_),
        }

    if tipo == "lote":
        filas = list(db.scalars(
            select(SugerenciaManual).where(
                SugerenciaManual.lote_id == id_,
                SugerenciaManual.archivada.is_(False),
            ).order_by(SugerenciaManual.producto)
        ).all())
        if not filas:
            raise HTTPException(status_code=404, detail="Esa carga masiva no existe.")
        lineas = _lineas_de_manuales(db, filas)
        primera = filas[0]
        return {
            "tipo": tipo,
            "id": id_,
            "titulo": "Carga masiva",
            "subtitulo": primera.motivo or f"{len(filas)} sugerencias cargadas juntas",
            "editable": True,
            "activa": True,
            "motivo": primera.motivo,
            "creado_por": primera.creado_por,
            "creado_en": primera.creado_en,
            "expira_en": primera.expira_en,
            "totales": _totales(lineas),
            "lineas": lineas,
            "historial": _historial(db, "sugerencia_manual_lote", id_),
        }

    # recurrente
    rec = db.get(SugerenciaRecurrente, id_)
    if not rec:
        raise HTTPException(status_code=404, detail="Esa recurrencia no existe.")
    instancias = list(db.scalars(
        select(SugerenciaManual).where(
            SugerenciaManual.recurrente_id == id_,
            SugerenciaManual.archivada.is_(False),
        ).order_by(SugerenciaManual.producto)
    ).all())
    lineas = _lineas_de_manuales(db, instancias)
    return {
        "tipo": tipo,
        "id": id_,
        "titulo": recurrentes_service.resumen(rec),
        "subtitulo": (
            f"Se re-aplica cada {rec.cada_dias} días"
            + (f", hasta el {rec.fecha_fin:%d-%m-%Y}" if rec.fecha_fin else " (sin fecha de término)")
        ),
        "editable": True,
        "activa": rec.activa,
        "motivo": rec.motivo,
        "creado_por": rec.creado_por,
        "creado_en": rec.creado_en,
        "cada_dias": rec.cada_dias,
        "proxima_ejecucion": rec.proxima_ejecucion,
        "ultima_ejecucion": rec.ultima_ejecucion,
        "fecha_fin": rec.fecha_fin,
        "totales": _totales(lineas),
        "lineas": lineas,
        "historial": _historial(db, "sugerencia_recurrente", id_),
    }


def _historial_instock(db: Session) -> list[dict]:
    """La regla InStock no tiene id propio: su historial son las cargas de la lista."""
    try:
        filas = db.scalars(
            select(AuditoriaLog)
            .where(AuditoriaLog.accion == "instock_cargado")
            .order_by(AuditoriaLog.creado_en.desc())
            .limit(20)
        ).all()
    except Exception:  # noqa: BLE001
        db.rollback()
        return []
    return [
        {
            "creado_en": a.creado_en,
            "accion": a.accion,
            "usuario_email": a.usuario_email,
            "detalle": a.detalle,
        }
        for a in filas
    ]


def pausar(db: Session, rec_id: str, activa: bool, usuario_email: str | None = None) -> dict:
    """Suspende o reactiva una regla recurrente sin borrarla.

    Antes la unica accion era eliminar: para parar una regla un mes habia que
    borrarla y volver a crearla, perdiendo el historial y el motivo original.
    Pausada deja de dispararse, y sus instancias vigentes se archivan para que no
    sigan sumando a la compra.
    """
    rec = db.get(SugerenciaRecurrente, rec_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Esa recurrencia no existe.")
    rec.activa = activa
    if not activa:
        # Pausar y dejar el ajuste sumando seria peor que no pausar: el comprador
        # cree que la paro y la compra sigue igual.
        for fila in db.scalars(
            select(SugerenciaManual).where(
                SugerenciaManual.recurrente_id == rec_id,
                SugerenciaManual.archivada.is_(False),
            )
        ).all():
            fila.archivada = True
    db.commit()
    return {"id": rec_id, "activa": rec.activa}
