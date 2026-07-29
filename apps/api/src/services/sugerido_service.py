"""Logica de consulta del sugerido: aplica filtros, ordena, pagina y calcula KPIs.

NOTA Fase 0: aca NO se calcula el sugerido. Los valores ya vienen del Power BI.
Solo se filtra/agrega lo que ya esta cargado en la tabla.
"""
import math
from datetime import datetime, timezone

from sqlalchemy import (
    Float,
    Integer,
    Numeric,
    String,
    and_,
    distinct,
    false,
    func,
    or_,
    select,
)
from sqlalchemy.orm import Session

from ..models import (
    ProductoCatalogo,
    StockUnificado,
    Sugerido,
    SugerenciaManual,
    VentaHistorica,
)
from ..schemas import SugeridoFiltros
from . import margen, pedidos_service, stock_service

# Columnas por las que se permite ordenar (whitelist para evitar inyeccion).
SORTABLE = {c.name for c in Sugerido.__table__.columns}

# Productos internos (taller, insumos, incentivos, deducciones) que no se compran a
# proveedor: se ocultan siempre del sugerido. Si aparece uno nuevo, agregar su prefijo aquí.
PREFIJOS_EXCLUIDOS = ("D&P", "MEC INSUMOS", "INCENTIVOS", "APLICA-DED")

# Sucursales cerradas/ocultas: siguen en el modelo del BI (arrastran ventas historicas
# dentro de la ventana movil de 12m) pero YA NO OPERAN, asi que no deben verse en la
# plataforma. Caso jul-2026: "DIEZ DE JULIO" cerro y fue reemplazada por la sucursal
# activa "DIEZ DE JULIO (2)" (dos bodegas distintas). El filtro va sobre `sucursal_id`
# (el id canonico del modelo) con comparacion EXACTA en minusculas -> nunca afecta a
# "DIEZ DE JULIO (2)". Es una decision de presentacion (el modelo las sigue calculando).
SUCURSALES_OCULTAS = ("DIEZ DE JULIO",)
_OCULTAS_LOWER = [s.lower() for s in SUCURSALES_OCULTAS]

# Centinela del filtro multi-select del grid para valores nulos/vacios.
BLANCO_SENTINEL = "(en blanco)"


def _columna_numerica(campo: str) -> bool:
    col = Sugerido.__table__.columns.get(campo)
    return col is not None and isinstance(col.type, (Integer, Float, Numeric))


def _clausula_columna(fc):
    """Traduce un filtro de columna (del multi-select del grid) a una clausula
    SQLAlchemy. `contiene` -> ILIKE %texto%; `valores` -> IN exacto, con el
    centinela "(en blanco)" = NULL/vacio. None si el campo no es valido o esta vacio."""
    campo = getattr(fc, "campo", None)
    if not campo or campo not in SORTABLE:
        return None
    col = getattr(Sugerido, campo)
    contiene = getattr(fc, "contiene", None)
    if contiene:
        # Cast a texto para poder hacer "contiene" tambien en columnas numericas.
        return func.cast(col, String).ilike(f"%{contiene}%")
    valores = getattr(fc, "valores", None)
    if valores is not None:
        incluir_blanco = BLANCO_SENTINEL in valores
        reales = [v for v in valores if v != BLANCO_SENTINEL]
        clausulas = []
        if _columna_numerica(campo):
            nums = []
            for v in reales:
                try:
                    nums.append(float(v))
                except (TypeError, ValueError):
                    pass
            if nums:
                clausulas.append(col.in_(nums))
            if incluir_blanco:
                clausulas.append(col.is_(None))
        else:
            if reales:
                clausulas.append(col.in_(reales))
            if incluir_blanco:
                clausulas.append(or_(col.is_(None), col == ""))
        # Sin clausulas (el usuario destildo todo) -> no matchea ninguna fila.
        return or_(*clausulas) if clausulas else false()
    return None


def _apply_alcance(stmt, f: SugeridoFiltros):
    """Lo que NO existe para la plataforma, pase lo que pase.

    Separado de `_apply_filters` porque son reglas de otra naturaleza: aca no hay
    nada que el usuario elija, es lo que esta fuera de alcance (su permiso de
    sucursal, sucursales cerradas, productos internos). `_resolver_manuales` lo
    usa para preguntar "¿este producto existe en el sugerido?" sin arrastrar la
    vista ni los filtros de la pantalla.
    """
    # Restriccion de acceso por sucursal (la fija el servidor segun el usuario).
    # Debe ir primero: acota TODO el sugerido a las sucursales del usuario.
    if f.sucursales_permitidas is not None:
        stmt = stmt.where(Sugerido.sucursal_id.in_(f.sucursales_permitidas))
    # Ocultar sucursales cerradas (p.ej. "DIEZ DE JULIO", reemplazada por su "(2)").
    # Aplica a grilla, KPIs, graficos, carga masiva y carros de compra (todos pasan
    # por aca). Exacto en minusculas: "DIEZ DE JULIO (2)" NO se ve afectada.
    if _OCULTAS_LOWER:
        stmt = stmt.where(func.lower(Sugerido.sucursal_id).notin_(_OCULTAS_LOWER))
    # Excluir productos internos (D&P REPTO-TALLER, etc.) de todo el sugerido.
    for pref in PREFIJOS_EXCLUIDOS:
        stmt = stmt.where(~Sugerido.producto.ilike(f"{pref}%"))
    return stmt


def _apply_filters(stmt, f: SugeridoFiltros):
    stmt = _apply_alcance(stmt, f)
    busqueda = bool(f.q and f.q.strip())
    if busqueda:
        like = f"%{f.q}%"
        # Busqueda global: matchea cualquier columna de texto del sugerido.
        # El usuario puede tipear codigo, descripcion, sucursal, marca, proveedor,
        # ABC, tipo_origen, abastece_cd, etc. y la fila aparece si contiene el texto.
        stmt = stmt.where(
            or_(
                Sugerido.producto.ilike(like),
                Sugerido.descripcion.ilike(like),
                Sugerido.nombre_sucursal.ilike(like),
                Sugerido.proveedor.ilike(like),
                Sugerido.filtro1_final.ilike(like),
                Sugerido.tipo_origen.ilike(like),
                Sugerido.clasificacion_abc.ilike(like),
                Sugerido.abastece_cd.ilike(like),
            )
        )
    if f.sucursales:
        stmt = stmt.where(Sugerido.nombre_sucursal.in_(f.sucursales))
    if f.abc:
        stmt = stmt.where(Sugerido.clasificacion_abc.in_(f.abc))
    if f.filtro1:
        stmt = stmt.where(Sugerido.filtro1_final.in_(f.filtro1))
    if f.tipo_origen:
        stmt = stmt.where(Sugerido.tipo_origen.in_(f.tipo_origen))
    if f.proveedor:
        stmt = stmt.where(Sugerido.proveedor.ilike(f"%{f.proveedor}%"))
    if f.proveedores:
        stmt = stmt.where(Sugerido.proveedor.in_(f.proveedores))
    # Cuando el usuario escribe un codigo o nombre, queremos que vea TODAS las
    # coincidencias aunque su sugerido del BI sea pedir=No. Si no, "no aparece".
    if f.solo_pedir and not busqueda:
        stmt = stmt.where(func.lower(Sugerido.pedir) == "si")
    if f.solo_nacionales and not busqueda:
        # Excluye importados. es_importado=False o NULL se considera nacional.
        stmt = stmt.where(or_(Sugerido.es_importado.is_(False), Sugerido.es_importado.is_(None)))
    # Vista del proceso de compras. La busqueda global (q) las anula igual que pedir/nacionales.
    if not busqueda:
        vista = (f.vista or "todas").lower()
        if vista == "sucursales":
            # Compra directa de sucursal: NO se abastece via CD Y la sucursal no es el CD.
            stmt = stmt.where(Sugerido.sucursal_id != "CD REPUESTOS")
            stmt = stmt.where(
                or_(
                    Sugerido.abastece_cd.is_(None),
                    ~func.lower(Sugerido.abastece_cd).in_(("si", "sí")),
                )
            )
        elif vista == "cd":
            # Compra del CD: lo que el CD le pide al proveedor.
            stmt = stmt.where(Sugerido.sucursal_id == "CD REPUESTOS")
        elif vista == "distribucion":
            # Distribucion / traslado del CD a las sucursales (no incluye el CD mismo).
            stmt = stmt.where(Sugerido.sucursal_id != "CD REPUESTOS")
            stmt = stmt.where(func.lower(Sugerido.abastece_cd).in_(("si", "sí")))
            # Solo filas accionables (contrato del modelo BI): con traslado sugerido
            # o con sugerido directo (importados locales A/B, pendiente regla de
            # negocio). Sin este guard la vista arrastra miles de filas en cero.
            stmt = stmt.where(
                or_(Sugerido.sugerido_traslado > 0, Sugerido.total_sugerido_suc > 0)
            )
    # Filtros de columna de la tabla (traducidos del multi-select del grid). Se
    # aplican server-side para que KPIs, conteo y Excel sean EXACTOS sobre el total.
    # El listado de filas NO los envia (el grid filtra del lado cliente para
    # conservar todas las opciones del multi-select): aca solo llegan en KPIs/export.
    for fc in getattr(f, "filtros_columna", None) or []:
        cl = _clausula_columna(fc)
        if cl is not None:
            stmt = stmt.where(cl)
    return stmt


def _apply_sort(stmt, sort: str | None):
    """sort = 'campo' o '-campo' (descendente)."""
    if not sort:
        return stmt.order_by(Sugerido.total_sugerido_suc.desc().nullslast())
    desc = sort.startswith("-")
    col_name = sort[1:] if desc else sort
    if col_name in SORTABLE:
        col = getattr(Sugerido, col_name)
        return stmt.order_by(col.desc().nullslast() if desc else col.asc().nullslast())
    return stmt.order_by(Sugerido.total_sugerido_suc.desc().nullslast())


def _row_desde_catalogo(c: ProductoCatalogo) -> dict:
    """Mapea una fila del catalogo maestro a la 'forma' de SugeridoRow,
    con los campos del sugerido vacios (el frontend renderiza '—')."""
    return {
        # marcador
        "id": -c.id,  # id negativo para no chocar con sugerido.id
        "origen": "catalogo",
        # campos basicos que sí tenemos
        "producto": c.producto,
        "descripcion": c.glosa,
        "empresa": None,
        "filtro1_final": None,  # el catalogo no tiene marca
        "proveedor": None,
        "costo_unitario": c.costo,
        "tipo_origen": c.procedencia,
        "unidad_medida": c.unidad,
        # campos especificos del sugerido -> None
        "sucursal_id": None,
        "nombre_sucursal": None,
        "clasificacion_abc": None,
        "es_importado": None,
        "lead_time_dias": None,
        "lt_efectivo": None,
        "lt_cd_a_sucursal_dias": None,
        "lt_origen": None,
        "abastece_cd": None,
        "prioridad_cd": None,
        "comprar_en_el_cd": None,
        "tiene_stock_cd": None,
        "demanda_mensual": None,
        "demanda_diaria": None,
        "desv_std_mensual": None,
        "stock_seguridad": None,
        "punto_de_pedido": None,
        "pedir": None,
        "reemplazos": c.reemplazo,
        "sugerido_suc": None,
        "stock_activo_suc": None,
        "stock_en_transito_suc": None,
        "stock_en_cd": None,
        "sugerido_traslado": None,
        "sugerido_compra_neto": None,
        "total_sugerido_suc": None,
        "total_valor_sugerido_clp": None,
        "pedir_flag": None,
    }


def _no_vencida():
    """Clausula: la sugerencia no tiene vencimiento o aun no llega. Asi una manual con
    duracion deja de sumar exactamente al vencer, sin esperar a que el cron la archive."""
    return or_(
        SugerenciaManual.expira_en.is_(None),
        SugerenciaManual.expira_en > datetime.now(timezone.utc),
    )


def _manuales_por_par(db: Session, q: str | None = None) -> dict[tuple[str, str], int]:
    """Devuelve {(producto, sucursal_id): unidades vigentes} de sugerencias manuales.

    Si se pasa q, solo trae los productos cuyo codigo lo contiene (acota al caso de busqueda).
    """
    stmt = (
        select(
            SugerenciaManual.producto,
            SugerenciaManual.sucursal_id,
            func.sum(SugerenciaManual.unidades).label("total"),
        )
        .where(SugerenciaManual.archivada.is_(False), _no_vencida())
        .group_by(SugerenciaManual.producto, SugerenciaManual.sucursal_id)
    )
    if q:
        stmt = stmt.where(SugerenciaManual.producto.ilike(f"%{q}%"))
    return {
        (p, s): int(t or 0) for p, s, t in db.execute(stmt).all() if t and int(t) > 0
    }


def _resolver_manuales(db: Session, f: SugeridoFiltros) -> dict:
    """Decide como entra cada sugerencia manual vigente en la pantalla actual.

    Tres destinos posibles:

    - `en_vista`: su fila del sugerido ya pasa todos los filtros. Las unidades se
      suman sobre esa fila y no hay nada mas que hacer.
    - `extras`: la fila pertenece a esta vista pero quedo fuera por "solo pedir" o
      "solo nacionales". Una manual es una orden explicita de comprar, asi que la
      fila se muestra igual (con sus datos reales, no en blanco).
    - `solas`: el producto NO tiene fila en el sugerido en ninguna parte. Recien
      ahi corresponde fabricar una fila desde el catalogo.

    OJO con `en_tabla`: se consulta la tabla COMPLETA, solo con el alcance del
    usuario, sin la vista ni los filtros de pantalla. Preguntando sobre el set ya
    filtrado, una manual de Linderos mirada desde la pestania "Compra CD" parecia
    huerfana: el codigo le fabricaba una fila desde `producto_catalogo`, que NO
    tiene columna de proveedor, y la pegaba en la vista del CD. Resultado: 97
    filas en blanco de otras sucursales dentro de la compra del CD, todas con su
    fila buena (con proveedor, ABC y stock) escondida en otra pestania.
    """
    vacio: dict = {"por_par": {}, "en_vista": set(), "extras": set(), "solas": {}}
    por_par = _manuales_por_par(db, (f.q or "").strip() or None)
    if not por_par:
        return vacio
    pares = set(por_par)
    productos = {p for p, _ in pares}

    def _consultar(stmt) -> set[tuple[str, str]]:
        stmt = stmt.where(Sugerido.producto.in_(productos))
        return {(p, s) for p, s in db.execute(stmt).all()} & pares

    cols = select(Sugerido.producto, Sugerido.sucursal_id)
    en_vista = _consultar(_apply_filters(cols, f))
    # Sin "solo pedir"/"solo nacionales": lo que la vista SI muestra pero esos dos
    # toggles esconden.
    amplio = f.model_copy(update={"solo_pedir": False, "solo_nacionales": False})
    extras = _consultar(_apply_filters(cols, amplio)) - en_vista
    en_tabla = _consultar(_apply_alcance(cols, f))

    solas = {par: u for par, u in por_par.items() if par not in en_tabla}
    if f.sucursales_permitidas is not None:
        permitidas = set(f.sucursales_permitidas)
        solas = {(p, s): u for (p, s), u in solas.items() if s in permitidas}
    return {"por_par": por_par, "en_vista": en_vista, "extras": extras, "solas": solas}


def _filas_de_pares(db: Session, pares: set[tuple[str, str]]) -> list[Sugerido]:
    """Filas del sugerido para un conjunto de pares (producto, sucursal).

    Con OR de AND en vez de `tuple_().in_()`: la forma con tuplas no es portable
    entre SQLite (tests) y Postgres (produccion).
    """
    if not pares:
        return []
    cond = or_(*[and_(Sugerido.producto == p, Sugerido.sucursal_id == s) for p, s in pares])
    return list(db.scalars(select(Sugerido).where(cond)).all())


def _fila_sintetica_manual(
    producto: str, sucursal_id: str, unidades: int, cat: ProductoCatalogo | None
) -> dict:
    """Fila para un par (producto, sucursal) que tiene sugerencia manual pero NO esta en el
    sugerido del BI. Se enriquece con los datos del catalogo si estan disponibles."""
    return {
        "id": -abs(hash((producto, sucursal_id))) % (10**9),
        "origen": "manual",
        "producto": producto,
        "descripcion": cat.glosa if cat else None,
        "sucursal_id": sucursal_id,
        "nombre_sucursal": sucursal_id,
        "empresa": None,
        "clasificacion_abc": None,
        "proveedor": None,
        "filtro1_final": None,
        "tipo_origen": cat.procedencia if cat else None,
        "es_importado": None,
        "unidad_medida": cat.unidad if cat else None,
        "lead_time_dias": None, "lt_efectivo": None, "lt_cd_a_sucursal_dias": None,
        "lt_origen": None, "abastece_cd": None, "prioridad_cd": None,
        "comprar_en_el_cd": None, "tiene_stock_cd": None,
        "demanda_mensual": None, "demanda_diaria": None, "desv_std_mensual": None,
        "stock_seguridad": None, "punto_de_pedido": None,
        "costo_unitario": cat.costo if cat else None,
        "pedir": "Si",
        "reemplazos": cat.reemplazo if cat else None,
        "sugerido_suc": None, "stock_activo_suc": None,
        "stock_en_transito_suc": None, "stock_en_cd": None,
        "sugerido_traslado": None,
        "sugerido_compra_neto": float(unidades),
        "total_sugerido_suc": float(unidades),
        "total_valor_sugerido_clp": (
            float(unidades) * float(cat.costo) if cat and cat.costo else None
        ),
        "pedir_flag": "Si",
    }


def _aplicar_manuales_a_fila(d: dict, manual_unidades: int) -> None:
    """Suma una sugerencia manual vigente a la fila dict del sugerido del BI.

    Muta `d` in-place. Misma logica usada en `listar` y `listar_por_ids` para que
    la grilla y el export devuelvan exactamente los mismos numeros.
    """
    if not manual_unidades:
        return
    base_total = float(d.get("total_sugerido_suc") or 0)
    d["total_sugerido_suc"] = base_total + manual_unidades
    base_compra = float(d.get("sugerido_compra_neto") or d.get("total_sugerido_suc") or 0)
    d["sugerido_compra_neto"] = base_compra + manual_unidades
    if d.get("costo_unitario"):
        d["total_valor_sugerido_clp"] = (
            float(d.get("total_valor_sugerido_clp") or 0)
            + manual_unidades * float(d["costo_unitario"])
        )
    d["pedir"] = "Si"
    d["pedir_flag"] = "Si"


def _mes_anterior_yyyymm(hoy: "date | None" = None) -> str:
    """Devuelve el mes calendario anterior en formato YYYYMM (string).

    Si hoy es 2026-06-26 -> "202605". Helper aislado para que el test pueda
    pasar una fecha fija.
    """
    from datetime import date as _date

    h = hoy or _date.today()
    if h.month == 1:
        return f"{h.year - 1}12"
    return f"{h.year}{h.month - 1:02d}"


def _aplicar_regla_stock_sin_venta(
    items: list[dict], db: Session, con_manual: set[tuple[str, str]] | None = None
) -> None:
    """Regla de negocio: si un producto tiene stock activo de sucursal >= demanda
    mensual Y no tuvo venta en el mes calendario anterior, no se sugiere comprar.

    `con_manual` son los pares que tienen sugerencia manual vigente: la regla NO
    los toca. Cargar una manual es decir "compra esto igual"; que una regla
    automatica la volviera a marcar "no pedir" seria pasar por encima de una
    decision explicita de Abastecimiento (y ademas dejaria la fila fuera del
    dashboard, que filtra por "solo pedir").

    Se aplica marcando `pedir = "No"` y `pedir_flag = "No"`. El total_sugerido_suc
    del BI NO se altera (la regla es opinable y conviene poder revisarla); como
    el dashboard filtra por defecto "Solo pedir = Si", las filas dejan de aparecer
    sin perder el dato original.

    Idea: evitar comprar a un proveedor cuando la sucursal tiene cubierta su
    demanda con stock propio y ademas el producto no se movio el mes pasado
    (= demanda historica que ya no se materializa hoy).

    Muta `items` in-place. Una sola query batch a `venta_historica` para todos los
    pares (producto, sucursal) involucrados.
    """
    if not items:
        return
    pares = {
        (it.get("producto"), it.get("sucursal_id"))
        for it in items
        if it.get("producto") and it.get("sucursal_id")
    }
    if not pares:
        return
    mes = _mes_anterior_yyyymm()

    # Guarda: "sin venta" solo se puede afirmar si el mes ESTA cargado. Si la tabla
    # no tiene ninguna fila de ese periodo, es que los datos no llegaron todavia, no
    # que nadie vendio; aplicar la regla ahi marcaria "No pedir" a todo producto con
    # stock >= demanda y los sacaria del sugerido (el dashboard filtra "solo pedir").
    # Ante la duda no se aplica: es preferible sugerir de mas que ocultar compras.
    hay_mes = db.scalar(
        select(func.count())
        .select_from(VentaHistorica)
        .where(VentaHistorica.periodo == mes)
        .limit(1)
    )
    if not hay_mes:
        return

    productos = {p for p, _ in pares}
    sucursales = {s for _, s in pares}
    # Suma de cantidad vendida el mes anterior por par.
    rows = db.execute(
        select(
            VentaHistorica.producto,
            VentaHistorica.sucursal,
            func.coalesce(func.sum(VentaHistorica.cantidad), 0).label("c"),
        )
        .where(
            VentaHistorica.producto.in_(productos),
            VentaHistorica.sucursal.in_(sucursales),
            VentaHistorica.periodo == mes,
        )
        .group_by(VentaHistorica.producto, VentaHistorica.sucursal)
    ).all()
    venta_map = {(p, s): float(c or 0) for p, s, c in rows}

    for it in items:
        p = it.get("producto")
        s = it.get("sucursal_id")
        if not p or not s:
            continue
        if con_manual and (p, s) in con_manual:
            continue
        stock_activo = it.get("stock_activo_suc")
        demanda = it.get("demanda_mensual")
        # Necesitamos ambos numericos y demanda > 0 (si demanda=0 la regla no
        # aporta nada: el modelo del BI ya no deberia sugerir nada).
        if stock_activo is None or demanda is None or float(demanda) <= 0:
            continue
        if float(stock_activo) < float(demanda):
            continue
        if venta_map.get((p, s), 0.0) > 0:
            continue
        # Stock cubre el mes + sin venta el mes anterior -> no pedir.
        it["pedir"] = "No"
        it["pedir_flag"] = "No"


def _enriquecer_con_catalogo(items: list[dict], db: Session) -> None:
    """Agrega campos del ProductoCatalogo que NO vienen del modelo Sugerido.

    Hoy solo `reemplazos` (catalogo.reemplazo). Un solo SELECT por todos los
    productos distintos de la lista. Muta `items` in-place.
    """
    if not items:
        return
    productos = {it.get("producto") for it in items if it.get("producto")}
    if not productos:
        return
    rows = db.execute(
        select(ProductoCatalogo.producto, ProductoCatalogo.reemplazo)
        .where(ProductoCatalogo.producto.in_(productos))
    ).all()
    cat_map = {p: r for p, r in rows}
    for it in items:
        p = it.get("producto")
        # Enriquecer solo si la fila no tiene reemplazo. El modelo Sugerido tiene
        # la columna `reemplazos` pero el BI no la llena (siempre None), asi que
        # la traemos del catalogo. Las filas de _row_desde_catalogo ya vienen con
        # su propio valor; no las pisamos.
        if p and not it.get("reemplazos"):
            it["reemplazos"] = cat_map.get(p)


def listar(
    db: Session, f: SugeridoFiltros, page: int = 1, limit: int = 50, sort: str | None = None
) -> tuple[list[dict], int]:
    base = _apply_filters(select(Sugerido), f)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0

    stmt = _apply_sort(base, sort).offset((page - 1) * limit).limit(limit)
    sugeridos = list(db.scalars(stmt).all())

    # Trae las manuales VIGENTES por par. Cuando hay busqueda acotamos al texto;
    # cuando no, traemos todas (el sugerido del BI ya esta paginado, son pocas).
    q_text = (f.q or "").strip() or None
    man = _resolver_manuales(db, f)
    manuales = man["por_par"]

    def _a_dict(s: Sugerido) -> dict:
        d = {c.name: getattr(s, c.name) for c in Sugerido.__table__.columns}
        d["origen"] = "sugerido"
        _aplicar_manuales_a_fila(d, manuales.get((s.producto, s.sucursal_id), 0))
        return d

    # Mapeo a dict + suma de manuales para los pares ya presentes en sugerido.
    items: list[dict] = [_a_dict(s) for s in sugeridos]

    # Los totales NO dependen de la pagina; las filas de abajo se agregan solo en
    # la primera: van despues de paginar, asi que repetirlas en cada pagina seria
    # mostrarlas N veces (y hacer que el total variara con el tamano de pagina).
    total_extras = len(man["extras"])
    total_manuales_solas = len(man["solas"])

    # Filas reales que "solo pedir"/"solo nacionales" escondia. La manual es una
    # orden explicita de comprar: gana sobre el toggle, y se muestra la fila BUENA
    # (con proveedor, ABC y stock), no una en blanco.
    if man["extras"] and page == 1:
        items.extend(_a_dict(s) for s in _filas_de_pares(db, man["extras"]))

    # Filas sinteticas para pares (producto, sucursal) que NO estan en el sugerido
    # en ninguna parte. Son las que alguien cargo a mano sobre un producto que el
    # modelo no pide; si no se mostraran, se compraria a ciegas. Salen sin
    # proveedor ni ABC porque `producto_catalogo` no los tiene: es lo unico que
    # hay cuando el producto no existe en el sugerido.
    if man["solas"] and page == 1:
        cat_map = {
            c.producto: c
            for c in db.scalars(
                select(ProductoCatalogo).where(
                    ProductoCatalogo.producto.in_({p for p, _ in man["solas"]})
                )
            ).all()
        }
        for (p, s), u in man["solas"].items():
            items.append(_fila_sintetica_manual(p, s, u, cat_map.get(p)))

    # Catalogo (productos que no estan ni en sugerido ni con manuales): solo cuando hay busqueda.
    total_cat = 0
    if q_text:
        like = f"%{q_text}%"
        productos_sugerido_sub = select(distinct(Sugerido.producto)).scalar_subquery()
        cat_stmt = (
            select(ProductoCatalogo)
            .where(or_(ProductoCatalogo.producto.ilike(like), ProductoCatalogo.glosa.ilike(like)))
            .where(~ProductoCatalogo.producto.in_(productos_sugerido_sub))
            .order_by(ProductoCatalogo.producto.asc())
            .limit(200)
        )
        try:
            catalogo_items = list(db.scalars(cat_stmt).all())
            # Omitir productos que ya aparecieron como filas sinteticas manuales.
            productos_manuales = {p for (p, _) in manuales.keys()}
            catalogo_items = [c for c in catalogo_items if c.producto not in productos_manuales]
            total_cat = len(catalogo_items)
            # Igual que las manuales sueltas: cuentan siempre, se muestran en la
            # pagina 1 (se agregan despues de paginar).
            if page == 1:
                rows_cat = [_row_desde_catalogo(c) for c in catalogo_items]
                stock_map = stock_service.stock_total_por_producto(
                    db, [r["producto"] for r in rows_cat]
                )
                for r in rows_cat:
                    if r["producto"] in stock_map:
                        r["stock_activo_suc"] = stock_map[r["producto"]]
                items.extend(rows_cat)
        except Exception:
            total_cat = 0

    # Enriquecer con columnas del catalogo (reemplazos, etc.) que no viven en
    # el modelo Sugerido. Las filas que ya vienen del catalogo o sinteticas no
    # se tocan: el helper salta cuando ya hay 'reemplazos' en la fila.
    _enriquecer_con_catalogo(items, db)
    margen.agregar_margen(items)
    pedidos_service.agregar_a_filas(items, db)

    # Regla de negocio (jun-2026): si tiene stock para su demanda mensual y no
    # tuvo venta el mes anterior, no se sugiere comprar. Las que tienen manual
    # quedan fuera: ahi ya hubo una decision explicita de comprar.
    _aplicar_regla_stock_sin_venta(items, db, con_manual=set(manuales))

    return items, total + total_extras + total_manuales_solas + total_cat


def _aporte_manuales(db: Session, f: SugeridoFiltros) -> dict:
    """Cuanto suman las sugerencias manuales vigentes sobre los KPIs.

    Espeja EXACTAMENTE lo que hace `listar`, y esa es la razon de ser de esta
    funcion: las tarjetas tienen que dar lo mismo que la tabla. Dos casos:

    - manual sobre un par que YA esta en el sugerido filtrado: suma unidades a esa
      fila, valorizadas con el costo de esa fila;
    - manual sobre un par que no esta: es una fila propia ("suelta"), valorizada
      con el costo del catalogo, y aporta un producto mas al conteo.

    Las sueltas no tienen proveedor ni clase ABC, asi que —igual que en `listar`—
    solo las acota el permiso de sucursal, no los filtros del usuario. Si algun dia
    eso cambia, hay que cambiarlo en los dos lados o las tarjetas dejan de cuadrar.
    """
    vacio = {"unidades": 0.0, "valor_clp": 0.0, "manual_unidades": 0.0, "manual_clp": 0.0,
             "filas": 0, "productos": set()}
    man = _resolver_manuales(db, f)
    manuales = man["por_par"]
    if not manuales:
        return vacio

    unidades = valor = 0.0          # lo que hay que SUMARLE a los totales base
    manual_u = manual_clp = 0.0     # de eso, cuanto viene de sugerencias manuales
    filas = 0
    productos: set[str] = set()

    # 1) Sobre filas que el KPI base ya conto: solo se agregan las unidades manuales.
    filas_en_vista = _filas_de_pares(db, man["en_vista"])
    for s in filas_en_vista:
        u = manuales[(s.producto, s.sucursal_id)]
        clp = u * float(s.costo_unitario or 0)
        unidades += u
        valor += clp
        manual_u += u
        manual_clp += clp

    # 2) Filas que el KPI base NO conto (las escondia "solo pedir"): entran enteras,
    #    con su propio sugerido, mas las unidades manuales.
    for s in _filas_de_pares(db, man["extras"]):
        u = manuales[(s.producto, s.sucursal_id)]
        clp = u * float(s.costo_unitario or 0)
        unidades += float(s.total_sugerido_suc or 0) + u
        valor += float(s.total_valor_sugerido_clp or 0) + clp
        manual_u += u
        manual_clp += clp
        filas += 1
        productos.add(s.producto)

    # 3) Filas propias (producto sin fila en el sugerido), valorizadas con el catalogo.
    if man["solas"]:
        costo_cat = {
            c.producto: float(c.costo or 0)
            for c in db.scalars(
                select(ProductoCatalogo).where(
                    ProductoCatalogo.producto.in_({p for p, _ in man["solas"]})
                )
            ).all()
        }
        for (p, _s), u in man["solas"].items():
            clp = u * costo_cat.get(p, 0.0)
            unidades += u
            valor += clp
            manual_u += u
            manual_clp += clp
            filas += 1
            productos.add(p)

    return {
        "unidades": unidades,
        "valor_clp": valor,
        "manual_unidades": manual_u,
        "manual_clp": manual_clp,
        "filas": filas,
        "productos": productos,
    }


def kpis(db: Session, f: SugeridoFiltros) -> dict:
    base = _apply_filters(select(Sugerido), f).subquery()

    total_sugerido = db.scalar(select(func.coalesce(func.sum(base.c.total_sugerido_suc), 0))) or 0
    valor_total = db.scalar(select(func.coalesce(func.sum(base.c.total_valor_sugerido_clp), 0))) or 0
    n_proveedores = db.scalar(select(func.count(distinct(base.c.proveedor)))) or 0
    # Conteo exacto de filas que cumplen los filtros (incluye los de columna):
    # el dashboard lo usa para mostrar cuántas filas quedan tras el filtro.
    n_filas = db.scalar(select(func.count()).select_from(base)) or 0

    # Las sugerencias manuales NO viven en la tabla Sugerido. Hasta jul-2026 las
    # tarjetas las ignoraban mientras la tabla si las sumaba: los numeros de arriba
    # no cuadraban con los de abajo y lo comprado a mano quedaba fuera del total.
    man = _aporte_manuales(db, f)

    # Productos: hay que unir los conjuntos (una manual puede traer un producto que
    # el sugerido no tiene en esta vista). Solo se materializa la lista si hace falta.
    if man["productos"]:
        productos = {p for (p,) in db.execute(select(distinct(base.c.producto))).all()}
        n_productos = len(productos | man["productos"])
    else:
        n_productos = db.scalar(select(func.count(distinct(base.c.producto)))) or 0

    return {
        "total_sugerido": float(total_sugerido) + man["unidades"],
        "valor_total_clp": float(valor_total) + man["valor_clp"],
        "n_productos": int(n_productos),
        "n_proveedores": int(n_proveedores),
        "n_filas": int(n_filas) + man["filas"],
        # Desglose para mostrar entre parentesis cuanto viene de sugerencias manuales.
        "total_sugerido_manual": man["manual_unidades"],
        "valor_manual_clp": man["manual_clp"],
    }


# Dimensiones permitidas para agrupar (para graficos).
DIMENSIONES = {
    "sucursal": Sugerido.nombre_sucursal,
    "marca": Sugerido.filtro1_final,
    "proveedor": Sugerido.proveedor,
}


def agrupado(db: Session, f: SugeridoFiltros, por: str, limite: int = 15) -> list[dict]:
    """Agrega el sugerido por una dimension (sucursal/marca/proveedor), respetando filtros.

    Devuelve los `limite` grupos con mayor valor CLP.
    """
    col = DIMENSIONES.get(por)
    if col is None:
        raise ValueError(f"Dimension no valida: {por}")

    stmt = (
        _apply_filters(
            select(
                col.label("grupo"),
                func.coalesce(func.sum(Sugerido.total_sugerido_suc), 0).label("total_sugerido"),
                func.coalesce(func.sum(Sugerido.total_valor_sugerido_clp), 0).label("valor_clp"),
                func.count(distinct(Sugerido.producto)).label("n_productos"),
            ),
            f,
        )
        .where(col.isnot(None))
        .group_by(col)
        .order_by(func.coalesce(func.sum(Sugerido.total_valor_sugerido_clp), 0).desc())
        .limit(limite)
    )

    return [
        {
            "grupo": str(row.grupo),
            "total_sugerido": float(row.total_sugerido),
            "valor_clp": float(row.valor_clp),
            "n_productos": int(row.n_productos),
        }
        for row in db.execute(stmt).all()
    ]


def pares_filtrados(db: Session, f: SugeridoFiltros) -> list[tuple[str, str]]:
    """Devuelve los pares (producto, sucursal_id) que cumplen los filtros.

    Se usa para la carga masiva de sugerencias manuales "a todos los productos
    segun los filtros del dashboard".
    """
    stmt = _apply_filters(select(Sugerido.producto, Sugerido.sucursal_id), f)
    return [(p, s) for p, s in db.execute(stmt).all()]


def unidades_desde_dias(
    db: Session, producto: str, sucursal_id: str, dias: int
) -> int | None:
    """Convierte 'dias de inventario' a unidades: ceil(dias * demanda_diaria).

    Devuelve None si el producto+sucursal no esta en el sugerido o no tiene
    demanda diaria > 0 (en ese caso el caller decide: omitir o avisar).
    """
    if dias <= 0:
        return None
    row = db.execute(
        select(Sugerido.demanda_diaria)
        .where(Sugerido.producto == producto, Sugerido.sucursal_id == sucursal_id)
    ).first()
    if not row or row[0] is None or row[0] <= 0:
        return None
    return max(1, math.ceil(float(row[0]) * dias))


def unidades_por_par(
    db: Session, pares: list[tuple[str, str]], dias: int
) -> dict[tuple[str, str], int]:
    """Calcula unidades para muchos pares de una sola query.

    Solo devuelve pares con demanda_diaria > 0; los demas quedan fuera del dict
    (el caller los reporta como omitidos).
    """
    if not pares or dias <= 0:
        return {}
    productos = {p for p, _ in pares}
    sucursales = {s for _, s in pares}
    rows = db.execute(
        select(Sugerido.producto, Sugerido.sucursal_id, Sugerido.demanda_diaria)
        .where(Sugerido.producto.in_(productos), Sugerido.sucursal_id.in_(sucursales))
    ).all()
    mapa: dict[tuple[str, str], float] = {(p, s): d for p, s, d in rows if d}
    out: dict[tuple[str, str], int] = {}
    for par in pares:
        d = mapa.get(par)
        if d and d > 0:
            out[par] = max(1, math.ceil(float(d) * dias))
    return out


def _faltante_para_objetivo(
    objetivo: int, stock: float | None, transito: float | None, sugerido_sistema: float | None
) -> int:
    """Cuanto falta comprar para dejar el inventario en `objetivo` unidades.

    Descuenta TRES cosas: lo que hay, lo que viene en camino y lo que el sistema
    ya esta sugiriendo. Si no se descontara el sugerido del sistema, la manual se
    sumaria encima y se compraria dos veces para el mismo nivel.

    Devuelve 0 cuando el nivel ya esta cubierto (no hay nada que pedir).
    """
    cubierto = (stock or 0) + (transito or 0) + (sugerido_sistema or 0)
    return max(0, math.ceil(objetivo - cubierto))


def unidades_para_objetivo(
    db: Session, producto: str, sucursal_id: str, objetivo: int
) -> int | None:
    """Unidades que faltan para mantener `objetivo` en stock.

    Funciona aunque el producto NO este en el sugerido de esa sucursal, que es
    justo el caso donde mas se usa: un repuesto que el modelo no pide (sin
    demanda registrada) pero del que igual se quiere tener siempre unas unidades
    (campanas, VOR, pedidos especiales). Ahi el stock real sale de
    `stock_unificado` y el sugerido del sistema es 0, porque no lo esta pidiendo.

    Si no hay ningun registro de stock se asume 0 y se pide el nivel completo.
    Devuelve 0 cuando el nivel ya esta cubierto; None solo si el objetivo es invalido.
    """
    if objetivo <= 0:
        return None
    return detalle_objetivo(db, producto, sucursal_id, objetivo)["faltante"]


def detalle_objetivo(
    db: Session, producto: str, sucursal_id: str, objetivo: int
) -> dict:
    """Lo mismo que `unidades_para_objetivo`, pero mostrando de donde sale el numero.

    Es lo que necesita la pantalla para explicar por que faltan N unidades (o por
    que no falta ninguna): un total sin desglose obliga al usuario a confiar."""
    row = db.execute(
        select(
            Sugerido.stock_activo_suc,
            Sugerido.stock_en_transito_suc,
            Sugerido.total_sugerido_suc,
        ).where(Sugerido.producto == producto, Sugerido.sucursal_id == sucursal_id)
    ).first()
    if row:
        stock, transito, sistema = float(row[0] or 0), float(row[1] or 0), float(row[2] or 0)
        en_sugerido = True
    else:
        # Fuera del sugerido: el stock igual se conoce por bodega y el sistema no pide nada.
        stock, transito, sistema = _stock_en_sucursal(db, producto, sucursal_id), 0.0, 0.0
        en_sugerido = False
    return {
        "objetivo": objetivo,
        "stock": stock,
        "transito": transito,
        "sugerido_sistema": sistema,
        "cubierto": stock + transito + sistema,
        "faltante": _faltante_para_objetivo(objetivo, stock, transito, sistema),
        "en_sugerido": en_sugerido,
        # En que bodegas esta ese stock. Sin esto el usuario lee "hay 3" y no
        # tiene como comprobarlo: el producto puede no aparecer en la grilla
        # (pedir=No) y las columnas de stock por bodega vienen ocultas.
        "bodegas": _bodegas_de(db, producto, sucursal_id),
    }


def _bodegas_de(db: Session, producto: str, sucursal_id: str) -> list[dict]:
    """Desglose por bodega del stock de ese producto en la sucursal."""
    try:
        filas = db.execute(
            select(StockUnificado.bodega, StockUnificado.stock, StockUnificado.origen)
            .where(
                StockUnificado.producto == producto,
                StockUnificado.sucursal_id == sucursal_id,
                StockUnificado.stock != 0,
            )
            .order_by(StockUnificado.stock.desc())
        ).all()
        return [
            {"bodega": b or "(sin bodega)", "stock": float(s or 0), "origen": o}
            for b, s, o in filas
        ]
    except Exception:  # noqa: BLE001
        db.rollback()
        return []


def _stock_en_sucursal(db: Session, producto: str, sucursal_id: str) -> float:
    """Stock real del producto en esa sucursal segun `stock_unificado`.

    Tolerante: si la tabla no existe todavia, devuelve 0, que es el supuesto
    conservador (se pide el nivel completo)."""
    try:
        total = db.execute(
            select(func.coalesce(func.sum(StockUnificado.stock), 0)).where(
                StockUnificado.producto == producto,
                StockUnificado.sucursal_id == sucursal_id,
            )
        ).scalar()
        return float(total or 0)
    except Exception:  # noqa: BLE001
        db.rollback()
        return 0.0


def unidades_objetivo_por_par(
    db: Session, pares: list[tuple[str, str]], objetivo: int
) -> dict[tuple[str, str], int]:
    """Igual que `unidades_para_objetivo` para muchos pares, en una sola query.

    Solo devuelve los pares donde falta algo; los que ya estan en nivel quedan
    fuera del dict (el caller los reporta como omitidos).
    """
    if not pares or objetivo <= 0:
        return {}
    productos = {p for p, _ in pares}
    sucursales = {s for _, s in pares}
    rows = db.execute(
        select(
            Sugerido.producto,
            Sugerido.sucursal_id,
            Sugerido.stock_activo_suc,
            Sugerido.stock_en_transito_suc,
            Sugerido.total_sugerido_suc,
        ).where(Sugerido.producto.in_(productos), Sugerido.sucursal_id.in_(sucursales))
    ).all()
    datos = {(p, s): (st, tr, sug) for p, s, st, tr, sug in rows}
    out: dict[tuple[str, str], int] = {}
    for par in pares:
        d = datos.get(par)
        if d is None:
            continue
        falta = _faltante_para_objetivo(objetivo, *d)
        if falta > 0:
            out[par] = falta
    return out


def listar_por_ids(
    db: Session, ids: list[int], sucursales_permitidas: list[str] | None = None
) -> list[dict]:
    """Devuelve las filas con esos IDs en formato dict (compatible con excel_export).

    Aplica los mismos enriquecimientos que `listar`: suma de sugerencias manuales
    vigentes y campos del catalogo (reemplazos). Solo procesa IDs del sugerido
    del BI (id > 0); las filas sinteticas de catalogo/manuales tienen IDs
    negativos y no se incluyen aqui (caso raro en exports). Si se pasa
    `sucursales_permitidas`, restringe a esas sucursales (acceso por usuario)."""
    if not ids:
        return []
    ids_validos = [i for i in ids if i > 0]
    if not ids_validos:
        return []
    stmt = select(Sugerido).where(Sugerido.id.in_(ids_validos))
    if sucursales_permitidas is not None:
        stmt = stmt.where(Sugerido.sucursal_id.in_(sucursales_permitidas))
    rows = list(db.scalars(stmt).all())
    if not rows:
        return []

    # Manuales vigentes solo de los pares (producto, sucursal) involucrados.
    pares = {(r.producto, r.sucursal_id) for r in rows}
    productos_unicos = {p for p, _ in pares}
    stmt = (
        select(
            SugerenciaManual.producto,
            SugerenciaManual.sucursal_id,
            func.sum(SugerenciaManual.unidades).label("total"),
        )
        .where(SugerenciaManual.archivada.is_(False), _no_vencida())
        .where(SugerenciaManual.producto.in_(productos_unicos))
        .group_by(SugerenciaManual.producto, SugerenciaManual.sucursal_id)
    )
    manuales = {
        (p, s): int(t or 0)
        for p, s, t in db.execute(stmt).all()
        if t and int(t) > 0 and (p, s) in pares
    }

    # Preserva el orden enviado por el frontend (el del AG Grid, con sort visual).
    by_id = {r.id: r for r in rows}
    items: list[dict] = []
    for i in ids_validos:
        s = by_id.get(i)
        if not s:
            continue
        d = {c.name: getattr(s, c.name) for c in Sugerido.__table__.columns}
        d["origen"] = "sugerido"
        _aplicar_manuales_a_fila(d, manuales.get((s.producto, s.sucursal_id), 0))
        items.append(d)

    _enriquecer_con_catalogo(items, db)
    margen.agregar_margen(items)
    pedidos_service.agregar_a_filas(items, db)
    # Misma regla de negocio que aplica `listar`: stock cubre el mes + sin venta
    # el mes anterior -> pedir = No, salvo que tenga manual. Asi el export Excel
    # respeta lo mismo que ve la grilla.
    _aplicar_regla_stock_sin_venta(items, db, con_manual=set(manuales))
    return items


def detalle(db: Session, producto: str, sucursal_id: str) -> Sugerido | None:
    stmt = select(Sugerido).where(
        Sugerido.producto == producto, Sugerido.sucursal_id == sucursal_id
    )
    return db.scalars(stmt).first()


def ventas_12m(db: Session, producto: str, sucursal_id: str | None = None) -> dict:
    """Histórico de venta de un producto (últimos 12 meses).

    Devuelve DOS series:
    - `meses_general`: suma del producto en TODAS las sucursales (la venta total).
    - `meses_sucursal`: solo la sucursal del sugerido (vacío si no se entrega).

    Sale de `venta_historica`, que se carga de los Excel de Ventas. Antes salia de
    `venta_mensual`, que solo llenaba el Power BI Desktop: al retirarlo el grafico
    quedo congelado en la ultima corrida del BI, en las tres pantallas que lo usan
    (detalle de producto, ficha del catalogo y el chat).
    """

    def _consulta(suc: str | None) -> list[tuple[str, float]]:
        stmt = select(
            VentaHistorica.periodo,
            func.coalesce(func.sum(VentaHistorica.cantidad), 0).label("cantidad"),
        ).where(VentaHistorica.producto == producto)
        if suc:
            stmt = stmt.where(VentaHistorica.sucursal == suc)
        stmt = stmt.group_by(VentaHistorica.periodo).order_by(VentaHistorica.periodo.asc())
        return [(m, float(c)) for m, c in db.execute(stmt).all()]

    general = _consulta(None)[-12:]
    suc = _consulta(sucursal_id)[-12:] if sucursal_id else []

    return {
        "producto": producto,
        "sucursal_id": sucursal_id or "",
        "meses_general": [{"mes": m, "cantidad": c} for m, c in general],
        "meses_sucursal": [{"mes": m, "cantidad": c} for m, c in suc],
        "total_general": sum(c for _, c in general),
        "total_sucursal": sum(c for _, c in suc),
    }
