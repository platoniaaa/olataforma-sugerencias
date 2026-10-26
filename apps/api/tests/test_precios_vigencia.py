"""Vigencia de precio fijo, margen fijo y congelar: datos, regla y ficha.

Un solo periodo por producto (`vigente_desde`, `vigente_hasta`, inclusivos y cada uno
opcional) gobierna las tres decisiones. Fuera del periodo no rigen pero se CONSERVAN:
por eso el vencimiento no escribe en `precio_override` (solo personas) y por eso
existen "Vencido" y "Renovar".

Lo que estos tests cuidan:

1. Que un producto SIN periodo calcule exactamente lo de siempre. Es lo mas importante:
   los 3.163 overrides de produccion no tienen fechas y ningun precio puede moverse por
   haber agregado esta funcion. La tabla de abajo se congelo corriendo la regla anterior.
2. Que 'hoy' sea el de Chile: en UTC, de 21:00 a 24:00 un Hasta venceria 3 horas antes.
3. Que cada regla de validacion rechace lo que tiene que rechazar, y que reenviar el
   estado completo (la ficha manda todo en cada guardado) no falle.
4. Que el vencimiento no toque lo que las personas decidieron.
"""
import inspect
import random
import re
from datetime import date, datetime, timedelta, timezone

import pytest

from src.models import AuditoriaLog, Notificacion, PrecioOverride, PrecioProducto
from src.services import calendario
from src.services import precios_carga_service as carga
from src.services import precios_service as svc

from .test_precios import FACT, RUB, _fila, lista_cargada  # noqa: F401  (fixture)
from .test_precios_carga import _a_csv, _bajar, _editar, _subir

HOY = date(2026, 10, 20)


def _dias(n: int) -> date:
    return HOY + timedelta(days=n)


@pytest.fixture()
def lista(lista_cargada):  # noqa: F811
    svc.recalcular(lista_cargada)
    return lista_cargada


@pytest.fixture()
def reloj(monkeypatch):
    """Fija 'hoy' en Chile y devuelve una funcion para moverlo."""
    estado = {"hoy": HOY}
    monkeypatch.setattr(calendario, "hoy_chile", lambda: estado["hoy"])

    def fijar(dia: date) -> None:
        estado["hoy"] = dia

    return fijar


def _poner(db, producto, **campos):
    """Escribe una decision directo en la base (lo que dejo una persona antes)."""
    o = db.query(PrecioOverride).filter_by(producto=producto).one_or_none()
    if o is None:
        o = PrecioOverride(tenant_id="curifor", producto=producto)
        db.add(o)
    for k, v in campos.items():
        setattr(o, k, v)
    db.commit()
    return o


def _override(db, producto):
    db.expire_all()
    return db.query(PrecioOverride).filter_by(producto=producto).one_or_none()


def _precio(db, producto):
    db.expire_all()
    return db.query(PrecioProducto).filter_by(producto=producto).one()


def guardar(db, datos, producto="71 AAA1"):
    return svc.guardar_override(db, producto, datos, "ana@curifor.com")


# ===================================================== 1. el estado del periodo
@pytest.mark.parametrize("desde,hasta,esperado", [
    (None, None, None),                      # sin periodo
    (HOY, None, "vigente"),                  # Desde = hoy: rige desde hoy
    (None, HOY, "vigente"),                  # Hasta = hoy: hoy es el ultimo dia
    (None, _dias(-1), "vencida"),            # Hasta = ayer
    (_dias(1), None, "programada"),          # Desde = manana
    (HOY, HOY, "vigente"),                   # un periodo de un solo dia
    (_dias(1), _dias(1), "programada"),
    (_dias(-1), _dias(-1), "vencida"),
    (_dias(5), _dias(-5), "vencida"),        # Desde > Hasta: defensivo, nunca rige
    (_dias(-30), _dias(30), "vigente"),
    (_dias(-30), None, "vigente"),           # solo Desde: ya empezo y no termina
    (None, _dias(30), "vigente"),            # solo Hasta: rige desde ya
])
def test_estado_vigencia_en_los_bordes(desde, hasta, esperado):
    assert svc.estado_vigencia(desde, hasta, HOY) == esperado


def test_vigencia_de_exige_que_haya_una_decision_que_gobernar():
    periodo = {"vigente_desde": _dias(-1), "vigente_hasta": _dias(5)}
    assert svc.vigencia_de(None, HOY) is None
    assert svc.vigencia_de({"precio_fijo": 990}, HOY) is None          # sin fechas
    assert svc.vigencia_de({**periodo, "obs": "x", "no_producto": True}, HOY) is None
    for decision in ({"precio_fijo": 990}, {"margen_fijo": 35}, {"congelar": True}):
        assert svc.vigencia_de({**decision, **periodo}, HOY) == "vigente"
    assert svc.vigencia_de({"precio_fijo": 0, **periodo}, HOY) == "vigente"      # 0 es un precio
    assert svc.vigencia_de({"precio_fijo": 990, "vigente_hasta": _dias(-1)}, HOY) == "vencida"
    assert svc.vigencia_de({"precio_fijo": 990, "vigente_desde": _dias(1)}, HOY) == "programada"


def test_sin_decisiones_fijas_deja_el_resto_intacto():
    ov = {"precio_fijo": 990, "margen_fijo": 35, "congelar": True, "congelado_precio": 12000,
          "tipo_manual": "Pesado", "procedencia_manual": "Importado", "no_producto": True,
          "obs": "n", "vigente_hasta": _dias(-1)}
    r = svc._sin_decisiones_fijas(ov)
    assert (r["precio_fijo"], r["margen_fijo"], r["congelar"], r["congelado_precio"]) == (
        None, None, False, None)
    for k in ("tipo_manual", "procedencia_manual", "no_producto", "obs", "vigente_hasta"):
        assert r[k] == ov[k]
    assert ov["precio_fijo"] == 990          # no muta el original


# ============================================ 2. sin periodo no cambia NADA
#
# Congelado corriendo la regla ANTERIOR sobre 59 combinaciones (producto normal, sin
# stock, solo con transito, Sugerido con y sin precio, sin procedencia y neumatico, cada
# uno contra: nada, precio fijo, margen, congelado con y sin foto, no es producto, tipo y
# procedencia a mano, y varias decisiones juntas). Cada fila es
# (tipo, tipo_origen, procedencia, procedencia_origen, factor, calculado, final, estado).
CASOS_BASE = [
    ('normal|sin_override', {}, None,
     ('Liviano', 'rubro', 'Nacional', 'maestro', 1.78, 17800.0, 17800.0, 'OK')),
    ('normal|fijo_990', {}, {'precio_fijo': 990},
     ('Liviano', 'rubro', 'Nacional', 'maestro', 1.78, 17800.0, 990.0, 'FIJO')),
    ('normal|margen_35', {}, {'margen_fijo': 35},
     ('Liviano', 'rubro', 'Nacional', 'maestro', 1.5385, 15385.0, 15385.0, 'MARGEN')),
    ('normal|congelado_12000', {}, {'congelar': True, 'congelado_precio': 12000},
     ('Liviano', 'rubro', 'Nacional', 'maestro', 1.78, 17800.0, 12000.0, 'CONGELADO')),
    ('normal|congelado_sin_foto', {}, {'congelar': True, 'congelado_precio': None},
     ('Liviano', 'rubro', 'Nacional', 'maestro', 1.78, 17800.0, 17800.0, 'CONGELADO')),
    ('normal|no_producto', {}, {'no_producto': True},
     ('Liviano', 'rubro', 'Nacional', 'maestro', 1.78, None, None, 'NO PRODUCTO')),
    ('normal|tipo_y_procedencia_manual', {}, {'tipo_manual': 'Pesado', 'procedencia_manual': 'Importado'},
     ('Pesado', 'manual', 'Importado', 'manual', 2.3, 23000.0, 23000.0, 'OK')),
    ('sin_stock|sin_override', {'stock': 0}, None,
     ('Liviano', 'rubro', 'Nacional', 'maestro', 1.78, 0.0, 0.0, 'SIN STOCK')),
    ('sin_stock|fijo_990', {'stock': 0}, {'precio_fijo': 990},
     ('Liviano', 'rubro', 'Nacional', 'maestro', 1.78, 0.0, 990.0, 'FIJO')),
    ('sin_stock|margen_35', {'stock': 0}, {'margen_fijo': 35},
     ('Liviano', 'rubro', 'Nacional', 'maestro', 1.5385, 0.0, 0.0, 'SIN STOCK')),
    ('sin_stock|congelado_12000', {'stock': 0}, {'congelar': True, 'congelado_precio': 12000},
     ('Liviano', 'rubro', 'Nacional', 'maestro', 1.78, 0.0, 12000.0, 'CONGELADO')),
    ('sin_stock|congelado_sin_foto', {'stock': 0}, {'congelar': True, 'congelado_precio': None},
     ('Liviano', 'rubro', 'Nacional', 'maestro', 1.78, 0.0, 0.0, 'CONGELADO')),
    ('sin_stock|no_producto', {'stock': 0}, {'no_producto': True},
     ('Liviano', 'rubro', 'Nacional', 'maestro', 1.78, 0.0, 0.0, 'SIN STOCK')),
    ('sin_stock|tipo_y_procedencia_manual', {'stock': 0}, {'tipo_manual': 'Pesado', 'procedencia_manual': 'Importado'},
     ('Pesado', 'manual', 'Importado', 'manual', 2.3, 0.0, 0.0, 'SIN STOCK')),
    ('solo_transito|sin_override', {'stock': 0, 'stock_transito': 3}, None,
     ('Liviano', 'rubro', 'Nacional', 'maestro', 1.78, 17800.0, 17800.0, 'OK')),
    ('solo_transito|fijo_990', {'stock': 0, 'stock_transito': 3}, {'precio_fijo': 990},
     ('Liviano', 'rubro', 'Nacional', 'maestro', 1.78, 17800.0, 990.0, 'FIJO')),
    ('solo_transito|margen_35', {'stock': 0, 'stock_transito': 3}, {'margen_fijo': 35},
     ('Liviano', 'rubro', 'Nacional', 'maestro', 1.5385, 15385.0, 15385.0, 'MARGEN')),
    ('solo_transito|congelado_12000', {'stock': 0, 'stock_transito': 3}, {'congelar': True, 'congelado_precio': 12000},
     ('Liviano', 'rubro', 'Nacional', 'maestro', 1.78, 17800.0, 12000.0, 'CONGELADO')),
    ('solo_transito|congelado_sin_foto', {'stock': 0, 'stock_transito': 3}, {'congelar': True, 'congelado_precio': None},
     ('Liviano', 'rubro', 'Nacional', 'maestro', 1.78, 17800.0, 17800.0, 'CONGELADO')),
    ('solo_transito|no_producto', {'stock': 0, 'stock_transito': 3}, {'no_producto': True},
     ('Liviano', 'rubro', 'Nacional', 'maestro', 1.78, None, None, 'NO PRODUCTO')),
    ('solo_transito|tipo_y_procedencia_manual', {'stock': 0, 'stock_transito': 3}, {'tipo_manual': 'Pesado', 'procedencia_manual': 'Importado'},
     ('Pesado', 'manual', 'Importado', 'manual', 2.3, 23000.0, 23000.0, 'OK')),
    ('sugerido_con_precio|sin_override', {'rubro': '95', 'precio_sugerido': 12345.6}, None,
     ('Sugerido', 'rubro', 'Nacional', 'maestro', None, 12346.0, 12346.0, 'SUGERIDO')),
    ('sugerido_con_precio|fijo_990', {'rubro': '95', 'precio_sugerido': 12345.6}, {'precio_fijo': 990},
     ('Sugerido', 'rubro', 'Nacional', 'maestro', None, 12346.0, 990.0, 'FIJO')),
    ('sugerido_con_precio|margen_35', {'rubro': '95', 'precio_sugerido': 12345.6}, {'margen_fijo': 35},
     ('Sugerido', 'rubro', 'Nacional', 'maestro', 1.5385, 15385.0, 15385.0, 'MARGEN')),
    ('sugerido_con_precio|congelado_12000', {'rubro': '95', 'precio_sugerido': 12345.6}, {'congelar': True, 'congelado_precio': 12000},
     ('Sugerido', 'rubro', 'Nacional', 'maestro', None, 12346.0, 12000.0, 'CONGELADO')),
    ('sugerido_con_precio|congelado_sin_foto', {'rubro': '95', 'precio_sugerido': 12345.6}, {'congelar': True, 'congelado_precio': None},
     ('Sugerido', 'rubro', 'Nacional', 'maestro', None, 12346.0, 12346.0, 'CONGELADO')),
    ('sugerido_con_precio|no_producto', {'rubro': '95', 'precio_sugerido': 12345.6}, {'no_producto': True},
     ('Sugerido', 'rubro', 'Nacional', 'maestro', None, None, None, 'NO PRODUCTO')),
    ('sugerido_con_precio|tipo_y_procedencia_manual', {'rubro': '95', 'precio_sugerido': 12345.6}, {'tipo_manual': 'Pesado', 'procedencia_manual': 'Importado'},
     ('Pesado', 'manual', 'Importado', 'manual', 2.3, 23000.0, 23000.0, 'OK')),
    ('sugerido_sin_precio|sin_override', {'rubro': '95', 'precio_sugerido': None}, None,
     ('Sugerido', 'rubro', 'Nacional', 'maestro', None, None, None, 'SIN REVISION')),
    ('sugerido_sin_precio|fijo_990', {'rubro': '95', 'precio_sugerido': None}, {'precio_fijo': 990},
     ('Sugerido', 'rubro', 'Nacional', 'maestro', None, None, 990.0, 'FIJO')),
    ('sugerido_sin_precio|margen_35', {'rubro': '95', 'precio_sugerido': None}, {'margen_fijo': 35},
     ('Sugerido', 'rubro', 'Nacional', 'maestro', 1.5385, 15385.0, 15385.0, 'MARGEN')),
    ('sugerido_sin_precio|congelado_12000', {'rubro': '95', 'precio_sugerido': None}, {'congelar': True, 'congelado_precio': 12000},
     ('Sugerido', 'rubro', 'Nacional', 'maestro', None, None, 12000.0, 'CONGELADO')),
    ('sugerido_sin_precio|congelado_sin_foto', {'rubro': '95', 'precio_sugerido': None}, {'congelar': True, 'congelado_precio': None},
     ('Sugerido', 'rubro', 'Nacional', 'maestro', None, None, None, 'CONGELADO')),
    ('sugerido_sin_precio|no_producto', {'rubro': '95', 'precio_sugerido': None}, {'no_producto': True},
     ('Sugerido', 'rubro', 'Nacional', 'maestro', None, None, None, 'NO PRODUCTO')),
    ('sugerido_sin_precio|tipo_y_procedencia_manual', {'rubro': '95', 'precio_sugerido': None}, {'tipo_manual': 'Pesado', 'procedencia_manual': 'Importado'},
     ('Pesado', 'manual', 'Importado', 'manual', 2.3, 23000.0, 23000.0, 'OK')),
    ('sin_procedencia|sin_override', {'procedencia_maestro': ''}, None,
     ('Liviano', 'rubro', 'SIN REVISION', 'default', None, None, None, 'SIN REVISION')),
    ('sin_procedencia|fijo_990', {'procedencia_maestro': ''}, {'precio_fijo': 990},
     ('Liviano', 'rubro', 'SIN REVISION', 'default', None, None, 990.0, 'FIJO')),
    ('sin_procedencia|margen_35', {'procedencia_maestro': ''}, {'margen_fijo': 35},
     ('Liviano', 'rubro', 'SIN REVISION', 'default', 1.5385, 15385.0, 15385.0, 'MARGEN')),
    ('sin_procedencia|congelado_12000', {'procedencia_maestro': ''}, {'congelar': True, 'congelado_precio': 12000},
     ('Liviano', 'rubro', 'SIN REVISION', 'default', None, None, 12000.0, 'CONGELADO')),
    ('sin_procedencia|congelado_sin_foto', {'procedencia_maestro': ''}, {'congelar': True, 'congelado_precio': None},
     ('Liviano', 'rubro', 'SIN REVISION', 'default', None, None, None, 'CONGELADO')),
    ('sin_procedencia|no_producto', {'procedencia_maestro': ''}, {'no_producto': True},
     ('Liviano', 'rubro', 'SIN REVISION', 'default', None, None, None, 'NO PRODUCTO')),
    ('sin_procedencia|tipo_y_procedencia_manual', {'procedencia_maestro': ''}, {'tipo_manual': 'Pesado', 'procedencia_manual': 'Importado'},
     ('Pesado', 'manual', 'Importado', 'manual', 2.3, 23000.0, 23000.0, 'OK')),
    ('neumatico|sin_override', {'glosa': 'NEUMATICO 265/70 R16'}, None,
     ('Neumatico', 'glosa', 'Nacional', 'maestro', 1.33, 13300.0, 13300.0, 'OK')),
    ('neumatico|fijo_990', {'glosa': 'NEUMATICO 265/70 R16'}, {'precio_fijo': 990},
     ('Neumatico', 'glosa', 'Nacional', 'maestro', 1.33, 13300.0, 990.0, 'FIJO')),
    ('neumatico|margen_35', {'glosa': 'NEUMATICO 265/70 R16'}, {'margen_fijo': 35},
     ('Neumatico', 'glosa', 'Nacional', 'maestro', 1.5385, 15385.0, 15385.0, 'MARGEN')),
    ('neumatico|congelado_12000', {'glosa': 'NEUMATICO 265/70 R16'}, {'congelar': True, 'congelado_precio': 12000},
     ('Neumatico', 'glosa', 'Nacional', 'maestro', 1.33, 13300.0, 12000.0, 'CONGELADO')),
    ('neumatico|congelado_sin_foto', {'glosa': 'NEUMATICO 265/70 R16'}, {'congelar': True, 'congelado_precio': None},
     ('Neumatico', 'glosa', 'Nacional', 'maestro', 1.33, 13300.0, 13300.0, 'CONGELADO')),
    ('neumatico|no_producto', {'glosa': 'NEUMATICO 265/70 R16'}, {'no_producto': True},
     ('Neumatico', 'glosa', 'Nacional', 'maestro', 1.33, None, None, 'NO PRODUCTO')),
    ('neumatico|tipo_y_procedencia_manual', {'glosa': 'NEUMATICO 265/70 R16'}, {'tipo_manual': 'Pesado', 'procedencia_manual': 'Importado'},
     ('Pesado', 'manual', 'Importado', 'manual', 2.3, 23000.0, 23000.0, 'OK')),
    ('normal|fijo_y_congelado', {}, {'precio_fijo': 990, 'congelar': True, 'congelado_precio': 12000},
     ('Liviano', 'rubro', 'Nacional', 'maestro', 1.78, 17800.0, 990.0, 'FIJO')),
    ('sin_stock|fijo_y_congelado', {'stock': 0}, {'precio_fijo': 990, 'congelar': True, 'congelado_precio': 12000},
     ('Liviano', 'rubro', 'Nacional', 'maestro', 1.78, 0.0, 990.0, 'FIJO')),
    ('normal|margen_y_no_producto', {}, {'margen_fijo': 35, 'no_producto': True},
     ('Liviano', 'rubro', 'Nacional', 'maestro', 1.5385, None, None, 'NO PRODUCTO')),
    ('sin_stock|margen_y_no_producto', {'stock': 0}, {'margen_fijo': 35, 'no_producto': True},
     ('Liviano', 'rubro', 'Nacional', 'maestro', 1.5385, 0.0, 0.0, 'SIN STOCK')),
    ('normal|fijo_y_no_producto', {}, {'precio_fijo': 990, 'no_producto': True},
     ('Liviano', 'rubro', 'Nacional', 'maestro', 1.78, None, 990.0, 'FIJO')),
    ('sin_stock|fijo_y_no_producto', {'stock': 0}, {'precio_fijo': 990, 'no_producto': True},
     ('Liviano', 'rubro', 'Nacional', 'maestro', 1.78, 0.0, 990.0, 'FIJO')),
    ('normal|margen_y_manual', {}, {'margen_fijo': 35, 'tipo_manual': 'Pesado', 'procedencia_manual': 'Importado'},
     ('Pesado', 'manual', 'Importado', 'manual', 1.5385, 15385.0, 15385.0, 'MARGEN')),
    ('sin_stock|margen_y_manual', {'stock': 0}, {'margen_fijo': 35, 'tipo_manual': 'Pesado', 'procedencia_manual': 'Importado'},
     ('Pesado', 'manual', 'Importado', 'manual', 1.5385, 0.0, 0.0, 'SIN STOCK')),
    ('normal|margen_y_congelado', {}, {'margen_fijo': 35, 'congelar': True, 'congelado_precio': 12000},
     ('Liviano', 'rubro', 'Nacional', 'maestro', 1.5385, 15385.0, 12000.0, 'CONGELADO')),
    ('sin_stock|margen_y_congelado', {'stock': 0}, {'margen_fijo': 35, 'congelar': True, 'congelado_precio': 12000},
     ('Liviano', 'rubro', 'Nacional', 'maestro', 1.5385, 0.0, 12000.0, 'CONGELADO')),
]

# Lo que valia `huella_decisiones` ANTES de la vigencia, para cada forma de override.
HUELLAS_HISTORICAS = {
    'vacia': (None, 'eed06f35'),
    'solo_obs': ({'obs': 'campania'}, '6c68c428'),
    'fijo': ({'precio_fijo': 990.0, 'obs': 'piso'}, 'd0d9de38'),
    'margen': ({'margen_fijo': 35.0}, '822fe633'),
    'congelado': ({'congelar': True, 'congelado_precio': 12000, 'obs': 'feria'}, 'ce19feac'),
    'todo': ({'tipo_manual': 'Pesado', 'procedencia_manual': 'Importado', 'margen_fijo': 28.571429, 'precio_fijo': 1234.5, 'congelar': True, 'no_producto': True, 'obs': 'nota con ñ y acentos áé'}, 'afbb42e2'),
}

_CAMPOS = ("tipo", "tipo_origen", "procedencia_final", "procedencia_origen", "factor",
           "precio_calculado", "precio_final", "estado")
_IDS = [c[0] for c in CASOS_BASE]


@pytest.mark.parametrize("nombre,fila,ov,esperado", CASOS_BASE, ids=_IDS)
def test_sin_periodo_calcular_da_lo_mismo_que_siempre(nombre, fila, ov, esperado):
    r = svc.calcular(_fila(**fila), ov, FACT, RUB)

    assert tuple(r[k] for k in _CAMPOS) == esperado
    assert r["vigencia_aplicada"] is None


def _decide(ov) -> bool:
    return bool(ov) and (ov.get("precio_fijo") is not None or ov.get("margen_fijo") is not None
                         or bool(ov.get("congelar")))


@pytest.mark.parametrize("nombre,fila,ov,esperado", [c for c in CASOS_BASE if _decide(c[2])],
                         ids=[c[0] for c in CASOS_BASE if _decide(c[2])])
def test_un_periodo_vigente_no_cambia_ninguna_combinacion(nombre, fila, ov, esperado):
    periodo = {"vigente_desde": _dias(-3), "vigente_hasta": _dias(3)}

    r = svc.calcular(_fila(**fila), {**ov, **periodo}, FACT, RUB, hoy=HOY)

    assert tuple(r[k] for k in _CAMPOS) == esperado
    assert r["vigencia_aplicada"] == "vigente"


@pytest.mark.parametrize("periodo,estado", [
    ({"vigente_hasta": _dias(-1)}, "vencida"),
    ({"vigente_desde": _dias(1)}, "programada"),
    ({"vigente_desde": _dias(5), "vigente_hasta": _dias(-5)}, "vencida"),
])
@pytest.mark.parametrize("nombre,fila,ov,esperado", [c for c in CASOS_BASE if _decide(c[2])],
                         ids=[c[0] for c in CASOS_BASE if _decide(c[2])])
def test_fuera_del_periodo_las_tres_decisiones_no_rigen(nombre, fila, ov, esperado, periodo, estado):
    """Programada o vencida = como si la persona no hubiera decidido el precio. Lo demas
    que decidio (tipo, procedencia, no es producto) sigue rigiendo."""
    sin_precio = {k: v for k, v in ov.items()
                  if k not in ("precio_fijo", "margen_fijo", "congelar", "congelado_precio")}

    r = svc.calcular(_fila(**fila), {**ov, **periodo}, FACT, RUB, hoy=HOY)
    base = svc.calcular(_fila(**fila), sin_precio or None, FACT, RUB)

    assert {k: r[k] for k in _CAMPOS} == {k: base[k] for k in _CAMPOS}
    assert r["vigencia_aplicada"] == estado


def test_con_periodo_en_tres_mil_combinaciones_al_azar_vale_lo_mismo_que_sin_el():
    """Vigente = como sin periodo. Programada o vencida = como si no hubiera decidido el
    precio. En todas las combinaciones, no solo en la tabla de arriba."""
    azar = random.Random(20261020)
    periodos = {"vigente": {"vigente_desde": _dias(-3), "vigente_hasta": _dias(3)},
                "programada": {"vigente_desde": _dias(2)},
                "vencida": {"vigente_hasta": _dias(-2)}}
    campos = ("tipo", "tipo_origen", "procedencia_final", "procedencia_origen", "factor",
              "precio_calculado", "precio_final", "estado")
    for _ in range(3000):
        fila = _fila(
            costo=azar.choice([0, 1000, 10000, 54115, 99999]), stock=azar.choice([0, 1, 5]),
            stock_transito=azar.choice([0, 3]), rubro=azar.choice(["71", "13", "86", "95", "99"]),
            glosa=azar.choice(["AMORTIGUADOR", "NEUMATICO 265/70"]),
            procedencia_maestro=azar.choice(["NACIONAL", "IMPORTADO", ""]),
            precio_sugerido=azar.choice([None, 0, 12345.6]))
        ov = {}
        if azar.random() < .4:
            ov["precio_fijo"] = azar.choice([0, 990, 17800])
        if azar.random() < .4:
            ov["margen_fijo"] = azar.choice([10, 35, 60])
        if azar.random() < .4:
            ov.update(congelar=True, congelado_precio=azar.choice([None, 12000]))
        if azar.random() < .2:
            ov["no_producto"] = True
        if azar.random() < .3:
            ov.update(tipo_manual="Pesado", procedencia_manual="Importado")
        decide = _decide(ov)
        sin_precio = {k: v for k, v in ov.items()
                      if k not in ("precio_fijo", "margen_fijo", "congelar", "congelado_precio")}
        sin = svc.calcular(fila, ov, FACT, RUB)
        sin_decision = svc.calcular(fila, sin_precio, FACT, RUB)
        for estado, periodo in periodos.items():
            r = svc.calcular(fila, {**ov, **periodo}, FACT, RUB, hoy=HOY)
            esperado = sin if estado == "vigente" else sin_decision
            assert {k: r[k] for k in campos} == {k: esperado[k] for k in campos}, (fila, ov, estado)
            assert r["vigencia_aplicada"] == (estado if decide else None)


def test_un_periodo_sin_decision_no_deja_estado_ni_cambia_el_precio():
    ov = {"obs": "nota", "tipo_manual": "Pesado", "vigente_hasta": _dias(-1)}

    r = svc.calcular(_fila(), ov, FACT, RUB, hoy=HOY)

    assert r["vigencia_aplicada"] is None and r["factor"] == 2.16


# ====================================== 3. la tabla de verdad (costo 10.000, 1,78)
@pytest.mark.parametrize("decision,rige", [
    ({"precio_fijo": 990}, (990.0, "FIJO", 1.78)),
    ({"margen_fijo": 35}, (15385.0, "MARGEN", 1.5385)),
    ({"congelar": True, "congelado_precio": 12000}, (12000.0, "CONGELADO", 1.78)),
])
@pytest.mark.parametrize("periodo,estado", [
    ({"vigente_desde": _dias(-1), "vigente_hasta": _dias(1)}, "vigente"),
    ({"vigente_desde": _dias(1), "vigente_hasta": _dias(9)}, "programada"),
    ({"vigente_desde": _dias(-9), "vigente_hasta": _dias(-1)}, "vencida"),
])
def test_tabla_de_verdad_de_la_vigencia(decision, rige, periodo, estado):
    r = svc.calcular(_fila(), {**decision, **periodo}, FACT, RUB, hoy=HOY)

    esperado = rige if estado == "vigente" else (17800.0, "OK", 1.78)
    assert (r["precio_final"], r["estado"], r["factor"]) == esperado
    assert r["precio_calculado"] == (15385.0 if decision.get("margen_fijo") and estado == "vigente"
                                     else 17800.0)
    assert r["vigencia_aplicada"] == estado


# ============================================================ 4. hoy es el de Chile
def _desde_utc(*args) -> datetime:
    """Un instante dado en UTC, expresado en hora de Chile (lo que devuelve el reloj)."""
    return datetime(*args, tzinfo=timezone.utc).astimezone(calendario.TZ_CHILE)


@pytest.mark.parametrize("instante_utc,estado", [
    ((2026, 11, 1, 2, 30), "vigente"),     # 31-10 23:30 en Chile: en UTC ya es 1 de noviembre
    ((2026, 11, 1, 3, 1), "vencida"),      # 01-11 00:01 en Chile
    ((2026, 9, 6, 3, 30), "vigente"),      # 05-09 23:30 (UTC-4): el horario de verano empieza a las 24:00
    ((2026, 9, 6, 4, 10), "vencida"),      # 06-09 01:10 (UTC-3)
    ((2026, 4, 5, 3, 10), "vigente"),      # 04-04 23:10 por segunda vez: el reloj retrocede a las 24:00
    ((2026, 4, 5, 4, 10), "vencida"),      # 05-04 00:10
])
def test_el_ultimo_dia_rige_hasta_la_medianoche_de_chile(monkeypatch, instante_utc, estado):
    chile = _desde_utc(*instante_utc)
    monkeypatch.setattr(calendario, "ahora_chile", lambda: chile)
    hasta = {(2026, 11, 1): date(2026, 10, 31), (2026, 9, 6): date(2026, 9, 5),
             (2026, 4, 5): date(2026, 4, 4)}[instante_utc[:3]]

    r = svc.calcular(_fila(), {"precio_fijo": 990, "vigente_hasta": hasta}, FACT, RUB)

    assert r["vigencia_aplicada"] == estado
    assert r["estado"] == ("FIJO" if estado == "vigente" else "OK")


def test_en_utc_el_mismo_instante_daria_otra_respuesta():
    """El caso que este diseño evita: 31-10 23:30 en Chile ya es 1 de noviembre en UTC."""
    chile = _desde_utc(2026, 11, 1, 2, 30)

    assert chile.date() == date(2026, 10, 31)
    assert chile.astimezone(timezone.utc).date() == date(2026, 11, 1)
    assert svc.estado_vigencia(None, date(2026, 10, 31), chile.date()) == "vigente"
    assert svc.estado_vigencia(None, date(2026, 10, 31), chile.astimezone(timezone.utc).date()) == "vencida"


def test_la_vigencia_no_decide_con_la_fecha_del_servidor():
    """Render corre en UTC: `date.today()` o `utcnow().date()` en cualquiera de estas
    funciones hace vencer y empezar los periodos 3 horas antes."""
    prohibido = re.compile(r"date\.today\(|datetime\.today\(|utcnow|\.date\(\)")
    funciones = (svc.estado_vigencia, svc.vigencia_de, svc.calcular, svc.validar_vigencia,
                 svc.guardar_override, svc._aplicar_override, svc._fila_dict, svc.recalcular,
                 svc._recalcular_una, svc._decision_de_precio, svc.detalle, svc.listar)
    for f in funciones:
        fuente = inspect.getsource(f)
        assert not prohibido.search(fuente), f"{f.__name__} usa la fecha del servidor"
    assert svc.calendario is calendario


# ================================================ 5. validar_vigencia (pura)
FIJO_VIGENTE = {"precio_fijo": 990.0, "vigente_desde": _dias(-1), "vigente_hasta": _dias(10)}
FIJO_VENCIDO = {"precio_fijo": 990.0, "vigente_desde": _dias(-20), "vigente_hasta": _dias(-1)}
CONGELADO_VIGENTE = {"congelar": True, "vigente_desde": _dias(-1), "vigente_hasta": _dias(10)}

MSG_ORDEN = "El Desde no puede ser posterior al Hasta."
MSG_VENCIDO = ("El periodo ya terminó (Hasta 19-10-2026): pon un Hasta de hoy en adelante o "
               "déjalo sin vencimiento.")
MSG_CONGELAR = ("Congelar toma el precio de hoy: no se puede programar con un Desde futuro "
                "(usa precio fijo).")
MSG_SIN_DECISION = "El periodo aplica a precio fijo, margen fijo o congelar: define uno."
MSG_3_ANIOS = "La fecha está a más de 3 años de hoy."


@pytest.mark.parametrize("ov,datos,esperado", [
    # --- lo que se rechaza ---
    ({}, {"precio_fijo": 500, "vigente_desde": _dias(5), "vigente_hasta": _dias(1)},
     [(MSG_ORDEN, False)]),
    (FIJO_VIGENTE, {"vigente_desde": _dias(20)}, [(MSG_ORDEN, True)]),     # el Hasta es el guardado
    ({}, {"precio_fijo": 500, "vigente_hasta": _dias(-1)}, [(MSG_VENCIDO, False)]),
    (FIJO_VENCIDO, {"precio_fijo": 700}, [(MSG_VENCIDO, True)]),           # el periodo es el guardado
    (FIJO_VENCIDO, {"margen_fijo": 30, "precio_fijo": None}, [(MSG_VENCIDO, True)]),
    ({}, {"congelar": True, "vigente_desde": _dias(2)}, [(MSG_CONGELAR, False)]),
    (CONGELADO_VIGENTE, {"vigente_desde": _dias(3)}, [(MSG_CONGELAR, True)]),
    ({}, {"vigente_hasta": _dias(5)}, [(MSG_SIN_DECISION, True)]),
    ({}, {"vigente_desde": _dias(5)}, [(MSG_SIN_DECISION, True)]),
    ({}, {"precio_fijo": 500, "vigente_hasta": date(2030, 1, 1)}, [(MSG_3_ANIOS, False)]),
    ({}, {"precio_fijo": 500, "vigente_desde": date(2022, 10, 1)}, [(MSG_3_ANIOS, False)]),
    # --- lo que pasa ---
    ({}, {"precio_fijo": 500, "vigente_hasta": _dias(5)}, []),
    ({}, {"precio_fijo": 500, "vigente_desde": HOY, "vigente_hasta": HOY}, []),
    ({}, {"precio_fijo": 500, "vigente_hasta": HOY}, []),                  # Hasta = hoy: ultimo dia
    ({}, {"congelar": True, "vigente_desde": HOY, "vigente_hasta": _dias(30)}, []),
    ({}, {"precio_fijo": 500, "vigente_hasta": date(2029, 10, 20)}, []),   # justo 3 anios
    ({}, {"vigente_hasta": None, "vigente_desde": None}, []),              # nada que quitar
    ({}, {"obs": "x"}, []),
    # --- reenviar el estado completo de un vencido, cambiando solo la obs ---
    (FIJO_VENCIDO, {"obs": "nueva"}, []),
    (FIJO_VENCIDO, {"precio_fijo": 990.0, "margen_fijo": None, "congelar": False,
                    "vigente_desde": _dias(-20), "vigente_hasta": _dias(-1), "obs": "nueva"}, []),
    ({**FIJO_VENCIDO, "vigente_desde": None}, {"precio_fijo": 990, "vigente_desde": None,
                                              "vigente_hasta": _dias(-1)}, []),
    # --- renovar, quitar el vencimiento o quitar la decision ---
    (FIJO_VENCIDO, {"vigente_hasta": _dias(30)}, []),
    (FIJO_VENCIDO, {"vigente_hasta": None}, []),
    (FIJO_VENCIDO, {"precio_fijo": None}, []),
    (FIJO_VIGENTE, {"precio_fijo": None, "vigente_hasta": _dias(5)}, []),  # sin decision: se borran solas
    ({**FIJO_VENCIDO, "congelar": True}, {"congelar": False}, []),         # solo quita una de dos
    # --- un congelado nuevo sobre un fijo vigente con Desde pasado ---
    (FIJO_VIGENTE, {"congelar": True}, []),
])
def test_validar_vigencia(ov, datos, esperado):
    errores = svc.validar_vigencia(ov, datos, HOY)

    assert [(e.mensaje, e.de_combinacion) for e in errores] == esperado


# ================================================= 6. guardar la decision (ficha)
def test_un_precio_fijo_con_periodo_rige_dentro_del_periodo_y_vuelve_a_la_regla_despues(lista, reloj):
    fila = guardar(lista, {"precio_fijo": 990, "vigente_desde": HOY, "vigente_hasta": _dias(10)})

    assert (fila["precio_final"], fila["estado"], fila["precio_fijo"]) == (990, "FIJO", 990)
    assert (fila["vigente_desde"], fila["vigente_hasta"]) == ("2026-10-20", "2026-10-30")
    assert (fila["vigencia"], fila["vigencia_dias"]) == ("vigente", 10)
    assert _precio(lista, "71 AAA1").vigencia_aplicada == "vigente"
    ov = _override(lista, "71 AAA1")
    quien, cuando = ov.editado_por, ov.editado_en

    reloj(_dias(11))
    svc.recalcular(lista, usuario="motor", refrescar_insumos=False)

    p = _precio(lista, "71 AAA1")
    assert (p.precio_final, p.estado, p.vigencia_aplicada) == (17800, "OK", "vencida")
    # El vencimiento NO escribe en precio_override: la decision sigue ahi, intacta.
    ov = _override(lista, "71 AAA1")
    assert (ov.precio_fijo, ov.vigente_hasta) == (990, _dias(10))
    assert (ov.editado_por, ov.editado_en) == (quien, cuando)
    # La ficha muestra la decision guardada y lo que rige hoy.
    ficha = svc.detalle(lista, "71 AAA1")
    assert (ficha["precio_fijo"], ficha["estado"], ficha["precio_final"]) == (990, "OK", 17800)
    assert (ficha["vigencia"], ficha["vigencia_dias"]) == ("vencida", 1)


def test_un_precio_programado_no_rige_hasta_su_desde(lista, reloj):
    fila = guardar(lista, {"precio_fijo": 990, "vigente_desde": _dias(3), "vigente_hasta": _dias(9)})

    assert (fila["precio_fijo"], fila["precio_final"], fila["estado"]) == (990, 17800, "OK")
    assert (fila["vigencia"], fila["vigencia_dias"]) == ("programada", 3)
    assert _precio(lista, "71 AAA1").vigencia_aplicada == "programada"

    reloj(_dias(3))
    svc.recalcular(lista, refrescar_insumos=False)

    p = _precio(lista, "71 AAA1")
    assert (p.precio_final, p.estado, p.vigencia_aplicada) == (990, "FIJO", "vigente")


def test_un_periodo_solo_con_desde_o_solo_con_hasta(lista, reloj):
    fila = guardar(lista, {"margen_fijo": 35, "vigente_hasta": _dias(0)})      # rige hasta hoy
    assert (fila["estado"], fila["vigencia"], fila["vigencia_dias"]) == ("MARGEN", "vigente", 0)

    fila = guardar(lista, {"vigente_hasta": None, "vigente_desde": _dias(-5)})  # permanente desde hace 5 dias
    assert (fila["estado"], fila["vigencia"], fila["vigencia_dias"]) == ("MARGEN", "vigente", None)


@pytest.mark.parametrize("datos,mensaje", [
    ({"precio_fijo": 990, "vigente_desde": _dias(5), "vigente_hasta": _dias(1)}, MSG_ORDEN),
    ({"precio_fijo": 990, "vigente_hasta": _dias(-1)}, MSG_VENCIDO),
    ({"congelar": True, "vigente_desde": _dias(2)}, MSG_CONGELAR),
    ({"vigente_hasta": _dias(5)}, MSG_SIN_DECISION),
    ({"precio_fijo": 990, "vigente_hasta": date(2030, 1, 1)}, MSG_3_ANIOS),
])
def test_cada_rechazo_dice_que_paso_y_no_escribe_nada(lista, reloj, datos, mensaje):
    with pytest.raises(ValueError) as e:
        guardar(lista, datos)

    assert str(e.value) == mensaje
    lista.commit()                  # aunque la sesion se reuse, no queda ninguna fila a medias
    assert _override(lista, "71 AAA1") is None
    assert _precio(lista, "71 AAA1").precio_final == 17800


def test_reenviar_el_estado_completo_de_un_vencido_cambiando_solo_la_obs_se_guarda(lista, reloj):
    """La ficha manda todo en cada guardado: editar una nota de un precio ya vencido
    no puede dar un 422 por un periodo que la persona no toco."""
    guardar(lista, {"precio_fijo": 990, "vigente_desde": HOY, "vigente_hasta": _dias(2)})
    reloj(_dias(5))
    svc.recalcular(lista, refrescar_insumos=False)

    fila = guardar(lista, {"precio_fijo": 990, "margen_fijo": None, "congelar": False,
                           "vigente_desde": HOY, "vigente_hasta": _dias(2), "obs": "campaña vieja"})

    assert fila["obs"] == "campaña vieja" and fila["precio_fijo"] == 990
    assert (fila["vigencia"], fila["estado"], fila["precio_final"]) == ("vencida", "OK", 17800)
    ov = _override(lista, "71 AAA1")
    assert (ov.vigente_desde, ov.vigente_hasta) == (HOY, _dias(2))


def test_renovar_un_vencido_con_un_hasta_nuevo_lo_vuelve_a_activar(lista, reloj):
    guardar(lista, {"precio_fijo": 990, "vigente_desde": HOY, "vigente_hasta": _dias(2)})
    reloj(_dias(5))
    svc.recalcular(lista, refrescar_insumos=False)
    assert _precio(lista, "71 AAA1").estado == "OK"

    fila = guardar(lista, {"vigente_hasta": _dias(30)})

    assert (fila["estado"], fila["precio_final"], fila["vigencia"]) == ("FIJO", 990, "vigente")


def test_quitar_la_ultima_decision_borra_el_periodo(lista, reloj):
    guardar(lista, {"precio_fijo": 990, "obs": "piso", "vigente_desde": HOY, "vigente_hasta": _dias(10)})

    fila = guardar(lista, {"precio_fijo": None})

    ov = _override(lista, "71 AAA1")
    assert (ov.precio_fijo, ov.vigente_desde, ov.vigente_hasta) == (None, None, None)
    assert ov.obs == "piso"                       # lo demas se conserva
    assert (fila["vigencia"], fila["vigente_desde"], fila["vigente_hasta"]) == (None, None, None)
    assert (fila["estado"], fila["precio_final"]) == ("OK", 17800)


def test_quitar_un_extremo_deja_el_otro(lista, reloj):
    guardar(lista, {"precio_fijo": 990, "vigente_desde": HOY, "vigente_hasta": _dias(10)})

    fila = guardar(lista, {"vigente_hasta": None})

    assert (fila["vigente_desde"], fila["vigente_hasta"]) == ("2026-10-20", None)
    assert fila["vigencia"] == "vigente"


def test_la_auditoria_dice_de_que_periodo_a_cual(lista, reloj):
    guardar(lista, {"precio_fijo": 990, "vigente_desde": HOY, "vigente_hasta": _dias(10)})
    guardar(lista, {"vigente_hasta": _dias(20)})
    guardar(lista, {"precio_fijo": None})

    # El id de la auditoria es un uuid: no da el orden, se busca cada frase en el conjunto.
    detalles = [a.detalle for a in lista.query(AuditoriaLog).filter_by(accion="precio_override").all()]
    assert len(detalles) == 3
    for frase in ("periodo sin periodo -> 20-10-2026 a 30-10-2026",
                  "periodo 20-10-2026 a 30-10-2026 -> 20-10-2026 a 09-11-2026",
                  "periodo 20-10-2026 a 09-11-2026 -> sin periodo"):
        assert sum(frase in d for d in detalles) == 1, frase


# --- precio fijo y margen no conviven: el mensaje dice cual es el vencido
def test_el_mensaje_de_fijo_y_margen_dice_cuando_el_estorbo_esta_vencido(lista, reloj):
    guardar(lista, {"margen_fijo": 35, "vigente_hasta": _dias(2)})
    reloj(_dias(5))

    with pytest.raises(ValueError) as e:
        guardar(lista, {"precio_fijo": 5000})

    assert str(e.value) == ("Elige precio fijo o margen fijo, no los dos "
                            "(el margen fijo guardado está vencido: bórralo o renuévalo)")


def test_el_mensaje_de_fijo_y_margen_dice_cuando_el_estorbo_esta_programado(lista, reloj):
    guardar(lista, {"precio_fijo": 5000, "vigente_desde": _dias(3)})

    with pytest.raises(ValueError) as e:
        guardar(lista, {"margen_fijo": 35})

    assert "el precio fijo guardado está programado: bórralo o renuévalo" in str(e.value)


def test_el_mensaje_de_fijo_y_margen_sigue_igual_si_el_guardado_esta_vigente_o_sin_periodo(lista, reloj):
    guardar(lista, {"margen_fijo": 35, "vigente_hasta": _dias(30)})
    with pytest.raises(ValueError) as e:
        guardar(lista, {"precio_fijo": 5000})
    assert str(e.value) == "Elige precio fijo o margen fijo, no los dos"

    with pytest.raises(ValueError) as e:
        guardar(lista, {"precio_fijo": 5000, "margen_fijo": 35}, producto="71 CCC3")
    assert str(e.value) == "Elige precio fijo o margen fijo, no los dos"


# --- congelar: el precio que queda congelado es el de HOY
def test_renovar_un_congelado_vencido_vuelve_a_congelar_el_precio_de_hoy(lista, reloj):
    guardar(lista, {"congelar": True, "vigente_hasta": _dias(5)})
    assert _override(lista, "71 AAA1").congelado_precio == 17800
    # El costo sube: el congelado vigente no se entera, el vencido vuelve a la regla.
    p = _precio(lista, "71 AAA1")
    p.costo = 20000
    lista.commit()
    reloj(_dias(6))
    svc.recalcular(lista, refrescar_insumos=False)
    assert _precio(lista, "71 AAA1").precio_final == 35600

    fila = guardar(lista, {"vigente_hasta": _dias(40)})

    assert _override(lista, "71 AAA1").congelado_precio == 35600
    assert (fila["estado"], fila["precio_final"]) == ("CONGELADO", 35600)


def test_renovar_un_congelado_vencido_toma_el_precio_de_hoy_aunque_nadie_haya_recalculado(lista, reloj):
    """El vencimiento se aplica en el proximo recalculo: hasta entonces la fila guarda
    el precio congelado. Al renovar, el precio de hoy es el que da la regla, no ese."""
    guardar(lista, {"congelar": True, "vigente_hasta": _dias(5)})
    p = _precio(lista, "71 AAA1")
    p.costo = 20000
    lista.commit()
    reloj(_dias(6))                              # vencio y nadie recalculo
    assert _precio(lista, "71 AAA1").precio_final == 17800

    guardar(lista, {"vigente_hasta": _dias(40)})

    assert _override(lista, "71 AAA1").congelado_precio == 35600


def test_renovar_un_congelado_vigente_conserva_su_precio(lista, reloj):
    guardar(lista, {"congelar": True, "vigente_hasta": _dias(5)})
    p = _precio(lista, "71 AAA1")
    p.costo = 20000
    lista.commit()
    svc.recalcular(lista, refrescar_insumos=False)
    assert _precio(lista, "71 AAA1").precio_final == 17800            # sigue congelado

    fila = guardar(lista, {"vigente_hasta": _dias(40)})

    assert _override(lista, "71 AAA1").congelado_precio == 17800
    assert (fila["estado"], fila["precio_final"]) == ("CONGELADO", 17800)


def test_congelar_sin_periodo_se_comporta_como_siempre(lista, reloj):
    fila = guardar(lista, {"congelar": True})
    assert (fila["estado"], fila["precio_final"], fila["vigencia"]) == ("CONGELADO", 17800, None)
    assert _override(lista, "71 AAA1").congelado_precio == 17800

    guardar(lista, {"congelar": False})
    ov = _override(lista, "71 AAA1")
    assert (ov.congelar, ov.congelado_precio, ov.congelado_en) == (False, None, None)


# ============================================================== 7. la API
def test_el_put_acepta_y_devuelve_las_fechas(client, lista, reloj):
    r = client.put("/api/precios/71 AAA1/override", json={
        "precio_fijo": 990, "vigente_desde": "2026-10-20", "vigente_hasta": "2026-10-31", "obs": "oferta"})

    assert r.status_code == 200, r.text
    f = r.json()
    assert (f["vigente_desde"], f["vigente_hasta"]) == ("2026-10-20", "2026-10-31")
    assert (f["vigencia"], f["vigencia_dias"], f["estado"], f["precio_final"]) == ("vigente", 11, "FIJO", 990)
    assert "vigencia_aplicada" not in f             # el marcador es interno

    r = client.put("/api/precios/71 AAA1/override", json={"vigente_hasta": None})
    assert r.json()["vigente_hasta"] is None and r.json()["vigente_desde"] == "2026-10-20"


@pytest.mark.parametrize("malo", ["2026-13-40", "31-10-2026", "2026/10/31", 20261031, "mañana",
                                  "2026-10-31T10:00:00", True, ""])
def test_el_put_rechaza_fechas_mal_formadas(client, lista, reloj, malo):
    for campo in ("vigente_desde", "vigente_hasta"):
        r = client.put("/api/precios/71 AAA1/override", json={"precio_fijo": 990, campo: malo})
        assert r.status_code == 422, (campo, malo, r.text)
    assert _override(lista, "71 AAA1") is None


def test_el_put_responde_422_con_el_mensaje_legible(client, lista, reloj):
    r = client.put("/api/precios/71 AAA1/override", json={"precio_fijo": 990, "vigente_hasta": "2026-10-19"})
    assert r.status_code == 422 and r.json()["detail"] == MSG_VENCIDO

    r = client.put("/api/precios/71 AAA1/override", json={"vigente_hasta": "2026-10-30"})
    assert r.status_code == 422 and r.json()["detail"] == MSG_SIN_DECISION

    r = client.put("/api/precios/71 AAA1/override", json={"congelar": True, "vigente_desde": "2026-10-25"})
    assert r.status_code == 422 and r.json()["detail"] == MSG_CONGELAR


def test_la_lista_y_la_ficha_traen_la_vigencia_y_solo_la_ficha_el_precio_de_la_regla(client, lista, reloj):
    client.put("/api/precios/71 AAA1/override", json={
        "precio_fijo": 990, "vigente_desde": "2026-10-20", "vigente_hasta": "2026-10-31"})
    client.put("/api/precios/13 BBB2/override", json={"obs": "sin periodo"})

    items = {i["producto"]: i for i in client.get("/api/precios").json()["items"]}
    assert (items["71 AAA1"]["vigencia"], items["71 AAA1"]["vigencia_dias"]) == ("vigente", 11)
    assert (items["71 AAA1"]["vigente_desde"], items["71 AAA1"]["vigente_hasta"]) == ("2026-10-20", "2026-10-31")
    assert items["71 AAA1"]["precio_regla"] is None            # solo en la ficha
    assert (items["13 BBB2"]["vigencia"], items["13 BBB2"]["vigencia_dias"]) == (None, None)
    assert "vigencia_aplicada" not in items["71 AAA1"]

    ficha = client.get("/api/precios/71 AAA1").json()
    assert (ficha["vigencia"], ficha["precio_regla"], ficha["precio_final"]) == ("vigente", 17800, 990)


def test_el_precio_de_la_regla_solo_sale_si_el_periodo_esta_vigente(lista, reloj):
    # Sin periodo: la decision rige siempre, no hay "a lo que vuelve".
    guardar(lista, {"precio_fijo": 990})
    assert svc.detalle(lista, "71 AAA1")["precio_regla"] is None

    guardar(lista, {"vigente_hasta": _dias(5)})
    assert svc.detalle(lista, "71 AAA1")["precio_regla"] == 17800

    reloj(_dias(6))
    assert svc.detalle(lista, "71 AAA1")["precio_regla"] is None         # vencida: ya es la regla


def test_el_precio_de_la_regla_ignora_tambien_el_margen_y_el_congelado(lista, reloj):
    guardar(lista, {"margen_fijo": 35, "vigente_hasta": _dias(5)})
    ficha = svc.detalle(lista, "71 AAA1")
    assert (ficha["precio_final"], ficha["precio_regla"]) == (15385, 17800)


# ===================================== 8. la huella de la carga por Excel
@pytest.mark.parametrize("clave", list(HUELLAS_HISTORICAS))
def test_sin_periodo_la_huella_de_decisiones_es_la_de_siempre(clave):
    """Esta huella viaja en la Referencia de cada archivo ya descargado: si cambiara,
    todos aparecerian con conflicto."""
    ov, historica = HUELLAS_HISTORICAS[clave]

    assert carga.huella_decisiones(ov) == historica


def test_con_periodo_la_huella_cambia_y_distingue_desde_de_hasta():
    base = {"precio_fijo": 990.0, "obs": "piso"}
    sin = carga.huella_decisiones(base)
    solo_hasta = carga.huella_decisiones({**base, "vigente_hasta": date(2026, 10, 31)})
    solo_desde = carga.huella_decisiones({**base, "vigente_desde": date(2026, 10, 31)})
    ambos = carga.huella_decisiones({**base, "vigente_desde": date(2026, 10, 1),
                                     "vigente_hasta": date(2026, 10, 31)})
    otro = carga.huella_decisiones({**base, "vigente_desde": date(2026, 10, 1),
                                    "vigente_hasta": date(2026, 11, 30)})

    assert len({sin, solo_hasta, solo_desde, ambos, otro}) == 5


def test_la_huella_no_depende_de_la_fecha_de_hoy(reloj):
    ov = {"precio_fijo": 990.0, "vigente_desde": HOY, "vigente_hasta": _dias(3)}
    antes = carga.huella_decisiones(ov)

    reloj(_dias(30))                  # el periodo vencio

    assert carga.huella_decisiones(ov) == antes


def test_un_precio_que_vence_despues_de_bajar_el_archivo_no_es_un_conflicto(client, lista, reloj):
    """El vencimiento no escribe en `precio_override`: la huella no se mueve de noche."""
    client.put("/api/precios/71 AAA1/override", json={
        "precio_fijo": 990, "vigente_desde": "2026-10-20", "vigente_hasta": "2026-10-25"})
    filas = _bajar(client)
    reloj(_dias(7))                   # vence entre la descarga y la carga
    svc.recalcular(lista, refrescar_insumos=False)
    assert _precio(lista, "71 AAA1").precio_final == 17800

    editado = _a_csv(_editar(filas, "71 AAA1", Obs="nota nueva"))
    v = _subir(client, editado).json()

    assert v["conflictos_total"] == 0 and v["errores_total"] == 0 and v["a_cambiar"] == 1
    r = _subir(client, editado, aplicar=True)
    assert r.status_code == 200 and r.json()["aplicados"] == 1
    ov = _override(lista, "71 AAA1")
    assert (ov.obs, ov.precio_fijo, ov.vigente_hasta) == ("nota nueva", 990, _dias(5))


def test_cambiar_el_periodo_en_la_ficha_despues_de_bajar_el_archivo_si_es_un_conflicto(client, lista, reloj):
    client.put("/api/precios/71 AAA1/override", json={
        "precio_fijo": 990, "vigente_desde": "2026-10-20", "vigente_hasta": "2026-10-25"})
    filas = _bajar(client)
    client.put("/api/precios/71 AAA1/override", json={"vigente_hasta": "2026-11-30"})

    v = _subir(client, _a_csv(_editar(filas, "71 AAA1", Obs="nota nueva"))).json()

    assert v["conflictos_total"] == 1 and v["a_cambiar"] == 0


# ==================================== 9. recalcular: lo de siempre y lo nuevo
def _ids(db, modelo) -> set[str]:
    return {x.id for x in db.query(modelo).all()}


def _nuevas(db, modelo, previas: set[str]) -> list:
    """Las filas que aparecieron desde `previas` (el id es un uuid: no da el orden)."""
    db.expire_all()
    return [x for x in db.query(modelo).all() if x.id not in previas]


def test_recalcular_sin_argumentos_nuevos_deja_lo_mismo_que_siempre(lista):
    _poner(lista, "71 AAA1", precio_fijo=990.0)
    auditorias, notificaciones = _ids(lista, AuditoriaLog), _ids(lista, Notificacion)

    r = svc.recalcular(lista, usuario="ana@curifor.com", refrescar_insumos=False)

    assert r["cambios"] == 1 and r["productos_con_cambios"] == 1
    (a,) = _nuevas(lista, AuditoriaLog, auditorias)
    assert a.accion == "precios_recalculados" and a.usuario_email == "ana@curifor.com"
    assert a.detalle == f"{r['productos']} productos, {r['cambios']} cambios"
    (n,) = _nuevas(lista, Notificacion, notificaciones)
    assert n.tipo == "precios" and n.creado_por_email == "ana@curifor.com"
    assert n.titulo == "Lista de precios recalculada: 1 cambios en 1 productos"


def test_recalcular_por_productos_deja_lo_mismo_que_siempre(lista):
    _poner(lista, "71 AAA1", precio_fijo=990.0)
    auditorias = _ids(lista, AuditoriaLog)

    svc.recalcular(lista, usuario="ana@curifor.com", refrescar_insumos=False, productos=["71 AAA1"])

    (a,) = _nuevas(lista, AuditoriaLog, auditorias)
    assert a.accion == "precios_recalculados"
    assert a.detalle == "1 productos, 1 cambios (solo los afectados por el cambio)"


def test_recalcular_sin_cambios_no_notifica_pero_si_audita(lista):
    auditorias, notificaciones = _ids(lista, AuditoriaLog), _ids(lista, Notificacion)

    r = svc.recalcular(lista, usuario="ana@curifor.com", refrescar_insumos=False)

    assert r["cambios"] == 0
    assert _nuevas(lista, Notificacion, notificaciones) == []
    (a,) = _nuevas(lista, AuditoriaLog, auditorias)
    assert a.accion == "precios_recalculados"


def test_recalcular_acepta_el_nombre_de_la_accion_y_el_titulo_de_la_notificacion(lista):
    _poner(lista, "71 AAA1", precio_fijo=990.0)
    auditorias, notificaciones = _ids(lista, AuditoriaLog), _ids(lista, Notificacion)

    svc.recalcular(lista, usuario="vigencias", refrescar_insumos=False,
                   accion="precios_vigencias", titulo="Vigencias de precios: 1 volvió a la regla")

    (a,) = _nuevas(lista, AuditoriaLog, auditorias)
    (n,) = _nuevas(lista, Notificacion, notificaciones)
    assert a.accion == "precios_vigencias"
    assert n.titulo == "Vigencias de precios: 1 volvió a la regla"


def test_recalcular_recibe_el_hoy_y_lo_usa_en_todas_las_filas(lista, reloj):
    guardar(lista, {"precio_fijo": 990, "vigente_desde": HOY, "vigente_hasta": _dias(10)})

    svc.recalcular(lista, refrescar_insumos=False, hoy=_dias(20))        # el reloj sigue en HOY

    p = _precio(lista, "71 AAA1")
    assert (p.precio_final, p.estado, p.vigencia_aplicada) == (17800, "OK", "vencida")


def test_recalcular_completo_y_por_productos_dan_el_mismo_precio_y_marcador(lista, reloj):
    guardar(lista, {"precio_fijo": 990, "vigente_desde": HOY, "vigente_hasta": _dias(10)})
    reloj(_dias(11))

    svc.recalcular(lista, refrescar_insumos=False, productos=["71 AAA1"])
    por_productos = (_precio(lista, "71 AAA1").precio_final, _precio(lista, "71 AAA1").vigencia_aplicada)
    svc.recalcular(lista, refrescar_insumos=False)
    completo = (_precio(lista, "71 AAA1").precio_final, _precio(lista, "71 AAA1").vigencia_aplicada)

    assert por_productos == completo == (17800, "vencida")


def test_el_vencimiento_deja_una_fila_de_historial_solo_si_el_precio_cambio(lista, reloj):
    from src.models import PrecioCambio

    # Un fijo igual a la regla: al vencer el precio no cambia, no hay nada que revisar.
    guardar(lista, {"precio_fijo": 17800, "vigente_hasta": _dias(2)})
    filas = lista.query(PrecioCambio).count()
    reloj(_dias(3))
    svc.recalcular(lista, refrescar_insumos=False)
    assert lista.query(PrecioCambio).count() == filas
    assert _precio(lista, "71 AAA1").vigencia_aplicada == "vencida"       # el marcador si cambio

    # Un fijo distinto: al vencer, una fila 'precio'.
    reloj(HOY)
    guardar(lista, {"precio_fijo": 990, "vigente_hasta": _dias(2)})
    svc.recalcular(lista, refrescar_insumos=False)
    filas = lista.query(PrecioCambio).filter_by(producto="71 AAA1", campo="precio").count()
    reloj(_dias(3))
    svc.recalcular(lista, refrescar_insumos=False)
    nuevas = (lista.query(PrecioCambio).filter_by(producto="71 AAA1", campo="precio")
              .order_by(PrecioCambio.id.desc()).all())
    assert len(nuevas) == filas + 1 and (nuevas[0].antes, nuevas[0].despues) == ("990", "17800")


# ============================== 10. la politica y las decisiones que ya no rigen
def test_una_decision_vencida_no_cuenta_como_decidida_para_la_politica(lista, reloj):
    rubros = [{"rubro": "71", "tipo": "Pesado", "procedencia_forzada": None}]

    def decididos():
        vp = svc.vista_previa_politica(lista, [], rubros)
        return next(r for r in vp["rubros"] if r["rubro"] == "71")["decididos"]

    # 71 CCC3 esta congelado sin periodo: la persona decidio, la politica no lo mueve.
    assert decididos() == 1
    _poner(lista, "71 CCC3", vigente_desde=_dias(-9), vigente_hasta=_dias(9))
    assert decididos() == 1                                              # vigente
    _poner(lista, "71 CCC3", vigente_desde=_dias(-9), vigente_hasta=_dias(-1))
    assert decididos() == 0                                              # vencida
    _poner(lista, "71 CCC3", vigente_desde=_dias(2), vigente_hasta=None)
    assert decididos() == 0                                              # programada


def test_la_vista_previa_de_la_politica_calcula_los_precios_con_el_periodo(lista, reloj):
    """Un fijo vencido ya no frena el cambio de factor: el precio que se mostraba como
    'no cambia' (990) en realidad ya era la regla."""
    guardar(lista, {"precio_fijo": 990, "vigente_hasta": _dias(2)})
    factores = [{"tipo": "Liviano", "procedencia": "Nacional", "factor": 2.0}]

    vigente = svc.vista_previa_politica(lista, factores, [])
    reloj(_dias(5))
    vencido = svc.vista_previa_politica(lista, factores, [])

    assert vigente["cambian"] == 0
    assert vencido["cambian"] == 1 and vencido["suben"] == 1


# ===================================== 11. los datos: columnas y modelo
def test_las_fechas_se_guardan_como_fecha_y_se_leen_como_fecha(lista):
    _poner(lista, "71 AAA1", precio_fijo=990.0, vigente_desde=date(2026, 11, 1), vigente_hasta=date(2026, 11, 30))

    ov = svc._overrides(lista, ["71 AAA1"])["71 AAA1"]

    assert (ov["vigente_desde"], ov["vigente_hasta"]) == (date(2026, 11, 1), date(2026, 11, 30))
    assert type(ov["vigente_desde"]) is date


def test_el_marcador_arranca_vacio_en_toda_la_lista(lista):
    assert all(p.vigencia_aplicada is None for p in lista.query(PrecioProducto).all())
