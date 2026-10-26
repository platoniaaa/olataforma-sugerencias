"""Canal Digital: reune lo que ya tiene la plataforma y corre el nucleo (`canal_digital.corrida`).

Fuentes (todas ya existen en la plataforma, ninguna se modifica):
  ventas del canal      canal_digital_venta (por producto, semana y periodo del documento)
  padres (equivalentes) sugerido.reemplazos: el grupo que publica el motor, master primero
  stock                 stock_unificado por NOMBRE de bodega (BODEGA ML suma; ML-FULL y CD, aparte)
  costo y descripcion   precio_producto
  primera venta         venta_historica (desde 2018, por mes)
  plazo de entrega      lead_time_proveedor_sucursal (fila global del proveedor) + 1 dia de gestion
  transito              stock_transito, solo con destino a la bodega del canal
"""
from __future__ import annotations

import datetime as dt
import re
from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..canal_digital.clasificacion import ParametrosClasificacion
from ..canal_digital.corrida import Corrida, DatosProducto, correr
from ..canal_digital.politica import BODEGA_CANAL_DIGITAL
from ..canal_digital.reposicion import ParametrosReposicion
from ..canal_digital.ventas_semanales import normalizar_codigo
from ..models import (
    CanalDigitalVenta, LeadTimeProveedorSucursal, PrecioProducto, ProveedorProducto, StockTransito,
    StockUnificado, Sugerido, VentaHistorica,
)
from .canal_digital_service import _tenant, asegurar_bodega, leer_politica

PLAZO_RESPALDO_DIAS = 3.0
N_SEMANAS = 52
_LOTE_IN = 500


def _clave(nombre: str | None) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(nombre or "").upper())


def _lista(txt: str | None) -> list[str]:
    return [x.strip() for x in str(txt or "").split(",") if x.strip()]


def _trozos(items, n=_LOTE_IN):
    items = list(items)
    for i in range(0, len(items), n):
        yield items[i : i + n]


def mapa_padres(db: Session) -> tuple[dict[str, str], int]:
    """codigo normalizado -> padre (el master del grupo que publica el motor en `sugerido.reemplazos`).

    Un codigo sin grupo es su propio padre y no aparece. Devuelve tambien cuantos codigos figuran en
    dos grupos a la vez (se queda con el master menor, de forma determinista).
    """
    filas = db.execute(
        select(Sugerido.producto, Sugerido.reemplazos)
        .where(Sugerido.tenant_id == _tenant(), Sugerido.reemplazos.is_not(None))
        .distinct()
    ).all()
    por_master: dict[str, set[str]] = defaultdict(set)
    for master, reem in filas:
        m = normalizar_codigo(master)
        if not m:
            continue
        for x in _lista(reem):
            c = normalizar_codigo(x)
            if c and c != m:
                por_master[m].add(c)
    mapa: dict[str, str] = {}
    conflictos = 0
    for m in sorted(por_master):
        for c in sorted(por_master[m]):
            if c in mapa and mapa[c] != m:
                conflictos += 1
                continue
            mapa[c] = m
    for _ in range(5):  # cadenas A -> B -> C: se cierran en el ultimo
        cambio = False
        for c, p in list(mapa.items()):
            if p in mapa and mapa[p] != p:
                mapa[c] = mapa[p]
                cambio = True
        if not cambio:
            break
    return mapa, conflictos


def ventana(hoy: dt.date, n_meses: int = 12) -> dict:
    """Los n meses cerrados antes de `hoy` y las 52 semanas completas (lunes a domingo) mas recientes."""
    primero_mes = hoy.replace(day=1)
    periodos = []
    y, m = primero_mes.year, primero_mes.month
    for _ in range(n_meses):
        m -= 1
        if m == 0:
            y, m = y - 1, 12
        periodos.append(f"{y}{m:02d}")
    periodos.reverse()
    lunes_actual = hoy - dt.timedelta(days=hoy.weekday())
    ultimo_lunes = lunes_actual - dt.timedelta(days=7)  # ultima semana COMPLETA
    semanas = [(ultimo_lunes - dt.timedelta(days=7 * k)).isoformat() for k in range(N_SEMANAS - 1, -1, -1)]
    return {"periodos": periodos, "semanas": semanas, "fecha_referencia": primero_mes}


def reunir_datos(db: Session, bodega: str, hoy: dt.date) -> tuple[list[DatosProducto], dict]:
    tenant = _tenant()
    cfg = asegurar_bodega(db, bodega)
    v = ventana(hoy, cfg.ventana_meses)
    periodos, semanas = v["periodos"], v["semanas"]
    idx_p = {p: i for i, p in enumerate(periodos)}
    idx_s = {s: i for i, s in enumerate(semanas)}
    aviso: dict = {
        "periodos": [periodos[0], periodos[-1]], "semanas": [semanas[0], semanas[-1]],
        "fecha_referencia": v["fecha_referencia"].isoformat(),
    }

    # Filas con periodo del documento desde el inicio de la ventana mensual o de la semanal
    # (la semanal puede empezar antes: una devolucion cuenta en la semana de la venta que anula).
    primera_semana = dt.date.fromisoformat(semanas[0])
    desde = min(periodos[0], f"{primera_semana.year}{primera_semana.month:02d}")
    ventas = db.execute(
        select(CanalDigitalVenta).where(
            CanalDigitalVenta.tenant_id == tenant, CanalDigitalVenta.bodega == bodega,
            CanalDigitalVenta.periodo >= desde,
        )
    ).scalars().all()
    mapa, conflictos = mapa_padres(db)
    aviso["codigos_en_dos_grupos"] = conflictos

    mes_u = defaultdict(lambda: [0.0] * len(periodos))
    mes_v = defaultdict(lambda: [0.0] * len(periodos))
    sem_u = defaultdict(lambda: [0.0] * N_SEMANAS)
    vendidos: dict[str, set[str]] = defaultdict(set)
    universo_set: set[str] = set()
    for r in ventas:
        p = mapa.get(r.producto, r.producto)
        neto = r.unid_brutas - r.unid_devueltas
        i = idx_p.get(r.periodo)
        if i is not None:
            mes_u[p][i] += neto
            mes_v[p][i] += r.valor_costo
            vendidos[p].add(r.producto)
            universo_set.add(p)
        j = idx_s.get(r.semana)
        if j is not None:
            sem_u[p][j] += neto
    universo = sorted(universo_set)
    aviso["productos"] = len(universo)
    aviso["ultimo_mes_con_ventas"] = max(
        (periodos[i] for p in universo for i, x in enumerate(mes_u[p]) if x), default=None
    )

    # miembros de cada padre: el mismo, los que el motor agrupa bajo el
    miembros: dict[str, set[str]] = {p: {p} for p in universo}
    for c, p in mapa.items():
        if p in miembros:
            miembros[p].add(c)
    todos = sorted({c for ms in miembros.values() for c in ms})
    set_todos = set(todos)

    # stock por codigo normalizado y por tipo de bodega (comparando nombres sin signos ni espacios)
    claves_stock = {_clave(x): "disp" for x in _lista(cfg.bodegas_stock)}
    claves_stock.update({_clave(x): "aparte" for x in _lista(cfg.bodegas_aparte)})
    claves_stock.update({_clave(x): "info" for x in _lista(cfg.bodegas_informativas)})
    stock = defaultdict(lambda: {"disp": 0.0, "aparte": 0.0, "info": 0.0, "total": 0.0})
    for fila in db.execute(
        select(StockUnificado.producto, StockUnificado.bodega, StockUnificado.stock)
        .where(StockUnificado.tenant_id == tenant)
    ).all():
        c = normalizar_codigo(fila.producto)
        if c is None or c not in set_todos:
            continue
        stock[c]["total"] += fila.stock or 0.0
        tipo = claves_stock.get(_clave(fila.bodega))
        if tipo:
            stock[c][tipo] += fila.stock or 0.0

    # costo y descripcion del maestro de precios
    costo: dict[str, float] = {}
    glosa: dict[str, str] = {}
    for trozo in _trozos(todos):
        for f in db.execute(
            select(PrecioProducto.producto, PrecioProducto.costo, PrecioProducto.glosa)
            .where(PrecioProducto.tenant_id == tenant, PrecioProducto.producto.in_(trozo))
        ).all():
            c = normalizar_codigo(f.producto)
            if f.costo is not None and c not in costo:
                costo[c] = float(f.costo)
            if f.glosa and c not in glosa:
                glosa[c] = f.glosa

    # primera venta en la empresa, por mes, desde el historico
    primera: dict[str, dt.date] = {}
    for trozo in _trozos(todos):
        for prod, per in db.execute(
            select(VentaHistorica.producto, func.min(VentaHistorica.periodo))
            .where(VentaHistorica.tenant_id == tenant, VentaHistorica.cantidad > 0,
                   VentaHistorica.producto.in_(trozo))
            .group_by(VentaHistorica.producto)
        ).all():
            if per and len(per) == 6:
                f = dt.date(int(per[:4]), int(per[4:]), 1)
                c = normalizar_codigo(prod)
                if c not in primera or f < primera[c]:
                    primera[c] = f

    # plazo: tabla del motor, fila global del proveedor
    plazo_prov: dict[str, tuple[float, int | None]] = {}
    for f in db.execute(
        select(LeadTimeProveedorSucursal).where(
            LeadTimeProveedorSucursal.tenant_id == tenant, LeadTimeProveedorSucursal.sucursal_id.is_(None)
        )
    ).scalars():
        plazo_prov[f.proveedor] = (float(f.lead_time_dias), f.n_muestras)
    prov_de: dict[str, str] = {}
    for trozo in _trozos(todos):
        for prod, prv in db.execute(
            select(ProveedorProducto.producto, ProveedorProducto.proveedor)
            .where(ProveedorProducto.tenant_id == tenant, ProveedorProducto.producto.in_(trozo))
        ).all():
            prov_de.setdefault(normalizar_codigo(prod), prv)

    # transito: solo OC con destino a la bodega; el resto, informativo
    claves_destino = {_clave(bodega), _clave("SUC" + bodega)}
    t_bodega: dict[str, float] = defaultdict(float)
    t_todos: dict[str, float] = defaultdict(float)
    for f in db.execute(
        select(StockTransito.producto, StockTransito.sucursal_id, StockTransito.cantidad)
        .where(StockTransito.tenant_id == tenant)
    ).all():
        c = normalizar_codigo(f.producto)
        if c not in set_todos:
            continue
        t_todos[c] += f.cantidad or 0.0
        if _clave(f.sucursal_id) in claves_destino:
            t_bodega[c] += f.cantidad or 0.0

    datos = []
    sin_proveedor = 0
    for p in universo:
        ms = sorted(miembros[p])
        prov = next((prov_de[c] for c in [p, *ms] if c in prov_de), "")
        if prov and prov in plazo_prov:
            dias, n = plazo_prov[prov]
            origen = (f"plazo del motor del proveedor ({n if n is not None else '?'} muestras) "
                      f"+ {cfg.gestion_dias:g} dia de gestion")
            confianza = "proveedor con 5 o mas muestras" if (n or 0) >= 5 else "proveedor con menos de 5 muestras"
        else:
            dias = PLAZO_RESPALDO_DIAS
            origen = f"respaldo {PLAZO_RESPALDO_DIAS:g} dias + {cfg.gestion_dias:g} dia de gestion (sin proveedor)"
            confianza = "sin proveedor (respaldo)"
            sin_proveedor += 1
        c_costo = costo.get(p) if p in costo else next((costo[c] for c in ms if c in costo), None)
        hay_stock = any(stock[c]["total"] > 0 for c in ms if c in stock)
        datos.append(DatosProducto(
            codigo=p,
            descripcion=glosa.get(p) or next((glosa[c] for c in ms if c in glosa), ""),
            codigos_vendidos=" | ".join(sorted(vendidos[p])) if vendidos[p] else p,
            unidades_mes=mes_u[p], valor_mes=mes_v[p],
            primera_venta=min((primera[c] for c in ms if c in primera), default=None),
            unidades_semana=sem_u[p],
            plazo_dias=dias + cfg.gestion_dias, plazo_origen=origen, plazo_confianza=confianza, proveedor=prov,
            plazo_motor_dias=dias,
            stock_disponible=sum(stock[c]["disp"] for c in ms if c in stock),
            stock_aparte=sum(stock[c]["aparte"] for c in ms if c in stock),
            stock_cd=sum(stock[c]["info"] for c in ms if c in stock),
            transito=sum(t_bodega[c] for c in ms if c in t_bodega),
            transito_cualquier_destino=sum(t_todos[c] for c in ms if c in t_todos),
            costo_actual=c_costo,
            costo_respaldo=("sin costo" if c_costo is None
                            else ("con stock hoy" if hay_stock else "sin respaldo de stock")),
        ))
    aviso["sin_proveedor"] = sin_proveedor
    return datos, aviso


def calcular(db: Session, bodega: str = BODEGA_CANAL_DIGITAL, hoy: dt.date | None = None) -> tuple[Corrida, dict]:
    """Corre la bodega con los datos de hoy y la politica guardada. No escribe nada."""
    hoy = hoy or dt.date.today()
    datos, aviso = reunir_datos(db, bodega, hoy)
    cfg = asegurar_bodega(db, bodega)
    parametros = ParametrosClasificacion(
        ventana_meses=cfg.ventana_meses, nuevo_meses=cfg.nuevo_meses,
        corte_a_pct=cfg.corte_a_pct, corte_b_pct=cfg.corte_b_pct,
    )
    corrida = correr(
        datos, leer_politica(db, bodega), dt.date.fromisoformat(aviso["fecha_referencia"]),
        parametros, ParametrosReposicion(r_semanas=cfg.r_semanas),
    )
    return corrida, aviso
