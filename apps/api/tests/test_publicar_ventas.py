"""El motor publica los meses de venta que a la plataforma le faltan.

Antes esto era un job manual conectado directo a la base. El mes que se pegaba en
el respaldo de Ventas no llegaba nunca a la plataforma salvo que alguien se
acordara de correrlo: julio-2026 se pego el 04-ago y la tabla seguia en junio.
"""
from src.models import VentaHistorica
from src.services import ventas_historicas_service as vh


def _fila(periodo, producto, sucursal, cantidad, neto=None, n=1):
    return {"periodo": periodo, "producto": producto, "sucursal": sucursal,
            "cantidad": cantidad, "neto": neto, "n_lineas": n}


def test_reemplaza_solo_los_periodos_que_vienen(db_session):
    """Recargar un mes corregido no puede llevarse el resto del historico."""
    db = db_session
    db.add_all([
        VentaHistorica(tenant_id="curifor", periodo="202605", producto="P1",
                       sucursal="LINDEROS", cantidad=10),
        VentaHistorica(tenant_id="curifor", periodo="202606", producto="P1",
                       sucursal="LINDEROS", cantidad=20),
    ])
    db.commit()

    r = vh.reemplazar_periodos(db, [_fila("202606", "P1", "LINDEROS", 99)])
    assert r["filas_cargadas"] == 1
    assert r["periodos"] == ["202606"]

    quedan = {(v.periodo, v.cantidad) for v in db.query(VentaHistorica)
              .filter_by(producto="P1").all()}
    assert quedan == {("202605", 10.0), ("202606", 99.0)}, "mayo intacto, junio reemplazado"


def test_una_tanda_vacia_no_borra_nada(db_session):
    db = db_session
    db.add(VentaHistorica(tenant_id="curifor", periodo="202606", producto="P1",
                          sucursal="LINDEROS", cantidad=20))
    db.commit()
    antes = db.query(VentaHistorica).count()

    r = vh.reemplazar_periodos(db, [])
    assert r["filas_cargadas"] == 0
    assert db.query(VentaHistorica).count() == antes


def test_descarta_filas_sin_periodo_valido(db_session):
    """Un periodo mal formado borraria un rango equivocado si se dejara pasar."""
    db = db_session
    r = vh.reemplazar_periodos(db, [
        _fila("202607", "P1", "LINDEROS", 5),
        _fila("2026-07", "P2", "LINDEROS", 5),   # con guion
        _fila("", "P3", "LINDEROS", 5),          # vacio
        _fila("202607", "", "LINDEROS", 5),      # sin producto
    ])
    assert r["filas_cargadas"] == 1
    assert r["ignoradas"] == 3
    assert r["periodos"] == ["202607"]


def test_el_neto_roto_no_bota_la_fila(db_session):
    """La cantidad es el dato; el neto es contexto."""
    db = db_session
    vh.reemplazar_periodos(db, [_fila("202607", "P1", "LINDEROS", 5, neto="no es numero")])
    fila = db.query(VentaHistorica).filter_by(producto="P1").one()
    assert fila.cantidad == 5
    assert fila.neto is None


def test_guarda_la_sucursal_tal_como_viene(db_session):
    """El motor ya publica normalizado; la plataforma NO vuelve a tocar el
    nombre, porque el historico viejo si trae las dos formas y hay que poder
    distinguirlas."""
    db = db_session
    vh.reemplazar_periodos(db, [_fila("202607", "P1", "02 LINDEROS", 5)])
    assert db.query(VentaHistorica).filter_by(producto="P1").one().sucursal == "02 LINDEROS"


def test_el_endpoint_exige_la_lista(client):
    assert client.post("/api/admin/ventas-historicas", json={}).status_code == 400


def test_el_endpoint_carga_y_deja_rastro(client, db_session):
    r = client.post("/api/admin/ventas-historicas", json={
        "filas": [_fila("202607", "P1", "TALCA", 7)],
    })
    assert r.status_code == 200, r.text[:200]
    assert r.json()["filas_cargadas"] == 1

    from src.models import AuditoriaLog
    acciones = {a.accion for a in db_session.query(AuditoriaLog).all()}
    assert "ventas_publicadas" in acciones
