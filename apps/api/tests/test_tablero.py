"""El tablero mensual de Abastecimiento.

Lo que estos tests cuidan no es la aritmetica -esa se ve- sino las tres formas en
que un tablero miente sin dar ningun error:

1. Contar dias de quiebre sobre un mes al que le faltan dias de medicion, y
   presentarlo como si estuviera completo.
2. Contar como incumplimiento InStock un quiebre en una sucursal donde la regla
   no aplica.
3. Esconder los indicadores que no se pueden calcular, y hacer creer que el
   tablero esta completo.
"""
from datetime import date

import pytest

from src.models import (
    ProductoCatalogo, ReemplazoFord, RepuestoInstock, Sugerido, SugeridoSnapshot,
)
from src.services import tablero_service

PERIODO = "2026-08"


def _snap(db, fecha: date, producto: str, sucursal: str, stock: float, abc: str = "A"):
    db.add(SugeridoSnapshot(
        tenant_id="curifor", fecha=fecha, producto=producto, sucursal_id=sucursal,
        clasificacion_abc=abc, stock_activo_suc=stock, total_sugerido_suc=0.0,
        demanda_diaria=1.0, costo_unitario=1000.0, pedir="No"))


# --- Dias de quiebre ------------------------------------------------------------


def test_los_dias_de_quiebre_se_cuentan_por_sku_y_sucursal(db_session):
    """Un repuesto en cero 3 dias en dos sucursales son 6 dias-SKU, no 3.

    Es la unidad que se puede sumar por clase y comparar contra el mes anterior.
    """
    for d in (1, 2, 3):
        _snap(db_session, date(2026, 8, d), "17 A", "LINDEROS", 0)
        _snap(db_session, date(2026, 8, d), "17 A", "CURICO", 0)
    _snap(db_session, date(2026, 8, 1), "17 B", "LINDEROS", 5, abc="B")
    db_session.commit()

    t = tablero_service.mensual(db_session, PERIODO)

    por_clase = {c["clase"]: c["dias"] for c in t["servicio"]["dias_quiebre_por_clase"]}
    assert por_clase["A"] == 6
    assert por_clase["B"] == 0, "un repuesto CON stock no puede sumar dias de quiebre"


def test_el_tablero_dice_cuantos_dias_alcanzo_a_medir(db_session):
    """40 dias de quiebre sobre 12 dias medidos no es lo mismo que sobre 31.

    Si el job diario se cayo, el mes esta incompleto y el numero no se puede
    comparar con el mes anterior. Callarlo es la forma mas facil de que alguien
    saque una conclusion al reves.
    """
    for d in (1, 2, 3):
        _snap(db_session, date(2026, 8, d), "17 A", "LINDEROS", 0)
    db_session.commit()

    s = tablero_service.mensual(db_session, PERIODO)["servicio"]

    assert s["dias_medidos"] == 3
    assert s["dias_del_mes"] == 31
    assert s["mes_completo"] is False


# --- InStock --------------------------------------------------------------------


def test_el_quiebre_instock_solo_cuenta_en_las_sucursales_con_taller(db_session):
    """InStock es producto-SUCURSAL. En Talca el mismo codigo es uno cualquiera.

    Contar ahi un incumplimiento inflaria un problema que no existe, y llevaria a
    revisar un minimo que en esa sucursal no aplica.
    """
    db_session.add(RepuestoInstock(tenant_id="curifor", producto="17 PAUTA", minimo=2))
    for d in (1, 2):
        _snap(db_session, date(2026, 8, d), "17 PAUTA", "LINDEROS", 0)
        _snap(db_session, date(2026, 8, d), "17 PAUTA", "TALCA", 0)
    db_session.commit()

    s = tablero_service.mensual(db_session, PERIODO)["servicio"]

    assert s["dias_quiebre_instock"] == 2, "se contaron los dias de Talca"
    assert s["repuestos_instock"] == 1


# --- Obsolescencia --------------------------------------------------------------


def test_solo_es_obsoleto_lo_que_tiene_sucesor_confirmado(db_session):
    """Sin sucesor confirmado, FORD nombro un reemplazo que no se puede pedir.

    Llamar obsoleto a ese stock seria acusar sin prueba, y el plan de liquidacion
    saldria con codigos que en realidad siguen siendo los buenos.
    """
    db_session.add_all([
        ReemplazoFord(tenant_id="curifor", producto="17 VIEJO",
                      reemplazado_por="17 NUEVO", sucesor_confirmado=True),
        ReemplazoFord(tenant_id="curifor", producto="17 DUDOSO",
                      reemplazado_por="17 OTRO", sucesor_confirmado=False),
        Sugerido(tenant_id="curifor", producto="17 VIEJO", sucursal_id="LINDEROS",
                 stock_activo_suc=10.0, costo_unitario=5000.0, descripcion="FILTRO"),
        Sugerido(tenant_id="curifor", producto="17 DUDOSO", sucursal_id="LINDEROS",
                 stock_activo_suc=10.0, costo_unitario=5000.0),
    ])
    db_session.commit()

    o = tablero_service.mensual(db_session, PERIODO)["obsolescencia"]

    assert o["n_codigos"] == 1
    assert o["valor_clp"] == 50_000
    assert o["top"][0]["producto"] == "17 VIEJO"


def test_un_codigo_de_baja_sin_stock_no_es_obsolescencia(db_session):
    """No hay plata en riesgo si no queda nada en bodega."""
    db_session.add_all([
        ReemplazoFord(tenant_id="curifor", producto="17 VIEJO",
                      reemplazado_por="17 NUEVO", sucesor_confirmado=True),
        Sugerido(tenant_id="curifor", producto="17 VIEJO", sucursal_id="LINDEROS",
                 stock_activo_suc=0.0, costo_unitario=5000.0),
    ])
    db_session.commit()

    assert tablero_service.mensual(db_session, PERIODO)["obsolescencia"]["n_codigos"] == 0


# --- Lo que no se puede calcular ------------------------------------------------


def test_la_ejecucion_de_compra_se_muestra_vacia_y_explicada(db_session):
    """Esconder el hueco haria creer que el tablero esta completo.

    Es la decision de fondo que la gerencia tiene que tomar: sin registrar la
    orden de compra, estos cuatro indicadores no existen.
    """
    e = tablero_service.mensual(db_session, PERIODO)["ejecucion_compra"]

    assert e["disponible"] is False
    assert len(e["indicadores"]) == 4
    assert "Adherencia al sugerido" in e["indicadores"]
    assert "orden de compra" in e["motivo"].lower()


# --- Salud del dato -------------------------------------------------------------


def test_la_salud_del_dato_cuenta_los_vigentes_que_faltan_en_el_maestro(db_session):
    """Mientras el vigente no exista, ese grupo no se puede comprar por el codigo
    bueno: es trabajo de Repuestos y tiene que estar a la vista."""
    db_session.add_all([
        ReemplazoFord(tenant_id="curifor", producto="17 VIEJO",
                      reemplazado_por="17 NO-EXISTE", sucesor_confirmado=True),
        ReemplazoFord(tenant_id="curifor", producto="17 OTRO",
                      reemplazado_por="17 SI-EXISTE", sucesor_confirmado=True),
        ProductoCatalogo(tenant_id="curifor", producto="17 SI-EXISTE", glosa="OK"),
    ])
    db_session.commit()

    salud = tablero_service.mensual(db_session, PERIODO)["salud_del_dato"]
    fila = next(f for f in salud if "por crear" in f["que"])

    assert fila["valor"] == 1
    assert fila["alerta"] is True


def test_el_periodo_por_defecto_es_el_ultimo_mes_con_datos(db_session):
    """Y no `hoy`: si el job lleva dias caido, el tablero mostraria un mes en
    blanco en vez del ultimo que si tiene dato."""
    _snap(db_session, date(2026, 7, 15), "17 A", "LINDEROS", 0)
    db_session.commit()

    assert tablero_service.periodo_actual(db_session) == "2026-07"


# --- El endpoint ----------------------------------------------------------------


def test_el_endpoint_responde_el_tablero(client, db_session):
    _snap(db_session, date(2026, 8, 4), "17 A", "LINDEROS", 0)
    db_session.commit()

    r = client.get("/api/tablero?periodo=2026-08")

    assert r.status_code == 200, r.text
    d = r.json()
    assert d["periodo"] == "2026-08"
    assert {"servicio", "inventario", "obsolescencia",
            "salud_del_dato", "ejecucion_compra"} <= set(d)


@pytest.mark.parametrize("malo", ["agosto", "2026-13", "2026/08", "26-08"])
def test_un_periodo_mal_escrito_lo_dice_en_vez_de_reventar(client, malo):
    assert client.get(f"/api/tablero?periodo={malo}").status_code == 422


# --- La antiguedad de los datos de FORD ------------------------------------------
#
# La corrida semanal fallo el 31-08-2026 por sesion vencida, dejo incidencia, y se
# supo 13 dias despues. Los avisos ya existian: lo que faltaba era que el dato
# estuviera donde alguien mira.


def _fila_ford(db):
    salud = tablero_service.mensual(db, PERIODO)["salud_del_dato"]
    return next(f for f in salud if "portal de FORD" in f["que"])


def test_muestra_cuantos_dias_tienen_los_datos_de_ford(db_session):
    from datetime import timedelta

    hace_una_semana = (date.today() - timedelta(days=7)).isoformat()
    db_session.add(ReemplazoFord(tenant_id="curifor", producto="17 A",
                                 reemplazado_por="17 B", extraido_en=hace_una_semana))
    db_session.commit()

    f = _fila_ford(db_session)

    assert f["valor"] == 7
    assert f["alerta"] is False, "una semana es lo normal: la corrida es semanal"


def test_avisa_cuando_los_datos_de_ford_pasan_de_una_corrida(db_session):
    """Pasados 10 dias hubo al menos una corrida semanal que no se hizo."""
    from datetime import timedelta

    hace_trece = (date.today() - timedelta(days=13)).isoformat()
    db_session.add(ReemplazoFord(tenant_id="curifor", producto="17 A",
                                 reemplazado_por="17 B", extraido_en=hace_trece))
    db_session.commit()

    f = _fila_ford(db_session)

    assert f["valor"] == 13
    assert f["alerta"] is True


def test_sin_fecha_de_extraccion_tambien_avisa(db_session):
    """No saber cuando se consulto es peor que saber que fue hace mucho."""
    db_session.add(ReemplazoFord(tenant_id="curifor", producto="17 A",
                                 reemplazado_por="17 B", extraido_en=None))
    db_session.commit()

    assert _fila_ford(db_session)["alerta"] is True
