"""Carga de precios desde Excel: lo que dejo la tercera revision (15-10-2026).

Un freno nuevo: una carga que pone mas de `UMBRAL_MASIVA` precios fijos o factores
propios pide confirmacion. Ordenar una sola columna (Precio final, Factor) deja cada
valor en la fila de otro producto, y cada fila parece una edicion valida.

Y los hallazgos menores: notas con caracteres que "CSV MS-DOS" o "Macintosh" no tienen,
pagina de codigos sin las columnas de descuento, notas que Excel lee como numero o fecha,
el escaneo del .xlsx con etiquetas poco comunes, filas vacias al final de un CSV, un error
de valor que una edicion ajena escondia como conflicto, y el plural de "error".
"""
import io

import pytest

from src.models import PrecioOverride
from src.services import precios_carga_service as carga
from src.services import precios_service as svc

from .test_precios import _producto, lista_cargada  # noqa: F401  (fixture)
from .test_precios_carga import _a_csv, _bajar, _editar, _override, _subir, lista  # noqa: F401
from .test_precios_carga_revision2 import _como_excel, _hoja, _texto_en, _xlsx_a_mano


def _con_productos(lista, n: int):
    for i in range(n):
        _producto(lista, f"72 M{i:03d}", procedencia_maestro="NACIONAL")
    svc.recalcular(lista, refrescar_insumos=False)


def _poner(filas, columna: str, valor: str, desde: int, hasta: int):
    """Escribe `valor` en `columna` de los productos 72 M<desde> a 72 M<hasta - 1>."""
    col = filas[0].index(columna)
    quiero = {f"72 M{i:03d}" for i in range(desde, hasta)}
    for f in filas[1:]:
        if f[0].strip() in quiero:
            f[col] = valor
    return filas


def test_cargar_mas_de_200_precios_fijos_pide_confirmacion(client, lista):
    _con_productos(lista, 201)
    contenido = _a_csv(_poner(_bajar(client), "Precio final", "123456", 0, 201))

    v = _subir(client, contenido).json()
    sin = _subir(client, contenido, aplicar=True)

    assert v["fijan_total"] == 201 and v["fijan"] == {"precio_fijo": 201}
    assert v["umbral_masiva"] == carga.UMBRAL_MASIVA == 200
    assert sin.status_code == 422 and "201 precios fijos o factores propios nuevos" in sin.json()["detail"]
    assert _override(lista, "72 M000") is None                  # sin confirmar, no se toco nada

    con = client.post("/api/precios/carga", data={"confirmar_masiva": "true"},
                      files={"archivo": ("lista.csv", contenido, "text/csv")})
    assert con.status_code == 200 and con.json()["aplicados"] == 201
    assert _override(lista, "72 M000").precio_fijo == 123456


def test_cargar_200_precios_fijos_no_pide_confirmacion(client, lista):
    _con_productos(lista, 200)

    r = _subir(client, _a_csv(_poner(_bajar(client), "Precio final", "123456", 0, 200)), aplicar=True)

    assert r.status_code == 200 and r.json()["aplicados"] == 200


def test_los_factores_propios_cuentan_junto_con_los_precios_fijos(client, lista):
    _con_productos(lista, 210)
    filas = _poner(_bajar(client), "Factor", "2", 0, 150)
    filas = _poner(filas, "Precio final", "123456", 150, 210)
    contenido = _a_csv(filas)

    v = _subir(client, contenido).json()
    sin = _subir(client, contenido, aplicar=True)

    assert v["fijan"] == {"factor": 150, "precio_fijo": 60} and v["fijan_total"] == 210
    assert sin.status_code == 422


def test_quitar_precios_fijos_no_cuenta_como_ponerlos(client, lista):
    """Quitar tiene su propio freno (`UMBRAL_QUITAS`): este es solo para poner."""
    _con_productos(lista, 5)
    for i in range(5):
        lista.add(PrecioOverride(tenant_id="curifor", producto=f"72 M{i:03d}", precio_fijo=1000.0 + i))
    lista.commit()
    svc.recalcular(lista, refrescar_insumos=False)

    v = _subir(client, _a_csv(_poner(_bajar(client), "Precio final", "", 0, 5))).json()

    assert v["a_cambiar"] == 5 and v["fijan_total"] == 0 and v["quitan_total"] == 5


# ------------------------------------------- CSV MS-DOS y Macintosh: otras paginas
@pytest.mark.parametrize("pagina,obs", [
    ("cp850", "Precio “especial” — según ‘convenio’ … • 5 € ™ ©"),      # texto pegado desde Word
    ("mac_roman", "½ m² 3³ ± × ÷ °C µ ¼ ¾ ¹"),
    ("cp850", "A → B ≥ 3"),
])
def test_una_nota_que_la_pagina_de_codigos_no_tiene_no_se_sobrescribe(client, lista, pagina, obs):
    """"CSV MS-DOS" (cp850) y "CSV Macintosh" cambian por "?" lo que su pagina no tiene, y
    la nota se tomaba por editada: la Referencia solo traia la huella de cp1252."""
    client.put("/api/precios/71 AAA1/override", json={"obs": obs})
    texto = _a_csv(_bajar(client)).decode("utf-8-sig")

    v = _subir(client, _como_excel(texto, pagina)).json()

    assert v["a_cambiar"] == 0 and v["errores_total"] == 0


def test_cambiar_de_verdad_una_nota_en_cp850_si_se_carga(client, lista):
    client.put("/api/precios/71 AAA1/override", json={"obs": "precio €100"})
    filas = _editar(_bajar(client), "71 AAA1", Obs="precio €120")

    r = _subir(client, _como_excel(_a_csv(filas).decode("utf-8-sig"), "cp850"), aplicar=True)

    assert r.status_code == 200 and r.json()["aplicados"] == 1
    assert _override(lista, "71 AAA1").obs == "precio ?120"       # lo que dejo Excel


def test_la_nota_se_compara_contra_la_actual_solo_si_nadie_edito_la_ficha(client, lista):
    """Si otra persona cambio la ficha despues de bajar el archivo, la tolerancia no se
    usa: seria comparar contra una nota que no es la del archivo."""
    client.put("/api/precios/71 AAA1/override", json={"obs": "precio €100"})
    texto = _a_csv(_bajar(client)).decode("utf-8-sig")
    client.put("/api/precios/71 AAA1/override", json={"obs": "otra cosa"})          # otra persona

    v = _subir(client, _como_excel(texto, "cp850")).json()

    assert v["a_cambiar"] == 0 and v["conflictos_total"] == 1


@pytest.mark.parametrize("pagina", ["cp850", "mac_roman"])
def test_sin_las_columnas_de_descuento_la_pagina_de_codigos_se_detecta_igual(client, lista, pagina):
    """Las columnas de descuento no se editan ni son obligatorias: sin ellas faltaba la
    unica marca con tilde, y cada "Sí" salia "S¡" o "S’"."""
    filas = _bajar(client)
    sobran = [filas[0].index(c) for c in svc.CAB_DESCUENTO]
    filas = [[v for j, v in enumerate(f) if j not in sobran] for f in filas]
    assert any("Sí" in f for f in filas)                    # 71 CCC3 esta congelado
    texto = _a_csv(filas).decode("utf-8-sig")

    v = _subir(client, _como_excel(texto, pagina)).json()

    assert v["errores_total"] == 0 and v["a_cambiar"] == 0, v["errores"][:2]


# ------------------------------------------------ notas que Excel lee como numero
@pytest.mark.parametrize("obs", ["0123", "3/4", "10-12", "1E5", "$ 5.000", "569123456789",
                                 "12345678901234567890", "15%", "12:30", "1,5", "2026-10-15", "'0123"])
def test_una_nota_que_excel_leeria_como_numero_o_fecha_sale_protegida_y_vuelve_igual(client, lista, obs):
    """"0123" pasa a 123, "3/4" a 03-abr y un telefono de 12 digitos a 5,69123E+11: se
    perdian digitos y la nota parecia editada. El apostrofe la deja como texto."""
    client.put("/api/precios/71 AAA1/override", json={"obs": obs})
    filas = _bajar(client)
    celda = next(f for f in filas[1:] if f[0] == "71 AAA1")[filas[0].index("Obs")]

    assert celda == "'" + obs
    v = _subir(client, _a_csv(filas)).json()
    assert v["a_cambiar"] == 0 and v["errores_total"] == 0


@pytest.mark.parametrize("obs", ["5", "12345", "piso", "revisar 3/4", "1.5 m"])
def test_lo_que_vuelve_igual_desde_excel_no_lleva_apostrofe(client, lista, obs):
    client.put("/api/precios/71 AAA1/override", json={"obs": obs})
    filas = _bajar(client)

    assert next(f for f in filas[1:] if f[0] == "71 AAA1")[filas[0].index("Obs")] == obs


@pytest.mark.parametrize("texto", ["=a", "'=a", "-5%", "0123", "'0123", "''0123", "5", "'5", "piso", "'", ""])
def test_proteger_y_quitar_el_apostrofe_son_inversos(texto):
    assert carga._c_obs(carga._proteger_obs(texto)) == carga._c_texto(texto)


# --------------------------------------------------------- escaneo del .xlsx
@pytest.mark.parametrize("celda", [
    '<c r="T1048576" t="inlineStr"><is><t>x</t></is></c>',
    '<c t="inlineStr" r="T1048576"><is><t>x</t></is></c>',          # otro orden de atributos
    "<c r='T1048576'><v>1</v></c>",                                  # comillas simples
    '<c  r="T1048576"><v>1</v></c>',                                 # dos espacios
    '<c\n r="T1048576"><v>1</v></c>',                                # salto de linea
    '<x:c r="T1048576"><x:v>1</x:v></x:c>',                          # prefijo de espacio de nombres
    '<x:c s="1" r="T1048576" t="n"><x:v>1</x:v></x:c>',
])
def test_el_escaneo_ve_una_celda_aunque_la_etiqueta_no_sea_la_de_excel(celda):
    """calamine lee todas estas formas: un xlsx de 1,6 KB llegaba a 1 GB de memoria."""
    xml = _hoja(f"<row r=\"1048576\">{celda}</row>")

    assert carga._escanear_hoja(io.BytesIO(xml.encode("utf-8"))) == (1048576, 20)


@pytest.mark.parametrize("celda", [
    '<c r="T1048576" s="1"/>', '<c r="T1048576" s="1"></c>', '<x:c r="T1048576" s="1"></x:c>',
    "<c r='T1048576' s='1'/>",
])
def test_el_escaneo_no_cuenta_las_celdas_vacias_con_formato(celda):
    assert carga._escanear_hoja(io.BytesIO(_hoja(f"<row r=\"1\">{celda}</row>").encode("utf-8"))) == (0, 0)


def test_una_celda_sin_referencia_ocupa_el_lugar_de_su_fila():
    """Sin `r` en la celda, la posicion la da `<row r=`: una fila perdida al final no se escapa."""
    lejos = _hoja('<row r="1048576"><c t="inlineStr"><is><t>x</t></is></c></row>')
    juntas = _hoja("<row><c><v>1</v></c><c><v>2</v></c></row><row><c><v>3</v></c></row>")

    assert carga._escanear_hoja(io.BytesIO(lejos.encode("utf-8"))) == (1048576, 1)
    assert carga._escanear_hoja(io.BytesIO(juntas.encode("utf-8"))) == (2, 2)


@pytest.mark.parametrize("bloque", [64, 211, 1000, 4096])
def test_el_escaneo_pasa_de_la_via_rapida_a_la_general_en_cualquier_borde(monkeypatch, bloque):
    """Las etiquetas de Excel se leen rapido; la primera rara cambia a la lectura general, aunque
    caiga en el borde de un bloque."""
    canonicas = "".join(_texto_en(f"A{n}") for n in range(1, 60))
    rara = "<row r='60'><c t=\"inlineStr\" r=\"T1048576\"><is><t>x</t></is></c></row>"
    monkeypatch.setattr(carga, "_BLOQUE_XML", bloque)

    assert carga._escanear_hoja(io.BytesIO(_hoja(canonicas + rara).encode("utf-8"))) == (1048576, 20)
    assert carga._escanear_hoja(io.BytesIO(_hoja(canonicas).encode("utf-8"))) == (59, 1)


@pytest.mark.parametrize("fila", ['<row r="99999999999">', '<row r="abc">'])
def test_una_fila_con_numero_danado_se_rechaza(fila):
    xml = _hoja(f'{fila}<c r="A1"><v>1</v></c></row>')

    with pytest.raises(carga.ErrorCarga, match="referencia dañada"):
        carga._escanear_hoja(io.BytesIO(xml.encode("utf-8")))


def test_un_xlsx_con_una_celda_de_texto_gigante_se_rechaza_sin_abrirlo(client, lista):
    """Una cadena de 100 MB cabia bajo el tope descomprimido y llevaba la memoria a 406 MB."""
    hoja = _hoja('<row r="1"><c r="A1" t="inlineStr"><is><t>' + "x" * (_TEXTO + 10) + "</t></is></c></row>")

    r = _subir(client, _xlsx_a_mano(hoja), nombre="lista.xlsx")

    assert r.status_code == 422 and "muchísimo texto" in r.json()["detail"]


_TEXTO = carga._TEXTO_MAXIMO


def test_un_xlsx_de_otra_forma_de_escribir_la_celda_perdida_se_rechaza_sin_abrirlo(client, lista):
    hoja = _hoja('<x:row r="1048576"><x:c r="T1048576" t="inlineStr"><x:is><x:t>x</x:t></x:is></x:c></x:row>')

    r = _subir(client, _xlsx_a_mano(hoja), nombre="lista.xlsx")

    assert r.status_code == 422 and "primera hoja tiene contenido" in r.json()["detail"]


def test_si_los_datos_estan_en_la_segunda_hoja_el_mensaje_dice_que_solo_se_lee_la_primera(client, lista):
    from openpyxl import Workbook

    wb = Workbook()
    wb.active.title = "Notas"
    wb.active["A1"] = "apuntes de la reunion"
    datos = wb.create_sheet("Datos")
    for f in _bajar(client):
        datos.append(f)
    buf = io.BytesIO()
    wb.save(buf)

    r = _subir(client, buf.getvalue(), nombre="lista.xlsx")

    assert r.status_code == 422
    assert "No encuentro las columnas Producto y Referencia" in r.json()["detail"]
    assert "solo se lee la primera hoja" in r.json()["detail"]


def test_el_mensaje_de_la_primera_hoja_no_sale_en_un_csv(client, lista):
    r = _subir(client, b"a;b\r\n1;2\r\n")

    assert r.status_code == 422 and "primera hoja" not in r.json()["detail"]


# ---------------------------------------------------- CSV con filas vacias al final
def test_las_filas_vacias_al_final_de_un_csv_no_cuentan_como_celdas(client, lista, monkeypatch):
    """Excel escribe ";;;;" por cada fila con formato debajo de los datos. Contaban como
    celdas y el mensaje culpaba a las columnas."""
    monkeypatch.setattr(carga, "MAX_CELDAS", 1000)
    filas = _bajar(client)
    vacias = ";" * (len(filas[0]) - 1) + "\r\n"

    r = _subir(client, _a_csv(filas) + (vacias * 5000).encode("utf-8"))

    assert r.status_code == 200, r.text
    assert r.json()["errores_total"] == 0 and r.json()["a_cambiar"] == 0


def test_demasiadas_celdas_con_texto_siguen_rechazandose_y_el_mensaje_habla_de_filas_y_columnas(
        client, lista, monkeypatch):
    monkeypatch.setattr(carga, "MAX_CELDAS", 50)

    r = _subir(client, _a_csv(_bajar(client)))

    assert r.status_code == 422
    assert "celdas con contenido" in r.json()["detail"] and "filas o columnas de más" in r.json()["detail"]


def test_el_tope_de_celdas_deja_holgura_en_la_memoria_del_plan_gratis():
    assert carga.MAX_CELDAS <= 2_000_000 and carga.MAX_DESCOMPRIMIDO <= 100 * 1024 * 1024


# ------------------------------------------- un error del archivo no se esconde
def test_un_error_de_valor_no_se_esconde_como_conflicto_aunque_otra_persona_edite_el_producto(client, lista):
    """Otra persona edita la Obs de X despues de bajar el archivo; el archivo trae un tipo
    que no existe en X y un cambio bueno en otro producto. Antes salia "conflicto", la carga
    seguia y el error aparecia recien al repetir el cambio."""
    filas = _bajar(client)
    client.put("/api/precios/71 AAA1/override", json={"obs": "de otra persona"})
    filas = _editar(filas, "71 AAA1", Tipo="NoExisteEsteTipo")
    filas = _editar(filas, "13 BBB2", Tipo="Pesado")

    v = _subir(client, _a_csv(filas)).json()
    r = _subir(client, _a_csv(filas), aplicar=True)

    assert v["errores_total"] == 1 and v["errores"][0]["producto"] == "71 AAA1"
    assert v["conflictos_total"] == 0
    assert r.status_code == 422
    assert _override(lista, "13 BBB2").tipo_manual is None          # todo o nada


def test_un_factor_fuera_de_rango_tambien_bloquea_con_edicion_ajena(client, lista):
    filas = _bajar(client)
    client.put("/api/precios/71 AAA1/override", json={"obs": "de otra persona"})

    v = _subir(client, _a_csv(_editar(filas, "71 AAA1", Factor="11"))).json()

    assert v["errores_total"] == 1 and v["conflictos_total"] == 0


# ---------------------------------------------- el factor redondeado se cuenta
def test_los_factores_redondeados_por_excel_se_cuentan_en_la_vista_previa(client, lista):
    _producto(lista, "72 R01", procedencia_maestro="NACIONAL")
    svc.recalcular(lista, refrescar_insumos=False)
    client.put("/api/precios/71 AAA1/override", json={"margen_fijo": 35})          # factor 1,5385
    client.put("/api/precios/72 R01/override", json={"margen_fijo": 12.5})         # factor 1,1429
    filas = _editar(_bajar(client), "71 AAA1", Factor="1,54")      # lo que dejo "disminuir decimales"
    filas = _editar(filas, "72 R01", Factor="1,14")

    v = _subir(client, _a_csv(filas)).json()

    assert v["a_cambiar"] == 0
    assert v["factor_redondeado_total"] == 2
    assert sorted(v["factor_redondeado"]) == ["71 AAA1", "72 R01"]


def test_sin_redondeos_la_cuenta_es_cero_y_una_edicion_de_verdad_no_cuenta(client, lista):
    client.put("/api/precios/71 AAA1/override", json={"margen_fijo": 35})
    sin_tocar = _subir(client, _a_csv(_bajar(client))).json()
    editado = _subir(client, _a_csv(_editar(_bajar(client), "71 AAA1", Factor="1,6"))).json()

    assert sin_tocar["factor_redondeado_total"] == 0 and sin_tocar["factor_redondeado"] == []
    assert editado["factor_redondeado_total"] == 0 and editado["a_cambiar"] == 1


# ---------------------------------------------------------------- el plural
def test_el_mensaje_de_errores_concuerda_con_la_cantidad(client, lista):
    uno = _subir(client, _a_csv(_editar(_bajar(client), "71 AAA1", Factor="0,9")), aplicar=True)
    dos = _subir(client, _a_csv(_editar(_editar(_bajar(client), "71 AAA1", Factor="0,9"),
                                        "13 BBB2", Factor="0,8")), aplicar=True)

    assert uno.status_code == 422 and dos.status_code == 422
    assert "1 error. No se cargó nada: corrígelo y súbelo de nuevo." in uno.json()["detail"]
    assert "2 errores. No se cargó nada: corrígelos y súbelo de nuevo." in dos.json()["detail"]
