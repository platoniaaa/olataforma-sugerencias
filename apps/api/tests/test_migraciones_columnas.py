"""Las columnas nuevas de un modelo tienen que llegar a las tablas que YA existen.

`Base.metadata.create_all()` crea tablas que faltan, pero **no agrega columnas a
una tabla que ya existe**. Por eso `db.py` mantiene una lista de mini-migraciones
con `ADD COLUMN IF NOT EXISTS`, y agregar un campo al modelo sin agregarlo ahi
deja la base de produccion sin esa columna.

El sintoma es peor que un error: varios servicios se tragan la excepcion a
proposito para no reventar las pantallas, asi que la funcionalidad **desaparece
en silencio**. Paso el 23-08-2026 con `reemplazo_ford.extraido_en`: se agrego al
modelo, no a la lista, y todos los avisos de FORD se apagaron en produccion sin
un solo error visible.

Este test recorre los modelos y comprueba que cada columna exista en una tabla
creada ANTES del cambio — o sea, que la migracion este puesta.
"""
import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from src.db import Base, create_all


@pytest.fixture()
def engine_con_tablas_viejas(monkeypatch):
    """Una base con las tablas ya creadas, como la de produccion.

    `create_all()` apunta al engine del modulo, asi que se le cambia por este.
    """
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False},
                        poolclass=StaticPool)
    Base.metadata.create_all(bind=eng)
    monkeypatch.setattr("src.db.engine", eng)
    return eng


def _columnas(eng, tabla: str) -> set[str]:
    return {c["name"] for c in inspect(eng).get_columns(tabla)}


def test_la_migracion_agrega_una_columna_que_falta(engine_con_tablas_viejas):
    """El mecanismo funciona de verdad, no solo por casualidad.

    Se le quita a la tabla una columna que la lista de migraciones declara, se
    corre `create_all()` y se comprueba que vuelve. Si alguien rompe el bloque de
    migraciones, este test lo dice.
    """
    eng = engine_con_tablas_viejas
    with eng.begin() as cx:
        cx.execute(text("ALTER TABLE reemplazo_ford DROP COLUMN extraido_en"))
    assert "extraido_en" not in _columnas(eng, "reemplazo_ford")

    create_all()

    assert "extraido_en" in _columnas(eng, "reemplazo_ford"), (
        "La mini-migracion no repuso la columna: revisa el bloque `migraciones` "
        "de `db.py`."
    )


# --- La siembra de NODISP en `bodega_tipo` -----------------------------------------
#
# El 20-10-2026 la lista de precios paso a contar todas las bodegas MENOS las no
# disponibles (tipo NODISP). Produccion tiene Danados (dos grafias), Devolucion,
# Scrap y la bodega sin nombre marcadas VIRT: sin esta siembra habria que cargar la
# tabla a mano antes de desplegar, y hasta entonces contarian. La sentencia corre en
# CADA arranque, asi que tiene que ser inerte despues de la primera vez y despues de
# cualquier decision de una persona, o revertiria lo que el admin decida.

_PRODUCCION = [
    # (bodega, tipo): un recorte fiel de lo que hay en produccion.
    ("LINDEROS", "REAL"), ("CURICO", "REAL"), ("TRANSITO", "REAL"),
    ("CASA MATRIZ", "ELIM"), ("COQUIMBO", "ELIM"),
    ("", "VIRT"),
    ("BODEGA DAÑADOS", "VIRT"),
    ("BODEGA DAÃ‘ADOS", "VIRT"),
    ("BODEGA DEVOLUCION", "VIRT"),
    ("BODEGA SCRAP", "VIRT"),
    ("COMEX", "VIRT"), ("IMPORTACION MOTOS", "VIRT"), ("PE X REGULARIZAR", "VIRT"),
    ("PE-FALTANTE", "VIRT"), ("TALCA 2 DIFERENCIA", "VIRT"),
]
_SEMBRADAS = {"", "BODEGA DAÑADOS", "BODEGA DAÃ‘ADOS", "BODEGA DEVOLUCION", "BODEGA SCRAP"}


def _cargar_bodegas(eng, filas, actualizado_por=None):
    from src.models import BodegaTipo
    from src.services.precios_service import clave_bodega

    with Session(eng) as s:
        for bodega, tipo in filas:
            s.add(BodegaTipo(tenant_id="curifor", bodega=bodega, clave=clave_bodega(bodega),
                             tipo=tipo, actualizado_por=actualizado_por))
        s.commit()


def _tipos(eng) -> dict[str, str]:
    from src.models import BodegaTipo

    with Session(eng) as s:
        return {b.bodega: b.tipo for b in s.query(BodegaTipo).all()}


def test_la_siembra_deja_en_nodisp_danados_devolucion_scrap_y_la_bodega_sin_nombre(
        engine_con_tablas_viejas):
    eng = engine_con_tablas_viejas
    _cargar_bodegas(eng, _PRODUCCION)

    create_all()

    tipos = _tipos(eng)
    assert {b for b, t in tipos.items() if t == "NODISP"} == _SEMBRADAS
    # Lo demas no se toca: PE X REGULARIZAR, COMEX... siguen VIRT y cuentan.
    for bodega, tipo in _PRODUCCION:
        if bodega not in _SEMBRADAS:
            assert tipos[bodega] == tipo, bodega


def test_la_siembra_corre_una_sola_vez(engine_con_tablas_viejas):
    """Un reinicio no revierte una decision: si el admin deja SCRAP en VIRT a
    proposito, la segunda corrida (el proximo arranque) no lo vuelve NODISP."""
    eng = engine_con_tablas_viejas
    _cargar_bodegas(eng, _PRODUCCION)
    create_all()
    with eng.begin() as cx:
        cx.execute(text("UPDATE bodega_tipo SET tipo='VIRT' WHERE bodega='BODEGA SCRAP'"))

    create_all()

    tipos = _tipos(eng)
    assert tipos["BODEGA SCRAP"] == "VIRT"
    assert {b for b, t in tipos.items() if t == "NODISP"} == _SEMBRADAS - {"BODEGA SCRAP"}


def test_la_siembra_no_corre_si_ya_hay_una_nodisp(engine_con_tablas_viejas):
    eng = engine_con_tablas_viejas
    _cargar_bodegas(eng, [("BODEGA DAÑADOS", "VIRT"), ("BODEGA SCRAP", "NODISP")])

    create_all()

    assert _tipos(eng) == {"BODEGA DAÑADOS": "VIRT", "BODEGA SCRAP": "NODISP"}


def test_la_siembra_no_corre_si_una_persona_ya_cargo_la_tabla(engine_con_tablas_viejas):
    """`actualizado_por` lo llena la carga del admin: si hay alguien ahi, la
    clasificacion es una decision, no el estado de fabrica."""
    eng = engine_con_tablas_viejas
    _cargar_bodegas(eng, _PRODUCCION, actualizado_por="admin@curifor.com")

    create_all()

    assert not [t for t in _tipos(eng).values() if t == "NODISP"]


def test_la_siembra_no_toca_una_bodega_que_el_admin_dejo_real(engine_con_tablas_viejas):
    eng = engine_con_tablas_viejas
    _cargar_bodegas(eng, [("BODEGA DEVOLUCION", "REAL"), ("BODEGA SCRAP", "VIRT")])

    create_all()

    assert _tipos(eng) == {"BODEGA DEVOLUCION": "REAL", "BODEGA SCRAP": "NODISP"}


def test_la_siembra_con_la_tabla_vacia_no_hace_nada(engine_con_tablas_viejas):
    eng = engine_con_tablas_viejas

    create_all()

    assert _tipos(eng) == {}
