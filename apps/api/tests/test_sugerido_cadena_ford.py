"""La cadena de reemplazos y su fecha llegan al sugerido.

Hasta ago-2026 la grilla solo mostraba `Reemplazado por (FORD)`: el ultimo salto.
La cadena completa vivia en la tabla `reemplazo_ford` y no llegaba a ninguna
pantalla, asi que no habia forma de ver el historico del codigo.

Y la fecha de extraccion no viajaba en absoluto. Eso importa desde que la
consulta al portal es semanal y automatica: si la corrida del lunes falla —la
sesion de FORD vence y pide MFA, que lo tiene que poner una persona— la
plataforma sigue mostrando lo de la semana pasada con la misma cara de siempre.
"""
import pytest

from src.models import ReemplazoFord
from src.services import sugerido_service


@pytest.fixture()
def con_reemplazo(db_session):
    db_session.add(ReemplazoFord(
        tenant_id="curifor", producto="19 MB3Z19N619A",
        reemplazado_por=None, reemplazado_por_ford=None,
        cadena="MB3Z/19N619/C/ > MB3Z/19N619/A/",
        reemplaza_a="25 MB3Z19N619C",
        sucesor_confirmado=True, agrupado=True,
        extraido_en="2026-08-22 16:17:53",
    ))
    db_session.commit()
    return db_session


def test_la_cadena_llega_a_la_fila_del_sugerido(con_reemplazo):
    items = [{"producto": "19 MB3Z19N619A"}]

    sugerido_service._agregar_reemplazo_ford(items, con_reemplazo)

    assert items[0]["cadena_ford"] == "MB3Z/19N619/C/ > MB3Z/19N619/A/"


def test_la_fecha_de_consulta_llega_a_la_fila(con_reemplazo):
    items = [{"producto": "19 MB3Z19N619A"}]

    sugerido_service._agregar_reemplazo_ford(items, con_reemplazo)

    assert items[0]["reemplazo_extraido_en"] == "2026-08-22 16:17:53"


def test_un_codigo_sin_reemplazo_queda_en_blanco(con_reemplazo):
    """No se inventa nada: en blanco significa "FORD no dice nada de este"."""
    items = [{"producto": "17 GK2Z9601B"}]

    sugerido_service._agregar_reemplazo_ford(items, con_reemplazo)

    assert items[0]["cadena_ford"] is None
    assert items[0]["reemplazo_extraido_en"] is None


def test_cada_fila_conserva_la_fecha_de_SU_archivo(db_session):
    """El motor combina dos archivos y cada uno se extrae por su lado.

    Al 22-08-2026 la lista de FORD era del 5 al 7 de agosto y la de los codigos
    de Curifor de ese mismo dia: 15 dias de diferencia en la misma tabla. Por eso
    la fecha va por fila y no como un valor global — uno solo mentiria sobre la
    mitad.
    """
    db_session.add_all([
        ReemplazoFord(tenant_id="curifor", producto="19 VIEJO",
                      reemplazado_por="19 NUEVO", cadena="A/1/ > B/2/",
                      sucesor_confirmado=True, agrupado=True,
                      extraido_en="2026-08-05 23:20:26"),
        ReemplazoFord(tenant_id="curifor", producto="19 RECIENTE",
                      reemplazado_por="19 OTRO", cadena="C/3/ > D/4/",
                      sucesor_confirmado=True, agrupado=True,
                      extraido_en="2026-08-22 18:24:47"),
    ])
    db_session.commit()
    items = [{"producto": "19 VIEJO"}, {"producto": "19 RECIENTE"}]

    sugerido_service._agregar_reemplazo_ford(items, db_session)

    assert items[0]["reemplazo_extraido_en"].startswith("2026-08-05")
    assert items[1]["reemplazo_extraido_en"].startswith("2026-08-22")


def test_sin_fecha_no_revienta(db_session):
    """Las filas cargadas antes de que la fecha existiera la tienen en null."""
    db_session.add(ReemplazoFord(
        tenant_id="curifor", producto="19 ANTIGUO",
        reemplazado_por="19 NUEVO", cadena="A/1/ > B/2/",
        sucesor_confirmado=True, agrupado=True, extraido_en=None,
    ))
    db_session.commit()
    items = [{"producto": "19 ANTIGUO"}]

    sugerido_service._agregar_reemplazo_ford(items, db_session)

    assert items[0]["cadena_ford"] == "A/1/ > B/2/"
    assert items[0]["reemplazo_extraido_en"] is None
