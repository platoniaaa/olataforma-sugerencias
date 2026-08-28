"""El tablero mensual de Abastecimiento.

Un tablero de veinticinco indicadores no lo abre nadie al tercer mes. Este trae
pocos, y el criterio para que uno entre es que **tenga dueño y gatille una
accion**: si nadie puede hacer nada con el numero, no va.

De donde sale cada bloque:

- **Servicio**: de `sugerido_snapshot`, la foto diaria. Es la unica fuente que
  sabe cuantos DIAS estuvo algo en cero; la tabla `sugerido` solo tiene el hoy.
- **Inventario**: de `inventario_service.salud()`, que ya calcula valor,
  inmovilizado, sobre-stock y cobertura. No se recalcula nada aca.
- **Obsolescencia**: cruza `reemplazo_ford` con el stock.
- **Salud del dato**: los huecos que, si nadie los mira, hacen que todo lo de
  arriba mienta sin avisar.
- **Ejecucion de la compra**: NO se calcula, y sale marcada como no disponible.
  `linea_pedida` esta vacia -la orden de compra no se registra en la
  plataforma-, asi que adherencia, lead time real y cumplimiento de proveedor no
  tienen de donde salir. Se devuelven igual, con el motivo, porque esconder el
  hueco haria creer que el tablero esta completo.

Sobre los dias de quiebre: se cuentan **dias-SKU**, no productos. Un repuesto en
cero durante 10 dias en dos sucursales suma 20. Es la medida que se puede sumar
por clase y comparar entre meses.
"""
from __future__ import annotations

import calendar
from datetime import date

from sqlalchemy import Integer, distinct, func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import (
    ProductoCatalogo,
    ReemplazoFord,
    RepuestoInstock,
    Sugerido,
    SugeridoSnapshot,
)
from ..schemas.sugerido import SugeridoFiltros
from . import instock_service, inventario_service

settings = get_settings()

# Clases en el orden en que se leen. D primero seria enterrar la que importa.
CLASES = ("A", "B", "C", "D")

# Por que "Ejecucion de la compra" viene vacia. Es texto de pantalla, no un log:
# lo lee la gerencia, asi que dice que falta y que haria falta para tenerlo.
MOTIVO_SIN_COMPRAS = (
    "La orden de compra no se registra en la plataforma: hoy el circuito termina "
    "cuando el comprador baja el Excel. Sin ese registro no hay con que comparar "
    "lo sugerido contra lo comprado, ni medir cuanto demoro en llegar."
)


def _rango(periodo: str) -> tuple[date, date]:
    """"2026-08" -> (2026-08-01, 2026-08-31)."""
    anio, mes = int(periodo[:4]), int(periodo[5:7])
    return date(anio, mes, 1), date(anio, mes, calendar.monthrange(anio, mes)[1])


def periodo_actual(db: Session) -> str:
    """El ultimo mes con snapshots. No `hoy`: si el job lleva dias caido, el
    tablero mostraria un mes en blanco en vez del ultimo que si tiene dato."""
    ultima = db.scalar(
        select(func.max(SugeridoSnapshot.fecha)).where(
            SugeridoSnapshot.tenant_id == settings.default_tenant_id)
    )
    ref = ultima or date.today()
    return f"{ref.year:04d}-{ref.month:02d}"


def _servicio(db: Session, desde: date, hasta: date) -> dict:
    """Dias-SKU en quiebre durante el mes, por clase y en los repuestos InStock."""
    tenant = settings.default_tenant_id
    base = (
        SugeridoSnapshot.tenant_id == tenant,
        SugeridoSnapshot.fecha >= desde,
        SugeridoSnapshot.fecha <= hasta,
    )

    # Dias con foto. Si el job fallo, el mes esta incompleto y hay que decirlo:
    # 40 dias de quiebre sobre 12 dias medidos no es lo mismo que sobre 31.
    dias_medidos = db.scalar(
        select(func.count(distinct(SugeridoSnapshot.fecha))).where(*base)
    ) or 0

    en_cero = (func.coalesce(SugeridoSnapshot.stock_activo_suc, 0.0) <= 0)

    por_clase = {c: 0 for c in CLASES}
    filas = db.execute(
        select(SugeridoSnapshot.clasificacion_abc, func.count())
        .where(*base, en_cero)
        .group_by(SugeridoSnapshot.clasificacion_abc)
    ).all()
    otras = 0
    for clase, n in filas:
        if clase in por_clase:
            por_clase[clase] = n
        else:
            otras += n

    # InStock: solo cuenta el quiebre donde la regla existe (producto Y sucursal
    # con taller). Contarlo en Talca inflaria un incumplimiento que no es tal.
    productos_instock = set(db.scalars(
        select(RepuestoInstock.producto).where(
            RepuestoInstock.tenant_id == tenant, RepuestoInstock.activo.is_(True))
    ).all())
    dias_instock = 0
    if productos_instock:
        dias_instock = db.scalar(
            select(func.count()).where(
                *base, en_cero,
                SugeridoSnapshot.producto.in_(productos_instock),
                SugeridoSnapshot.sucursal_id.in_(instock_service.SUCURSALES_INSTOCK),
            )
        ) or 0

    # Quiebre HOY: sin stock y con demanda viva. La foto con la que se arranca.
    quiebre_hoy = db.scalar(
        select(func.count()).select_from(Sugerido).where(
            Sugerido.tenant_id == tenant,
            func.coalesce(Sugerido.stock_activo_suc, 0.0) <= 0,
            func.coalesce(Sugerido.demanda_mensual, 0.0) > 0,
        )
    ) or 0

    dias_del_mes = (hasta - desde).days + 1
    return {
        "dias_medidos": dias_medidos,
        "dias_del_mes": dias_del_mes,
        "mes_completo": dias_medidos >= dias_del_mes,
        "dias_quiebre_por_clase": [
            {"clase": c, "dias": por_clase[c]} for c in CLASES
        ],
        "dias_quiebre_sin_clase": otras,
        "dias_quiebre_total": sum(por_clase.values()) + otras,
        "dias_quiebre_instock": dias_instock,
        "repuestos_instock": len(productos_instock),
        "quiebre_con_demanda_hoy": quiebre_hoy,
    }


def _obsolescencia(db: Session) -> dict:
    """Stock de codigos que FORD dio de baja: se deprecia mientras nadie lo mira.

    Solo cuentan los que tienen sucesor CONFIRMADO. Sin esa marca, FORD nombro un
    reemplazo que no se puede pedir, y llamarlo obsoleto seria acusar sin prueba.
    """
    tenant = settings.default_tenant_id
    dados_de_baja = set(db.scalars(
        select(ReemplazoFord.producto).where(
            ReemplazoFord.tenant_id == tenant,
            ReemplazoFord.sucesor_confirmado.is_(True),
            ReemplazoFord.reemplazado_por.is_not(None),
        )
    ).all())
    if not dados_de_baja:
        return {"valor_clp": 0, "n_codigos": 0, "top": []}

    filas = db.execute(
        select(
            Sugerido.producto,
            func.max(Sugerido.descripcion),
            func.sum(func.coalesce(Sugerido.stock_activo_suc, 0.0)),
            func.max(func.coalesce(Sugerido.costo_unitario, 0.0)),
        )
        .where(Sugerido.tenant_id == tenant, Sugerido.producto.in_(dados_de_baja))
        .group_by(Sugerido.producto)
    ).all()

    items = []
    for producto, desc, unidades, costo in filas:
        unidades = float(unidades or 0)
        if unidades <= 0:
            continue
        items.append({
            "producto": producto,
            "descripcion": desc,
            "unidades": round(unidades),
            "valor_clp": round(unidades * float(costo or 0)),
        })
    items.sort(key=lambda x: x["valor_clp"], reverse=True)
    return {
        "valor_clp": sum(i["valor_clp"] for i in items),
        "n_codigos": len(items),
        "top": items[:10],
    }


def _salud_del_dato(db: Session, servicio: dict) -> list[dict]:
    """Los huecos que hacen mentir al resto del tablero sin dar ningun error."""
    tenant = settings.default_tenant_id

    def _contar(*cond) -> int:
        return db.scalar(
            select(func.count()).select_from(Sugerido)
            .where(Sugerido.tenant_id == tenant, *cond)
        ) or 0

    con_sugerido = func.coalesce(Sugerido.total_sugerido_suc, 0.0) > 0
    con_stock = func.coalesce(Sugerido.stock_activo_suc, 0.0) > 0

    pide_total = _contar(con_sugerido)
    sin_proveedor = _contar(con_sugerido, Sugerido.proveedor.is_(None))
    sin_costo = _contar(con_stock, Sugerido.costo_unitario.is_(None))

    # Vigentes que FORD confirmo y que el maestro todavia no tiene: hasta que
    # Repuestos los cree, ese grupo no se puede comprar por el codigo bueno.
    vigentes = set(db.scalars(
        select(ReemplazoFord.reemplazado_por).where(
            ReemplazoFord.tenant_id == tenant,
            ReemplazoFord.sucesor_confirmado.is_(True),
            ReemplazoFord.reemplazado_por.is_not(None),
        )
    ).all())
    por_crear = 0
    if vigentes:
        existentes = set(db.scalars(
            select(ProductoCatalogo.producto).where(
                ProductoCatalogo.tenant_id == tenant,
                ProductoCatalogo.producto.in_(vigentes),
            )
        ).all())
        por_crear = len(vigentes - existentes)

    return [
        {"que": "Filas con sugerido y sin proveedor",
         "valor": sin_proveedor, "de": pide_total,
         "alerta": pide_total > 0 and sin_proveedor / pide_total > 0.03,
         "detalle": "Caen al carro 'Sin proveedor asignado' y nadie las compra."},
        {"que": "Codigos vigentes de FORD por crear en el maestro",
         "valor": por_crear, "de": None, "alerta": por_crear > 0,
         "detalle": "Hasta que existan, el grupo no se puede pedir por el codigo bueno."},
        {"que": "Filas con stock y sin costo unitario",
         "valor": sin_costo, "de": None, "alerta": sin_costo > 0,
         "detalle": "Todo lo valorizado en pesos las deja fuera."},
        {"que": "Dias del mes con foto guardada",
         "valor": servicio["dias_medidos"], "de": servicio["dias_del_mes"],
         "alerta": not servicio["mes_completo"],
         "detalle": "Los dias de quiebre se cuentan solo sobre los dias medidos."},
    ]


def mensual(db: Session, periodo: str | None = None) -> dict:
    """El tablero completo de un mes. `periodo` en formato "YYYY-MM"."""
    periodo = periodo or periodo_actual(db)
    desde, hasta = _rango(periodo)

    servicio = _servicio(db, desde, hasta)
    # `salud` mira el inventario completo, no solo lo que se sugiere comprar: el
    # inmovilizado esta justamente en lo que el sistema NO pide.
    inventario = inventario_service.salud(db, SugeridoFiltros())

    return {
        "periodo": periodo,
        "servicio": servicio,
        "inventario": inventario,
        "obsolescencia": _obsolescencia(db),
        "salud_del_dato": _salud_del_dato(db, servicio),
        "ejecucion_compra": {
            "disponible": False,
            "motivo": MOTIVO_SIN_COMPRAS,
            "indicadores": [
                "Adherencia al sugerido",
                "Lead time real vs. el del calculo",
                "Cumplimiento por proveedor",
                "Compras fuera del sugerido",
            ],
        },
    }
