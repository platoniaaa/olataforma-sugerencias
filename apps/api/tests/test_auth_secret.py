"""El AUTH_SECRET nunca queda en la clave publica del repo (hallazgo C-1)."""
import base64
import hashlib
import hmac
import json
import time

from src.config import Settings, _AUTH_SECRET_INSEGURO
from src.services import auth


def test_sin_variable_usa_una_clave_aleatoria(monkeypatch):
    monkeypatch.delenv("AUTH_SECRET", raising=False)
    s = Settings(_env_file=None)
    assert s.auth_secret != _AUTH_SECRET_INSEGURO
    assert len(s.auth_secret) >= 40


def test_respeta_el_auth_secret_configurado(monkeypatch):
    monkeypatch.setenv("AUTH_SECRET", "clave-estable-larga-de-produccion-2026")
    s = Settings(_env_file=None)
    assert s.auth_secret == "clave-estable-larga-de-produccion-2026"


def test_token_forjado_con_la_clave_publica_se_rechaza():
    """Reproduce el ataque de la auditoria: firmar un token de admin con la clave
    publica del repo. Con el blindaje, la app firma con otra clave -> se rechaza."""
    def b64(d: bytes) -> str:
        return base64.urlsafe_b64encode(d).decode().rstrip("=")

    payload = b64(json.dumps({"sub": "admin@curifor.com", "exp": int(time.time()) + 600}).encode())
    sig = b64(hmac.new(_AUTH_SECRET_INSEGURO.encode(), payload.encode(), hashlib.sha256).digest())
    forjado = f"{payload}.{sig}"

    # La app no esta firmando con la clave publica (el conftest no define AUTH_SECRET),
    # asi que el token forjado no valida.
    assert auth.settings.auth_secret != _AUTH_SECRET_INSEGURO
    assert auth.verificar_token(forjado) is None
