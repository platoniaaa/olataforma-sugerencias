"""Carga de precios desde Excel: lo que dejo la tercera revision (15-10-2026).

Un freno nuevo: una carga que pone mas de `UMBRAL_MASIVA` precios fijos o factores
propios pide confirmacion. Ordenar una sola columna (Precio final, Factor) deja cada
valor en la fila de otro producto, y cada fila parece una edicion valida.
"""
from src.models import PrecioOverride
from src.services import precios_carga_service as carga
from src.services import precios_service as svc

from .test_precios import _producto, lista_cargada  # noqa: F401  (fixture)
from .test_precios_carga import _a_csv, _bajar, _override, _subir, lista  # noqa: F401


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
