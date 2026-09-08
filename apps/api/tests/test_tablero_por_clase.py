"""Los indicadores del tablero, cortados por clase ABC.

Medido en produccion el 08-09-2026 sobre las 17.129 filas del sugerido:

- De los 11.680 quiebres con demanda, **11.533 son clase D** (98,7%). Los de
  clase A son 26. El total no sirve para decidir: un quiebre de A se atiende hoy
  y uno de D probablemente no se atienda nunca.
- La mediana de cobertura daba **0,0 dias** porque metia en el calculo las filas
  sin stock, que son 11.678 de 16.891 (69%). Asi el indicador no medi­a cuanto
  dura el inventario sino cuantas filas estaban en cero -que ya lo dice el
  quiebre-. Contando solo las que tienen stock da 168 dias.
- El total de unidades lo dominan 12 codigos de aceite a granel cargados en
  mililitros: son el 98,3% de 4,5 millones. El numero existe, pero no es una
  cantidad de repuestos y la pantalla tiene que poder decirlo.
"""
from src.models import Sugerido
from src.schemas.sugerido import SugeridoFiltros
from src.services import inventario_service


def _fila(db, producto, clase, stock, demanda_mes, costo=1000.0, sucursal="LINDEROS"):
    db.add(Sugerido(
        tenant_id="curifor", producto=producto, sucursal_id=sucursal,
        nombre_sucursal=sucursal, clasificacion_abc=clase,
        stock_activo_suc=stock, demanda_mensual=demanda_mes,
        demanda_diaria=(demanda_mes / 30) if demanda_mes else 0.0,
        costo_unitario=costo, pedir="No",
    ))


# --- El corte por clase ---------------------------------------------------------


def test_el_quiebre_se_corta_por_clase(db_session):
    """Sin el corte, 26 quiebres de clase A quedan enterrados bajo 11.533 de D."""
    _fila(db_session, "17 A1", "A", stock=0, demanda_mes=30)
    _fila(db_session, "17 D1", "D", stock=0, demanda_mes=1)
    _fila(db_session, "17 D2", "D", stock=0, demanda_mes=1)
    db_session.commit()

    r = inventario_service.salud(db_session, SugeridoFiltros())
    por_clase = {c["clase"]: c for c in r["por_clase"]}

    assert r["resumen"]["quiebre_con_demanda_n"] == 3
    assert por_clase["A"]["quiebre_n"] == 1
    assert por_clase["D"]["quiebre_n"] == 2


def test_el_sobre_stock_y_el_inmovilizado_tambien(db_session):
    # Se mueve pero alcanza para anos: sobre-stock.
    _fila(db_session, "17 A1", "A", stock=1000, demanda_mes=1)
    # Hay stock y el modelo no le ve demanda: inmovilizado.
    _fila(db_session, "17 D1", "D", stock=50, demanda_mes=0)
    db_session.commit()

    por_clase = {c["clase"]: c for c in
                 inventario_service.salud(db_session, SugeridoFiltros())["por_clase"]}

    assert por_clase["A"]["sobre_stock_n"] == 1
    assert por_clase["D"]["inmovilizado_n"] == 1
    assert por_clase["D"]["inmovilizado_clp"] == 50_000


def test_las_clases_sin_filas_no_se_muestran(db_session):
    """Una fila "(sin clase)" en cero solo distrae."""
    _fila(db_session, "17 A1", "A", stock=5, demanda_mes=10)
    db_session.commit()

    assert [c["clase"] for c in
            inventario_service.salud(db_session, SugeridoFiltros())["por_clase"]] == ["A"]


def test_la_fila_sin_clase_se_cuenta_aparte(db_session):
    _fila(db_session, "17 X", None, stock=5, demanda_mes=10)
    db_session.commit()

    por_clase = {c["clase"]: c for c in
                 inventario_service.salud(db_session, SugeridoFiltros())["por_clase"]}

    assert por_clase["(sin clase)"]["n_filas"] == 1


# --- La mediana de cobertura ----------------------------------------------------


def test_la_cobertura_no_cuenta_lo_que_no_tiene_stock(db_session):
    """Tres filas en cero y una con 60 dias: la mediana es 60, no 0.

    Con las filas en cero adentro la mediana daba 0 y el indicador dejaba de medir
    duracion para medir cuantas filas estan en cero -que ya lo dice el quiebre-.
    """
    _fila(db_session, "17 CON", "A", stock=60, demanda_mes=30)   # 60 dias
    for i in range(3):
        _fila(db_session, f"17 SIN{i}", "D", stock=0, demanda_mes=30)
    db_session.commit()

    r = inventario_service.salud(db_session, SugeridoFiltros())["resumen"]

    assert r["cobertura_dias_mediana"] == 60.0
    assert r["cobertura_filas"] == 1


def test_sin_ninguna_fila_con_stock_la_cobertura_es_nula(db_session):
    """None y no 0: no es que dure cero, es que no hay de donde medirlo."""
    _fila(db_session, "17 SIN", "A", stock=0, demanda_mes=30)
    db_session.commit()

    r = inventario_service.salud(db_session, SugeridoFiltros())["resumen"]

    assert r["cobertura_dias_mediana"] is None
    assert r["cobertura_filas"] == 0


# --- La concentracion de las unidades -------------------------------------------


def test_avisa_cuando_las_unidades_estan_en_un_punado_de_codigos(db_session):
    """El granel en mililitros: 12 codigos son el 98% de 4,5 millones."""
    _fila(db_session, "70 GRANEL", "D", stock=1_000_000, demanda_mes=1)
    for i in range(20):
        _fila(db_session, f"17 P{i:02d}", "D", stock=10, demanda_mes=1)
    db_session.commit()

    r = inventario_service.salud(db_session, SugeridoFiltros())["resumen"]

    assert r["unidades"] == 1_000_200
    assert r["unidades_top10_pct"] > 99


def test_sin_unidades_no_revienta(db_session):
    _fila(db_session, "17 A", "A", stock=0, demanda_mes=1)
    db_session.commit()

    assert inventario_service.salud(
        db_session, SugeridoFiltros())["resumen"]["unidades_top10_pct"] == 0.0


# --- Llega al tablero -----------------------------------------------------------


def test_el_tablero_trae_el_corte_por_clase(client, db_session):
    _fila(db_session, "17 A1", "A", stock=0, demanda_mes=30)
    db_session.commit()

    r = client.get("/api/tablero")

    assert r.status_code == 200, r.text
    clases = {c["clase"]: c for c in r.json()["inventario"]["por_clase"]}
    assert clases["A"]["quiebre_n"] == 1
