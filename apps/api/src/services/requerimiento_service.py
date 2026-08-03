"""Requerimiento de sucursal: pegar una lista de codigos y decidir rapido.

El vendedor de una sucursal le manda al comprador una lista de repuestos con sus
cantidades. Antes de la plataforma el comprador la pegaba en un Excel que le
llenaba solo el contexto (stock, frecuencia de venta, reemplazo) y le armaba el
archivo para subir al portal del proveedor. Esto reemplaza ese Excel.

La idea de diseno es POKA-YOKE: que el error no pueda ocurrir, en vez de avisarlo.

- Se pega como venga. Tabulacion, coma, punto y coma o espacios; con encabezado o
  sin el; con cantidad o sin ella. No hay formato que aprenderse.
- El codigo de Curifor trae un rubro con espacio ("70 2723982") y ademas hay
  codigos que son puros numeros, asi que "codigo espacio numero" es ambiguo. En
  vez de adivinar con una regla, se pregunta al catalogo cual de las dos lecturas
  existe de verdad.
- La sucursal se elige UNA vez, no por linea.
- Lo que no se puede comprar no se puede seleccionar.

Estados de una linea:
  `en_sugerido`   el modelo ya lo pide en esa sucursal: hay frecuencia y clase.
  `sin_venta_local` existe, pero nunca se vendio en esa sucursal en 12 meses. No
                  es un error: es la respuesta. Si se vende en otra, se muestra.
  `no_existe`     no esta en ninguna parte. Error de tipeo.
"""
from __future__ import annotations

import re
from typing import Any

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import (
    DimSucursal,
    ProductoCatalogo,
    Requerimiento,
    RequerimientoLinea,
    StockUnificado,
    Sugerido,
)
from . import sugerido_service

settings = get_settings()

# Separadores explicitos: cuando aparece uno, la lectura es inequivoca.
_SEPARADORES = re.compile(r"[\t;,|]")
# Cantidad: entero o decimal, con separador de miles opcional.
_NUMERO = re.compile(r"^\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?$|^\d+(?:[.,]\d+)?$")

# Palabras que delatan una fila de encabezado pegada sin querer.
_ENCABEZADOS = {"codigo", "código", "producto", "sku", "cantidad", "cant", "cant.",
                "descripcion", "descripción", "item", "linea", "línea"}


def _a_numero(s: str) -> float | None:
    s = s.strip()
    if not _NUMERO.match(s):
        return None
    # "1.234" son mil doscientos treinta y cuatro; "1,5" es uno coma cinco.
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif s.count(".") == 1 and len(s.split(".")[1]) == 3:
        s = s.replace(".", "")
    elif s.count(",") == 1 and len(s.split(",")[1]) == 3:
        s = s.replace(",", "")
    else:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _candidatos(linea: str) -> list[tuple[str, float | None]]:
    """Lecturas posibles de una linea, de la mas confiable a la menos.

    Con separador explicito hay una sola. Con espacios hay dos: que el ultimo
    token sea la cantidad, o que sea parte del codigo ("70 2723982").
    """
    linea = linea.strip()
    if not linea:
        return []
    if _SEPARADORES.search(linea):
        partes = [p.strip() for p in _SEPARADORES.split(linea) if p.strip()]
        if not partes:
            return []
        if len(partes) == 1:
            return [(partes[0], None)]
        # El codigo es la primera parte; la cantidad, la primera que sea numero.
        cantidad = next((_a_numero(p) for p in partes[1:] if _a_numero(p) is not None), None)
        return [(partes[0], cantidad)]

    tokens = linea.split()
    if len(tokens) == 1:
        return [(tokens[0], None)]
    ultimo = _a_numero(tokens[-1])
    lecturas: list[tuple[str, float | None]] = []
    if ultimo is not None:
        # Lectura A: el ultimo token es la cantidad.
        lecturas.append((" ".join(tokens[:-1]), ultimo))
    # Lectura B: toda la linea es el codigo (caso "70 2723982").
    lecturas.append((linea, None))
    return lecturas


def parsear(db: Session, texto: str) -> list[dict]:
    """Texto pegado -> lineas (producto, cantidad), resolviendo la ambiguedad.

    Se hace en dos pasadas: primero se juntan TODAS las lecturas posibles y se
    pregunta al catalogo cuales existen, y despues se elige. Asi el desempate lo
    decide el dato y no una regla que va a fallar con el proximo codigo raro.
    """
    lineas_texto = [l for l in (texto or "").splitlines() if l.strip()]
    por_linea = [_candidatos(l) for l in lineas_texto]

    posibles = {c for cands in por_linea for c, _ in cands}
    existentes = _cuales_existen(db, posibles)

    salida: list[dict] = []
    for texto_linea, cands in zip(lineas_texto, por_linea):
        if not cands:
            continue
        if texto_linea.strip().lower().split()[0] in _ENCABEZADOS and not any(
            c in existentes for c, _ in cands
        ):
            continue  # fila de encabezado pegada sin querer
        elegido = next((c for c in cands if c[0] in existentes), cands[0])
        salida.append({
            "producto": elegido[0].strip(),
            "cantidad": elegido[1],
            "texto_original": texto_linea.strip(),
        })
    return salida


def _cuales_existen(db: Session, codigos: set[str]) -> set[str]:
    """De una lista de codigos candidatos, cuales existen en Curifor."""
    codigos = {c for c in codigos if c}
    if not codigos:
        return set()
    encontrados: set[str] = set()
    for modelo, col in ((Sugerido, Sugerido.producto), (ProductoCatalogo, ProductoCatalogo.producto)):
        try:
            encontrados |= {
                p for (p,) in db.execute(select(col).where(col.in_(codigos)).distinct()).all()
            }
        except Exception:  # noqa: BLE001 - una tabla ausente no puede voltear el parseo
            db.rollback()
    return encontrados


def _frecuencia_otras_sucursales(db: Session, productos: set[str], sucursal_id: str) -> dict:
    """Para los que no se venden en la sucursal pedida: donde SI se venden.

    Devuelve, por producto, la sucursal con mas meses de venta en 12m. Es lo que
    convierte un "no hay dato" en algo accionable: "aca nunca, en Curico 7 de 12".
    """
    if not productos:
        return {}
    filas = db.execute(
        select(
            Sugerido.producto, Sugerido.sucursal_id, Sugerido.nombre_sucursal,
            Sugerido.meses_con_venta_12m, Sugerido.clasificacion_abc,
        ).where(
            Sugerido.producto.in_(productos),
            Sugerido.sucursal_id != sucursal_id,
            Sugerido.meses_con_venta_12m.isnot(None),
            Sugerido.meses_con_venta_12m > 0,
        )
    ).all()
    mejor: dict[str, dict] = {}
    for prod, suc, nombre, m12, abc in filas:
        actual = mejor.get(prod)
        if actual is None or (m12 or 0) > actual["meses_con_venta_12m"]:
            mejor[prod] = {
                "sucursal_id": suc,
                "nombre_sucursal": nombre or suc,
                "meses_con_venta_12m": m12 or 0,
                "clasificacion_abc": abc,
            }
    return mejor


def _stock_nacional(db: Session, productos: set[str]) -> dict[str, float]:
    """Stock total del producto en TODA la empresa (todas las bodegas)."""
    if not productos:
        return {}
    try:
        filas = db.execute(
            select(StockUnificado.producto, func.sum(StockUnificado.stock))
            .where(StockUnificado.producto.in_(productos))
            .group_by(StockUnificado.producto)
        ).all()
        return {p: float(t or 0) for p, t in filas}
    except Exception:  # noqa: BLE001 - tabla ausente en un deploy nuevo
        db.rollback()
        return {}


def analizar(db: Session, sucursal_id: str, lineas: list[dict]) -> dict:
    """Enriquece cada linea con lo necesario para decidir comprar o no."""
    if not lineas:
        return {"lineas": [], "resumen": {"total": 0, "en_sugerido": 0,
                                          "sin_venta_local": 0, "no_existe": 0,
                                          "duplicados": 0}}

    productos = [str(l.get("producto") or "").strip() for l in lineas]
    pares = [(p, sucursal_id) for p in productos]
    contexto = sugerido_service.contexto_de_pares(db, pares)

    # Fila propia del sugerido (la que trae frecuencia y clase de ESTA sucursal).
    propias = {
        (s.producto, s.sucursal_id): s
        for s in sugerido_service._filas_de_pares(db, set(pares))
    }
    existen = _cuales_existen(db, set(productos))
    sin_local = {p for p in productos if (p, sucursal_id) not in propias and p in existen}
    otras = _frecuencia_otras_sucursales(db, sin_local, sucursal_id)
    nacional = _stock_nacional(db, set(productos))

    vistos: dict[str, int] = {}
    salida: list[dict] = []
    for i, (linea, ctx) in enumerate(zip(lineas, contexto)):
        prod = productos[i]
        propia = propias.get((prod, sucursal_id))
        if prod not in existen:
            estado = "no_existe"
        elif propia is not None:
            estado = "en_sugerido"
        else:
            estado = "sin_venta_local"

        vistos[prod] = vistos.get(prod, 0) + 1
        fila: dict[str, Any] = {
            "producto": prod,
            "texto_original": linea.get("texto_original"),
            "cantidad": linea.get("cantidad"),
            "estado": estado,
            "duplicado": vistos[prod] > 1,
            "descripcion": ctx.get("descripcion"),
            "proveedor": ctx.get("proveedor"),
            "costo_unitario": ctx.get("costo_unitario"),
            "reemplazos": ctx.get("reemplazos"),
            "nombre_sucursal": ctx.get("nombre_sucursal"),
            # Stock: el de la sucursal sale del mismo camino que la grilla.
            "stock_sucursal": ctx.get("stock_activo_suc"),
            "stock_nacional": nacional.get(prod),
            # Frecuencia de ESTA sucursal (solo si el modelo la tiene).
            "meses_con_venta_3m": propia.meses_con_venta_3m if propia else None,
            "meses_con_venta_6m": propia.meses_con_venta_6m if propia else None,
            "meses_con_venta_12m": propia.meses_con_venta_12m if propia else None,
            "clasificacion_abc": (propia.clasificacion_abc if propia
                                  else ctx.get("clasificacion_abc")),
            "stock_cd": propia.stock_en_cd if propia else None,
            "total_sugerido_suc": propia.total_sugerido_suc if propia else None,
            # Cuando no se vende aca, donde SI se vende.
            "frecuencia_otra_sucursal": otras.get(prod),
        }
        salida.append(fila)

    return {
        "lineas": salida,
        "resumen": {
            "total": len(salida),
            "en_sugerido": sum(1 for f in salida if f["estado"] == "en_sugerido"),
            "sin_venta_local": sum(1 for f in salida if f["estado"] == "sin_venta_local"),
            "no_existe": sum(1 for f in salida if f["estado"] == "no_existe"),
            "duplicados": sum(1 for f in salida if f["duplicado"]),
        },
    }


# --------------------------------------------------------------------------- #
# Carro del vendedor y bandeja del comprador.
#
# El vendedor de sucursal no manda un correo: arma un carro contra la lista de
# precios de Curifor y lo envia. El comprador lo recibe en su bandeja con el
# MISMO analisis de la pantalla de pegar lista, decide, y si quiere baja el
# archivo del portal. La foto de precio/descripcion se explica en
# `models/requerimiento.py`.
# --------------------------------------------------------------------------- #
def buscar_productos(
    db: Session, q: str, sucursal_id: str | None = None, limit: int = 25
) -> list[dict]:
    """Buscador del carro: solo devuelve lo que existe en la lista de precios.

    Es la pieza poka-yoke central de la vista del vendedor. Al no poder escribir
    un codigo a mano, el codigo inventado o mal tipeado deja de ser posible y el
    comprador nunca recibe una linea que no se puede comprar.

    Se busca por codigo o por descripcion, y el codigo calza tambien sin el rubro
    ("SZ6Z3B437B" encuentra "19 SZ6Z3B437B"), que es como lo tiene el vendedor a
    mano cuando lo saca de la caja o del portal.
    """
    q = (q or "").strip()
    if len(q) < 2:  # con una letra la lista no dice nada y pesa
        return []
    like = f"%{q}%"
    filas = list(
        db.scalars(
            select(ProductoCatalogo)
            .where(
                ProductoCatalogo.tenant_id == settings.default_tenant_id,
                or_(ProductoCatalogo.producto.ilike(like), ProductoCatalogo.glosa.ilike(like)),
            )
            # El que empieza con lo tecleado primero: si el vendedor escribe el
            # codigo completo, su producto no puede quedar en la pagina 2.
            .order_by(ProductoCatalogo.producto.ilike(f"{q}%").desc(), ProductoCatalogo.producto)
            .limit(limit)
        ).all()
    )
    if not filas:
        return []

    productos = [p.producto for p in filas]
    nacional = _stock_nacional(db, set(productos))
    local: dict[str, float] = {}
    if sucursal_id:
        try:
            local = {
                p: float(t or 0)
                for p, t in db.execute(
                    select(StockUnificado.producto, func.sum(StockUnificado.stock))
                    .where(
                        StockUnificado.producto.in_(productos),
                        StockUnificado.sucursal_id == sucursal_id,
                    )
                    .group_by(StockUnificado.producto)
                ).all()
            }
        except Exception:  # noqa: BLE001 - tabla ausente: se muestra sin stock local
            db.rollback()
    return [
        {
            "producto": p.producto,
            "descripcion": p.glosa,
            "precio": p.precio,
            "stock_sucursal": local.get(p.producto),
            "stock_nacional": nacional.get(p.producto, p.stock_total),
            "familia": p.familia,
        }
        for p in filas
    ]


def desde_lista_pegada(
    db: Session, lineas: list[dict], sucursal_id: str | None = None
) -> list[dict]:
    """Lineas pegadas -> filas del carro, resueltas contra la lista de precios.

    El vendedor casi siempre YA tiene la lista (un Excel, un WhatsApp). Obligarlo
    a buscar producto por producto seria mas trabajo del que tenia con el correo,
    y volveria al correo. Lo que no existe vuelve igual con `encontrado=False`:
    tiene que VERLO, no que desaparezca en silencio.
    """
    if not lineas:
        return []
    productos = [str(l.get("producto") or "").strip() for l in lineas]
    catalogo = {
        p.producto: p
        for p in db.scalars(
            select(ProductoCatalogo).where(
                ProductoCatalogo.tenant_id == settings.default_tenant_id,
                ProductoCatalogo.producto.in_([p for p in productos if p]),
            )
        ).all()
    }
    nacional = _stock_nacional(db, set(catalogo))
    local: dict[str, float] = {}
    if sucursal_id and catalogo:
        try:
            local = {
                p: float(t or 0)
                for p, t in db.execute(
                    select(StockUnificado.producto, func.sum(StockUnificado.stock))
                    .where(
                        StockUnificado.producto.in_(list(catalogo)),
                        StockUnificado.sucursal_id == sucursal_id,
                    )
                    .group_by(StockUnificado.producto)
                ).all()
            }
        except Exception:  # noqa: BLE001 - tabla ausente: se muestra sin stock local
            db.rollback()

    salida: list[dict] = []
    for linea, prod in zip(lineas, productos):
        cat = catalogo.get(prod)
        salida.append({
            "producto": prod,
            "descripcion": cat.glosa if cat else None,
            "precio": cat.precio if cat else None,
            "stock_sucursal": local.get(prod),
            "stock_nacional": nacional.get(prod, cat.stock_total if cat else None),
            "familia": cat.familia if cat else None,
            "cantidad": linea.get("cantidad"),
            "encontrado": cat is not None,
            "texto_original": linea.get("texto_original"),
        })
    return salida


def _nombre_sucursal(db: Session, sucursal_id: str) -> str | None:
    try:
        return db.scalar(
            select(DimSucursal.nombre).where(DimSucursal.sucursal_id == sucursal_id)
        )
    except Exception:  # noqa: BLE001 - sin la dimension se muestra el id
        db.rollback()
        return None


def crear(
    db: Session,
    *,
    sucursal_id: str,
    email: str,
    nombre: str | None,
    lineas: list[dict],
    nota: str | None = None,
) -> Requerimiento:
    """Guarda el carro del vendedor como un requerimiento enviado.

    Valida en el servidor lo mismo que impide la pantalla. La pantalla evita el
    error; esta validacion evita que el error entre por otro lado (una pestana
    vieja, un reintento, alguien llamando la API directo).
    """
    if not lineas:
        raise HTTPException(status_code=400, detail="El requerimiento no tiene productos.")

    # Repetidos: se suman en vez de rechazarse. Pedir dos veces el mismo codigo no
    # es un error del vendedor, es como quedo el carro; lo que el comprador
    # necesita es UNA linea con el total.
    consolidado: dict[str, dict] = {}
    for linea in lineas:
        prod = str(linea.get("producto") or "").strip()
        if not prod:
            continue
        cant = float(linea.get("cantidad") or 0)
        if cant <= 0:
            raise HTTPException(
                status_code=400, detail=f"La cantidad de {prod} tiene que ser mayor que cero."
            )
        previo = consolidado.get(prod)
        if previo:
            previo["cantidad"] += cant
            # Se conservan los dos comentarios: el comprador tiene que leer ambos.
            comentarios = [c for c in (previo.get("comentario"), linea.get("comentario")) if c]
            previo["comentario"] = " / ".join(comentarios) or None
        else:
            consolidado[prod] = {
                "cantidad": cant,
                "comentario": (linea.get("comentario") or "").strip() or None,
            }

    # Foto de la lista de precios (y control de que el codigo existe de verdad).
    catalogo = {
        p.producto: p
        for p in db.scalars(
            select(ProductoCatalogo).where(
                ProductoCatalogo.tenant_id == settings.default_tenant_id,
                ProductoCatalogo.producto.in_(list(consolidado)),
            )
        ).all()
    }
    faltantes = [p for p in consolidado if p not in catalogo]
    if faltantes:
        raise HTTPException(
            status_code=400,
            detail="Estos códigos no están en la lista de precios: " + ", ".join(faltantes[:10]),
        )

    req = Requerimiento(
        tenant_id=settings.default_tenant_id,
        sucursal_id=sucursal_id,
        nombre_sucursal=_nombre_sucursal(db, sucursal_id) or sucursal_id,
        creado_por=email,
        creado_por_nombre=nombre,
        estado="enviado",
        nota=(nota or "").strip() or None,
    )
    for prod, datos in consolidado.items():
        cat = catalogo[prod]
        req.lineas.append(
            RequerimientoLinea(
                producto=prod,
                descripcion=cat.glosa,
                precio_lista=cat.precio,
                cantidad_pedida=datos["cantidad"],
                comentario=datos["comentario"],
            )
        )
    db.add(req)
    db.commit()
    db.refresh(req)
    return req


def _total(lineas: list[RequerimientoLinea]) -> float:
    """Valorizado del requerimiento a la lista de precios que vio el vendedor."""
    total = 0.0
    for l in lineas:
        cantidad = l.cantidad_aprobada if l.cantidad_aprobada is not None else l.cantidad_pedida
        total += float(cantidad or 0) * float(l.precio_lista or 0)
    return total


def _cabecera(req: Requerimiento) -> dict:
    return {
        "id": req.id,
        "sucursal_id": req.sucursal_id,
        "nombre_sucursal": req.nombre_sucursal or req.sucursal_id,
        "creado_por": req.creado_por,
        "creado_por_nombre": req.creado_por_nombre,
        "creado_en": req.creado_en,
        "estado": req.estado,
        "nota": req.nota,
        "revisado_por": req.revisado_por,
        "revisado_en": req.revisado_en,
        "nota_comprador": req.nota_comprador,
        "n_lineas": len(req.lineas),
        "total_estimado": _total(req.lineas),
    }


def _linea_dict(l: RequerimientoLinea) -> dict:
    return {
        "id": l.id,
        "producto": l.producto,
        "descripcion": l.descripcion,
        "precio_lista": l.precio_lista,
        "cantidad_pedida": l.cantidad_pedida,
        "cantidad_aprobada": l.cantidad_aprobada,
        "comentario": l.comentario,
        "analisis": None,
    }


def listar_bandeja(
    db: Session,
    *,
    email: str | None = None,
    estados: list[str] | None = None,
    sucursales: list[str] | None = None,
    limit: int = 300,
) -> dict:
    """Bandeja: la del comprador (todas) o la del vendedor (solo las suyas).

    `email` acota a lo que creo esa persona; `sucursales` a las de su usuario. El
    comprador no manda ninguno de los dos y ve todo.
    """
    stmt = select(Requerimiento).where(Requerimiento.tenant_id == settings.default_tenant_id)
    if email:
        stmt = stmt.where(Requerimiento.creado_por == email)
    if sucursales:
        stmt = stmt.where(Requerimiento.sucursal_id.in_(sucursales))
    if estados:
        stmt = stmt.where(Requerimiento.estado.in_(estados))
    filas = list(db.scalars(stmt.order_by(Requerimiento.creado_en.desc()).limit(limit)).all())
    return {
        "items": [_cabecera(r) for r in filas],
        "total": len(filas),
        "sin_revisar": sum(1 for r in filas if r.estado == "enviado"),
    }


def obtener(db: Session, req_id: int) -> Requerimiento:
    req = db.get(Requerimiento, req_id)
    if not req or req.tenant_id != settings.default_tenant_id:
        raise HTTPException(status_code=404, detail="Ese requerimiento no existe.")
    return req


def detalle(db: Session, req_id: int, *, con_analisis: bool = False) -> dict:
    """Un requerimiento completo. Con `con_analisis` trae el contexto del comprador.

    El analisis es exactamente el mismo que da la pantalla de pegar lista: no hay
    dos formas de mirar un requerimiento segun por donde entro.
    """
    req = obtener(db, req_id)
    salida = _cabecera(req)
    lineas = [_linea_dict(l) for l in req.lineas]
    if con_analisis and lineas:
        contexto = analizar(
            db,
            req.sucursal_id,
            [{"producto": l["producto"], "cantidad": l["cantidad_pedida"]} for l in lineas],
        )
        for linea, ctx in zip(lineas, contexto["lineas"]):
            linea["analisis"] = ctx
    salida["lineas"] = lineas
    return salida


def marcar_en_revision(db: Session, req: Requerimiento, email: str) -> None:
    """Acuse de recibo: el comprador lo abrio.

    Le sirve al vendedor, que hoy no tiene forma de saber si su correo se leyo.
    Solo avanza desde `enviado`; nunca retrocede un requerimiento ya cerrado.
    """
    if req.estado != "enviado":
        return
    req.estado = "en_revision"
    req.revisado_por = email
    req.revisado_en = datetime.now(timezone.utc)
    db.commit()


def actualizar(
    db: Session,
    req_id: int,
    *,
    email: str,
    estado: str | None = None,
    nota_comprador: str | None = None,
    cantidades: list[dict] | None = None,
) -> dict:
    """Lo que decide el comprador: cantidades, estado y su respuesta al vendedor."""
    from ..models.requerimiento import CERRADOS, ESTADOS

    req = obtener(db, req_id)
    if req.estado in CERRADOS:
        raise HTTPException(
            status_code=409,
            detail=f"El requerimiento {req.id} ya está {req.estado} y no se puede modificar.",
        )
    if estado and estado not in ESTADOS:
        raise HTTPException(status_code=400, detail=f"Estado desconocido: {estado}")
    # Un rechazo sin motivo obliga al vendedor a preguntar por correo, que es
    # justo lo que este modulo viene a sacar.
    if estado == "rechazado" and not (nota_comprador or req.nota_comprador or "").strip():
        raise HTTPException(
            status_code=400, detail="Para rechazar hay que decir por qué (nota al vendedor)."
        )

    if cantidades:
        por_id = {l.id: l for l in req.lineas}
        for c in cantidades:
            linea = por_id.get(int(c.get("linea_id") or 0))
            if linea is None:
                continue
            cantidad = c.get("cantidad")
            if cantidad is None:
                linea.cantidad_aprobada = None
                continue
            cantidad = float(cantidad)
            if cantidad < 0:
                raise HTTPException(
                    status_code=400, detail=f"La cantidad de {linea.producto} no puede ser negativa."
                )
            linea.cantidad_aprobada = cantidad

    if nota_comprador is not None:
        req.nota_comprador = nota_comprador.strip() or None
    if estado:
        req.estado = estado
    req.revisado_por = email
    req.revisado_en = datetime.now(timezone.utc)
    db.commit()
    db.refresh(req)
    return detalle(db, req.id, con_analisis=False)
