"""La carga del sugerido y las descargas grandes no corren a la vez.

Render (plan free) reinicia el proceso si pasa los 512 MB. Medido el 19-10 con el CSV
real del motor (18.252 filas) en Postgres 16: la carga sola sube el proceso +241 MB,
el Excel de la grilla completa +132 MB, y la carga con ese Excel pedido 8 s despues
llego a 534 MB. Mientras la carga era `async def` no podian coincidir (tomaba el loop);
en el pool de hilos si. Ahora la descarga espera a que la carga termine y, si tarda
demasiado, responde 503 con un motivo que se puede mostrar tal cual.
"""
import threading
import time

from src.services import excel_loader, operacion_pesada

CSV = b"Producto,SucursalID\nX,LINDEROS\n"


def _carga_bloqueada(monkeypatch):
    """Reemplaza la carga por una que se queda adentro hasta que se le avise."""
    en_curso = threading.Event()
    soltar = threading.Event()

    def _carga_lenta(db, filename, content):
        en_curso.set()
        soltar.wait(timeout=10)
        return {"filas_cargadas": 1}

    monkeypatch.setattr(excel_loader, "cargar_sugerido", _carga_lenta)
    return en_curso, soltar


def _en_hilo(respuestas: dict, clave: str, fn) -> threading.Thread:
    hilo = threading.Thread(target=lambda: respuestas.__setitem__(clave, fn()))
    hilo.start()
    return hilo


def test_el_excel_pedido_durante_la_carga_espera_a_que_termine(client, monkeypatch):
    en_curso, soltar = _carga_bloqueada(monkeypatch)
    resp: dict = {}
    carga = _en_hilo(resp, "carga", lambda: client.post(
        "/api/admin/cargar-sugerido", files={"file": ("s.csv", CSV, "text/csv")}
    ))
    try:
        assert en_curso.wait(timeout=5), "la carga nunca empezo"
        excel = _en_hilo(resp, "excel", lambda: client.post(
            "/api/sugerido/export-excel", json={"filtros": {"solo_pedir": False}}
        ))
        time.sleep(1.5)
        assert "excel" not in resp, "el Excel se armo mientras la carga seguia en memoria"
    finally:
        soltar.set()
        carga.join(timeout=10)
    excel.join(timeout=10)
    assert resp["carga"].status_code == 200
    assert resp["excel"].status_code == 200


def test_si_la_carga_tarda_la_descarga_responde_503_con_el_motivo(client, monkeypatch):
    monkeypatch.setattr(operacion_pesada, "ESPERA_DESCARGA_S", 0.2)
    en_curso, soltar = _carga_bloqueada(monkeypatch)
    resp: dict = {}
    carga = _en_hilo(resp, "carga", lambda: client.post(
        "/api/admin/cargar-sugerido", files={"file": ("s.csv", CSV, "text/csv")}
    ))
    try:
        assert en_curso.wait(timeout=5), "la carga nunca empezo"
        excel = client.post("/api/sugerido/export-excel", json={"filtros": {}})
        precios = client.get("/api/precios/exportar", params={"formato": "completa"})
    finally:
        soltar.set()
        carga.join(timeout=10)
    motivo = "Se está cargando el sugerido del día; intenta en un minuto."
    assert excel.status_code == 503
    assert excel.json()["detail"] == motivo
    assert precios.status_code == 503
    assert precios.json()["detail"] == motivo
    assert resp["carga"].status_code == 200
    # Terminada la carga, la descarga vuelve a funcionar.
    assert client.post("/api/sugerido/export-excel", json={"filtros": {}}).status_code == 200


def test_dos_descargas_grandes_van_en_fila_y_el_503_dice_cual(client, monkeypatch):
    monkeypatch.setattr(operacion_pesada, "ESPERA_DESCARGA_S", 0.2)
    with operacion_pesada.descarga_pesada():
        r = client.post("/api/sugerido/export-excel", json={"filtros": {}})
    assert r.status_code == 503
    assert r.json()["detail"] == "Hay otra descarga grande en curso; intenta en un minuto."
    assert client.post("/api/sugerido/export-excel", json={"filtros": {}}).status_code == 200


def test_una_carga_que_falla_suelta_el_turno(client, monkeypatch):
    """Un archivo malo (400) no puede dejar tomadas las descargas para siempre."""
    monkeypatch.setattr(operacion_pesada, "ESPERA_DESCARGA_S", 0.2)
    r = client.post(
        "/api/admin/cargar-sugerido", files={"file": ("s.txt", b"nada", "text/plain")}
    )
    assert r.status_code == 400
    assert client.post("/api/sugerido/export-excel", json={"filtros": {}}).status_code == 200
