"""Tests del simulador what-if."""
from src.models import Sugerido
from src.services import simulador_service


def _sug(**kw):
    base = dict(
        tenant_id="curifor", sucursal_id="LINDEROS", nombre_sucursal="Linderos",
        clasificacion_abc="A", abastece_cd="No", demanda_diaria=1.0,
        desv_std_mensual=0.0, lt_efectivo=10, stock_activo_suc=0,
        stock_en_transito_suc=0, costo_unitario=1000.0,
    )
    base.update(kw)
    return Sugerido(**base)


def _solo(db_session, *filas):
    """Deja en la tabla exactamente estas filas: el simulador agrega sobre TODO
    el universo filtrado, asi que la fila del seed descuadraria los totales."""
    db_session.query(Sugerido).delete()
    for f in filas:
        db_session.add(f)
    db_session.commit()


def test_con_los_parametros_actuales_reproduce_el_sugerido_vigente(client, db_session):
    """La prueba de que la formula del simulador es la del modelo: sin cambiar
    nada, tiene que dar lo mismo que ya esta cargado."""
    # DD=1, LT=10, CO=5 (compra directa), SS=0, sin stock -> 15 unidades.
    _solo(db_session, _sug(producto="P1", total_sugerido_suc=15))
    r = client.post("/api/inventario/simular", json={}).json()
    assert r["resumen"]["actual_unidades"] == 15
    assert r["resumen"]["simulado_unidades"] == 15
    assert r["resumen"]["delta_unidades"] == 0
    assert r["resumen"]["lineas_que_cambian"] == 0


def test_subir_el_ciclo_de_orden_aumenta_la_compra(client, db_session):
    _solo(db_session, _sug(producto="P1", total_sugerido_suc=15))
    r = client.post("/api/inventario/simular", json={"ciclo_orden_dias": 10}).json()
    # DD=1, LT=10, CO=10 -> 20 unidades (5 mas).
    assert r["resumen"]["simulado_unidades"] == 20
    assert r["resumen"]["delta_unidades"] == 5
    assert r["resumen"]["delta_clp"] == 5000


def test_el_ciclo_del_cd_solo_afecta_a_lo_abastecido_del_cd(client, db_session):
    _solo(
        db_session,
        _sug(producto="DIRECTA", abastece_cd="No", total_sugerido_suc=15),
        _sug(producto="VIA-CD", abastece_cd="Si", total_sugerido_suc=13),
    )
    r = client.post("/api/inventario/simular", json={"ciclo_orden_dias_cd": 6}).json()
    cambios = {c["producto"]: c for c in r["mayores_cambios"]}
    assert "DIRECTA" not in cambios
    assert cambios["VIA-CD"]["delta"] == 3  # de CO=3 a CO=6


def test_bajar_el_nivel_de_servicio_reduce_el_stock_de_seguridad(client, db_session):
    _solo(db_session, _sug(producto="P1", desv_std_mensual=10.0, total_sugerido_suc=100))
    base = client.post("/api/inventario/simular", json={}).json()
    bajo = client.post(
        "/api/inventario/simular", json={"z_por_clase": {"A": 0.842}}
    ).json()
    assert bajo["resumen"]["simulado_unidades"] < base["resumen"]["simulado_unidades"]


def test_alargar_el_lead_time_aumenta_la_compra(client, db_session):
    _solo(db_session, _sug(producto="P1", total_sugerido_suc=15))
    r = client.post("/api/inventario/simular", json={"factor_lead_time": 2.0}).json()
    # LT pasa de 10 a 20 dias -> 25 unidades.
    assert r["resumen"]["simulado_unidades"] == 25


def test_el_stock_disponible_se_descuenta(client, db_session):
    _solo(db_session, _sug(
        producto="P1", stock_activo_suc=10, stock_en_transito_suc=2, total_sugerido_suc=3,
    ))
    r = client.post("/api/inventario/simular", json={}).json()
    assert r["resumen"]["simulado_unidades"] == 3  # 15 - 10 - 2


def test_clase_d_no_genera_compra(client, db_session):
    _solo(db_session, _sug(
        producto="P1", clasificacion_abc="D", clasificacion_abc_agregada="D",
        total_sugerido_suc=0,
    ))
    r = client.post("/api/inventario/simular", json={}).json()
    assert r["resumen"]["simulado_unidades"] == 0


def test_no_modifica_ningun_dato(client, db_session):
    """Es un calculo al vuelo: la tabla queda igual."""
    _solo(db_session, _sug(producto="P1", total_sugerido_suc=15))
    antes = {(s.producto, s.total_sugerido_suc) for s in db_session.query(Sugerido).all()}
    client.post("/api/inventario/simular", json={"ciclo_orden_dias": 30})
    despues = {(s.producto, s.total_sugerido_suc) for s in db_session.query(Sugerido).all()}
    assert antes == despues


def test_redondeo_es_el_del_modelo():
    """DAX redondea half-away-from-zero; Python por defecto usa el bancario."""
    assert simulador_service._round_com(2.5) == 3
    assert simulador_service._round_com(3.5) == 4
    assert round(2.5) == 2  # el de Python, que NO se debe usar aca
