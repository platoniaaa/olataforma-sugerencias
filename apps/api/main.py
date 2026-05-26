"""Punto de entrada para Vercel (preset FastAPI).

Vercel detecta la app FastAPI en `main.py` de la raiz del proyecto (apps/api) y
enruta todas las peticiones hacia ella. El codigo real vive en `src/`.
"""
from src.main import app

__all__ = ["app"]
