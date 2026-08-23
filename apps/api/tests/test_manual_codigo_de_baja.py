"""Un codigo que FORD dio de baja se AVISA, no se bloquea.

La sugerencia manual es el otro camino por el que un codigo descontinuado entra
al sugerido sin pasar por el motor (el primero era InStock). El modal avisaba una
sola cosa —que el codigo no existe— y el servidor la rechaza con 422; un codigo
que SI existe pero esta dado de baja entraba sin que nadie dijera nada.

**Este test existe para que el aviso no se convierta en un rechazo.** Va contra el
instinto: `_validar_producto` rechaza los inexistentes, y parece natural hacer lo
mismo aca. No corresponde. Si el vigente no tiene stock en FORD, la orden va con
otro codigo del grupo — o sea que pedir el viejo a veces es lo correcto.
Bloquearlo dejaria al comprador sin poder hacer su trabajo.

Si alguien "arregla" esto convirtiendolo en un 422, el test se cae.
"""
import pytest

from src.models import ProductoCatalogo, ReemplazoFord


@pytest.fixture()
def de_baja(db_session):
    db_session.add_all([
        ProductoCatalogo(tenant_id="curifor", producto="25 MB3Z19N619C",
                         glosa="FILTRO DE CABINA"),
        ProductoCatalogo(tenant_id="curifor", producto="19 MB3Z19N619A",
                         glosa="FILTRO DE CABINA"),
    ])
    db_session.add(ReemplazoFord(
        tenant_id="curifor", producto="25 MB3Z19N619C",
        reemplazado_por="19 MB3Z19N619A",
        reemplazado_por_ford="MB3Z/19N619/A/",
        cadena="MB3Z/19N619/C/ > MB3Z/19N619/A/",
        sucesor_confirmado=True, agrupado=True,
        extraido_en="2026-08-22 16:17:53",
    ))
    db_session.commit()
    return db_session


def test_el_autocomplete_avisa_cual_es_el_vigente(client, de_baja):
    """De ahi lo saca el modal: sin una segunda llamada por cada tecla."""
    r = client.get("/api/productos", params={"q": "MB3Z19N619C"})

    assert r.status_code == 200
    fila = next(i for i in r.json()["items"] if i["producto"] == "25 MB3Z19N619C")
    assert fila["reemplazado_por"] == "19 MB3Z19N619A"


def test_un_codigo_vigente_no_trae_aviso(client, de_baja):
    """No se inventa nada: en blanco significa "FORD no dice nada de este"."""
    r = client.get("/api/productos", params={"q": "MB3Z19N619A"})

    fila = next(i for i in r.json()["items"] if i["producto"] == "19 MB3Z19N619A")
    assert fila["reemplazado_por"] is None


def test_la_sugerencia_manual_de_un_codigo_de_baja_SE_GUARDA(client, de_baja):
    """El corazon de la fase: avisar, no bloquear.

    Si esto empieza a devolver 422, un comprador que necesita el codigo viejo
    -porque el vigente no tiene stock en FORD- se queda sin poder pedirlo.
    """
    r = client.post("/api/sugerencias-manuales", json={
        "producto": "25 MB3Z19N619C",
        "sucursal_id": "RANCAGUA",
        "unidades": 2,
        "motivo": "El vigente no tiene stock en FORD",
    })

    assert r.status_code in (200, 201), r.text
