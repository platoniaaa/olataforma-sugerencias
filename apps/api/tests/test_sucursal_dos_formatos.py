"""`venta_historica.sucursal` trae el mismo lugar en DOS formas a la vez.

El Excel de Ventas escribe la sucursal tal como venga: "02 LINDEROS" y tambien
"LINDEROS", a veces en el mismo archivo. `sugerido.sucursal_id` usa siempre la
forma corta, asi que cruzarlas por igualdad pierde la mayor parte de la venta.

Medido en el respaldo de julio-2026: 76% de las filas trae prefijo numerico, y en
TALCA y CHILLAN la forma corta directamente NO EXISTE.

Lo caro es la regla "sin venta el mes pasado + stock >= demanda -> No pedir":
leyendo venta cero marcaba "No pedir" en todo lo que tuviera stock, y el
dashboard esconde esas filas por defecto. O sea, escondia compras que si habia
que hacer.
"""
import pytest

from src.models import VentaHistorica
from src.services import sugerido_service


def _venta(db, periodo, producto, sucursal, cantidad):
    db.add(VentaHistorica(tenant_id="curifor", periodo=periodo, producto=producto,
                          sucursal=sucursal, cantidad=cantidad))


# --- El normalizador --------------------------------------------------------- #

@pytest.mark.parametrize("entrada,esperado", [
    ("02 LINDEROS", "LINDEROS"),
    ("LINDEROS", "LINDEROS"),
    ("10 CHILLAN VIEJO", "CHILLAN VIEJO"),
    ("DIEZ DE JULIO (2)", "DIEZ DE JULIO (2)"),
    ("  07 CURICO  ", "CURICO"),
    (None, None),
])
def test_normalizar_sucursal(entrada, esperado):
    assert sugerido_service.normalizar_sucursal(entrada) == esperado


def test_normalizar_no_deja_el_nombre_vacio():
    """Un nombre que es puro numero no puede quedar en cadena vacia: perderia
    la fila en vez de conservarla como venga."""
    assert sugerido_service.normalizar_sucursal("02 ") == "02"


# --- La regla que escondia compras ------------------------------------------- #

def _item(producto, sucursal, stock, demanda):
    return {"producto": producto, "sucursal_id": sucursal,
            "stock_activo_suc": stock, "demanda_mensual": demanda,
            "pedir": "Si", "pedir_flag": "Si"}


def test_la_venta_con_prefijo_numerico_cuenta_como_venta(db_session):
    """TALCA solo existe como "08 TALCA" en el respaldo. Con igualdad la regla
    veia cero y marcaba "No pedir"."""
    db = db_session
    mes = sugerido_service._mes_anterior_yyyymm()
    _venta(db, mes, "P1", "08 TALCA", 5)
    db.commit()

    items = [_item("P1", "TALCA", stock=10, demanda=2)]
    sugerido_service._aplicar_regla_stock_sin_venta(items, db)
    assert items[0]["pedir"] == "Si", "vendio en julio: no se puede marcar No pedir"


def test_sin_venta_de_verdad_si_marca_no_pedir(db_session):
    """La contracara: el arreglo no puede desactivar la regla."""
    db = db_session
    mes = sugerido_service._mes_anterior_yyyymm()
    _venta(db, mes, "OTRO", "08 TALCA", 5)  # el mes esta cargado, pero no este producto
    db.commit()

    items = [_item("P1", "TALCA", stock=10, demanda=2)]
    sugerido_service._aplicar_regla_stock_sin_venta(items, db)
    assert items[0]["pedir"] == "No"


def test_suma_las_dos_formas_del_mismo_lugar(db_session):
    """Linderos viene repartido entre las dos formas: hay que sumarlas."""
    db = db_session
    mes = sugerido_service._mes_anterior_yyyymm()
    _venta(db, mes, "P1", "02 LINDEROS", 3)
    _venta(db, mes, "P1", "LINDEROS", 1)
    db.commit()

    items = [_item("P1", "LINDEROS", stock=10, demanda=2)]
    sugerido_service._aplicar_regla_stock_sin_venta(items, db)
    assert items[0]["pedir"] == "Si"


def test_no_se_confunde_con_una_sucursal_que_termina_igual(db_session):
    """CHILLAN VIEJO no es CHILLAN: su venta no puede salvar a la otra."""
    db = db_session
    mes = sugerido_service._mes_anterior_yyyymm()
    _venta(db, mes, "P1", "10 CHILLAN VIEJO", 50)
    db.commit()

    items = [_item("P1", "CHILLAN", stock=10, demanda=2)]
    sugerido_service._aplicar_regla_stock_sin_venta(items, db)
    assert items[0]["pedir"] == "No", "la venta de Chillan Viejo no es de Chillan"


def test_la_venta_de_otra_sucursal_no_cuenta(db_session):
    """Al sacar el filtro de sucursal de la consulta, la separacion pasa a
    hacerse en Python: hay que fijar que sigue separando."""
    db = db_session
    mes = sugerido_service._mes_anterior_yyyymm()
    _venta(db, mes, "P1", "07 CURICO", 99)
    db.commit()

    items = [_item("P1", "TALCA", stock=10, demanda=2)]
    sugerido_service._aplicar_regla_stock_sin_venta(items, db)
    assert items[0]["pedir"] == "No"


def test_sin_el_mes_cargado_la_regla_no_se_aplica(db_session):
    """La guarda de siempre: "sin venta" solo se afirma si el mes esta cargado."""
    items = [_item("P1", "TALCA", stock=10, demanda=2)]
    sugerido_service._aplicar_regla_stock_sin_venta(items, db_session)
    assert items[0]["pedir"] == "Si"


# --- El grafico de 12 meses --------------------------------------------------- #

def test_la_serie_de_la_sucursal_incluye_la_forma_numerada(db_session):
    """Salia plana en cero en el detalle de producto, la ficha y el chat."""
    db = db_session
    _venta(db, "202605", "P1", "02 LINDEROS", 7)
    _venta(db, "202605", "P1", "LINDEROS", 1)
    _venta(db, "202605", "P1", "07 CURICO", 100)
    db.commit()

    r = sugerido_service.ventas_12m(db, "P1", "LINDEROS")
    assert r["total_sucursal"] == 8, "las dos formas de Linderos, y solo esas"
    assert r["total_general"] == 108
