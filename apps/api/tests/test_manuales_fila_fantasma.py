"""Una sugerencia manual no debe inventar una fila en blanco si la fila ya existe.

El bug (jul-2026): para decidir si una manual era huerfana, el codigo preguntaba
"¿existe su fila?" mirando el set YA FILTRADO. Desde la pestania "Compra CD", una
manual de Linderos no aparecia entre las filas del CD, se daba por huerfana y se
le fabricaba una fila desde `producto_catalogo` —que no tiene columna de
proveedor— pegada dentro de la compra del CD. En produccion eran 97 filas en
blanco de otras sucursales, todas con su fila buena escondida en otra pestania.

Los tres destinos correctos de una manual:
  - su fila pasa los filtros            -> se suma sobre esa fila
  - su fila existe pero la esconde un toggle -> se muestra la fila REAL igual
  - el producto no esta en el sugerido  -> recien ahi, fila sintetica del catalogo
"""
from src.models import ProductoCatalogo, Sugerido, SugerenciaManual, VentaHistorica
from src.services.sugerido_service import _mes_anterior_yyyymm

PROV = "Ford Motor Company Chile"


def _sug(db_session, producto, sucursal="LINDEROS", total=10, costo=1000.0, **kw):
    base = dict(
        tenant_id="curifor", producto=producto, sucursal_id=sucursal,
        nombre_sucursal=sucursal.title(), pedir="Si", pedir_flag="Si",
        clasificacion_abc="A", proveedor=PROV, costo_unitario=costo,
        total_sugerido_suc=total, sugerido_compra_neto=total,
        total_valor_sugerido_clp=total * costo,
    )
    base.update(kw)
    db_session.add(Sugerido(**base))
    db_session.commit()


def _manual(db_session, producto, unidades, sucursal_id="LINDEROS"):
    db_session.add(SugerenciaManual(
        tenant_id="curifor", producto=producto, sucursal_id=sucursal_id,
        unidades=unidades, creado_por="mary",
    ))
    db_session.commit()


def _filas(client, **params):
    r = client.get("/api/sugerido", params={"limit": 5000, **params})
    assert r.status_code == 200
    return r.json()


def _kpis(client, **params):
    r = client.get("/api/sugerido/kpis", params=params)
    assert r.status_code == 200
    return r.json()


def test_manual_de_sucursal_no_se_cuela_en_la_vista_del_cd(client, db_session):
    _sug(db_session, "FAN-1", sucursal="LINDEROS")
    _sug(db_session, "FAN-2", sucursal="CD REPUESTOS")
    _manual(db_session, "FAN-1", 5, "LINDEROS")

    cd = _filas(client, vista="cd")
    sucs = {f["sucursal_id"] for f in cd["items"]}
    assert sucs == {"CD REPUESTOS"}, f"se colaron filas de otra sucursal: {sucs}"
    assert "FAN-1" not in {f["producto"] for f in cd["items"]}
    assert cd["total"] == len(cd["items"])


def test_la_manual_aparece_en_su_vista_con_los_datos_reales(client, db_session):
    _sug(db_session, "FAN-3", sucursal="LINDEROS", total=23)
    _manual(db_session, "FAN-3", 5, "LINDEROS")

    fila = next(f for f in _filas(client, q="FAN-3")["items"] if f["producto"] == "FAN-3")
    # La fila BUENA: con proveedor y ABC, no la fabricada desde el catalogo.
    assert fila["proveedor"] == PROV
    assert fila["clasificacion_abc"] == "A"
    assert fila["origen"] == "sugerido"
    assert fila["total_sugerido_suc"] == 28  # 23 del modelo + 5 a mano


def test_la_manual_gana_sobre_solo_pedir(client, db_session):
    """Si alguien la cargo a mano, quiere comprarla: el toggle no debe esconderla.

    SIN `q` a proposito: con busqueda activa `solo_pedir` no se aplica, asi que el
    caso no se probaria."""
    _sug(db_session, "FAN-4", sucursal="LINDEROS", total=7, pedir="No", pedir_flag="No")
    _manual(db_session, "FAN-4", 3, "LINDEROS")

    r = _filas(client, solo_pedir=True)
    fila = next(f for f in r["items"] if f["producto"] == "FAN-4")
    assert fila["proveedor"] == PROV          # con sus datos, no en blanco
    assert fila["clasificacion_abc"] == "A"
    assert fila["total_sugerido_suc"] == 10   # 7 + 3
    assert fila["pedir"] == "Si"
    assert r["total"] == len(r["items"])


def test_sin_manual_el_toggle_sigue_escondiendo(client, db_session):
    """Contraparte: el rescate es solo para las que tienen manual."""
    _sug(db_session, "FAN-9", sucursal="LINDEROS", total=7, pedir="No", pedir_flag="No")

    r = _filas(client, solo_pedir=True)
    assert "FAN-9" not in {f["producto"] for f in r["items"]}


def test_producto_fuera_del_sugerido_si_lleva_fila_sintetica(client, db_session):
    """El caso para el que se invento la fila sintetica: aca si corresponde."""
    db_session.add(ProductoCatalogo(
        tenant_id="curifor", producto="FAN-5", glosa="Repuesto suelto", costo=2500.0,
    ))
    db_session.commit()
    _manual(db_session, "FAN-5", 4, "LINDEROS")

    fila = next(f for f in _filas(client, q="FAN-5")["items"] if f["producto"] == "FAN-5")
    assert fila["origen"] == "manual"
    assert fila["total_sugerido_suc"] == 4
    assert fila["proveedor"] is None  # el catalogo del ERP no guarda proveedor


def test_la_regla_de_stock_sin_venta_no_pisa_una_manual(client, db_session):
    """"Tiene stock y no vendio -> no pedir" no puede tumbar una orden explicita."""
    mes = _mes_anterior_yyyymm()
    # Con al menos una fila del mes, la regla deja de abstenerse y se aplica.
    db_session.add(VentaHistorica(
        tenant_id="curifor", producto="OTRO", sucursal="LINDEROS",
        periodo=mes, cantidad=1,
    ))
    db_session.commit()
    # Stock (100) cubre la demanda mensual (10) y no vendio el mes pasado.
    comun = dict(stock_activo_suc=100, demanda_mensual=10)
    _sug(db_session, "REG-1", sucursal="LINDEROS", **comun)
    _sug(db_session, "REG-2", sucursal="LINDEROS", **comun)
    _manual(db_session, "REG-2", 4, "LINDEROS")

    filas = {f["producto"]: f for f in _filas(client, solo_pedir=False)["items"]}
    assert filas["REG-1"]["pedir"] == "No"   # la regla se aplica...
    assert filas["REG-2"]["pedir"] == "Si"   # ...pero no sobre la que tiene manual


def test_buscar_por_descripcion_no_borra_las_unidades_manuales(client, db_session):
    """La misma fila tiene que dar lo mismo se la busque como se la busque.

    `_manuales_por_par` filtraba por `producto ILIKE %q%`, pero la busqueda global
    matchea tambien descripcion, sucursal, proveedor y marca: buscando por
    descripcion el diccionario quedaba vacio y las unidades manuales se perdian.
    Medido en produccion: 53 unidades por codigo vs 17 por descripcion."""
    _sug(db_session, "BUS-1", sucursal="LINDEROS", total=17, descripcion="ACEITE MOTOR 5W20")
    _manual(db_session, "BUS-1", 36, "LINDEROS")

    def total(q):
        r = _filas(client, q=q, solo_pedir=False)
        return next(f["total_sugerido_suc"] for f in r["items"] if f["producto"] == "BUS-1")

    assert total("BUS-1") == 53                 # por codigo
    assert total("ACEITE MOTOR 5W20") == 53     # por descripcion
    assert total("Linderos") == 53              # por sucursal
    assert total(PROV) == 53                    # por proveedor


def test_los_kpis_tambien_cuentan_las_manuales_al_buscar_por_sucursal(client, db_session):
    _sug(db_session, "BUS-2", sucursal="LINDEROS", total=10)
    _manual(db_session, "BUS-2", 8, "LINDEROS")

    k = _kpis(client, q="Linderos", solo_pedir=False)
    assert k["total_sugerido_manual"] == 8


def test_una_manual_huerfana_no_aparece_en_una_busqueda_ajena(client, db_session):
    """La fila sintetica SI se acota a la busqueda: es una fila que se agrega."""
    _sug(db_session, "BUS-3", sucursal="LINDEROS", total=10, descripcion="FILTRO DE AIRE")
    db_session.add(ProductoCatalogo(
        tenant_id="curifor", producto="HUE-1", glosa="CORREA DENTADA", costo=100.0,
    ))
    db_session.commit()
    _manual(db_session, "HUE-1", 4, "LINDEROS")

    assert "HUE-1" not in {f["producto"] for f in _filas(client, q="FILTRO DE AIRE")["items"]}
    # ...pero si aparece cuando la busqueda le corresponde.
    assert "HUE-1" in {f["producto"] for f in _filas(client, q="CORREA")["items"]}
    assert "HUE-1" in {f["producto"] for f in _filas(client, q="HUE-")["items"]}


def test_los_kpis_siguen_cuadrando_con_la_tabla(client, db_session):
    _sug(db_session, "FAN-6", sucursal="LINDEROS", total=23)
    _sug(db_session, "FAN-7", sucursal="LINDEROS", total=7, pedir="No", pedir_flag="No")
    db_session.add(ProductoCatalogo(
        tenant_id="curifor", producto="FAN-8", glosa="Suelto", costo=300.0,
    ))
    db_session.commit()
    _manual(db_session, "FAN-6", 5, "LINDEROS")   # sobre fila visible
    _manual(db_session, "FAN-7", 3, "LINDEROS")   # sobre fila escondida por el toggle
    _manual(db_session, "FAN-8", 4, "LINDEROS")   # sin fila en el sugerido

    # Sin `q`: con busqueda activa `solo_pedir` no se aplica y el caso de FAN-7
    # (la rescatada) no se probaria. Los totales incluyen la fila del seed.
    k = _kpis(client, solo_pedir=True)
    filas = _filas(client, solo_pedir=True)["items"]

    assert k["n_filas"] == len(filas)
    assert k["total_sugerido"] == sum(f["total_sugerido_suc"] or 0 for f in filas)
    assert k["valor_total_clp"] == sum(f["total_valor_sugerido_clp"] or 0 for f in filas)
    assert k["n_productos"] == len({f["producto"] for f in filas})
    # El desglose cuenta SOLO las unidades cargadas a mano, no el sugerido del modelo.
    assert k["total_sugerido_manual"] == 12
