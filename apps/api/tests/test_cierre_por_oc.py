"""Lo de una sola vez se cierra solo cuando aparece su OC en el ERP (08-10-2026).

Nadie aprieta "Marcar como pedido": sin esto, una sugerencia de una sola vez seguia
sumando despues de comprada y la descarga del sugerido de unos dias despues la
volvia a pedir. El motor manda las OC de los ultimos 90 dias y se cierra la
sugerencia con la primera OC que cumple: mismo producto y sucursal, fecha igual o
posterior al dia en que se creo, y al menos esas unidades.
"""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from src.models import AuditoriaLog, SugerenciaManual, SugerenciaRecurrente, Sugerido
from src.services import oc_service

PROD = "25 DG9Z8100A"
CHILE = ZoneInfo("America/Santiago")


def _hoy() -> date:
    return datetime.now(CHILE).date()


def _sug(db_session, producto=PROD, sucursal="LINDEROS"):
    db_session.add(Sugerido(
        tenant_id="curifor", producto=producto, sucursal_id=sucursal,
        nombre_sucursal=sucursal.title(), pedir="Si", demanda_diaria=0.8,
        stock_activo_suc=5, stock_en_transito_suc=2, total_sugerido_suc=3,
    ))
    db_session.commit()


def _manual(client, unidades=7, producto=PROD, sucursal="LINDEROS"):
    r = client.post("/api/sugerencias-manuales",
                    json={"producto": producto, "sucursal_id": sucursal, "unidades": unidades})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _oc(n_oc="5758", fecha=None, cantidad=10, producto=PROD, sucursal="LINDEROS",
        motivo="COMPRA CALZADA"):
    return {"producto": producto, "sucursal_id": sucursal, "n_oc": n_oc,
            "fecha_oc": (fecha or _hoy()).isoformat(), "cantidad": cantidad,
            "motivo": motivo, "origen": "Curifor Nacional"}


def _publicar(client, filas, **extra):
    r = client.post("/api/admin/oc-recientes", json={"filas": filas, **extra})
    assert r.status_code == 200, r.text
    return r.json()


def _fila(db_session, id_):
    db_session.expire_all()
    return db_session.get(SugerenciaManual, id_)


def test_la_oc_que_cumple_la_cierra_y_queda_anotada(client, db_session):
    _sug(db_session)
    id_ = _manual(client)

    r = _publicar(client, [_oc()])

    assert r["sugerencias_cerradas"] == 1
    s = _fila(db_session, id_)
    assert s.archivada is True
    assert (s.cerrada_por_oc, s.cerrada_oc_fecha, s.cerrada_oc_unidades) == ("5758", _hoy(), 10)
    assert s.cerrada_en is not None
    assert db_session.query(AuditoriaLog).filter_by(accion="cerrada_por_oc").count() == 1
    # La pagina la muestra con la OC que la cerro, para poder revisarla.
    lista = client.get("/api/sugerencias-manuales/cerradas-por-oc").json()
    assert [(x["id"], x["cerrada_por_oc"], x["cerrada_oc_unidades"]) for x in lista] == [
        (id_, "5758", 10)
    ]
    # Y ya no esta entre las vigentes.
    assert client.get("/api/sugerencias-manuales?solo_unicas=true").json() == []


def test_una_oc_anterior_a_la_sugerencia_no_la_cierra(client, db_session):
    _sug(db_session)
    id_ = _manual(client)
    assert _publicar(client, [_oc(fecha=_hoy() - timedelta(days=1))])["sugerencias_cerradas"] == 0
    assert _fila(db_session, id_).archivada is False


def test_una_oc_con_menos_unidades_no_la_cierra(client, db_session):
    _sug(db_session)
    id_ = _manual(client, unidades=7)
    assert _publicar(client, [_oc(cantidad=5)])["sugerencias_cerradas"] == 0
    assert _fila(db_session, id_).archivada is False


def test_las_lineas_de_una_misma_oc_se_suman(client, db_session):
    _sug(db_session)
    id_ = _manual(client, unidades=7)
    assert _publicar(client, [_oc(cantidad=3), _oc(cantidad=4)])["sugerencias_cerradas"] == 1
    assert _fila(db_session, id_).cerrada_oc_unidades == 7


def test_otra_sucursal_u_otro_producto_no_la_cierran(client, db_session):
    _sug(db_session)
    id_ = _manual(client)
    r = _publicar(client, [_oc(sucursal="CURICO"), _oc(producto="20 XO5W30BA")])
    assert r["sugerencias_cerradas"] == 0
    assert _fila(db_session, id_).archivada is False


def test_la_cierra_la_primera_oc_que_cumple(client, db_session):
    _sug(db_session)
    id_ = _manual(client, unidades=7)
    manana = _hoy() + timedelta(days=1)
    _publicar(client, [
        _oc(n_oc="6200", fecha=manana, cantidad=20),
        _oc(n_oc="6000", cantidad=3),       # muy chica
        _oc(n_oc="6100", cantidad=8),       # la primera que cumple
    ])
    assert _fila(db_session, id_).cerrada_por_oc == "6100"


def test_el_codigo_y_la_sucursal_se_comparan_sin_espacios_ni_mayusculas(client, db_session):
    _sug(db_session)
    id_ = _manual(client)
    _publicar(client, [_oc(producto=" 25 dg9z8100a ", sucursal="linderos")])
    assert _fila(db_session, id_).archivada is True


def test_previsualizar_dice_cuales_sin_cerrar_nada(client, db_session):
    _sug(db_session)
    id_ = _manual(client)
    r = _publicar(client, [_oc()], previsualizar=True)
    assert r["sugerencias_cerradas"] == 0
    assert [(x["id"], x["n_oc"]) for x in r["a_cerrar"]] == [(id_, "5758")]
    assert _fila(db_session, id_).archivada is False
    assert db_session.query(AuditoriaLog).filter_by(accion="cerrada_por_oc").count() == 0


def test_no_toca_las_reglas_ni_las_vencidas(client, db_session):
    """La regla se recalcula con lo que viene en camino; la vencida ya no suma."""
    _sug(db_session)
    client.post("/api/sugerencias-manuales/recurrentes", json={
        "modo": "individual", "producto": PROD, "sucursal_id": "LINDEROS",
        "stock_objetivo": 12, "cada_dias": 1,
    })
    vencida = _manual(client, unidades=1)
    s = _fila(db_session, vencida)
    s.expira_en = datetime.now(timezone.utc) - timedelta(hours=1)
    db_session.commit()

    assert _publicar(client, [_oc(cantidad=50)])["sugerencias_cerradas"] == 0
    instancia = db_session.query(SugerenciaManual).filter(
        SugerenciaManual.recurrente_id.isnot(None)
    ).one()
    assert instancia.archivada is False
    assert db_session.query(SugerenciaRecurrente).filter_by(activa=True).count() == 1


def test_sin_la_lista_de_filas_responde_400(client):
    assert client.post("/api/admin/oc-recientes", json={}).status_code == 400


def test_el_dia_de_la_sugerencia_es_el_de_chile():
    """Creada el lunes a las 23:30 en Chile ya es martes en UTC: la OC del lunes cuenta."""
    lunes = date(2026, 10, 5)
    noche = datetime.combine(lunes, time(23, 30), tzinfo=CHILE).astimezone(timezone.utc)
    assert noche.date() == lunes + timedelta(days=1)
    assert oc_service.dia_chile(noche) == lunes
    # Una fecha sin zona se toma como UTC, que es como la guarda la base.
    assert oc_service.dia_chile(noche.replace(tzinfo=None)) == lunes
