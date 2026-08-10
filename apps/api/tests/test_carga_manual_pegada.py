"""Carga masiva de sugerencias manuales pegando una lista.

La masiva vieja aplica UN criterio y UN numero a todos los pares que pasan un
filtro. Esta acepta una lista donde cada linea trae lo suyo, que es como llega el
pedido real: un Excel armado a mano.
"""
from src.services.carga_manual_service import parsear

TAB = "\t"


def _lineas(*filas: str) -> str:
    return "\n".join(filas)


# --- Lo basico -------------------------------------------------------------------

def test_lee_una_lista_pegada_de_excel():
    texto = _lineas(
        f"25 DG9Z8100A{TAB}LINDEROS{TAB}5",
        f"20 BXO5W30BA{TAB}CURICO{TAB}{TAB}30",
        f"13 C5TS7600B3{TAB}TALCA{TAB}{TAB}{TAB}12",
    )
    r = parsear(texto)
    assert r["errores"] == []
    assert [f["criterio"] for f in r["filas"]] == ["unidades", "dias", "mantener"]
    assert r["filas"][0]["unidades"] == 5
    assert r["filas"][1]["dias"] == 30
    assert r["filas"][2]["mantener"] == 12


def test_el_codigo_con_espacios_no_se_parte():
    """Los codigos de Curifor traen espacios ("70 2723982"). Con separador
    explicito no hay ambiguedad, que es justo por lo que se exige."""
    r = parsear(f"70 2723982{TAB}LINDEROS{TAB}3")
    assert r["filas"][0]["producto"] == "70 2723982"
    assert r["filas"][0]["unidades"] == 3


def test_una_linea_sin_separador_avisa_en_vez_de_adivinar():
    r = parsear("25 DG9Z8100A LINDEROS 5")
    assert r["filas"] == []
    assert "columnas separadas" in r["errores"][0]["error"]


# --- Encabezado ------------------------------------------------------------------

def test_reconoce_el_encabezado_y_el_orden_da_igual():
    texto = _lineas(
        f"Sucursal{TAB}Código{TAB}Días de cobertura",
        f"LINDEROS{TAB}25 DG9Z8100A{TAB}45",
    )
    r = parsear(texto)
    assert r["encabezado_detectado"] is True
    assert r["filas"] == [{
        "producto": "25 DG9Z8100A", "sucursal": "LINDEROS",
        "unidades": None, "dias": 45, "mantener": None, "criterio": "dias",
    }]


def test_sin_encabezado_asume_el_orden_documentado():
    r = parsear(f"25 DG9Z8100A{TAB}LINDEROS{TAB}7")
    assert r["encabezado_detectado"] is False
    assert r["filas"][0]["unidades"] == 7


def test_una_fila_de_datos_no_se_confunde_con_encabezado():
    """Un producto en la primera celda no convierte la fila en encabezado."""
    r = parsear(f"25 DG9Z8100A{TAB}LINDEROS{TAB}5")
    assert r["encabezado_detectado"] is False
    assert len(r["filas"]) == 1


# --- La regla de prioridad -------------------------------------------------------

def test_mantener_le_gana_a_dias_y_a_unidades():
    """Mismo orden que el modal por filtros: no puede haber dos reglas."""
    r = parsear(f"25 A{TAB}LINDEROS{TAB}5{TAB}30{TAB}12")
    f = r["filas"][0]
    assert f["criterio"] == "mantener"
    assert f["mantener"] == 12
    assert f["unidades"] is None and f["dias"] is None


def test_dias_le_gana_a_unidades():
    r = parsear(f"25 A{TAB}LINDEROS{TAB}5{TAB}30")
    assert r["filas"][0]["criterio"] == "dias"
    assert r["filas"][0]["unidades"] is None


# --- Errores que no abortan la carga ---------------------------------------------

def test_las_lineas_malas_no_botan_las_buenas():
    """Una lista de 200 con 3 malas no puede obligar a empezar de nuevo."""
    texto = _lineas(
        f"25 A{TAB}LINDEROS{TAB}5",
        f"{TAB}LINDEROS{TAB}5",          # sin producto
        f"25 C{TAB}{TAB}5",              # sin sucursal
        f"25 D{TAB}LINDEROS{TAB}",       # sin cantidad
        f"25 E{TAB}CURICO{TAB}2",
    )
    r = parsear(texto)
    assert [f["producto"] for f in r["filas"]] == ["25 A", "25 E"]
    assert [e["linea"] for e in r["errores"]] == [2, 3, 4]
    assert "producto" in r["errores"][0]["error"]
    assert "sucursal" in r["errores"][1]["error"]
    assert "cantidad" in r["errores"][2]["error"]


def test_una_cantidad_en_cero_no_es_una_carga():
    r = parsear(f"25 A{TAB}LINDEROS{TAB}0")
    assert r["filas"] == []
    assert "cantidad" in r["errores"][0]["error"]


def test_las_lineas_en_blanco_se_saltan_sin_ruido():
    r = parsear(_lineas(f"25 A{TAB}LINDEROS{TAB}5", "", "   ", f"25 B{TAB}CURICO{TAB}2"))
    assert len(r["filas"]) == 2
    assert r["errores"] == []


# --- Numeros ---------------------------------------------------------------------

def test_acepta_separador_de_miles():
    r = parsear(f"25 A{TAB}LINDEROS{TAB}1.500")
    assert r["filas"][0]["unidades"] == 1500


def test_otros_separadores_ademas_del_tab():
    for sep in [";", "|"]:
        r = parsear(f"25 A{sep}LINDEROS{sep}5")
        assert r["filas"][0]["unidades"] == 5, sep


def test_texto_vacio_no_revienta():
    r = parsear("")
    assert r == {"filas": [], "errores": [], "encabezado_detectado": False}


# --- El endpoint -----------------------------------------------------------------

def _pegar(client, texto: str, **kw):
    return client.post("/api/sugerencias-manuales/pegada",
                       json={"texto": texto, **kw})


def test_previsualizar_no_escribe_nada(client):
    antes = client.get("/api/sugerencias-manuales").json()
    r = _pegar(client, f"P1{TAB}LINDEROS{TAB}5", previsualizar=True)
    assert r.status_code == 200
    d = r.json()
    assert d["creadas"] == 0
    assert d["lineas"][0]["unidades_resultantes"] == 5
    despues = client.get("/api/sugerencias-manuales").json()
    assert len(despues) == len(antes)


def test_crea_las_sugerencias_con_un_lote_comun(client):
    r = _pegar(client, _lineas(f"P1{TAB}LINDEROS{TAB}5", f"P1{TAB}CURICO{TAB}3"))
    assert r.status_code == 200
    d = r.json()
    assert d["creadas"] == 2
    assert d["lote_id"]
    # El lote sirve para borrarlas juntas, como la masiva por filtros.
    borrado = client.delete(f"/api/sugerencias-manuales/lote/{d['lote_id']}")
    assert borrado.status_code in (200, 204)


def test_cada_linea_conserva_su_criterio(client):
    """Una carga puede mezclar los tres, y el detalle tiene que poder explicarlo."""
    r = _pegar(client, _lineas(
        f"P1{TAB}LINDEROS{TAB}5",
        f"P1{TAB}CURICO{TAB}{TAB}30",
    ))
    assert r.status_code == 200
    creadas = client.get("/api/sugerencias-manuales").json()
    lote = [s for s in creadas if s.get("lote_id") == r.json()["lote_id"]]
    porcriterio = {
        (s["dias_inventario"], s["stock_objetivo"]) for s in lote
    }
    # Una por unidades (los dos None) y otra por dias (30, None).
    assert (None, None) in porcriterio


def test_los_errores_vuelven_con_su_numero_de_linea(client):
    r = _pegar(client, _lineas(f"P1{TAB}LINDEROS{TAB}5", "linea mala sin separador"))
    d = r.json()
    assert d["creadas"] == 1
    assert d["errores"][0]["linea"] == 2


def test_una_lista_entera_mala_no_crea_nada(client):
    r = _pegar(client, "todo mal")
    d = r.json()
    assert d["creadas"] == 0
    assert d["lote_id"] is None
    assert d["errores"]
