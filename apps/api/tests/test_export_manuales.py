"""Verifica que las sugerencias manuales lleguen al Excel exportado.

El export tiene dos caminos y hay que cubrir los dos: por filtros (sin ids) y por
ids exactos (los que el usuario dejo visibles en la grilla).
"""
import io

import openpyxl
from src.models import Sugerido, SugerenciaManual


def _sug(db_session, producto, **kw):
    # El BI entrega el valor CLP ya calculado (sugerido x costo); replicarlo es lo
    # que hace realista la fila: con costo y sugerido, el valor nunca viene vacio.
    base = dict(
        tenant_id="curifor", producto=producto, sucursal_id="LINDEROS",
        nombre_sucursal="Linderos", pedir="Si", total_sugerido_suc=10,
        sugerido_compra_neto=10, costo_unitario=1000.0, demanda_mensual=50,
        total_valor_sugerido_clp=10000.0,
    )
    base.update(kw)
    s = Sugerido(**base)
    db_session.add(s)
    db_session.commit()
    db_session.refresh(s)
    return s


def _manual(db_session, producto, unidades, sucursal_id="LINDEROS"):
    db_session.add(SugerenciaManual(
        tenant_id="curifor", producto=producto, sucursal_id=sucursal_id,
        unidades=unidades, creado_por="test",
    ))
    db_session.commit()


def _leer(contenido: bytes) -> list[dict]:
    wb = openpyxl.load_workbook(io.BytesIO(contenido))
    ws = wb.active
    filas = list(ws.iter_rows(values_only=True))
    cabeceras = filas[0]
    return [dict(zip(cabeceras, f)) for f in filas[1:]]


_COLS = ["producto", "total_sugerido_suc", "total_valor_sugerido_clp", "sugerido_compra_neto"]


def test_export_por_filtros_suma_la_manual(client, db_session):
    _sug(db_session, "EXP-1")
    _manual(db_session, "EXP-1", 7)

    r = client.post("/api/sugerido/export-excel", json={
        "filtros": {"q": "EXP-1", "solo_pedir": False}, "columnas": _COLS,
    })
    assert r.status_code == 200
    fila = next(f for f in _leer(r.content) if f["Producto"] == "EXP-1")
    # 10 del sistema + 7 manuales.
    assert fila["Total Sugerido"] == 17
    assert fila["Sugerido Compra Neto"] == 17
    # El valor en CLP tambien se recalcula con las unidades manuales.
    assert fila["Valor Total CLP"] == 17000


def test_export_por_ids_suma_la_manual(client, db_session):
    """Camino que usa la grilla cuando el usuario filtro columnas."""
    s = _sug(db_session, "EXP-2")
    _manual(db_session, "EXP-2", 5)

    r = client.post("/api/sugerido/export-excel", json={
        "filtros": {}, "columnas": _COLS, "ids": [s.id],
    })
    fila = _leer(r.content)[0]
    assert fila["Total Sugerido"] == 15


def test_manual_archivada_no_suma(client, db_session):
    _sug(db_session, "EXP-3")
    db_session.add(SugerenciaManual(
        tenant_id="curifor", producto="EXP-3", sucursal_id="LINDEROS",
        unidades=99, creado_por="test", archivada=True,
    ))
    db_session.commit()

    r = client.post("/api/sugerido/export-excel", json={
        "filtros": {"q": "EXP-3", "solo_pedir": False}, "columnas": _COLS,
    })
    fila = next(f for f in _leer(r.content) if f["Producto"] == "EXP-3")
    assert fila["Total Sugerido"] == 10


def test_manual_de_producto_que_no_esta_en_el_sugerido(client, db_session):
    """Producto que NO viene del BI y solo existe por una sugerencia manual.

    Documenta el comportamiento real: la fila sintetica aparece cuando hay
    busqueda (es la unica forma de que el listado la traiga)."""
    _manual(db_session, "SOLO-MANUAL", 12)

    r = client.post("/api/sugerido/export-excel", json={
        "filtros": {"q": "SOLO-MANUAL", "solo_pedir": False}, "columnas": _COLS,
    })
    productos = [f["Producto"] for f in _leer(r.content)]
    assert "SOLO-MANUAL" in productos


def test_export_del_modo_mantener_stock(client, db_session):
    """Extremo a extremo del modo nuevo: se crea la sugerencia y llega al Excel."""
    _sug(db_session, "EXP-OBJ", total_sugerido_suc=2, sugerido_compra_neto=2,
         stock_activo_suc=3, total_valor_sugerido_clp=2000.0)
    creada = client.post("/api/sugerencias-manuales", json={
        "producto": "EXP-OBJ", "sucursal_id": "LINDEROS", "stock_objetivo": 20,
    })
    assert creada.status_code == 201
    assert creada.json()["unidades"] == 15  # 20 - 3 stock - 2 que ya sugiere

    r = client.post("/api/sugerido/export-excel", json={
        "filtros": {"q": "EXP-OBJ", "solo_pedir": False}, "columnas": _COLS,
    })
    fila = next(f for f in _leer(r.content) if f["Producto"] == "EXP-OBJ")
    # 2 del sistema + 15 manuales = 17, y con el stock de 3 el inventario
    # termina en el nivel pedido (20).
    assert fila["Total Sugerido"] == 17
