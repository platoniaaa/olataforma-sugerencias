"""Detalle de una sugerencia manual: que toca y cuanto aporta de verdad.

Lo que se prueba es la distincion que motiva la pantalla: una sugerencia puede
estar viva y no estar agregando nada. Con InStock pasa de verdad — en produccion,
97 de 262 lineas no aportan una sola unidad porque el stock, el transito o el
sugerido del modelo ya cubren el minimo.
"""
import json
from datetime import date, timedelta

import pytest

from src.models import (
    RepuestoInstock,
    StockUnificado,
    SugerenciaManual,
    SugerenciaRecurrente,
    Sugerido,
)


@pytest.fixture()
def datos(db_session):
    """Una manual suelta, un lote, una recurrente y dos repuestos de pauta."""
    db_session.add_all([
        SugerenciaManual(id="m1", tenant_id="curifor", producto="20 BXO5W30AA",
                         sucursal_id="LINDEROS", unidades=3, motivo="Campaña de invierno",
                         creado_por="mary@curifor.com"),
        SugerenciaManual(id="l1", tenant_id="curifor", producto="20 BXO5W30AA",
                         sucursal_id="LINDEROS", unidades=2, lote_id="LOTE-A",
                         motivo="Carga masiva de julio"),
        SugerenciaManual(id="l2", tenant_id="curifor", producto="99 OTRO",
                         sucursal_id="LINDEROS", unidades=5, lote_id="LOTE-A",
                         motivo="Carga masiva de julio"),
        SugerenciaRecurrente(id="r1", tenant_id="curifor", modo="individual",
                             producto="20 BXO5W30AA", sucursal_id="LINDEROS",
                             unidades=2, cada_dias=7,
                             proxima_ejecucion=date.today() + timedelta(days=7),
                             activa=True, motivo="Mantener stock del taller"),
        SugerenciaManual(id="ri1", tenant_id="curifor", producto="20 BXO5W30AA",
                         sucursal_id="LINDEROS", unidades=2, recurrente_id="r1"),
    ])
    db_session.commit()
    return db_session


# --- Manuales: aditivas, con el contraste contra lo que pide el modelo --------

def test_una_unica_muestra_lo_que_aporta_y_lo_que_ya_pide_el_modelo(client, datos):
    r = client.get("/api/sugerencias-manuales/detalle/unica/m1")
    assert r.status_code == 200
    d = r.json()
    assert d["titulo"] == "20 BXO5W30AA · LINDEROS"
    assert d["motivo"] == "Campaña de invierno"
    linea = d["lineas"][0]
    assert linea["aporta"] == 3
    # El sugerido de la fixture pide 10 unidades por su cuenta.
    assert linea["sugerido_modelo"] == 10
    assert linea["total_con_sugerencia"] == 13
    assert linea["estado"] == "aporta"
    # Costo 5000 en la fixture -> 3 x 5000.
    assert linea["valor_aporte_clp"] == 15000


def test_marca_como_redundante_cuando_el_modelo_ya_pide_de_sobra(client, datos):
    """No la apaga: la senala. El comprador decide si la deja o la saca."""
    d = client.get("/api/sugerencias-manuales/detalle/unica/m1").json()
    assert d["lineas"][0]["redundante"] is True


def test_el_lote_trae_todas_sus_lineas_y_el_total(client, datos):
    d = client.get("/api/sugerencias-manuales/detalle/lote/LOTE-A").json()
    assert {l["producto"] for l in d["lineas"]} == {"20 BXO5W30AA", "99 OTRO"}
    assert d["totales"]["n_lineas"] == 2
    assert d["totales"]["unidades"] == 7
    assert d["totales"]["n_aportan"] == 2


def test_cada_linea_del_lote_trae_su_id_para_poder_borrarla_sola(client, datos):
    """Antes borrar era todo o nada: un lote de 95 se iba entero por una fila mala."""
    d = client.get("/api/sugerencias-manuales/detalle/lote/LOTE-A").json()
    ids = {l["id"] for l in d["lineas"]}
    assert ids == {"l1", "l2"}
    assert client.delete("/api/sugerencias-manuales/l2").status_code == 204
    d2 = client.get("/api/sugerencias-manuales/detalle/lote/LOTE-A").json()
    assert d2["totales"]["n_lineas"] == 1


def test_la_recurrente_trae_sus_instancias_vigentes(client, datos):
    d = client.get("/api/sugerencias-manuales/detalle/recurrente/r1").json()
    assert d["activa"] is True
    assert d["cada_dias"] == 7
    assert len(d["lineas"]) == 1
    assert d["lineas"][0]["aporta"] == 2


def test_un_id_que_no_existe_da_404(client, datos):
    assert client.get("/api/sugerencias-manuales/detalle/unica/no-existe").status_code == 404


def test_un_tipo_inventado_da_400(client, datos):
    assert client.get("/api/sugerencias-manuales/detalle/loquesea/m1").status_code == 400


# --- InStock: completa hasta un minimo, asi que puede aportar cero -----------

@pytest.fixture()
def instock(db_session):
    db_session.add_all([
        # Con stock 0 en todas: la regla tiene que pedir el minimo.
        RepuestoInstock(tenant_id="curifor", producto="95 FILTRO", part_number="FILTRO",
                        marca="HYUNDAI", modelos="Accent", operacion="FILTRO ACEITE",
                        minimo=2, activo=True),
        # Este ya esta cubierto en Linderos.
        RepuestoInstock(tenant_id="curifor", producto="95 CORREA", part_number="CORREA",
                        marca="HYUNDAI", modelos="i20", operacion="CORREA",
                        minimo=2, activo=True),
    ])
    db_session.add(StockUnificado(tenant_id="curifor", producto="95 CORREA",
                                  sucursal_id="LINDEROS", stock=9))
    db_session.add(Sugerido(tenant_id="curifor", producto="95 CORREA", sucursal_id="LINDEROS",
                            nombre_sucursal="Linderos", stock_activo_suc=9,
                            total_sugerido_suc=0, costo_unitario=1000))
    db_session.commit()
    return db_session


def test_instock_separa_lo_que_aporta_de_lo_que_ya_esta_cubierto(client, instock):
    d = client.get("/api/sugerencias-manuales/detalle/instock/instock").json()
    por_par = {(l["producto"], l["sucursal_id"]): l for l in d["lineas"]}
    # 2 repuestos x 4 sucursales con taller.
    assert d["totales"]["n_lineas"] == 8

    falta = por_par[("95 FILTRO", "LINDEROS")]
    assert falta["estado"] == "aporta"
    assert falta["aporta"] == 2

    cubierto = por_par[("95 CORREA", "LINDEROS")]
    assert cubierto["estado"] == "sin_efecto"
    assert cubierto["aporta"] == 0
    # El motivo tiene que decir POR QUE, no solo que no aporta.
    assert "9" in cubierto["motivo_sin_efecto"]


def test_instock_trae_los_datos_de_la_pauta(client, instock):
    """Marca, modelos y operacion: es lo que permite auditar de donde salio."""
    d = client.get("/api/sugerencias-manuales/detalle/instock/instock").json()
    linea = next(l for l in d["lineas"] if l["producto"] == "95 FILTRO")
    assert linea["marca"] == "HYUNDAI"
    assert linea["modelos"] == "Accent"
    assert linea["operacion"] == "FILTRO ACEITE"
    assert linea["minimo"] == 2


def test_instock_lista_los_part_numbers_que_no_calzan(client, instock, tmp_path, monkeypatch):
    """Sin esto nadie se entera de que la pauta trae codigos que no existen."""
    from src.jobs import cargar_instock as job

    csv = tmp_path / "pautas.csv"
    csv.write_text(
        "part_number;marca;modelos;operacion;detalle\n"
        "NOEXISTE;HYUNDAI;i20;FILTRO COMBUSTIBLE;mantencion\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(job, "DEFAULT_PATH", csv)
    d = client.get("/api/sugerencias-manuales/detalle/instock/instock").json()
    assert [p["part_number"] for p in d["pautas_sin_codigo"]] == ["NOEXISTE"]


# --- Pausar sin borrar -------------------------------------------------------

def test_pausar_deja_de_sumar_a_la_compra(client, datos):
    """Pausar y dejar el ajuste sumando seria peor que no pausar."""
    r = client.patch("/api/sugerencias-manuales/recurrentes/r1/activa", json={"activa": False})
    assert r.status_code == 200
    assert r.json()["activa"] is False
    # Su instancia vigente queda archivada.
    assert datos.get(SugerenciaManual, "ri1").archivada is True
    assert client.get("/api/sugerencias-manuales/detalle/recurrente/r1").json()["lineas"] == []


def test_reactivar_la_vuelve_a_dejar_activa(client, datos):
    client.patch("/api/sugerencias-manuales/recurrentes/r1/activa", json={"activa": False})
    r = client.patch("/api/sugerencias-manuales/recurrentes/r1/activa", json={"activa": True})
    assert r.json()["activa"] is True
    assert client.get("/api/sugerencias-manuales/detalle/recurrente/r1").json()["activa"] is True


def test_pausar_algo_que_no_existe_da_404(client, datos):
    assert client.patch(
        "/api/sugerencias-manuales/recurrentes/no-existe/activa", json={"activa": False}
    ).status_code == 404


# --- Excel -------------------------------------------------------------------

def test_baja_la_lista_en_excel(client, datos):
    r = client.get("/api/sugerencias-manuales/detalle/lote/LOTE-A/excel")
    assert r.status_code == 200
    assert "spreadsheetml" in r.headers["content-type"]
    assert r.content[:2] == b"PK"  # un xlsx es un zip
    assert "LOTE-A" in r.headers["content-disposition"]
