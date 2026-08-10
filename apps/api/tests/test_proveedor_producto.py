"""A quien se le compra cada producto, para las filas que el motor no calcula.

El proveedor se DEDUCE de las ordenes de compra historicas. El motor ya lo hacia,
pero solo para los pares producto x sucursal que evalua, y viajaba dentro de la
tabla `sugerido`. Las filas que la plataforma inyecta despues —minimo InStock y
sugerencias manuales— quedaban en blanco.

Caso real (10-08-2026): de 114 filas sin proveedor, 14 eran productos con OC
conocidas. `25 KV6Z9155D` tenia 78 ordenes a FORD y salia con la celda vacia. No
es cosmetico: `compras_service` filtra por `proveedor IS NOT NULL`, asi que esas
lineas no llegaban a ningun carro de compra.
"""
from src.models import ProductoCatalogo, RepuestoInstock, Sugerido
from src.services import proveedor_producto_service as svc
from src.services import sugerido_service


# --- La tabla -------------------------------------------------------------------

def test_publica_y_consulta(db_session):
    resumen = svc.reemplazar(db_session, [{"producto": "25 KV6Z9155D", "proveedor": "FORD MOTOR"}])
    assert resumen["filas_cargadas"] == 1
    assert svc.mapa(db_session, ["25 KV6Z9155D"]) == {"25 KV6Z9155D": "FORD MOTOR"}


def test_es_una_foto_no_un_historico(db_session):
    """Cada corrida reemplaza la anterior: si un producto deja de comprarse, se va."""
    svc.reemplazar(db_session, [{"producto": "25 VIEJO", "proveedor": "FORD MOTOR"}])
    svc.reemplazar(db_session, [{"producto": "25 NUEVO", "proveedor": "GILDEMEISTER"}])
    assert svc.mapa(db_session, ["25 VIEJO", "25 NUEVO"]) == {"25 NUEVO": "GILDEMEISTER"}


def test_ignora_las_filas_incompletas(db_session):
    resumen = svc.reemplazar(db_session, [
        {"producto": "25 OK", "proveedor": "FORD MOTOR"},
        {"producto": "", "proveedor": "FORD MOTOR"},
        {"producto": "25 SINPROV", "proveedor": ""},
        {"producto": "25 NULO", "proveedor": None},
    ])
    assert resumen["filas_cargadas"] == 1
    assert resumen["ignoradas"] == 3


def test_si_el_producto_viene_repetido_gana_el_primero(db_session):
    """El motor ya desempato con la misma regla del sugerido; elegir de nuevo aca
    abriria la puerta a dos verdades distintas para el mismo repuesto."""
    svc.reemplazar(db_session, [
        {"producto": "25 DOBLE", "proveedor": "FORD MOTOR"},
        {"producto": "25 DOBLE", "proveedor": "OTRO PROVEEDOR"},
    ])
    assert svc.mapa(db_session, ["25 DOBLE"]) == {"25 DOBLE": "FORD MOTOR"}


def test_pedir_el_mapa_de_nada_no_consulta(db_session):
    assert svc.mapa(db_session, []) == {}
    assert svc.mapa(db_session, ["", None]) == {}


# --- El endpoint que usa el motor -----------------------------------------------

def test_el_motor_lo_publica(client):
    r = client.post("/api/admin/proveedor-producto", json={
        "filas": [{"producto": "25 KV6Z9155D", "proveedor": "FORD MOTOR COMPANY CHILE SPA"}],
    })
    assert r.status_code == 200
    assert r.json()["filas_cargadas"] == 1


def test_sin_la_lista_de_filas_es_400(client):
    assert client.post("/api/admin/proveedor-producto", json={}).status_code == 400


# --- Lo que se venia a arreglar --------------------------------------------------

def _instock(db_session, producto, minimo=2):
    db_session.add(RepuestoInstock(
        tenant_id="curifor", producto=producto, part_number=producto.split(" ")[-1],
        marca="FORD", modelos="Ranger", operacion="Filtro de Aceite", minimo=minimo,
        activo=True,
    ))
    db_session.add(ProductoCatalogo(
        tenant_id="curifor", producto=producto, glosa=f"Repuesto {producto}", costo=1000.0,
    ))
    db_session.commit()


def _fila_instock(client, producto, sucursal_id="LINDEROS"):
    r = client.get("/api/sugerido", params={"limit": 5000, "solo_pedir": "false"})
    assert r.status_code == 200
    coincide = [
        f for f in r.json()["items"]
        if f["producto"] == producto and f["sucursal_id"] == sucursal_id
    ]
    assert len(coincide) == 1, f"esperaba 1 fila de {producto}/{sucursal_id}, hay {len(coincide)}"
    return coincide[0]


def test_la_fila_instock_recibe_el_proveedor_deducido(db_session, client):
    """El nucleo del arreglo: producto que NO esta en el sugerido, con OC conocidas."""
    _instock(db_session, "25 KV6Z9155D")
    assert _fila_instock(client, "25 KV6Z9155D").get("proveedor") in (None, "")

    svc.reemplazar(db_session, [{"producto": "25 KV6Z9155D", "proveedor": "FORD MOTOR"}])
    assert _fila_instock(client, "25 KV6Z9155D")["proveedor"] == "FORD MOTOR"


def test_no_pisa_el_proveedor_que_la_fila_ya_trae(db_session, client):
    """Lo que viene del motor manda: es la deduccion por sucursal, mas precisa que
    la global."""
    _instock(db_session, "25 CONPROV")
    db_session.add(Sugerido(
        tenant_id="curifor", producto="25 CONPROV", descripcion="Repuesto",
        sucursal_id="CHILLAN", nombre_sucursal="Chillan", pedir="No", pedir_flag="No",
        total_sugerido_suc=0, costo_unitario=1000.0, proveedor="EL DEL MOTOR",
    ))
    db_session.commit()
    svc.reemplazar(db_session, [{"producto": "25 CONPROV", "proveedor": "EL DEDUCIDO"}])
    assert _fila_instock(client, "25 CONPROV")["proveedor"] == "EL DEL MOTOR"


def test_sin_la_tabla_cargada_la_fila_sale_igual(db_session, client):
    """La grilla no puede depender de que el motor haya publicado esto."""
    _instock(db_session, "25 SINTABLA")
    fila = _fila_instock(client, "25 SINTABLA")
    assert fila["producto"] == "25 SINTABLA"
    assert fila.get("proveedor") in (None, "")


def test_un_producto_ajeno_no_contagia_su_proveedor(db_session, client):
    _instock(db_session, "25 MIO")
    svc.reemplazar(db_session, [{"producto": "25 AJENO", "proveedor": "OTRO"}])
    assert _fila_instock(client, "25 MIO").get("proveedor") in (None, "")


def test_con_proveedor_la_linea_entra_al_carro_de_compra(db_session, client):
    """El para que de todo esto: `compras_service` filtra por proveedor IS NOT NULL.

    Se compara contra el MISMO producto sin la tabla publicada, para que el test
    falle si el filtro del carro cambia y deja de depender del proveedor.
    """
    db_session.add(Sugerido(
        tenant_id="curifor", producto="25 PARAELCARRO", descripcion="Repuesto",
        sucursal_id="LINDEROS", nombre_sucursal="Linderos", pedir="Si", pedir_flag="Si",
        total_sugerido_suc=5, sugerido_compra_neto=5, costo_unitario=1000.0,
        proveedor=None,
    ))
    db_session.commit()

    def en_el_carro() -> bool:
        r = client.get("/api/compras/carros")
        assert r.status_code == 200
        return any(
            linea["producto"] == "25 PARAELCARRO"
            for carro in r.json()["carros"] for linea in carro["lineas"]
        )

    assert not en_el_carro(), "sin proveedor no deberia entrar (esa es la falla)"

    fila = db_session.query(Sugerido).filter_by(producto="25 PARAELCARRO").one()
    fila.proveedor = "FORD MOTOR"
    db_session.commit()
    assert en_el_carro(), "con proveedor tiene que entrar al carro"
