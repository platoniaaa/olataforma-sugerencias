"""Requerimiento de sucursal: pegar la lista, decidir, bajar el archivo del portal.

Lo delicado es el PARSEO. El codigo de Curifor trae un rubro con espacio
("70 2723982") y ademas hay codigos que son puros numeros, asi que "codigo espacio
numero" es ambiguo: `70 2723982` puede leerse como producto "70 2723982" sin
cantidad, o como producto "70" con cantidad 2.723.982. La segunda lectura seria un
desastre silencioso. Se desempata preguntandole al catalogo cual existe.
"""
import pytest

from src.models import ProductoCatalogo, SkuProveedor, Sugerido
from src.services import archivo_portal, requerimiento_service


@pytest.fixture()
def catalogo(db_session):
    """Un catalogo chico con los casos que importan."""
    db_session.add_all([
        # Codigo con rubro y letras.
        Sugerido(tenant_id="curifor", producto="19 SZ6Z3B437B", sucursal_id="LINDEROS",
                 nombre_sucursal="Linderos", clasificacion_abc="A", pedir="Si",
                 meses_con_venta_3m=3, meses_con_venta_6m=6, meses_con_venta_12m=11,
                 stock_activo_suc=2, costo_unitario=1000.0, proveedor="FORD"),
        # Codigo que es puro numero: el caso ambiguo.
        Sugerido(tenant_id="curifor", producto="70 2723982", sucursal_id="LINDEROS",
                 nombre_sucursal="Linderos", clasificacion_abc="A", pedir="Si",
                 meses_con_venta_3m=2, meses_con_venta_6m=5, meses_con_venta_12m=10,
                 stock_activo_suc=50, costo_unitario=500.0, proveedor="GM"),
        # Existe, pero se vende en OTRA sucursal.
        Sugerido(tenant_id="curifor", producto="25 OTRA", sucursal_id="CURICO",
                 nombre_sucursal="Curicó", clasificacion_abc="C", pedir="Si",
                 meses_con_venta_3m=1, meses_con_venta_6m=4, meses_con_venta_12m=7,
                 costo_unitario=200.0, proveedor="FORD"),
    ])
    db_session.add(ProductoCatalogo(tenant_id="curifor", producto="25 OTRA",
                                    glosa="Repuesto de otra sucursal", costo=200.0))
    db_session.commit()
    return db_session


# --- Parseo: lo que se pega ---------------------------------------------------

def test_separadores_distintos_dan_el_mismo_resultado(catalogo):
    for texto in ["19 SZ6Z3B437B\t4", "19 SZ6Z3B437B;4", "19 SZ6Z3B437B,4",
                  "19 SZ6Z3B437B 4", "19 SZ6Z3B437B|4"]:
        r = requerimiento_service.parsear(catalogo, texto)
        assert r == [{"producto": "19 SZ6Z3B437B", "cantidad": 4.0,
                      "texto_original": texto}], texto


def test_un_codigo_que_es_puro_numero_no_se_confunde_con_la_cantidad(catalogo):
    """`70 2723982` es UN codigo, no el producto 70 con cantidad 2.723.982."""
    r = requerimiento_service.parsear(catalogo, "70 2723982")
    assert r[0]["producto"] == "70 2723982"
    assert r[0]["cantidad"] is None


def test_ese_mismo_codigo_con_cantidad_se_lee_bien(catalogo):
    r = requerimiento_service.parsear(catalogo, "70 2723982 6")
    assert r[0]["producto"] == "70 2723982"
    assert r[0]["cantidad"] == 6.0


def test_se_ignora_la_fila_de_encabezado(catalogo):
    r = requerimiento_service.parsear(catalogo, "codigo\tcantidad\n19 SZ6Z3B437B\t2")
    assert len(r) == 1
    assert r[0]["producto"] == "19 SZ6Z3B437B"


def test_lineas_vacias_no_generan_filas(catalogo):
    r = requerimiento_service.parsear(catalogo, "\n\n19 SZ6Z3B437B 1\n\n  \n")
    assert len(r) == 1


def test_cantidad_con_separador_de_miles(catalogo):
    r = requerimiento_service.parsear(catalogo, "70 2723982;1.500")
    assert r[0]["cantidad"] == 1500.0


def test_un_codigo_desconocido_igual_se_devuelve(catalogo):
    """No se descarta: el comprador tiene que ver que ese codigo no existe."""
    r = requerimiento_service.parsear(catalogo, "NO-EXISTE 3")
    assert r[0]["producto"] == "NO-EXISTE"
    assert r[0]["cantidad"] == 3.0


# --- Analisis: los tres estados ------------------------------------------------

def test_los_tres_estados(catalogo):
    lineas = requerimiento_service.parsear(
        catalogo, "19 SZ6Z3B437B 2\n25 OTRA 1\nNO-EXISTE 5"
    )
    r = requerimiento_service.analizar(catalogo, "LINDEROS", lineas)
    estados = {l["producto"]: l["estado"] for l in r["lineas"]}
    assert estados["19 SZ6Z3B437B"] == "en_sugerido"
    assert estados["25 OTRA"] == "sin_venta_local"
    assert estados["NO-EXISTE"] == "no_existe"
    assert r["resumen"] == {"total": 3, "en_sugerido": 1, "sin_venta_local": 1,
                            "no_existe": 1, "duplicados": 0}


def test_trae_la_frecuencia_de_la_sucursal_pedida(catalogo):
    lineas = [{"producto": "19 SZ6Z3B437B", "cantidad": 1}]
    r = requerimiento_service.analizar(catalogo, "LINDEROS", lineas)
    fila = r["lineas"][0]
    assert (fila["meses_con_venta_3m"], fila["meses_con_venta_6m"],
            fila["meses_con_venta_12m"]) == (3, 6, 11)


def test_si_no_se_vende_aca_dice_donde_si(catalogo):
    """Un "no hay dato" no sirve; "en Curico 7 de 12" si."""
    lineas = [{"producto": "25 OTRA", "cantidad": 1}]
    r = requerimiento_service.analizar(catalogo, "LINDEROS", lineas)
    fila = r["lineas"][0]
    assert fila["meses_con_venta_12m"] is None
    otra = fila["frecuencia_otra_sucursal"]
    assert otra["sucursal_id"] == "CURICO"
    assert otra["meses_con_venta_12m"] == 7


def test_marca_los_repetidos(catalogo):
    lineas = [{"producto": "19 SZ6Z3B437B", "cantidad": 1},
              {"producto": "19 SZ6Z3B437B", "cantidad": 2}]
    r = requerimiento_service.analizar(catalogo, "LINDEROS", lineas)
    assert [l["duplicado"] for l in r["lineas"]] == [False, True]
    assert r["resumen"]["duplicados"] == 1


# --- Archivo del portal --------------------------------------------------------

def test_clave_producto_saca_el_rubro():
    assert archivo_portal.clave_producto("19 SZ6Z3B437B") == "SZ6Z3B437B"
    assert archivo_portal.clave_producto("83 51703-4A000") == "517034A000"
    assert archivo_portal.clave_producto(None) is None


def test_ford_empieza_en_a1_y_convierte_el_codigo(db_session):
    db_session.add(SkuProveedor(tenant_id="curifor", proveedor="FORD",
                                clave="SZ6Z3B437B", sku="SZ6Z/3B437/B/"))
    db_session.commit()
    contenido, fuera = archivo_portal.generar_csv(
        db_session, [{"producto": "19 SZ6Z3B437B", "cantidad": 4}], "FORD"
    )
    assert contenido.decode("latin-1").split("\r\n")[0] == "SZ6Z/3B437/B/,4"
    assert fuera == []


def test_gildemeister_empieza_en_a2(db_session):
    contenido, fuera = archivo_portal.generar_csv(
        db_session, [{"producto": "83 51703-4A000", "cantidad": 2}], "GILDEMEISTER"
    )
    filas = contenido.decode("latin-1").split("\r\n")
    assert filas[0] == ""              # A1 va vacia
    assert filas[1] == "517034A000,2"  # el detalle arranca en A2
    assert fuera == []


def test_sin_equivalencia_ford_la_linea_queda_fuera_y_se_avisa(db_session):
    contenido, fuera = archivo_portal.generar_csv(
        db_session, [{"producto": "19 DESCONOCIDO", "cantidad": 1}], "FORD"
    )
    assert contenido.decode("latin-1").strip() == ""
    assert len(fuera) == 1
    assert "ford" in fuera[0]["motivo"].lower()


def test_sin_cantidad_la_linea_queda_fuera(db_session):
    db_session.add(SkuProveedor(tenant_id="curifor", proveedor="FORD",
                                clave="ABC", sku="A/B/C/"))
    db_session.commit()
    _, fuera = archivo_portal.generar_csv(
        db_session, [{"producto": "19 ABC", "cantidad": 0}], "FORD"
    )
    assert fuera[0]["motivo"] == "sin cantidad"


def test_proveedor_no_soportado_falla_claro(db_session):
    with pytest.raises(ValueError, match="no soportado"):
        archivo_portal.generar_csv(db_session, [], "TOYOTA")
