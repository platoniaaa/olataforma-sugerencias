"""Cargar la lista InStock desde la plataforma, sin conexion directa a la base.

El endpoint existe por un problema concreto: la regla InStock estuvo desplegada
en produccion con la tabla vacia, pidiendo cero unidades, porque la unica forma
de cargarla era un script de consola conectado a Supabase y nadie lo corrio ahi.
"""
import pytest

from src.jobs import cargar_instock as job
from src.models import ProductoCatalogo, RepuestoInstock, StockUnificado, Sugerido
from src.services import instock_service


@pytest.fixture()
def pautas(db_session):
    """Maestro con los casos que importan y un par de pautas."""
    db_session.add_all([
        # El part number existe bajo DOS rubros: se marca uno solo.
        ProductoCatalogo(tenant_id="curifor", producto="28 2151323001", glosa="GOLILLA CARTER"),
        ProductoCatalogo(tenant_id="curifor", producto="95 2151323001", glosa="GOLILLA CARTER"),
        ProductoCatalogo(tenant_id="curifor", producto="95 2630035505", glosa="FILTRO ACEITE"),
    ])
    # El rubro 95 es el que Curifor stockea; el 28 no.
    db_session.add(StockUnificado(tenant_id="curifor", producto="95 2151323001",
                                  sucursal_id="LINDEROS", stock=301))
    db_session.commit()
    return db_session


def _pautas_csv(tmp_path, filas: list[str]):
    p = tmp_path / "pautas.csv"
    p.write_text(
        "part_number;marca;modelos;operacion;detalle\n" + "\n".join(filas),
        encoding="utf-8",
    )
    return p


def test_carga_la_lista_y_la_regla_queda_activa(client, pautas, tmp_path, monkeypatch):
    monkeypatch.setattr(
        job, "DEFAULT_PATH",
        _pautas_csv(tmp_path, [
            "2630035505;HYUNDAI;Accent;FILTRO ACEITE;cambio de aceite",
            "2151323001;HYUNDAI;Accent;GOLILLA CARTER;cambio de aceite",
        ]),
    )
    assert instock_service.resumen(pautas)["activo"] is False

    r = client.post("/api/admin/cargar-instock")
    assert r.status_code == 200
    assert r.json()["productos"] == 2
    assert r.json()["sin_codigo"] == 0

    resumen = instock_service.resumen(pautas)
    assert resumen["activo"] is True
    assert resumen["n_repuestos"] == 2


def test_un_part_number_en_dos_rubros_marca_uno_solo(client, pautas, tmp_path, monkeypatch):
    """Marcar los dos pediria 2 unidades por rubro: 4 del mismo repuesto fisico."""
    monkeypatch.setattr(
        job, "DEFAULT_PATH",
        _pautas_csv(tmp_path, ["2151323001;HYUNDAI;Accent;GOLILLA CARTER;cambio de aceite"]),
    )
    r = client.post("/api/admin/cargar-instock").json()
    assert r["productos"] == 1
    marcados = [x.producto for x in pautas.query(RepuestoInstock).all()]
    # Gana el que Curifor stockea de verdad.
    assert marcados == ["95 2151323001"]
    assert r["varios_rubros"][0]["se_descarta"] == ["28 2151323001"]


def test_un_part_number_que_no_esta_en_el_maestro_se_reporta(client, pautas, tmp_path, monkeypatch):
    """No se marca, pero tiene que salir en la respuesta para revisarlo con Repuestos."""
    monkeypatch.setattr(
        job, "DEFAULT_PATH",
        _pautas_csv(tmp_path, ["NOEXISTE123;HYUNDAI;i20;FILTRO COMBUSTIBLE;mantencion"]),
    )
    r = client.post("/api/admin/cargar-instock").json()
    assert r["productos"] == 0
    assert r["sin_codigo"] == 1
    assert r["sin_codigo_detalle"][0]["part_number"] == "NOEXISTE123"


def test_recargar_reemplaza_la_lista_no_la_acumula(client, pautas, tmp_path, monkeypatch):
    monkeypatch.setattr(
        job, "DEFAULT_PATH",
        _pautas_csv(tmp_path, [
            "2630035505;HYUNDAI;Accent;FILTRO ACEITE;cambio",
            "2151323001;HYUNDAI;Accent;GOLILLA CARTER;cambio",
        ]),
    )
    client.post("/api/admin/cargar-instock")
    monkeypatch.setattr(
        job, "DEFAULT_PATH",
        _pautas_csv(tmp_path, ["2630035505;HYUNDAI;Accent;FILTRO ACEITE;cambio"]),
    )
    assert client.post("/api/admin/cargar-instock").json()["productos"] == 1
    assert pautas.query(RepuestoInstock).count() == 1


def test_queda_registrado_en_la_auditoria(client, pautas, tmp_path, monkeypatch):
    from src.models import AuditoriaLog

    monkeypatch.setattr(
        job, "DEFAULT_PATH",
        _pautas_csv(tmp_path, ["2630035505;HYUNDAI;Accent;FILTRO ACEITE;cambio"]),
    )
    client.post("/api/admin/cargar-instock")
    acciones = [a.accion for a in pautas.query(AuditoriaLog).all()]
    assert "instock_cargado" in acciones


def test_solo_admin(client, pautas, tmp_path, monkeypatch):
    from src.main import app
    from src.services.auth import requiere_auth

    monkeypatch.setattr(
        job, "DEFAULT_PATH",
        _pautas_csv(tmp_path, ["2630035505;HYUNDAI;Accent;FILTRO ACEITE;cambio"]),
    )
    app.dependency_overrides[requiere_auth] = lambda: "noadmin@curifor.com"
    try:
        assert client.post("/api/admin/cargar-instock").status_code == 403
    finally:
        app.dependency_overrides[requiere_auth] = lambda: "test@curifor.com"
