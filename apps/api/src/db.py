"""Configuracion de SQLAlchemy: engine, sesiones y base declarativa."""
import os
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings

# En Vercel (serverless) no se mantienen conexiones entre invocaciones.
EN_SERVERLESS = bool(os.environ.get("VERCEL"))

settings = get_settings()


class Base(DeclarativeBase):
    """Base declarativa para todos los modelos."""


def _make_engine():
    url = settings.database_url
    connect_args: dict = {}
    kwargs: dict = {}
    if url.startswith("sqlite"):
        # SQLite necesita esto para usarse desde varios threads (FastAPI).
        connect_args = {"check_same_thread": False}
        # Asegurar que la carpeta del archivo .db exista (ej. ./data/sugerido.db).
        if ":///" in url:
            db_path = url.split(":///", 1)[1]
            if db_path and db_path != ":memory:":
                Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    elif url.startswith("postgresql"):
        # PostgreSQL (Supabase): SSL obligatorio + reciclar conexiones para evitar
        # cortes del pooler. pg8000 habilita TLS via ssl_context.
        kwargs["pool_pre_ping"] = True
        if EN_SERVERLESS:
            # Sin pool persistente: cada invocacion abre/cierra su conexion.
            from sqlalchemy.pool import NullPool

            kwargs["poolclass"] = NullPool
        else:
            kwargs["pool_recycle"] = 300
        if "pg8000" in url and settings.db_ssl:
            import ssl

            ctx = ssl.create_default_context()
            # En redes corporativas con inspeccion TLS (proxy/antivirus) la verificacion
            # del certificado falla. La conexion sigue encriptada; solo no se verifica la
            # cadena. Poner DB_SSL_VERIFY=true si el entorno tiene certificados validos.
            if not settings.db_ssl_verify:
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            connect_args = {"ssl_context": ctx}
    return create_engine(url, connect_args=connect_args, **kwargs)


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def create_all() -> None:
    """Crea las tablas si no existen (Fase 0; en Fase 1+ se usa Alembic)."""
    # Importa los modelos para registrarlos en el metadata antes de create_all.
    from . import models  # noqa: F401
    from sqlalchemy import text

    Base.metadata.create_all(bind=engine)
    # Mini-migracion in-line: agregar columnas nuevas a tablas ya creadas.
    # Mientras no haya Alembic, usamos ADD COLUMN IF NOT EXISTS (Postgres y SQLite>=3.35).
    migraciones = [
        "ALTER TABLE sugerencia_recurrente ADD COLUMN IF NOT EXISTS dias_inventario INTEGER",
        "ALTER TABLE usuario ADD COLUMN IF NOT EXISTS es_admin BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE sugerido ADD COLUMN IF NOT EXISTS empresa VARCHAR",
        "ALTER TABLE sugerencia_manual ADD COLUMN IF NOT EXISTS lote_id VARCHAR",
        "CREATE INDEX IF NOT EXISTS ix_sugmanual_lote ON sugerencia_manual (lote_id)",
        "ALTER TABLE sugerencia_manual ADD COLUMN IF NOT EXISTS expira_en TIMESTAMP WITH TIME ZONE",
        "CREATE INDEX IF NOT EXISTS ix_sugmanual_expira ON sugerencia_manual (expira_en)",
        # 2026-07: traslado lateral + stock por bodega en el sugerido.
        "ALTER TABLE sugerido ADD COLUMN IF NOT EXISTS trasladar_desde VARCHAR",
        "ALTER TABLE sugerido ADD COLUMN IF NOT EXISTS stock_linderos INTEGER",
        "ALTER TABLE sugerido ADD COLUMN IF NOT EXISTS stock_curico INTEGER",
        "ALTER TABLE sugerido ADD COLUMN IF NOT EXISTS stock_talca INTEGER",
        "ALTER TABLE sugerido ADD COLUMN IF NOT EXISTS stock_rancagua INTEGER",
        "ALTER TABLE sugerido ADD COLUMN IF NOT EXISTS stock_diez_de_julio_2 INTEGER",
        "ALTER TABLE sugerido ADD COLUMN IF NOT EXISTS stock_chillan INTEGER",
        "ALTER TABLE sugerido ADD COLUMN IF NOT EXISTS stock_cd_repuestos INTEGER",
        "ALTER TABLE sugerido ADD COLUMN IF NOT EXISTS stock_brasil_18 INTEGER",
        "ALTER TABLE sugerido ADD COLUMN IF NOT EXISTS stock_placilla INTEGER",
        "ALTER TABLE sugerido ADD COLUMN IF NOT EXISTS stock_chillan_viejo INTEGER",
        "ALTER TABLE sugerido ADD COLUMN IF NOT EXISTS stock_talca_2 INTEGER",
        # 2026-07: clase ABC agregada + sucursales que consolida el CD.
        "ALTER TABLE sugerido ADD COLUMN IF NOT EXISTS clasificacion_abc_agregada VARCHAR",
        "ALTER TABLE sugerido ADD COLUMN IF NOT EXISTS sucursales_origen_cd VARCHAR",
        # 2026-07: acceso por sucursal (usuario ve solo sus sucursales).
        "ALTER TABLE usuario ADD COLUMN IF NOT EXISTS sucursales_permitidas TEXT",
        # 2026-07: usuario de solo lectura (no puede crear/editar sugerencias).
        "ALTER TABLE usuario ADD COLUMN IF NOT EXISTS solo_lectura BOOLEAN NOT NULL DEFAULT FALSE",
        # 2026-07: precios FORD (cruce por codigo con la tabla Precios del BI).
        "ALTER TABLE sugerido ADD COLUMN IF NOT EXISTS precio_flota_ford INTEGER",
        "ALTER TABLE sugerido ADD COLUMN IF NOT EXISTS precio_dealer_ford INTEGER",
        "ALTER TABLE sugerido ADD COLUMN IF NOT EXISTS precio_publico_ford INTEGER",
        "ALTER TABLE sugerido ADD COLUMN IF NOT EXISTS precio_publico_iva_ford INTEGER",
        "ALTER TABLE sugerido ADD COLUMN IF NOT EXISTS precio_reposicion_ford INTEGER",
        "ALTER TABLE sugerido ADD COLUMN IF NOT EXISTS precio_urgente_vor_ford INTEGER",
        "ALTER TABLE sugerido ADD COLUMN IF NOT EXISTS precio_promociones_ford INTEGER",
        "ALTER TABLE sugerido ADD COLUMN IF NOT EXISTS precio_urgente_recargo15_ford INTEGER",
        # 2026-07: lista de precios de Gildemeister (Hyundai, JAC, Mahindra...).
        "ALTER TABLE sugerido ADD COLUMN IF NOT EXISTS precio_sugerido_gilde INTEGER",
        "ALTER TABLE sugerido ADD COLUMN IF NOT EXISTS precio_dealer_gilde INTEGER",
        "ALTER TABLE sugerido ADD COLUMN IF NOT EXISTS precio_final_dealer_gilde INTEGER",
        # 2026-07: sugerencias que mantienen un nivel de stock (modo objetivo).
        "ALTER TABLE sugerencia_recurrente ADD COLUMN IF NOT EXISTS stock_objetivo INTEGER",
        # 2026-07: como se pidio cada sugerencia manual (para poder explicarla).
        "ALTER TABLE sugerencia_manual ADD COLUMN IF NOT EXISTS dias_inventario INTEGER",
        "ALTER TABLE sugerencia_manual ADD COLUMN IF NOT EXISTS stock_objetivo INTEGER",
        # 2026-07: mas perillas calibrables (modulos Lead time y Demanda).
        "ALTER TABLE configuracion_modelo ADD COLUMN IF NOT EXISTS dias_habiles_mes INTEGER NOT NULL DEFAULT 22",
        "ALTER TABLE configuracion_modelo ADD COLUMN IF NOT EXISTS lt_cd_rm_dias INTEGER NOT NULL DEFAULT 1",
        "ALTER TABLE configuracion_modelo ADD COLUMN IF NOT EXISTS lt_cd_resto_dias INTEGER NOT NULL DEFAULT 2",
        "ALTER TABLE configuracion_modelo ADD COLUMN IF NOT EXISTS lt_tope_dias INTEGER NOT NULL DEFAULT 30",
        "ALTER TABLE configuracion_modelo ADD COLUMN IF NOT EXISTS transito_nacional_dias INTEGER NOT NULL DEFAULT 30",
        "ALTER TABLE configuracion_modelo ADD COLUMN IF NOT EXISTS transito_importado_dias INTEGER NOT NULL DEFAULT 180",
        "ALTER TABLE configuracion_modelo ADD COLUMN IF NOT EXISTS abc_umbral_a_m6 INTEGER NOT NULL DEFAULT 5",
        "ALTER TABLE configuracion_modelo ADD COLUMN IF NOT EXISTS abc_umbral_b_m6 INTEGER NOT NULL DEFAULT 4",
        "ALTER TABLE configuracion_modelo ADD COLUMN IF NOT EXISTS abc_umbral_c_m6 INTEGER NOT NULL DEFAULT 3",
        "ALTER TABLE configuracion_modelo ADD COLUMN IF NOT EXISTS abc_umbral_c_m3 INTEGER NOT NULL DEFAULT 2",
        "ALTER TABLE configuracion_modelo ADD COLUMN IF NOT EXISTS abc_umbral_c_m12 INTEGER NOT NULL DEFAULT 6",
        # 2026-07: reposicion al nivel maximo (el faltante ya no se redondea a cero).
        "ALTER TABLE configuracion_modelo ADD COLUMN IF NOT EXISTS reponer_a_maximo BOOLEAN NOT NULL DEFAULT TRUE",
        "ALTER TABLE configuracion_modelo ADD COLUMN IF NOT EXISTS clases_que_reponen VARCHAR NOT NULL DEFAULT 'AB'",
        "ALTER TABLE sugerido ADD COLUMN IF NOT EXISTS nivel_maximo INTEGER",
        # 2026-08: frecuencia de venta (meses con venta de los ultimos 3/6/12).
        "ALTER TABLE sugerido ADD COLUMN IF NOT EXISTS meses_con_venta_3m INTEGER",
        "ALTER TABLE sugerido ADD COLUMN IF NOT EXISTS meses_con_venta_6m INTEGER",
        "ALTER TABLE sugerido ADD COLUMN IF NOT EXISTS meses_con_venta_12m INTEGER",
        # 2026-08: venta mes a mes de los ultimos 12 y sus promedios a 3/6/12.
        "ALTER TABLE sugerido ADD COLUMN IF NOT EXISTS venta_mes_01 DOUBLE PRECISION",
        "ALTER TABLE sugerido ADD COLUMN IF NOT EXISTS venta_mes_02 DOUBLE PRECISION",
        "ALTER TABLE sugerido ADD COLUMN IF NOT EXISTS venta_mes_03 DOUBLE PRECISION",
        "ALTER TABLE sugerido ADD COLUMN IF NOT EXISTS venta_mes_04 DOUBLE PRECISION",
        "ALTER TABLE sugerido ADD COLUMN IF NOT EXISTS venta_mes_05 DOUBLE PRECISION",
        "ALTER TABLE sugerido ADD COLUMN IF NOT EXISTS venta_mes_06 DOUBLE PRECISION",
        "ALTER TABLE sugerido ADD COLUMN IF NOT EXISTS venta_mes_07 DOUBLE PRECISION",
        "ALTER TABLE sugerido ADD COLUMN IF NOT EXISTS venta_mes_08 DOUBLE PRECISION",
        "ALTER TABLE sugerido ADD COLUMN IF NOT EXISTS venta_mes_09 DOUBLE PRECISION",
        "ALTER TABLE sugerido ADD COLUMN IF NOT EXISTS venta_mes_10 DOUBLE PRECISION",
        "ALTER TABLE sugerido ADD COLUMN IF NOT EXISTS venta_mes_11 DOUBLE PRECISION",
        "ALTER TABLE sugerido ADD COLUMN IF NOT EXISTS venta_mes_12 DOUBLE PRECISION",
        "ALTER TABLE sugerido ADD COLUMN IF NOT EXISTS prom_vta_3m DOUBLE PRECISION",
        "ALTER TABLE sugerido ADD COLUMN IF NOT EXISTS prom_vta_6m DOUBLE PRECISION",
        "ALTER TABLE sugerido ADD COLUMN IF NOT EXISTS prom_vta_12m DOUBLE PRECISION",
        "ALTER TABLE sugerido ADD COLUMN IF NOT EXISTS periodo_ultimo_mes VARCHAR",
        # 2026-09: el menor precio de compra de la lista de FORD.
        "ALTER TABLE sugerido ADD COLUMN IF NOT EXISTS precio_recomendado_compra INTEGER",
        # 2026-08: vendedor de sucursal (arma requerimientos, no ve el sugerido).
        "ALTER TABLE usuario ADD COLUMN IF NOT EXISTS es_vendedor BOOLEAN NOT NULL DEFAULT FALSE",
        # 2026-08: notificaciones dirigidas ("tu requerimiento fue comprado").
        "ALTER TABLE notificacion ADD COLUMN IF NOT EXISTS para_email VARCHAR",
        "CREATE INDEX IF NOT EXISTS ix_notificacion_para_email ON notificacion (para_email)",
        # 2026-08: cuando se consulto el portal de FORD por cada reemplazo.
        # Sin esta linea el modelo pide una columna que la tabla no tiene, y como
        # `reemplazo_service.por_producto` se traga la excepcion para no reventar
        # las pantallas, el efecto es que TODOS los avisos de FORD desaparecen sin
        # ningun error visible: la ficha, la columna del sugerido, el autocomplete
        # y la tabla del grupo quedan en blanco. Paso en produccion el 23-08-2026.
        "ALTER TABLE reemplazo_ford ADD COLUMN IF NOT EXISTS extraido_en VARCHAR",
        # 2026-08: repuestos InStock agregados a mano desde la plataforma. Sin
        # `origen` la carga desde el CSV se los lleva por delante, porque borra la
        # tabla entera antes de reinsertar.
        "ALTER TABLE repuesto_instock ADD COLUMN IF NOT EXISTS origen VARCHAR NOT NULL DEFAULT 'pauta'",
        "ALTER TABLE repuesto_instock ADD COLUMN IF NOT EXISTS motivo TEXT",
        "ALTER TABLE repuesto_instock ADD COLUMN IF NOT EXISTS creado_por VARCHAR",
        "ALTER TABLE repuesto_instock ADD COLUMN IF NOT EXISTS creado_en VARCHAR",
    ]
    # SQLite NO soporta "ADD COLUMN IF NOT EXISTS" (error de sintaxis que se
    # tragaba el try, dejando bases locales viejas sin las columnas nuevas):
    # se ejecuta sin la clausula y el error por columna duplicada se ignora.
    es_sqlite = settings.database_url.startswith("sqlite")
    for sql in migraciones:
        if es_sqlite and sql.startswith("ALTER TABLE"):
            sql = sql.replace("ADD COLUMN IF NOT EXISTS", "ADD COLUMN", 1)
        try:
            # Transaccion por sentencia: una que falle (columna ya existe) no
            # aborta las siguientes (en Postgres abortaria la transaccion entera).
            with engine.begin() as conn:
                conn.execute(text(sql))
        except Exception as e:
            # La mayoria de los fallos aca son "la columna ya existe", que es lo
            # normal y esperado. Pero un fallo DE VERDAD (corte del pooler
            # justo en esa sentencia) deja el modelo declarando una columna que
            # la tabla no tiene, y ahi TODA consulta de esa tabla se cae hasta
            # el proximo reinicio. Con `pass` eso no dejaba ni una linea de log.
            texto = str(e).lower()
            ya_existe = any(
                p in texto
                for p in ("already exists", "duplicate column", "ya existe")
            )
            if not ya_existe:
                print(f"[migracion] FALLO: {sql} -> {type(e).__name__}: {e}")


def get_db() -> Generator[Session, None, None]:
    """Dependencia de FastAPI: entrega una sesion y la cierra al terminar."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
