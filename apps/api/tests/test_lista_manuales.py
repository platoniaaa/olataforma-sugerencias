"""La lista de sugerencias manuales tiene que decir QUE se sugirio, no solo el codigo.

La pantalla mostraba "74 1324409TBW0000 · CHILLAN · +1 u" y para saber que repuesto
era habia que ir al catalogo. Ahora la fila trae descripcion, marca, proveedor,
costo, valor y el stock que hay hoy en esa sucursal.

El contexto sale del MISMO camino que llena la grilla del sugerido, asi que las dos
pantallas no pueden contradecirse.
"""
from src.models import ProductoCatalogo, StockUnificado, Sugerido, SugerenciaManual


def _manual(db_session, producto, sucursal_id="LINDEROS", unidades=3, **kw):
    base = dict(
        tenant_id="curifor", producto=producto, sucursal_id=sucursal_id,
        unidades=unidades, creado_por="mramos@curifor.com",
    )
    base.update(kw)
    db_session.add(SugerenciaManual(**base))
    db_session.commit()


def _listar(client):
    r = client.get("/api/sugerencias-manuales", params={"solo_unicas": True})
    assert r.status_code == 200
    return r.json()


def test_la_fila_dice_que_repuesto_es(client, db_session):
    db_session.add(Sugerido(
        tenant_id="curifor", producto="LM-1", descripcion="FILTRO DE ACEITE RANGER",
        sucursal_id="LINDEROS", nombre_sucursal="Linderos", proveedor="Ford Motor Company Chile",
        filtro1_final="FORD", costo_unitario=3000.0, stock_activo_suc=4,
    ))
    db_session.commit()
    _manual(db_session, "LM-1", unidades=3)

    fila = next(f for f in _listar(client) if f["producto"] == "LM-1")
    assert fila["descripcion"] == "FILTRO DE ACEITE RANGER"
    assert fila["marca"] == "FORD"
    assert fila["proveedor"] == "Ford Motor Company Chile"
    assert fila["costo_unitario"] == 3000
    assert fila["valor_clp"] == 9000       # 3 u x 3.000
    assert fila["stock_actual"] == 4
    # El id es "LINDEROS" pero la sucursal se llama "Linderos".
    assert fila["nombre_sucursal"] == "Linderos"


def test_sirve_para_un_producto_que_el_modelo_no_pide(client, db_session):
    """El caso que mas se usa: se carga a mano justo lo que el sugerido no trae."""
    db_session.add(ProductoCatalogo(
        tenant_id="curifor", producto="LM-2", glosa="CORREA ALTERNADOR i20", costo=12000.0,
    ))
    db_session.add(StockUnificado(
        tenant_id="curifor", producto="LM-2", bodega="CHILLAN",
        sucursal_id="CHILLAN", stock=2,
    ))
    db_session.commit()
    _manual(db_session, "LM-2", sucursal_id="CHILLAN", unidades=5)

    fila = next(f for f in _listar(client) if f["producto"] == "LM-2")
    assert fila["descripcion"] == "CORREA ALTERNADOR i20"
    assert fila["costo_unitario"] == 12000
    assert fila["valor_clp"] == 60000
    assert fila["stock_actual"] == 2


def test_un_codigo_que_no_existe_lo_dice_en_vez_de_quedar_vacio(client, db_session):
    """Paso en produccion con `74 1324409TBW0000`, tipeado a mano: la fila salia
    en blanco y parecia un bug de la pantalla."""
    _manual(db_session, "LM-FANTASMA", unidades=1)

    fila = next(f for f in _listar(client) if f["producto"] == "LM-FANTASMA")
    assert fila["descripcion"] == "(codigo no encontrado en el catalogo)"
    assert fila["costo_unitario"] is None
    assert fila["valor_clp"] is None


def test_la_lista_vacia_no_rompe(client, db_session):
    assert _listar(client) == []
