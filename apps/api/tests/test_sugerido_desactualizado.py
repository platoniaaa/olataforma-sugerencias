"""Avisar cuando el sugerido quedo viejo.

Del 31-jul al 03-ago-2026 la tarea diaria fallo dos dias habiles seguidos con un
500 y nadie se entero: el unico rastro era "RESULTADO: FALLO" en un log local. El
equipo siguio comprando sobre la foto del 30-jul. El aviso se calcula en el
servidor para que NO dependa de que el job que fallo alcance a avisar.

Se cuenta en dias HABILES: contando horas, todos los lunes avisaria que los datos
son de hace 3 dias cuando la corrida del viernes fue la que correspondia.
"""
from datetime import date, datetime, timedelta, timezone

import pytest

from src.models import AuditoriaLog
from src.routers.auditoria import _dias_habiles_entre


@pytest.mark.parametrize("desde,hasta,esperado", [
    # 2026-08-03 es lunes.
    (date(2026, 8, 3), date(2026, 8, 3), 0),   # mismo dia
    (date(2026, 8, 3), date(2026, 8, 4), 1),   # lunes -> martes
    (date(2026, 7, 31), date(2026, 8, 3), 1),  # viernes -> lunes: NO avisa
    (date(2026, 7, 30), date(2026, 8, 3), 2),  # jueves -> lunes: se perdio el viernes
    (date(2026, 8, 1), date(2026, 8, 3), 1),   # sabado -> lunes
    (date(2026, 7, 27), date(2026, 8, 3), 5),  # una semana
])
def test_cuenta_dias_habiles(desde, hasta, esperado):
    assert _dias_habiles_entre(desde, hasta) == esperado


def _sincronizacion(db_session, hace_dias: int):
    db_session.add(AuditoriaLog(
        tenant_id="curifor", accion="datos_sincronizados", entidad="sugerido",
        detalle="Sugerido cargado: 100 filas",
        creado_en=datetime.now(timezone.utc) - timedelta(days=hace_dias),
    ))
    db_session.commit()


def test_carga_de_hoy_no_avisa(client, db_session):
    _sincronizacion(db_session, 0)
    r = client.get("/api/ultima-sincronizacion").json()
    assert r["desactualizado"] is False
    assert r["dias_habiles"] == 0


def test_sin_ninguna_carga_no_inventa_un_aviso(client, db_session):
    r = client.get("/api/ultima-sincronizacion").json()
    assert r["creado_en"] is None
    assert r["desactualizado"] is False


def test_una_semana_sin_cargar_avisa(client, db_session):
    _sincronizacion(db_session, 7)
    r = client.get("/api/ultima-sincronizacion").json()
    assert r["desactualizado"] is True
    assert r["dias_habiles"] >= 2
