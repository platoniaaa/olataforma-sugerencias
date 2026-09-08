"""Paginar el sugerido no puede repetir ni perder filas.

El 08-09-2026, bajando el sugerido completo por la API (`solo_pedir=false`,
paginas de 5.000), de 17.129 filas volvieron solo 12.943 distintas: 4.186 pares
(producto, sucursal) llegaron dos veces -la MISMA fila, con el mismo `id`- y
otras tantas nunca llegaron.

La causa no era la data: el orden por defecto es `total_sugerido_suc DESC` y con
`solo_pedir=false` casi todas las filas valen 0 o NULL ahi. Entre filas empatadas
la base no promete ningun orden, y `offset`/`limit` se apoya justamente en ese
orden para saber donde cortar cada pagina. Sin un desempate unico, cada consulta
puede ordenar distinto y las paginas se solapan.

Esto no es solo un problema al exportar: la tabla de la pantalla pide sus filas
por pagina igual que el script.
"""
from src.models import Sugerido
from src.services import sugerido_service
from src.services.sugerido_service import _apply_sort


def _ultimo_criterio(sort) -> str:
    """Como queda la ULTIMA clausula del ORDER BY. Comparar contra el texto
    completo y no buscar "id" adentro: "sugerido" lo contiene."""
    from sqlalchemy import select
    return str(list(_apply_sort(select(Sugerido), sort)._order_by_clauses)[-1])


def test_el_orden_por_defecto_desempata_por_id():
    assert _ultimo_criterio(None) == "sugerido.id"


def test_el_orden_pedido_por_el_usuario_tambien_desempata():
    assert _ultimo_criterio("-total_sugerido_suc") == "sugerido.id"
    assert _ultimo_criterio("producto") == "sugerido.id"


def test_un_campo_que_no_existe_cae_al_default_y_tambien_desempata():
    assert _ultimo_criterio("no_existe") == "sugerido.id"


def test_paginar_no_repite_ni_pierde_filas(db_session):
    """Todas empatadas en `total_sugerido_suc`, que es el caso real."""
    from src.schemas.sugerido import SugeridoFiltros

    for i in range(25):
        db_session.add(Sugerido(
            tenant_id="curifor", producto=f"17 P{i:03d}", sucursal_id="LINDEROS",
            nombre_sucursal="LINDEROS", clasificacion_abc="D", pedir="No",
            total_sugerido_suc=0.0,
        ))
    db_session.commit()

    f = SugeridoFiltros(solo_pedir=False)
    _, total = sugerido_service.listar(db_session, f, page=1, limit=5)

    vistos = []
    for page in range(1, (total + 4) // 5 + 1):
        items, _ = sugerido_service.listar(db_session, f, page=page, limit=5)
        vistos.extend(i["producto"] for i in items)

    assert len(vistos) == len(set(vistos)), "una fila volvio en dos paginas"
    mios = {f"17 P{i:03d}" for i in range(25)}
    assert mios <= set(vistos), f"se perdieron {len(mios - set(vistos))} filas al paginar"
