"""Agregar repuestos InStock a mano desde la plataforma.

La lista salia solo de las pautas del fabricante. Abastecimiento necesita poder
sumar un repuesto que no esta en la pauta pero que en la practica no puede
faltar en el taller.

**El riesgo que define el diseño**: `cargar_instock` BORRA la tabla entera y la
reinserta desde el CSV, y desde ago-2026 esa carga se dispara sola en cada
corrida del motor. Sin la columna `origen`, un repuesto agregado a mano
desapareceria el mismo dia sin que nadie lo note. Por eso el primer test de este
archivo es el de la recarga, y no el de agregar.
"""
import pytest

from src.jobs import cargar_instock
from src.models import ProductoCatalogo, RepuestoInstock, Sugerido
from src.services import instock_service


@pytest.fixture()
def catalogo(db_session):
    """Dos productos en el maestro: uno de pauta y otro que se agrega a mano."""
    db_session.add_all([
        ProductoCatalogo(tenant_id="curifor", producto="17 DE-PAUTA",
                         glosa="FILTRO DE PAUTA"),
        ProductoCatalogo(tenant_id="curifor", producto="19 A-MANO",
                         glosa="CORREA QUE NO PUEDE FALTAR"),
    ])
    db_session.commit()
    return db_session


PAUTA = [{"part_number": "DE-PAUTA", "marca": "FORD", "modelos": "Transit",
          "operacion": "Filtro", "detalle": ""}]


# --- Lo primero: sobrevivir a la recarga ----------------------------------------


def test_la_recarga_de_la_pauta_no_borra_lo_agregado_a_mano(catalogo):
    """Es la razon de ser de la columna `origen`.

    La carga borra la tabla entera antes de reinsertar, y corre sola en cada
    corrida del motor. Si se llevara lo manual, el repuesto agregado hoy no
    llegaria a mañana.
    """
    instock_service.agregar_manual(
        catalogo, producto="19 A-MANO", minimo=3,
        motivo="se quiebra siempre", email="ana@curifor.com")

    cargar_instock.cargar_en(catalogo, PAUTA)

    lista = {f["producto"]: f for f in instock_service.listar(catalogo)}
    assert "19 A-MANO" in lista, "la recarga se llevo el repuesto manual"
    assert lista["19 A-MANO"]["minimo"] == 3
    assert lista["19 A-MANO"]["motivo"] == "se quiebra siempre"
    assert "17 DE-PAUTA" in lista


def test_la_recarga_si_renueva_lo_de_la_pauta(catalogo):
    """La otra mitad: lo del fabricante se reemplaza entero, como antes."""
    cargar_instock.cargar_en(catalogo, PAUTA)
    r = cargar_instock.cargar_en(catalogo, [])

    assert r["productos"] == 0
    assert [f["producto"] for f in instock_service.listar(catalogo)] == []


def test_si_la_pauta_incorpora_un_codigo_manual_manda_la_pauta(catalogo):
    """El fabricante gana, y ademas el indice unico no admite las dos filas.

    Se informa cuales fueron absorbidos: dejan de estar bajo la responsabilidad
    de quien los agrego.
    """
    instock_service.agregar_manual(
        catalogo, producto="17 DE-PAUTA", minimo=5, motivo="lo pidio el taller",
        email="ana@curifor.com")

    r = cargar_instock.cargar_en(catalogo, PAUTA)

    assert r["manuales_absorbidos_por_la_pauta"] == ["17 DE-PAUTA"]
    lista = {f["producto"]: f for f in instock_service.listar(catalogo)}
    assert lista["17 DE-PAUTA"]["origen"] == "pauta"


# --- Agregar y quitar -----------------------------------------------------------


def test_agregar_deja_el_repuesto_en_la_lista(catalogo, client):
    r = client.post("/api/instock", json={
        "producto": "19 A-MANO", "minimo": 4, "motivo": "no puede faltar"})

    assert r.status_code == 201, r.text
    fila = next(f for f in instock_service.listar(catalogo)
                if f["producto"] == "19 A-MANO")
    assert fila["origen"] == "manual"
    assert fila["minimo"] == 4
    assert fila["motivo"] == "no puede faltar"
    assert fila["creado_por"]


def test_un_codigo_que_el_erp_no_conoce_se_rechaza(catalogo, client):
    """Dejarlo entrar solo produciria una fila pidiendo algo que no se puede comprar."""
    r = client.post("/api/instock", json={"producto": "99 NO-EXISTE", "minimo": 2})

    assert r.status_code == 404


def test_agregar_algo_que_ya_estaba_ajusta_en_vez_de_fallar(catalogo, client):
    """Que el comprador tenga que adivinar si ya estaba no aporta nada."""
    client.post("/api/instock", json={"producto": "19 A-MANO", "minimo": 2})

    r = client.post("/api/instock", json={"producto": "19 A-MANO", "minimo": 6})

    assert r.status_code == 201
    assert r.json()["ya_estaba"] is True
    fila = next(f for f in instock_service.listar(catalogo)
                if f["producto"] == "19 A-MANO")
    assert fila["minimo"] == 6


def test_quitar_uno_manual(catalogo, client):
    client.post("/api/instock", json={"producto": "19 A-MANO", "minimo": 2})

    r = client.delete("/api/instock/19 A-MANO")

    assert r.status_code == 204
    assert not [f for f in instock_service.listar(catalogo)
                if f["producto"] == "19 A-MANO"]


def test_no_se_puede_quitar_uno_de_la_pauta(catalogo, client):
    """La proxima carga lo repondria: el boton estaria mintiendo."""
    cargar_instock.cargar_en(catalogo, PAUTA)

    r = client.delete("/api/instock/17 DE-PAUTA")

    assert r.status_code == 409
    assert "pauta" in r.json()["detail"].lower()
    assert [f for f in instock_service.listar(catalogo)
            if f["producto"] == "17 DE-PAUTA"]


# --- Que sirva de verdad --------------------------------------------------------


def test_el_repuesto_agregado_a_mano_obliga_la_compra(catalogo, client):
    """Vale lo mismo que uno de la pauta: sin esto la funcionalidad no hace nada."""
    catalogo.add(Sugerido(tenant_id="curifor", producto="19 A-MANO",
                          sucursal_id="LINDEROS", stock_activo_suc=0.0,
                          total_sugerido_suc=0.0, pedir="No"))
    catalogo.commit()
    client.post("/api/instock", json={"producto": "19 A-MANO", "minimo": 3})

    from src.schemas.sugerido import SugeridoFiltros
    from src.services import sugerido_service
    items, _ = sugerido_service.listar(catalogo, SugeridoFiltros(), limit=50)

    fila = next(i for i in items if i["producto"] == "19 A-MANO")
    assert fila["instock"] is True
    assert fila["total_sugerido_suc"] == 3
