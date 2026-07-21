"""Tests del margen FORD (precio de lista contra costo unitario)."""
from src.services import margen


def test_margen_sobre_precio_publico():
    fila = {"costo_unitario": 6000.0, "precio_publico_ford": 10000, "total_sugerido_suc": 5}
    margen.calcular_margen(fila)
    assert fila["margen_unitario_clp"] == 4000
    assert fila["margen_pct"] == 40.0
    # Margen potencial de lo que se sugiere comprar.
    assert fila["margen_sugerido_clp"] == 20000


def test_margen_negativo_cuando_el_costo_supera_el_precio():
    """Se compra mas caro de lo que se vende: el dato tiene que verse, no ocultarse."""
    fila = {"costo_unitario": 12000.0, "precio_publico_ford": 10000, "total_sugerido_suc": 2}
    margen.calcular_margen(fila)
    assert fila["margen_unitario_clp"] == -2000
    assert fila["margen_pct"] == -20.0
    # La proyeccion tambien sale negativa: comprar esas 2 unidades destruye margen,
    # y eso es justamente lo que el comprador necesita ver.
    assert fila["margen_sugerido_clp"] == -4000


def test_sin_precio_ford_queda_en_blanco():
    """La mayoria de los productos no son FORD: no se inventa un margen."""
    fila = {"costo_unitario": 5000.0, "precio_publico_ford": None, "total_sugerido_suc": 3}
    margen.calcular_margen(fila)
    for campo in margen.CAMPOS_MARGEN:
        assert fila[campo] is None


def test_sin_costo_queda_en_blanco():
    fila = {"costo_unitario": None, "precio_publico_ford": 10000}
    margen.calcular_margen(fila)
    assert fila["margen_pct"] is None


def test_costo_cero_no_divide_ni_inventa():
    fila = {"costo_unitario": 0.0, "precio_publico_ford": 10000}
    margen.calcular_margen(fila)
    assert fila["margen_pct"] is None


def test_precio_cero_no_divide_por_cero():
    fila = {"costo_unitario": 5000.0, "precio_publico_ford": 0, "precio_flota_ford": 0}
    margen.calcular_margen(fila)
    assert fila["margen_pct"] is None
    assert fila["margen_flota_pct"] is None


def test_margen_flota_y_sobrecosto_dealer():
    fila = {
        "costo_unitario": 8000.0,
        "precio_publico_ford": 10000,
        "precio_flota_ford": 9000,
        "precio_dealer_ford": 7000,
    }
    margen.calcular_margen(fila)
    assert fila["margen_pct"] == 20.0
    assert fila["margen_flota_pct"] == 11.1
    # El costo esta 14,3% por encima del precio dealer de FORD.
    assert fila["sobrecosto_vs_dealer_pct"] == 14.3


def test_el_listado_trae_los_campos_de_margen(client, db_session):
    """La fila del sugerido llega a la API con el margen ya calculado."""
    from src.models import Sugerido

    db_session.add(Sugerido(
        tenant_id="curifor", producto="FORD-1", sucursal_id="LINDEROS",
        nombre_sucursal="Linderos", pedir="Si", total_sugerido_suc=4,
        costo_unitario=6000.0, precio_publico_ford=10000, precio_flota_ford=9000,
    ))
    db_session.commit()
    items = client.get("/api/sugerido?q=FORD-1&solo_pedir=false").json()["items"]
    fila = next(i for i in items if i["producto"] == "FORD-1")
    assert fila["margen_pct"] == 40.0
    assert fila["margen_unitario_clp"] == 4000
    assert fila["margen_sugerido_clp"] == 16000


def test_export_incluye_las_columnas_de_margen():
    """Si no estan en LABELS el export las descarta en silencio."""
    from src.services.excel_export import LABELS

    for campo in margen.CAMPOS_MARGEN:
        assert campo in LABELS
