"""La sugerencia manual guarda COMO se pidio, no solo el resultado en unidades.

Sin esto, una fila de "+4 u" no se puede explicar despues: no se sabe si fueron
4 unidades cargadas a mano, la conversion de N dias de inventario o la brecha
para mantener un nivel de stock.
"""
from src.models import Sugerido, SugerenciaManual


def _sug(db_session, producto, **kw):
    base = dict(
        tenant_id="curifor", producto=producto, sucursal_id="LINDEROS",
        nombre_sucursal="Linderos", pedir="Si", total_sugerido_suc=2,
        stock_activo_suc=3, demanda_diaria=2.0,
    )
    base.update(kw)
    db_session.add(Sugerido(**base))
    db_session.commit()


def test_unidades_directas_no_marcan_ningun_criterio(client, db_session):
    _sug(db_session, "T-UNI")
    r = client.post("/api/sugerencias-manuales", json={
        "producto": "T-UNI", "sucursal_id": "LINDEROS", "unidades": 4,
    }).json()
    assert r["unidades"] == 4
    assert r["dias_inventario"] is None
    assert r["stock_objetivo"] is None


def test_dias_de_inventario_queda_registrado(client, db_session):
    _sug(db_session, "T-DIAS")
    r = client.post("/api/sugerencias-manuales", json={
        "producto": "T-DIAS", "sucursal_id": "LINDEROS", "dias_inventario": 3,
    }).json()
    assert r["unidades"] == 6  # 3 dias x 2 u/dia
    assert r["dias_inventario"] == 3
    assert r["stock_objetivo"] is None


def test_stock_objetivo_queda_registrado(client, db_session):
    _sug(db_session, "T-OBJ")
    r = client.post("/api/sugerencias-manuales", json={
        "producto": "T-OBJ", "sucursal_id": "LINDEROS", "stock_objetivo": 20,
    }).json()
    assert r["unidades"] == 15  # 20 - 3 de stock - 2 que ya sugiere el sistema
    assert r["stock_objetivo"] == 20
    assert r["dias_inventario"] is None


def test_la_masiva_marca_el_criterio_en_cada_fila(client, db_session):
    _sug(db_session, "T-MAS-1")
    _sug(db_session, "T-MAS-2")
    client.post("/api/sugerencias-manuales/masiva", json={
        "filtros": {"q": "T-MAS-", "solo_pedir": False}, "stock_objetivo": 12,
    })
    filas = db_session.query(SugerenciaManual).filter(
        SugerenciaManual.producto.like("T-MAS-%")
    ).all()
    assert len(filas) == 2
    assert all(f.stock_objetivo == 12 for f in filas)


def test_la_instancia_recurrente_hereda_el_criterio(client, db_session):
    """La instancia que genera el cron tiene que poder explicarse igual que la manual."""
    _sug(db_session, "T-REC")
    client.post("/api/sugerencias-manuales/recurrentes", json={
        "modo": "individual", "producto": "T-REC", "sucursal_id": "LINDEROS",
        "stock_objetivo": 25, "cada_dias": 7,
    })
    inst = db_session.query(SugerenciaManual).filter_by(producto="T-REC").one()
    assert inst.stock_objetivo == 25
    assert inst.recurrente_id is not None


def test_el_listado_expone_el_criterio_y_el_origen(client, db_session):
    """Es lo que la ficha del producto necesita para etiquetar cada sugerencia."""
    _sug(db_session, "T-LIST")
    client.post("/api/sugerencias-manuales", json={
        "producto": "T-LIST", "sucursal_id": "LINDEROS", "dias_inventario": 5,
    })
    fila = client.get("/api/sugerencias-manuales?producto=T-LIST").json()[0]
    assert fila["dias_inventario"] == 5
    assert "stock_objetivo" in fila
    assert "recurrente_id" in fila
    assert "archivada" in fila
