"""Un error interno responde JSON con CORS, no un 500 mudo.

Starlette arma el 500 de una excepcion sin atajar por fuera del middleware de CORS:
la respuesta no trae `Access-Control-Allow-Origin` y el navegador la esconde. La
persona veia "Failed to fetch", igual que si se hubiera caido la red, y no habia
forma de distinguir una falla del servidor de un corte (09-10-2026, descarga de
"Solo diferencias").
"""
import pytest
from fastapi.testclient import TestClient

from src.config import get_settings
from src.main import app
from src.services import precios_service


@pytest.fixture
def cae(monkeypatch):
    def _falla(*a, **k):
        raise RuntimeError("se cayo la base")

    monkeypatch.setattr(precios_service, "exportar", _falla)


def _pedir(origen):
    # Sin relanzar la excepcion: se prueba lo que recibe el navegador.
    return TestClient(app, raise_server_exceptions=False).get(
        "/api/precios/exportar", headers={"Origin": origen}
    )


def test_el_error_interno_responde_json_y_con_cors(client, cae):
    origen = get_settings().cors_origins_list[0]
    r = _pedir(origen)
    assert r.status_code == 500
    assert r.json()["detail"].startswith("El servidor tuvo un error")
    assert r.headers["access-control-allow-origin"] in (origen, "*")


def test_a_un_origen_ajeno_no_se_le_abre_el_cors(client, cae):
    if "*" in get_settings().cors_origins_list:
        pytest.skip("CORS abierto a cualquier origen")
    r = _pedir("https://sitio-ajeno.example")
    assert r.status_code == 500
    assert "access-control-allow-origin" not in r.headers


def test_un_pedido_normal_no_cambia(client):
    assert client.get("/api/health").status_code == 200
