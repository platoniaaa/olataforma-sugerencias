"""Reemplazos de FORD: el motor los publica, el comprador los ve.

FORD dice que codigo descontinuado sustituyo a cual. Sirve para avisarle al
comprador que le estan pidiendo un codigo muerto y cual es el vigente.

Ojo con la distincion que atraviesa todo esto: AGRUPAR (sumar el stock del viejo
con el del nuevo) lo hace el motor y solo cuando FORD confirmo el sucesor. Esta
tabla ademas guarda los NO confirmados, que se muestran como aviso pero no tocan
el calculo.
"""
from src.services import reemplazo_service


def _fila(**kw) -> dict:
    base = {
        "producto": "25 MB3Z19N619C",
        "reemplazado_por": "19 MB3Z19N619A",
        "reemplazado_por_ford": "MB3Z/19N619/A/",
        "cadena": "MB3Z/19N619/C/ > MB3Z/19N619/A/",
        "reemplaza_a": [],
        "sucesor_confirmado": True,
        "agrupado": True,
        "aviso": None,
    }
    base.update(kw)
    return base


def test_publica_y_lee(db_session):
    resumen = reemplazo_service.reemplazar(db_session, [_fila()])
    assert resumen["filas_cargadas"] == 1
    assert resumen["reemplazo"] is True

    fila = reemplazo_service.de_producto(db_session, "25 MB3Z19N619C")
    assert fila["reemplazado_por"] == "19 MB3Z19N619A"
    assert fila["reemplazado_por_ford"] == "MB3Z/19N619/A/"
    assert fila["sucesor_confirmado"] is True
    assert fila["agrupado"] is True


def test_la_lista_de_reemplaza_a_va_y_vuelve_como_lista(db_session):
    reemplazo_service.reemplazar(db_session, [
        _fila(producto="25 NUEVO", reemplazado_por=None, reemplazado_por_ford=None,
              reemplaza_a=["25 VIEJO1", "25 VIEJO2"]),
    ])
    fila = reemplazo_service.de_producto(db_session, "25 NUEVO")
    assert fila["reemplaza_a"] == ["25 VIEJO1", "25 VIEJO2"]


def test_un_sucesor_sin_confirmar_se_guarda_pero_marcado(db_session):
    """Los 999 'Sin candidato vigente': se avisan, no agrupan."""
    reemplazo_service.reemplazar(db_session, [
        _fila(producto="25 DUDOSO", sucesor_confirmado=False, agrupado=False,
              aviso="ningun codigo de la cadena quedo activo"),
    ])
    fila = reemplazo_service.de_producto(db_session, "25 DUDOSO")
    assert fila["sucesor_confirmado"] is False
    assert fila["agrupado"] is False
    assert "ningun codigo" in fila["aviso"]


def test_una_tanda_vacia_no_borra_lo_que_hay(db_session):
    """Mismo criterio que el transito: mejor una foto vieja que decirle al
    comprador 'este codigo no tiene reemplazo' porque el motor fallo."""
    reemplazo_service.reemplazar(db_session, [_fila()])
    resumen = reemplazo_service.reemplazar(db_session, [])
    assert resumen["reemplazo"] is False
    assert reemplazo_service.de_producto(db_session, "25 MB3Z19N619C") is not None


def test_la_publicacion_reemplaza_la_foto_anterior(db_session):
    reemplazo_service.reemplazar(db_session, [_fila(producto="25 VIEJA")])
    reemplazo_service.reemplazar(db_session, [_fila(producto="25 NUEVA")])
    assert reemplazo_service.de_producto(db_session, "25 VIEJA") is None
    assert reemplazo_service.de_producto(db_session, "25 NUEVA") is not None


def test_filas_sin_ningun_reemplazo_se_ignoran(db_session):
    """Una fila que no dice nada solo agranda la tabla."""
    resumen = reemplazo_service.reemplazar(db_session, [
        _fila(),
        _fila(producto="25 VACIA", reemplazado_por=None, reemplazado_por_ford=None,
              reemplaza_a=[]),
    ])
    assert resumen["filas_cargadas"] == 1
    assert resumen["ignoradas"] == 1


def test_sin_producto_se_ignora(db_session):
    resumen = reemplazo_service.reemplazar(db_session, [_fila(producto="  ")])
    assert resumen["filas_cargadas"] == 0


def test_por_producto_con_varios(db_session):
    reemplazo_service.reemplazar(db_session, [
        _fila(producto="25 A"), _fila(producto="25 B"), _fila(producto="25 C"),
    ])
    encontrados = reemplazo_service.por_producto(db_session, {"25 A", "25 C", "25 NOEXISTE"})
    assert set(encontrados) == {"25 A", "25 C"}


# --- De punta a punta: el endpoint que llama el motor ----------------------------

def test_el_endpoint_publica(client):
    r = client.post("/api/admin/reemplazos-ford", json={"filas": [_fila()]})
    assert r.status_code == 200
    assert r.json()["filas_cargadas"] == 1


def test_el_endpoint_exige_la_lista(client):
    r = client.post("/api/admin/reemplazos-ford", json={})
    assert r.status_code == 400


# --- La columna del sugerido -----------------------------------------------------

def test_el_sugerido_marca_las_filas_dadas_de_baja(client, db_session):
    """La columna sale de un cruce, no de una columna de `sugerido`.

    Esa tabla se borra y reinserta entera en cada carga: duplicar el dato ahi
    obligaria a que el motor lo mandara en el CSV y a mantener dos copias.
    """
    fila = client.get("/api/sugerido", params={"solo_pedir": False, "limit": 1}).json()
    # Sin `assert` esto seria un test que pasa sin probar nada si el fixture deja
    # de sembrar sugerido. Mejor que avise.
    assert fila["items"], "el fixture no tiene filas de sugerido: el test no prueba nada"
    producto = fila["items"][0]["producto"]

    reemplazo_service.reemplazar(db_session, [
        _fila(producto=producto, reemplazado_por="25 VIGENTE"),
    ])
    datos = client.get("/api/sugerido", params={"solo_pedir": False, "limit": 50}).json()
    marcada = next(i for i in datos["items"] if i["producto"] == producto)
    assert marcada["reemplazado_por_ford"] == "25 VIGENTE"


def test_sin_el_vigente_en_curifor_cae_al_codigo_de_ford(db_session):
    """Aunque Curifor no tenga el sucesor, saber que esta descontinuado importa."""
    reemplazo_service.reemplazar(db_session, [
        _fila(producto="25 SOLOFORD", reemplazado_por=None,
              reemplazado_por_ford="MB3Z/19N619/A/"),
    ])
    fila = reemplazo_service.de_producto(db_session, "25 SOLOFORD")
    assert fila["reemplazado_por"] is None
    assert fila["reemplazado_por_ford"] == "MB3Z/19N619/A/"
