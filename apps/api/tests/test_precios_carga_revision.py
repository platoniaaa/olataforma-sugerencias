"""Carga de precios desde Excel: lo que encontro la revision adversarial del 14-10-2026.

Cada test es un escenario reproducido en la revision. Los agrupa una idea: el archivo
llega desde Excel, y Excel (y las personas) hacen cosas que el servidor no puede
suponer: ordenar una columna suelta, guardar en otra codificacion, dejar celdas de
error, subir el mismo archivo dos veces.
"""
import csv
import io

import pytest

from src.models import PrecioOverride, PrecioProducto
from src.services import precios_carga_service as carga
from src.services import precios_service as svc

from .test_precios import _producto, lista_cargada  # noqa: F401  (fixture)
from .test_precios_carga import _a_csv, _bajar, _editar, _ficha, _override, _subir, lista  # noqa: F401


def _csv(filas, sep=";", fin="\r\n", codificacion="utf-8-sig") -> bytes:
    buf = io.StringIO(newline="")
    csv.writer(buf, delimiter=sep, lineterminator=fin).writerows(filas)
    return buf.getvalue().encode(codificacion)


# ------------------------------------------- la referencia es de SU producto
def test_una_referencia_que_es_de_otro_producto_es_un_error(client, lista):
    """Ordenar o pegar solo la columna Referencia la deja en otra fila: los precios
    de esa fila se volvian precio fijo, sin error ni conflicto."""
    filas = _bajar(client)
    cab = filas[0]
    ref = cab.index("Referencia")
    fila_a = next(f for f in filas[1:] if f[0] == "71 AAA1")
    fila_b = next(f for f in filas[1:] if f[0] == "71 CCC3")
    fila_a[ref], fila_b[ref] = fila_b[ref], fila_a[ref]

    v = _subir(client, _a_csv(filas)).json()
    r = _subir(client, _a_csv(filas), aplicar=True)

    assert v["errores_total"] == 2 and v["a_cambiar"] == 0
    assert all("de otro producto" in e["mensaje"] for e in v["errores"])
    assert r.status_code == 422
    assert _override(lista, "71 AAA1") is None


# ------------------------------------------------- subir dos veces el mismo
def test_subir_otra_vez_el_mismo_archivo_dice_que_no_hay_cambios(client, lista):
    """Antes acusaba a "alguien" de un conflicto: la huella de las decisiones ya
    habia cambiado con la propia carga. Es la ruta de recuperacion tras un corte."""
    filas = _editar(_bajar(client), "71 AAA1", Tipo="Pesado")
    filas = _editar(filas, "71 CCC3", Obs="nota")
    contenido = _a_csv(filas)
    assert _subir(client, contenido, aplicar=True).json()["aplicados"] == 2

    v = _subir(client, contenido).json()
    r = _subir(client, contenido, aplicar=True).json()

    assert v["a_cambiar"] == 0 and v["conflictos_total"] == 0 and v["errores_total"] == 0
    assert r["aplicados"] == 0 and r["omitidos"] == {"conflictos": 0, "desconocidos": 0, "sin_referencia": 0}


def test_el_conflicto_no_acusa_solo_a_otra_persona(client, lista):
    filas = _editar(_bajar(client), "71 AAA1", Tipo="Pesado")
    _subir(client, _a_csv(filas), aplicar=True)
    filas = _editar(filas, "71 AAA1", Obs="corrección")     # el mismo archivo, con otra celda

    v = _subir(client, _a_csv(filas)).json()

    assert v["conflictos_total"] == 1
    assert "una carga tuya anterior" in v["conflictos"][0]["mensaje"]


# -------------------------------------------------------------- observaciones
@pytest.mark.parametrize("obs", ["uno ¦ dos", "a | b", "x|y|z|w|v|u|t|s|r", "=HYPERLINK(\"http://x\")",
                                 "+IVA incluido", "-5% convenio", "@usuario", "dice 'hola'", "linea1\nlinea2"])
def test_una_observacion_rara_no_es_una_edicion(client, lista, obs):
    client.put("/api/precios/71 AAA1/override", json={"obs": obs})

    v = _subir(client, _a_csv(_bajar(client))).json()

    assert v["a_cambiar"] == 0 and v["errores_total"] == 0


def test_una_observacion_con_barra_no_marca_conflicto_en_una_fila_sin_tocar(client, lista):
    client.put("/api/precios/71 AAA1/override", json={"obs": "uno ¦ dos"})
    filas = _bajar(client)
    client.put("/api/precios/71 AAA1/override", json={"tipo_manual": "Pesado"})   # otra persona

    v = _subir(client, _a_csv(filas)).json()

    assert v["conflictos_total"] == 0 and v["a_cambiar"] == 0


def test_las_celdas_que_excel_abriria_como_formula_salen_protegidas(client, lista):
    """"-5% convenio" sale #NOMBRE? en Excel, y un "=HYPERLINK(...)" escrito por
    alguien se ejecuta al abrir el archivo. El apostrofe las deja como texto."""
    client.put("/api/precios/71 AAA1/override", json={"obs": "=HYPERLINK(\"http://x\")"})
    client.put("/api/precios/71 CCC3/override", json={"obs": "-5% convenio"})
    lista.query(PrecioProducto).filter_by(producto="13 BBB2").one().glosa = "-FILTRO RARO"
    lista.commit()
    filas = _bajar(client)
    cab = filas[0]
    por = {f[0]: dict(zip(cab, f)) for f in filas[1:]}

    assert por["71 AAA1"]["Obs"] == "'=HYPERLINK(\"http://x\")"
    assert por["71 CCC3"]["Obs"] == "'-5% convenio"
    assert por["13 BBB2"]["Glosa"] == "'-FILTRO RARO"
    assert por["71 AAA1"]["Producto"] == "71 AAA1"                  # el codigo no se toca
    # Y al volver, lo protegido se lee como lo que era.
    assert _subir(client, _a_csv(filas)).json()["a_cambiar"] == 0
    editado = _editar(filas, "71 CCC3", Obs="'-10% convenio")
    assert _subir(client, _a_csv(editado), aplicar=True).status_code == 200
    assert _override(lista, "71 CCC3").obs == "-10% convenio"


# ------------------------------------------------------ archivos que no sirven
def test_un_csv_de_mac_con_fin_de_linea_cr_se_lee(client, lista):
    """"CSV (Macintosh)" termina las lineas con CR solo: antes daba 500."""
    filas = _editar(_bajar(client), "71 AAA1", Tipo="Pesado")

    v = _subir(client, _csv(filas, fin="\r")).json()

    assert v["a_cambiar"] == 1 and v["errores_total"] == 0


def test_el_texto_unicode_de_excel_en_utf16_se_lee(client, lista):
    """"Texto Unicode (.txt)": UTF-16 con tabuladores."""
    filas = _editar(_bajar(client), "71 AAA1", Tipo="Pesado", Obs="revisión ñ")
    texto = _csv(filas, sep="\t", fin="\r\n", codificacion="utf-8").decode("utf-8")

    r = _subir(client, texto.encode("utf-16"), nombre="lista.txt", aplicar=True)

    assert r.status_code == 200 and r.json()["aplicados"] == 1
    assert _override(lista, "71 AAA1").obs == "revisión ñ"


def test_una_celda_gigante_da_un_mensaje_y_no_un_500(client, lista):
    filas = _editar(_bajar(client), "71 AAA1", Obs="x" * 200_000)

    r = _subir(client, _a_csv(filas))

    assert r.status_code == 422 and "No pude leer el archivo como CSV" in r.json()["detail"]


def test_un_archivo_binario_da_un_mensaje_y_no_un_500(client, lista):
    r = _subir(client, b"\x00\x01\x02" * 2000, nombre="lista.csv")

    assert r.status_code == 422 and "no parece un CSV de texto" in r.json()["detail"]


def test_un_csv_con_demasiadas_filas_se_rechaza(client, lista, monkeypatch):
    monkeypatch.setattr(carga, "MAX_FILAS", 50)
    filas = _bajar(client) + [[""] * 3] * 100

    r = _subir(client, _a_csv(filas))

    assert r.status_code == 422 and "más de 50 filas" in r.json()["detail"]


def test_un_xlsx_con_una_celda_perdida_al_final_de_la_hoja_se_rechaza_sin_abrirlo(client, lista):
    """Una letra en A1048576 (Ctrl+Flecha abajo y escribir) hacia que calamine
    armara una hoja de un millon de filas: mas de 1 GB y la API caida."""
    from openpyxl import Workbook

    filas = _bajar(client)
    wb = Workbook()
    ws = wb.active
    for f in filas:
        ws.append(f)
    ws["A1048576"] = "x"
    buf = io.BytesIO()
    wb.save(buf)

    r = _subir(client, buf.getvalue(), nombre="lista.xlsx")

    assert r.status_code == 422 and "La primera hoja tiene contenido" in r.json()["detail"]
    assert len(buf.getvalue()) < 100_000          # es chico: el tope de bytes no lo frena


def test_un_nul_dentro_de_un_texto_se_quita():
    """Postgres no acepta 0x00 en un texto: la carga entera respondia 500."""
    assert carga._texto("a\x00b") == "ab"
    assert carga._c_texto("a\x00 b") == "a b"


# ------------------------------------------------------- numeros y tipos
def test_el_cero_del_formato_contable_no_es_un_error(client, lista):
    """Con formato Contable, Excel escribe el cero como "$ -" y bloqueaba toda la carga."""
    _producto(lista, "71 CERO", procedencia_maestro="NACIONAL", stock=0.0)      # sin stock: precio 0
    svc.recalcular(lista, refrescar_insumos=False)
    filas = _bajar(client)
    assert next(f for f in filas[1:] if f[0] == "71 CERO")[filas[0].index("Precio final")] == "0"

    v = _subir(client, _a_csv(_editar(filas, "71 CERO", Precio_final=" $ - "))).json()

    assert v["errores_total"] == 0 and v["a_cambiar"] == 0
    assert carga.leer_numero(" $ - ", entero=True) == 0.0


@pytest.mark.parametrize("tipo", ["Neumático", "NEUMÁTICOS", "neumaticos"])
def test_un_tipo_se_acepta_con_o_sin_tildes(client, lista, tipo):
    r = _subir(client, _a_csv(_editar(_bajar(client), "71 AAA1", Tipo=tipo)), aplicar=True)

    assert r.status_code == 200, r.text
    assert _override(lista, "71 AAA1").tipo_manual == "Neumatico"


def test_un_factor_redondeado_por_excel_a_dos_decimales_no_es_una_edicion(client, lista):
    """Con "disminuir decimales", 1,1429 queda 1,14 y parecia una edicion del factor."""
    client.put("/api/precios/71 AAA1/override", json={"margen_fijo": 12.5})      # factor 1,1429
    filas = _bajar(client)
    assert next(f for f in filas[1:] if f[0] == "71 AAA1")[filas[0].index("Factor")] == "1,1429"

    redondeado = _subir(client, _a_csv(_editar(filas, "71 AAA1", Factor="1,14"))).json()
    otro = _subir(client, _a_csv(_editar(filas, "71 AAA1", Factor="1,2"))).json()

    assert redondeado["a_cambiar"] == 0
    assert otro["a_cambiar"] == 1


# ----------------------------------------------- quitar muchas decisiones
def _con_precios_fijos(lista, n: int):
    for i in range(n):
        _producto(lista, f"71 Q{i:02d}", procedencia_maestro="NACIONAL")
        lista.add(PrecioOverride(tenant_id="curifor", producto=f"71 Q{i:02d}", precio_fijo=1000.0 + i))
    lista.commit()
    svc.recalcular(lista, refrescar_insumos=False)


def _vaciar_precios(filas, n: int):
    for i in range(n):
        filas = _editar(filas, f"71 Q{i:02d}", Precio_final="")
    return filas


def test_quitar_muchas_decisiones_pide_confirmacion(client, lista):
    """Una celda vacia quita la decision, y un .xlsx con celdas de error (#N/D, #REF!)
    las entrega vacias: un BUSCARV roto borraria precios fijos en silencio."""
    _con_precios_fijos(lista, 12)
    contenido = _a_csv(_vaciar_precios(_bajar(client), 12))

    v = _subir(client, contenido).json()
    sin = _subir(client, contenido, aplicar=True)

    assert v["quitan_total"] == 12 and v["umbral_quitas"] == carga.UMBRAL_QUITAS
    assert v["quitan"] == {"precio_fijo": 12} and len(v["quitan_ejemplos"]) == 12
    assert sin.status_code == 422 and "quita 12 decisiones" in sin.json()["detail"]
    assert _override(lista, "71 Q00").precio_fijo == 1000                  # sin confirmar, no se toco nada

    con = client.post("/api/precios/carga", data={"confirmar_quitas": "true"},
                      files={"archivo": ("lista.csv", contenido, "text/csv")})
    assert con.status_code == 200 and con.json()["aplicados"] == 12
    assert _override(lista, "71 Q00").precio_fijo is None


def test_quitar_pocas_decisiones_no_pide_confirmacion(client, lista):
    _con_precios_fijos(lista, 3)

    r = _subir(client, _a_csv(_vaciar_precios(_bajar(client), 3)), aplicar=True)

    assert r.status_code == 200 and r.json()["aplicados"] == 3


def test_descongelar_o_quitar_no_es_producto_cuenta_como_quitar(client, lista):
    v = _subir(client, _a_csv(_editar(_bajar(client), "71 CCC3", Congelar="No"))).json()    # estaba congelado

    assert v["quitan"] == {"congelar": 1}


# -------------------------------------------------------- la ventana
def test_si_alguien_edita_justo_entre_comparar_y_escribir_no_se_pisa(client, lista, monkeypatch):
    filas = _editar(_bajar(client), "71 AAA1", Tipo="Pesado")
    real = carga.planificar

    # Cambia a proposito (20-10-2026): `planificar` recibe `modo` (corto | completo | auto).
    def con_carrera(db, nombre, contenido, modo="auto"):
        plan = real(db, nombre, contenido, modo)
        db.add(PrecioOverride(tenant_id="curifor", producto="71 AAA1", obs="de otra persona"))
        db.commit()                                  # otra persona edita la ficha despues de comparar
        return plan

    monkeypatch.setattr(carga, "planificar", con_carrera)
    r = _subir(client, _a_csv(filas), aplicar=True)

    assert r.status_code == 200
    assert r.json()["aplicados"] == 0 and r.json()["omitidos"]["conflictos"] == 1
    o = _override(lista, "71 AAA1")
    assert o.tipo_manual is None and o.obs == "de otra persona"


def test_un_producto_que_se_borra_entre_comparar_y_escribir_no_da_500(client, lista, monkeypatch):
    filas = _editar(_bajar(client), "71 AAA1", Tipo="Pesado")
    real = carga.planificar

    def con_carrera(db, nombre, contenido, modo="auto"):     # ver arriba: `planificar` recibe `modo`
        plan = real(db, nombre, contenido, modo)
        db.query(PrecioProducto).filter_by(producto="71 AAA1").delete()
        db.commit()
        return plan

    monkeypatch.setattr(carga, "planificar", con_carrera)
    r = _subir(client, _a_csv(filas), aplicar=True)

    assert r.status_code == 200
    assert r.json()["aplicados"] == 0 and r.json()["omitidos"]["desconocidos"] == 1


def test_si_no_se_puede_leer_la_politica_no_se_carga_nada(client, lista, monkeypatch):
    """`politica.factores` atrapa el error y devuelve {}: leida despues de escribir,
    se llevaba por delante los overrides y el codigo seguia, con la auditoria hecha."""
    filas = _editar(_bajar(client), "71 AAA1", Tipo="Pesado")
    plan = carga.planificar(lista, "lista.csv", _a_csv(filas))
    monkeypatch.setattr(carga, "planificar", lambda *a, **k: plan)
    monkeypatch.setattr(carga.politica, "factores", lambda db: {})

    r = _subir(client, _a_csv(filas), aplicar=True)

    assert r.status_code == 422 and "política" in r.json()["detail"]
    assert _override(lista, "71 AAA1") is None
    assert _ficha(client, "71 AAA1")["precio_final"] == 17800
