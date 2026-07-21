"""Vista previa del modo 'mantener stock': explicar de donde sale el numero.

Un total sin desglose obliga al usuario a confiar; con el desglose puede
verificar si el dato de stock que ve la plataforma es el que el conoce.
"""
from src.models import StockUnificado, Sugerido


def _sug(db_session, producto, **kw):
    base = dict(
        tenant_id="curifor", producto=producto, sucursal_id="LINDEROS",
        nombre_sucursal="Linderos", pedir="Si",
    )
    base.update(kw)
    db_session.add(Sugerido(**base))
    db_session.commit()


def _preview(client, producto, sucursal, nivel):
    return client.get(
        "/api/sugerencias-manuales/previsualizar-objetivo",
        params={"producto": producto, "sucursal_id": sucursal, "stock_objetivo": nivel},
    ).json()


def test_desglosa_las_tres_partes(client, db_session):
    _sug(db_session, "PV-1", stock_activo_suc=5, stock_en_transito_suc=2,
         total_sugerido_suc=1)
    p = _preview(client, "PV-1", "LINDEROS", 20)
    assert p["stock"] == 5
    assert p["transito"] == 2
    assert p["sugerido_sistema"] == 1
    assert p["cubierto"] == 8
    assert p["faltante"] == 12
    assert p["en_sugerido"] is True
    assert p["desglose"] == "5 en stock + 2 en transito + 1 que ya sugiere el sistema = 8 u"


def test_omite_las_partes_en_cero(client, db_session):
    """Mencionar '0 en transito' es ruido: se muestra solo lo que aporta."""
    _sug(db_session, "PV-2", stock_activo_suc=4)
    p = _preview(client, "PV-2", "LINDEROS", 10)
    assert p["desglose"] == "4 en stock = 4 u"


def test_nombra_las_bodegas_del_stock(client, db_session):
    """Decir "hay 3" sin decir donde deja al usuario sin poder comprobarlo."""
    db_session.add(StockUnificado(
        tenant_id="curifor", producto="PV-BOD", sucursal_id="CD REPUESTOS",
        bodega="CD REPUESTOS", stock=3, origen="Curifor",
    ))
    db_session.commit()
    p = _preview(client, "PV-BOD", "CD REPUESTOS", 3)
    assert p["bodegas"] == [
        {"bodega": "CD REPUESTOS", "stock": 3.0, "origen": "Curifor"}
    ]
    assert p["desglose"] == "3 en stock (CD REPUESTOS: 3) = 3 u"


def test_nivel_cubierto_reporta_cero_faltante(client, db_session):
    _sug(db_session, "PV-3", stock_activo_suc=30)
    p = _preview(client, "PV-3", "LINDEROS", 5)
    assert p["faltante"] == 0
    assert p["cubierto"] == 30


def test_producto_fuera_del_sugerido_usa_la_bodega(client, db_session):
    db_session.add(StockUnificado(
        tenant_id="curifor", producto="PV-4", sucursal_id="CD REPUESTOS",
        bodega="CD REPUESTOS", stock=2,
    ))
    db_session.commit()
    p = _preview(client, "PV-4", "CD REPUESTOS", 3)
    assert p["en_sugerido"] is False
    assert p["stock"] == 2
    assert p["faltante"] == 1


def test_sin_stock_conocido_pide_todo(client):
    p = _preview(client, "PV-NADA", "CD REPUESTOS", 3)
    assert p["cubierto"] == 0
    assert p["faltante"] == 3


def test_el_error_al_guardar_trae_el_desglose(client, db_session):
    """El mensaje tiene que decir CON QUE esta cubierto, no solo que lo esta."""
    _sug(db_session, "PV-5", stock_activo_suc=7, total_sugerido_suc=2)
    r = client.post("/api/sugerencias-manuales", json={
        "producto": "PV-5", "sucursal_id": "LINDEROS", "stock_objetivo": 5,
    })
    assert r.status_code == 409
    detalle = r.json()["detail"]
    assert "7 en stock" in detalle
    assert "2 que ya sugiere el sistema" in detalle
    assert "= 9 u" in detalle


def test_el_error_nombra_la_bodega(client, db_session):
    """El caso real: 3 unidades en el CD que el usuario no veia en ninguna parte."""
    db_session.add(StockUnificado(
        tenant_id="curifor", producto="PV-CD", sucursal_id="CD REPUESTOS",
        bodega="CD REPUESTOS", stock=3, origen="Curifor",
    ))
    db_session.commit()
    r = client.post("/api/sugerencias-manuales", json={
        "producto": "PV-CD", "sucursal_id": "CD REPUESTOS", "stock_objetivo": 3,
    })
    assert r.status_code == 409
    assert "CD REPUESTOS: 3" in r.json()["detail"]


def test_la_regla_se_guarda_aunque_hoy_no_falte_nada(client, db_session):
    """El caso de la jefa: hay 3 en el CD y quiere mantener 3.

    Hoy no hay que comprar, pero la regla tiene que quedar viva para reponer
    cuando el stock baje. Si esto bloqueara, "mantener" no mantendria nada."""
    from datetime import date

    from src.models import SugerenciaManual, SugerenciaRecurrente
    from src.services import recurrentes_service

    db_session.add(StockUnificado(
        tenant_id="curifor", producto="REGLA-CD", sucursal_id="CD REPUESTOS",
        bodega="CD REPUESTOS", stock=3, origen="Curifor",
    ))
    db_session.commit()

    r = client.post("/api/sugerencias-manuales/recurrentes", json={
        "modo": "individual", "producto": "REGLA-CD", "sucursal_id": "CD REPUESTOS",
        "stock_objetivo": 3, "cada_dias": 7, "motivo": "Campana movil",
    })
    assert r.status_code == 201
    assert r.json()["stock_objetivo"] == 3
    # Hoy no se pide nada...
    assert db_session.query(SugerenciaManual).filter_by(producto="REGLA-CD").count() == 0

    # ...pero al bajar el stock, la siguiente ejecucion repone la diferencia.
    fila = db_session.query(StockUnificado).filter_by(producto="REGLA-CD").one()
    fila.stock = 1
    regla = db_session.query(SugerenciaRecurrente).filter_by(producto="REGLA-CD").one()
    regla.proxima_ejecucion = date.today()
    db_session.commit()
    recurrentes_service.procesar(db_session, hoy=date.today())

    inst = db_session.query(SugerenciaManual).filter_by(
        producto="REGLA-CD", archivada=False
    ).one()
    assert inst.unidades == 2


def test_nivel_invalido_rechazado(client):
    r = client.get(
        "/api/sugerencias-manuales/previsualizar-objetivo",
        params={"producto": "X", "sucursal_id": "Y", "stock_objetivo": 0},
    )
    assert r.status_code == 422


def test_decimales_se_muestran_cortos(client, db_session):
    """El stock del BI es float; '5' se lee mejor que '5.0'."""
    _sug(db_session, "PV-6", stock_activo_suc=5.0, stock_en_transito_suc=1.5)
    p = _preview(client, "PV-6", "LINDEROS", 20)
    assert p["desglose"].startswith("5 en stock + 1.5 en transito")
