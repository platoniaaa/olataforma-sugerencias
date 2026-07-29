"""Pedir "N dias de inventario" no debe comprar de mas cuando ya hay stock.

Antes el modo dias era ciego al inventario: convertia dias x demanda diaria y esas
unidades se sumaban encima del sugerido del sistema. Un SKU con stock para 50 dias
al que se le pedian 30 terminaba con 30 dias de compra que no hacian falta.

Ahora los dias fijan un NIVEL de cobertura y se pide solo la brecha, descontando lo
mismo que el modo "mantener stock": stock, transito y lo que el sistema ya sugiere.
"""
from datetime import date

from src.models import SugerenciaManual, SugerenciaRecurrente, Sugerido
from src.services import recurrentes_service


def _sug(db_session, producto, **kw):
    base = dict(
        tenant_id="curifor", producto=producto, sucursal_id="LINDEROS",
        nombre_sucursal="Linderos", pedir="Si", demanda_diaria=2.0,
        stock_activo_suc=0, stock_en_transito_suc=0, total_sugerido_suc=0,
    )
    base.update(kw)
    db_session.add(Sugerido(**base))
    db_session.commit()


def _crear(client, producto, dias, sucursal="LINDEROS"):
    return client.post("/api/sugerencias-manuales", json={
        "producto": producto, "sucursal_id": sucursal, "dias_inventario": dias,
    })


def test_sin_stock_pide_los_dias_completos(client, db_session):
    """El caso base no cambia: si no hay nada, hacen falta los dias enteros."""
    _sug(db_session, "D-VACIO")
    assert _crear(client, "D-VACIO", 10).json()["unidades"] == 20  # 10 dias x 2 u/dia


def test_el_stock_existente_se_descuenta(client, db_session):
    _sug(db_session, "D-PARCIAL", stock_activo_suc=12)
    # 10 dias = 20 u de nivel, ya hay 12 -> faltan 8.
    assert _crear(client, "D-PARCIAL", 10).json()["unidades"] == 8


def test_stock_de_sobra_no_pide_nada(client, db_session):
    """Lo que motivo el cambio: 50 dias de stock y se piden 30."""
    _sug(db_session, "D-LLENO", stock_activo_suc=100)
    r = _crear(client, "D-LLENO", 30)
    assert r.status_code == 409
    assert db_session.query(SugerenciaManual).filter_by(producto="D-LLENO").count() == 0


def test_el_error_explica_con_que_esta_cubierto(client, db_session):
    """Un "no hay nada que pedir" sin desglose obliga al usuario a creer."""
    _sug(db_session, "D-MSG", stock_activo_suc=100)
    detalle = _crear(client, "D-MSG", 30).json()["detail"]
    assert "100 en stock" in detalle
    assert "30 dias" in detalle
    assert "50 dias" in detalle  # 100 u / 2 u por dia


def test_descuenta_transito_y_lo_que_ya_sugiere_el_sistema(client, db_session):
    """Sin descontar el sugerido del sistema se compraria dos veces el mismo nivel."""
    _sug(db_session, "D-TRES", stock_activo_suc=4, stock_en_transito_suc=3,
         total_sugerido_suc=5)
    # 10 dias = 20 u; cubierto 4 + 3 + 5 = 12 -> faltan 8.
    assert _crear(client, "D-TRES", 10).json()["unidades"] == 8


def test_demanda_fraccionaria_redondea_hacia_arriba(client, db_session):
    _sug(db_session, "D-FRAC", demanda_diaria=0.7, stock_activo_suc=1)
    # 5 dias x 0.7 = 3.5 -> 4 u de nivel, menos 1 de stock.
    assert _crear(client, "D-FRAC", 5).json()["unidades"] == 3


def test_sin_demanda_diaria_sigue_siendo_400(client, db_session):
    """Sin demanda no hay como convertir dias a unidades; es otro problema."""
    _sug(db_session, "D-SINDEM", demanda_diaria=0)
    r = _crear(client, "D-SINDEM", 10)
    assert r.status_code == 400
    assert "unidades" in r.json()["detail"].lower()


def test_la_masiva_omite_los_que_ya_estan_cubiertos(client, db_session):
    _sug(db_session, "D-MAS-1", stock_activo_suc=0)    # faltan 20
    _sug(db_session, "D-MAS-2", stock_activo_suc=100)  # cubierto
    _sug(db_session, "D-MAS-3", demanda_diaria=0)      # sin demanda
    r = client.post("/api/sugerencias-manuales/masiva", json={
        "filtros": {"q": "D-MAS-", "solo_pedir": False}, "dias_inventario": 10,
    }).json()
    assert r["creadas"] == 1
    assert r["omitidas"] == 2
    fila = db_session.query(SugerenciaManual).filter_by(producto="D-MAS-1").one()
    assert fila.unidades == 20
    assert fila.dias_inventario == 10


def test_la_regla_recurrente_repone_solo_cuando_baja(client, db_session):
    """La cobertura por dias se mantiene sola, igual que el nivel en unidades."""
    _sug(db_session, "D-REC", stock_activo_suc=100)
    r = client.post("/api/sugerencias-manuales/recurrentes", json={
        "modo": "individual", "producto": "D-REC", "sucursal_id": "LINDEROS",
        "dias_inventario": 30, "cada_dias": 7,
    })
    assert r.status_code == 201
    # Hoy hay para 50 dias: no se pide nada...
    assert db_session.query(SugerenciaManual).filter_by(producto="D-REC").count() == 0

    # ...y cuando el stock baja, la siguiente ejecucion pide solo la brecha.
    fila = db_session.query(Sugerido).filter_by(producto="D-REC").one()
    fila.stock_activo_suc = 20
    regla = db_session.query(SugerenciaRecurrente).filter_by(producto="D-REC").one()
    regla.proxima_ejecucion = date.today()
    db_session.commit()
    recurrentes_service.procesar(db_session, hoy=date.today())

    inst = db_session.query(SugerenciaManual).filter_by(
        producto="D-REC", archivada=False
    ).one()
    assert inst.unidades == 40  # 60 u de nivel - 20 de stock
