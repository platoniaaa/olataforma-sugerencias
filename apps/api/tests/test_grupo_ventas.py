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


def test_un_miembro_sin_ficha_no_se_acusa_de_no_estar_agrupado(db_session):
    """Sin fila no se sabe si el motor agrupo: decir que no lo hizo es inventar.

    Hasta el 23-08-2026 este era el caso NORMAL. El motor publicaba una fila por
    codigo consultado a FORD y no una por miembro del grupo, asi que 3.713
    codigos llegaban aca sin ficha propia y la pantalla los acusaba -en 2.935
    fichas- de algo que nadie habia comprobado.

    Se siguen dejando fuera del total, porque no se puede afirmar que el sugerido
    los junte, pero el aviso tiene que decir la verdad: falta el dato.
    """
    db_session.add(ReemplazoFord(
        tenant_id="curifor", producto="19 MB3Z19N619A",
        reemplaza_a="25 MB3Z19N619C",
        sucesor_confirmado=True, agrupado=True,
        extraido_en="2026-08-22 16:17:53",
    ))
    db_session.commit()

    r = sugerido_service.grupo_ventas(db_session, "19 MB3Z19N619A")

    viejo = next(m for m in r["miembros"] if m["producto"] == "25 MB3Z19N619C")
    assert viejo["cuenta_en_el_total"] is False
    assert "no trajo su ficha" in viejo["motivo_fuera"]
    assert "el motor no los agrupo" not in viejo["motivo_fuera"]


def test_el_que_el_motor_dejo_aparte_si_lo_dice(db_session):
    """El otro caso si esta comprobado, y el aviso tiene que seguir diciendolo."""
    db_session.add_all([
        ReemplazoFord(
            tenant_id="curifor", producto="19 MB3Z19N619A",
            reemplaza_a="25 MB3Z19N619C",
            sucesor_confirmado=True, agrupado=True,
            extraido_en="2026-08-22 16:17:53",
        ),
        ReemplazoFord(
            tenant_id="curifor", producto="25 MB3Z19N619C",
            reemplazado_por="19 MB3Z19N619A",
            sucesor_confirmado=True, agrupado=False,
            extraido_en="2026-08-22 16:17:53",
        ),
    ])
    db_session.commit()

    r = sugerido_service.grupo_ventas(db_session, "19 MB3Z19N619A")

    viejo = next(m for m in r["miembros"] if m["producto"] == "25 MB3Z19N619C")
    assert viejo["cuenta_en_el_total"] is False
    assert "el motor no los agrupo" in viejo["motivo_fuera"]


# --- La ventana de 12 meses -----------------------------------------------------


def test_la_venta_de_hace_dos_anos_no_cuenta_como_venta_del_ano(db_session):
    """`venta_historica` solo trae los meses CON venta.

    Tomar "las ultimas 12 filas" no es lo mismo que "los ultimos 12 meses": para
    un codigo que vendio 8 meses de 2024 y nunca mas, esas 8 filas eran sus
    "ultimos 12". `19 CYFS12F1X` mostraba 65 unidades vendidas hasta 09-2024 como
    Venta 12m en agosto de 2026, y la tarjeta existe justamente para responder
    "¿este repuesto se vende o se dejo de vender?".

    La señal de que la ventana no filtraba era que `venta_12m` daba igual que
    `venta_total`.
    """
    db_session.add(ReemplazoFord(
        tenant_id="curifor", producto="19 VIGENTE",
        reemplaza_a="19 MUERTO", sucesor_confirmado=True, agrupado=True,
        extraido_en="2026-08-22 16:17:53",
    ))
    # El vigente vende hoy; el viejo vendio hace dos años y nunca mas.
    db_session.add_all([
        VentaHistorica(tenant_id="curifor", periodo="202607",
                       producto="19 VIGENTE", cantidad=10),
        VentaHistorica(tenant_id="curifor", periodo="202404",
                       producto="19 MUERTO", cantidad=65),
    ])
    db_session.commit()

    r = sugerido_service.grupo_ventas(db_session, "19 VIGENTE")

    muerto = next(m for m in r["miembros"] if m["producto"] == "19 MUERTO")
    assert muerto["venta_12m"] == 0, "la venta de 2024 no es venta de los ultimos 12 meses"
    assert muerto["venta_total"] == 65, "pero el historico completo si la conserva"
    assert muerto["ultimo_mes_con_venta"] == "202404"


def test_el_grafico_trae_los_12_meses_aunque_no_haya_venta(db_session):
    """Sin los meses en cero, un repuesto que se apago no muestra la caida."""
    db_session.add(ReemplazoFord(
        tenant_id="curifor", producto="19 VIGENTE",
        reemplaza_a="19 MUERTO", sucesor_confirmado=True, agrupado=True,
        extraido_en="2026-08-22 16:17:53",
    ))
    db_session.add(VentaHistorica(tenant_id="curifor", periodo="202607",
                                  producto="19 VIGENTE", cantidad=10))
    db_session.commit()

    r = sugerido_service.grupo_ventas(db_session, "19 VIGENTE")

    assert len(r["meses"]) == 12
    assert r["meses"][-1]["mes"] == "202607"
    assert r["meses"][0]["mes"] == "202508"


# --- El grupo tiene que ser el mismo entre por donde se entre --------------------


@pytest.fixture()
def cadena_de_tres(db_session):
    """A -> B -> C, con el motor publicando el grupo bajo C.

    Es el caso de `17 2005485` -> `17 GK2Z9365A` -> `17 GK2Z9365C`.
    """
    from src.models import Sugerido
    db_session.add_all([
        ReemplazoFord(tenant_id="curifor", producto="17 A",
                      reemplazado_por="17 B", sucesor_confirmado=True, agrupado=True,
                      extraido_en="2026-08-22 16:17:53"),
        ReemplazoFord(tenant_id="curifor", producto="17 B",
                      reemplazado_por="17 C", reemplaza_a="17 A",
                      sucesor_confirmado=True, agrupado=True,
                      extraido_en="2026-08-22 16:17:53"),
        ReemplazoFord(tenant_id="curifor", producto="17 C",
                      reemplaza_a="17 A; 17 B",
                      sucesor_confirmado=True, agrupado=True,
                      extraido_en="2026-08-22 16:17:53"),
    ])
    # Lo que el motor publico: C es el master y arrastra a los otros dos.
    db_session.add(Sugerido(tenant_id="curifor", producto="17 C",
                            sucursal_id="LINDEROS", reemplazos="17 A, 17 B"))
    db_session.commit()
    return db_session


def test_el_grupo_es_el_mismo_entrando_por_cualquier_miembro(cadena_de_tres):
    """Reconstruirlo desde `reemplazo_ford` solo veia UN salto.

    Entrando por A se armaba {A, B} y entrando por C se armaba {A, B, C}: el mismo
    grupo mostraba dos cosas distintas. Al 24-08-2026 pasaba en 76 de 178 entradas.
    """
    esperado = {"17 A", "17 B", "17 C"}

    for entrada in ("17 A", "17 B", "17 C"):
        miembros = reemplazo_service.miembros_del_grupo(cadena_de_tres, entrada)
        assert set(miembros) == esperado, f"entrando por {entrada}"


def test_el_master_del_motor_va_primero(cadena_de_tres):
    """La tarjeta lo marca como vigente y suma su venta al total."""
    for entrada in ("17 A", "17 B", "17 C"):
        assert reemplazo_service.miembros_del_grupo(cadena_de_tres, entrada)[0] == "17 C"


def test_un_grupo_del_mix_tambien_se_ve_completo(db_session):
    """El mix no deja nada en `reemplazo_ford`, asi que antes era invisible.

    `20 BXO5W30AA` mostraba 3 de sus 5 miembros por esto.
    """
    from src.models import Sugerido
    db_session.add(Sugerido(tenant_id="curifor", producto="20 MASTER",
                            sucursal_id="LINDEROS",
                            reemplazos="20 UNO, 20 DOS, 20 TRES"))
    db_session.commit()

    miembros = reemplazo_service.miembros_del_grupo(db_session, "20 DOS")

    assert set(miembros) == {"20 MASTER", "20 UNO", "20 DOS", "20 TRES"}
    assert miembros[0] == "20 MASTER"


def test_un_codigo_parecido_no_se_cuela(db_session):
    """El pre-filtro es un LIKE; la pertenencia se confirma partiendo el texto.

    Sin eso, `17 200548` entraria al grupo de `17 2005485` por ser subcadena.
    """
    from src.models import Sugerido
    db_session.add(Sugerido(tenant_id="curifor", producto="17 MASTER",
                            sucursal_id="LINDEROS", reemplazos="17 2005485"))
    db_session.commit()

    assert reemplazo_service.miembros_del_grupo(db_session, "17 200548") == []
