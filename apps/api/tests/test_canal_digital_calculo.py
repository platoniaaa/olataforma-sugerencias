"""El calculo de Canal Digital dentro de la plataforma: junta las tablas existentes y corre el nucleo."""
import datetime as dt

from src.canal_digital.ventas_semanales import normalizar_codigo
from src.models import (
    LeadTimeProveedorSucursal, PrecioProducto, ProveedorProducto, StockTransito, StockUnificado,
    Sugerido, VentaHistorica,
)
from src.services import canal_digital_calculo as calc
from src.services import canal_digital_service as svc

HOY = dt.date(2026, 10, 26)  # lunes: la ultima semana completa empieza el 19-10


def _ventas(db, producto, unidades_por_semana=4, cada=1):
    """Una fila por semana de la ventana, con el periodo del documento que corresponde a su fecha."""
    v = calc.ventana(HOY)
    filas = []
    for i, semana in enumerate(v["semanas"]):
        if i % cada:
            continue
        f = dt.date.fromisoformat(semana)
        filas.append({"producto": producto, "semana": semana, "periodo": f"{f.year}{f.month:02d}",
                      "unid_brutas": unidades_por_semana, "unid_devueltas": 0, "valor_costo": 100.0 * unidades_por_semana,
                      "unid_liquidacion": 0, "n_lineas": 1})
    return filas


def test_la_ventana_son_12_meses_cerrados_y_52_semanas_completas():
    v = calc.ventana(HOY)
    assert v["periodos"][0] == "202510" and v["periodos"][-1] == "202609" and len(v["periodos"]) == 12
    assert v["semanas"][-1] == "2026-10-19" and len(v["semanas"]) == 52
    assert all(dt.date.fromisoformat(s).weekday() == 0 for s in v["semanas"])
    assert v["fecha_referencia"] == dt.date(2026, 10, 1)


def test_mapa_de_padres_sale_del_grupo_que_publica_el_motor(db_session):
    db_session.add(Sugerido(tenant_id="curifor", producto="20 M1", sucursal_id="LINDEROS", reemplazos="20 OLD1, 20 OLD2"))
    db_session.add(Sugerido(tenant_id="curifor", producto="20 M1", sucursal_id="SUC2", reemplazos="20 OLD1, 20 OLD2"))
    db_session.commit()
    mapa, conflictos = calc.mapa_padres(db_session)
    assert mapa == {"20 OLD1": "20 M1", "20 OLD2": "20 M1"} and conflictos == 0


def test_un_codigo_en_dos_grupos_se_cuenta_y_no_se_duplica(db_session):
    db_session.add(Sugerido(tenant_id="curifor", producto="20 A", sucursal_id="L", reemplazos="20 X"))
    db_session.add(Sugerido(tenant_id="curifor", producto="20 B", sucursal_id="L", reemplazos="20 X"))
    db_session.commit()
    mapa, conflictos = calc.mapa_padres(db_session)
    assert mapa["20 X"] == "20 A" and conflictos == 1


def test_calcula_con_las_tablas_de_la_plataforma(db_session):
    db = db_session
    svc.asegurar_bodega(db, "430")
    # el codigo viejo y el vigente se funden bajo el vigente
    db.add(Sugerido(tenant_id="curifor", producto="20 M1", sucursal_id="LINDEROS", reemplazos="20 OLD1"))
    filas = _ventas(db, "20 M1", 6) + _ventas(db, "20 OLD1", 2) + _ventas(db, "20 SOLO", 1, cada=7)
    svc.reemplazar_ventas(db, "430", filas)
    # stock: ML suma; ML-FULL y CD quedan aparte; el codigo viejo trae el suyo
    db.add_all([
        StockUnificado(tenant_id="curifor", producto="20 M1", bodega="BODEGA ML", stock=30),
        StockUnificado(tenant_id="curifor", producto="20 OLD1", bodega="BODEGA ML", stock=5),
        StockUnificado(tenant_id="curifor", producto="20 M1", bodega="BODEGA ML-FULL", stock=100),
        StockUnificado(tenant_id="curifor", producto="20 M1", bodega="CD REPUESTOS", stock=900),
    ])
    db.add(PrecioProducto(tenant_id="curifor", producto="20 M1", glosa="ACEITE", costo=1000.0))
    db.add(ProveedorProducto(tenant_id="curifor", producto="20 M1", proveedor="PROV A"))
    db.add(LeadTimeProveedorSucursal(tenant_id="curifor", proveedor="PROV A", sucursal_id=None,
                                     lead_time_dias=6.0, n_muestras=12))
    db.add_all([
        StockTransito(tenant_id="curifor", producto="20 M1", sucursal_id="LINDEROS", cantidad=40),
        StockTransito(tenant_id="curifor", producto="20 M1", sucursal_id="SUC430", cantidad=7),
    ])
    db.add(VentaHistorica(tenant_id="curifor", producto="20 OLD1", sucursal="X", periodo="201901", cantidad=3))
    db.commit()

    corrida, aviso = calc.calcular(db, "430", HOY)
    por = corrida.por_codigo()
    assert set(por) == {"20 M1", "20 SOLO"}, "el codigo viejo no queda suelto"
    m1 = por["20 M1"]
    d = m1.datos
    assert d.codigos_vendidos == "20 M1 | 20 OLD1"
    assert d.stock_disponible == 35 and d.stock_aparte == 100 and d.stock_cd == 900
    assert d.transito == 7 and d.transito_cualquier_destino == 47
    assert d.plazo_motor_dias == 6 and d.plazo_dias == 7  # +1 dia de gestion
    assert d.costo_actual == 1000 and d.descripcion == "ACEITE" and d.proveedor == "PROV A"
    assert d.primera_venta == dt.date(2019, 1, 1)
    assert sum(d.unidades_semana) == 8 * 52 and sum(d.unidades_mes) == 8 * 52 - 8 * (
        sum(1 for s in calc.ventana(HOY)["semanas"] if s >= "2026-10-01"))
    solo = por["20 SOLO"].datos
    assert solo.plazo_dias == 4 and solo.plazo_confianza == "sin proveedor (respaldo)"
    assert aviso["sin_proveedor"] == 1 and aviso["productos"] == 2
    assert aviso["ultimo_mes_con_ventas"] == "202609"
    assert m1.reposicion.posicion == 35 + 7


def test_sin_ventas_en_la_ventana_no_hay_productos(db_session):
    corrida, aviso = calc.calcular(db_session, "430", HOY)
    assert corrida.productos == () and aviso["productos"] == 0 and aviso["ultimo_mes_con_ventas"] is None


def test_normalizar_en_la_union_con_el_stock(db_session):
    """El ERP guarda algunos codigos con espacio al final: el stock debe cruzar igual."""
    db = db_session
    svc.reemplazar_ventas(db, "430", _ventas(db, "15 MXD1454M", 3))
    db.add(StockUnificado(tenant_id="curifor", producto="15 MXD1454M ", bodega="BODEGA ML", stock=12))
    db.commit()
    corrida, _ = calc.calcular(db, "430", HOY)
    assert normalizar_codigo("15 MXD1454M ") in corrida.por_codigo()
    assert corrida.por_codigo()["15 MXD1454M"].datos.stock_disponible == 12
