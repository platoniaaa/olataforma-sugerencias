"""El modal de sugerencia manual en frases (opcion A, aprobada el 08-10-2026).

Lo que el servidor tiene que garantizar para que las frases digan la verdad:

- "Hoy se compran N en total": el modal calcula con el contexto del par
  (stock, en camino, lo que pide el sistema, venta diaria).
- "Se borra sola cuando la marques como pedida": marcar el pedido cierra las
  sugerencias del producto.
- "Se revisa todos los dias": las reglas se aplican cada dia. El workflow que
  debia hacerlo fallaba con 403 desde hace mas de 40 corridas; ahora lo dispara
  el motor por un endpoint de admin.
- Una sugerencia por producto: si ya hay una, se reemplaza o se suma, a eleccion.
"""
from datetime import date, timedelta

from src.models import SugerenciaManual, SugerenciaRecurrente, Sugerido
from src.services import recurrentes_service

PROD = "25 DG9Z8100A"


def _sug(db_session, producto=PROD, sucursal="LINDEROS", **kw):
    base = dict(
        tenant_id="curifor", producto=producto, sucursal_id=sucursal,
        nombre_sucursal=sucursal.title(), pedir="Si", demanda_diaria=0.8,
        stock_activo_suc=5, stock_en_transito_suc=2, total_sugerido_suc=3,
    )
    base.update(kw)
    db_session.add(Sugerido(**base))
    db_session.commit()


def _vigentes(db_session, producto=PROD, sucursal="LINDEROS"):
    return (
        db_session.query(SugerenciaManual)
        .filter_by(producto=producto, sucursal_id=sucursal, archivada=False)
        .all()
    )


def test_el_contexto_trae_lo_que_el_modal_necesita(client, db_session):
    _sug(db_session)
    r = client.get("/api/sugerencias-manuales/contexto",
                   params={"producto": PROD, "sucursal_id": "LINDEROS"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert (d["stock"], d["transito"], d["sugerido_sistema"]) == (5, 2, 3)
    assert d["demanda_diaria"] == 0.8 and d["en_sugerido"] is True
    assert d["vigentes"] == [] and d["reglas"] == []
    assert "objetivo" not in d and "faltante" not in d


def test_sin_venta_en_el_modelo_la_demanda_viene_vacia(client, db_session):
    """Ahi la frase de dias no se puede calcular: el modal lo tiene que saber."""
    _sug(db_session, demanda_diaria=0)
    d = client.get("/api/sugerencias-manuales/contexto",
                   params={"producto": PROD, "sucursal_id": "LINDEROS"}).json()
    assert d["demanda_diaria"] is None


def test_el_contexto_muestra_lo_que_ya_hay_cargado(client, db_session):
    _sug(db_session)
    client.post("/api/sugerencias-manuales",
                json={"producto": PROD, "sucursal_id": "LINDEROS", "unidades": 5})
    client.post("/api/sugerencias-manuales/recurrentes", json={
        "modo": "individual", "producto": PROD, "sucursal_id": "LINDEROS",
        "stock_objetivo": 12, "cada_dias": 1,
    })
    d = client.get("/api/sugerencias-manuales/contexto",
                   params={"producto": PROD, "sucursal_id": "LINDEROS"}).json()
    # La instancia de la regla no se lista como "vigente": se lista la regla.
    assert [v["unidades"] for v in d["vigentes"]] == [5]
    assert [r["stock_objetivo"] for r in d["reglas"]] == [12]


def test_reemplazar_cierra_lo_anterior(client, db_session):
    _sug(db_session)
    client.post("/api/sugerencias-manuales",
                json={"producto": PROD, "sucursal_id": "LINDEROS", "unidades": 5})
    r = client.post("/api/sugerencias-manuales", json={
        "producto": PROD, "sucursal_id": "LINDEROS", "unidades": 7, "reemplazar": True,
    })
    assert r.status_code == 201, r.text
    assert [s.unidades for s in _vigentes(db_session)] == [7]


def test_sin_reemplazar_se_suman(client, db_session):
    _sug(db_session)
    for u in (5, 7):
        client.post("/api/sugerencias-manuales",
                    json={"producto": PROD, "sucursal_id": "LINDEROS", "unidades": u})
    assert sorted(s.unidades for s in _vigentes(db_session)) == [5, 7]


def test_una_regla_nueva_con_reemplazar_apaga_la_anterior(client, db_session):
    _sug(db_session)
    client.post("/api/sugerencias-manuales/recurrentes", json={
        "modo": "individual", "producto": PROD, "sucursal_id": "LINDEROS",
        "stock_objetivo": 12, "cada_dias": 1,
    })
    r = client.post("/api/sugerencias-manuales/recurrentes", json={
        "modo": "individual", "producto": PROD, "sucursal_id": "LINDEROS",
        "dias_inventario": 30, "cada_dias": 1, "reemplazar": True,
    })
    assert r.status_code == 201, r.text
    activas = db_session.query(SugerenciaRecurrente).filter_by(activa=True).all()
    assert [a.dias_inventario for a in activas] == [30]
    # Queda solo la instancia de la regla nueva: 30 dias x 0,8 = 24, menos 10 = 14.
    assert [s.unidades for s in _vigentes(db_session)] == [14]


def test_marcar_como_pedido_cierra_las_sugerencias_del_producto(client, db_session):
    """"Se borra sola cuando la marques como pedida" tiene que ser cierto."""
    _sug(db_session)
    _sug(db_session, sucursal="CURICO")
    client.post("/api/sugerencias-manuales",
                json={"producto": PROD, "sucursal_id": "LINDEROS", "unidades": 7})
    client.post("/api/sugerencias-manuales/recurrentes", json={
        "modo": "individual", "producto": PROD, "sucursal_id": "LINDEROS",
        "stock_objetivo": 12, "cada_dias": 1,
    })
    client.post("/api/sugerencias-manuales",
                json={"producto": PROD, "sucursal_id": "CURICO", "unidades": 4})

    r = client.post("/api/compras/pedidos",
                    json={"producto": PROD, "sucursal_id": "LINDEROS", "unidades": 9})

    assert r.status_code == 201 and r.json()["sugerencias_cerradas"] == 2
    assert _vigentes(db_session) == []
    # La regla sigue: manana se recalcula con lo que ya viene en camino.
    assert db_session.query(SugerenciaRecurrente).filter_by(activa=True).count() == 1
    # Otra sucursal no se toca.
    assert [s.unidades for s in _vigentes(db_session, sucursal="CURICO")] == [4]


def test_el_motor_aplica_las_reglas_del_dia_una_sola_vez(client, db_session):
    _sug(db_session)
    db_session.add(SugerenciaRecurrente(
        tenant_id="curifor", modo="individual", producto=PROD, sucursal_id="LINDEROS",
        unidades=0, stock_objetivo=12, cada_dias=1, proxima_ejecucion=date.today(),
    ))
    db_session.commit()

    r = client.post("/api/admin/procesar-recurrentes")
    assert r.status_code == 200, r.text
    assert r.json()["recurrencias_procesadas"] == 1
    assert [s.unidades for s in _vigentes(db_session)] == [2]  # 12 - (5 + 2 + 3)
    # Llamarlo de nuevo el mismo dia no repite nada.
    assert client.post("/api/admin/procesar-recurrentes").json()["recurrencias_procesadas"] == 0
    assert len(_vigentes(db_session)) == 1


def test_la_regla_diaria_no_vuelve_a_pedir_lo_que_ya_viene(client, db_session):
    """Lo que hace que "nunca menos de 12" no compre dos veces."""
    _sug(db_session)
    client.post("/api/sugerencias-manuales/recurrentes", json={
        "modo": "individual", "producto": PROD, "sucursal_id": "LINDEROS",
        "stock_objetivo": 12, "cada_dias": 1,
    })
    assert [s.unidades for s in _vigentes(db_session)] == [2]

    # Se compro: al dia siguiente lo pedido aparece en camino y el sistema ya no pide.
    fila = db_session.query(Sugerido).filter_by(producto=PROD, sucursal_id="LINDEROS").one()
    fila.stock_en_transito_suc, fila.total_sugerido_suc = 7, 0
    db_session.commit()
    recurrentes_service.procesar(db_session, hoy=date.today() + timedelta(days=1))

    assert _vigentes(db_session) == []


def test_reemplazar_no_toca_lo_que_viene_de_una_regla_por_grupo(client, db_session):
    """El modal no muestra la regla por grupo como "ya hay una": no se la borra."""
    _sug(db_session)
    r = client.post("/api/sugerencias-manuales/recurrentes", json={
        "modo": "grupo", "filtros": {"sucursales": ["Linderos"]}, "unidades": 4, "cada_dias": 1,
    })
    assert r.status_code == 201, r.text
    client.post("/api/sugerencias-manuales",
                json={"producto": PROD, "sucursal_id": "LINDEROS", "unidades": 5})

    client.post("/api/sugerencias-manuales", json={
        "producto": PROD, "sucursal_id": "LINDEROS", "unidades": 7, "reemplazar": True,
    })

    assert sorted(s.unidades for s in _vigentes(db_session)) == [4, 7]
    assert db_session.query(SugerenciaRecurrente).filter_by(activa=True).count() == 1


def test_el_conteo_de_varios_productos_respeta_el_proveedor(client, db_session):
    """El modal decia "Se aplica a N productos" sin filtrar por proveedor."""
    _sug(db_session, proveedor="FORD")
    _sug(db_session, producto="20 XO5W30BA", proveedor="SHELL")
    todos = client.get("/api/sugerido", params={"limit": 1}).json()["total"]
    solo = client.get(
        "/api/sugerido", params=[("limit", 1), ("proveedores", "SHELL")]
    ).json()["total"]
    # La base de pruebas ya trae otras filas: lo que importa es que filtre.
    assert solo == 1 < todos


def test_la_regla_por_grupo_dice_su_proveedor(client, db_session):
    _sug(db_session, proveedor="SHELL")
    r = client.post("/api/sugerencias-manuales/recurrentes", json={
        "modo": "grupo", "filtros": {"proveedores": ["SHELL"]},
        "stock_objetivo": 12, "cada_dias": 1,
    })
    assert r.status_code == 201, r.text
    assert r.json()["resumen"] == "Proveedor: SHELL"
