"""Logica de consulta del sugerido: aplica filtros, ordena, pagina y calcula KPIs.

NOTA Fase 0: aca NO se calcula el sugerido. Los valores ya vienen del Power BI.
Solo se filtra/agrega lo que ya esta cargado en la tabla.
"""
import math
import re
import unicodedata
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
    DimProducto,
    DimSucursal,
    ProductoCatalogo,
    StockUnificado,
    Sugerido,
    SugerenciaManual,
    VentaHistorica,
)
from ..schemas import SugeridoFiltros
from . import (
    instock_service,
    margen,
    pedidos_service,
    proveedor_producto_service,
    reemplazo_service,
    stock_service,
)

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


def _fila_pasa_columna(fila: dict, fc) -> bool:
    """Gemelo en Python de `_clausula_columna`, para las filas que NO salen del query.

    `listar` devuelve dos clases de fila: las que vienen del SELECT sobre
    `Sugerido` -que ya pasaron por `_apply_filters`- y las que se INYECTAN despues
    (sugerencias manuales, minimo InStock, catalogo). Esas ultimas nunca tocaron el
    WHERE, asi que sin esto se colaban aunque el usuario hubiera filtrado la
    columna: un comprador filtro Sucursal = Chillan y el Excel salio con 6
    sucursales, 78 filas de mas (10-08-2026).

    Tiene que replicar la MISMA semantica que la clausula SQL, incluido el
    centinela de blancos y el caso "destildo todo" (que no matchea nada).
    """
    campo = getattr(fc, "campo", None)
    if not campo or campo not in SORTABLE:
        return True
    valor = fila.get(campo)

    contiene = getattr(fc, "contiene", None)
    if contiene:
        return str(contiene).lower() in str("" if valor is None else valor).lower()

    valores = getattr(fc, "valores", None)
    if valores is None:
        return True
    incluir_blanco = BLANCO_SENTINEL in valores
    reales = [v for v in valores if v != BLANCO_SENTINEL]
    es_blanco = valor is None or valor == ""
    if es_blanco:
        return incluir_blanco
    if not reales:
        # Destildo todo salvo "(en blanco)": ninguna fila con valor entra.
        return False
    if _columna_numerica(campo):
        try:
            objetivo = float(valor)
        except (TypeError, ValueError):
            return False
        for v in reales:
            try:
                if float(v) == objetivo:
                    return True
            except (TypeError, ValueError):
                continue
        return False
    return str(valor) in {str(v) for v in reales}


def _filtrar_inyectadas(items: list[dict], f: SugeridoFiltros) -> list[dict]:
    """Deja solo las filas inyectadas que pasan los filtros de columna.

    Las que vienen del query ya estan filtradas; se reconocen porque `listar` las
    marca con `_inyectada`. Ese marcador se saca aca mismo para que no viaje al
    schema ni al Excel.
    """
    filtros = getattr(f, "filtros_columna", None) or []
    salida = []
    for it in items:
        inyectada = it.pop("_inyectada", False)
        if inyectada and not all(_fila_pasa_columna(it, fc) for fc in filtros):
            continue
        salida.append(it)
    return salida


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


def _manuales_por_par(db: Session) -> dict[tuple[str, str], int]:
    """Devuelve {(producto, sucursal_id): unidades vigentes} de sugerencias manuales.

    SIN filtrar por la busqueda, a proposito. Antes recibia `q` y filtraba por
    `producto ILIKE %q%`, pero la busqueda global del dashboard matchea ademas
    descripcion, sucursal, proveedor, marca, tipo de origen, ABC y abastece_cd:
    buscar "ACEITE MOTOR 5W20 SN" o "Rancagua" dejaba el diccionario VACIO y las
    unidades cargadas a mano desaparecian de filas que igual se estaban mostrando.
    Medido en produccion: `20 XO5W20Q1SP`/LINDEROS salia con 53 unidades buscando
    por codigo y con 17 buscando por su propia descripcion (las 36 manuales se
    evaporaban), y el KPI con q="Rancagua" reportaba 0 unidades manuales teniendo
    27 pares por 349 unidades.

    Son pocas filas (~100), asi que traerlas todas no cuesta nada. El acotamiento
    por busqueda se hace donde corresponde: sobre las filas que se AGREGAN
    (`solas` en `_resolver_manuales`), no sobre las unidades que se suman.
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
    por_par = _manuales_por_par(db)
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
    # Estas si se acotan a la busqueda: son filas que se AGREGAN, y meter en los
    # resultados de "aceite" una fila que no tiene nada que ver seria ruido. Se
    # mira el codigo, la glosa del catalogo y la sucursal, que es lo unico que
    # tiene una fila sintetica (la busqueda global mira mas columnas, pero una
    # fila sin sugerido no las tiene).
    q_text = (f.q or "").strip()
    if q_text and solas:
        like = f"%{q_text}%"
        por_glosa = {
            c.producto
            for c in db.scalars(
                select(ProductoCatalogo).where(
                    ProductoCatalogo.producto.in_({p for p, _ in solas}),
                    ProductoCatalogo.glosa.ilike(like),
                )
            ).all()
        }
        ql = q_text.lower()
        solas = {
            (p, s): u
            for (p, s), u in solas.items()
            if ql in p.lower() or ql in s.lower() or p in por_glosa
        }
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


def producto_existe(db: Session, producto: str) -> bool:
    """El codigo aparece en alguna fuente de datos: sugerido, catalogo o stock.

    Es la condicion minima para poder cargarle una sugerencia manual. Si el codigo
    no esta en ninguna, no hay de donde sacar descripcion, costo ni proveedor: la
    fila sale entera en blanco en la grilla y en el Excel, y nadie puede saber que
    producto era (paso en produccion con `74 1324409TBW0000`, tipeado a mano en el
    modal, que no existe en el maestro de 409k productos).

    Se mira tambien `stock_unificado` y no solo el catalogo: si hay stock cargado
    del producto, el producto existe aunque el maestro venga desfasado. Es el lado
    seguro del error -bloquear una compra legitima es peor que dejar pasar un
    codigo raro que ademas tiene stock-.
    """

    def _hay(modelo) -> bool:
        try:
            return bool(
                db.scalar(
                    select(func.count()).select_from(
                        select(modelo.id).where(modelo.producto == producto).limit(1).subquery()
                    )
                )
            )
        except Exception:
            # Tabla ausente (despliegue viejo): no bloquear por eso.
            return False

    return any(_hay(m) for m in (Sugerido, ProductoCatalogo, StockUnificado))


def _stock_de_pares(db: Session, pares: set[tuple[str, str]]) -> dict[tuple[str, str], float]:
    """Stock de `stock_unificado` para varios pares (producto, sucursal), en una query.

    Tolerante igual que `_stock_en_sucursal`: si la tabla no existe todavia, devuelve
    vacio y las filas quedan con el stock en '-' en vez de romper la pantalla.
    """
    if not pares:
        return {}
    cond = or_(
        *[
            and_(StockUnificado.producto == p, StockUnificado.sucursal_id == s)
            for p, s in pares
        ]
    )
    try:
        filas = db.execute(
            select(
                StockUnificado.producto,
                StockUnificado.sucursal_id,
                func.coalesce(func.sum(StockUnificado.stock), 0),
            )
            .where(cond)
            .group_by(StockUnificado.producto, StockUnificado.sucursal_id)
        ).all()
    except Exception:
        return {}
    return {(p, s): float(t or 0) for p, s, t in filas}


# Descripcion de reemplazo cuando el codigo no aparece en NINGUNA fuente (sugerido de
# otra sucursal, dim_producto, catalogo). Sin esto la fila sale entera en blanco y
# parece un bug de la grilla, cuando el problema es el codigo. Se aplica al final de
# `_completar_filas_sinteticas`, no al construir la fila: puesto antes taparia la
# descripcion real que el enriquecimiento si encuentra.
SIN_CATALOGO = "(codigo no encontrado en el catalogo)"


def _fila_sintetica_manual(
    producto: str,
    sucursal_id: str,
    unidades: int,
    cat: ProductoCatalogo | None,
    stock_suc: float | None = None,
    origen: str = "manual",
) -> dict:
    """Fila para un par (producto, sucursal) que hay que comprar pero NO esta en el
    sugerido del BI. Se enriquece con los datos del catalogo si estan disponibles.

    `origen` distingue de donde salio la orden de comprar: "manual" (alguien la
    cargo a mano) o "instock" (la regla del minimo de pauta). En los dos casos la
    fila es igual: el BI no la tiene y las unidades son las que hay que comprar.
    """
    return {
        "id": -abs(hash((producto, sucursal_id))) % (10**9),
        "origen": origen,
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
        "sugerido_suc": None,
        # El BI no tiene la fila, pero el stock de la sucursal si se conoce por
        # bodega: mostrarlo evita comprar sobre stock que ya esta ahi.
        "stock_activo_suc": stock_suc,
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


def _sin_tildes(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()


def _sucursales_instock(f: SugeridoFiltros) -> list[str]:
    """Sucursales con taller que el usuario puede ver y que la pantalla no filtro.

    Tres recortes, en orden: las que tienen taller (donde rige el minimo), las que
    el permiso del usuario le deja ver, y las que eligio en el filtro de sucursal.

    Ese ultimo filtro va por `nombre_sucursal` ("Curico") y aca tenemos el
    `sucursal_id` ("CURICO"), asi que se comparan en mayusculas y SIN TILDES: si el
    BI escribe "Curicó" o "Chillán", una comparacion literal dejaria esas dos
    sucursales fuera de la regla justo cuando el usuario las filtra.
    """
    permitidas = f.sucursales_permitidas
    elegidas = {
        _sin_tildes(s.strip().upper()) for s in (f.sucursales or []) if s and s.strip()
    }
    return [
        s
        for s in instock_service.SUCURSALES_INSTOCK
        if (permitidas is None or s in permitidas)
        and (not elegidas or _sin_tildes(s.upper()) in elegidas)
    ]


def _resolver_instock(db: Session, f: SugeridoFiltros, manuales: dict, man: dict) -> dict:
    """Que pares InStock no llegan al minimo y como entran en la pantalla actual.

    Mismo problema que `_resolver_manuales`, y por eso la misma estructura: la
    regla del minimo obliga a comprar filas que el sugerido del BI deja en cero, y
    esas filas las esconde el toggle "solo pedir" o directamente no existen en la
    tabla. Si no se inyectaran, la regla seria invisible justo en el caso que la
    justifica (repuesto de pauta clase D, sin venta y con stock cero).

    Tres destinos, calculados sobre el universo completo (no sobre la pagina):

    - `solo_unidades`: la fila ya esta contada en la pantalla —o la conto
      `_aporte_manuales`—; solo falta sumarle las unidades del minimo. No hay nada
      que inyectar: cuando la fila se pinte, `instock_service.aplicar` la sube.
    - `extras`: la fila existe en esta vista pero la escondio "solo pedir" o "solo
      nacionales". Se muestra la fila BUENA (con proveedor, ABC y stock).
    - `solas`: el par no esta en el sugerido en ninguna parte. Recien ahi se
      fabrica una fila desde el catalogo.

    Las que ya inyecto el camino de las sugerencias manuales quedan fuera de
    `extras`/`solas` (irian dos veces): entran en `solo_unidades`.
    """
    vacio: dict = {"cat": {}, "solo_unidades": {}, "extras": {}, "solas": {}, "costos": {}}
    cat = instock_service.catalogo(db)
    if not cat:
        return vacio
    sucursales = _sucursales_instock(f)
    if not sucursales:
        return vacio

    productos = set(cat)
    q_text = (f.q or "").strip()
    if q_text:
        # Con busqueda, la pantalla muestra lo que matchea el texto: inyectar todos
        # los repuestos de pauta encima seria ruido. Mismo criterio que las manuales.
        productos = {p for p in productos if q_text.lower() in p.lower()}
        if not productos:
            return vacio

    # Datos del BI para los pares candidatos, en una query.
    filas = db.execute(
        select(
            Sugerido.producto,
            Sugerido.sucursal_id,
            Sugerido.stock_activo_suc,
            Sugerido.stock_en_transito_suc,
            Sugerido.total_sugerido_suc,
            Sugerido.costo_unitario,
        ).where(Sugerido.producto.in_(productos), Sugerido.sucursal_id.in_(sucursales))
    ).all()
    datos = {(p, s): (st, tr, sug, costo) for p, s, st, tr, sug, costo in filas}

    # Stock real de los pares que el BI no tiene (ahi el sugerido del sistema es 0).
    sin_fila = {
        (p, s) for p in productos for s in sucursales if (p, s) not in datos
    }
    stock_suelto = _stock_de_pares(db, sin_fila) if sin_fila else {}

    faltantes: dict[tuple[str, str], int] = {}
    costos: dict[tuple[str, str], float] = {}
    for p in productos:
        minimo = cat[p]["minimo"]
        for s in sucursales:
            par = (p, s)
            manual = manuales.get(par, 0)
            if par in datos:
                st, tr, sug, costo = datos[par]
                falta = instock_service.faltante(minimo, st, tr, float(sug or 0) + manual)
                costos[par] = float(costo or 0)
            else:
                falta = instock_service.faltante(
                    minimo, stock_suelto.get(par), 0, manual
                )
            if falta > 0:
                faltantes[par] = falta
    if not faltantes:
        return vacio

    pares = set(faltantes)
    cols = select(Sugerido.producto, Sugerido.sucursal_id)

    def _consultar(stmt) -> set[tuple[str, str]]:
        stmt = stmt.where(Sugerido.producto.in_({p for p, _ in pares}))
        return {(p, s) for p, s in db.execute(stmt).all()} & pares

    en_vista = _consultar(_apply_filters(cols, f))
    amplio = f.model_copy(update={"solo_pedir": False, "solo_nacionales": False})
    extras = _consultar(_apply_filters(cols, amplio)) - en_vista
    en_tabla = _consultar(_apply_alcance(cols, f))

    # Las filas que las sugerencias manuales ya inyectan: no se repiten.
    ya_inyectados = set(man.get("extras") or ()) | set(man.get("solas") or ())
    solo_unidades = {par: faltantes[par] for par in (en_vista | ya_inyectados) & pares}
    extras = {par: faltantes[par] for par in extras - ya_inyectados}
    # Las filas sueltas son compra de sucursal: no tienen sentido en las pestanias
    # del CD ni de distribucion, que miran otro tramo del proceso.
    vista = (f.vista or "todas").lower()
    solas = (
        {
            par: faltantes[par]
            for par in pares - en_tabla - ya_inyectados
        }
        if vista in ("todas", "sucursales")
        else {}
    )
    return {
        "cat": cat,
        "solo_unidades": solo_unidades,
        "extras": extras,
        "solas": solas,
        "costos": costos,
    }


_PREFIJO_SUCURSAL = re.compile(r"^\d+\s+")


def normalizar_sucursal(nombre: str | None) -> str | None:
    """"02 LINDEROS" -> "LINDEROS". El resto vuelve igual.

    `venta_historica.sucursal` sale tal cual del Excel de Ventas, y ahi el mismo
    lugar aparece con y sin el codigo por delante -a veces en el MISMO archivo-.
    `sugerido.sucursal_id` en cambio usa siempre la forma corta, asi que cruzar
    las dos tablas por igualdad pierde la mayor parte de la venta.
    """
    if not nombre:
        return nombre
    return _PREFIJO_SUCURSAL.sub("", nombre.strip()) or nombre.strip()


def misma_sucursal(sucursal_id: str):
    """Condicion SQL que acepta "LINDEROS" y "02 LINDEROS" como el mismo lugar.

    Se escapan los comodines por si un dia un sucursal_id trae % o _. El patron
    NO lleva `%` al final a proposito: asi "% CHILLAN" no se come
    "10 CHILLAN VIEJO", que es otra sucursal.
    """
    seguro = sucursal_id.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
    return or_(
        VentaHistorica.sucursal == sucursal_id,
        VentaHistorica.sucursal.like(f"% {seguro}", escape="\\"),
    )


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
    items: list[dict], db: Session, protegidos: set[tuple[str, str]] | None = None
) -> None:
    """Regla de negocio: si un producto tiene stock activo de sucursal >= demanda
    mensual Y no tuvo venta en el mes calendario anterior, no se sugiere comprar.

    `protegidos` son los pares donde ya hay una decision explicita de comprar: los
    que tienen sugerencia manual vigente y los repuestos InStock bajo el minimo de
    pauta. La regla NO los toca. Cargar una manual (o dejar un repuesto de pauta
    bajo el minimo) es decir "compra esto igual"; que una regla automatica lo
    volviera a marcar "no pedir" seria pasar por encima de esa decision (y ademas
    dejaria la fila fuera del dashboard, que filtra por "solo pedir").

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
    # Suma vendida el mes anterior por par. NO se filtra por sucursal en la
    # consulta: `venta_historica.sucursal` trae el mismo lugar en dos formas
    # ("02 LINDEROS" y "LINDEROS") y comparar por igualdad se come la mayoria.
    # Medido en el respaldo de julio-2026: el 76% de las filas viene con prefijo
    # numerico, y en Talca y Chillan la forma corta NO EXISTE. Con el filtro
    # exacto esas dos sucursales daban venta CERO y la regla marcaba "No pedir"
    # en todo lo que tuviera stock, escondiendolo del dashboard.
    # Se agrupa en Python normalizando el nombre; las filas ya vienen acotadas
    # por producto y periodo, asi que no se trae de mas.
    rows = db.execute(
        select(
            VentaHistorica.producto,
            VentaHistorica.sucursal,
            func.coalesce(func.sum(VentaHistorica.cantidad), 0).label("c"),
        )
        .where(
            VentaHistorica.producto.in_(productos),
            VentaHistorica.periodo == mes,
        )
        .group_by(VentaHistorica.producto, VentaHistorica.sucursal)
    ).all()
    venta_map: dict[tuple[str, str], float] = {}
    for p, s, c in rows:
        clave = (p, normalizar_sucursal(s))
        if clave[1] in sucursales:
            venta_map[clave] = venta_map.get(clave, 0.0) + float(c or 0)

    for it in items:
        p = it.get("producto")
        s = it.get("sucursal_id")
        if not p or not s:
            continue
        if protegidos and (p, s) in protegidos:
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


# Columna de stock por bodega del sugerido que corresponde a cada sucursal.
# Espejo de las columnas fisicas del modelo (ver models/sugerido.py): si se agrega
# una sucursal alla, hay que agregarla aca tambien.
COLUMNA_STOCK_SUCURSAL = {
    "LINDEROS": "stock_linderos",
    "CURICO": "stock_curico",
    "TALCA": "stock_talca",
    "RANCAGUA": "stock_rancagua",
    "DIEZ DE JULIO (2)": "stock_diez_de_julio_2",
    "CHILLAN": "stock_chillan",
    "CD REPUESTOS": "stock_cd_repuestos",
    "BRASIL 18": "stock_brasil_18",
    "PLACILLA": "stock_placilla",
    "CHILLAN VIEJO": "stock_chillan_viejo",
    "TALCA (2)": "stock_talca_2",
}

# Campos que describen al PRODUCTO, no a la sucursal: se pueden copiar desde la
# fila del mismo producto en cualquier otra sucursal. Los que dependen de la
# sucursal (clase ABC local, demanda, stock, sugerido, lead time efectivo) NO
# entran aca: copiarlos seria inventar datos de una sucursal con los de otra.
CAMPOS_DE_PRODUCTO = (
    "descripcion", "proveedor", "filtro1_final", "tipo_origen", "es_importado",
    "unidad_medida", "clasificacion_abc_agregada", "lead_time_dias", "lt_origen",
    "costo_unitario", "reemplazos", "empresa",
) + tuple(c.name for c in Sugerido.__table__.columns if c.name.startswith("precio_"))

# Filas que NO vienen del sugerido del BI y por lo tanto salen con las columnas
# vacias si nadie las completa.
ORIGENES_SINTETICOS = ("manual", "instock", "catalogo")


def _completar_filas_sinteticas(items: list[dict], db: Session) -> None:
    """Rellena las columnas de las filas que el sugerido del BI no trae.

    Una sugerencia manual sobre un producto que el modelo no pide (o un repuesto
    InStock sin fila) salia practicamente en blanco: sin proveedor, sin marca, sin
    clase, sin precios y sin stock por bodega. En la grilla y en el Excel se veia
    como un error, y el comprador no tenia con que decidir.

    De donde sale cada cosa, en orden de confianza:

    1. **Otra fila del MISMO producto en el sugerido** (cualquier sucursal): es la
       mejor fuente para lo que describe al producto —proveedor, marca, si es
       importado, precios de lista—, porque ya paso por el motor. Lo que depende de
       la sucursal no se copia (ver `CAMPOS_DE_PRODUCTO`).
    2. **`dim_producto`**: marca, unidad, costo y proveedor del maestro del motor.
    3. **`proveedor_producto`**: a quien se le compra, deducido de las ordenes de
       compra historicas. Cubre lo que las dos anteriores no: un producto que no
       esta en el sugerido de hoy tampoco esta en `dim_producto` (se llena con lo
       que trae el CSV del sugerido), asi que hasta aca la celda quedaba vacia
       aunque hubiera 78 OC a FORD. Y sin proveedor la linea no entra a ningun
       carro de compra (`compras_service` filtra por `proveedor IS NOT NULL`).
    4. **`producto_catalogo`**: glosa, procedencia, unidad, costo y reemplazos.
    5. **`stock_unificado`**: el stock real por sucursal, que llena tanto las
       columnas por bodega como el stock de la propia sucursal de la fila.

    Nunca pisa un valor que la fila ya traiga. Muta `items` in-place.
    """
    filas = [
        it for it in items
        if it.get("origen") in ORIGENES_SINTETICOS and it.get("producto")
    ]
    if not filas:
        return
    productos = {it["producto"] for it in filas}

    def _rellenar(fila: dict, campo: str, valor) -> None:
        if valor is not None and fila.get(campo) is None:
            fila[campo] = valor

    # 1) Fila del mismo producto en otra sucursal (la de mayor sugerido, que suele
    #    ser la mas representativa).
    desde_sugerido: dict[str, Sugerido] = {}
    for s in db.scalars(
        select(Sugerido)
        .where(Sugerido.producto.in_(productos))
        .order_by(Sugerido.producto, Sugerido.total_sugerido_suc.desc().nullslast())
    ).all():
        desde_sugerido.setdefault(s.producto, s)

    # 2) dim_producto (maestro del motor).
    try:
        dim = {
            d.producto: d
            for d in db.scalars(
                select(DimProducto).where(DimProducto.producto.in_(productos))
            ).all()
        }
    except Exception:  # noqa: BLE001 - tabla ausente en despliegues viejos
        db.rollback()
        dim = {}

    # 3) proveedor deducido de las OC (cubre lo que no esta en el sugerido).
    try:
        prov_deducido = proveedor_producto_service.mapa(db, productos)
    except Exception:  # noqa: BLE001 - tabla ausente en despliegues viejos
        db.rollback()
        prov_deducido = {}

    # 4) catalogo maestro.
    cat = {
        c.producto: c
        for c in db.scalars(
            select(ProductoCatalogo).where(ProductoCatalogo.producto.in_(productos))
        ).all()
    }

    # 5) stock real por sucursal, en una query.
    stock: dict[str, dict[str, float]] = {}
    try:
        for p, suc, total in db.execute(
            select(
                StockUnificado.producto,
                StockUnificado.sucursal_id,
                func.coalesce(func.sum(StockUnificado.stock), 0),
            )
            .where(StockUnificado.producto.in_(productos))
            .group_by(StockUnificado.producto, StockUnificado.sucursal_id)
        ).all():
            stock.setdefault(p, {})[suc or ""] = float(total or 0)
    except Exception:  # noqa: BLE001
        db.rollback()

    for fila in filas:
        p = fila["producto"]
        base = desde_sugerido.get(p)
        if base is not None:
            for campo in CAMPOS_DE_PRODUCTO:
                _rellenar(fila, campo, getattr(base, campo, None))
        d = dim.get(p)
        if d is not None:
            _rellenar(fila, "descripcion", d.descripcion)
            _rellenar(fila, "filtro1_final", d.filtro1_final)
            _rellenar(fila, "unidad_medida", d.unidad_medida)
            _rellenar(fila, "costo_unitario", d.costo_unitario)
            _rellenar(fila, "proveedor", d.proveedor)
            _rellenar(fila, "es_importado", d.es_importado)
        _rellenar(fila, "proveedor", prov_deducido.get(p))
        c = cat.get(p)
        if c is not None:
            _rellenar(fila, "descripcion", c.glosa)
            _rellenar(fila, "tipo_origen", c.procedencia)
            _rellenar(fila, "unidad_medida", c.unidad)
            _rellenar(fila, "costo_unitario", c.costo)
            _rellenar(fila, "reemplazos", c.reemplazo)

        por_suc = stock.get(p, {})
        for suc, columna in COLUMNA_STOCK_SUCURSAL.items():
            if suc in por_suc:
                _rellenar(fila, columna, int(por_suc[suc]))
        _rellenar(fila, "stock_en_cd", por_suc.get("CD REPUESTOS"))
        if fila.get("sucursal_id"):
            _rellenar(fila, "stock_activo_suc", por_suc.get(fila["sucursal_id"]))

        # Valorizar ahora que puede haber aparecido un costo.
        if fila.get("costo_unitario") and fila.get("total_valor_sugerido_clp") is None:
            fila["total_valor_sugerido_clp"] = (
                float(fila.get("total_sugerido_suc") or 0) * float(fila["costo_unitario"])
            )

        # Ultimo recurso: ninguna de las cuatro fuentes conoce el codigo. Decirlo es
        # mejor que dejar la celda vacia, que se lee como un error de la grilla
        # cuando en realidad el codigo no existe (paso con `74 1324409TBW0000`,
        # tipeado a mano antes de que el alta lo validara).
        if fila.get("descripcion") is None:
            fila["descripcion"] = SIN_CATALOGO


def contexto_de_pares(
    db: Session, pares: list[tuple[str, str]], unidades: list[float] | None = None
) -> list[dict]:
    """Datos del producto y de la sucursal para una lista de (producto, sucursal).

    Lo usa la pantalla de sugerencias manuales: hasta ahora listaba el codigo
    pelado ("74 1324409TBW0000") y habia que ir al catalogo a ver que repuesto era.

    Reutiliza `_completar_filas_sinteticas`, que es el mismo camino por el que la
    grilla llena esas filas: asi la lista y el sugerido muestran exactamente el
    mismo proveedor, costo y stock, en vez de dos verdades distintas.

    Devuelve una lista alineada con `pares` (misma posicion, mismo largo).
    """
    if not pares:
        return []
    filas = [
        {
            "origen": "manual",
            "producto": p,
            "sucursal_id": s,
            "total_sugerido_suc": float(unidades[i]) if unidades else None,
        }
        for i, (p, s) in enumerate(pares)
    ]
    # Stock y clase de la fila EXACTA del par, cuando el sugerido la tiene. Va antes
    # del relleno generico porque ese copia datos del producto en otra sucursal, y
    # el stock es de esta: tiene que ser el mismo numero que muestra la grilla.
    propias = {
        (s.producto, s.sucursal_id): s for s in _filas_de_pares(db, set(pares))
    }
    for fila in filas:
        propia = propias.get((fila["producto"], fila["sucursal_id"]))
        if propia is not None:
            fila["stock_activo_suc"] = propia.stock_activo_suc
            fila["clasificacion_abc"] = propia.clasificacion_abc
    _completar_filas_sinteticas(filas, db)
    # Nombre de la sucursal ("Curicó" en vez de "CURICO").
    try:
        nombres = {
            s: n or s
            for s, n in db.execute(
                select(DimSucursal.sucursal_id, DimSucursal.nombre).where(
                    DimSucursal.sucursal_id.in_({s for _p, s in pares})
                )
            ).all()
        }
    except Exception:  # noqa: BLE001
        db.rollback()
        nombres = {}
    for fila, (_p, s) in zip(filas, pares):
        fila["nombre_sucursal"] = nombres.get(s, s)
    return filas


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

    # Repuestos de pauta bajo el minimo (regla InStock). Se resuelve DESPUES de las
    # manuales porque el minimo descuenta lo que la manual ya pidio.
    ins = _resolver_instock(db, f, manuales, man)

    # Los totales NO dependen de la pagina; las filas de abajo se agregan solo en
    # la primera: van despues de paginar, asi que repetirlas en cada pagina seria
    # mostrarlas N veces (y hacer que el total variara con el tamano de pagina).
    total_extras = len(man["extras"])
    total_manuales_solas = len(man["solas"])
    total_instock = len(ins["extras"]) + len(ins["solas"])

    # Filas reales que "solo pedir"/"solo nacionales" escondia. La manual es una
    # orden explicita de comprar: gana sobre el toggle, y se muestra la fila BUENA
    # (con proveedor, ABC y stock), no una en blanco.
    if man["extras"] and page == 1:
        items.extend(
            {**_a_dict(s), "_inyectada": True}
            for s in _filas_de_pares(db, man["extras"])
        )

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
        stock_pares = _stock_de_pares(db, set(man["solas"]))
        for (p, s), u in man["solas"].items():
            items.append(
                {**_fila_sintetica_manual(p, s, u, cat_map.get(p), stock_pares.get((p, s))),
                 "_inyectada": True}
            )

    # Lo mismo para la regla InStock: la fila real cuando existe, una sintetica
    # cuando el BI no tiene el par. Un repuesto de pauta bajo el minimo hay que
    # comprarlo aunque el modelo no lo pida; si no se mostrara, el mínimo seria
    # una regla invisible.
    if (ins["extras"] or ins["solas"]) and page == 1:
        if ins["extras"]:
            items.extend(
                {**_a_dict(s), "_inyectada": True}
                for s in _filas_de_pares(db, set(ins["extras"]))
            )
        if ins["solas"]:
            cat_ins = {
                c.producto: c
                for c in db.scalars(
                    select(ProductoCatalogo).where(
                        ProductoCatalogo.producto.in_({p for p, _ in ins["solas"]})
                    )
                ).all()
            }
            stock_ins = _stock_de_pares(db, set(ins["solas"]))
            for (p, s), u in ins["solas"].items():
                fila = _fila_sintetica_manual(
                    p, s, u, cat_ins.get(p), stock_ins.get((p, s)), origen="instock"
                )
                # Ya viene con el faltante adentro: se deja anotado para que la
                # columna "InStock agregado" explique de donde salio el numero (y
                # para que `aplicar` no lo vuelva a sumar).
                fila["instock_agregado"] = float(u)
                fila["_inyectada"] = True
                items.append(fila)

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
            # Omitir productos que ya aparecieron como filas sinteticas (manuales o
            # InStock): la fila del catalogo seria la misma sin sucursal ni unidades.
            ya_sinteticos = {p for (p, _) in manuales} | {p for (p, _) in ins["solas"]}
            catalogo_items = [c for c in catalogo_items if c.producto not in ya_sinteticos]
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
                    r["_inyectada"] = True
                items.extend(rows_cat)
        except Exception:
            total_cat = 0

    # Enriquecer con columnas del catalogo (reemplazos, etc.) que no viven en
    # el modelo Sugerido. Las filas que ya vienen del catalogo o sinteticas no
    # se tocan: el helper salta cuando ya hay 'reemplazos' en la fila.
    _enriquecer_con_catalogo(items, db)
    # Las filas que el sugerido del BI no trae (manuales, InStock, catalogo) salen
    # con casi todo en blanco: se completan con lo que se sepa del producto en
    # otras fuentes. Va antes del margen y de InStock porque de aca puede salir el
    # costo y el stock, que los dos necesitan.
    _completar_filas_sinteticas(items, db)
    # Regla InStock (jul-2026): marca los repuestos de pauta y completa el minimo
    # en las sucursales con taller. Va antes del margen para que el margen del
    # sugerido incluya las unidades que agrega la regla.
    instock_service.aplicar(items, ins["cat"])
    margen.agregar_margen(items)
    pedidos_service.agregar_a_filas(items, db)

    # Regla de negocio (jun-2026): si tiene stock para su demanda mensual y no
    # tuvo venta el mes anterior, no se sugiere comprar. Las que tienen manual o
    # estan bajo el minimo InStock quedan fuera: ahi ya hubo una decision
    # explicita de comprar.
    protegidos = set(manuales) | set(ins["solo_unidades"]) | set(ins["extras"]) | set(ins["solas"])
    _aplicar_regla_stock_sin_venta(items, db, protegidos=protegidos)

    _agregar_reemplazo_ford(items, db)

    # Las filas inyectadas (manuales, InStock, catalogo) nunca pasaron por el WHERE
    # con los filtros de columna: se filtran aca. Va al final para que lo hagan ya
    # completas -- el margen, InStock y las manuales llenan campos por los que el
    # usuario puede estar filtrando.
    antes_de_filtrar = len(items)
    items = _filtrar_inyectadas(items, f)
    descartadas = antes_de_filtrar - len(items)

    total_final = total + total_extras + total_manuales_solas + total_instock + total_cat
    # El total tiene que cuadrar con lo que se devuelve: si no, el Excel trae N
    # filas y el contador de la pantalla dice otra cosa.
    return items, max(total_final - descartadas, len(items))


def _agregar_reemplazo_ford(items: list[dict], db: Session) -> None:
    """Marca las filas cuyo codigo FORD dio de baja.

    Se cruza contra la tabla `reemplazo_ford` en vez de guardar la columna en
    `sugerido`: esa tabla se borra y se reinserta entera en cada carga, asi que
    duplicar el dato ahi obligaria a que el motor lo mandara en el CSV y a
    mantener las dos copias sincronizadas. Aca es un join sobre la pagina que se
    esta mostrando (50 filas), no sobre las 18.000.
    """
    if not items:
        return
    mapa = reemplazo_service.por_producto(
        db, {str(i.get("producto")) for i in items if i.get("producto")}
    )
    for it in items:
        r = mapa.get(str(it.get("producto") or ""))
        # Solo interesa la baja, no la direccion inversa: la columna responde
        # "¿este codigo sigue vivo?".
        it["reemplazado_por_ford"] = (
            (r.get("reemplazado_por") or r.get("reemplazado_por_ford")) if r else None
        )
        # La cadena completa, para ver el historico y no solo el ultimo salto.
        # Viene en codigo de FORD ("MB3Z/19N619/C/ > MB3Z/19N619/A/"), que NO es
        # el de la grilla: por eso la columna lo dice en su encabezado.
        it["cadena_ford"] = r.get("cadena") if r else None
        # Cuando se le pregunto al portal. Sin esto un dato de hace tres semanas
        # se ve igual que uno de hoy.
        it["reemplazo_extraido_en"] = r.get("extraido_en") if r else None
        # El veredicto del portal sobre la cadena: cual candidato quedo descartado
        # por no estar activo/pedible/con precio, si hubo bifurcacion, o si ningun
        # codigo sirve. El extractor ya elige el sucesor PEDIBLE -esa es la regla 3
        # y vive en `runner.py::_sirve`- pero hasta ahora ese razonamiento solo se
        # veia en la ficha. Aca llega a la grilla, que es donde se decide la compra.
        it["reemplazo_aviso"] = r.get("aviso") if r else None
        # FORD nombra un vigente que Curifor NO tiene en el maestro. El motor no
        # puede colgar el grupo de un codigo que el ERP no conoce, asi que la fila
        # sigue saliendo con el viejo; la pantalla lo marca "POR CREAR" para que se
        # vea que ese numero hay que darlo de alta antes de poder pedirlo.
        #
        # Se manda como bandera y no se deduce en el front mirando si el codigo
        # trae barras: el formato es una casualidad del proveedor, no un contrato.
        #
        # Exige `sucesor_confirmado`, y esa es la parte que importa. Cuando FORD
        # avisa "ningun codigo de la cadena quedo activo, pedible y con precio",
        # igual deja un numero escrito en `reemplazado_por_ford` -el ultimo de la
        # cadena- pero ese codigo NO se puede comprar. Marcarlo "POR CREAR" mandaria
        # a Repuestos a dar de alta un numero muerto. Medido el 24-08-2026: de 16
        # productos que traen un vigente ajeno al maestro, 12 estan en ese caso.
        it["vigente_por_crear"] = bool(
            r
            and not r.get("reemplazado_por")
            and r.get("reemplazado_por_ford")
            and r.get("sucesor_confirmado")
        )
    _resolver_padre_sin_stock(items, db)


def _resolver_padre_sin_stock(items: list[dict], db: Session) -> None:
    """El codigo viejo solo representa al grupo mientras quede stock que vender.

    Cuando FORD nombra un vigente que Curifor no tiene en el maestro, el ERP no
    puede comprar ese numero, asi que la fila sigue colgando del codigo viejo. Eso
    es correcto MIENTRAS quede stock: hay unidades que despachar y es el codigo con
    el que estan.

    Sin stock ya no hay nada que representar: mostrar un codigo muerto esconde lo
    unico accionable, que es pedirle a Repuestos que cree el vigente. Por eso ahi
    la pantalla pasa a mostrar el codigo de FORD con la pegatina.

    Se mira el stock OPERATIVO. Una unidad en Bodega Dañados no se le vende a
    nadie: `19 DG1Z8501D` tenia stock 1 y era eso, y contarlo habria dejado el
    codigo viejo a la vista sin que hubiera nada que despachar.
    """
    candidatos = [i for i in items if i.get("vigente_por_crear")]
    if not candidatos:
        return
    stock = stock_service.stock_operativo_por_producto(
        db, sorted({str(i["producto"]) for i in candidatos})
    )
    for i in candidatos:
        if stock.get(str(i["producto"]), 0) > 0:
            i["vigente_por_crear"] = False


def _aporte_manuales(db: Session, f: SugeridoFiltros, man: dict | None = None) -> dict:
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

    `man` es la resolucion ya calculada (`_resolver_manuales`); se puede pasar para
    no repetir las queries cuando el caller tambien la necesita.
    """
    vacio = {"unidades": 0.0, "valor_clp": 0.0, "manual_unidades": 0.0, "manual_clp": 0.0,
             "filas": 0, "productos": set()}
    if man is None:
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


def _aporte_instock(db: Session, f: SugeridoFiltros, ins: dict) -> dict:
    """Cuanto suma la regla InStock sobre los KPIs. Espeja lo que hace `listar`.

    Misma logica de tres casos que `_aporte_manuales`, con la diferencia de que
    aca lo que se suma es el FALTANTE para llegar al minimo, no unidades pedidas
    a mano:

    - `solo_unidades`: la fila ya la conto alguien (el SQL base o el aporte de las
      manuales); solo se agregan las unidades del minimo.
    - `extras`: fila real que escondia "solo pedir"; entra entera (su sugerido mas
      el faltante) y suma una fila y un producto.
    - `solas`: fila propia, valorizada con el costo del catalogo.
    """
    vacio = {"unidades": 0.0, "valor_clp": 0.0, "instock_unidades": 0.0,
             "instock_clp": 0.0, "filas": 0, "productos": set()}
    if not (ins["solo_unidades"] or ins["extras"] or ins["solas"]):
        return vacio

    unidades = valor = 0.0        # lo que hay que SUMARLE a los totales base
    instock_u = instock_clp = 0.0  # de eso, cuanto pone la regla del minimo
    filas = 0
    productos: set[str] = set()

    # Costos. Tienen que salir de las MISMAS fuentes y en el mismo orden que usa
    # `_completar_filas_sinteticas` para la grilla, o las tarjetas dejan de cuadrar
    # con la tabla: una fila sin fila propia en el BI igual hereda el costo del
    # mismo producto en otra sucursal, y el KPI tiene que valorizarla igual.
    costos = dict(ins["costos"])
    pares_valorizar = set(ins["solo_unidades"]) | set(ins["solas"])
    sin_costo = {par[0] for par in pares_valorizar if not costos.get(par)}
    costo_producto: dict[str, float] = {}
    if sin_costo:
        # Mismo criterio que la grilla: la fila del producto con mayor sugerido.
        for prod, costo in db.execute(
            select(Sugerido.producto, Sugerido.costo_unitario)
            .where(Sugerido.producto.in_(sin_costo))
            .order_by(Sugerido.producto, Sugerido.total_sugerido_suc.desc().nullslast())
        ).all():
            costo_producto.setdefault(prod, float(costo or 0))
        for c in db.scalars(
            select(ProductoCatalogo).where(ProductoCatalogo.producto.in_(sin_costo))
        ).all():
            if not costo_producto.get(c.producto):
                costo_producto[c.producto] = float(c.costo or 0)

    def _costo(par: tuple[str, str]) -> float:
        return costos.get(par) or costo_producto.get(par[0], 0.0)

    for par, falta in ins["solo_unidades"].items():
        clp = falta * _costo(par)
        unidades += falta
        valor += clp
        instock_u += falta
        instock_clp += clp

    for s in _filas_de_pares(db, set(ins["extras"])):
        falta = ins["extras"][(s.producto, s.sucursal_id)]
        clp = falta * float(s.costo_unitario or 0)
        unidades += float(s.total_sugerido_suc or 0) + falta
        valor += float(s.total_valor_sugerido_clp or 0) + clp
        instock_u += falta
        instock_clp += clp
        filas += 1
        productos.add(s.producto)

    for par, falta in ins["solas"].items():
        clp = falta * _costo(par)
        unidades += falta
        valor += clp
        instock_u += falta
        instock_clp += clp
        filas += 1
        productos.add(par[0])

    return {
        "unidades": unidades,
        "valor_clp": valor,
        "instock_unidades": instock_u,
        "instock_clp": instock_clp,
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
    resolucion = _resolver_manuales(db, f)
    man = _aporte_manuales(db, f, resolucion)
    # Idem con la regla InStock: lo que agrega para llegar al minimo de pauta.
    ins = _aporte_instock(
        db, f, _resolver_instock(db, f, resolucion["por_par"], resolucion)
    )

    # Productos: hay que unir los conjuntos (una manual o un repuesto de pauta puede
    # traer un producto que el sugerido no tiene en esta vista). Solo se materializa
    # la lista si hace falta.
    extra_productos = man["productos"] | ins["productos"]
    if extra_productos:
        productos = {p for (p,) in db.execute(select(distinct(base.c.producto))).all()}
        n_productos = len(productos | extra_productos)
    else:
        n_productos = db.scalar(select(func.count(distinct(base.c.producto)))) or 0

    return {
        "total_sugerido": float(total_sugerido) + man["unidades"] + ins["unidades"],
        "valor_total_clp": float(valor_total) + man["valor_clp"] + ins["valor_clp"],
        "n_productos": int(n_productos),
        "n_proveedores": int(n_proveedores),
        "n_filas": int(n_filas) + man["filas"] + ins["filas"],
        # Desglose para mostrar entre parentesis cuanto viene de sugerencias manuales.
        "total_sugerido_manual": man["manual_unidades"],
        "valor_manual_clp": man["manual_clp"],
        # Idem para la regla InStock (minimo de repuestos de pauta).
        "total_sugerido_instock": ins["instock_unidades"],
        "valor_instock_clp": ins["instock_clp"],
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


def _objetivo_dias(demanda_diaria: float, dias: int) -> int:
    """Unidades necesarias para cubrir `dias` de venta. Minimo 1."""
    return max(1, math.ceil(demanda_diaria * dias))


def unidades_desde_dias(
    db: Session, producto: str, sucursal_id: str, dias: int
) -> int | None:
    """Unidades que FALTAN para tener `dias` de inventario cubiertos.

    El nivel a alcanzar es ceil(dias * demanda_diaria), y de ahi se descuenta lo
    que ya esta cubierto: stock, transito y lo que el sistema ya sugiere. Un SKU
    con stock de sobra devuelve 0 en vez de sumar los dias completos encima: pedir
    "30 dias" sobre un producto que ya tiene para 50 era comprar de mas.

    Devuelve None si el producto+sucursal no esta en el sugerido o no tiene
    demanda diaria > 0: sin demanda no hay como convertir dias a unidades (en ese
    caso el caller decide: omitir o avisar).
    """
    if dias <= 0:
        return None
    d = detalle_dias(db, producto, sucursal_id, dias)
    return None if d is None else d["faltante"]


def unidades_por_par(
    db: Session, pares: list[tuple[str, str]], dias: int
) -> dict[tuple[str, str], int]:
    """Calcula unidades para muchos pares de una sola query.

    Misma regla que `unidades_desde_dias`: el nivel por dias menos lo ya cubierto.
    Quedan fuera del dict los pares sin demanda diaria y los que ya tienen esos
    dias cubiertos (el caller los reporta como omitidos).
    """
    if not pares or dias <= 0:
        return {}
    productos = {p for p, _ in pares}
    sucursales = {s for _, s in pares}
    rows = db.execute(
        select(
            Sugerido.producto,
            Sugerido.sucursal_id,
            Sugerido.demanda_diaria,
            Sugerido.stock_activo_suc,
            Sugerido.stock_en_transito_suc,
            Sugerido.total_sugerido_suc,
        ).where(Sugerido.producto.in_(productos), Sugerido.sucursal_id.in_(sucursales))
    ).all()
    datos = {(p, s): (dem, st, tr, sug) for p, s, dem, st, tr, sug in rows}
    out: dict[tuple[str, str], int] = {}
    for par in pares:
        fila = datos.get(par)
        if not fila or not fila[0] or float(fila[0]) <= 0:
            continue
        falta = _faltante_para_objetivo(
            _objetivo_dias(float(fila[0]), dias), *fila[1:]
        )
        if falta > 0:
            out[par] = falta
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


def detalle_dias(
    db: Session, producto: str, sucursal_id: str, dias: int
) -> dict | None:
    """Lo mismo que `detalle_objetivo`, pero con el nivel expresado en dias de venta.

    Devuelve las mismas claves (por eso el desglose de la pantalla sirve para los
    dos modos) mas la demanda diaria y cuantos dias cubre hoy lo que ya hay, que es
    como el usuario piensa el problema: "ya tengo para 50 dias, no me pidas 30 mas".

    Devuelve None cuando no hay demanda diaria: sin ella los dias no se pueden
    convertir a unidades. A diferencia del modo objetivo, este modo necesita si o
    si que el par este en el sugerido del BI (de ahi sale la demanda).
    """
    if dias <= 0:
        return None
    row = db.execute(
        select(
            Sugerido.demanda_diaria,
            Sugerido.stock_activo_suc,
            Sugerido.stock_en_transito_suc,
            Sugerido.total_sugerido_suc,
        ).where(Sugerido.producto == producto, Sugerido.sucursal_id == sucursal_id)
    ).first()
    if not row or row[0] is None or float(row[0]) <= 0:
        return None
    demanda = float(row[0])
    stock, transito, sistema = float(row[1] or 0), float(row[2] or 0), float(row[3] or 0)
    objetivo = _objetivo_dias(demanda, dias)
    cubierto = stock + transito + sistema
    return {
        "dias": dias,
        "demanda_diaria": demanda,
        "objetivo": objetivo,
        "stock": stock,
        "transito": transito,
        "sugerido_sistema": sistema,
        "cubierto": cubierto,
        "faltante": _faltante_para_objetivo(objetivo, stock, transito, sistema),
        "dias_cubiertos": cubierto / demanda,
        "en_sugerido": True,
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
    # Regla InStock: marca y completa el minimo, igual que en `listar`, para que el
    # Excel exporte los mismos numeros que muestra la grilla.
    cat_instock = instock_service.catalogo(db)
    instock_service.aplicar(items, cat_instock)
    margen.agregar_margen(items)
    pedidos_service.agregar_a_filas(items, db)
    # Misma regla de negocio que aplica `listar`: stock cubre el mes + sin venta
    # el mes anterior -> pedir = No, salvo que tenga manual o sea un repuesto de
    # pauta bajo el minimo. Asi el export Excel respeta lo mismo que ve la grilla.
    protegidos = set(manuales) | {
        (it["producto"], it["sucursal_id"])
        for it in items
        if it.get("instock_agregado")
    }
    _aplicar_regla_stock_sin_venta(items, db, protegidos=protegidos)
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
            # "02 LINDEROS" tambien es Linderos: con igualdad, la serie de la
            # sucursal salia plana en cero para la mayoria de los productos.
            stmt = stmt.where(misma_sucursal(suc))
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


def _ventana_12_meses(db: Session) -> list[str]:
    """Los 12 periodos "YYYYMM" que terminan en el ultimo mes cargado.

    `venta_historica` solo tiene filas de los meses en que hubo venta, asi que
    tomar "las ultimas 12 filas" NO es lo mismo que "los ultimos 12 meses": para
    un codigo que vendio 8 meses de 2024 y nunca mas, esas 8 filas eran sus
    "ultimos 12" y su venta de hace dos años se mostraba como venta del año.
    Paso con `19 CYFS12F1X`: 65 unidades vendidas hasta 09-2024 salian como
    "Venta 12m" en agosto de 2026, y `venta_12m` era igual a `venta_total`, que es
    justo la señal de que la ventana no estaba filtrando nada.

    El ancla es el ultimo periodo CARGADO y no la fecha de hoy: el motor publica
    hasta el ultimo mes cerrado, y anclar en hoy dejaria el mes en curso -siempre
    incompleto- dentro de la ventana.
    """
    tope = db.scalar(select(func.max(VentaHistorica.periodo)))
    if not tope or len(str(tope)) != 6:
        return []
    anio, mes = int(str(tope)[:4]), int(str(tope)[4:])
    salida = []
    for _ in range(12):
        salida.append(f"{anio:04d}{mes:02d}")
        mes -= 1
        if mes == 0:
            anio, mes = anio - 1, 12
    return sorted(salida)


def grupo_ventas(db: Session, producto: str) -> dict:
    """Venta mes a mes de CADA codigo del grupo de reemplazos.

    El comprador ve un numero consolidado y no sabe de donde viene. Con esto puede
    responder "¿este repuesto se vende o se dejo de vender?" cuando el codigo
    cambio tres veces en dos años: sin el desglose, un repuesto que siempre se
    vendio igual parece nuevo cada vez que FORD lo renumera.

    El dato ya estaba: `venta_historica` guarda la venta POR CODIGO CRUDO desde
    2018, asi que no hay que cargar nada ni pedirle nada al motor.

    Ojo con `agrupado`: la tabla tiene que mostrar el grupo que el MOTOR armo, no
    el que FORD declara. FORD puede declarar un reemplazo que el motor descarto
    por ambiguo, y eso queda con `agrupado=False`. Si el total del pie sumara
    codigos que el motor no junto, no cuadraria con lo que muestra el sugerido y
    el comprador confiaria en el numero equivocado. Esos codigos se muestran
    igual, pero marcados y FUERA del total.
    """
    miembros = reemplazo_service.miembros_del_grupo(db, producto)
    if len(miembros) < 2:
        # Un solo codigo no es un grupo: la tarjeta no se muestra.
        return {"producto": producto, "miembros": [], "meses": []}

    filas = reemplazo_service.por_producto(db, set(miembros))
    vigente = miembros[0]
    ventana = set(_ventana_12_meses(db))

    stock = {}
    for m in miembros:
        stock[m] = sum(r["stock"] for r in stock_service.stock_por_sucursal(db, m))

    meses: dict[str, dict[str, float]] = {}
    salida = []
    for m in miembros:
        stmt = (
            select(VentaHistorica.periodo,
                   func.coalesce(func.sum(VentaHistorica.cantidad), 0))
            .where(VentaHistorica.producto == m)
            .group_by(VentaHistorica.periodo)
            .order_by(VentaHistorica.periodo.asc())
        )
        serie = [(p, float(c)) for p, c in db.execute(stmt).all()]
        # Solo los periodos de la ventana: ver `_ventana_12_meses`.
        ult12 = [(p, c) for p, c in serie if p in ventana]
        for p, c in ult12:
            meses.setdefault(p, {})[m] = c
        f = filas.get(m)
        # `agrupado` vive en la fila del codigo DADO DE BAJA, no en la del
        # vigente: el vigente siempre cuenta.
        cuenta = m == vigente or bool((f or {}).get("agrupado"))
        # Sin fila no se sabe si el motor agrupo o no, y decir que no lo hizo
        # seria inventar. Se deja fuera del total igual -no se puede afirmar que
        # el sugerido los junto- pero el aviso dice la verdad: falta el dato.
        # Hasta el 23-08-2026 este era el caso NORMAL y no el raro: el motor
        # publicaba una fila por codigo consultado a FORD, no una por miembro del
        # grupo, asi que 3.713 codigos caian aca y la pantalla los acusaba de algo
        # que nadie habia comprobado.
        sin_dato = f is None
        salida.append({
            "producto": m,
            "es_vigente": m == vigente,
            "sku_ford": (f or {}).get("reemplazado_por_ford") if m != vigente else None,
            "venta_12m": sum(c for _, c in ult12),
            "venta_total": sum(c for _, c in serie),
            "ultimo_mes_con_venta": next(
                (p for p, c in reversed(serie) if c > 0), None),
            "stock": stock.get(m, 0),
            "cuenta_en_el_total": cuenta,
            # Por que no cuenta, para que la pantalla lo pueda decir.
            "motivo_fuera": None if cuenta else (
                "FORD lo nombra en el grupo pero la ultima corrida no trajo su "
                "ficha: no se puede confirmar que el sugerido los junte."
                if sin_dato else
                "FORD lo declara reemplazo pero el motor no los agrupo: su stock "
                "y su venta se cuentan por separado."
            ),
        })

    return {
        "producto": producto,
        "vigente": vigente,
        "miembros": salida,
        # Los 12 periodos completos, no solo los que tuvieron venta: un repuesto
        # que se dejo de vender tiene que MOSTRAR la caida, y con el eje lleno de
        # huecos el grafico la esconde.
        "meses": [
            {"mes": p, **{m: meses.get(p, {}).get(m, 0.0) for m in miembros}}
            for p in sorted(ventana)
        ],
        "total_venta_12m": sum(m["venta_12m"] for m in salida if m["cuenta_en_el_total"]),
        "total_stock": sum(m["stock"] for m in salida if m["cuenta_en_el_total"]),
    }
