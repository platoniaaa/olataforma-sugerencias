# -*- coding: utf-8 -*-
"""Pone (o cambia) la contraseña de un usuario de la plataforma.

La plataforma guarda las contraseñas con PBKDF2, asi que la original NO se puede
recuperar de la base: cuando alguien no la tiene, el unico camino es ponerle una
nueva. Y no hay pantalla para hacerlo, solo el endpoint de admin.

Este script existe para que esa clave la escriba una persona en su propio
teclado: se pide oculta, viaja al endpoint y no se imprime, no se guarda en un
archivo ni queda en el historial del shell.

    python scripts/clave_usuario.py hgarcia@curifor.com

Las credenciales de admin salen del .env del motor (PLATAFORMA_*), que es el
mismo que ya usan los scripts de precios.
"""
import getpass
import json
import os
import ssl
import sys
import urllib.error
import urllib.request

ENV_MOTOR = r"C:\Users\icalderon\dev\Sugerencia-SaaS-para-sucursales\.env"
LARGO_MINIMO = 4  # el que valida el backend (routers/usuarios.py)


def contexto_tls() -> ssl.SSLContext:
    """La red de Curifor hace inspeccion TLS: sin truststore, Python no valida el
    certificado del proxy y todo falla con CERTIFICATE_VERIFY_FAILED. truststore
    valida contra el almacen de Windows, que si lo conoce."""
    try:
        import truststore

        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        return ssl.create_default_context()


def leer_env(ruta: str) -> dict:
    datos = {}
    with open(ruta, encoding="utf-8") as f:
        for linea in f:
            if "=" in linea and not linea.strip().startswith("#"):
                k, _, v = linea.partition("=")
                datos[k.strip()] = v.strip().strip('"')
    return datos


def pedir(url: str, cuerpo: dict, ctx, token: str | None = None) -> dict:
    req = urllib.request.Request(url, data=json.dumps(cuerpo).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=180, context=ctx) as r:
        return json.load(r)


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    correo = sys.argv[1].strip().lower()

    env = leer_env(os.environ.get("MOTOR_ENV", ENV_MOTOR))
    base = env["PLATAFORMA_API_URL"].rstrip("/")
    ctx = contexto_tls()

    print(f"Vas a poner una contraseña nueva para {correo} en {base}.")
    print("No se muestra al escribirla y no queda guardada en ninguna parte.")
    clave = getpass.getpass("Contraseña nueva: ")
    if len(clave) < LARGO_MINIMO:
        print(f"Muy corta: el minimo son {LARGO_MINIMO} caracteres.")
        return 1
    if clave != getpass.getpass("Reescribela para confirmar: "):
        print("No coinciden. No se cambio nada.")
        return 1

    try:
        token = pedir(f"{base}/api/auth/login",
                      {"email": env["PLATAFORMA_EMAIL"], "password": env["PLATAFORMA_PASSWORD"]},
                      ctx)["token"]
        # Solo se manda la clave: los demas campos en None dejan al usuario como
        # esta (permisos, nombre, activo). Ver UsuarioCrear.
        out = pedir(f"{base}/api/admin/usuarios", {"email": correo, "password": clave}, ctx, token)
    except urllib.error.HTTPError as e:
        print(f"La plataforma respondio {e.code}: {e.read()[:300].decode(errors='replace')}")
        return 1
    finally:
        del clave

    print(f"Listo: {out['email']} ({out.get('nombre') or 'sin nombre'}) ya puede entrar. "
          f"admin={out.get('es_admin')} activo={out.get('activo')}")
    print("Pasasela por un medio que no sea el correo del aviso (interno, en persona).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
