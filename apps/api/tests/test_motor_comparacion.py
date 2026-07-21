"""Tests del comparador motor vs Power BI (modo sombra)."""
from src.models import Sugerido
from src.services import motor_comparacion

_CABECERAS = "Producto,SucursalID,total_sugerido_suc,stock_activo_suc,punto_de_pedido,Proveedor"


def _csv(filas: list[str]) -> bytes:
    return ("\n".join([_CABECERAS, *filas])).encode("utf-8")


def _sug(**kw):
    base = dict(tenant_id="curifor", sucursal_id="LINDEROS", nombre_sucursal="Linderos")
    base.update(kw)
    return Sugerido(**base)


def test_paridad_total_cuando_coinciden(client, db_session):
    db_session.add(_sug(producto="P1", total_sugerido_suc=10, stock_activo_suc=5,
                        punto_de_pedido=3, proveedor="FORD"))
    db_session.commit()
    r = client.post(
        "/api/admin/motor/comparar",
        files={"file": ("motor.csv", _csv(["P1,LINDEROS,10,5,3,FORD"]), "text/csv")},
    ).json()
    assert r["filas_comunes"] == 1
    assert r["paridad_pct"] == 100.0
    assert r["ejemplos"] == []


def test_detecta_divergencia_y_la_reporta(client, db_session):
    db_session.add(_sug(producto="P1", total_sugerido_suc=10, stock_activo_suc=5))
    db_session.commit()
    r = client.post(
        "/api/admin/motor/comparar",
        files={"file": ("motor.csv", _csv(["P1,LINDEROS,40,5,,"]), "text/csv")},
    ).json()
    assert r["paridad_pct"] == 0.0
    dif = r["ejemplos"][0]["diferencias"]["total_sugerido_suc"]
    assert dif["motor"] == 40 and dif["bi"] == 10


def test_tolera_diferencias_de_redondeo(client, db_session):
    """DAX y Python redondean distinto; media unidad no es un error de calculo."""
    db_session.add(_sug(producto="P1", total_sugerido_suc=10.0))
    db_session.commit()
    r = client.post(
        "/api/admin/motor/comparar",
        files={"file": ("motor.csv", _csv(["P1,LINDEROS,10.4,,,"]), "text/csv")},
    ).json()
    assert r["paridad_pct"] == 100.0


def test_columna_que_el_motor_no_emite_cuenta_como_divergencia(client, db_session):
    """Si el motor deja de calcular algo, tiene que verse: un vacio no es un match."""
    db_session.add(_sug(producto="P1", total_sugerido_suc=10, demanda_diaria=1.2))
    db_session.commit()
    r = client.post(
        "/api/admin/motor/comparar",
        files={"file": ("motor.csv", _csv(["P1,LINDEROS,10,,,"]), "text/csv")},
    ).json()
    assert r["paridad_pct"] == 0.0
    assert r["por_columna"]["demanda_diaria"]["distintas"] == 1


def test_reporta_filas_que_solo_estan_en_un_lado(client, db_session):
    db_session.add(_sug(producto="SOLO-BI", total_sugerido_suc=1))
    db_session.commit()
    r = client.post(
        "/api/admin/motor/comparar",
        files={"file": ("motor.csv", _csv(["SOLO-MOTOR,LINDEROS,1,,,"]), "text/csv")},
    ).json()
    assert r["filas_solo_motor"] == 1
    assert "SOLO-BI / LINDEROS" in r["ejemplos_solo_bi"]


def test_la_comparacion_no_toca_la_tabla_sugerido(client, db_session):
    """La garantia central del modo sombra."""
    db_session.add(_sug(producto="P1", total_sugerido_suc=10))
    db_session.commit()
    antes = {(s.producto, s.total_sugerido_suc) for s in db_session.query(Sugerido).all()}

    client.post(
        "/api/admin/motor/comparar",
        files={"file": ("motor.csv", _csv(["P1,LINDEROS,999,,,", "NUEVO,TALCA,50,,,"]), "text/csv")},
    )
    despues = {(s.producto, s.total_sugerido_suc) for s in db_session.query(Sugerido).all()}
    assert antes == despues


def test_guarda_el_historial(client, db_session):
    db_session.add(_sug(producto="P1", total_sugerido_suc=10))
    db_session.commit()
    client.post(
        "/api/admin/motor/comparar",
        files={"file": ("motor.csv", _csv(["P1,LINDEROS,10,,,"]), "text/csv")},
    )
    items = client.get("/api/admin/motor/comparaciones").json()["items"]
    assert len(items) == 1
    assert items[0]["paridad_pct"] == 100.0
    assert items[0]["ejecutado_por"] == "test@curifor.com"


def test_archivo_vacio_rechazado(client):
    r = client.post(
        "/api/admin/motor/comparar",
        files={"file": ("motor.csv", b"", "text/csv")},
    )
    assert r.status_code == 400


def test_columnas_comparadas_existen_en_el_modelo():
    """Si alguien renombra una columna, el comparador tiene que fallar aca y no en prod."""
    columnas = {c.name for c in Sugerido.__table__.columns}
    assert set(motor_comparacion.COLUMNAS_COMPARADAS) <= columnas
