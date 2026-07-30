"""Regla InStock: los repuestos de pauta nunca bajan del mínimo en las sucursales con taller.

Curifor hace las mantenciones de la pauta del fabricante, así que esos repuestos se
venden sí o sí. El modelo del BI no los pide (clase D, sin venta registrada) y sin
esta regla el comprador no se entera hasta que el auto está en el taller.

Lo que se prueba acá es lo que hace fallar la regla en producción: que se aplique
solo donde hay taller, que no compre encima de lo que ya hay (stock, tránsito,
sugerido o una manual), que la fila APAREZCA aunque "solo pedir" la esconda y que
las tarjetas de arriba cuadren con la tabla de abajo.
"""
from src.models import ProductoCatalogo, RepuestoInstock, Sugerido, SugerenciaManual
from src.services.instock_service import SUCURSALES_INSTOCK


def _sug(db_session, producto, sucursal_id="LINDEROS", **kw):
    base = dict(
        tenant_id="curifor", producto=producto, descripcion=f"Repuesto {producto}",
        sucursal_id=sucursal_id, nombre_sucursal=sucursal_id.title(),
        pedir="No", pedir_flag="No", total_sugerido_suc=0, sugerido_compra_neto=0,
        costo_unitario=1000.0, total_valor_sugerido_clp=0, stock_activo_suc=0,
        stock_en_transito_suc=0, proveedor="Ford Motor Company Chile",
    )
    base.update(kw)
    db_session.add(Sugerido(**base))
    db_session.commit()


def _instock(db_session, producto, minimo=2, modelos="Ranger", marca="FORD"):
    db_session.add(RepuestoInstock(
        tenant_id="curifor", producto=producto, part_number=producto.split(" ")[-1],
        marca=marca, modelos=modelos, operacion="Filtro de Aceite", minimo=minimo,
        activo=True,
    ))
    db_session.commit()


def _grilla(client, **params):
    r = client.get("/api/sugerido", params=params)
    assert r.status_code == 200
    return r.json()


def _fila(client, producto, sucursal_id="LINDEROS", **params):
    items = _grilla(client, limit=5000, **params)["items"]
    coincide = [
        f for f in items
        if f["producto"] == producto and f["sucursal_id"] == sucursal_id
    ]
    assert len(coincide) == 1, f"esperaba 1 fila de {producto}/{sucursal_id}, hay {len(coincide)}"
    return coincide[0]


def _kpis(client, **params):
    r = client.get("/api/sugerido/kpis", params=params)
    assert r.status_code == 200
    return r.json()


def test_marca_el_repuesto_y_completa_el_minimo(client, db_session):
    _sug(db_session, "INS-1")
    _instock(db_session, "INS-1")

    f = _fila(client, "INS-1")
    assert f["instock"] is True
    assert f["instock_modelos"] == "Ranger"
    assert f["instock_minimo"] == 2
    # Stock 0, tránsito 0, sugerido 0 -> hay que comprar las 2 del mínimo.
    assert f["instock_agregado"] == 2
    assert f["total_sugerido_suc"] == 2
    assert f["sugerido_compra_neto"] == 2
    assert f["total_valor_sugerido_clp"] == 2000
    # Y deja de estar escondida tras "solo pedir": si falta, hay que comprarlo.
    assert f["pedir"] == "Si"


def test_la_fila_aparece_aunque_el_modelo_no_la_pida(client, db_session):
    """El caso que justifica la regla: pedir='No' la sacaba del dashboard."""
    _sug(db_session, "INS-OCULTA")
    _instock(db_session, "INS-OCULTA")

    # solo_pedir=True es el default del dashboard, y sin búsqueda que lo anule.
    productos = [f["producto"] for f in _grilla(client, solo_pedir=True, limit=5000)["items"]]
    assert "INS-OCULTA" in productos


def test_no_compra_encima_de_lo_que_ya_hay(client, db_session):
    _sug(db_session, "INS-STOCK", stock_activo_suc=3)          # stock de sobra
    _sug(db_session, "INS-JUSTO", stock_activo_suc=2)          # justo en el mínimo
    _sug(db_session, "INS-TRANSITO", stock_en_transito_suc=2)  # viene en camino
    _sug(db_session, "INS-SUGERIDO", total_sugerido_suc=5, pedir="Si", pedir_flag="Si")
    for p in ("INS-STOCK", "INS-JUSTO", "INS-TRANSITO", "INS-SUGERIDO"):
        _instock(db_session, p)

    for producto, total in [
        ("INS-STOCK", 0), ("INS-JUSTO", 0), ("INS-TRANSITO", 0), ("INS-SUGERIDO", 5),
    ]:
        f = _fila(client, producto, solo_pedir=False)
        assert f["instock"] is True, producto
        assert not f["instock_agregado"], f"{producto} no debería sumar nada"
        assert f["total_sugerido_suc"] == total, producto


def test_solo_completa_el_minimo_en_las_sucursales_con_taller(client, db_session):
    _sug(db_session, "INS-SUC", sucursal_id="LINDEROS")
    _sug(db_session, "INS-SUC", sucursal_id="PLACILLA")
    _instock(db_session, "INS-SUC")

    con_taller = _fila(client, "INS-SUC", "LINDEROS", solo_pedir=False)
    sin_taller = _fila(client, "INS-SUC", "PLACILLA", solo_pedir=False)

    assert con_taller["total_sugerido_suc"] == 2
    # En Placilla la marca es informativa: sirve para reconocer el repuesto, pero
    # el mínimo no la obliga a comprar (no tiene taller de mantención).
    assert sin_taller["instock"] is True
    assert not sin_taller["instock_agregado"]
    assert sin_taller["total_sugerido_suc"] == 0


def test_el_repuesto_sin_fila_en_el_sugerido_igual_se_pide(client, db_session):
    """Sin fila en el BI no hay nada que completar: se fabrica una por sucursal."""
    db_session.add(ProductoCatalogo(
        tenant_id="curifor", producto="INS-SOLO", glosa="Filtro de pauta", costo=1500.0,
    ))
    db_session.commit()
    _instock(db_session, "INS-SOLO")

    items = _grilla(client, limit=5000)["items"]
    filas = {f["sucursal_id"]: f for f in items if f["producto"] == "INS-SOLO"}
    assert set(filas) == set(SUCURSALES_INSTOCK)
    for suc, f in filas.items():
        assert f["origen"] == "instock", suc
        assert f["total_sugerido_suc"] == 2, suc
        assert f["descripcion"] == "Filtro de pauta", suc
        assert f["total_valor_sugerido_clp"] == 3000, suc


def test_la_sugerencia_manual_ya_cubre_el_minimo(client, db_session):
    """La manual y el mínimo no se suman: los dos apuntan al mismo nivel de stock."""
    _sug(db_session, "INS-MAN")
    _instock(db_session, "INS-MAN")
    db_session.add(SugerenciaManual(
        tenant_id="curifor", producto="INS-MAN", sucursal_id="LINDEROS",
        unidades=2, creado_por="test",
    ))
    db_session.commit()

    f = _fila(client, "INS-MAN", solo_pedir=False)
    assert not f["instock_agregado"], "la manual ya deja el stock en el mínimo"
    assert f["total_sugerido_suc"] == 2


def test_la_regla_de_stock_sin_venta_no_pisa_el_minimo(client, db_session):
    """Un repuesto de pauta bajo el mínimo se compra igual: es decisión explícita.

    Sin la protección, la regla de "stock cubre el mes + sin venta" lo marcaba
    pedir='No' y el dashboard volvía a esconderlo, dejando el mínimo en nada.
    """
    from src.models import VentaHistorica
    from src.services.sugerido_service import _mes_anterior_yyyymm

    # Mes anterior cargado (si no, la regla se abstiene y el test no probaría nada).
    db_session.add(VentaHistorica(
        tenant_id="curifor", producto="OTRO", sucursal="LINDEROS",
        periodo=_mes_anterior_yyyymm(), cantidad=1,
    ))
    db_session.commit()
    # Stock 1 cubre la demanda mensual de 0,5 y no hubo venta: la otra regla querría
    # marcar pedir='No'. Pero 1 < 2, así que el mínimo manda.
    _sug(db_session, "INS-CHOQUE", stock_activo_suc=1, demanda_mensual=0.5)
    _instock(db_session, "INS-CHOQUE")

    f = _fila(client, "INS-CHOQUE", solo_pedir=False)
    assert f["pedir"] == "Si"
    assert f["instock_agregado"] == 1
    assert f["total_sugerido_suc"] == 1


def test_los_kpis_cuadran_con_la_tabla(client, db_session):
    """El invariante de siempre: las tarjetas suman lo mismo que se ve abajo."""
    _sug(db_session, "INS-K1")                                   # completa 2
    _sug(db_session, "INS-K2", stock_activo_suc=5)               # ya cubierto
    _sug(db_session, "INS-K3", sucursal_id="CURICO")             # completa 2
    db_session.add(ProductoCatalogo(
        tenant_id="curifor", producto="INS-K4", glosa="Suelto", costo=800.0,
    ))
    db_session.commit()
    for p in ("INS-K1", "INS-K2", "INS-K3", "INS-K4"):
        _instock(db_session, p)

    k = _kpis(client, solo_pedir=False)
    filas = _grilla(client, solo_pedir=False, limit=5000)["items"]

    assert k["n_filas"] == len(filas)
    assert k["total_sugerido"] == sum(f["total_sugerido_suc"] or 0 for f in filas)
    assert k["valor_total_clp"] == sum(f["total_valor_sugerido_clp"] or 0 for f in filas)
    assert k["n_productos"] == len({f["producto"] for f in filas})
    # El mínimo rige en las 4 sucursales con taller, no solo donde el BI tiene fila:
    # K1 2+2·3, K2 0 (stock 5) +2·3, K3 2+2·3 y K4 2·4 = 30 unidades.
    assert k["total_sugerido_instock"] == 30


def test_el_filtro_de_sucursal_con_tilde_no_apaga_la_regla(client, db_session):
    """El filtro va por nombre ("Curicó") y la regla por id ("CURICO")."""
    _sug(db_session, "INS-TILDE", sucursal_id="CURICO", nombre_sucursal="Curicó")
    _instock(db_session, "INS-TILDE")

    f = _fila(client, "INS-TILDE", "CURICO", solo_pedir=False, sucursal="Curicó")
    assert f["instock_agregado"] == 2


def test_la_fila_sin_sugerido_sale_con_sus_columnas(client, db_session, en_catalogo):
    """Una fila que el BI no trae ya no sale en blanco.

    Lo que describe al PRODUCTO (proveedor, marca, importado, precios) se copia de
    la fila del mismo producto en otra sucursal; el stock sale de bodega. Lo que
    depende de la sucursal (ABC local, demanda) NO se copia: seria inventarlo.
    """
    from src.models import StockUnificado

    # El producto existe en el sugerido de Linderos, pero no en el de Curicó.
    _sug(db_session, "INS-COL", sucursal_id="LINDEROS", proveedor="Gildemeister",
         filtro1_final="HYUNDAI", tipo_origen="Importado", es_importado=True,
         unidad_medida="UNIDAD", clasificacion_abc="A", clasificacion_abc_agregada="B",
         demanda_mensual=9.0, costo_unitario=4000.0, stock_activo_suc=50)
    db_session.add(StockUnificado(
        tenant_id="curifor", producto="INS-COL", bodega="CURICO",
        sucursal_id="CURICO", stock=1,
    ))
    db_session.commit()
    _instock(db_session, "INS-COL")

    f = _fila(client, "INS-COL", "CURICO", solo_pedir=False)
    assert f["origen"] == "instock"
    # Copiado del mismo producto en Linderos:
    assert f["proveedor"] == "Gildemeister"
    assert f["filtro1_final"] == "HYUNDAI"
    assert f["tipo_origen"] == "Importado"
    assert f["es_importado"] is True
    assert f["unidad_medida"] == "UNIDAD"
    assert f["clasificacion_abc_agregada"] == "B"
    assert f["costo_unitario"] == 4000
    # Stock real de Curicó (1) y de la otra bodega, desde stock_unificado:
    assert f["stock_activo_suc"] == 1
    assert f["stock_curico"] == 1
    # Falta 1 para llegar a 2, valorizado con el costo heredado:
    assert f["instock_agregado"] == 1
    assert f["total_valor_sugerido_clp"] == 4000
    # Lo que depende de la sucursal NO se copia de Linderos.
    assert f["clasificacion_abc"] is None
    assert f["demanda_mensual"] is None


def test_la_manual_de_un_producto_fuera_del_sugerido_sale_completa(client, db_session):
    """Mismo trato para una sugerencia manual: es el caso que usa Mary a diario."""
    from src.models import ProductoCatalogo, SugerenciaManual

    _sug(db_session, "MAN-COL", sucursal_id="LINDEROS", proveedor="Ford Motor Company Chile",
         filtro1_final="FORD", costo_unitario=2500.0)
    db_session.add(ProductoCatalogo(
        tenant_id="curifor", producto="MAN-COL", glosa="Filtro de aceite",
        procedencia="NACIONAL", unidad="UNIDAD",
    ))
    db_session.add(SugerenciaManual(
        tenant_id="curifor", producto="MAN-COL", sucursal_id="TALCA",
        unidades=3, creado_por="mramos@curifor.com",
    ))
    db_session.commit()

    f = _fila(client, "MAN-COL", "TALCA", solo_pedir=False)
    assert f["origen"] == "manual"
    assert f["proveedor"] == "Ford Motor Company Chile"
    assert f["filtro1_final"] == "FORD"
    # La descripcion la pone el catalogo al armar la fila; el relleno no la pisa.
    assert f["descripcion"] == "Filtro de aceite"
    assert f["tipo_origen"] == "NACIONAL"
    assert f["unidad_medida"] == "UNIDAD"
    assert f["costo_unitario"] == 2500
    assert f["total_sugerido_suc"] == 3
    assert f["total_valor_sugerido_clp"] == 7500


def test_sin_lista_instock_nada_cambia(client, db_session):
    """La regla es opt-in: sin repuestos cargados, el sugerido queda igual."""
    _sug(db_session, "SIN-INS", total_sugerido_suc=7, pedir="Si", pedir_flag="Si")

    f = _fila(client, "SIN-INS", solo_pedir=False)
    assert f["instock"] is False
    assert f["total_sugerido_suc"] == 7
    assert not f["instock_agregado"]
