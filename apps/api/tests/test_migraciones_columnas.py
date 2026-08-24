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
