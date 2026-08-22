"""La fila InStock cuelga del codigo VIGENTE, no del que FORD dio de baja.

Las pautas de mantencion de FORD traen part numbers que despues se
descontinuaron. El cruce que resuelve el codigo del ERP busca el MISMO part
number bajo otro rubro ("28 2151323001" y "95 2151323001" son la misma golilla),
y eso no sirve aca: el vigente es un part number DISTINTO — `BR3Z8620S` pasa a
`RB5Z8620D`.

Sin este paso la fila InStock quedaba colgada del codigo muerto, y era lo que se
veia en pantalla: el sugerido pedia `19 BR3Z8620S`, `25 KV6Z9155D` y
`17 GK2Z9365A` teniendo los tres su vigente en el catalogo. El motor agrupaba
bien; el problema era que la fila InStock se inyecta aparte y no pasaba por esa
agrupacion.
"""
import pytest

from src.jobs import cargar_instock as job
from src.models import ProductoCatalogo, ReemplazoFord, RepuestoInstock, Sugerido


def _pautas_csv(tmp_path, filas: list[str]):
    p = tmp_path / "pautas.csv"
    p.write_text(
        "part_number;marca;modelos;operacion;detalle\n" + "\n".join(filas),
        encoding="utf-8",
    )
    return p


@pytest.fixture()
def base(db_session):
    """El par real: la pauta pide BR3Z8620S y FORD ya lo reemplazo."""
    db_session.add_all([
        ProductoCatalogo(tenant_id="curifor", producto="19 BR3Z8620S",
                         glosa="CORREA DE ACCESORIOS A/C"),
        ProductoCatalogo(tenant_id="curifor", producto="19 RB5Z8620D",
                         glosa="CORREA DE ACCESORIOS A/C"),
    ])
    # El motor agrupo: el sugerido tiene UNA fila, la del master (el vigente).
    db_session.add(Sugerido(tenant_id="curifor", producto="19 RB5Z8620D",
                            sucursal_id="RANCAGUA"))
    db_session.add(ReemplazoFord(
        tenant_id="curifor", producto="19 BR3Z8620S",
        reemplazado_por="19 RB5Z8620D", reemplazado_por_ford="RB5Z/8620/D/",
        cadena="BR3Z/8620/S/ > RB5Z/8620/D/",
        sucesor_confirmado=True, agrupado=True,
    ))
    db_session.commit()
    return db_session


def test_la_fila_instock_cuelga_del_vigente(base, tmp_path):
    csv = _pautas_csv(tmp_path, ["BR3Z8620S;FORD;Ranger;Correa de Accesorios A/C;"])

    job.cargar_en(base, job._leer_csv(csv))

    filas = base.query(RepuestoInstock).all()
    assert len(filas) == 1
    assert filas[0].producto == "19 RB5Z8620D"
    # El part number de la pauta se conserva: es con lo que Abastecimiento la
    # busca, y perderlo haria imposible rastrear de donde salio la fila.
    assert filas[0].part_number == "BR3Z8620S"


def test_el_codigo_dado_de_baja_deja_de_tener_fila(base, tmp_path):
    csv = _pautas_csv(tmp_path, ["BR3Z8620S;FORD;Ranger;Correa de Accesorios A/C;"])

    job.cargar_en(base, job._leer_csv(csv))

    productos = {f.producto for f in base.query(RepuestoInstock).all()}
    assert "19 BR3Z8620S" not in productos


def test_si_el_motor_no_agrupo_se_queda_con_el_codigo_de_la_pauta(base, tmp_path):
    """`agrupado=False` significa que el stock de los dos codigos se cuenta por
    separado. Colgar el minimo del vigente ahi pediria de mas: se exigiria su
    minimo completo sin descontar lo que hay del viejo."""
    r = base.query(ReemplazoFord).first()
    r.agrupado = False
    base.commit()
    csv = _pautas_csv(tmp_path, ["BR3Z8620S;FORD;Ranger;Correa de Accesorios A/C;"])

    job.cargar_en(base, job._leer_csv(csv))

    filas = base.query(RepuestoInstock).all()
    assert len(filas) == 1
    assert filas[0].producto == "19 BR3Z8620S"


def test_sin_reemplazo_todo_sigue_igual(db_session, tmp_path):
    """El caso de control: un repuesto de pauta que FORD no toco no cambia."""
    db_session.add(ProductoCatalogo(tenant_id="curifor", producto="19 AA5Z6714A",
                                    glosa="FILTRO ACEITE"))
    db_session.commit()
    csv = _pautas_csv(tmp_path, ["AA5Z6714A;FORD;F-150;Filtro de Aceite;"])

    job.cargar_en(db_session, job._leer_csv(csv))

    filas = db_session.query(RepuestoInstock).all()
    assert len(filas) == 1
    assert filas[0].producto == "19 AA5Z6714A"


def test_vigentes_de_ignora_los_que_no_agrupan(base):
    """La funcion sola, para que el criterio quede fijado aparte del job."""
    assert job.vigentes_de(base, {"19 BR3Z8620S"}) == {"19 BR3Z8620S": "19 RB5Z8620D"}

    r = base.query(ReemplazoFord).first()
    r.agrupado = False
    base.commit()
    assert job.vigentes_de(base, {"19 BR3Z8620S"}) == {}


def test_vigentes_de_sin_codigos_no_consulta(db_session):
    assert job.vigentes_de(db_session, set()) == {}
