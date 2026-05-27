"""Entry serverless de Vercel (estructura canonica: app en api/index.py).

Vercel instala requirements.txt (raiz del proyecto) y empaqueta el proyecto; aqui
agregamos la raiz al path para poder importar el paquete `src`.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.main import app  # noqa: E402

__all__ = ["app"]
