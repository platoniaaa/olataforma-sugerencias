"""Reposicion al nivel maximo: que un SKU bajo su maximo se reponga siempre.

El caso que motivo la regla (fila real del snapshot del 30-jul-2026):

    13 C5TS7600B3 · Linderos · clase A
    demanda diaria 0,053 · lead time 3 d · stock seguridad 1 · stock 1
    nivel = 0,053 x (5+3) + 1 = 1,42  ->  maximo entero 2  ->  falta 1

Antes el faltante (0,42) se redondeaba a 0 y no se pedia nada.
"""
from src.services import config_modelo_service, nivel_maximo

CONFIG = dict(config_modelo_service.DEFAULTS)


def _fila(**kw) -> dict:
    """Fila del sugerido con lo minimo para el calculo. `kw` pisa lo que haga falta."""
    base = {
        "producto": "P1",
        "sucursal_id": "LINDEROS",
        "clasificacion_abc": "A",
        "clasificacion_abc_agregada": "A",
        "abastece_cd": "No",
        "demanda_diaria": 0.053030303030303,
        "lt_efectivo": 3,
        "stock_seguridad": 1,
        "stock_activo_suc": 1.0,
        "stock_en_transito_suc": 0.0,
        "total_sugerido_suc": 0.0,
        "costo_unitario": 10000.0,
    }
    base.update(kw)
    return base


# --- El nivel maximo es un entero -------------------------------------------------

def test_nivel_maximo_redondea_hacia_arriba():
    # 0,053 x (5+3) + 1 = 1,42 -> el maximo son 2 unidades, no 1,42.
    assert nivel_maximo.nivel_de(_fila(), CONFIG) == 2


def test_sin_demanda_no_hay_nivel():
    """Sin demanda no hay nivel que mantener: la regla no inventa un minimo."""
    assert nivel_maximo.nivel_de(_fila(demanda_diaria=0), CONFIG) is None
    assert nivel_maximo.nivel_de(_fila(demanda_diaria=None), CONFIG) is None


def test_lead_time_por_defecto_cuando_falta():
    # Sin lt_efectivo ni lead_time_dias usa el fallback de configuracion (8 d).
    fila = _fila(lt_efectivo=None, lead_time_dias=None, demanda_diaria=1.0, stock_seguridad=0)
    assert nivel_maximo.nivel_de(fila, CONFIG) == 13  # 1,0 x (5+8)


# --- El caso del usuario ----------------------------------------------------------

def test_maximo_2_con_stock_1_sugiere_1():
    filas = [_fila()]
    resumen = nivel_maximo.aplicar(filas, CONFIG)

    assert filas[0]["nivel_maximo"] == 2
    assert filas[0]["total_sugerido_suc"] == 1
    assert filas[0]["sugerido_suc"] == 1
    assert filas[0]["pedir"] == "Si"
    assert filas[0]["pedir_flag"] == "Si"
    assert filas[0]["total_valor_sugerido_clp"] == 10000
    assert resumen["filas_nuevas"] == 1
    assert resumen["unidades_extra"] == 1


def test_stock_en_el_maximo_no_pide_nada():
    """Ya esta en su nivel: la fila se deja EXACTAMENTE como la mando el motor.

    Ni siquiera se le escribe `pedir`: la regla solo agrega, y tocar una fila que no
    cambia seria pisar la decision del motor con la nuestra."""
    filas = [_fila(stock_activo_suc=2.0, pedir="No", pedir_flag="No")]
    resumen = nivel_maximo.aplicar(filas, CONFIG)
    assert filas[0]["total_sugerido_suc"] == 0.0
    assert filas[0]["pedir"] == "No"
    assert resumen["filas_nuevas"] == 0
    assert resumen["filas_que_suben"] == 0


def test_el_transito_cuenta_como_cubierto():
    """Lo que viene en camino ya llena el maximo: no se pide dos veces."""
    filas = [_fila(stock_activo_suc=0.0, stock_en_transito_suc=2.0)]
    nivel_maximo.aplicar(filas, CONFIG)
    assert filas[0]["total_sugerido_suc"] == 0


# --- Piso: la regla solo agrega ---------------------------------------------------

def test_no_baja_un_sugerido_mayor_del_motor():
    """Hay filas (demanda consolidada del CD, aceites en mL) donde el motor llega a
    un numero mas alto por caminos que esta reconstruccion no reproduce. Bajarlas
    seria dejar de comprar algo que si hace falta."""
    filas = [_fila(total_sugerido_suc=40.0)]
    resumen = nivel_maximo.aplicar(filas, CONFIG)
    assert filas[0]["total_sugerido_suc"] == 40.0
    assert resumen["filas_nuevas"] == 0
    assert resumen["filas_que_suben"] == 0


def test_sube_una_fila_que_ya_pedia_poco():
    filas = [_fila(demanda_diaria=1.0, stock_seguridad=0, stock_activo_suc=0.0,
                   total_sugerido_suc=5.0)]
    resumen = nivel_maximo.aplicar(filas, CONFIG)
    assert filas[0]["total_sugerido_suc"] == 8  # 1,0 x (5+3)
    assert resumen["filas_que_suben"] == 1
    assert resumen["filas_nuevas"] == 0


# --- Alcance por clase ------------------------------------------------------------

def test_clase_d_queda_fuera_con_ab():
    filas = [_fila(clasificacion_abc="D", clasificacion_abc_agregada="D")]
    nivel_maximo.aplicar(filas, CONFIG)
    assert filas[0]["total_sugerido_suc"] == 0
    # El nivel se calcula igual: es informativo y no cambia ninguna decision.
    assert filas[0]["nivel_maximo"] == 2


def test_clase_d_entra_con_abcd():
    filas = [_fila(clasificacion_abc="D", clasificacion_abc_agregada="D")]
    nivel_maximo.aplicar(filas, {**CONFIG, "clases_que_reponen": "ABCD"})
    assert filas[0]["total_sugerido_suc"] == 1


def test_clase_agregada_ab_basta():
    """D local pero A a nivel empresa: el modelo igual lo abastece via CD."""
    filas = [_fila(clasificacion_abc="D", clasificacion_abc_agregada="A")]
    nivel_maximo.aplicar(filas, CONFIG)
    assert filas[0]["total_sugerido_suc"] == 1


def test_regla_apagada_no_toca_el_sugerido():
    filas = [_fila()]
    resumen = nivel_maximo.aplicar(filas, {**CONFIG, "reponer_a_maximo": False})
    assert filas[0]["total_sugerido_suc"] == 0.0
    assert filas[0]["nivel_maximo"] == 2  # se sigue publicando
    assert resumen["activa"] is False


# --- Cadena del CD ----------------------------------------------------------------

def test_el_traslado_se_reparte_por_prioridad():
    """El stock del CD alcanza para la sucursal de prioridad 1 y deja sin nada a la 2:
    la segunda tiene que comprar, no trasladar."""
    comun = {
        "producto": "P1", "abastece_cd": "Si", "stock_en_cd": 1.0,
        "demanda_diaria": 1.0, "lt_efectivo": 3, "stock_seguridad": 0,
        "stock_activo_suc": 7.0, "stock_en_transito_suc": 0.0,
        "total_sugerido_suc": 0.0, "clasificacion_abc": "A",
        "clasificacion_abc_agregada": "A", "costo_unitario": 100.0,
    }
    primera = {**comun, "sucursal_id": "LINDEROS", "prioridad_cd": 1}
    segunda = {**comun, "sucursal_id": "RANCAGUA", "prioridad_cd": 2}
    filas = [segunda, primera]  # desordenadas a proposito

    nivel_maximo.aplicar(filas, CONFIG)

    # Nivel 8 (1,0 x (5+3)), stock 7 -> cada una necesita 1.
    assert primera["total_sugerido_suc"] == 1
    assert segunda["total_sugerido_suc"] == 1
    # La de prioridad 1 se lleva la unica unidad del CD.
    assert primera["sugerido_traslado"] == 1
    assert primera["sugerido_compra_neto"] == 0
    assert segunda["sugerido_traslado"] is None
    assert segunda["sugerido_compra_neto"] == 1
    # El CD ya no da abasto para las dos -> hay que reponerlo.
    assert segunda["comprar_en_el_cd"] == "Si"


def test_compra_directa_no_tiene_traslado():
    filas = [_fila(abastece_cd="No", stock_en_cd=50.0)]
    nivel_maximo.aplicar(filas, CONFIG)
    assert filas[0]["sugerido_traslado"] is None
    assert filas[0]["sugerido_compra_neto"] == 1


def test_no_toca_la_cadena_de_productos_que_no_cambiaron():
    """Si la regla no movio nada de ese producto, se respetan los numeros del motor."""
    fila = _fila(producto="P2", stock_activo_suc=2.0, abastece_cd="Si",
                 sugerido_traslado=99.0, sugerido_compra_neto=99.0)
    nivel_maximo.aplicar([fila], CONFIG)
    assert fila["sugerido_traslado"] == 99.0
    assert fila["sugerido_compra_neto"] == 99.0


# --- De punta a punta: archivo cargado -> fila en la grilla -----------------------

def test_la_carga_aplica_la_regla_y_la_fila_queda_pidiendo(client):
    """El archivo del motor trae la fila en cero; la plataforma la deja pidiendo 1.

    Es la prueba de que la regla vive en la carga: nadie mas tiene que acordarse
    de aplicarla y los KPIs (que suman en SQL) cuadran solos con la tabla.
    """
    import io

    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["producto", "sucursal_id", "nombre_sucursal", "clasificacion_abc",
               "demanda_diaria", "lt_efectivo", "stock_seguridad", "stock_activo_suc",
               "stock_en_transito_suc", "total_sugerido_suc", "costo_unitario", "pedir"])
    # El caso real: nivel 1,42 -> maximo 2, stock 1, el motor manda 0.
    ws.append(["13 C5TS7600B3", "LINDEROS", "Linderos", "A",
               0.053030303030303, 3, 1, 1, 0, 0, 12000, "No"])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    r = client.post(
        "/api/admin/cargar-sugerido",
        files={"file": ("sugerido.xlsx", buf,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r.status_code == 200
    assert r.json()["reposicion_maximo"]["filas_nuevas"] == 1

    # La fila aparece en la grilla con "solo pedir" (antes quedaba escondida).
    datos = client.get("/api/sugerido", params={"solo_pedir": True}).json()
    assert datos["total"] == 1
    fila = datos["items"][0]
    assert fila["producto"] == "13 C5TS7600B3"
    assert fila["nivel_maximo"] == 2
    assert fila["total_sugerido_suc"] == 1
    assert fila["pedir"] == "Si"

    # Y los KPIs dan lo mismo que la tabla.
    kpis = client.get("/api/sugerido/kpis", params={"solo_pedir": True}).json()
    assert kpis["total_sugerido"] == 1
    assert kpis["valor_total_clp"] == 12000
