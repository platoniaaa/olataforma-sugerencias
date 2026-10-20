"""Carga desde Excel, version 2 (20-10-2026): el archivo para editar trae 25 columnas y 11 se
editan. Se suman Precio fijo, Margen fijo %, Desde y Hasta, y la Referencia pasa de 10 a 14
partes.

Lo que estos tests cuidan:

1. Que los archivos que ya se bajaron (Referencia de 10 partes, 20 columnas) sigan cargando:
   hay un archivo "dorado" generado con el codigo de ANTES (`fixtures/editable_v1.csv`).
2. Que las 16 primeras columnas sean exactamente las de "Exportar completa", y que bajar y
   subir sin tocar nada siga dando cero cambios, incluso con periodos y con codigos raros.
3. Que Precio fijo y Margen fijo % muestren la decision GUARDADA aunque no rija, mientras
   Precio final y Factor muestran lo que rige hoy.
4. Que cada regla del periodo sea la de la ficha (`validar_vigencia`) y que las fechas se
   lean como las escribe Excel en Chile: nunca mes/dia.
5. Que las ediciones nuevas pasen por los mismos frenos que las de siempre (quitar, poner
   muchas a la vez) y por el mismo conflicto con lo que otra persona hizo en la ficha.
"""
import csv
import io
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from src.models import AuditoriaLog, PrecioProducto
from src.services import calendario
from src.services import precios_carga_service as carga
from src.services import precios_service as svc

from .test_precios import _producto, lista_cargada  # noqa: F401  (fixture)
from .test_precios_carga import _a_csv, _bajar, _editar, _ficha, _override, _subir, lista  # noqa: F401
from .test_precios_vigencia import HOY, _dias, _poner, reloj  # noqa: F401  (fixture)

DORADO = Path(__file__).parent / "fixtures" / "editable_v1.csv"

COLUMNAS = [
    "Producto", "Glosa", "Rubro", "Tipo", "Procedencia", "Factor", "Costo", "Precio ERP",
    "Precio calculado", "Precio final", "Estado", "Stock", "En transito", "Ultima venta",
    "Descuento máximo", "Descuento+1",
    "Obs", "Congelar", "No es producto", "Precio fijo", "Margen fijo %", "Desde", "Hasta",
    "Vigencia", "Referencia",
]
EDITABLES = {"Tipo", "Procedencia", "Factor", "Precio final", "Obs", "Congelar", "No es producto",
             "Precio fijo", "Margen fijo %", "Desde", "Hasta"}


# ---------------------------------------------------------------- utilidades
def _iso(d: date) -> str:
    return d.isoformat()


def _dmy(d: date) -> str:
    return d.strftime("%d-%m-%Y")


def _celda(filas, producto, columna):
    """La celda de `columna` en la fila de `producto` (el codigo se compara recortado)."""
    cab = filas[0]
    for f in filas[1:]:
        if f[0].strip() == producto:
            return f[cab.index(columna)]
    raise AssertionError(f"{producto} no esta en el archivo")


def _vista(client, filas, **kw) -> dict:
    r = _subir(client, _a_csv(filas), **kw)
    assert r.status_code == 200, r.text
    return r.json()


def _cargar(client, filas, confirmar_quitas=False, confirmar_masiva=False):
    return client.post(
        "/api/precios/carga",
        data={"confirmar_quitas": str(confirmar_quitas).lower(), "confirmar_masiva": str(confirmar_masiva).lower()},
        files={"archivo": ("lista.csv", _a_csv(filas), "text/csv")})


def _errores(v) -> list[str]:
    return [e["mensaje"] for e in v["errores"]]


def _recalcular(db):
    svc.recalcular(db, refrescar_insumos=False)


def _leer_csv(contenido: bytes) -> list[list[str]]:
    return list(csv.reader(io.StringIO(contenido.decode("utf-8-sig")), delimiter=";"))


# ================================================ 1. el archivo dorado (v1)
@pytest.fixture()
def lista_dorada(client, lista):  # noqa: F811
    """El estado en que estaba la lista cuando se bajo `editable_v1.csv`: sin 13 BBB2, con un
    producto de codigo con dos espacios y 71 AAA1 editado en la ficha (tipo y nota)."""
    assert client.delete("/api/precios/13 BBB2").status_code == 200
    _producto(lista, "71  DOBLE", procedencia_maestro="NACIONAL")
    r = client.put("/api/precios/71 AAA1/override", json={"tipo_manual": "Pesado", "obs": "revisar"})
    assert r.status_code == 200, r.text
    svc.recalcular(lista)
    return lista


def _dorado() -> list[list[str]]:
    return _leer_csv(DORADO.read_bytes())


def test_el_archivo_dorado_es_de_formato_v1():
    """Lo generó el código de ANTES de este cambio: 20 columnas y Referencia de 10 partes. Si
    alguien lo regenera con el código nuevo, deja de probar la compatibilidad."""
    filas = _dorado()

    assert len(filas[0]) == 20 and filas[0][-4:] == ["Obs", "Congelar", "No es producto", "Referencia"]
    assert "Precio fijo" not in filas[0] and "Desde" not in filas[0]
    assert [len(f[-1].split("|")) for f in filas[1:]] == [10, 10, 10]
    assert [f[0] for f in filas[1:]] == ["71  DOBLE", "71 AAA1", "71 CCC3"]


def test_subir_el_archivo_dorado_sin_tocarlo_no_cambia_nada(client, lista_dorada):
    r = _subir(client, DORADO.read_bytes())

    assert r.status_code == 200, r.text
    v = r.json()
    assert (v["filas"], v["a_cambiar"], v["sin_cambios"]) == (3, 0, 3)
    assert v["errores_total"] == v["conflictos_total"] == v["desconocidos_total"] == 0
    assert v["sin_referencia_total"] == 0
    assert v["archivo_viejo_total"] == 3                  # son tres filas de formato anterior


def test_el_archivo_dorado_editado_en_tipo_y_precio_final_se_aplica(client, lista_dorada):
    filas = _editar(_dorado(), "71  DOBLE", Tipo="Pesado", Precio_final="2500")

    previa = _vista(client, filas)
    r = _subir(client, _a_csv(filas), aplicar=True)

    assert previa["a_cambiar"] == 1 and previa["errores_total"] == 0
    assert previa["por_campo"] == {"tipo": 1, "precio_fijo": 1}
    assert r.status_code == 200 and r.json()["aplicados"] == 1
    o = _override(lista_dorada, "71  DOBLE")
    assert (o.tipo_manual, o.precio_fijo) == ("Pesado", 2500)
    ficha = _ficha(client, "71  DOBLE")
    assert (ficha["precio_final"], ficha["estado"]) == (2500, "FIJO")


def test_el_archivo_dorado_con_el_producto_cambiado_en_la_ficha_es_un_conflicto(client, lista_dorada):
    client.put("/api/precios/71 AAA1/override", json={"obs": "otra persona"})
    filas = _editar(_dorado(), "71 AAA1", Tipo="Liviano")

    v = _vista(client, filas)

    assert v["conflictos_total"] == 1 and v["a_cambiar"] == 0 and v["errores_total"] == 0


def test_una_fila_v1_dentro_de_un_archivo_con_columnas_nuevas_ignora_las_nuevas(client, lista):
    """La Referencia de 10 partes dice que ese archivo no conocia el periodo: lo que haya en
    Precio fijo, Margen fijo %, Desde y Hasta de esa fila no se lee (y se cuenta)."""
    filas = _bajar(client)
    for f in filas[1:]:
        if f[0] == "71 AAA1":
            partes = f[-1].split("|")
            f[-1] = "|".join(partes[:9] + partes[-1:])               # la Referencia v1 de esa fila
    filas = _editar(filas, "71 AAA1", **{"Precio fijo": "990", "Margen fijo %": "", "Desde": _iso(HOY),
                                         "Hasta": _iso(_dias(10)), "Tipo": "Pesado"})

    v = _vista(client, filas)

    assert v["a_cambiar"] == 1 and v["archivo_viejo_total"] == 1
    (c,) = v["cambios"]
    assert [x["campo"] for x in c["campos"]] == ["Tipo"]                # lo de las 7 de siempre
    r = _subir(client, _a_csv(filas), aplicar=True)
    o = _override(lista, "71 AAA1")
    assert r.status_code == 200 and (o.tipo_manual, o.precio_fijo, o.vigente_hasta) == ("Pesado", None, None)


def test_un_archivo_v2_no_cuenta_filas_de_formato_viejo(client, lista):
    assert _vista(client, _bajar(client))["archivo_viejo_total"] == 0


@pytest.mark.parametrize("columnas,dicen", [
    (["Hasta"], "Faltan las columnas: Hasta."),
    (["Precio fijo", "Margen fijo %"], "Faltan las columnas: Precio fijo, Margen fijo %."),
    (["Precio fijo", "Margen fijo %", "Desde", "Hasta"], "Faltan las columnas: Precio fijo, Margen fijo %, Desde, Hasta."),
])
def test_si_la_referencia_es_v2_y_faltan_las_columnas_nuevas_es_un_error_global(client, lista, columnas, dicen):
    """Sin esas columnas no se sabe que mostraba el archivo, y se las tomaria por vacias: o
    sea, por quitas de todas las decisiones."""
    filas = _bajar(client)
    fuera = {filas[0].index(c) for c in columnas}
    sin = [[c for j, c in enumerate(f) if j not in fuera] for f in filas]

    r = _subir(client, _a_csv(sin))

    assert r.status_code == 422 and dicen in r.json()["detail"]
    assert "Descargar para editar" in r.json()["detail"]


@pytest.mark.parametrize("n", [1, 9, 11, 12, 13, 15])
def test_una_referencia_de_otro_largo_esta_danada(client, lista, n):
    """Solo valen 10 (v1) y 14 (v2)."""
    filas = _bajar(client)
    assert filas[0][-1] == "Referencia"
    for f in filas[1:]:
        if f[0] == "71 AAA1":
            partes = f[-1].split("|")
            f[-1] = "|".join((partes + ["x"] * 5)[:n]) if n > 1 else "sinseparadores"

    v = _vista(client, filas)

    assert v["errores_total"] == 1 and "Referencia está dañada" in v["errores"][0]["mensaje"]
    assert v["errores"][0]["producto"] == "71 AAA1"


# ============================================================= 2. las columnas
def test_el_archivo_para_editar_trae_las_25_columnas_en_el_orden_acordado(client, lista):
    filas = _bajar(client)
    cab = filas[0]

    assert cab == COLUMNAS
    assert cab == carga.CABECERA_ARCHIVO and len(cab) == 25
    assert {len(f) for f in filas} == {25}                      # cada fila trae sus 25 celdas


def test_hay_once_columnas_editables_y_trece_de_solo_lectura(client, lista):
    assert set(carga.COLUMNAS_EDITABLES) == EDITABLES and len(carga.COLUMNAS_EDITABLES) == 11
    assert len(carga.COLUMNAS_SOLO_LECTURA) == 13
    assert set(carga.COLUMNAS_SOLO_LECTURA) == set(COLUMNAS) - EDITABLES - {"Referencia"}
    assert "Vigencia" in carga.COLUMNAS_SOLO_LECTURA and "Referencia" not in carga.COLUMNAS_SOLO_LECTURA


def test_las_primeras_16_columnas_son_las_de_exportar_completa_celda_a_celda(client, lista):
    """Es el pedido: el archivo para editar parte de la misma lista que "Exportar completa". Hoy
    son dos listas de columnas en dos archivos distintos, y este test las ata."""
    p = lista.query(PrecioProducto).filter_by(producto="71 AAA1").one()
    p.codigo_erp = "71 AAA1 "                                   # el ERP lo tiene con espacio al final
    lista.commit()
    completa = _leer_csv(client.get("/api/precios/exportar", params={"formato": "completa"}).content)
    editable = _bajar(client)

    assert [f[:16] for f in editable] == completa
    assert completa[0] == COLUMNAS[:16] == [t for t, _ in carga.COLUMNAS_ARCHIVO[:16]]
    assert any(f[0] == "71 AAA1 " for f in completa[1:])


def test_la_lista_completa_sigue_con_sus_16_columnas(client, lista):
    cab = _leer_csv(client.get("/api/precios/exportar", params={"formato": "completa"}).content)[0]

    assert cab == COLUMNAS[:16]


def test_precio_fijo_y_margen_fijo_muestran_la_decision_guardada_aunque_no_rija(client, lista, reloj):
    # programada: el precio fijo empieza en 5 dias
    _poner(lista, "71 AAA1", precio_fijo=990.0, vigente_desde=_dias(5), vigente_hasta=_dias(20))
    # vencida: el periodo termino ayer
    _poner(lista, "13 BBB2", vigente_desde=_dias(-20), vigente_hasta=_dias(-1))
    # margen vigente
    _poner(lista, "71 CCC3", congelar=False, congelado_precio=None, margen_fijo=35.0, vigente_hasta=_dias(5))
    _recalcular(lista)

    filas = _bajar(client)

    prog = {c: _celda(filas, "71 AAA1", c) for c in ("Precio final", "Precio fijo", "Estado", "Desde", "Hasta")}
    assert prog == {"Precio final": "17800", "Precio fijo": "990", "Estado": "OK",
                    "Desde": _iso(_dias(5)), "Hasta": _iso(_dias(20))}      # Precio final = la regla
    assert (_celda(filas, "13 BBB2", "Precio fijo"), _celda(filas, "13 BBB2", "Hasta")) == ("990", _iso(_dias(-1)))
    assert _celda(filas, "13 BBB2", "Estado") == "SIN STOCK"
    marg = {c: _celda(filas, "71 CCC3", c) for c in ("Factor", "Precio final", "Margen fijo %", "Estado")}
    assert marg == {"Factor": "1,5385", "Precio final": "1539", "Margen fijo %": "35", "Estado": "MARGEN"}


def test_sin_decision_no_hay_nada_en_las_columnas_nuevas(client, lista):
    filas = _bajar(client)

    assert [_celda(filas, "71 AAA1", c) for c in ("Precio fijo", "Margen fijo %", "Desde", "Hasta", "Vigencia")] == [""] * 5


def test_el_margen_se_baja_con_coma_y_hasta_2_decimales(client, lista):
    _poner(lista, "71 AAA1", margen_fijo=33.33333333)
    _poner(lista, "71 CCC3", congelar=False, congelado_precio=None, margen_fijo=35.5)
    _recalcular(lista)

    filas = _bajar(client)

    assert _celda(filas, "71 AAA1", "Margen fijo %") == "33,33"
    assert _celda(filas, "71 CCC3", "Margen fijo %") == "35,5"


def test_la_columna_vigencia_dice_fijo_hasta_programado_desde_y_vencido_el(client, lista, reloj):
    _poner(lista, "71 AAA1", precio_fijo=990.0, vigente_desde=_dias(-1), vigente_hasta=_dias(11))
    _poner(lista, "13 BBB2", vigente_desde=_dias(-20), vigente_hasta=_dias(-1))
    _poner(lista, "71 CCC3", vigente_desde=_dias(3), vigente_hasta=_dias(10))          # congelado y programado
    _recalcular(lista)

    filas = _bajar(client)

    assert _celda(filas, "71 AAA1", "Vigencia") == "Fijo hasta 31-10-2026"
    assert _celda(filas, "13 BBB2", "Vigencia") == "Vencido el 19-10-2026"
    assert _celda(filas, "71 CCC3", "Vigencia") == "Programado desde 23-10-2026"


def test_vigente_sin_hasta_no_dice_nada_en_vigencia(client, lista, reloj):
    _poner(lista, "71 AAA1", precio_fijo=990.0, vigente_desde=_dias(-1))
    _recalcular(lista)

    filas = _bajar(client)

    assert _celda(filas, "71 AAA1", "Desde") == _iso(_dias(-1)) and _celda(filas, "71 AAA1", "Vigencia") == ""


def test_bajar_y_subir_sin_tocar_nada_da_cero_cambios_con_periodos_y_codigos_raros(client, lista, reloj):
    """Lo mas importante del cambio: el archivo recien bajado nunca se ve como editado."""
    _producto(lista, "71  DOBLE", procedencia_maestro="NACIONAL")                # doble espacio adentro
    p = lista.query(PrecioProducto).filter_by(producto="71 AAA1").one()
    p.codigo_erp = "71 AAA1 "                                                    # espacio al final
    lista.commit()
    _poner(lista, "71 AAA1", precio_fijo=990.0, vigente_desde=_dias(-1), vigente_hasta=_dias(5))
    _poner(lista, "13 BBB2", vigente_desde=_dias(-20), vigente_hasta=_dias(-1))   # vencido
    _poner(lista, "71 CCC3", vigente_desde=_dias(3), vigente_hasta=_dias(10))     # congelado y programado
    _poner(lista, "71  DOBLE", margen_fijo=33.33333333, vigente_hasta=_dias(5))
    _recalcular(lista)
    filas = _bajar(client)

    v = _vista(client, filas)

    assert v["filas"] == 4 and v["a_cambiar"] == 0 and v["sin_cambios"] == 4
    assert v["errores_total"] == v["conflictos_total"] == v["desconocidos_total"] == 0
    assert v["archivo_viejo_total"] == 0 and v["programados_total"] == 0
    assert _subir(client, _a_csv(filas), aplicar=True).json()["aplicados"] == 0


def test_la_referencia_v2_lleva_la_decision_guardada(client, lista, reloj):
    _poner(lista, "71 AAA1", precio_fijo=990.0, vigente_desde=_dias(5), vigente_hasta=_dias(20))
    _poner(lista, "71 CCC3", congelar=False, congelado_precio=None, margen_fijo=35.0)
    _recalcular(lista)

    filas = _bajar(client)

    aaa = _celda(filas, "71 AAA1", "Referencia").split("|")
    assert len(aaa) == 14 and aaa[9:13] == ["990", "", _iso(_dias(5)), _iso(_dias(20))]
    assert _celda(filas, "71 CCC3", "Referencia").split("|")[9:13] == ["", "35", "", ""]


# ====================================================== 3. editar el periodo
def test_poner_un_precio_fijo_con_su_periodo_desde_el_archivo(client, lista, reloj):
    filas = _editar(_bajar(client), "71 AAA1", **{"Precio fijo": "990", "Desde": _iso(HOY), "Hasta": _iso(_dias(10))})

    v = _vista(client, filas)
    r = _subir(client, _a_csv(filas), aplicar=True)

    assert v["a_cambiar"] == 1 and v["errores_total"] == 0
    (c,) = v["cambios"]
    assert [x["campo"] for x in c["campos"]] == ["Precio fijo", "Desde", "Hasta"]
    assert c["vigencia"] == "Rige del 20-10-2026 al 30-10-2026"
    assert (c["precio_antes"], c["precio_despues"]) == (17800, 990)
    assert v["por_campo"] == {"precio_fijo": 1, "desde": 1, "hasta": 1}
    assert v["fijan"] == {"precio_fijo": 1, "desde": 1, "hasta": 1} and v["fijan_total"] == 3
    assert v["quitan_total"] == 0 and v["programados_total"] == 0
    assert r.status_code == 200 and r.json()["aplicados"] == 1
    o = _override(lista, "71 AAA1")
    assert (o.precio_fijo, o.vigente_desde, o.vigente_hasta) == (990, HOY, _dias(10))
    ficha = _ficha(client, "71 AAA1")
    assert (ficha["precio_final"], ficha["estado"], ficha["vigencia"]) == (990, "FIJO", "vigente")
    assert ficha["precio_final"] == c["precio_despues"]            # lo que dijo la vista previa
    detalle = lista.query(AuditoriaLog).filter_by(accion="precio_override", producto="71 AAA1").one().detalle
    assert "periodo sin periodo -> 20-10-2026 a 30-10-2026" in detalle and "(carga desde Excel)" in detalle


def test_un_precio_con_desde_futuro_no_cambia_hoy_y_se_cuenta_como_programado(client, lista, reloj):
    filas = _editar(_bajar(client), "71 AAA1", **{"Precio fijo": "990", "Desde": _iso(_dias(5))})

    v = _vista(client, filas)

    assert v["programados_total"] == 1 and v["a_cambiar"] == 1
    assert v["efecto"] == {"suben": 0, "bajan": 0, "sin_cambio_de_precio": 1, "con_precio_nuevo": 0}
    assert v["cambios"][0]["vigencia"] == "Rige desde el 25-10-2026"
    _subir(client, _a_csv(filas), aplicar=True)
    assert _ficha(client, "71 AAA1")["precio_final"] == 17800 and _ficha(client, "71 AAA1")["vigencia"] == "programada"


def test_un_producto_que_ya_estaba_programado_y_solo_cambia_la_nota_no_cuenta_como_programado(client, lista, reloj):
    _poner(lista, "71 AAA1", precio_fijo=990.0, vigente_desde=_dias(5))
    _recalcular(lista)

    v = _vista(client, _editar(_bajar(client), "71 AAA1", Obs="nota nueva"))

    assert v["a_cambiar"] == 1 and v["programados_total"] == 0


def test_renovar_un_vencido_es_cambiar_solo_el_hasta(client, lista, reloj):
    _poner(lista, "13 BBB2", vigente_desde=_dias(-20), vigente_hasta=_dias(-1))
    _recalcular(lista)
    filas = _bajar(client)
    assert _celda(filas, "13 BBB2", "Vigencia") == "Vencido el 19-10-2026"

    filas = _editar(filas, "13 BBB2", Hasta=_iso(_dias(30)))
    v = _vista(client, filas)
    r = _subir(client, _a_csv(filas), aplicar=True)

    assert v["a_cambiar"] == 1 and v["errores_total"] == 0
    assert v["cambios"][0]["campos"] == [{"campo": "Hasta", "antes": "19-10-2026", "despues": "19-11-2026"}]
    assert r.status_code == 200 and r.json()["por_campo"] == {"hasta": 1}
    o = _override(lista, "13 BBB2")
    assert (o.precio_fijo, o.vigente_hasta) == (990, _dias(30))
    ficha = _ficha(client, "13 BBB2")
    assert (ficha["precio_final"], ficha["estado"], ficha["vigencia"]) == (990, "FIJO", "vigente")


def test_vaciar_el_hasta_cuenta_como_quita_y_pide_confirmacion(client, lista, reloj, monkeypatch):
    """Vuelve permanente un precio temporal: un BUSCARV roto que vacie la columna no puede
    hacerlo en silencio."""
    _poner(lista, "71 AAA1", precio_fijo=990.0, vigente_desde=_dias(-1), vigente_hasta=_dias(5))
    _recalcular(lista)
    monkeypatch.setattr(carga, "UMBRAL_QUITAS", 1)
    filas = _editar(_bajar(client), "71 AAA1", Hasta="")

    v = _vista(client, filas)
    sin = _cargar(client, filas)
    con = _cargar(client, filas, confirmar_quitas=True)

    assert v["quitan"] == {"hasta": 1} and v["quitan_total"] == 1
    assert v["cambios"][0]["campos"] == [{"campo": "Hasta", "antes": "25-10-2026", "despues": "(sin vencimiento)"}]
    assert sin.status_code == 422 and "quita 1 decisiones" in sin.json()["detail"]
    assert con.status_code == 200
    o = _override(lista, "71 AAA1")
    assert (o.precio_fijo, o.vigente_desde, o.vigente_hasta) == (990, _dias(-1), None)


def test_vaciar_el_desde_tambien_cuenta_como_quita(client, lista, reloj):
    _poner(lista, "71 AAA1", precio_fijo=990.0, vigente_desde=_dias(-3))
    _recalcular(lista)

    v = _vista(client, _editar(_bajar(client), "71 AAA1", Desde=""))

    assert v["quitan"] == {"desde": 1}
    assert v["cambios"][0]["campos"] == [{"campo": "Desde", "antes": "17-10-2026", "despues": "(sin Desde)"}]


def test_desde_posterior_al_hasta_es_un_error_que_bloquea_todo(client, lista, reloj):
    filas = _editar(_bajar(client), "71 AAA1", **{"Precio fijo": "990", "Desde": _iso(_dias(10)), "Hasta": _iso(_dias(5))})

    v = _vista(client, filas)
    r = _subir(client, _a_csv(filas), aplicar=True)

    assert v["errores_total"] == 1 and _errores(v) == ["El Desde no puede ser posterior al Hasta."]
    assert r.status_code == 422 and "1 error" in r.json()["detail"]
    assert _override(lista, "71 AAA1") is None


def test_un_hasta_que_ya_paso_es_un_error(client, lista, reloj):
    filas = _editar(_bajar(client), "71 AAA1", **{"Precio fijo": "990", "Hasta": _iso(_dias(-1))})

    v = _vista(client, filas)

    assert v["errores_total"] == 1 and "El periodo ya terminó (Hasta 19-10-2026)" in _errores(v)[0]


def test_fechas_sin_ninguna_decision_son_un_error(client, lista, reloj):
    v = _vista(client, _editar(_bajar(client), "71 AAA1", Desde=_iso(_dias(1))))

    assert _errores(v) == ["El periodo aplica a precio fijo, margen fijo o congelar: define uno."]


@pytest.mark.parametrize("columna", ["Precio fijo", "Precio final"])
def test_quitar_la_ultima_decision_limpia_las_fechas(client, lista, reloj, columna):
    _poner(lista, "71 AAA1", precio_fijo=990.0, vigente_desde=_dias(-1), vigente_hasta=_dias(5))
    _recalcular(lista)

    r = _subir(client, _a_csv(_editar(_bajar(client), "71 AAA1", **{columna: ""})), aplicar=True)

    assert r.status_code == 200 and r.json()["por_campo"] == {"precio_fijo": 1}
    o = _override(lista, "71 AAA1")
    assert (o.precio_fijo, o.vigente_desde, o.vigente_hasta) == (None, None, None)
    ficha = _ficha(client, "71 AAA1")
    assert (ficha["precio_final"], ficha["vigencia"]) == (17800, None)


def test_congelar_con_un_desde_futuro_es_un_error(client, lista, reloj):
    v = _vista(client, _editar(_bajar(client), "71 AAA1", Congelar="Sí", Desde=_iso(_dias(3))))

    assert _errores(v) == ["Congelar toma el precio de hoy: no se puede programar con un Desde futuro (usa precio fijo)."]


def test_congelar_con_hasta_congela_el_precio_de_hoy_hasta_esa_fecha(client, lista, reloj):
    filas = _editar(_bajar(client), "71 AAA1", Congelar="Sí", Hasta=_iso(_dias(10)))

    v = _vista(client, filas)
    r = _subir(client, _a_csv(filas), aplicar=True)

    assert v["fijan"] == {"congelar": 1, "hasta": 1}
    assert r.status_code == 200
    o = _override(lista, "71 AAA1")
    assert (o.congelar, o.congelado_precio, o.vigente_hasta) == (True, 17800, _dias(10))
    assert _ficha(client, "71 AAA1")["estado"] == "CONGELADO"


def test_renovar_un_congelado_vencido_toma_el_precio_de_hoy_y_no_el_de_la_fila(client, lista, reloj):
    """La fila puede seguir mostrando el precio de la decision vencida hasta el proximo
    recalculo: el congelado nuevo toma el que da la regla (igual que en la ficha)."""
    _poner(lista, "71 CCC3", vigente_desde=_dias(-20), vigente_hasta=_dias(-1), congelado_precio=5000.0)
    _recalcular(lista)
    filas = _editar(_bajar(client), "71 CCC3", Hasta=_iso(_dias(30)))
    p = lista.query(PrecioProducto).filter_by(producto="71 CCC3").one()
    p.precio_final = 5000.0                                    # una fila que quedo atrasada
    lista.commit()

    r = _subir(client, _a_csv(filas), aplicar=True)

    assert r.status_code == 200 and r.json()["aplicados"] == 1
    assert _override(lista, "71 CCC3").congelado_precio == 2160


def test_editar_solo_la_nota_de_un_vencido_se_guarda(client, lista, reloj):
    """Como en la ficha: lo unico que cambia es la nota, el periodo no se toca."""
    _poner(lista, "13 BBB2", vigente_desde=_dias(-20), vigente_hasta=_dias(-1))
    _recalcular(lista)

    v = _vista(client, _editar(_bajar(client), "13 BBB2", Obs="sigue la nota"))

    assert v["a_cambiar"] == 1 and v["errores_total"] == 0 and v["conflictos_total"] == 0


def test_cambiar_el_precio_de_un_vencido_sin_renovar_el_periodo_es_un_error(client, lista, reloj):
    """El producto muestra la regla (Precio final = 0 hoy); escribir ahi un precio lo dejaria
    guardado y sin regir. Dice que hay que renovar el periodo."""
    _poner(lista, "13 BBB2", vigente_desde=_dias(-20), vigente_hasta=_dias(-1))
    _recalcular(lista)

    v = _vista(client, _editar(_bajar(client), "13 BBB2", **{"Precio fijo": "1200"}))

    assert v["errores_total"] == 1 and "El periodo ya terminó (Hasta 19-10-2026)" in _errores(v)[0]


# =============================================== 4. margen fijo y precio fijo
def test_el_margen_fijo_se_carga_en_su_columna(client, lista):
    filas = _editar(_bajar(client), "71 AAA1", **{"Margen fijo %": "35"})

    v = _vista(client, filas)
    r = _subir(client, _a_csv(filas), aplicar=True)

    assert v["a_cambiar"] == 1 and v["por_campo"] == {"factor": 1}
    assert v["cambios"][0]["campos"] == [
        {"campo": "Factor", "antes": "(el de la política: 1,78)", "despues": "1,5385"}]
    assert r.status_code == 200
    assert _override(lista, "71 AAA1").margen_fijo == 35
    ficha = _ficha(client, "71 AAA1")
    assert (ficha["factor"], ficha["precio_final"], ficha["estado"]) == (1.5385, 15385, "MARGEN")


def test_factor_y_margen_que_dicen_lo_mismo_se_aplican_una_sola_vez(client, lista):
    filas = _editar(_bajar(client), "71 AAA1", Factor="1,5385", **{"Margen fijo %": "35"})

    v = _vista(client, filas)
    r = _subir(client, _a_csv(filas), aplicar=True)

    assert v["a_cambiar"] == 1 and v["errores_total"] == 0
    assert v["por_campo"] == {"factor": 1} and v["fijan"] == {"factor": 1}
    assert r.status_code == 200 and r.json()["por_campo"] == {"factor": 1}
    assert _override(lista, "71 AAA1").margen_fijo == 35


def test_factor_y_margen_que_discrepan_son_un_error(client, lista):
    v = _vista(client, _editar(_bajar(client), "71 AAA1", Factor="1,5", **{"Margen fijo %": "35"}))

    assert v["errores_total"] == 1
    assert "Factor (1,5) y Margen fijo % (35) no dicen lo mismo" in _errores(v)[0]
    assert "factor de 1,5385" in _errores(v)[0]


def test_un_factor_y_un_margen_vacios_a_la_vez_quitan_el_margen_una_vez(client, lista):
    client.put("/api/precios/71 AAA1/override", json={"margen_fijo": 35})
    filas = _editar(_bajar(client), "71 AAA1", Factor="", **{"Margen fijo %": ""})

    v = _vista(client, filas)

    assert v["quitan"] == {"factor": 1} and v["a_cambiar"] == 1 and v["errores_total"] == 0


def test_un_factor_vacio_y_un_margen_con_valor_discrepan(client, lista):
    client.put("/api/precios/71 AAA1/override", json={"margen_fijo": 35})

    v = _vista(client, _editar(_bajar(client), "71 AAA1", Factor="", **{"Margen fijo %": "40"}))

    assert "uno quedó vacío y el otro no" in _errores(v)[0]


@pytest.mark.parametrize("margen,dice", [
    ("0,35", "Escribe 35 para un margen de 35 %, no 0,35"),
    ("0", "tiene que ser 1 o más"),
    ("-5", "tiene que ser 1 o más"),
    ("100", "tiene que ser menor que 100"),
    ("150", "tiene que ser menor que 100"),
])
def test_un_margen_fuera_de_rango_es_un_error_y_el_de_0_35_explica_el_porcentaje(client, lista, margen, dice):
    v = _vista(client, _editar(_bajar(client), "71 AAA1", **{"Margen fijo %": margen}))

    assert v["errores_total"] == 1 and dice in _errores(v)[0] and _errores(v)[0].startswith("Margen fijo %")


def test_un_margen_con_decimales_se_guarda_con_2_y_baja_y_sube_sin_cambios(client, lista):
    _subir(client, _a_csv(_editar(_bajar(client), "71 AAA1", **{"Margen fijo %": "33,33"})), aplicar=True)

    filas = _bajar(client)

    assert _override(lista, "71 AAA1").margen_fijo == 33.33
    assert _celda(filas, "71 AAA1", "Margen fijo %") == "33,33"
    assert _vista(client, filas)["a_cambiar"] == 0


def test_el_atajo_del_factor_sigue_dando_un_margen_y_la_columna_nueva_lo_muestra(client, lista):
    _subir(client, _a_csv(_editar(_bajar(client), "71 AAA1", Factor="2")), aplicar=True)

    filas = _bajar(client)

    assert (_celda(filas, "71 AAA1", "Factor"), _celda(filas, "71 AAA1", "Margen fijo %")) == ("2", "50")
    assert _vista(client, filas)["a_cambiar"] == 0


def test_un_margen_fijo_puede_traer_su_periodo(client, lista, reloj):
    filas = _editar(_bajar(client), "71 AAA1", **{"Margen fijo %": "35", "Hasta": _iso(_dias(10))})

    v = _vista(client, filas)

    assert v["errores_total"] == 0 and v["cambios"][0]["vigencia"] == "Rige hasta el 30-10-2026"
    assert (v["cambios"][0]["precio_antes"], v["cambios"][0]["precio_despues"]) == (17800, 15385)


def test_precio_final_y_precio_fijo_que_discrepan_son_un_error(client, lista):
    v = _vista(client, _editar(_bajar(client), "71 AAA1", Precio_final="1000", **{"Precio fijo": "2000"}))

    assert v["errores_total"] == 1
    assert "Precio final (1.000) y Precio fijo (2.000) no dicen lo mismo" in _errores(v)[0]


def test_precio_final_y_precio_fijo_iguales_se_aplican_una_sola_vez(client, lista):
    filas = _editar(_bajar(client), "71 AAA1", Precio_final="1500", **{"Precio fijo": "1.500"})

    v = _vista(client, filas)

    assert v["errores_total"] == 0 and v["por_campo"] == {"precio_fijo": 1} and v["fijan_total"] == 1


def test_el_atajo_de_precio_final_solo_sigue_fijando_el_precio(client, lista):
    _subir(client, _a_csv(_editar(_bajar(client), "71 AAA1", Precio_final="1500")), aplicar=True)

    filas = _bajar(client)

    assert _override(lista, "71 AAA1").precio_fijo == 1500
    assert (_celda(filas, "71 AAA1", "Precio fijo"), _celda(filas, "71 AAA1", "Precio final")) == ("1500", "1500")


def test_un_precio_fijo_negativo_es_un_error(client, lista):
    v = _vista(client, _editar(_bajar(client), "71 AAA1", **{"Precio fijo": "-5"}))

    assert _errores(v) == ["Precio fijo: no puede ser negativo."]


def test_precio_fijo_y_margen_a_la_vez_es_un_error_de_combinacion(client, lista):
    v = _vista(client, _editar(_bajar(client), "71 AAA1", **{"Precio fijo": "990", "Margen fijo %": "35"}))

    assert v["errores_total"] == 1 and "precio fijo y factor propio" in _errores(v)[0]


def test_el_estorbo_vencido_se_nombra_en_el_error_de_combinacion(client, lista, reloj):
    """Quien sube el archivo no ve el margen vencido rigiendo: el mensaje dice que existe."""
    _poner(lista, "71 AAA1", margen_fijo=35.0, vigente_desde=_dias(-20), vigente_hasta=_dias(-1))
    _recalcular(lista)

    v = _vista(client, _editar(_bajar(client), "71 AAA1", **{"Precio fijo": "990", "Hasta": _iso(_dias(30))}))

    assert v["errores_total"] == 1
    assert "(el margen fijo guardado está vencido: bórralo o renuévalo)" in _errores(v)[0]


# ============================================== 5. las fechas, como las escribe Excel
@pytest.mark.parametrize("valor,esperado", [
    ("2026-10-31", date(2026, 10, 31)),
    ("31-10-2026", date(2026, 10, 31)),
    ("31/10/2026", date(2026, 10, 31)),
    ("1-2-2026", date(2026, 2, 1)),
    ("31-10-26", date(2026, 10, 31)),
    ("31/10/26", date(2026, 10, 31)),
    (" 31-10-2026 ", date(2026, 10, 31)),
    ("2026-10-31 13:05:00", date(2026, 10, 31)),
    (date(2026, 10, 31), date(2026, 10, 31)),
    (datetime(2026, 10, 31, 13, 5), date(2026, 10, 31)),
    (46326, date(2026, 10, 31)),                    # el numero de serie de Excel
    (46326.0, date(2026, 10, 31)),
    (46326.5, date(2026, 10, 31)),
    ("46326", date(2026, 10, 31)),
    ("", None),
    (None, None),
    ("   ", None),
    ("13/10/2026", date(2026, 10, 13)),             # dia/mes: 13 de octubre
    ("10/11/2026", date(2026, 11, 10)),             # NUNCA mes/dia: es el 10 de noviembre
])
def test_formatos_de_fecha_que_se_leen(valor, esperado):
    assert carga._leer_fecha(valor) == esperado


@pytest.mark.parametrize("valor", [
    "31-oct", "31-oct-2026", "31 de octubre", "hoy", "31-02-2026", "2026-13-01", "2026-02-30",
    "10/13/2026",                                   # mes/dia: no existe el mes 13
    "31.10.2026", "20261031", 20261031, 12345, True, "1e3", "31/12", "2026",
])
def test_formatos_de_fecha_que_no_se_adivinan(valor):
    with pytest.raises(ValueError, match="usa dd-mm-aaaa"):
        carga._leer_fecha(valor)


@pytest.mark.parametrize("texto", ["2026-10-31", "31-10-2026", "31/10/2026", "31-10-26", "46326"])
def test_el_hasta_se_lee_igual_en_cualquiera_de_los_formatos_del_csv(client, lista, reloj, texto):
    filas = _editar(_bajar(client), "71 AAA1", **{"Precio fijo": "990", "Hasta": texto})

    v = _vista(client, filas)

    assert v["errores_total"] == 0 and v["cambios"][0]["vigencia"] == "Rige hasta el 31-10-2026"


@pytest.mark.parametrize("texto,mensaje", [
    ("31-oct", 'Hasta: no entiendo "31-oct" como fecha: usa dd-mm-aaaa (por ejemplo 31-10-2026).'),
    ("31-02-2026", 'Hasta: no entiendo "31-02-2026" como fecha: usa dd-mm-aaaa (por ejemplo 31-10-2026).'),
])
def test_una_fecha_que_no_se_entiende_es_un_error_con_su_columna(client, lista, reloj, texto, mensaje):
    v = _vista(client, _editar(_bajar(client), "71 AAA1", **{"Precio fijo": "990", "Hasta": texto}))

    assert _errores(v) == [mensaje]


def test_un_xlsx_con_celdas_de_fecha_de_verdad(client, lista, reloj):
    """En un .xlsx Excel guarda las fechas como fecha (o como numero de serie): calamine las
    entrega como date, datetime o numero."""
    from openpyxl import Workbook

    filas = _bajar(client)
    cab = filas[0]
    wb = Workbook()
    ws = wb.active
    ws.append(cab)
    for f in filas[1:]:
        fila = list(f)
        if f[0] == "71 AAA1":
            fila[cab.index("Precio fijo")] = 990
            fila[cab.index("Desde")] = date(2026, 10, 20)
            fila[cab.index("Hasta")] = datetime(2026, 10, 31, 0, 0)
        elif f[0] == "13 BBB2":
            fila[cab.index("Hasta")] = 46326                     # numero de serie
        ws.append(fila)
    buf = io.BytesIO()
    wb.save(buf)

    v = _subir(client, buf.getvalue(), nombre="lista.xlsx").json()

    assert v["errores_total"] == 0 and v["a_cambiar"] == 2
    por = {c["producto"]: c["vigencia"] for c in v["cambios"]}
    assert por == {"71 AAA1": "Rige del 20-10-2026 al 31-10-2026", "13 BBB2": "Rige hasta el 31-10-2026"}


def test_hoy_es_el_de_chile_a_las_2330_aunque_en_utc_ya_sea_manana(client, lista, monkeypatch):
    """31-10 23:30 en Chile ya es 1 de noviembre en UTC: un Hasta de hoy todavia vale."""
    noche = datetime(2026, 11, 1, 2, 30, tzinfo=timezone.utc).astimezone(calendario.TZ_CHILE)
    assert noche.date() == date(2026, 10, 31)
    monkeypatch.setattr(calendario, "ahora_chile", lambda: noche)
    filas = _editar(_bajar(client), "71 AAA1", **{"Precio fijo": "990", "Hasta": "31-10-2026"})

    antes = _vista(client, filas)
    manana = datetime(2026, 11, 1, 3, 1, tzinfo=timezone.utc).astimezone(calendario.TZ_CHILE)   # 00:01 en Chile
    monkeypatch.setattr(calendario, "ahora_chile", lambda: manana)
    despues = _vista(client, filas)

    assert antes["errores_total"] == 0 and antes["cambios"][0]["vigencia"] == "Rige hasta el 31-10-2026"
    assert despues["errores_total"] == 1 and "El periodo ya terminó (Hasta 31-10-2026)" in _errores(despues)[0]


# ============================================ 6. conflictos y frenos
def test_si_la_ficha_cambio_solo_las_fechas_despues_de_bajar_el_archivo_es_un_conflicto(client, lista, reloj):
    client.put("/api/precios/71 AAA1/override", json={"precio_fijo": 990, "vigente_hasta": _iso(_dias(5))})
    filas = _bajar(client)
    client.put("/api/precios/71 AAA1/override", json={"vigente_hasta": _iso(_dias(30))})   # otra persona

    v = _vista(client, _editar(filas, "71 AAA1", Hasta=_iso(_dias(10))))

    assert v["conflictos_total"] == 1 and v["a_cambiar"] == 0 and v["errores_total"] == 0


def test_el_mismo_cambio_de_fechas_sin_que_nadie_toque_la_ficha_se_aplica(client, lista, reloj):
    client.put("/api/precios/71 AAA1/override", json={"precio_fijo": 990, "vigente_hasta": _iso(_dias(5))})

    v = _vista(client, _editar(_bajar(client), "71 AAA1", Hasta=_iso(_dias(10))))

    assert v["conflictos_total"] == 0 and v["a_cambiar"] == 1


def test_el_periodo_vencido_por_otra_persona_se_ve_como_conflicto_y_no_como_error(client, lista, reloj):
    """El archivo edita el precio fijo, y despues de bajarlo otra persona dejo el periodo ya
    vencido: ese error viene de lo guardado y no del archivo, asi que solo se omite esa fila."""
    client.put("/api/precios/71 AAA1/override", json={"precio_fijo": 990, "vigente_hasta": _iso(_dias(5))})
    filas = _bajar(client)
    _poner(lista, "71 AAA1", vigente_hasta=_dias(-1))                        # la otra persona lo dejo vencido

    v = _vista(client, _editar(filas, "71 AAA1", **{"Precio fijo": "1200"}))

    assert v["conflictos_total"] == 1 and v["errores_total"] == 0


def test_ordenar_solo_la_columna_congelar_dispara_la_confirmacion_masiva(client, lista, monkeypatch):
    """Antes no la disparaba: UMBRAL_MASIVA contaba solo precios fijos y factores."""
    monkeypatch.setattr(carga, "UMBRAL_MASIVA", 1)
    filas = _bajar(client)
    for f in filas[1:]:
        if f[0] in ("71 AAA1", "13 BBB2"):
            f[filas[0].index("Congelar")] = "Sí"
    assert _celda(filas, "71 CCC3", "Congelar") == "Sí"

    v = _vista(client, filas)
    sin = _cargar(client, filas)
    con = _cargar(client, filas, confirmar_masiva=True)

    assert v["fijan"] == {"congelar": 2} and v["fijan_total"] == 2 and v["umbral_masiva"] == 1
    assert sin.status_code == 422 and "2 precios fijos o factores propios nuevos" in sin.json()["detail"]
    assert con.status_code == 200 and con.json()["aplicados"] == 2
    assert _override(lista, "71 AAA1").congelar is True


def test_descongelar_es_una_quita_y_no_cuenta_como_poner(client, lista):
    v = _vista(client, _editar(_bajar(client), "71 CCC3", Congelar="No"))

    assert v["quitan"] == {"congelar": 1} and v["fijan_total"] == 0


def test_las_fechas_cuentan_contra_el_freno_de_cargas_masivas(client, lista, reloj, monkeypatch):
    """Ordenar solo la columna Hasta deja cada fecha en el producto de otro: es el mismo
    riesgo que ordenar los precios."""
    monkeypatch.setattr(carga, "UMBRAL_MASIVA", 1)
    client.put("/api/precios/71 AAA1/override", json={"precio_fijo": 990})
    filas = _editar(_bajar(client), "71 AAA1", Hasta=_iso(_dias(10)))
    filas = _editar(filas, "13 BBB2", Hasta=_iso(_dias(12)))

    v = _vista(client, filas)

    assert v["fijan"] == {"hasta": 2} and v["fijan_total"] == 2
    assert _cargar(client, filas).status_code == 422
    assert _cargar(client, filas, confirmar_masiva=True).status_code == 200


def test_cargar_dos_veces_el_mismo_archivo_con_fechas_da_sin_cambios(client, lista, reloj):
    filas = _editar(_bajar(client), "71 AAA1", **{"Precio fijo": "990", "Hasta": _iso(_dias(10))})

    primera = _subir(client, _a_csv(filas), aplicar=True).json()
    segunda = _subir(client, _a_csv(filas), aplicar=True).json()

    assert primera["aplicados"] == 1
    assert segunda["aplicados"] == 0 and segunda["omitidos"]["conflictos"] == 0


# ================================ 7. lo que la carga comparte con el servicio de precios
def test_la_decision_que_quedaria_es_la_que_se_guarda_y_no_toca_lo_original(lista):
    """La vista previa calcula el precio de "despues" con la misma `_aplicar_override` que lo
    escribe, sobre una copia: nada de la decision guardada cambia."""
    ov = {"precio_fijo": 990.0, "vigente_desde": _dias(-1), "vigente_hasta": _dias(5), "obs": "piso"}
    original = dict(ov)

    sin_decision = svc.override_despues(ov, {"precio_fijo": None}, 17800, HOY)
    congelado = svc.override_despues({}, {"congelar": True, "vigente_hasta": _dias(5)}, 17800, HOY)

    assert ov == original
    # Sin ninguna decision no hay periodo: se borra, como al guardar.
    assert (sin_decision["precio_fijo"], sin_decision["vigente_desde"], sin_decision["vigente_hasta"]) == (None, None, None)
    assert sin_decision["obs"] == "piso"
    assert (congelado["congelar"], congelado["congelado_precio"], congelado["vigente_hasta"]) == (True, 17800, _dias(5))
    assert len(lista.new) == 0                                  # la copia no queda en la sesion


def test_el_precio_de_hoy_es_el_de_la_fila_salvo_que_el_periodo_no_rija(lista):
    from src.services import politica_precio_service as pol

    fila = {"glosa": "AMORT DEL", "rubro": "71", "procedencia_maestro": "NACIONAL", "costo": 10000,
            "stock": 5, "stock_transito": 0, "ult_recep_importado": None, "ult_pe_nacional": None,
            "precio_sugerido": None}
    fact, rub = pol.factores(lista), pol.rubros(lista)

    def hoy(ov):
        return svc.precio_de_hoy(fila, 990.0, ov, fact, rub, HOY)

    assert hoy({"precio_fijo": 990.0, "vigente_hasta": _dias(5)}) == 990.0          # rige
    assert hoy({}) == 990.0 and hoy(None) == 990.0                                    # sin periodo
    assert hoy({"precio_fijo": 990.0, "vigente_hasta": _dias(-1)}) == 17800           # vencido: la regla
    assert hoy({"precio_fijo": 990.0, "vigente_desde": _dias(3)}) == 17800            # programado: la regla


@pytest.mark.parametrize("ov,esperado", [
    (None, ""),
    ({}, ""),
    ({"precio_fijo": 990.0}, ""),                                                            # sin periodo
    ({"precio_fijo": 990.0, "vigente_hasta": _dias(11)}, "Fijo hasta 31-10-2026"),
    ({"margen_fijo": 35.0, "vigente_hasta": _dias(11)}, "Margen hasta 31-10-2026"),
    ({"congelar": True, "vigente_hasta": _dias(11)}, "Congelado hasta 31-10-2026"),
    ({"precio_fijo": 990.0, "congelar": True, "vigente_hasta": _dias(11)}, "Fijo hasta 31-10-2026"),
    ({"precio_fijo": 990.0, "vigente_desde": _dias(-3)}, ""),                                # vigente sin Hasta
    ({"precio_fijo": 990.0, "vigente_desde": _dias(3), "vigente_hasta": _dias(9)}, "Programado desde 23-10-2026"),
    ({"precio_fijo": 990.0, "vigente_desde": _dias(-9), "vigente_hasta": _dias(-1)}, "Vencido el 19-10-2026"),
    ({"vigente_hasta": _dias(11)}, ""),                                                      # fechas sin decision
    ({"precio_fijo": 990.0, "vigente_hasta": "2026-10-31"}, "Fijo hasta 31-10-2026"),         # fecha en ISO
])
def test_texto_de_la_columna_vigencia(ov, esperado):
    assert svc.texto_vigencia(ov, HOY) == esperado
