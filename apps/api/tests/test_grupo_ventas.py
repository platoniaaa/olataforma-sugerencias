"""La venta de cada codigo del grupo, para la ficha del producto.

El comprador ve un numero consolidado y no sabe de donde viene. Con el desglose
puede responder "¿este repuesto se vende o se dejo de vender?" cuando el codigo
cambio tres veces en dos años: sin el, un repuesto que siempre se vendio igual
parece nuevo cada vez que FORD lo renumera.
"""
import pytest

from src.models import ReemplazoFord, StockUnificado, VentaHistorica
from src.services import reemplazo_service, sugerido_service


@pytest.fixture()
def grupo(db_session):
    """`25 MB3Z19N619C` (de baja) agrupado bajo `19 MB3Z19N619A` (vigente)."""
    db_session.add_all([
        ReemplazoFord(
            tenant_id="curifor", producto="25 MB3Z19N619C",
            reemplazado_por="19 MB3Z19N619A",
            reemplazado_por_ford="MB3Z/19N619/A/",
            cadena="MB3Z/19N619/C/ > MB3Z/19N619/A/",
            sucesor_confirmado=True, agrupado=True,
            extraido_en="2026-08-22 16:17:53",
        ),
        ReemplazoFord(
            tenant_id="curifor", producto="19 MB3Z19N619A",
            reemplazado_por=None, reemplazado_por_ford=None, cadena=None,
            reemplaza_a="25 MB3Z19N619C",
            sucesor_confirmado=True, agrupado=True,
            extraido_en="2026-08-22 16:17:53",
        ),
    ])
    # El viejo vendia y se apago; el vigente arranco.
    db_session.add_all([
        VentaHistorica(tenant_id="curifor", periodo="202508",
                       producto="19 MB3Z19N619A", cantidad=30),
        VentaHistorica(tenant_id="curifor", periodo="202507",
                       producto="19 MB3Z19N619A", cantidad=10),
        VentaHistorica(tenant_id="curifor", periodo="202506",
                       producto="25 MB3Z19N619C", cantidad=40),
        VentaHistorica(tenant_id="curifor", periodo="202505",
                       producto="25 MB3Z19N619C", cantidad=50),
    ])
    db_session.add_all([
        StockUnificado(tenant_id="curifor", producto="19 MB3Z19N619A",
                       sucursal_id="CHILLAN", stock=9),
        StockUnificado(tenant_id="curifor", producto="25 MB3Z19N619C",
                       sucursal_id="RANCAGUA", stock=110),
    ])
    db_session.commit()
    return db_session


def test_entrando_por_el_codigo_viejo_devuelve_el_grupo_completo(grupo):
    """El caso que se rompe solo, y ya paso con los equivalentes del mix: el
    motor escribe la lista unicamente en la fila del master, y entrando por otro
    miembro parecia que el producto no tenia reemplazos."""
    r = sugerido_service.grupo_ventas(grupo, "25 MB3Z19N619C")

    assert [m["producto"] for m in r["miembros"]] == [
        "19 MB3Z19N619A", "25 MB3Z19N619C"]


def test_entrando_por_el_vigente_devuelve_lo_mismo(grupo):
    por_viejo = sugerido_service.grupo_ventas(grupo, "25 MB3Z19N619C")
    por_vigente = sugerido_service.grupo_ventas(grupo, "19 MB3Z19N619A")

    assert ([m["producto"] for m in por_viejo["miembros"]]
            == [m["producto"] for m in por_vigente["miembros"]])
    assert por_viejo["total_venta_12m"] == por_vigente["total_venta_12m"]


def test_el_vigente_va_primero_y_marcado(grupo):
    r = sugerido_service.grupo_ventas(grupo, "25 MB3Z19N619C")

    assert r["vigente"] == "19 MB3Z19N619A"
    assert r["miembros"][0]["es_vigente"] is True
    assert r["miembros"][1]["es_vigente"] is False


def test_el_total_suma_los_dos_codigos(grupo):
    """Es lo que el sugerido trata como una sola pieza."""
    r = sugerido_service.grupo_ventas(grupo, "25 MB3Z19N619C")

    assert r["total_venta_12m"] == 130   # 30 + 10 + 40 + 50
    assert r["total_stock"] == 119       # 9 + 110


def test_se_ve_cuando_se_apago_cada_codigo(grupo):
    """Para eso esta el desglose: ver el mes del traspaso."""
    r = sugerido_service.grupo_ventas(grupo, "25 MB3Z19N619C")
    por_codigo = {m["producto"]: m for m in r["miembros"]}

    assert por_codigo["25 MB3Z19N619C"]["ultimo_mes_con_venta"] == "202506"
    assert por_codigo["19 MB3Z19N619A"]["ultimo_mes_con_venta"] == "202508"


def test_la_serie_trae_un_valor_por_codigo_y_por_mes(grupo):
    """Es lo que alimenta el grafico de barras apiladas."""
    r = sugerido_service.grupo_ventas(grupo, "25 MB3Z19N619C")
    por_mes = {m["mes"]: m for m in r["meses"]}

    assert por_mes["202505"]["25 MB3Z19N619C"] == 50
    assert por_mes["202505"]["19 MB3Z19N619A"] == 0
    assert por_mes["202508"]["19 MB3Z19N619A"] == 30


def test_lo_que_el_motor_no_agrupo_queda_fuera_del_total(grupo):
    """Si la tabla sumara codigos que el motor no junto, el total no cuadraria
    con lo que muestra el sugerido y el comprador confiaria en el numero
    equivocado. Se muestra igual, pero marcado y fuera del total."""
    r = grupo.query(ReemplazoFord).filter_by(producto="25 MB3Z19N619C").first()
    r.agrupado = False
    grupo.commit()

    out = sugerido_service.grupo_ventas(grupo, "25 MB3Z19N619C")
    viejo = [m for m in out["miembros"] if m["producto"] == "25 MB3Z19N619C"][0]

    assert viejo["cuenta_en_el_total"] is False
    assert viejo["motivo_fuera"]
    # Sigue en la tabla, pero no suma.
    assert out["total_venta_12m"] == 40    # solo el vigente
    assert out["total_stock"] == 9


def test_un_codigo_sin_reemplazos_no_devuelve_grupo(db_session):
    """Una tabla de una sola fila no dice nada: la tarjeta no se muestra."""
    r = sugerido_service.grupo_ventas(db_session, "17 GK2Z9601B")

    assert r["miembros"] == []


def test_miembros_del_grupo_sin_reemplazo_es_vacio(db_session):
    assert reemplazo_service.miembros_del_grupo(db_session, "17 GK2Z9601B") == []
