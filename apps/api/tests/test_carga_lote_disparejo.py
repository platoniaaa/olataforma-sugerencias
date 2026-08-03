"""La carga no puede morir porque a una fila le falte una columna.

El 31-jul-2026 la tarea diaria empezo a fallar con un 500 sin detalle y estuvo
rota hasta el 03-ago. Causa: `nivel_maximo.aplicar` escribia la clave
`nivel_maximo` solo en las filas con demanda. El insert de la carga es
multi-fila (un unico VALUES por lote de 500), y SQLAlchemy aborta con
CompileError si los dicts del lote no traen las mismas claves.

Se cubre por los dos lados: que el servicio escriba siempre la clave, y que la
carga nivele el lote igual, para que el proximo servicio que enriquezca solo
algunas filas no vuelva a voltear la carga entera.
"""
from sqlalchemy import func, select

from src.models import Sugerido
from src.services import excel_loader, nivel_maximo

CONFIG = {"reponer_a_maximo": True, "clases_que_reponen": "AB",
          "ciclo_orden_dias": 5, "ciclo_orden_dias_cd": 5}


def test_nivel_maximo_escribe_la_clave_en_todas_las_filas():
    filas = [
        # Con demanda: recibe un nivel.
        {"producto": "A-1", "sucursal_id": "LINDEROS", "clasificacion_abc": "A",
         "demanda_diaria": 0.5, "lt_efectivo": 3, "stock_seguridad": 1,
         "total_sugerido_suc": 0, "stock_activo_suc": 0, "stock_en_transito_suc": 0},
        # SIN demanda: no hay nivel que mantener, pero la clave tiene que estar.
        {"producto": "A-2", "sucursal_id": "LINDEROS", "clasificacion_abc": "A",
         "demanda_diaria": 0, "lt_efectivo": 3, "stock_seguridad": 0,
         "total_sugerido_suc": 0, "stock_activo_suc": 0, "stock_en_transito_suc": 0},
    ]
    nivel_maximo.aplicar(filas, CONFIG)
    assert all("nivel_maximo" in f for f in filas), "una fila quedo sin la clave"
    assert filas[0]["nivel_maximo"] is not None
    assert filas[1]["nivel_maximo"] is None


def test_la_carga_soporta_un_lote_con_claves_dispares(db_session):
    """Guardarrail: aunque un servicio deje el lote disparejo, la carga entra."""
    filas = [
        {"tenant_id": "curifor", "producto": "LOTE-1", "sucursal_id": "LINDEROS",
         "nivel_maximo": 3, "total_sugerido_suc": 1.0},
        # A esta le falta `nivel_maximo` a proposito.
        {"tenant_id": "curifor", "producto": "LOTE-2", "sucursal_id": "LINDEROS",
         "total_sugerido_suc": 2.0},
    ]
    # Se usa el mismo helper que la carga real.
    from sqlalchemy import insert

    claves = set().union(*(r.keys() for r in filas))
    lote = [{k: r.get(k) for k in claves} for r in filas]
    db_session.execute(insert(Sugerido).values(lote))
    db_session.commit()

    n = db_session.scalar(
        select(func.count()).select_from(Sugerido).where(Sugerido.producto.like("LOTE-%"))
    )
    assert n == 2


def test_carga_completa_con_filas_sin_demanda(client, db_session):
    """El caso real: un CSV donde conviven filas con y sin demanda."""
    csv = (
        "Producto,SucursalID,Nombre Sucursal,Clasificacion ABC,Demanda Diaria,"
        "LT Efectivo,Stock de Seguridad,total_sugerido_suc,stock_activo_suc,Pedir\n"
        "CSV-1,LINDEROS,Linderos,A,0.5,3,1,0,0,No\n"
        "CSV-2,LINDEROS,Linderos,A,0,3,0,0,0,No\n"
        "CSV-3,LINDEROS,Linderos,D,0.2,3,0,0,0,No\n"
    )
    r = client.post(
        "/api/admin/cargar-sugerido",
        files={"file": ("sugerido.csv", csv.encode("utf-8"), "text/csv")},
    )
    assert r.status_code == 200, r.text
    assert r.json()["filas_cargadas"] == 3
