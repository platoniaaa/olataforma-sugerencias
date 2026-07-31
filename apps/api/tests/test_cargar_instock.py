"""Un part number de la pauta se marca en UN solo código de producto.

El ERP repite el mismo part number bajo varios rubros ("28 2151323001" y
"95 2151323001" son la misma golilla). El mínimo InStock se aplica por código, así
que marcar los dos hacía que la plataforma pidiera 2 unidades de cada rubro: 4 del
mismo repuesto físico por sucursal, 16 entre las cuatro con taller. Y la mitad
sobre un rubro que Curifor no usa.
"""
from src.jobs.cargar_instock import elegir_codigo


def test_gana_el_codigo_que_esta_en_el_sugerido():
    """Es el que la plataforma usa para representar la pieza (y el maestro de su
    grupo de reemplazos): colgar el mínimo de otro sería pedirlo aparte."""
    elegido = elegir_codigo(
        {"28 2151323001", "95 2151323001"},
        en_sugerido={"95 2151323001"},
        stock={"28 2151323001": 500.0, "95 2151323001": 1.0},
    )
    # Gana aunque el otro tenga MUCHO más stock: estar en el sugerido manda.
    assert elegido == "95 2151323001"


def test_si_ninguno_esta_en_el_sugerido_gana_el_que_curifor_stockea():
    elegido = elegir_codigo(
        {"28 2151323001", "95 2151323001"},
        en_sugerido=set(),
        stock={"95 2151323001": 301.0},
    )
    assert elegido == "95 2151323001"


def test_entre_dos_con_stock_gana_el_de_mas_stock():
    elegido = elegir_codigo(
        {"17 ABC", "61 ABC"},
        en_sugerido=set(),
        stock={"17 ABC": 5.0, "61 ABC": 80.0},
    )
    assert elegido == "61 ABC"


def test_sin_sugerido_ni_stock_el_criterio_es_estable():
    """Dos corridas del job tienen que marcar el mismo código."""
    codigos = {"95 ZZZ", "17 ZZZ", "61 ZZZ"}
    elegidos = {
        elegir_codigo(codigos, en_sugerido=set(), stock={}) for _ in range(5)
    }
    assert elegidos == {"17 ZZZ"}


def test_un_solo_candidato_se_devuelve_tal_cual():
    assert elegir_codigo({"95 UNICO"}, en_sugerido=set(), stock={}) == "95 UNICO"
