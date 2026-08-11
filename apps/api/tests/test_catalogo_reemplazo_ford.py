"""La ficha del catalogo tiene que RECIBIR el reemplazo de FORD, no solo pintarlo.

`catalogo_service.detalle` calculaba `reemplazo_ford` desde ago-2026 y la pagina
`app/catalogo/[producto]` tiene el bloque rojo listo para mostrarlo, pero
`CatalogoDetalle` no declaraba el campo: FastAPI lo descartaba al serializar y el
aviso nunca aparecio en pantalla. Un dato que el backend calcula y el front sabe
dibujar, perdido en el medio.
"""
from src.models import ProductoCatalogo
from src.services import reemplazo_service


def _producto(db_session, codigo="25 MB3Z19N619C"):
    db_session.add(ProductoCatalogo(
        tenant_id="curifor", producto=codigo, glosa="MODULO", costo=1000.0,
    ))
    db_session.commit()
    return codigo


def _reemplazo(db_session, **kw):
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
    reemplazo_service.reemplazar(db_session, [base])


def test_la_ficha_trae_el_aviso_de_ford(db_session, client):
    codigo = _producto(db_session)
    _reemplazo(db_session)

    r = client.get(f"/api/catalogo/{codigo}")
    assert r.status_code == 200
    rf = r.json().get("reemplazo_ford")
    assert rf is not None, "el campo se perdia al serializar: ese era el bug"
    assert rf["reemplazado_por"] == "19 MB3Z19N619A"
    assert rf["reemplazado_por_ford"] == "MB3Z/19N619/A/"
    assert rf["cadena"] == "MB3Z/19N619/C/ > MB3Z/19N619/A/"
    assert rf["sucesor_confirmado"] is True
    assert rf["agrupado"] is True


def test_la_lista_de_reemplaza_a_llega_como_lista(db_session, client):
    """El front la recorre con .map: si llegara como texto, reventaria la pagina."""
    codigo = _producto(db_session, "13 CC455J272AC")
    _reemplazo(db_session, producto=codigo, reemplazado_por=None,
               reemplazado_por_ford=None, cadena=None,
               reemplaza_a=["13 CC455J272AB", "13 CC455J272AA"])

    rf = client.get(f"/api/catalogo/{codigo}").json()["reemplazo_ford"]
    assert rf["reemplaza_a"] == ["13 CC455J272AB", "13 CC455J272AA"]


def test_el_sucesor_sin_confirmar_llega_marcado(db_session, client):
    """La ficha muestra un texto distinto segun esto: si se pierde, el comprador
    lee "el stock se cuenta junto" cuando NO se cuenta junto."""
    codigo = _producto(db_session, "25 1710216")
    _reemplazo(db_session, producto=codigo, reemplazado_por=None,
               reemplazado_por_ford="3S71/17D568/AD/",
               cadena="/1710216// > 3S7Z/17D550/B/ > 3S71/17D568/AD/",
               sucesor_confirmado=False, agrupado=False,
               aviso="ningun codigo de la cadena quedo activo")

    rf = client.get(f"/api/catalogo/{codigo}").json()["reemplazo_ford"]
    assert rf["sucesor_confirmado"] is False
    assert rf["agrupado"] is False
    assert "ningun codigo" in rf["aviso"]


def test_un_producto_sin_reemplazo_lo_deja_en_null(db_session, client):
    """El caso normal: FORD no dice nada y la ficha no pinta el bloque."""
    codigo = _producto(db_session, "25 SINREEMPLAZO")
    assert client.get(f"/api/catalogo/{codigo}").json()["reemplazo_ford"] is None
