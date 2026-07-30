"""Una sugerencia manual no puede apuntar a un codigo que no existe en ninguna parte.

El campo Producto del modal es texto libre (el autocomplete ayuda, no obliga). En
produccion se cargo `74 1324409TBW0000` en CHILLAN: ese codigo no esta en el sugerido,
ni en el maestro de 409k productos, ni en el stock. La grilla no tenia de donde sacar
descripcion, proveedor ni costo, asi que mostraba una fila entera en blanco -y el
Excel de compra tambien-: nadie podia saber que producto era ni a quien pedirselo.

La correccion es doble:
- no dejar entrar el codigo (aca);
- y si igual queda una fila sin catalogo (el maestro se recarga y podria perder un
  codigo viejo), decirlo en la descripcion en vez de dejarla vacia.
"""
from src.models import ProductoCatalogo, StockUnificado, Sugerido, SugerenciaManual
from src.services import sugerido_service


def test_codigo_que_no_existe_en_ninguna_parte_se_rechaza(client, db_session):
    r = client.post("/api/sugerencias-manuales", json={
        "producto": "74 1324409TBW0000", "sucursal_id": "LINDEROS", "unidades": 1,
    })
    assert r.status_code == 422
    assert "74 1324409TBW0000" in r.json()["detail"]
    assert db_session.query(SugerenciaManual).count() == 0


def test_el_codigo_del_sugerido_pasa(client, db_session):
    """El producto sembrado por el conftest esta en el sugerido."""
    r = client.post("/api/sugerencias-manuales", json={
        "producto": "20 BXO5W30AA", "sucursal_id": "LINDEROS", "unidades": 3,
    })
    assert r.status_code == 201


def test_el_codigo_solo_del_catalogo_pasa(client, en_catalogo):
    """Caso normal del modo 'mantener stock': producto real que el motor no sugiere."""
    en_catalogo("SOLO-CAT")
    r = client.post("/api/sugerencias-manuales", json={
        "producto": "SOLO-CAT", "sucursal_id": "LINDEROS", "unidades": 2,
    })
    assert r.status_code == 201


def test_el_codigo_solo_con_stock_pasa(client, db_session):
    """Si hay stock cargado, el producto existe aunque el maestro venga desfasado."""
    db_session.add(StockUnificado(
        tenant_id="curifor", producto="SOLO-STOCK", sucursal_id="LINDEROS",
        bodega="LINDEROS", stock=4,
    ))
    db_session.commit()
    r = client.post("/api/sugerencias-manuales", json={
        "producto": "SOLO-STOCK", "sucursal_id": "LINDEROS", "unidades": 2,
    })
    assert r.status_code == 201


def test_la_recurrente_individual_tambien_valida(client, db_session):
    """Sin esto, una regla mala fabricaria una fila en blanco por ciclo, para siempre."""
    r = client.post("/api/sugerencias-manuales/recurrentes", json={
        "modo": "individual", "producto": "NO-EXISTE-XYZ", "sucursal_id": "LINDEROS",
        "unidades": 5, "cada_dias": 7,
    })
    assert r.status_code == 422


def test_la_fila_sin_catalogo_dice_por_que_esta_vacia(client, db_session):
    """Las manuales cargadas antes de la validacion siguen ahi: que no parezcan un bug."""
    db_session.add(SugerenciaManual(
        tenant_id="curifor", producto="HUERFANO-1", sucursal_id="LINDEROS", unidades=1,
    ))
    db_session.commit()
    items = client.get("/api/sugerido?page=1").json()["items"]
    fila = next(i for i in items if i["producto"] == "HUERFANO-1")
    assert fila["descripcion"] == sugerido_service.SIN_CATALOGO


def test_el_aviso_no_tapa_la_descripcion_que_si_se_conoce(client, db_session):
    """`SIN_CATALOGO` es el ULTIMO recurso, despues del enriquecimiento.

    `_completar_filas_sinteticas` saca la descripcion de la fila del mismo producto en
    otra sucursal, de `dim_producto` o del catalogo, y nunca pisa un valor ya puesto.
    Si el aviso se escribiera al construir la fila, ganaria siempre y taparia el dato
    real."""
    from src.models import DimProducto

    db_session.add(DimProducto(
        producto="SOLO-DIM", tenant_id="curifor", descripcion="AMORTIGUADOR TRASERO",
        proveedor="Derco", costo_unitario=1000,
    ))
    db_session.add(SugerenciaManual(
        tenant_id="curifor", producto="SOLO-DIM", sucursal_id="LINDEROS", unidades=2,
    ))
    db_session.commit()
    items = client.get("/api/sugerido?page=1").json()["items"]
    fila = next(i for i in items if i["producto"] == "SOLO-DIM")
    assert fila["descripcion"] == "AMORTIGUADOR TRASERO"
    assert fila["proveedor"] == "Derco"


def test_la_fila_sola_muestra_el_stock_de_la_sucursal(client, db_session, en_catalogo):
    """El BI no tiene la fila, pero el stock por bodega si se conoce: mostrarlo evita
    comprar sobre unidades que ya estan en la sucursal."""
    en_catalogo("CON-STOCK", glosa="REPUESTO CON STOCK")
    db_session.add(StockUnificado(
        tenant_id="curifor", producto="CON-STOCK", sucursal_id="LINDEROS",
        bodega="LINDEROS", stock=7,
    ))
    db_session.add(SugerenciaManual(
        tenant_id="curifor", producto="CON-STOCK", sucursal_id="LINDEROS", unidades=2,
    ))
    db_session.commit()
    items = client.get("/api/sugerido?page=1").json()["items"]
    fila = next(i for i in items if i["producto"] == "CON-STOCK")
    assert fila["descripcion"] == "REPUESTO CON STOCK"
    assert fila["stock_activo_suc"] == 7
    assert fila["total_sugerido_suc"] == 2


def test_producto_existe_no_se_confunde_de_codigo(db_session):
    db_session.add(ProductoCatalogo(
        tenant_id="curifor", producto="ABC-123", glosa="X",
    ))
    db_session.commit()
    assert sugerido_service.producto_existe(db_session, "ABC-123")
    assert not sugerido_service.producto_existe(db_session, "ABC-1234")
    assert not sugerido_service.producto_existe(db_session, "abc-123")
