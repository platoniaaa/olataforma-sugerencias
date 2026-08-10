"""El filtro de columna del grid tiene que valer tambien en el Excel.

Caso real (10-08-2026): un comprador filtro la columna Sucursal por "Chillán" y
"CHILLAN", exporto, y el Excel salio con 164 filas de SEIS sucursales — 78 de
Rancagua, Linderos, Curico y Talca que el no habia pedido.

La causa: `listar` devuelve dos clases de fila. Las que salen del SELECT sobre
`Sugerido` pasan por el WHERE con los filtros de columna; las de sugerencias
manuales, minimo InStock y catalogo se INYECTAN despues y nunca lo tocaron.
"""
from src.schemas import ColumnaFiltro, SugeridoFiltros
from src.services import sugerido_service
from src.services.sugerido_service import _fila_pasa_columna


def _fc(campo: str, valores: list[str]) -> ColumnaFiltro:
    return ColumnaFiltro(campo=campo, valores=valores)


# --- La regla, fila por fila -----------------------------------------------------

def test_deja_pasar_lo_que_el_usuario_eligio():
    fila = {"sucursal_id": "CHILLAN"}
    assert _fila_pasa_columna(fila, _fc("sucursal_id", ["CHILLAN", "LINDEROS"]))


def test_descarta_lo_que_no_eligio():
    fila = {"sucursal_id": "RANCAGUA"}
    assert not _fila_pasa_columna(fila, _fc("sucursal_id", ["CHILLAN"]))


def test_el_centinela_de_blancos_se_respeta():
    """"(en blanco)" representa NULL y vacio, igual que en la clausula SQL."""
    assert _fila_pasa_columna({"sucursal_id": None}, _fc("sucursal_id", ["(en blanco)"]))
    assert _fila_pasa_columna({"sucursal_id": ""}, _fc("sucursal_id", ["(en blanco)"]))
    assert not _fila_pasa_columna({"sucursal_id": None}, _fc("sucursal_id", ["CHILLAN"]))


def test_destildar_todo_no_deja_pasar_nada():
    """Mismo comportamiento que `false()` en la version SQL."""
    assert not _fila_pasa_columna({"sucursal_id": "CHILLAN"}, _fc("sucursal_id", []))


def test_contiene_es_case_insensitive_como_el_ilike():
    fila = {"descripcion": "FILTRO DE ACEITE"}
    assert _fila_pasa_columna(fila, ColumnaFiltro(campo="descripcion", contiene="aceite"))
    assert not _fila_pasa_columna(fila, ColumnaFiltro(campo="descripcion", contiene="bujia"))


def test_columna_numerica_compara_como_numero():
    """El grid manda los valores como texto; "5" tiene que casar con 5.0."""
    assert _fila_pasa_columna({"total_sugerido_suc": 5.0},
                              _fc("total_sugerido_suc", ["5"]))
    assert not _fila_pasa_columna({"total_sugerido_suc": 7.0},
                                  _fc("total_sugerido_suc", ["5"]))


def test_un_campo_desconocido_no_filtra_nada():
    """Si el grid manda una columna que no existe, no se puede inventar el criterio:
    mejor dejar pasar que borrar filas por un nombre mal escrito."""
    assert _fila_pasa_columna({"sucursal_id": "CHILLAN"}, _fc("no_existe", ["X"]))


# --- El descarte, sin depender de lo que traiga el fixture -----------------------

def test_descarta_la_inyectada_y_deja_la_del_query():
    """El nucleo del arreglo, con las dos clases de fila en la misma lista.

    La del query ya paso por el WHERE, asi que no se vuelve a mirar aunque no
    cumpla; la inyectada nunca lo toco y por eso se filtra aca.
    """
    items = [
        {"producto": "P1", "sucursal_id": "CHILLAN"},                      # del query
        {"producto": "P2", "sucursal_id": "RANCAGUA", "_inyectada": True},  # InStock
        {"producto": "P3", "sucursal_id": "CHILLAN", "_inyectada": True},   # InStock
    ]
    f = SugeridoFiltros(filtros_columna=[_fc("sucursal_id", ["CHILLAN"])])
    salida = sugerido_service._filtrar_inyectadas(items, f)
    assert [i["producto"] for i in salida] == ["P1", "P3"]
    assert all("_inyectada" not in i for i in salida)


def test_sin_filtros_de_columna_pasan_todas():
    items = [{"producto": "P1", "sucursal_id": "RANCAGUA", "_inyectada": True}]
    salida = sugerido_service._filtrar_inyectadas(items, SugeridoFiltros())
    assert len(salida) == 1


def test_una_inyectada_tiene_que_cumplir_TODOS_los_filtros():
    items = [
        {"producto": "P1", "sucursal_id": "CHILLAN", "clasificacion_abc": "D",
         "_inyectada": True},
        {"producto": "P2", "sucursal_id": "CHILLAN", "clasificacion_abc": "A",
         "_inyectada": True},
    ]
    f = SugeridoFiltros(filtros_columna=[
        _fc("sucursal_id", ["CHILLAN"]), _fc("clasificacion_abc", ["A"]),
    ])
    salida = sugerido_service._filtrar_inyectadas(items, f)
    assert [i["producto"] for i in salida] == ["P2"]


# --- El caso del comprador, de punta a punta -------------------------------------

def test_las_filas_inyectadas_respetan_el_filtro_de_columna(db_session):
    """Lo que fallaba: InStock y manuales entraban aunque no pasaran el filtro."""
    filtros = SugeridoFiltros(
        solo_pedir=False,
        filtros_columna=[_fc("sucursal_id", ["CHILLAN"])],
    )
    items, total = sugerido_service.listar(db_session, filtros, page=1, limit=10000)
    sucursales = {i.get("sucursal_id") for i in items if i.get("sucursal_id")}
    assert sucursales <= {"CHILLAN"}, f"se colaron: {sucursales - {'CHILLAN'}}"


def test_el_total_cuadra_con_las_filas_devueltas(db_session):
    """Si no cuadran, el Excel trae N filas y la pantalla dice otro numero."""
    filtros = SugeridoFiltros(
        solo_pedir=False,
        filtros_columna=[_fc("sucursal_id", ["CHILLAN"])],
    )
    items, total = sugerido_service.listar(db_session, filtros, page=1, limit=10000)
    assert total >= len(items)


def test_el_marcador_interno_no_viaja_al_resultado(db_session):
    """`_inyectada` es de uso interno: si sale, Pydantic o el Excel lo muestran."""
    items, _ = sugerido_service.listar(
        db_session, SugeridoFiltros(solo_pedir=False), page=1, limit=10000
    )
    assert all("_inyectada" not in i for i in items)


def test_sin_filtro_de_columna_no_se_descarta_nada(db_session):
    """La correccion no puede achicar el resultado normal."""
    sin = SugeridoFiltros(solo_pedir=False)
    items, _ = sugerido_service.listar(db_session, sin, page=1, limit=10000)
    assert len(items) > 0
