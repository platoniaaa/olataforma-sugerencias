"""La cadena de reemplazos y su fecha llegan al sugerido.

Hasta ago-2026 la grilla solo mostraba `Reemplazado por (FORD)`: el ultimo salto.
La cadena completa vivia en la tabla `reemplazo_ford` y no llegaba a ninguna
pantalla, asi que no habia forma de ver el historico del codigo.

Y la fecha de extraccion no viajaba en absoluto. Eso importa desde que la
consulta al portal es semanal y automatica: si la corrida del lunes falla —la
sesion de FORD vence y pide MFA, que lo tiene que poner una persona— la
plataforma sigue mostrando lo de la semana pasada con la misma cara de siempre.
"""
import pytest

from src.models import ReemplazoFord
from src.services import sugerido_service


@pytest.fixture()
def con_reemplazo(db_session):
    db_session.add(ReemplazoFord(
        tenant_id="curifor", producto="19 MB3Z19N619A",
        reemplazado_por=None, reemplazado_por_ford=None,
        cadena="MB3Z/19N619/C/ > MB3Z/19N619/A/",
        reemplaza_a="25 MB3Z19N619C",
        sucesor_confirmado=True, agrupado=True,
        extraido_en="2026-08-22 16:17:53",
    ))
    db_session.commit()
    return db_session


def test_la_cadena_llega_a_la_fila_del_sugerido(con_reemplazo):
    items = [{"producto": "19 MB3Z19N619A"}]

    sugerido_service._agregar_reemplazo_ford(items, con_reemplazo)

    assert items[0]["cadena_ford"] == "MB3Z/19N619/C/ > MB3Z/19N619/A/"


def test_la_fecha_de_consulta_llega_a_la_fila(con_reemplazo):
    items = [{"producto": "19 MB3Z19N619A"}]

    sugerido_service._agregar_reemplazo_ford(items, con_reemplazo)

    assert items[0]["reemplazo_extraido_en"] == "2026-08-22 16:17:53"


def test_un_codigo_sin_reemplazo_queda_en_blanco(con_reemplazo):
    """No se inventa nada: en blanco significa "FORD no dice nada de este"."""
    items = [{"producto": "17 GK2Z9601B"}]

    sugerido_service._agregar_reemplazo_ford(items, con_reemplazo)

    assert items[0]["cadena_ford"] is None
    assert items[0]["reemplazo_extraido_en"] is None


def test_cada_fila_conserva_la_fecha_de_SU_archivo(db_session):
    """El motor combina dos archivos y cada uno se extrae por su lado.

    Al 22-08-2026 la lista de FORD era del 5 al 7 de agosto y la de los codigos
    de Curifor de ese mismo dia: 15 dias de diferencia en la misma tabla. Por eso
    la fecha va por fila y no como un valor global — uno solo mentiria sobre la
    mitad.
    """
    db_session.add_all([
        ReemplazoFord(tenant_id="curifor", producto="19 VIEJO",
                      reemplazado_por="19 NUEVO", cadena="A/1/ > B/2/",
                      sucesor_confirmado=True, agrupado=True,
                      extraido_en="2026-08-05 23:20:26"),
        ReemplazoFord(tenant_id="curifor", producto="19 RECIENTE",
                      reemplazado_por="19 OTRO", cadena="C/3/ > D/4/",
                      sucesor_confirmado=True, agrupado=True,
                      extraido_en="2026-08-22 18:24:47"),
    ])
    db_session.commit()
    items = [{"producto": "19 VIEJO"}, {"producto": "19 RECIENTE"}]

    sugerido_service._agregar_reemplazo_ford(items, db_session)

    assert items[0]["reemplazo_extraido_en"].startswith("2026-08-05")
    assert items[1]["reemplazo_extraido_en"].startswith("2026-08-22")


def test_sin_fecha_no_revienta(db_session):
    """Las filas cargadas antes de que la fecha existiera la tienen en null."""
    db_session.add(ReemplazoFord(
        tenant_id="curifor", producto="19 ANTIGUO",
        reemplazado_por="19 NUEVO", cadena="A/1/ > B/2/",
        sucesor_confirmado=True, agrupado=True, extraido_en=None,
    ))
    db_session.commit()
    items = [{"producto": "19 ANTIGUO"}]

    sugerido_service._agregar_reemplazo_ford(items, db_session)

    assert items[0]["cadena_ford"] == "A/1/ > B/2/"
    assert items[0]["reemplazo_extraido_en"] is None


# --- El vigente que Curifor todavia no tiene -------------------------------------
# FORD nombra un sucesor que no esta en el maestro. El motor no puede colgar el
# grupo de un codigo que el ERP no conoce, asi que la fila sigue saliendo con el
# viejo. La columna Producto lo marca "POR CREAR" para que se vea que ese numero
# hay que dar de alta antes de poder pedirlo. Al 24-08-2026 eran 22 filas.


@pytest.fixture()
def vigente_ajeno(db_session):
    """FORD dice `7C3Z/9601/C/`, que Curifor no tiene: no hay codigo de Curifor."""
    db_session.add(ReemplazoFord(
        tenant_id="curifor", producto="19 7C3Z9601A",
        reemplazado_por=None, reemplazado_por_ford="7C3Z/9601/C/",
        cadena="7C3Z/9601/A/ > 7C3Z/9601/C/",
        sucesor_confirmado=True, agrupado=False,
        extraido_en="2026-08-22 16:17:53",
    ))
    db_session.commit()
    return db_session


def test_marca_el_vigente_que_hay_que_crear(vigente_ajeno):
    """La bandera va del servidor, no se deduce en la pantalla.

    Se podria mirar si el codigo trae barras -los de FORD las tienen y los de
    Curifor no- pero ese formato es una casualidad del proveedor, no un contrato:
    el dia que FORD cambie de notacion, la pantalla dejaria de avisar sin que
    nadie lo note.
    """
    items = [{"producto": "19 7C3Z9601A"}]

    sugerido_service._agregar_reemplazo_ford(items, vigente_ajeno)

    assert items[0]["vigente_por_crear"] is True
    assert items[0]["reemplazado_por_ford"] == "7C3Z/9601/C/"


def test_un_vigente_que_si_esta_en_el_maestro_no_se_marca(con_reemplazo):
    """Solo se marca lo que falta crear; si el codigo existe, no hay nada que pedirle
    a Repuestos."""
    con_reemplazo.add(ReemplazoFord(
        tenant_id="curifor", producto="25 MB3Z19N619C",
        reemplazado_por="19 MB3Z19N619A", reemplazado_por_ford="MB3Z/19N619/A/",
        sucesor_confirmado=True, agrupado=True,
        extraido_en="2026-08-22 16:17:53",
    ))
    con_reemplazo.commit()
    items = [{"producto": "25 MB3Z19N619C"}]

    sugerido_service._agregar_reemplazo_ford(items, con_reemplazo)

    assert items[0]["vigente_por_crear"] is False


def test_un_codigo_vigente_tampoco_se_marca(con_reemplazo):
    """Sin reemplazo no hay nada que crear."""
    items = [{"producto": "19 MB3Z19N619A"}]

    sugerido_service._agregar_reemplazo_ford(items, con_reemplazo)

    assert items[0]["vigente_por_crear"] is False


def test_no_manda_a_crear_un_codigo_que_ford_dice_que_no_se_puede_pedir(db_session):
    """El caso que hace inutil la pegatina si no se filtra.

    Cuando FORD avisa "ningun codigo de la cadena quedo activo, pedible y con
    precio", igual deja escrito el ultimo numero de la cadena. Ese codigo no se
    puede comprar: marcarlo POR CREAR mandaria a Repuestos a dar de alta un numero
    muerto. Al 24-08-2026 eran 12 de los 16 productos con vigente ajeno.
    """
    db_session.add(ReemplazoFord(
        tenant_id="curifor", producto="19 7C3Z9601A",
        reemplazado_por=None, reemplazado_por_ford="7C3Z/9601/C/",
        cadena="7C3Z/9601/A/ > 7C3Z/9601/C/",
        sucesor_confirmado=False, agrupado=False,
        aviso="ningun codigo de la cadena quedo activo, pedible y con precio: revisar a mano",
        extraido_en="2026-08-22 16:17:53",
    ))
    db_session.commit()
    items = [{"producto": "19 7C3Z9601A"}]

    sugerido_service._agregar_reemplazo_ford(items, db_session)

    assert items[0]["vigente_por_crear"] is False
    # El aviso no se pierde: la columna sigue nombrando lo que FORD dijo.
    assert items[0]["reemplazado_por_ford"] == "7C3Z/9601/C/"


# --- El codigo viejo representa al grupo solo mientras haya que despachar --------


def _stock(db, producto, sucursal, cantidad):
    from src.models import DimSucursal, StockUnificado
    if not db.get(DimSucursal, sucursal):
        db.add(DimSucursal(sucursal_id=sucursal, tenant_id="curifor", nombre=sucursal))
    db.add(StockUnificado(tenant_id="curifor", producto=producto, bodega=sucursal,
                          sucursal_id=sucursal, stock=cantidad, origen="CURIFOR"))


def test_con_stock_del_viejo_manda_el_viejo(vigente_ajeno):
    """Quedan unidades que despachar, y estan bajo ese codigo."""
    _stock(vigente_ajeno, "19 7C3Z9601A", "CURICO", 3)
    vigente_ajeno.commit()
    items = [{"producto": "19 7C3Z9601A"}]

    sugerido_service._agregar_reemplazo_ford(items, vigente_ajeno)

    assert items[0]["vigente_por_crear"] is False


def test_sin_stock_del_viejo_manda_el_vigente_de_ford(vigente_ajeno):
    """Ya no hay nada que despachar: lo unico accionable es crear el vigente."""
    items = [{"producto": "19 7C3Z9601A"}]

    sugerido_service._agregar_reemplazo_ford(items, vigente_ajeno)

    assert items[0]["vigente_por_crear"] is True


def test_el_stock_en_una_bodega_virtual_no_cuenta(vigente_ajeno):
    """Una unidad en Bodega Dañados no se le vende a nadie.

    Es el caso de `19 DG1Z8501D`, que tenia stock 1 y era eso. Si contara, el
    codigo muerto quedaria a la vista sin nada que despachar detras.
    """
    from src.models import StockUnificado
    vigente_ajeno.add(StockUnificado(
        tenant_id="curifor", producto="19 7C3Z9601A", bodega="BODEGA DAÑADOS",
        sucursal_id="BODEGA DANADOS", stock=1, origen="CURIFOR"))
    vigente_ajeno.commit()
    items = [{"producto": "19 7C3Z9601A"}]

    sugerido_service._agregar_reemplazo_ford(items, vigente_ajeno)

    assert items[0]["vigente_por_crear"] is True
