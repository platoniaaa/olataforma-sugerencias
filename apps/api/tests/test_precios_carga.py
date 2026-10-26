"""Editar la lista de precios en Excel: bajar, editar y volver a cargar.

Lo que estos tests cuidan:

1. Que bajar y subir SIN tocar nada no cambie nada: es la base de todo lo demas.
2. Que cada columna editable haga lo mismo que su equivalente en la ficha.
3. Que lo que la lista cambio SOLA entre la descarga y la carga (el motor recalcula
   los precios cada noche) no se confunda con una edicion y se vuelva precio fijo.
4. Que lo que otra persona decidio en la ficha despues de bajar el archivo no se pise
   en silencio.
5. Que un error en el archivo no cargue la mitad: todo o nada.
"""
import csv
import io

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.models import AuditoriaLog, PrecioCambio, PrecioOverride, PrecioProducto
from src.services import precios_carga_service as carga
from src.services import precios_service as svc
from src.services.auth import requiere_auth

from .test_precios import lista_cargada  # noqa: F401  (fixture)


@pytest.fixture()
def lista(lista_cargada):  # noqa: F811
    svc.recalcular(lista_cargada)
    return lista_cargada


# ---------------------------------------------------------------- utilidades
def _bajar(client) -> list[list[str]]:
    r = client.get("/api/precios/exportar", params={"formato": "editable"})
    assert r.status_code == 200, r.text
    return list(csv.reader(io.StringIO(r.content.decode("utf-8-sig")), delimiter=";"))


def _a_csv(filas, sep=";", codificacion="utf-8-sig") -> bytes:
    buf = io.StringIO()
    csv.writer(buf, delimiter=sep, lineterminator="\r\n").writerows(filas)
    return buf.getvalue().encode(codificacion)


def _editar(filas, producto, **celdas):
    """Cambia celdas de la fila de `producto` (por nombre de columna, con `_` en vez
    de espacio). Devuelve las filas: edita sobre una copia."""
    filas = [list(f) for f in filas]
    cab = filas[0]
    for f in filas[1:]:
        if f[0].strip() == producto:
            for nombre, valor in celdas.items():
                f[cab.index(nombre.replace("_", " "))] = valor
            return filas
    raise AssertionError(f"{producto} no esta en el archivo")


def _subir(client, contenido, nombre="lista.csv", aplicar=False):
    ruta = "/api/precios/carga" if aplicar else "/api/precios/carga/vista-previa"
    return client.post(ruta, files={"archivo": (nombre, contenido, "application/octet-stream")})


def _ficha(client, producto):
    return client.get(f"/api/precios/{producto}").json()


def _override(db, producto):
    db.expire_all()
    return db.query(PrecioOverride).filter_by(producto=producto).one_or_none()


# ------------------------------------------------------------------ descarga
def test_el_archivo_para_editar_trae_las_columnas_y_la_referencia(client, lista):
    filas = _bajar(client)
    cab = filas[0]

    # Cambia a proposito (20-10-2026): al final se agregan Precio fijo, Margen fijo %, Desde,
    # Hasta y Vigencia. El orden completo de las 25 esta en test_precios_carga_v2.py.
    assert cab[-9:] == ["Obs", "Congelar", "No es producto", "Precio fijo", "Margen fijo %",
                        "Desde", "Hasta", "Vigencia", "Referencia"]
    assert {"Producto", "Tipo", "Procedencia", "Factor", "Precio final", "Estado"} <= set(cab)
    por = {f[0]: dict(zip(cab, f)) for f in filas[1:]}
    aaa1 = por["71 AAA1"]
    assert (aaa1["Tipo"], aaa1["Factor"], aaa1["Precio final"]) == ("Liviano", "1,78", "17800")
    assert aaa1["Congelar"] == "No" and aaa1["No es producto"] == "No"
    # La referencia lleva lo que mostraba el archivo (la observacion, como huella), la
    # huella de las decisiones de las personas y la huella del codigo.
    # Cambia a proposito (20-10-2026): la Referencia v2 tiene 14 partes (la v1, 10): suma las
    # cuatro columnas de precio fijo, margen fijo, desde y hasta antes de la huella de las
    # decisiones.
    partes = aaa1["Referencia"].split("|")
    assert len(partes) == 14 and partes[0] == carga._h("71 AAA1")        # el codigo, primero
    assert partes[1:8] == ["Liviano", "Nacional", "1.78", "17800", carga._h(""), carga._h(""), "0"]
    assert partes[8] == "0"
    assert partes[9:13] == ["", "", "", ""]                               # sin decision ni periodo
    # Lo que decidio una persona se ve en su fila.
    assert por["13 BBB2"]["Obs"] == "piso" and por["13 BBB2"]["Precio final"] == "990"
    assert por["71 CCC3"]["Congelar"] == "Sí"


def test_el_factor_del_archivo_trae_4_decimales(client, lista):
    """Un margen fijo da 1,5385: con 2 decimales saldria 1,54 y al subirlo parecería
    una edicion."""
    client.put("/api/precios/71 AAA1/override", json={"margen_fijo": 35})

    por = {f[0]: f for f in _bajar(client)[1:]}
    cab = _bajar(client)[0]

    assert por["71 AAA1"][cab.index("Factor")] == "1,5385"


def test_la_lista_completa_de_siempre_no_cambia(client, lista):
    r = client.get("/api/precios/exportar", params={"formato": "completa"})
    cab = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig")), delimiter=";"))[0]
    assert "Referencia" not in cab and "Obs" not in cab


# ------------------------------------------------------------ ida y vuelta
def test_bajar_y_subir_sin_tocar_nada_no_cambia_nada(client, lista):
    filas = _bajar(client)

    r = _subir(client, _a_csv(filas))

    assert r.status_code == 200, r.text
    v = r.json()
    assert v["filas"] == len(filas) - 1 and v["a_cambiar"] == 0 and v["errores_total"] == 0
    assert v["sin_cambios"] == v["filas"]
    assert v["conflictos_total"] == v["desconocidos_total"] == v["sin_referencia_total"] == 0


def test_un_precio_fijo_con_medio_peso_no_es_una_edicion(client, lista):
    """`round` de Python baja 1234,5 a 1234; la referencia sube a 1235."""
    client.put("/api/precios/71 AAA1/override", json={"precio_fijo": 1234.5})

    v = _subir(client, _a_csv(_bajar(client))).json()

    assert v["a_cambiar"] == 0


def test_un_codigo_con_espacio_al_final_se_carga_igual(client, lista):
    p = lista.query(PrecioProducto).filter_by(producto="71 AAA1").one()
    p.codigo_erp = "71 AAA1 "
    lista.commit()
    filas = _bajar(client)
    assert any(f[0] == "71 AAA1 " for f in filas[1:])

    v = _subir(client, _a_csv(_editar(filas, "71 AAA1", Tipo="Pesado"))).json()

    assert v["a_cambiar"] == 1 and v["desconocidos_total"] == 0


def test_dos_codigos_que_solo_difieren_en_un_espacio_de_adentro_son_productos_distintos(client, lista):
    """En produccion hay "19  FB5Z15201H" y "19 FB5Z15201H". Al leer el archivo se
    fundian en uno: error de codigo repetido, o peor, la edicion de uno caia en el otro."""
    from tests.test_precios import _producto

    _producto(lista, "71 DOBLE", procedencia_maestro="NACIONAL")
    _producto(lista, "71  DOBLE", procedencia_maestro="NACIONAL")
    svc.recalcular(lista)
    filas = _bajar(client)

    sin_tocar = _subir(client, _a_csv(filas)).json()
    editado = _editar(filas, "71  DOBLE", Tipo="Pesado")
    r = _subir(client, _a_csv(editado), aplicar=True)

    assert sin_tocar["errores_total"] == 0 and sin_tocar["a_cambiar"] == 0
    assert r.status_code == 200 and r.json()["aplicados"] == 1
    assert _override(lista, "71  DOBLE").tipo_manual == "Pesado"
    assert _override(lista, "71 DOBLE") is None


# ---------------------------------------------------- cada columna editable
def test_editar_el_tipo_lo_escribe_a_mano(client, lista):
    filas = _editar(_bajar(client), "71 AAA1", Tipo="Pesado")

    previa = _subir(client, _a_csv(filas)).json()
    r = _subir(client, _a_csv(filas), aplicar=True)

    assert previa["a_cambiar"] == 1
    (c,) = previa["cambios"]
    assert c["campos"] == [{"campo": "Tipo", "antes": "(el del rubro: Liviano)", "despues": "Pesado"}]
    assert (c["precio_antes"], c["precio_despues"]) == (17800, 21600)
    assert r.status_code == 200, r.text
    ficha = _ficha(client, "71 AAA1")
    assert (ficha["tipo"], ficha["tipo_origen"], ficha["precio_final"]) == ("Pesado", "manual", 21600)


def test_el_tipo_se_acepta_con_otra_mayuscula_o_con_el_alias(client, lista):
    filas = _editar(_bajar(client), "71 AAA1", Tipo="NEUMATICOS")

    _subir(client, _a_csv(filas), aplicar=True)

    assert _override(lista, "71 AAA1").tipo_manual == "Neumatico"


def test_vaciar_el_tipo_vuelve_a_seguir_al_rubro(client, lista):
    """71 CCC3 tiene Pesado escrito a mano: la celda vacia lo quita."""
    filas = _editar(_bajar(client), "71 CCC3", Tipo="")

    _subir(client, _a_csv(filas), aplicar=True)

    assert _override(lista, "71 CCC3").tipo_manual is None
    assert _ficha(client, "71 CCC3")["tipo"] == "Liviano"


def test_editar_la_procedencia_la_escribe_a_mano(client, lista):
    filas = _editar(_bajar(client), "71 AAA1", Procedencia="importado")

    _subir(client, _a_csv(filas), aplicar=True)

    ficha = _ficha(client, "71 AAA1")
    assert (ficha["procedencia_final"], ficha["procedencia_origen"], ficha["precio_final"]) == (
        "Importado", "manual", 18900)


@pytest.mark.parametrize("factor", [1.88, 1.5385, 2.0, 1.01, 9.9999, 3.3333, 1.0001, 7.77])
def test_el_factor_editado_queda_como_factor_propio(client, lista, factor):
    texto = f"{factor}".replace(".", ",")
    filas = _editar(_bajar(client), "71 AAA1", Factor=texto)

    r = _subir(client, _a_csv(filas), aplicar=True)

    assert r.status_code == 200, r.text
    ficha = _ficha(client, "71 AAA1")
    assert ficha["estado"] == "MARGEN"
    assert ficha["factor"] == round(factor, 4)
    assert ficha["precio_final"] == svc.redondear(10000 * round(factor, 4))


def test_el_margen_que_se_guarda_da_exactamente_el_factor_pedido():
    """El factor se guarda como margen: la ida y vuelta no puede perder ni un decimal."""
    f = 1.0001
    while f <= 10:
        margen = round((1 - 1 / f) * 100, 8)
        assert svc.factor_desde_margen(margen) == round(f, 4), f
        f += 0.0137


def test_el_precio_final_editado_queda_como_precio_fijo(client, lista):
    filas = _editar(_bajar(client), "71 AAA1", Precio_final="20.000")

    previa = _subir(client, _a_csv(filas)).json()
    r = _subir(client, _a_csv(filas), aplicar=True)

    assert previa["cambios"][0]["campos"] == [
        {"campo": "Precio fijo", "antes": "(sin precio fijo)", "despues": "20.000"}]
    assert r.status_code == 200, r.text
    ficha = _ficha(client, "71 AAA1")
    assert (ficha["estado"], ficha["precio_final"]) == ("FIJO", 20000)


def test_vaciar_el_precio_quita_el_precio_fijo(client, lista):
    """13 BBB2 tiene precio fijo 990."""
    filas = _editar(_bajar(client), "13 BBB2", Precio_final="")

    _subir(client, _a_csv(filas), aplicar=True)

    assert _override(lista, "13 BBB2").precio_fijo is None
    assert _ficha(client, "13 BBB2")["estado"] != "FIJO"


def test_vaciar_un_precio_que_no_era_fijo_no_hace_nada(client, lista):
    filas = _editar(_bajar(client), "71 AAA1", Precio_final="")

    v = _subir(client, _a_csv(filas)).json()

    assert v["a_cambiar"] == 0 and v["errores_total"] == 0


def test_obs_congelar_y_no_es_producto(client, lista):
    filas = _bajar(client)
    filas = _editar(filas, "71 AAA1", Obs="precio de piso", Congelar="Sí")
    filas = _editar(filas, "71 CCC3", Congelar="No")
    filas = _editar(filas, "13 BBB2", No_es_producto="sí")

    r = _subir(client, _a_csv(filas), aplicar=True)

    assert r.status_code == 200, r.text
    a = _override(lista, "71 AAA1")
    assert (a.obs, a.congelar, a.congelado_precio) == ("precio de piso", True, 17800)
    assert _override(lista, "71 CCC3").congelar is False
    assert _override(lista, "13 BBB2").no_producto is True


def test_congelar_congela_el_precio_de_hoy_no_el_del_archivo(client, lista):
    filas = _bajar(client)                                   # el archivo dice 17.800
    lista.query(PrecioProducto).filter_by(producto="71 AAA1").one().costo = 20000
    lista.commit()
    svc.recalcular(lista, refrescar_insumos=False)           # hoy vale 35.600

    _subir(client, _a_csv(_editar(filas, "71 AAA1", Congelar="Sí")), aplicar=True)

    assert _override(lista, "71 AAA1").congelado_precio == 35600


# ------------------------------------------- lo que cambio mientras tanto
def test_lo_que_el_motor_movio_no_se_vuelve_precio_fijo(client, lista):
    """El archivo dice 17.800; de noche el costo sube y el precio pasa a 35.600.
    Quien sube el archivo sin tocar el precio no decidio nada sobre el precio."""
    filas = _bajar(client)
    lista.query(PrecioProducto).filter_by(producto="71 AAA1").one().costo = 20000
    lista.commit()
    svc.recalcular(lista, refrescar_insumos=False)

    v = _subir(client, _a_csv(filas)).json()
    assert v["a_cambiar"] == 0

    # Y si ademas edita OTRA columna, el precio tampoco se toca.
    filas = _editar(filas, "71 AAA1", Obs="revisar")
    _subir(client, _a_csv(filas), aplicar=True)
    assert _override(lista, "71 AAA1").precio_fijo is None
    assert _ficha(client, "71 AAA1")["precio_final"] == 35600


def test_si_alguien_edito_el_producto_despues_de_bajar_el_archivo_no_se_pisa(client, lista):
    filas = _bajar(client)
    client.put("/api/precios/71 AAA1/override", json={"tipo_manual": "Pesado"})   # otra persona

    # El archivo edita la observacion del MISMO producto y el precio de otro.
    filas = _editar(filas, "71 AAA1", Obs="mi cambio")
    filas = _editar(filas, "13 BBB2", Precio_final="1500")
    previa = _subir(client, _a_csv(filas)).json()
    r = _subir(client, _a_csv(filas), aplicar=True)

    assert previa["conflictos_total"] == 1 and previa["conflictos"][0]["producto"] == "71 AAA1"
    assert previa["a_cambiar"] == 1                       # el otro producto si va
    assert r.json()["aplicados"] == 1 and r.json()["omitidos"]["conflictos"] == 1
    assert _override(lista, "71 AAA1").obs is None        # no se pisó
    assert _override(lista, "71 AAA1").tipo_manual == "Pesado"
    assert _override(lista, "13 BBB2").precio_fijo == 1500


def test_una_fila_que_nadie_toco_no_es_conflicto_aunque_el_producto_haya_cambiado(client, lista):
    filas = _bajar(client)
    client.put("/api/precios/71 AAA1/override", json={"tipo_manual": "Pesado"})

    v = _subir(client, _a_csv(filas)).json()

    assert v["conflictos_total"] == 0 and v["a_cambiar"] == 0


# ------------------------------------------------------ lo que se ignora
def test_un_codigo_que_no_esta_en_la_lista_se_ignora_y_se_avisa(client, lista):
    filas = _bajar(client)
    nueva = next(list(f) for f in filas[1:] if f[0] == "71 AAA1")   # copia de una fila real...
    nueva[0] = "71 NO-EXISTE"                            # ...con otro codigo
    nueva[filas[0].index("Tipo")] = "Pesado"             # ...y una edicion
    ref = filas[0].index("Referencia")
    nueva[ref] = "|".join([carga._h("71 NO-EXISTE")] + nueva[ref].split("|")[1:])   # que es de el
    filas.append(nueva)
    filas.append([""] * len(filas[0]))                   # y una fila en blanco al final

    v = _subir(client, _a_csv(filas)).json()

    assert v["desconocidos"] == ["71 NO-EXISTE"] and v["desconocidos_total"] == 1
    assert v["a_cambiar"] == 0 and v["errores_total"] == 0


def test_una_fila_sin_referencia_no_se_carga(client, lista):
    filas = _editar(_bajar(client), "71 AAA1", Tipo="Pesado", Referencia="")

    v = _subir(client, _a_csv(filas)).json()

    assert v["sin_referencia"] == ["71 AAA1"] and v["a_cambiar"] == 0


# --------------------------------------------------------------- errores
def test_un_error_en_el_archivo_bloquea_toda_la_carga(client, lista):
    filas = _bajar(client)
    filas = _editar(filas, "71 AAA1", Tipo="Pesado")          # esta esta bien
    filas = _editar(filas, "13 BBB2", Precio_final="1500")     # esta tambien
    filas = _editar(filas, "71 CCC3", Factor="0,9", Procedencia="Marte")

    previa = _subir(client, _a_csv(filas)).json()
    r = _subir(client, _a_csv(filas), aplicar=True)

    assert previa["errores_total"] == 2
    msgs = " | ".join(e["mensaje"] for e in previa["errores"])
    assert "Factor" in msgs and "Procedencia" in msgs
    assert r.status_code == 422 and "2 error" in r.json()["detail"]
    # Nada se cargó, ni lo que estaba bien.
    assert _override(lista, "71 AAA1") is None
    assert _override(lista, "13 BBB2").precio_fijo == 990


def test_un_tipo_que_no_existe_dice_cuales_hay(client, lista):
    filas = _editar(_bajar(client), "71 AAA1", Tipo="Livano")

    v = _subir(client, _a_csv(filas)).json()

    (e,) = v["errores"]
    assert e["fila"] == 3 and e["producto"] == "71 AAA1"      # fila 1 = encabezados; 13 BBB2 es la 2
    assert '"Livano" no existe' in e["mensaje"] and "Liviano" in e["mensaje"]


@pytest.mark.parametrize("columna,valor,texto", [
    ("Factor", "1", "mayor que 1"), ("Factor", "11", "hasta 10"), ("Factor", "abc", "no entiendo"),
    ("Precio_final", "-5", "negativo"), ("Precio_final", "mucho", "no entiendo"),
    ("Congelar", "quizás", "Sí o No"), ("Obs", "x" * 501, "501 caracteres"),
])
def test_los_valores_invalidos_se_rechazan_con_un_mensaje_claro(client, lista, columna, valor, texto):
    filas = _editar(_bajar(client), "71 AAA1", **{columna: valor})

    v = _subir(client, _a_csv(filas)).json()

    assert v["errores_total"] == 1 and texto in v["errores"][0]["mensaje"]


def test_precio_fijo_y_factor_propio_a_la_vez_es_un_error(client, lista):
    filas = _editar(_bajar(client), "71 AAA1", Factor="1,88", Precio_final="20000")

    v = _subir(client, _a_csv(filas)).json()

    assert v["errores_total"] == 1 and "precio fijo y factor propio" in v["errores"][0]["mensaje"]


def test_cambiar_el_precio_de_un_producto_con_factor_propio_pide_quitar_el_factor(client, lista):
    client.put("/api/precios/71 AAA1/override", json={"margen_fijo": 35})
    filas = _editar(_bajar(client), "71 AAA1", Precio_final="20000")
    assert _subir(client, _a_csv(filas)).json()["errores_total"] == 1

    # Quitandole el factor en la misma fila, si se puede.
    filas = _editar(filas, "71 AAA1", Factor="")
    r = _subir(client, _a_csv(filas), aplicar=True)

    assert r.status_code == 200, r.text
    o = _override(lista, "71 AAA1")
    assert (o.precio_fijo, o.margen_fijo) == (20000, None)


def test_un_codigo_repetido_es_un_error(client, lista):
    filas = _bajar(client)
    filas.append(list(filas[1]))

    v = _subir(client, _a_csv(filas)).json()

    assert v["errores_total"] == 1 and "repetido" in v["errores"][0]["mensaje"]


# ------------------------------------------------------- formatos de archivo
@pytest.mark.parametrize("sep,codificacion", [(";", "utf-8-sig"), (";", "cp1252"), (",", "utf-8"), ("\t", "utf-8")])
def test_acepta_el_csv_como_lo_deja_excel(client, lista, sep, codificacion):
    """Excel guarda "CSV" en la pagina de codigos de Windows (no en UTF-8) y el
    separador depende de la configuracion regional."""
    filas = _editar(_bajar(client), "71 AAA1", Obs="revisión áéíóú ñ", Tipo="Pesado")

    r = _subir(client, _a_csv(filas, sep=sep, codificacion=codificacion), aplicar=True)

    assert r.status_code == 200, r.text
    o = _override(lista, "71 AAA1")
    assert o.tipo_manual == "Pesado" and o.obs == "revisión áéíóú ñ"


def test_acepta_un_xlsx_con_numeros_de_verdad(client, lista):
    """En un .xlsx el factor y el precio vienen como numeros, no como "1,88"."""
    from openpyxl import Workbook

    filas = _bajar(client)
    cab = filas[0]
    wb = Workbook()
    ws = wb.active
    ws.append(cab)
    for f in filas[1:]:
        fila = list(f)
        if f[0] == "71 AAA1":
            fila[cab.index("Factor")] = 1.88
        elif f[0] == "13 BBB2":
            fila[cab.index("Precio final")] = 1500
        ws.append(fila)
    buf = io.BytesIO()
    wb.save(buf)

    previa = _subir(client, buf.getvalue(), nombre="lista.xlsx").json()
    r = _subir(client, buf.getvalue(), nombre="lista.xlsx", aplicar=True)

    assert previa["a_cambiar"] == 2 and previa["errores_total"] == 0
    assert r.status_code == 200, r.text
    assert _ficha(client, "71 AAA1")["precio_final"] == 18800
    assert _override(lista, "13 BBB2").precio_fijo == 1500


@pytest.mark.parametrize("nombre,contenido,texto", [
    ("lista.csv", b"", "vacío"),
    ("lista.pdf", b"x", "csv o .xlsx"),
    ("lista.xls", b"x", "antiguo"),
    ("lista.xlsx", b"esto no es un excel", "No pude abrir"),
    ("lista.csv", b"Producto;Tipo\r\n71 A;Liviano\r\n", "Producto y Referencia"),
])
def test_un_archivo_que_no_sirve_dice_por_que(client, lista, nombre, contenido, texto):
    r = _subir(client, contenido, nombre=nombre)

    assert r.status_code == 422 and texto in r.json()["detail"]


def test_si_falta_una_columna_dice_cual(client, lista):
    filas = _bajar(client)
    i = filas[0].index("Obs")
    sin_obs = [f[:i] + f[i + 1:] for f in filas]

    r = _subir(client, _a_csv(sin_obs))

    assert r.status_code == 422 and "Faltan las columnas: Obs" in r.json()["detail"]


def test_las_columnas_pueden_estar_en_otro_orden_y_con_otras_mayusculas(client, lista):
    filas = _editar(_bajar(client), "71 AAA1", Tipo="Pesado")
    cab = [c.upper() if c in ("Tipo", "Obs") else c for c in filas[0]]
    filas = [cab] + filas[1:]

    assert _subir(client, _a_csv(filas)).json()["a_cambiar"] == 1


# ------------------------------------------------------ lo que deja la carga
def test_la_carga_deja_rastro_en_auditoria(client, lista):
    filas = _editar(_bajar(client), "71 AAA1", Tipo="Pesado", Obs="piso")

    _subir(client, _a_csv(filas), aplicar=True)

    por = {a.accion: a for a in lista.query(AuditoriaLog).filter(
        AuditoriaLog.accion.in_(["precio_override", "precios_carga_excel"])).all()}
    ficha = por["precio_override"]
    assert (ficha.producto, ficha.usuario_email) == ("71 AAA1", "test@curifor.com")
    assert "tipo_manual None -> Pesado" in ficha.detalle and "(carga desde Excel)" in ficha.detalle
    resumen = por["precios_carga_excel"]
    assert resumen.usuario_email == "test@curifor.com" and "1 productos" in resumen.detalle


def test_la_carga_no_llena_la_lista_de_cambios_sin_revisar(client, lista):
    """Son decisiones de una persona, no cambios que alguien tenga que revisar."""
    antes = lista.query(PrecioCambio).count()

    _subir(client, _a_csv(_editar(_bajar(client), "71 AAA1", Tipo="Pesado")), aplicar=True)

    assert lista.query(PrecioCambio).count() == antes
    assert _ficha(client, "71 AAA1")["cambios_pendientes"] == 0


def test_la_misma_carga_dos_veces_no_repite_nada(client, lista):
    contenido = _a_csv(_editar(_bajar(client), "71 AAA1", Tipo="Pesado"))

    primera = _subir(client, contenido, aplicar=True).json()
    segunda = _subir(client, contenido, aplicar=True).json()

    assert primera["aplicados"] == 1 and segunda["aplicados"] == 0


def test_la_vista_previa_no_guarda_nada(client, lista):
    _subir(client, _a_csv(_editar(_bajar(client), "71 AAA1", Tipo="Pesado")))

    assert _override(lista, "71 AAA1") is None
    assert _ficha(client, "71 AAA1")["precio_final"] == 17800


def test_la_carga_recalcula_solo_lo_editado(client, lista):
    otro = lista.query(PrecioProducto).filter_by(producto="71 CCC3").one()
    antes = otro.actualizado_en

    _subir(client, _a_csv(_editar(_bajar(client), "71 AAA1", Tipo="Pesado")), aplicar=True)

    lista.expire_all()
    assert lista.query(PrecioProducto).filter_by(producto="71 CCC3").one().actualizado_en == antes


# ----------------------------------------------------------------- permisos
def test_solo_el_equipo_de_precios_puede_cargar(client, lista):
    contenido = _a_csv(_bajar(client))
    app.dependency_overrides[requiere_auth] = lambda: "noadmin@curifor.com"
    try:
        with TestClient(app) as c:
            assert _subir(c, contenido).status_code == 403
            assert _subir(c, contenido, aplicar=True).status_code == 403
    finally:
        app.dependency_overrides[requiere_auth] = lambda: "test@curifor.com"


# ----------------------------------------------------------- lectura de numeros
@pytest.mark.parametrize("texto,entero,esperado", [
    ("1,78", False, 1.78), ("1.78", False, 1.78), ("17800", True, 17800), ("17.800", True, 17800),
    ("17.800", False, 17.8), ("$ 17.800", True, 17800), ("1.234,56", False, 1234.56),
    ("1,234.56", False, 1234.56), ("17,800", True, 17800), (" 2 ", False, 2.0), ("", False, None),
    (None, False, None), (17800.0, True, 17800.0), (1.88, False, 1.88),
])
def test_leer_numero_entiende_lo_que_escribe_excel(texto, entero, esperado):
    assert carga.leer_numero(texto, entero=entero) == esperado


@pytest.mark.parametrize("texto", ["abc", "1,2,3x", "nan", "inf", True])
def test_leer_numero_rechaza_lo_que_no_es_un_numero(texto):
    with pytest.raises(ValueError):
        carga.leer_numero(texto)
