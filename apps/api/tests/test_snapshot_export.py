"""Export de la foto diaria del sugerido (GET /api/admin/snapshot/export): el ABC y el
stock de un cierre de mes, que el sugerido (se reemplaza en cada carga) no guarda."""
import csv
import io
from datetime import date

from src.models import ProductoCatalogo, Sugerido, SugeridoSnapshot
from src.services import snapshot_service


def _foto(db, fecha, producto, suc, abc, stock):
    db.add(SugeridoSnapshot(tenant_id="curifor", fecha=fecha, producto=producto, sucursal_id=suc,
                            clasificacion_abc=abc, stock_activo_suc=stock, stock_en_transito_suc=1,
                            punto_de_pedido=3, demanda_diaria=0.5, costo_unitario=100.0,
                            total_sugerido_suc=2))


def _filas(contenido: bytes) -> list[dict]:
    assert contenido.startswith(b"\xef\xbb\xbf"), "UTF-8 con BOM para que Excel lea las tildes"
    return list(csv.DictReader(io.StringIO(contenido.decode("utf-8-sig"))))


def test_exporta_solo_la_fecha_pedida_con_proveedor_y_descripcion(db_session):
    cierre, otro = date(2026, 9, 30), date(2026, 10, 1)
    _foto(db_session, cierre, "P1", "LINDEROS", "A", 10)
    _foto(db_session, cierre, "P1", "TALCA", "B", 4)
    _foto(db_session, otro, "P1", "LINDEROS", "C", 99)
    db_session.add(Sugerido(tenant_id="curifor", producto="P1", sucursal_id="LINDEROS",
                            nombre_sucursal="Linderos", proveedor="PROV UNO"))
    db_session.add(ProductoCatalogo(tenant_id="curifor", producto="P1", glosa="FILTRO ACEITE ñandú"))
    db_session.commit()

    contenido, n = snapshot_service.exportar_foto(db_session, cierre)

    filas = _filas(contenido)
    assert n == 2 and len(filas) == 2
    assert [(f["sucursal_id"], f["clasificacion_abc"], f["stock_activo_suc"]) for f in filas] == [
        ("LINDEROS", "A", "10.0"), ("TALCA", "B", "4.0")]
    assert {f["proveedor"] for f in filas} == {"PROV UNO"}
    assert filas[0]["descripcion"] == "FILTRO ACEITE ñandú"
    assert list(filas[0]) == list(snapshot_service.COLUMNAS_EXPORT)


def test_producto_que_ya_no_esta_en_el_sugerido_sale_con_proveedor_vacio(db_session):
    _foto(db_session, date(2026, 9, 30), "VIEJO", "LINDEROS", "D", 1)
    db_session.commit()

    contenido, n = snapshot_service.exportar_foto(db_session, date(2026, 9, 30))

    assert n == 1 and _filas(contenido)[0]["proveedor"] == ""


def test_sin_foto_de_esa_fecha_la_ruta_responde_404_y_con_foto_baja_el_csv(client, db_session):
    r = client.get("/api/admin/snapshot/export", params={"fecha": "2026-09-30"})
    assert r.status_code == 404 and "No hay foto" in r.json()["detail"]

    _foto(db_session, date(2026, 9, 30), "P1", "LINDEROS", "A", 10)
    db_session.commit()
    r = client.get("/api/admin/snapshot/export", params={"fecha": "2026-09-30"})
    assert r.status_code == 200
    assert r.headers["x-filas"] == "1"
    assert "sugerido_foto_2026-09-30.csv" in r.headers["content-disposition"]
    assert _filas(r.content)[0]["clasificacion_abc"] == "A"


def test_fecha_mal_escrita_es_422(client):
    assert client.get("/api/admin/snapshot/export", params={"fecha": "30-09-2026"}).status_code == 422
