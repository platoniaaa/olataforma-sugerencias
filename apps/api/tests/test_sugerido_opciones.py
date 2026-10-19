"""GET /api/sugerido/opciones: los valores distintos para los desplegables.

La portada armaba la lista de proveedores del modal de sugerencia manual bajando las
primeras 5.000 filas del sugerido (12,5 MB en produccion, 9 a 17 s) y le faltaban
57 de 142 proveedores: los que solo tienen filas en cero quedaban despues del corte.
"""
import json

from src.main import app
from src.models import Sugerido, Usuario
from src.services.auth import requiere_auth


def _fila(producto, sucursal, proveedor, **extra):
    base = dict(
        tenant_id="curifor", producto=producto, sucursal_id=sucursal,
        nombre_sucursal=sucursal.title(), proveedor=proveedor, pedir="No",
        pedir_flag="No", total_sugerido_suc=0,
    )
    return Sugerido(**{**base, **extra})


def test_trae_todos_los_proveedores_aunque_no_pidan_nada(client, db_session):
    # 5.000 filas en cero de un proveedor grande y DESPUES 10 de uno chico, tambien en
    # cero. Las primeras 5.000 (por total sugerido y luego por id) no llegan al chico.
    db_session.add(_fila("30 GRANDE", "CURICO", "PROVEEDOR GRANDE",
                         total_sugerido_suc=50, pedir="Si", filtro1_final="GILDEMEISTER",
                         tipo_origen="Nacional", clasificacion_abc="B"))
    db_session.add_all(
        _fila(f"30 GRANDE{i:05d}", "CURICO", "PROVEEDOR GRANDE") for i in range(5000)
    )
    db_session.add_all(
        _fila(f"30 CHICO{i:02d}", "TALCA", "PROVEEDOR CHICO") for i in range(10)
    )
    db_session.commit()
    viejo = client.get("/api/sugerido", params={"solo_pedir": "false", "limit": 5000}).json()
    assert "PROVEEDOR CHICO" not in {f["proveedor"] for f in viejo["items"]}

    r = client.get("/api/sugerido/opciones")
    assert r.status_code == 200
    op = r.json()
    assert op["proveedores"] == [
        "Ford Motor Company Chile", "PROVEEDOR CHICO", "PROVEEDOR GRANDE",
    ]
    assert op["marcas"] == ["FORD", "GILDEMEISTER"]
    assert op["tipos_origen"] == ["Importado", "Nacional"]
    assert op["clases_abc"] == ["A", "B"]
    assert op["sucursales"] == [
        {"sucursal_id": "CURICO", "nombre": "Curico"},
        {"sucursal_id": "LINDEROS", "nombre": "Linderos"},
        {"sucursal_id": "TALCA", "nombre": "Talca"},
    ]
    # Unos cientos de bytes, no megas.
    assert len(r.content) < 2_000


def test_deja_fuera_lo_que_la_plataforma_no_muestra(client, db_session):
    db_session.add_all([
        _fila("40 VACIO", "TALCA", ""),
        _fila("40 NULO", "TALCA", None),
        # Sucursal cerrada: no existe para la plataforma.
        _fila("40 CERRADA", "DIEZ DE JULIO", "SOLO EN LA CERRADA"),
        # Producto interno.
        _fila("D&P REPTO-TALLER", "TALCA", "SOLO INTERNO"),
    ])
    db_session.commit()
    op = client.get("/api/sugerido/opciones").json()
    assert op["proveedores"] == ["Ford Motor Company Chile"]
    assert "DIEZ DE JULIO" not in {s["sucursal_id"] for s in op["sucursales"]}


def test_respeta_las_sucursales_del_usuario(client, db_session):
    db_session.add(_fila("50 CURICO", "CURICO", "SOLO CURICO"))
    usuario = db_session.get(Usuario, "noadmin@curifor.com")
    usuario.sucursales_permitidas = json.dumps(["CURICO"])
    db_session.commit()
    app.dependency_overrides[requiere_auth] = lambda: "noadmin@curifor.com"
    try:
        op = client.get("/api/sugerido/opciones").json()
    finally:
        app.dependency_overrides[requiere_auth] = lambda: "test@curifor.com"
    assert op["proveedores"] == ["SOLO CURICO"]
    assert op["sucursales"] == [{"sucursal_id": "CURICO", "nombre": "Curico"}]


def test_no_la_confunde_con_la_ficha_de_un_producto(client):
    """La ruta de la ficha es `/{producto}/{sucursal}`: "opciones" sola no calza ahi,
    pero si alguien cambia el orden de las rutas, este test lo dice."""
    r = client.get("/api/sugerido/opciones")
    assert r.status_code == 200
    assert "proveedores" in r.json()
