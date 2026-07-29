"""Vista previa del modo "dias de inventario": de donde sale el numero.

Mismo contrato que la del modo objetivo, mas la demanda diaria y cuantos dias
cubre hoy lo que ya hay — que es como el usuario piensa el problema ("ya tengo
para 50 dias, no me pidas 30 mas").
"""
from src.models import Sugerido


def _sug(db_session, producto, **kw):
    base = dict(
        tenant_id="curifor", producto=producto, sucursal_id="LINDEROS",
        nombre_sucursal="Linderos", pedir="Si", demanda_diaria=2.0,
    )
    base.update(kw)
    db_session.add(Sugerido(**base))
    db_session.commit()


def _preview(client, producto, dias, sucursal="LINDEROS"):
    return client.get(
        "/api/sugerencias-manuales/previsualizar-dias",
        params={"producto": producto, "sucursal_id": sucursal, "dias": dias},
    ).json()


def test_desglosa_el_nivel_y_lo_ya_cubierto(client, db_session):
    _sug(db_session, "PD-1", stock_activo_suc=5, stock_en_transito_suc=2,
         total_sugerido_suc=1)
    p = _preview(client, "PD-1", 10)
    assert p["objetivo"] == 20  # 10 dias x 2 u/dia
    assert p["cubierto"] == 8
    assert p["faltante"] == 12
    assert p["demanda_diaria"] == 2.0
    assert p["dias_cubiertos"] == 4  # 8 u alcanzan para 4 dias
    assert p["sin_demanda"] is False
    assert p["desglose"] == "5 en stock + 2 en transito + 1 que ya sugiere el sistema = 8 u"


def test_cobertura_de_sobra_reporta_cero_faltante(client, db_session):
    _sug(db_session, "PD-2", stock_activo_suc=100)
    p = _preview(client, "PD-2", 30)
    assert p["faltante"] == 0
    assert p["dias_cubiertos"] == 50


def test_sin_demanda_lo_dice_en_vez_de_fallar(client, db_session):
    """La pantalla necesita explicarlo mientras el usuario tipea, no al guardar."""
    _sug(db_session, "PD-3", demanda_diaria=0)
    p = _preview(client, "PD-3", 10)
    assert p["sin_demanda"] is True


def test_producto_fuera_del_sugerido_no_tiene_demanda(client):
    """Sin fila en el sugerido no hay demanda diaria de donde partir."""
    assert _preview(client, "PD-NADA", 10)["sin_demanda"] is True


def test_dias_invalidos_rechazados(client):
    r = client.get(
        "/api/sugerencias-manuales/previsualizar-dias",
        params={"producto": "X", "sucursal_id": "Y", "dias": 0},
    )
    assert r.status_code == 422
