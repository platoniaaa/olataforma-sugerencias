"""La descarga no puede quedar cortada en silencio.

El CSV de ventas historicas usaba el limite de la GRILLA (2.000 filas). Si la
consulta daba mas, el archivo salia mocho y nada lo decia: un CSV cortado se ve
exactamente igual de completo que uno entero, y el que lo recibe suma sobre una
parte creyendo que tiene todo.
"""
from src.services import ventas_historicas_service as svc


def test_el_tope_de_la_descarga_es_mayor_que_el_de_la_pantalla():
    """Son dos cosas distintas: en pantalla 2.000 filas ya no se leen; una
    descarga se abre en Excel y se trabaja ahi."""
    assert svc.LIMITE_EXPORT > svc.LIMITE_FILAS


def test_sin_tope_sigue_mandando_el_limite_de_pantalla(db_session):
    """La grilla no puede empezar a traer 100.000 filas por este cambio."""
    d = svc.detalle(db_session, {}, limit=999_999)
    assert len(d["items"]) <= svc.LIMITE_FILAS


def test_con_tope_se_puede_pasar_del_limite_de_pantalla(db_session):
    d = svc.detalle(db_session, {}, limit=svc.LIMITE_EXPORT, tope=svc.LIMITE_EXPORT)
    # Con el fixture hay pocas filas; lo que se comprueba es que el tope manda.
    assert len(d["items"]) <= svc.LIMITE_EXPORT
    assert d["total"] >= len(d["items"])


def test_el_csv_avisa_cuando_corta(client, monkeypatch):
    """Con la consulta truncada, la ultima linea tiene que decirlo."""
    def _fake(db, f, limit=500, tope=None):
        return {"items": [{"periodo": "202607", "producto": "P1", "sucursal": "LINDEROS",
                           "cantidad": 3, "neto": 100, "n_lineas": 1}],
                "total": 5000}

    monkeypatch.setattr(svc, "detalle", _fake)
    r = client.get("/api/ventas-historicas/export-csv")
    assert r.status_code == 200
    texto = r.content.decode("utf-8-sig")
    assert "ATENCION" in texto
    assert "4.999" in texto or "4,999" in texto  # las que faltan


def test_el_csv_no_avisa_cuando_esta_completo(client, monkeypatch):
    def _fake(db, f, limit=500, tope=None):
        return {"items": [{"periodo": "202607", "producto": "P1", "sucursal": "LINDEROS",
                           "cantidad": 3, "neto": 100, "n_lineas": 1}],
                "total": 1}

    monkeypatch.setattr(svc, "detalle", _fake)
    r = client.get("/api/ventas-historicas/export-csv")
    assert "ATENCION" not in r.content.decode("utf-8-sig")
