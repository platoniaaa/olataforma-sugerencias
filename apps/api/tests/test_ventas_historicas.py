"""Consulta del historico de ventas desde 2018."""
from src.models import VentaHistorica


def _vh(db_session, periodo, producto, sucursal, cantidad, neto=None, n=1):
    db_session.add(VentaHistorica(
        tenant_id="curifor", periodo=periodo, producto=producto, sucursal=sucursal,
        cantidad=cantidad, neto=neto, n_lineas=n,
    ))
    db_session.commit()


def test_meta_reporta_el_rango_cargado(client, db_session):
    _vh(db_session, "201801", "P1", "LINDEROS", 5)
    _vh(db_session, "202607", "P1", "TALCA", 3)
    m = client.get("/api/ventas-historicas/meta").json()
    assert m["periodo_min"] == "201801"
    assert m["periodo_max"] == "202607"
    assert m["filas"] == 2
    assert set(m["sucursales"]) == {"LINDEROS", "TALCA"}


def test_serie_mensual_suma_las_sucursales(client, db_session):
    _vh(db_session, "202401", "P1", "LINDEROS", 5, neto=5000)
    _vh(db_session, "202401", "P1", "TALCA", 3, neto=3000)
    _vh(db_session, "202402", "P1", "LINDEROS", 2, neto=2000)
    r = client.get("/api/ventas-historicas?producto=P1").json()
    serie = {p["periodo"]: p for p in r["por_periodo"]}
    assert serie["202401"]["cantidad"] == 8
    assert serie["202401"]["neto"] == 8000
    assert serie["202402"]["cantidad"] == 2


def test_filtra_por_rango_de_periodos(client, db_session):
    for p in ("201801", "202001", "202601"):
        _vh(db_session, p, "P1", "LINDEROS", 1)
    r = client.get(
        "/api/ventas-historicas?producto=P1&periodo_desde=201901&periodo_hasta=202512"
    ).json()
    assert [x["periodo"] for x in r["por_periodo"]] == ["202001"]


def test_filtra_por_sucursal(client, db_session):
    _vh(db_session, "202401", "P1", "LINDEROS", 5)
    _vh(db_session, "202401", "P1", "TALCA", 99)
    r = client.get("/api/ventas-historicas?sucursal=LINDEROS").json()
    assert r["detalle"]["total"] == 1
    assert r["detalle"]["items"][0]["cantidad"] == 5


def test_busqueda_parcial_de_producto(client, db_session):
    _vh(db_session, "202401", "83 1025100GH20A", "LINDEROS", 4)
    r = client.get("/api/ventas-historicas?producto=1025100").json()
    assert r["detalle"]["total"] == 1


def test_ranking_por_sucursal(client, db_session):
    _vh(db_session, "202401", "P1", "LINDEROS", 5)
    _vh(db_session, "202401", "P1", "TALCA", 20)
    r = client.get("/api/ventas-historicas?producto=P1").json()
    assert [s["sucursal"] for s in r["por_sucursal"]] == ["TALCA", "LINDEROS"]


def test_avisa_cuando_trunca(client, db_session):
    for i in range(5):
        _vh(db_session, f"20240{i+1}", "P1", "LINDEROS", 1)
    r = client.get("/api/ventas-historicas?producto=P1&limit=2").json()
    assert len(r["detalle"]["items"]) == 2
    assert r["detalle"]["total"] == 5
    assert r["detalle"]["truncado"] is True


def test_export_csv(client, db_session):
    _vh(db_session, "202401", "P1", "LINDEROS", 5, neto=5000)
    r = client.get("/api/ventas-historicas/export-csv?producto=P1")
    assert r.status_code == 200
    texto = r.content.decode("utf-8-sig")
    assert "Periodo;Producto;Sucursal" in texto
    assert "202401;P1;LINDEROS;5.0;5000.0" in texto


def test_oculta_los_conceptos_internos(client, db_session):
    """"D&P CONTRATISTA" trae 10 millones de "unidades" que son montos contables:
    dejarlo visible arruina cualquier ranking de repuestos."""
    _vh(db_session, "202401", "D&P CONTRATISTA-DE", "TALCA", 10_573_448)
    _vh(db_session, "202401", "REPUESTO-1", "TALCA", 5)
    r = client.get("/api/ventas-historicas").json()
    productos = [i["producto"] for i in r["detalle"]["items"]]
    assert productos == ["REPUESTO-1"]

    # Se pueden ver a proposito.
    r2 = client.get("/api/ventas-historicas?incluir_internos=true").json()
    assert len(r2["detalle"]["items"]) == 2


def test_el_historico_no_toca_la_tabla_del_sugerido(client, db_session):
    """`venta_mensual` alimenta la demanda; esta tabla es solo para consulta."""
    from src.models import VentaMensual

    antes = db_session.query(VentaMensual).count()
    _vh(db_session, "202401", "P1", "LINDEROS", 5)
    assert db_session.query(VentaMensual).count() == antes
