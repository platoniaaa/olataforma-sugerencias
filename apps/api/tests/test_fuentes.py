"""Fuentes de datos (/api/admin/fuentes): configuracion, reportes del motor y equipo.

El semaforo (reglas de §3.6) tiene su propio archivo: test_fuentes_semaforo.py.

Los datos de prueba reproducen la semilla del motor (17 fuentes: 13 que lee y 4 que
solo reconoce, dos carpetas) y el listado de carpetas de un dia normal. Los PCs, los
correos y la URL de SharePoint son ficticios.
"""
import copy
import inspect
import json
from datetime import datetime, timedelta

import pytest

from src import db as db_modulo
from src.main import app
from src.models import AuditoriaLog, FuenteConfig, MotorCorrida, Notificacion, Usuario
from src.services import fuentes_service
from src.services.auth import hash_password, requiere_auth
from src.services.calendario import TZ_CHILE

URL = "/api/admin/fuentes"
PC = "PC-ABAST-01"
PC_JEFA = "PC-JEFA-01"
MOTOR = "motor@ejemplo.com"

# --------------------------------------------------------------------------- #
# La semilla del motor (config_efectiva)
# --------------------------------------------------------------------------- #
CARPETAS = [
    {"clave": "bases_de_datos", "nombre": "Bases de datos", "tipo": "onedrive",
     "params": {"ruta": "Documentos/Desarrollos/Bases de datos"},
     "rutas_por_pc": {}, "activa": True},
    {"clave": "databi_datos", "nombre": "Data BI › Datos (SharePoint del equipo)",
     "tipo": "sharepoint",
     "params": {"sitio_url": "https://ejemplo.sharepoint.com/sites/AbastecimientoyLogistica-DataBI",
                "biblioteca": "Documentos compartidos", "ruta": "Data BI/Datos",
                "nombre_atajo": "Abastecimiento y Logística-Data BI - Datos"},
     "rutas_por_pc": {}, "activa": True},
]

_LEE = {"uso": "lee", "modos": ["archivo_exacto", "mas_reciente"]}
CATALOGO = {
    "stock_bodegas": {**_LEE, "requerida": True, "frecuencia_max": 5, "al_vencer_fijo": "frena",
                      "efecto_si_falta": "Sin stock el motor no calcula."},
    "stock_bodegas_frontera": {**_LEE, "requerida": True, "frecuencia_max": 5,
                               "al_vencer_fijo": "frena",
                               "efecto_si_falta": "Sin stock el motor no calcula."},
    "ventas": {"uso": "lee", "requerida": True, "modos": ["por_descarte"],
               "efecto_si_falta": "Sin ventas el motor no calcula."},
    "seguimiento_curifor_nacional": {**_LEE, "frecuencia_max": 5, "al_vencer_fijo": "frena",
                                     "efecto_si_falta": "El tránsito nacional sale en cero."},
    "seguimiento_curifor_importado": {**_LEE, "efecto_si_falta": "El tránsito importado sale en cero."},
    "seguimiento_frontera": {**_LEE, "efecto_si_falta": "El tránsito de Frontera sale en cero."},
    "mix_reemplazos": {**_LEE, "efecto_si_falta": "Los reemplazos no se consideran."},
    "catalogo": {**_LEE, "efecto_si_falta": "No se excluyen COLISION ni CAMPANAS."},
    "ventas_frontera": {**_LEE, "efecto_si_falta": "La demanda de Frontera no se suma."},
    "lista_erp": {**_LEE, "efecto_si_falta": "La lista de precios no recibe repuestos nuevos."},
    "precios_ford": {**_LEE, "efecto_si_falta": "No se calcula el margen con precios Ford."},
    "precios_gildemeister": {**_LEE, "efecto_si_falta": "No se calcula el margen con precios "
                                                        "Gildemeister."},
    "vigentes_ford": {**_LEE, "efecto_si_falta": "No se usan los reemplazos vigentes de Ford."},
    "lista_new_wings": {"uso": "reconoce", "modos": ["mas_reciente"]},
    "precios_proveedor": {"uso": "reconoce", "modos": ["mas_reciente"]},
    "dim_sucursal": {"uso": "reconoce", "modos": ["mas_reciente"]},
    "pautas_mantencion": {"uso": "reconoce", "modos": ["mas_reciente"]},
}

_BD = [{"carpeta": "bases_de_datos", "subcarpeta": "", "recursiva": True}]
_STOCK = _BD + [{"carpeta": "databi_datos", "subcarpeta": "", "recursiva": False}]


def _f(clave, nombre, incluye, excluye=(), *, ubic=_BD, freq=None, al="frena", oblig=False,
       modo="mas_reciente", ext=(".xlsx", ".xlsm", ".csv"), hoja=None, fila=None):
    return {"clave": clave, "nombre": nombre, "ubicaciones": copy.deepcopy(list(ubic)),
            "modo": modo, "nombre_archivo": None, "incluye": list(incluye),
            "excluye": list(excluye), "extensiones": list(ext), "frecuencia_dias": freq,
            "al_vencer": al, "obligatoria": oblig, "activa": True,
            "diferencia_esperada": False, "hoja": hoja, "fila_encabezado": fila}


FUENTES = [
    _f("stock_bodegas", "Stock bodegas Curifor", ["*stock*bodega*"], ["*frontera*"],
       ubic=_STOCK, freq=2, oblig=True),
    _f("stock_bodegas_frontera", "Stock bodegas Frontera",
       ["*stock*frontera*", "*stock*bodegas*frontera*"], ubic=_STOCK, freq=2, oblig=True),
    _f("ventas", "Respaldos de ventas", ["*venta*"],
       ["*presupuesto*", "*post*venta*", "*produccion*"], modo="por_descarte", ext=(".xlsx",),
       oblig=True),
    _f("seguimiento_curifor_nacional", "Seguimiento de compras nacional", ["*seguimiento*"],
       ["*importado*", "*frontera*"], freq=2, oblig=True, fila=1),
    _f("seguimiento_curifor_importado", "Seguimiento de compras importado",
       ["*seguimiento*importado*"], freq=7, oblig=True, fila=1),
    _f("seguimiento_frontera", "Seguimiento de compras Frontera",
       ["*frontera*seguimiento*", "*seguimiento*frontera*"], freq=7, oblig=True, fila=1),
    _f("mix_reemplazos", "Mix de reemplazos", ["*mix*", "*reemplaz*"], ["*~*"], freq=120,
       oblig=True, fila=1),
    _f("catalogo", "Maestro de repuestos",
       ["*maestro*", "*listado*maestro*", "*lista*rep*", "lista de precios.*",
        "lista de precios curifor.*"], ["*stock*", "*venta*", "*seguimiento*"], freq=120,
       oblig=True, hoja="Lista sin duplicados"),
    _f("ventas_frontera", "Ventas Frontera",
       ["*vta*frontera*", "*venta*frontera*", "*frontera*vta*", "*frontera*venta*"],
       ["*stock*", "*seguimiento*"], freq=35, al="avisa"),
    _f("lista_erp", "Lista del ERP", ["lista_erp.*", "lista erp.*", "listaerp.*"],
       ["*proveedor*", "*ford*", "*gildemeister*"], freq=10, al="avisa", hoja=0),
    _f("precios_ford", "Lista de precios Ford", ["*precio*ford*", "*ford*precio*"],
       ["*gildemeister*"], hoja="Precios"),
    _f("precios_gildemeister", "Lista de precios Gildemeister",
       ["*precio*gildemeister*", "*gildemeister*precio*"], ["*ford*"], hoja="Precios"),
    _f("vigentes_ford", "Vigentes Ford", ["*vigentes*ford*"], hoja="Precios"),
    _f("lista_new_wings", "Lista new (WINGS)", ["lista_new*"]),
    _f("precios_proveedor", "Otras listas de proveedor", ["*lista*de*precio*"],
       ["lista de precios.*", "lista de precios curifor.*", "*maestro*", "*lista*rep*",
        "*stock*", "*seguimiento*"], hoja="Precios"),
    _f("dim_sucursal", "Sucursales", ["*sucursal*", "*dim*local*"],
       ["*seguimiento*", "*stock*", "*venta*"]),
    _f("pautas_mantencion", "Pautas de mantención", ["*pauta*"]),
]
LEE = [f["clave"] for f in FUENTES if CATALOGO[f["clave"]]["uso"] == "lee"]


def config_efectiva(**cambios) -> dict:
    datos = {"catalogo": copy.deepcopy(CATALOGO), "carpetas": copy.deepcopy(CARPETAS),
             "fuentes": copy.deepcopy(FUENTES)}
    datos.update(cambios)
    return datos


# --------------------------------------------------------------------------- #
# El listado de un dia normal y lo que el motor elige
# --------------------------------------------------------------------------- #
DIA = "2026-10-15"   # jueves


def _hora(h: str, dia: str = DIA) -> str:
    return f"{dia}T{h}:00-03:00"


ARCHIVOS_BD = [
    # El motor corre en Windows: las rutas relativas llegan con "\".
    ("stock\\Stock bodegas.xlsx", "07:40", 2_100_000),
    ("stock\\stock_frontera.xlsx", "07:41", 900_000),
    ("Seguimientos de compras\\Curifor - Seguimiento Compras.xlsx", "07:45", 500_000),
    ("Seguimientos de compras\\Seguimiento importado.xlsx", "07:45", 300_000),
    ("Seguimientos de compras\\Frontera seguimiento.xlsx", "07:46", 200_000),
    ("Ventas\\2026 (6).xlsx", "08:00", 40_000_000),
    ("Ventas\\2025 (4).xlsx", "08:00", 60_000_000),
    ("Ventas\\Motorcraft 2026.xlsx", "08:00", 30_000),
    ("BASE NUEVO MIX 2026_1.xlsx", "08:00", 800_000),
    ("LISTA DE PRECIOS.xlsx", "08:00", 104_000_000),
    ("lista_erp.xlsx", "08:00", 3_000_000),
    ("vtas frontera.xlsx", "08:00", 1_000_000),
    ("Lista de precio ford al 28.07.2026.xlsx", "08:00", 5_000_000),
    ("Precios Gildemeister 20260728.xlsx", "08:00", 2_000_000),
    ("vigentes ford.xlsx", "08:00", 1_500_000),
    ("Pauta de mantención Baic Enero 2026.xlsx", "08:00", 100_000),
    ("dim sucursal.xlsx", "08:00", 10_000),
    ("lista_new_wings.xlsx", "08:00", 10_000),
]
ARCHIVOS_DATABI = [
    ("Stock bodegas.xlsx", "09:34", 2_100_000),
    ("stock_frontera.xlsx", "09:34", 900_000),
    ("Curifor - Seguimiento Compras.xlsx", "09:20", 500_000),
    ("Frontera - Produccion Mensual Post-Venta.xlsx", "09:20", 700_000),
    ("Anteriores\\Stock bodegas.xlsx", "09:00", 2_000_000),
]

# clave -> (carpeta, ruta_relativa, hora, filas). Ventas trae dos.
ELEGIDOS = {
    "stock_bodegas": [("databi_datos", "Stock bodegas.xlsx", "09:34", 19883)],
    "stock_bodegas_frontera": [("databi_datos", "stock_frontera.xlsx", "09:34", 4120)],
    "ventas": [("bases_de_datos", "Ventas\\2025 (4).xlsx", "08:00", None),
               ("bases_de_datos", "Ventas\\2026 (6).xlsx", "08:00", None)],
    "seguimiento_curifor_nacional": [("bases_de_datos",
                                      "Seguimientos de compras\\Curifor - Seguimiento Compras.xlsx",
                                      "07:45", 812)],
    "seguimiento_curifor_importado": [("bases_de_datos",
                                       "Seguimientos de compras\\Seguimiento importado.xlsx",
                                       "07:45", 120)],
    "seguimiento_frontera": [("bases_de_datos", "Seguimientos de compras\\Frontera seguimiento.xlsx",
                              "07:46", 90)],
    "mix_reemplazos": [("bases_de_datos", "BASE NUEVO MIX 2026_1.xlsx", "08:00", 3000)],
    "catalogo": [("bases_de_datos", "LISTA DE PRECIOS.xlsx", "08:00", 39000)],
    "ventas_frontera": [("bases_de_datos", "vtas frontera.xlsx", "08:00", 5000)],
    "lista_erp": [("bases_de_datos", "lista_erp.xlsx", "08:00", 40000)],
    "precios_ford": [("bases_de_datos", "Lista de precio ford al 28.07.2026.xlsx", "08:00", 39622)],
    "precios_gildemeister": [("bases_de_datos", "Precios Gildemeister 20260728.xlsx", "08:00", 8000)],
    "vigentes_ford": [("bases_de_datos", "vigentes ford.xlsx", "08:00", 9000)],
}


def listados(dia: str = DIA, *, sin: tuple = ()) -> list[dict]:
    def _l(clave, archivos, ruta_portable):
        return {
            "clave": clave, "existe": clave not in sin, "metodo": "onedrive",
            "ruta_portable": ruta_portable,
            "ruta_absoluta": "C:\\Users\\usuario\\OneDrive - Empresa\\"
                             + ruta_portable[len("%OneDriveCommercial%\\"):],
            "truncado": False,
            "archivos": [] if clave in sin else [
                {"ruta_relativa": r, "tamano": t, "modificado_en": _hora(h, dia),
                 "onedrive": "local", "fuente": None, "elegido": False}
                for r, h, t in archivos
            ],
        }
    return [
        _l("bases_de_datos", ARCHIVOS_BD, "%OneDriveCommercial%\\Documentos\\Desarrollos\\Bases de datos"),
        _l("databi_datos", ARCHIVOS_DATABI,
           "%OneDriveCommercial%\\Abastecimiento y Logística-Data BI - Datos"),
    ]


def estado(clave: str, dia: str = DIA, *, prueba: str | None = None, **extra) -> dict:
    archivos = [
        {"carpeta": c, "ruta_relativa": r, "modificado_en": _hora(h, dia), "tamano": 1000,
         "sha256": f"sha-{clave}-{dia}-{i}", "onedrive": "local"}
        for i, (c, r, h, _f) in enumerate(ELEGIDOS[clave])
    ]
    e = {"hecho": "encontrado", "archivos": archivos, "candidatos": len(archivos),
         "descartados": [], "filas": ELEGIDOS[clave][0][3], "hoja_leida": "Hoja1",
         "mismo_contenido_que_anterior": False, "abierto_en_excel": False, "extra": {}}
    if clave == "ventas":
        e["extra"] = {"periodo_ultimo_mes": "202609", "total_mes_cerrado": 1_234_567.0}
        e["descartados"] = [{"nombre": "Motorcraft 2026.xlsx",
                             "motivo": "no tiene forma de respaldo de venta"}]
    if clave == "stock_bodegas":
        e["carpetas_con_candidatos"] = ["bases_de_datos", "databi_datos"]
    if prueba:
        e["prueba"] = {"resultado": prueba, "archivo": ELEGIDOS[clave][0][1]}
    e.update(extra)
    return e


def fuentes_del_dia(dia: str = DIA, *, prueba: str | None = None) -> dict:
    return {c: estado(c, dia, prueba=prueba) for c in ELEGIDOS}


def _mas(iso: str, minutos: int) -> str:
    return (datetime.fromisoformat(iso) + timedelta(minutes=minutos)).isoformat()


def mandar(client, id: str, *, fase: str = "fin", pc: str = PC, tipo: str = "oficial",
           resultado: str = "ok", fuentes: dict | None = None, carpetas: list | None = None,
           config_origen: str = "env", config_version: int | None = None,
           iniciada_en: str | None = None, motivo: str | None = None,
           efectiva: dict | None | bool = True, extra_reporte: dict | None = None,
           publico: bool | None = None, esperado: int = 200):
    iniciada_en = iniciada_en or _hora("09:30")
    cuerpo = {
        "id": id, "fase": fase, "pc": pc, "tipo": tipo, "iniciada_en": iniciada_en,
        "config_origen": config_origen, "config_version": config_version,
        "version_motor": "4de6a2e arreglar-job-diario", "titular": True,
        "publico": publico if publico is not None else (tipo == "oficial" and resultado == "ok"),
        "reporte": {"fuentes": fuentes if fuentes is not None else fuentes_del_dia(),
                    "carpetas": carpetas if carpetas is not None else listados(),
                    "avisos": [], **(extra_reporte or {})},
    }
    if efectiva is True:
        cuerpo["config_efectiva"] = config_efectiva()
    elif isinstance(efectiva, dict):
        cuerpo["config_efectiva"] = efectiva
    if fase == "fin":
        cuerpo["resultado"] = resultado
        cuerpo["terminada_en"] = _mas(iniciada_en, 28)
        cuerpo["motivo"] = motivo
    r = client.post(f"{URL}/reporte", json=cuerpo)
    assert r.status_code == esperado, r.text
    return r.json()


def sembrado(client, *, pc: str = PC, efectiva: dict | None = None,
             carpetas: list | None = None) -> dict:
    """Siembra desde una corrida `probar` de ese PC (Anexo C: no hace falta esperar a
    una oficial). Corre a las 08:00, antes que las oficiales de las 09:30."""
    mandar(client, f"siembra-{pc}", tipo="probar", pc=pc, iniciada_en=_hora("08:00"),
           efectiva=efectiva if efectiva is not None else True, carpetas=carpetas)
    r = client.post(f"{URL}/sembrar", json={"corrida_id": f"siembra-{pc}"})
    assert r.status_code == 200, r.text
    return r.json()


def config(client) -> dict:
    return client.get(f"{URL}/config").json()


def fuente(cfg: dict, clave: str) -> dict:
    return next(f for f in cfg["fuentes"] if f["clave"] == clave)


@pytest.fixture()
def como(client, db_session):
    """Permite ejecutar peticiones como un email cualquiera."""
    def _como(email: str):
        app.dependency_overrides[requiere_auth] = lambda: email
    yield _como
    app.dependency_overrides[requiere_auth] = lambda: "test@curifor.com"


def _usuario(db, email, *, admin=False, activo=True):
    db.add(Usuario(email=email, password_hash=hash_password("123456"), nombre="Usuario de prueba",
                   es_admin=admin, activo=activo))
    db.commit()


# --------------------------------------------------------------------------- #
# 1. Acceso
# --------------------------------------------------------------------------- #
def test_un_no_admin_recibe_403_en_cada_endpoint(client, como):
    como("noadmin@curifor.com")
    pedidos = [
        ("get", URL, None),
        ("get", f"{URL}/config", None),
        ("post", f"{URL}/reporte", {"id": "x", "fase": "inicio", "pc": PC, "tipo": "probar"}),
        ("get", f"{URL}/corridas", None),
        ("get", f"{URL}/carpetas/bases_de_datos/archivos", None),
        ("get", f"{URL}/stock_bodegas", None),
        ("post", f"{URL}/stock_bodegas/vista-previa", {"cambios": {}}),
        ("put", f"{URL}/stock_bodegas", {"cambios": {}, "nota": "x", "base_version": 1}),
        ("post", f"{URL}/carpetas", {"carpeta": {"clave": "x", "nombre": "X", "tipo": "onedrive",
                                                 "params": {"ruta": "Documentos/X"}},
                                     "nota": "x", "base_version": 1}),
        ("put", f"{URL}/carpetas/bases_de_datos", {"cambios": {}, "nota": "x", "base_version": 1}),
        ("put", f"{URL}/pcs/{PC}", {"alias": "PC de prueba", "base_version": 1}),
        ("post", f"{URL}/titular", {"pc": PC, "nota": "x", "base_version": 1}),
        ("post", f"{URL}/modo", {"modo": "activa", "nota": "x", "base_version": 1}),
        ("post", f"{URL}/sembrar", {"corrida_id": "x"}),
        ("post", f"{URL}/revertir/1", {}),
    ]
    for metodo, url, cuerpo in pedidos:
        r = getattr(client, metodo)(url, json=cuerpo) if cuerpo is not None \
            else getattr(client, metodo)(url)
        assert r.status_code == 403, (metodo, url, r.status_code)


# --------------------------------------------------------------------------- #
# 2. Configuracion inicial
# --------------------------------------------------------------------------- #
def test_con_la_base_vacia_el_motor_recibe_sin_configurar(client):
    assert client.get(f"{URL}/config").json() == {"modo": "sin_configurar"}
    panel = client.get(URL).json()
    assert panel["modo"] == "sin_configurar"
    assert panel["modo_texto"] == "Sin configurar"
    assert panel["fuentes"] == []
    assert panel["activacion"]["puede_activar"] is False


def test_las_tablas_nuevas_no_agregan_alter_table():
    """Las dos tablas son nuevas: las crea create_all, sin lineas en `migraciones`."""
    fuente_db = inspect.getsource(db_modulo.create_all)
    assert "fuente_config" not in fuente_db
    assert "motor_corrida" not in fuente_db


def test_sembrar_copia_la_configuracion_deja_prueba_y_el_titular(client):
    mandar(client, "c-probar", tipo="probar")
    # Sin configurar, el panel ofrece sembrar desde esa corrida.
    panel = client.get(URL).json()
    assert [s["corrida_id"] for s in panel["sembrar_desde"]] == ["c-probar"]

    r = client.post(f"{URL}/sembrar", json={"corrida_id": "c-probar"})
    assert r.status_code == 200, r.text
    assert r.json()["version"] == 1 and r.json()["modo"] == "prueba"

    cfg = config(client)
    assert cfg["modo"] == "prueba"
    assert cfg["version"] == 1
    assert cfg["pc_titular"] == PC
    assert PC in cfg["pcs"]
    assert [f["clave"] for f in cfg["fuentes"]] == [f["clave"] for f in FUENTES]
    assert fuente(cfg, "stock_bodegas")["incluye"] == ["*stock*bodega*"]
    assert cfg["catalogo"]["ventas"]["modos"] == ["por_descarte"]
    assert cfg["hash"] == fuentes_service.hash_config(
        {k: cfg[k] for k in ("modo", "pc_titular", "pcs", "catalogo", "carpetas", "fuentes")})

    # La segunda vez, 409.
    r = client.post(f"{URL}/sembrar", json={"corrida_id": "c-probar"})
    assert r.status_code == 409


def test_sembrar_desde_una_corrida_sin_configuracion_efectiva_da_422(client):
    mandar(client, "c-vieja", tipo="probar", efectiva=None)
    r = client.post(f"{URL}/sembrar", json={"corrida_id": "c-vieja"})
    assert r.status_code == 422
    assert "no trae la configuración" in r.json()["detail"]
    assert client.post(f"{URL}/sembrar", json={"corrida_id": "no-existe"}).status_code == 404


def test_el_catalogo_del_motor_no_se_confunde_con_la_fuente_catalogo():
    """Hay una fuente que se llama "catalogo" (el maestro de repuestos)."""
    antes = config_efectiva(modo="prueba")
    despues = copy.deepcopy(antes)
    despues["catalogo"]["lista_erp"]["efecto_si_falta"] = "otro texto"
    assert fuentes_service._claves_cambiadas(antes, despues) == ["catalogo:motor"]
    despues = copy.deepcopy(antes)
    fuente(despues, "catalogo")["frecuencia_dias"] = 60
    assert fuentes_service._claves_cambiadas(antes, despues) == ["catalogo"]


def test_un_campo_nuevo_del_motor_se_guarda_al_sembrar(client):
    """Un campo que esta version de la plataforma no conoce no se pierde."""
    efectiva = config_efectiva()
    efectiva["fuentes"][0]["columnas_esperadas"] = ["Producto", "Stock"]
    efectiva["catalogo"]["stock_bodegas"]["origen"] = "programa del ERP"
    sembrado(client, efectiva=efectiva)
    cfg = config(client)
    assert fuente(cfg, "stock_bodegas")["columnas_esperadas"] == ["Producto", "Stock"]
    assert cfg["catalogo"]["stock_bodegas"]["origen"] == "programa del ERP"


# --------------------------------------------------------------------------- #
# 3. Reporte
# --------------------------------------------------------------------------- #
def test_inicio_y_fin_quedan_en_una_sola_fila(client, db_session):
    mandar(client, "c-1", fase="inicio", fuentes={"stock_bodegas": estado("stock_bodegas")})
    fila = db_session.get(MotorCorrida, "c-1")
    assert fila.resultado == "en_curso" and fila.terminada_en is None

    out = mandar(client, "c-1", fase="fin", resultado="ok")
    assert out["resultado"] == "ok"
    db_session.expire_all()
    assert db_session.query(MotorCorrida).count() == 1
    fila = db_session.get(MotorCorrida, "c-1")
    assert fila.resultado == "ok" and fila.terminada_en is not None
    assert set(json.loads(fila.reporte)["fuentes"]) == set(ELEGIDOS)
    assert fila.publico is True
    # La hora se guarda en UTC: 09:30 de Chile (UTC-3 en octubre) son las 12:30 UTC.
    assert fila.iniciada_en.replace(tzinfo=None) == datetime(2026, 10, 15, 12, 30)


def test_un_inicio_que_llega_despues_del_fin_no_lo_pisa(client, db_session):
    mandar(client, "c-1", fase="fin", resultado="frenada", motivo="No se carga a produccion con "
           "archivos desactualizados.")
    mandar(client, "c-1", fase="inicio", fuentes={})
    db_session.expire_all()
    fila = db_session.get(MotorCorrida, "c-1")
    assert fila.resultado == "frenada"
    assert json.loads(fila.reporte)["fuentes"]


def test_una_corrida_huerfana_cortada_no_borra_lo_que_trajo_el_inicio(client, db_session):
    mandar(client, "c-1", fase="inicio")
    # El motor la reporta en la corrida siguiente, sin manifiesto ni hora de fin.
    r = client.post(f"{URL}/reporte", json={
        "id": "c-1", "fase": "fin", "pc": PC, "tipo": "oficial", "resultado": "cortada",
        "terminada_en": None, "motivo": "La corrida se cortó antes de terminar.",
        "reporte": {"fuentes": {}, "carpetas": [], "avisos": ["reportada como cortada"]}})
    assert r.status_code == 200, r.text
    db_session.expire_all()
    fila = db_session.get(MotorCorrida, "c-1")
    assert fila.resultado == "cortada" and fila.terminada_en is None
    rep = json.loads(fila.reporte)
    assert set(rep["fuentes"]) == set(ELEGIDOS) and len(rep["carpetas"]) == 2
    assert "reportada como cortada" in rep["avisos"]


def test_una_hora_sin_zona_del_motor_es_hora_de_chile(client, db_session):
    mandar(client, "c-1", fase="inicio", iniciada_en="2026-10-15T09:30:00")
    fila = db_session.get(MotorCorrida, "c-1")
    assert fila.iniciada_en.replace(tzinfo=None) == datetime(2026, 10, 15, 12, 30)


def test_al_sembrar_el_alias_igual_al_hostname_queda_vacio(client):
    """El motor siembra `pcs: {host: {alias: host}}`: eso no es un nombre."""
    efectiva = config_efectiva(pcs={PC: {"alias": PC}}, modo="prueba", pc_titular=PC)
    sembrado(client, efectiva=efectiva)
    assert config(client)["pcs"][PC]["alias"] is None


def test_una_clave_desconocida_se_guarda_con_aviso_y_no_da_error(client, db_session):
    fuentes = fuentes_del_dia()
    fuentes["fuente_del_futuro"] = {"hecho": "encontrado", "archivos": []}
    out = mandar(client, "c-1", fuentes=fuentes)
    assert any("fuente_del_futuro" in a for a in out["avisos"])
    fila = db_session.get(MotorCorrida, "c-1")
    assert "fuente_del_futuro" in json.loads(fila.reporte)["fuentes"]
    # Un estado con forma inesperada tampoco rompe el panel.
    fuentes["stock_bodegas"] = {"hecho": "encontrado", "archivos": "no es una lista", "filas": "x"}
    mandar(client, "c-2", fuentes=fuentes, iniciada_en=_hora("10:30"))
    assert client.get(URL).status_code == 200


def test_un_reporte_sobre_2_mb_responde_413(client):
    relleno = "x" * (2 * 1024 * 1024 + 10)
    r = client.post(f"{URL}/reporte", json={"id": "c-1", "fase": "inicio", "pc": PC,
                                            "tipo": "probar", "motivo": relleno})
    assert r.status_code == 413


def test_el_fin_sin_resultado_da_422(client):
    r = client.post(f"{URL}/reporte", json={"id": "c-1", "fase": "fin", "pc": PC, "tipo": "oficial"})
    assert r.status_code == 422


def test_config_trae_anterior_de_la_ultima_oficial_ok_del_titular(client):
    sembrado(client)
    mandar(client, "c-ok", iniciada_en=_hora("09:30", "2026-10-14"),
           fuentes=fuentes_del_dia("2026-10-14"))
    # Una frenada posterior y una de otro PC no cuentan.
    mandar(client, "c-frenada", resultado="frenada", iniciada_en=_hora("09:30", "2026-10-15"))
    mandar(client, "c-jefa", pc=PC_JEFA, iniciada_en=_hora("09:31", "2026-10-15"))
    anterior = config(client)["anterior"]
    assert anterior["stock_bodegas"]["sha256"] == "sha-stock_bodegas-2026-10-14-0"
    assert anterior["stock_bodegas"]["filas"] == 19883
    assert len(anterior["ventas"]["archivos"]) == 2


# --------------------------------------------------------------------------- #
# 5. Validaciones (contra el catalogo) y vista previa
# --------------------------------------------------------------------------- #
def _put(client, clave, cambios, *, base=None, nota="ensayo"):
    base = base if base is not None else config(client)["version"]
    return client.put(f"{URL}/{clave}", json={"cambios": cambios, "nota": nota,
                                              "base_version": base})


@pytest.fixture()
def con_listado(client):
    """Configuracion sembrada y una corrida oficial del titular con su listado."""
    sembrado(client)
    mandar(client, "c-dia")
    return client


@pytest.mark.parametrize("clave, cambios, texto", [
    # El modo tiene que estar en catalogo[clave].modos.
    ("stock_bodegas", {"modo": "por_descarte"}, "no está permitida"),
    ("ventas", {"modo": "mas_reciente"}, "no está permitida"),
    # archivo_exacto exige nombre; mas_reciente, al menos un patron.
    ("lista_erp", {"modo": "archivo_exacto", "nombre_archivo": None}, "falta el nombre"),
    ("lista_erp", {"incluye": []}, "falta al menos un texto"),
    # Patrones sin /, \, .. ni letra de unidad, y hasta 100 caracteres.
    ("lista_erp", {"incluye": ["Bases/lista_erp.*"]}, "no puede llevar"),
    ("lista_erp", {"incluye": ["Bases\\lista_erp.*"]}, "no puede llevar"),
    ("lista_erp", {"excluye": ["..*"]}, "no puede llevar"),
    ("lista_erp", {"modo": "archivo_exacto", "nombre_archivo": "C:lista_erp.xlsx"},
     "no puede llevar"),
    ("lista_erp", {"incluye": ["a" * 101]}, "100 caracteres"),
    # La subcarpeta: "/" como separador, sin .., sin / al inicio ni letra de unidad.
    ("lista_erp", {"ubicaciones": [{"carpeta": "bases_de_datos", "subcarpeta": "../otra"}]},
     "no es válida"),
    ("lista_erp", {"ubicaciones": [{"carpeta": "bases_de_datos", "subcarpeta": "/Ventas"}]},
     "relativa"),
    ("lista_erp", {"ubicaciones": [{"carpeta": "bases_de_datos", "subcarpeta": "C:/Ventas"}]},
     "relativa"),
    # Las ubicaciones apuntan a carpetas que existen.
    ("lista_erp", {"ubicaciones": [{"carpeta": "no_existe"}]}, "no existe"),
    ("lista_erp", {"ubicaciones": []}, "al menos una carpeta"),
    # Plazo de 1 a 365 o null.
    ("lista_erp", {"frecuencia_dias": 0}, "de 1 a 365"),
    ("lista_erp", {"frecuencia_dias": 366}, "de 1 a 365"),
    # Minimos del catalogo: requerida -> obligatoria y activa.
    ("stock_bodegas", {"obligatoria": False}, "tiene que ser obligatoria"),
    ("ventas", {"activa": False}, "no se puede desactivar"),
    # frecuencia_max / al_vencer_fijo.
    ("stock_bodegas", {"frecuencia_dias": 6}, "no puede pasar de 5"),
    ("seguimiento_curifor_nacional", {"frecuencia_dias": None}, "no puede pasar de 5"),
    ("stock_bodegas_frontera", {"al_vencer": "avisa"}, "frenar la publicación"),
])
def test_cada_validacion_responde_422(con_listado, clave, cambios, texto):
    r = _put(con_listado, clave, cambios)
    assert r.status_code == 422, r.text
    assert texto in r.json()["detail"]


def test_las_validaciones_salen_del_catalogo_y_no_de_claves_escritas(client):
    """Si el motor declara otra fuente como requerida, la regla aplica a esa."""
    efectiva = config_efectiva()
    efectiva["catalogo"]["vigentes_ford"]["requerida"] = True
    efectiva["catalogo"]["stock_bodegas"]["requerida"] = False
    efectiva["catalogo"]["stock_bodegas"]["frecuencia_max"] = None
    efectiva["catalogo"]["stock_bodegas"]["al_vencer_fijo"] = None
    sembrado(client, efectiva=efectiva)
    r = _put(client, "vigentes_ford", {"obligatoria": False})
    assert r.status_code == 422 and "tiene que ser obligatoria" in r.json()["detail"]
    r = _put(client, "vigentes_ford", {"obligatoria": True, "activa": False})
    assert r.status_code == 422 and "no se puede desactivar" in r.json()["detail"]
    r = _put(client, "stock_bodegas", {"obligatoria": False, "frecuencia_dias": 30,
                                       "al_vencer": "avisa"})
    assert r.status_code == 200, r.text


def test_una_subcarpeta_con_barra_y_una_valida_se_guardan(con_listado):
    r = _put(con_listado, "lista_erp", {"ubicaciones": [
        {"carpeta": "bases_de_datos", "subcarpeta": "Exportes\\2026", "recursiva": False}]})
    assert r.status_code == 200, r.text
    assert fuente(config(con_listado), "lista_erp")["ubicaciones"][0]["subcarpeta"] == "Exportes/2026"


def test_put_sube_la_version_y_una_base_vieja_da_409(con_listado):
    r = _put(con_listado, "lista_erp", {"frecuencia_dias": 5}, base=1, nota="se pide cada 5")
    assert r.status_code == 200, r.text
    assert r.json()["version"] == 2
    assert r.json()["claves_cambiadas"] == ["lista_erp"]
    cfg = config(con_listado)
    assert cfg["version"] == 2 and fuente(cfg, "lista_erp")["frecuencia_dias"] == 5

    # Otro admin guardo con la version 1 en pantalla.
    r = _put(con_listado, "lista_erp", {"frecuencia_dias": 7}, base=1)
    assert r.status_code == 409
    assert r.json()["detail"] == "Otro admin guardó un cambio; recarga"


def test_guardar_sin_cambios_no_crea_version(con_listado):
    r = _put(con_listado, "lista_erp", {"frecuencia_dias": 10})
    assert r.status_code == 422 and "No hay cambios" in r.json()["detail"]


def test_vista_previa_dice_que_tomaria_y_que_toma_hoy_sin_guardar(con_listado, db_session):
    r = con_listado.post(f"{URL}/stock_bodegas/vista-previa", json={"cambios": {
        "ubicaciones": [{"carpeta": "bases_de_datos", "subcarpeta": "stock", "recursiva": False}]}})
    assert r.status_code == 200, r.text
    vp = r.json()
    assert [a["ruta_relativa"] for a in vp["elegiria"]["archivos"]] == ["stock/Stock bodegas.xlsx"]
    assert vp["elegiria"]["texto"].startswith("Con este cambio el motor tomaría Stock bodegas.xlsx")
    assert vp["hoy_toma"]["archivos"][0]["carpeta"] == "databi_datos"
    assert vp["hoy_toma"]["texto"].startswith("Hoy toma Stock bodegas.xlsx")
    assert vp["conflictos"] == []
    assert vp["listado"]["corrida_id"] == "c-dia"
    assert db_session.query(FuenteConfig).count() == 1


def test_vista_previa_normaliza_tildes(con_listado):
    # Patron con tilde contra un archivo sin tilde, y al reves.
    r = con_listado.post(f"{URL}/catalogo/vista-previa", json={"cambios": {
        "incluye": ["lísta de precíos.*"]}})
    assert r.json()["elegiria"]["archivos"][0]["nombre"] == "LISTA DE PRECIOS.xlsx"
    r = con_listado.post(f"{URL}/pautas_mantencion/vista-previa", json={"cambios": {
        "incluye": ["*mantencion*"]}})
    assert r.json()["elegiria"]["archivos"][0]["nombre"] == "Pauta de mantención Baic Enero 2026.xlsx"


def test_dos_fuentes_que_leen_el_mismo_archivo_dan_422(con_listado):
    cambios = {"modo": "archivo_exacto", "nombre_archivo": "Stock bodegas.xlsx"}
    vp = con_listado.post(f"{URL}/stock_bodegas_frontera/vista-previa",
                          json={"cambios": cambios}).json()
    assert vp["conflictos"] and "tomarían el mismo archivo" in vp["conflictos"][0]
    r = _put(con_listado, "stock_bodegas_frontera", cambios)
    assert r.status_code == 422 and "tomarían el mismo archivo" in r.json()["detail"]


def test_una_que_lee_y_una_que_reconoce_con_el_mismo_archivo_es_solo_aviso(con_listado):
    """Hoy precios_ford y precios_proveedor comparten la lista de Ford."""
    r = _put(con_listado, "precios_ford", {"frecuencia_dias": 30, "al_vencer": "avisa"})
    assert r.status_code == 200, r.text
    assert any("Otras listas de proveedor" in a for a in r.json()["avisos"])


def test_en_prueba_una_obligatoria_sin_archivo_es_solo_aviso(con_listado):
    r = _put(con_listado, "seguimiento_curifor_nacional", {"incluye": ["*no existe*"]})
    assert r.status_code == 200, r.text
    assert any("en modo activa, esto frenaría" in a for a in r.json()["avisos"])


def test_en_activa_una_obligatoria_sin_archivo_da_422(client):
    activada(client)
    r = _put(client, "seguimiento_curifor_nacional", {"incluye": ["*no existe*"]})
    assert r.status_code == 422
    assert r.json()["detail"] == ("Con este cambio el motor no encontraría el archivo y la "
                                  "publicación se frenaría.")


def test_vista_previa_sin_listado_del_titular_avisa(client):
    sembrado(client, carpetas=[])
    vp = client.post(f"{URL}/lista_erp/vista-previa", json={"cambios": {}}).json()
    assert vp["listado"] is None and vp["elegiria"]["archivos"] == []
    assert "Todavía no hay un listado" in vp["avisos"][0]
    # Sin listado no hay contra que probar: guardar igual se puede.
    assert _put(client, "lista_erp", {"frecuencia_dias": 5}).status_code == 200


def test_vista_previa_por_descarte_usa_los_respaldos_del_ano(con_listado, monkeypatch):
    # El motor toma los respaldos del ano en curso y del anterior: se fija la fecha.
    monkeypatch.setattr(fuentes_service, "ahora_chile",
                        lambda: datetime(2026, 10, 16, 10, 0, tzinfo=TZ_CHILE))
    vp = con_listado.post(f"{URL}/ventas/vista-previa", json={"cambios": {}}).json()
    nombres = sorted(a["nombre"] for a in vp["elegiria"]["archivos"])
    # El Motorcraft calza por nombre: el motor lo descarta despues por contenido.
    assert nombres == ["2025 (4).xlsx", "2026 (6).xlsx", "Motorcraft 2026.xlsx"]
    assert any("revisa el contenido" in a for a in vp["avisos"])


# --------------------------------------------------------------------------- #
# Carpetas, alias, titular, revertir
# --------------------------------------------------------------------------- #
def _carpeta(clave="motor_sp", **params):
    base = {"sitio_url": "https://ejemplo.sharepoint.com/sites/DataBI",
            "biblioteca": "Documentos compartidos", "ruta": "Data BI/Motor"}
    base.update(params)
    return {"clave": clave, "nombre": "Data BI › Motor", "tipo": "sharepoint", "params": base}


@pytest.mark.parametrize("carpeta, texto", [
    (_carpeta(sitio_url="https://ejemplo.com/sites/DataBI"), "sharepoint.com/sites"),
    (_carpeta(biblioteca=""), "biblioteca"),
    (_carpeta(ruta=""), "falta la ruta"),
    (_carpeta(ruta="Data BI/../Otra"), "relativa a OneDrive"),
    ({"clave": "od", "nombre": "OneDrive", "tipo": "onedrive", "params": {"ruta": ""}},
     "falta la ruta"),
    ({"clave": "Mayus", "nombre": "X", "tipo": "onedrive", "params": {"ruta": "Documentos"}},
     "minúsculas"),
    ({"clave": "bases_de_datos", "nombre": "X", "tipo": "onedrive",
      "params": {"ruta": "Documentos"}}, "Ya existe"),
])
def test_validaciones_de_carpetas(client, carpeta, texto):
    sembrado(client)
    r = client.post(f"{URL}/carpetas", json={"carpeta": carpeta, "nota": "x", "base_version": 1})
    assert r.status_code == 422, r.text
    assert texto in r.json()["detail"]


def test_alta_y_edicion_de_carpetas(client):
    sembrado(client)
    r = client.post(f"{URL}/carpetas", json={"carpeta": _carpeta(), "nota": "carpeta del ERP",
                                             "base_version": 1})
    assert r.status_code == 200, r.text
    assert r.json()["claves_cambiadas"] == ["carpeta:motor_sp"]
    r = client.put(f"{URL}/carpetas/motor_sp", json={
        "cambios": {"rutas_por_pc": {PC_JEFA: "C:\\Users\\usuario\\OneDrive - Empresa\\Motor"}},
        "nota": "ruta del PC de la jefa", "base_version": 2})
    assert r.status_code == 200, r.text
    carpeta = next(c for c in config(client)["carpetas"] if c["clave"] == "motor_sp")
    assert carpeta["rutas_por_pc"] == {PC_JEFA: "C:\\Users\\usuario\\OneDrive - Empresa\\Motor"}
    # Una carpeta que usa una fuente no se puede desactivar.
    r = client.put(f"{URL}/carpetas/databi_datos", json={
        "cambios": {"activa": False}, "nota": "x", "base_version": 3})
    assert r.status_code == 422 and "Stock bodegas Curifor" in r.json()["detail"]
    # Base vieja: 409.
    r = client.put(f"{URL}/carpetas/motor_sp", json={"cambios": {"nombre": "Otra"}, "nota": "x",
                                                     "base_version": 1})
    assert r.status_code == 409


def test_alias_del_pc(client):
    sembrado(client)
    r = client.put(f"{URL}/pcs/{PC}", json={"alias": "PC del dueño actual", "base_version": 1})
    assert r.status_code == 200, r.text
    assert config(client)["pcs"][PC]["alias"] == "PC del dueño actual"
    assert client.get(URL).json()["pc_titular_alias"] == "PC del dueño actual"
    r = client.put(f"{URL}/pcs/PC-NUNCA-VISTO", json={"alias": "x", "base_version": 2})
    assert r.status_code == 404


def test_el_titular_solo_puede_ser_un_pc_que_ya_reporto(client):
    sembrado(client)
    r = client.post(f"{URL}/titular", json={"pc": PC_JEFA, "nota": "x", "base_version": 1})
    assert r.status_code == 422 and "no ha reportado" in r.json()["detail"]
    mandar(client, "c-jefa", pc=PC_JEFA, tipo="probar")
    r = client.post(f"{URL}/titular", json={"pc": PC_JEFA, "nota": "pasa al PC de la jefa",
                                            "base_version": 1})
    assert r.status_code == 200, r.text
    assert config(client)["pc_titular"] == PC_JEFA


def test_revertir_inserta_una_copia_y_no_toca_el_modo(con_listado, db_session):
    _put(con_listado, "lista_erp", {"frecuencia_dias": 5}, base=1)
    _put(con_listado, "vigentes_ford", {"frecuencia_dias": 30, "al_vencer": "avisa"}, base=2)
    r = con_listado.post(f"{URL}/revertir/1", json={"base_version": 3})
    assert r.status_code == 200, r.text
    assert r.json()["version"] == 4
    assert sorted(r.json()["claves_cambiadas"]) == ["lista_erp", "vigentes_ford"]
    cfg = config(con_listado)
    assert fuente(cfg, "lista_erp")["frecuencia_dias"] == 10
    assert fuente(cfg, "vigentes_ford")["frecuencia_dias"] is None
    fila = db_session.query(FuenteConfig).filter_by(version=4).one()
    assert fila.revierte_a == 1 and fila.nota == "Volver a la versión 1"
    assert db_session.query(FuenteConfig).count() == 4


def test_revertir_una_sola_fuente(con_listado):
    _put(con_listado, "lista_erp", {"frecuencia_dias": 5}, base=1)
    _put(con_listado, "vigentes_ford", {"frecuencia_dias": 30, "al_vencer": "avisa"}, base=2)
    r = con_listado.post(f"{URL}/revertir/1", json={"clave": "lista_erp"})
    assert r.status_code == 200, r.text
    assert r.json()["claves_cambiadas"] == ["lista_erp"]
    cfg = config(con_listado)
    assert fuente(cfg, "lista_erp")["frecuencia_dias"] == 10
    assert fuente(cfg, "vigentes_ford")["frecuencia_dias"] == 30
    assert con_listado.post(f"{URL}/revertir/99", json={}).status_code == 404


# --------------------------------------------------------------------------- #
# Activar y volver a prueba
# --------------------------------------------------------------------------- #
def _corridas_verdes(client, n, *, version=1, desde_dia=14, prueba="coincide"):
    for i in range(n):
        dia = f"2026-10-{desde_dia + i:02d}"
        mandar(client, f"verde-{dia}", iniciada_en=_hora("09:30", dia),
               fuentes=fuentes_del_dia(dia, prueba=prueba),
               config_origen="plataforma", config_version=version)


def activada(client):
    sembrado(client)
    _corridas_verdes(client, fuentes_service.CORRIDAS_PARA_ACTIVAR)
    r = client.post(f"{URL}/modo", json={"modo": "activa", "nota": "2 de 2 en verde",
                                         "base_version": 1})
    assert r.status_code == 200, r.text
    return r.json()


def test_activar_sin_las_corridas_en_verde_da_409(client):
    sembrado(client)
    _corridas_verdes(client, fuentes_service.CORRIDAS_PARA_ACTIVAR - 1)
    panel = client.get(URL).json()
    assert panel["activacion"]["puede_activar"] is False
    assert panel["activacion"]["corridas_en_verde"] == fuentes_service.CORRIDAS_PARA_ACTIVAR - 1
    r = client.post(f"{URL}/modo", json={"modo": "activa", "nota": "x", "base_version": 1})
    assert r.status_code == 409
    assert "hacen falta 2 corridas" in r.json()["detail"]


def test_activar_con_dos_de_dos_y_volver_a_prueba(client):
    assert fuentes_service.CORRIDAS_PARA_ACTIVAR == 2
    sembrado(client)
    _corridas_verdes(client, 2)
    assert client.get(URL).json()["activacion"]["puede_activar"] is True
    out = activada_desde_panel(client)
    assert out["modo"] == "activa"
    assert config(client)["modo"] == "activa"
    r = client.post(f"{URL}/modo", json={"modo": "prueba", "nota": "volver a prueba",
                                         "base_version": out["version"]})
    assert r.status_code == 200 and config(client)["modo"] == "prueba"


def activada_desde_panel(client):
    r = client.post(f"{URL}/modo", json={"modo": "activa", "nota": "listo",
                                         "base_version": config(client)["version"]})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.parametrize("problema", ["difiere", "frenada", "cache", "falta_obligatoria"])
def test_una_corrida_que_no_esta_en_verde_corta_la_racha(client, problema):
    sembrado(client)
    _corridas_verdes(client, 1, desde_dia=14)
    fuentes = fuentes_del_dia("2026-10-15", prueba="coincide")
    resultado, origen = "ok", "plataforma"
    if problema == "difiere":
        fuentes["stock_bodegas"]["prueba"]["resultado"] = "difiere"
    elif problema == "frenada":
        resultado = "frenada"
    elif problema == "cache":
        origen = "cache"
    else:
        fuentes["seguimiento_frontera"]["prueba"]["resultado"] = "falta"
    mandar(client, "c-15", iniciada_en=_hora("09:30", "2026-10-15"), fuentes=fuentes,
           resultado=resultado, config_origen=origen, config_version=1)
    r = client.post(f"{URL}/modo", json={"modo": "activa", "nota": "x", "base_version": 1})
    assert r.status_code == 409


def test_una_diferencia_esperada_y_una_opcional_que_falta_en_los_dos_no_cortan(client):
    sembrado(client)
    for dia in ("2026-10-14", "2026-10-15"):
        fuentes = fuentes_del_dia(dia, prueba="coincide")
        fuentes["stock_bodegas"]["prueba"]["resultado"] = "difiere_esperado"
        # vigentes_ford no es obligatoria: si ni el .env ni la plataforma la encuentran,
        # activar no cambia nada.
        fuentes["vigentes_ford"] = {"hecho": "falta", "archivos": [], "prueba": {"resultado": "falta"}}
        mandar(client, f"c-{dia}", iniciada_en=_hora("09:30", dia), fuentes=fuentes,
               config_origen="plataforma", config_version=1)
    assert client.get(URL).json()["activacion"]["puede_activar"] is True


def test_si_la_configuracion_cambio_despues_de_las_corridas_no_se_activa(client):
    sembrado(client)
    _corridas_verdes(client, 2)
    assert _put(client, "lista_erp", {"frecuencia_dias": 5}, base=1).status_code == 200
    r = client.post(f"{URL}/modo", json={"modo": "activa", "nota": "x", "base_version": 2})
    assert r.status_code == 409 and "cambió después" in r.json()["detail"]


def test_cambiar_el_nombre_de_un_pc_no_invalida_las_corridas(client):
    sembrado(client)
    _corridas_verdes(client, 2)
    client.put(f"{URL}/pcs/{PC}", json={"alias": "PC del dueño actual", "base_version": 1})
    r = client.post(f"{URL}/modo", json={"modo": "activa", "nota": "x", "base_version": 2})
    assert r.status_code == 200, r.text


def test_revertir_a_una_version_activa_no_activa(client):
    activada(client)
    client.post(f"{URL}/modo", json={"modo": "prueba", "nota": "x", "base_version": 2})
    r = client.post(f"{URL}/revertir/2", json={})
    # La v2 solo cambio el modo: no hay fuentes ni carpetas distintas que copiar.
    assert r.status_code == 422
    assert config(client)["modo"] == "prueba"


# --------------------------------------------------------------------------- #
# Panel, detalle, listados e historial
# --------------------------------------------------------------------------- #
def test_panel_muestra_las_13_que_lee_las_4_que_reconoce_y_las_carpetas(con_listado):
    panel = con_listado.get(URL).json()
    assert panel["modo"] == "prueba" and panel["modo_texto"] == "En prueba"
    assert sorted(f["clave"] for f in panel["fuentes"]) == sorted(LEE)
    assert len(panel["fuentes"]) == 13
    assert sorted(f["clave"] for f in panel["reconoce"]) == [
        "dim_sucursal", "lista_new_wings", "pautas_mantencion", "precios_proveedor"]
    pc = panel["carpetas_por_pc"][0]
    assert pc["pc"] == PC and pc["es_titular"] is True
    bd = next(c for c in pc["carpetas"] if c["clave"] == "bases_de_datos")
    assert bd["existe"] is True and bd["archivos"] == len(ARCHIVOS_BD)
    assert bd["ruta_portable"].startswith("%OneDriveCommercial%")
    # La ruta absoluta (trae el usuario de Windows) no va en el panel.
    assert "ruta_absoluta" not in bd
    # De la peor a la mejor.
    niveles = [f["nivel"] for f in panel["fuentes"]]
    orden = {"rojo": 0, "amarillo": 1, "gris": 2, "verde": 3}
    assert niveles == sorted(niveles, key=orden.get)


def test_detalle_de_una_fuente(con_listado):
    _put(con_listado, "stock_bodegas", {"frecuencia_dias": 3}, base=1, nota="ensayo de plazo")
    d = con_listado.get(f"{URL}/stock_bodegas").json()
    assert d["config"]["frecuencia_dias"] == 3
    assert d["uso"] == "lee"
    assert set(d["bloqueos"]) >= {"obligatoria", "activa", "frecuencia_dias", "al_vencer"}
    assert d["hoja_texto"] == "Automático (detectado: hoja 'Hoja1', fila 1)"
    assert [c["corrida_id"] for c in d["corridas"]][:1] == ["c-dia"]
    # Competencia entre carpetas: las dos tienen un stock y gana el mas nuevo.
    por_carpeta = {c["carpeta"]: c for c in d["competencia"]}
    assert set(por_carpeta) == {"bases_de_datos", "databi_datos"}
    assert [a["elegido"] for a in por_carpeta["databi_datos"]["candidatos"]] == [True]
    assert por_carpeta["databi_datos"]["ruta_absoluta"].startswith("C:\\Users\\")
    # Versiones que la cambiaron: la siembra y el ensayo.
    assert [v["version"] for v in d["versiones"]] == [2, 1]
    assert d["versiones"][0]["nota"] == "ensayo de plazo"
    assert con_listado.get(f"{URL}/no_existe").status_code == 404


def test_archivos_de_una_carpeta_para_los_selectores(con_listado):
    r = con_listado.get(f"{URL}/carpetas/bases_de_datos/archivos").json()
    assert r["pc"] == PC and r["existe"] is True
    assert "Seguimientos de compras" in r["subcarpetas"] and "Ventas" in r["subcarpetas"]
    gilde = next(a for a in r["archivos"] if a["nombre"].startswith("Precios Gildemeister"))
    assert gilde["patron_propuesto"] == "precios gildemeister *"
    stock = next(a for a in r["archivos"] if a["ruta_relativa"] == "stock/Stock bodegas.xlsx")
    assert stock["subcarpeta"] == "stock" and stock["patron_propuesto"] == "stock bodegas.*"
    otro = con_listado.get(f"{URL}/carpetas/bases_de_datos/archivos?pc=PC-OTRO").json()
    assert otro["archivos"] == [] and otro["corrida_id"] is None


def test_historial_de_corridas(con_listado):
    mandar(con_listado, "c-jefa", pc=PC_JEFA, tipo="probar", iniciada_en=_hora("09:35"),
           carpetas=listados(sin=("bases_de_datos",)))
    items = con_listado.get(f"{URL}/corridas?limit=30").json()["items"]
    assert [c["id"] for c in items][:2] == ["c-jefa", "c-dia"]
    dia = next(c for c in items if c["id"] == "c-dia")
    assert dia["resultado_texto"] == "Publicó" and dia["duracion_min"] == 28
    assert sum(dia["resumen"].values()) == 13
    jefa = next(c for c in items if c["id"] == "c-jefa")
    assert jefa["resultado_texto"] == "Revisión sin publicar"


def test_el_motivo_del_log_se_traduce_sin_opciones_de_linea_de_comandos(client):
    motivo = ("No se carga a produccion con archivos desactualizados.\nArchivos vencidos:\n  - "
              "stock.xlsx\n\nActualizalos en la carpeta de datos, o corre con "
              "--ignorar-frescura si sabes que asi corresponde.")
    mandar(client, "c-1", resultado="frenada", motivo=motivo)
    item = client.get(f"{URL}/corridas").json()["items"][0]
    assert item["motivo_texto"] == "No se publicó porque hay archivos vencidos."
    assert "--" not in json.dumps(client.get(URL).json(), ensure_ascii=False)
    assert fuentes_service.traducir_motivo("Algo raro. Corre con --forzar para seguir.") == \
        "Algo raro."


# --------------------------------------------------------------------------- #
# Lo que el equipo no ve, y la campanita a los admins (Anexo C, punto 4)
# --------------------------------------------------------------------------- #
@pytest.fixture()
def admins(db_session):
    _usuario(db_session, MOTOR, admin=True)
    _usuario(db_session, "admin2@ejemplo.com", admin=True)
    _usuario(db_session, "admin-inactivo@ejemplo.com", admin=True, activo=False)
    _usuario(db_session, "comprador@ejemplo.com")
    # El usuario de los tests (conftest) tambien es admin.
    return ["test@curifor.com", "admin2@ejemplo.com"]


def _avisos(db, email=None):
    q = db.query(Notificacion).filter(Notificacion.tipo.like("fuentes_datos:%"))
    if email:
        q = q.filter(Notificacion.para_email == email)
    return q.all()


def test_nada_de_fuentes_aparece_en_auditoria_ni_en_las_notificaciones_del_equipo(
        client, db_session, como, admins):
    como(MOTOR)
    sembrado(client)
    mandar(client, "c-frenada", resultado="frenada", motivo="No se carga a produccion con "
           "archivos desactualizados.")
    como("test@curifor.com")
    _put(client, "lista_erp", {"frecuencia_dias": 5}, base=1)
    client.post(f"{URL}/carpetas", json={"carpeta": _carpeta(), "nota": "x", "base_version": 2})
    client.put(f"{URL}/pcs/{PC}", json={"alias": "PC del dueño actual", "base_version": 3})

    assert db_session.query(AuditoriaLog).count() == 0
    assert client.get("/api/auditoria").json()["total"] == 0
    # Todo aviso de fuentes es personal: ninguno sale para todo el equipo.
    assert all(n.para_email for n in _avisos(db_session))
    for email in ("comprador@ejemplo.com", "noadmin@curifor.com", "admin-inactivo@ejemplo.com",
                  MOTOR):
        como(email)
        if email == "admin-inactivo@ejemplo.com":
            continue  # no puede entrar
        titulos = [n["titulo"] for n in client.get("/api/notificaciones").json()["items"]]
        assert not any("Fuentes de datos" in t for t in titulos), email


def test_una_corrida_oficial_frenada_avisa_a_cada_admin_activo_menos_al_motor(
        client, db_session, como, admins):
    como(MOTOR)
    sembrado(client)
    out = mandar(client, "c-frenada", resultado="frenada",
                 motivo="No se carga a produccion con archivos desactualizados.")
    assert out["notificados"] == 2
    for email in admins:
        avisos = _avisos(db_session, email)
        assert [n.tipo for n in avisos] == ["fuentes_datos:frenada"]
        assert avisos[0].titulo == "Fuentes de datos: la corrida no publicó"
        assert avisos[0].mensaje == "No se publicó porque hay archivos vencidos."
    assert _avisos(db_session, MOTOR) == []
    assert _avisos(db_session, "admin-inactivo@ejemplo.com") == []
    assert _avisos(db_session, "comprador@ejemplo.com") == []
    # El admin lo ve en su campanita.
    como("admin2@ejemplo.com")
    titulos = [n["titulo"] for n in client.get("/api/notificaciones").json()["items"]]
    assert "Fuentes de datos: la corrida no publicó" in titulos


def test_maximo_un_aviso_al_dia_por_admin_y_por_motivo(client, db_session, como, admins):
    como(MOTOR)
    sembrado(client)
    mandar(client, "c-1", resultado="frenada", motivo="x")
    out = mandar(client, "c-2", resultado="frenada", motivo="x", iniciada_en=_hora("11:00"))
    assert out["notificados"] == 0
    # Otro motivo el mismo dia si avisa.
    out = mandar(client, "c-3", resultado="fallo", motivo="El motor no pudo calcular el sugerido.",
                 iniciada_en=_hora("12:00"))
    assert out["notificados"] == 2
    assert len(_avisos(db_session, "admin2@ejemplo.com")) == 2


def test_una_fuente_en_rojo_avisa_aunque_la_corrida_publique(client, db_session, como, admins):
    como(MOTOR)
    sembrado(client)
    fuentes = fuentes_del_dia()
    fuentes["stock_bodegas"]["filas"] = 0
    out = mandar(client, "c-1", resultado="ok", fuentes=fuentes)
    assert out["notificados"] == 2
    aviso = _avisos(db_session, "admin2@ejemplo.com")[0]
    assert aviso.tipo == "fuentes_datos:rojo:stock_bodegas"
    assert aviso.titulo == "Fuentes de datos: Stock bodegas Curifor en rojo (llegó vacío o incompleto)"


@pytest.mark.parametrize("tipo, resultado", [("probar", "frenada"), ("oficial", "no_titular"),
                                             ("oficial", "ok"), ("comparacion", "fallo")])
def test_sin_aviso_cuando_no_corresponde(client, db_session, como, admins, tipo, resultado):
    como(MOTOR)
    sembrado(client)
    out = mandar(client, "c-1", tipo=tipo, resultado=resultado)
    assert out["notificados"] == 0
    assert _avisos(db_session) == []
