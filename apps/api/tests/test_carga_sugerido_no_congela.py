"""La carga diaria del sugerido no puede dejar tomada la API entera.

Hasta el 19-10 `cargar_sugerido` y `comparar_motor` eran `async def` con trabajo
sincrono adentro: corrian dentro del loop de eventos y, mientras duraba la carga
(~6 minutos en Render, todos los dias hacia las 09:43), no respondia ninguna otra
ruta, ni siquiera /api/health. Pasadas a `def`, FastAPI las corre en su pool de
hilos. Eso abre otra puerta, que se cierra con un candado: dos cargas encimadas
(el reintento del motor sobre una carga que sigue en curso) borrarian e insertarian
en paralelo y dejarian el sugerido con las filas dobles.
"""
import inspect
import threading
import time

from sqlalchemy import func, select

from src.models import Sugerido
from src.routers import admin
from src.services import excel_loader


def test_las_cargas_pesadas_no_son_corrutinas():
    assert not inspect.iscoroutinefunction(admin.cargar_sugerido)
    assert not inspect.iscoroutinefunction(admin.comparar_motor)


def test_health_responde_mientras_corre_una_carga(client, monkeypatch):
    """Una carga lenta en curso y, mientras tanto, /api/health tiene que contestar
    al tiro. Con la version `async def` el health esperaba a que la carga soltara el
    loop: aca eso se ve como un health que tarda lo mismo que la carga (5 s)."""
    en_curso = threading.Event()
    soltar = threading.Event()

    def _carga_lenta(db, filename, content):
        en_curso.set()
        soltar.wait(timeout=5)
        return {"filas_cargadas": 1}

    monkeypatch.setattr(excel_loader, "cargar_sugerido", _carga_lenta)
    respuesta: dict = {}

    def _subir():
        respuesta["carga"] = client.post(
            "/api/admin/cargar-sugerido",
            files={"file": ("sugerido.csv", b"Producto,SucursalID\nX,LINDEROS\n", "text/csv")},
        )

    hilo = threading.Thread(target=_subir)
    hilo.start()
    try:
        assert en_curso.wait(timeout=5), "la carga nunca empezo"
        t0 = time.perf_counter()
        r = client.get("/api/health")
        demora = time.perf_counter() - t0
        assert r.status_code == 200
        assert not soltar.is_set()
        assert demora < 2, f"/api/health espero {demora:.1f} s a que terminara la carga"
    finally:
        soltar.set()
        hilo.join(timeout=10)
    assert respuesta["carga"].status_code == 200


def test_dos_cargas_encimadas_van_en_fila(monkeypatch):
    """Mientras una carga tiene el candado, la otra no empieza a reemplazar."""
    entradas: list[str] = []

    def _persistir(db, filas, detectadas, ignoradas):
        entradas.append("entro")
        return {}

    monkeypatch.setattr(excel_loader, "_persistir_filas", _persistir)
    excel_loader.CARGA_SUGERIDO.acquire()
    try:
        hilo = threading.Thread(target=excel_loader.persistir_filas, args=(None, [], [], []))
        hilo.start()
        time.sleep(0.3)
        assert entradas == [], "la segunda carga reemplazo sin esperar a la primera"
    finally:
        excel_loader.CARGA_SUGERIDO.release()
    hilo.join(timeout=5)
    assert entradas == ["entro"]


def test_el_insert_en_lote_respeta_el_tope_de_parametros(db_session):
    """1.000 filas con todas las columnas del sugerido son ~83 mil parametros, mas
    del doble de lo que acepta SQLite en una sentencia. Tiene que entrar igual (el
    helper arma los lotes) y con los valores en su lugar."""
    columnas = [
        c.name for c in Sugerido.__table__.columns if c.name not in ("id", "tenant_id")
    ]
    filas = []
    for i in range(1000):
        fila = {c: None for c in columnas}
        fila.update({
            "tenant_id": "curifor", "producto": f"LOTE-{i:04d}", "sucursal_id": "LINDEROS",
            "total_sugerido_suc": float(i), "descripcion": f"Repuesto {i}",
        })
        filas.append(fila)
    assert len(filas) * len(filas[0]) > 32_766

    excel_loader._insertar_en_lote(db_session, Sugerido, filas)
    db_session.commit()

    base = select(Sugerido).where(Sugerido.producto.like("LOTE-%")).subquery()
    assert db_session.scalar(select(func.count()).select_from(base)) == 1000
    assert db_session.scalar(select(func.sum(base.c.total_sugerido_suc))) == sum(range(1000))
    fila = db_session.scalars(
        select(Sugerido).where(Sugerido.producto == "LOTE-0777")
    ).one()
    assert fila.descripcion == "Repuesto 777"
    assert fila.total_sugerido_suc == 777
