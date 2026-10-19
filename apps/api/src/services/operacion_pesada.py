"""Una operacion pesada a la vez: la carga diaria del sugerido y las descargas grandes.

Render (plan free, render.yaml) reinicia el proceso si pasa los 512 MB. Medido el 19-10
con el CSV real del motor (18.252 filas) en Postgres 16 local:

- la carga sola sube el proceso +241 MB;
- el Excel de la grilla completa, +132 MB; las exportaciones de precios, +190 a +230;
- la carga con ese Excel pedido 8 s despues: de 138 a 534 MB.

Mientras `cargar_sugerido` era `async def` no podian coincidir: la carga tomaba el loop
y el pedido esperaba. En el pool de hilos si coinciden, y un reinicio a mitad de carga
la deshace, corta la descarga y cierra la sesion de todos.

Este semaforo las pone en fila. La carga espera lo que haga falta (una descarga termina
en segundos). Una descarga espera hasta `ESPERA_DESCARGA_S` y, si no le toca, responde
503 con un motivo que se muestra tal cual. La API corre en un solo proceso, asi que un
semaforo del proceso alcanza. No es reentrante: se toma una sola vez, en el endpoint.
"""
import threading
from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import HTTPException

_SEMAFORO = threading.BoundedSemaphore(1)

CARGA = "carga"
DESCARGA = "descarga"
# Quien tiene el turno ahora: para que el 503 diga lo que de verdad pasa.
_turno: dict[str, str | None] = {"de": None}

# La carga tarda alrededor de un minuto en Render; una descarga, segundos.
ESPERA_DESCARGA_S = 60.0

MOTIVO_503 = {
    CARGA: "Se está cargando el sugerido del día; intenta en un minuto.",
    DESCARGA: "Hay otra descarga grande en curso; intenta en un minuto.",
}
MOTIVO_503_GENERICO = "La plataforma está ocupada con otra operación grande; intenta en un minuto."


@contextmanager
def _con_turno(quien: str) -> Iterator[None]:
    _turno["de"] = quien
    try:
        yield
    finally:
        _turno["de"] = None
        _SEMAFORO.release()


@contextmanager
def carga_del_sugerido() -> Iterator[None]:
    """La carga del sugerido: espera su turno sin plazo."""
    _SEMAFORO.acquire()
    with _con_turno(CARGA):
        yield


@contextmanager
def descarga_pesada() -> Iterator[None]:
    """Una descarga grande (Excel de la grilla, exportaciones de precios)."""
    if not _SEMAFORO.acquire(timeout=ESPERA_DESCARGA_S):
        quien = _turno["de"]
        raise HTTPException(
            status_code=503, detail=MOTIVO_503.get(quien or "", MOTIVO_503_GENERICO)
        )
    with _con_turno(DESCARGA):
        yield
