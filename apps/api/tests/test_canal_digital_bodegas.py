"""Parametros por bodega de Canal Digital: listar, editar con validacion de todo o nada, crear y el 404 de las demas rutas.

Lo que estos tests cuidan:

1. Leer no escribe: solo la tabla vacia siembra la bodega por defecto (una vez); una bodega desconocida da 404 en
   TODAS las rutas y no se crea.
2. Las listas se guardan como texto con comas pero salen como listas limpias (sin vacios, duplicados ni espacios).
3. Editar valida el resultado completo ANTES de guardar: un campo malo no deja pasar a los buenos, cada limite se
   prueba por los dos lados, y la ventana sigue en 12.
4. Los permisos: editar pide escritura, crear pide admin.
5. Guardar deja auditoria, descarta la corrida en cache (el resumen refleja el cambio) y avisa que los tipos de
   venta aplican solo a las cargas futuras.
"""
import datetime as dt

import pytest
from sqlalchemy import event

from src.main import app
from src.models import AuditoriaLog, CanalDigitalBodega, CanalDigitalPolitica, CanalDigitalVenta, Usuario
from src.routers import canal_digital as router_cd
from src.services import canal_digital_bodegas as bodegas_cd
from src.services import canal_digital_calculo as calc
from src.services import canal_digital_service as svc
from src.services.auth import hash_password, requiere_auth

HOY = dt.date(2026, 10, 26)
ANCLA = dt.date(2026, 10, 1)
URL = "/api/canal-digital/bodegas"
TABLAS = (CanalDigitalBodega, CanalDigitalPolitica, CanalDigitalVenta, AuditoriaLog)


@pytest.fixture(autouse=True)
def _fijar_hoy(monkeypatch):
    monkeypatch.setattr(router_cd, "_hoy", lambda: HOY)
    router_cd._invalidar()
    yield
    router_cd._invalidar()


def _conteos(db):
    db.expire_all()
    return {t.__tablename__: db.query(t).count() for t in TABLAS}


class _Escrituras:
    """Cuenta las sentencias INSERT / UPDATE / DELETE que pasan por la base mientras dura el bloque."""

    def __init__(self, db):
        self.motor = db.get_bind()
        self.sentencias: list[str] = []

    def _registrar(self, conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().split(None, 1)[0].upper() in ("INSERT", "UPDATE", "DELETE"):
            self.sentencias.append(statement)

    def __enter__(self):
        event.listen(self.motor, "before_cursor_execute", self._registrar)
        return self

    def __exit__(self, *exc):
        event.remove(self.motor, "before_cursor_execute", self._registrar)


def _como(email: str):
    app.dependency_overrides[requiere_auth] = lambda: email


def _usuario(db, email: str, **kw):
    db.add(Usuario(email=email, password_hash=hash_password("x"), nombre=email, **kw))
    db.commit()


def _fila(db, bodega: str) -> CanalDigitalBodega:
    db.expire_all()
    return db.query(CanalDigitalBodega).filter_by(bodega=bodega).one()


def _put(client, codigo="430", /, **cambios):
    """PUT a la bodega `codigo`; todo lo demas va al cuerpo (incluso un campo llamado `bodega`)."""
    return client.put(f"{URL}/{codigo}", json=cambios)


def _problemas(r) -> str:
    """Todos los problemas de un 400 en un solo texto, para buscar palabras."""
    assert r.status_code == 400, r.text
    return " | ".join(r.json()["detail"]["problemas"])


def _filas_venta(producto, por_semana):
    out = []
    for semana in calc.ventana(ANCLA)["semanas"]:
        f = dt.date.fromisoformat(semana)
        out.append({"producto": producto, "semana": semana, "periodo": f"{f.year}{f.month:02d}",
                    "unid_brutas": por_semana, "unid_devueltas": 0, "valor_costo": 100.0 * por_semana,
                    "unid_liquidacion": 0, "n_lineas": 1})
    return out


@pytest.fixture()
def con_430(db_session):
    svc.asegurar_bodega(db_session, "430")
    return db_session


# --------------------------------------------------------------------------- GET: lectura que no escribe

def test_con_la_tabla_vacia_siembra_solo_la_430_una_vez_y_con_su_politica(client, db_session):
    assert db_session.query(CanalDigitalBodega).count() == 0
    r = client.get(URL)
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert [b["bodega"] for b in cuerpo["bodegas"]] == ["430"]
    assert cuerpo["tipos_venta_sugeridos"] == ["VTA ML", "VTA SHOPIFY", "VTA WALMART", "VTA PARIS"]
    assert db_session.query(CanalDigitalBodega).count() == 1
    assert db_session.query(CanalDigitalPolitica).filter_by(bodega="430").count() == 27
    # la segunda vez ya no escribe nada
    with _Escrituras(db_session) as e:
        assert client.get(URL).status_code == 200
    assert e.sentencias == []
    assert db_session.query(CanalDigitalBodega).count() == 1


def test_los_parametros_de_siembra_salen_como_listas_y_con_la_ventana_en_12(client, con_430):
    b = client.get(URL).json()["bodegas"][0]
    assert b == {
        "bodega": "430", "nombre": "Canal digital 430", "activa": True,
        "tipos_venta": ["VTA ML", "VTA SHOPIFY", "VTA WALMART", "VTA PARIS"],
        "r_semanas": 1, "ventana_meses": 12, "nuevo_meses": 6, "corte_a_pct": 80, "corte_b_pct": 95,
        "gestion_dias": 1, "bodegas_stock": ["BODEGA ML"], "bodegas_aparte": ["BODEGA ML-FULL"],
        "bodegas_informativas": ["CD REPUESTOS"],
    }


def test_leer_con_otras_bodegas_no_siembra_la_430_ni_escribe(client, db_session):
    svc.asegurar_bodega(db_session, "500")
    antes = _conteos(db_session)
    with _Escrituras(db_session) as e:
        r = client.get(URL)
    assert [b["bodega"] for b in r.json()["bodegas"]] == ["500"]
    assert e.sentencias == [] and _conteos(db_session) == antes
    assert db_session.query(CanalDigitalBodega).filter_by(bodega="430").count() == 0


def test_la_430_sale_primero_y_el_resto_por_codigo(client, db_session):
    for b in ("700", "431", "430", "ABC"):
        svc.asegurar_bodega(db_session, b)
    assert [b["bodega"] for b in client.get(URL).json()["bodegas"]] == ["430", "431", "700", "ABC"]


def test_las_listas_guardadas_con_comas_salen_limpias(client, con_430):
    f = _fila(con_430, "430")
    f.tipos_venta = " VTA ML,, VTA ML ,VTA PARIS , "
    f.bodegas_stock = "BODEGA ML, bodega-ml ,BODEGA  ML,BODEGA 2"  # las tres primeras son la misma bodega
    f.bodegas_aparte = ""
    con_430.commit()
    b = client.get(URL).json()["bodegas"][0]
    assert b["tipos_venta"] == ["VTA ML", "VTA PARIS"]
    assert b["bodegas_stock"] == ["BODEGA ML", "BODEGA 2"]
    assert b["bodegas_aparte"] == []


def test_normalizar_lista_compara_tipos_tal_cual_y_bodegas_sin_signos():
    assert bodegas_cd.normalizar_lista(["vta ml", "VTA ML", " VTA ML "], por_clave=False) == ["vta ml", "VTA ML"]
    assert bodegas_cd.normalizar_lista(["vta ml", "VTA-ML", "VTA ML "], por_clave=True) == ["vta ml"]
    assert bodegas_cd.normalizar_lista(["", "  ", "A"], por_clave=True) == ["A"]


# --------------------------------------------------------------------------- 404 en las demas rutas

RUTAS_DE_LECTURA = [
    "/api/canal-digital/resumen", "/api/canal-digital/productos", "/api/canal-digital/productos/export-csv",
    "/api/canal-digital/datos", "/api/canal-digital/politica", "/api/canal-digital/meta",
]


@pytest.mark.parametrize("ruta", RUTAS_DE_LECTURA + ["/api/canal-digital/producto/paso-a-paso?producto=P1"])
def test_una_bodega_que_no_existe_da_404_en_cada_lectura_y_no_se_crea(client, con_430, ruta):
    antes = _conteos(con_430)
    sep = "&" if "?" in ruta else "?"
    r = client.get(f"{ruta}{sep}bodega=999")
    assert r.status_code == 404 and "999" in r.json()["detail"]
    assert _conteos(con_430) == antes
    assert con_430.query(CanalDigitalBodega).filter_by(bodega="999").count() == 0


def test_guardar_la_politica_de_una_bodega_que_no_existe_da_404_y_no_la_crea(client, con_430):
    filas = client.get("/api/canal-digital/politica").json()["filas"]
    antes = _conteos(con_430)
    r = client.put("/api/canal-digital/politica?bodega=999", json={"filas": filas})
    assert r.status_code == 404
    assert _conteos(con_430) == antes


@pytest.mark.parametrize("ruta", RUTAS_DE_LECTURA)
def test_la_430_sigue_respondiendo_sin_haber_sido_creada(client, db_session, ruta):
    """La por defecto se siembra sola al primer uso: es la unica excepcion."""
    assert client.get(ruta).status_code == 200


def test_una_bodega_creada_responde_en_las_rutas_de_lectura(client, db_session):
    assert client.post(URL, json={"bodega": "500", "nombre": "Canal 500"}).status_code == 201
    for ruta in RUTAS_DE_LECTURA:
        assert client.get(ruta, params={"bodega": "500"}).status_code == 200, ruta
    assert len(client.get("/api/canal-digital/politica", params={"bodega": "500"}).json()["filas"]) == 27


def test_una_bodega_inactiva_sigue_consultable(client, con_430):
    svc.asegurar_bodega(con_430, "500")
    assert _put(client, "500", activa=False).status_code == 200
    assert client.get(URL).json()["bodegas"][1]["activa"] is False
    assert client.get("/api/canal-digital/resumen", params={"bodega": "500"}).status_code == 200
    assert client.get("/api/canal-digital/politica", params={"bodega": "500"}).status_code == 200


# --------------------------------------------------------------------------- PUT: lo que se guarda

def test_guardar_cambia_los_parametros_y_responde_la_bodega_con_lo_que_cambio(client, con_430):
    r = _put(
        client, nombre="  Canal ML  ", activa=False, tipos_venta=[" VTA ML ", "", "VTA PARIS", "VTA ML"],
        r_semanas=2, nuevo_meses=4, corte_a_pct=70, corte_b_pct=90.5, gestion_dias=2.5,
        bodegas_stock=["BODEGA ML", "BODEGA 2"], bodegas_aparte=[], bodegas_informativas=["CD REPUESTOS", "CD 2"],
    )
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["nombre"] == "Canal ML" and cuerpo["activa"] is False
    assert cuerpo["tipos_venta"] == ["VTA ML", "VTA PARIS"]
    assert (cuerpo["r_semanas"], cuerpo["nuevo_meses"], cuerpo["corte_a_pct"], cuerpo["corte_b_pct"]) == (2, 4, 70, 90.5)
    assert cuerpo["gestion_dias"] == 2.5 and cuerpo["ventana_meses"] == 12
    assert cuerpo["bodegas_stock"] == ["BODEGA ML", "BODEGA 2"] and cuerpo["bodegas_aparte"] == []
    assert sorted(cuerpo["cambios"]) == sorted(
        ["nombre", "activa", "tipos_venta", "r_semanas", "nuevo_meses", "corte_a_pct", "corte_b_pct", "gestion_dias",
         "bodegas_stock", "bodegas_aparte", "bodegas_informativas"])
    # y quedo guardado: en la base como texto con comas, y al leer como listas
    f = _fila(con_430, "430")
    assert f.tipos_venta == "VTA ML,VTA PARIS" and f.bodegas_stock == "BODEGA ML,BODEGA 2" and f.bodegas_aparte == ""
    assert f.actualizado_en is not None
    assert client.get(URL).json()["bodegas"][0] == {k: v for k, v in cuerpo.items() if k not in ("cambios", "avisos")}


def test_solo_cambia_lo_que_viene(client, con_430):
    r = _put(client, r_semanas=3)
    assert r.status_code == 200 and r.json()["cambios"] == ["r_semanas"]
    f = _fila(con_430, "430")
    assert f.r_semanas == 3 and f.corte_a_pct == 80 and f.bodegas_stock == "BODEGA ML" and f.nombre == "Canal digital 430"


def test_guardar_los_mismos_valores_no_cambia_nada_ni_deja_rastro(client, con_430):
    actual = {k: v for k, v in client.get(URL).json()["bodegas"][0].items() if k != "bodega"}
    with _Escrituras(con_430) as e:
        r = _put(client, **actual)
    assert r.status_code == 200 and r.json()["cambios"] == [] and r.json()["avisos"] == []
    assert e.sentencias == [] and con_430.query(AuditoriaLog).count() == 0


@pytest.mark.parametrize("campo,valor", [
    ("r_semanas", 0), ("r_semanas", 8), ("r_semanas", 0.5), ("nuevo_meses", 1), ("nuevo_meses", 12),
    ("nuevo_meses", 6.0), ("gestion_dias", 0), ("gestion_dias", 30), ("corte_a_pct", 0.1), ("corte_a_pct", 94.9),
    ("corte_b_pct", 100), ("corte_b_pct", 80.1),
])
def test_los_limites_valen_por_dentro(client, con_430, campo, valor):
    r = _put(client, **{campo: valor})
    assert r.status_code == 200, r.text


def test_el_limite_de_elementos_vale_por_dentro(client, con_430):
    assert _put(client, tipos_venta=[f"VTA {i}" for i in range(bodegas_cd.MAX_ELEMENTOS)]).status_code == 200
    assert _put(client, nombre="x" * bodegas_cd.MAX_LARGO).status_code == 200


def test_la_ventana_en_12_se_acepta_porque_no_cambia_nada(client, con_430):
    r = _put(client, ventana_meses=12, bodega="430", r_semanas=2)
    assert r.status_code == 200 and r.json()["cambios"] == ["r_semanas"] and r.json()["ventana_meses"] == 12


# --------------------------------------------------------------------------- PUT: lo que se rechaza

# (campo y valor, texto que debe decir el mensaje). Cada limite por fuera y cada tipo equivocado.
RECHAZOS = [
    ("r_semanas", -0.1, "entre 0 y 8"), ("r_semanas", 8.1, "entre 0 y 8"), ("r_semanas", "2", "debe ser un número"),
    ("r_semanas", True, "debe ser un número"), ("r_semanas", None, "debe ser un número"),
    ("r_semanas", [1], "debe ser un número"), ("r_semanas", 10**400, "número finito"),
    ("nuevo_meses", 0, "entre 1 y 12"), ("nuevo_meses", 13, "entre 1 y 12"), ("nuevo_meses", 6.5, "número entero"),
    ("nuevo_meses", "6", "debe ser un número"), ("nuevo_meses", False, "debe ser un número"),
    ("gestion_dias", -1, "entre 0 y 30"), ("gestion_dias", 30.5, "entre 0 y 30"),
    ("gestion_dias", "1", "debe ser un número"),
    ("corte_a_pct", 0, "mayor que 0"), ("corte_a_pct", -5, "entre 0 y 100"), ("corte_a_pct", 101, "entre 0 y 100"),
    ("corte_a_pct", "80", "debe ser un número"), ("corte_a_pct", 95, "debe ser menor que el corte B"),
    ("corte_a_pct", 96, "debe ser menor que el corte B"),
    ("corte_b_pct", 0, "mayor que 0"), ("corte_b_pct", 100.1, "entre 0 y 100"),
    ("corte_b_pct", 80, "debe ser menor que el corte B"), ("corte_b_pct", 50, "debe ser menor que el corte B"),
    ("tipos_venta", [], "no puede quedar vacío"), ("tipos_venta", ["", "  "], "no puede quedar vacío"),
    ("tipos_venta", "VTA ML", "lista de textos"), ("tipos_venta", None, "lista de textos"),
    ("tipos_venta", ["VTA ML", 3], "solo puede tener textos"), ("tipos_venta", ["VTA ML,VTA PARIS"], "lleva una coma"),
    ("tipos_venta", ["x" * 61], "pasa de 60"), ("tipos_venta", [f"T{i}" for i in range(21)], "hasta 20 elementos"),
    ("bodegas_stock", [], "no puede quedar vacío"), ("bodegas_stock", "BODEGA ML", "lista de textos"),
    ("bodegas_stock", ["---"], "no tiene letras ni números"),
    ("bodegas_aparte", "BODEGA ML-FULL", "lista de textos"), ("bodegas_informativas", [["CD"]], "solo puede tener textos"),
    ("nombre", "", "no puede quedar vacío"), ("nombre", "   ", "no puede quedar vacío"),
    ("nombre", 5, "debe ser un texto"), ("nombre", "x" * 61, "pasa de 60"),
    ("activa", "si", "verdadero o falso"), ("activa", 1, "verdadero o falso"), ("activa", None, "verdadero o falso"),
    ("ventana_meses", 6, "ventana es de 12 meses"), ("ventana_meses", 13, "ventana es de 12 meses"),
    ("ventana_meses", "12", "ventana es de 12 meses"), ("ventana_meses", True, "ventana es de 12 meses"),
    ("ventana_meses", None, "ventana es de 12 meses"),
    ("bodega", "999", "no es la de la dirección"), ("r_semana", 2, "no es un parámetro"),
    ("id", 1, "no es un parámetro"), ("tenant_id", "otro", "no es un parámetro"),
]


@pytest.mark.parametrize("campo,valor,texto", RECHAZOS)
def test_cada_valor_invalido_da_400_con_su_mensaje_y_no_guarda_nada(client, con_430, campo, valor, texto):
    antes = _conteos(con_430)
    f = _fila(con_430, "430")
    firma = (f.nombre, f.activa, f.tipos_venta, f.r_semanas, f.ventana_meses, f.nuevo_meses, f.corte_a_pct,
             f.corte_b_pct, f.gestion_dias, f.bodegas_stock, f.bodegas_aparte, f.bodegas_informativas)
    r = _put(client, **{campo: valor})
    assert texto in _problemas(r)
    assert r.json()["detail"]["mensaje"]
    f = _fila(con_430, "430")
    assert firma == (f.nombre, f.activa, f.tipos_venta, f.r_semanas, f.ventana_meses, f.nuevo_meses, f.corte_a_pct,
                     f.corte_b_pct, f.gestion_dias, f.bodegas_stock, f.bodegas_aparte, f.bodegas_informativas)
    assert _conteos(con_430) == antes


@pytest.mark.parametrize("cuerpo", ['{"r_semanas": NaN}', '{"gestion_dias": Infinity}', '{"corte_b_pct": -Infinity}'])
def test_nan_e_infinito_no_son_numeros(client, con_430, cuerpo):
    r = client.put(f"{URL}/430", content=cuerpo, headers={"Content-Type": "application/json"})
    assert "número finito" in _problemas(r)


@pytest.mark.parametrize("campos,pares", [
    # una bodega no puede estar en dos de las tres listas; se compara sin signos ni espacios ni mayusculas
    ({"bodegas_aparte": ["bodega-ml"]}, ["bodegas_stock", "bodegas_aparte"]),
    ({"bodegas_informativas": ["BODEGA  ML"]}, ["bodegas_stock", "bodegas_informativas"]),
    ({"bodegas_informativas": ["bodega ml full"]}, ["bodegas_aparte", "bodegas_informativas"]),
    ({"bodegas_stock": ["CD REPUESTOS"]}, ["bodegas_stock", "bodegas_informativas"]),
    ({"bodegas_stock": ["BODEGA ML", "bodega-ml-full"]}, ["bodegas_stock", "bodegas_aparte"]),
])
def test_una_bodega_no_puede_estar_en_dos_listas(client, con_430, campos, pares):
    texto = _problemas(_put(client, **campos))
    assert "cada bodega va en una sola lista" in texto
    for p in pares:
        assert bodegas_cd.ETIQUETA[p] in texto


def test_el_mismo_nombre_repetido_dentro_de_una_lista_no_es_un_choque(client, con_430):
    r = _put(client, bodegas_stock=["BODEGA ML", "bodega ml", "BODEGA-ML"])
    assert r.status_code == 200 and r.json()["bodegas_stock"] == ["BODEGA ML"]


def test_los_cortes_se_comparan_con_el_otro_corte_ya_guardado(client, con_430):
    assert _put(client, corte_a_pct=96).status_code == 400  # el B guardado es 95
    assert _put(client, corte_b_pct=79).status_code == 400  # el A guardado es 80
    assert _put(client, corte_a_pct=96, corte_b_pct=99).status_code == 200  # juntos si valen


def test_si_un_campo_viene_mal_no_se_guarda_ninguno_y_se_informan_todos_los_problemas(client, con_430):
    antes = _conteos(con_430)
    r = _put(client, nombre="Nombre nuevo", r_semanas=3, nuevo_meses=99, gestion_dias=-2,
             tipos_venta=[], bodegas_aparte=["BODEGA ML"])
    texto = _problemas(r)
    for esperado in ("entre 1 y 12", "entre 0 y 30", "Tipos de venta", "cada bodega va en una sola lista"):
        assert esperado in texto, texto
    assert len(r.json()["detail"]["problemas"]) >= 4
    f = _fila(con_430, "430")
    assert f.nombre == "Canal digital 430" and f.r_semanas == 1  # ni siquiera los campos buenos
    assert _conteos(con_430) == antes  # sin auditoria


def test_un_rechazo_no_descarta_la_corrida_en_cache(client, con_430):
    client.get("/api/canal-digital/resumen")
    clave = next(iter(router_cd._cache))
    assert _put(client, nuevo_meses=99).status_code == 400
    assert clave in router_cd._cache


# --------------------------------------------------------------------------- PUT: 404 y permisos

def test_guardar_una_bodega_que_no_existe_da_404_y_no_la_crea(client, con_430):
    antes = _conteos(con_430)
    r = _put(client, "999", r_semanas=2)
    assert r.status_code == 404 and "999" in r.json()["detail"]
    assert _conteos(con_430) == antes


def test_guardar_la_430_la_siembra_si_faltaba(client, db_session):
    r = _put(client, "430", r_semanas=2)
    assert r.status_code == 200 and r.json()["r_semanas"] == 2
    assert db_session.query(CanalDigitalPolitica).filter_by(bodega="430").count() == 27


def test_un_usuario_de_solo_lectura_no_puede_editar(client, con_430):
    _usuario(con_430, "lector@curifor.com", solo_lectura=True)
    _como("lector@curifor.com")
    antes = _conteos(con_430)
    r = _put(client, r_semanas=5)
    assert r.status_code == 403
    assert _fila(con_430, "430").r_semanas == 1 and _conteos(con_430) == antes
    assert client.get(URL).status_code == 200  # ver, si


def test_editar_pide_escritura_y_no_admin(client, con_430):
    _como("noadmin@curifor.com")  # existe en el seed, no es admin y puede escribir
    assert _put(client, r_semanas=4).status_code == 200
    assert _fila(con_430, "430").r_semanas == 4


# --------------------------------------------------------------------------- PUT: auditoria, cache y tipos de venta

def test_guardar_deja_auditoria_con_quien_y_que_cambio(client, con_430):
    assert _put(client, r_semanas=2, tipos_venta=["VTA ML", "VTA PARIS"]).status_code == 200
    reg = con_430.query(AuditoriaLog).filter_by(accion="canal_digital_bodega").one()
    assert reg.entidad == "canal_digital" and reg.entidad_id == "430" and reg.usuario_email == "test@curifor.com"
    assert "r_semanas 1 -> 2" in reg.detalle
    assert "tipos_venta [VTA ML, VTA SHOPIFY, VTA WALMART, VTA PARIS] -> [VTA ML, VTA PARIS]" in reg.detalle
    assert "corte_a_pct" not in reg.detalle  # solo lo que cambio


def test_guardar_descarta_la_corrida_en_cache_y_el_resumen_refleja_el_cambio(client, con_430):
    svc.reemplazar_ventas(con_430, "430", _filas_venta("20 ALTO", 20) + _filas_venta("20 MEDIO", 5) + _filas_venta("20 BAJO", 1))
    letra = lambda: {  # noqa: E731
        i["producto"]: i["valor"] for i in client.get("/api/canal-digital/productos").json()["items"]
    }
    antes = letra()  # esto deja la corrida en cache
    assert antes["20 MEDIO"] == "A" and router_cd._cache
    # con el corte A en 50% el segundo producto (que arranca en 77% acumulado) ya no es A
    assert _put(client, corte_a_pct=50).status_code == 200
    assert not router_cd._cache
    despues = letra()
    assert despues["20 ALTO"] == "A" and despues["20 MEDIO"] == "B", despues


def test_las_semanas_entre_revisiones_cambian_lo_que_se_sugiere(client, con_430):
    svc.reemplazar_ventas(con_430, "430", _filas_venta("20 ALTO", 20))
    unidades = lambda: client.get("/api/canal-digital/resumen").json()["totales"]["unidades_sugeridas"]  # noqa: E731
    uno = unidades()
    assert _put(client, r_semanas=4).status_code == 200
    assert unidades() > uno > 0


def test_cambiar_los_tipos_de_venta_avisa_que_aplica_a_las_cargas_futuras(client, con_430):
    r = _put(client, tipos_venta=["VTA ML"])
    assert r.json()["avisos"] == [bodegas_cd.AVISO_TIPOS_VENTA]
    assert "próxima carga" in r.json()["avisos"][0] and "no se vuelve a filtrar" in r.json()["avisos"][0]
    # otro cambio no repite el aviso
    assert _put(client, r_semanas=3).json()["avisos"] == []


def _linea(tipo_venta, numero):
    return {"periodo": "202609", "tipo_docto": "FA-ELECTR REPTO", "numero": numero, "fecha": "2026-09-10",
            "tipo_venta": tipo_venta, "producto": "P1", "cantidad": 2, "costo_neto": 100, "doc_ref": "", "nro_doc_ref": ""}


def test_los_tipos_nuevos_filtran_la_proxima_carga_y_no_tocan_lo_ya_guardado(client, con_430):
    r = svc.reemplazar_lineas(con_430, "430", [_linea("VTA ML", "1"), _linea("VTA PARIS", "2")])
    assert r["lineas_cargadas"] == 2
    assert _put(client, tipos_venta=["VTA ML"]).status_code == 200
    # lo guardado no cambia: las dos lineas siguen ahi
    assert con_430.query(CanalDigitalVenta).one().n_lineas == 2
    # la carga siguiente ya filtra con los tipos nuevos: la de PARIS no entra
    r = svc.reemplazar_lineas(con_430, "430", [_linea("VTA ML", "3"), _linea("VTA PARIS", "4")])
    assert r["lineas_cargadas"] == 1 and r["estadisticas"]["ignoradas_tipo_venta"] == 1


# --------------------------------------------------------------------------- POST: crear

def test_el_admin_crea_una_bodega_con_sus_27_filas_de_politica_y_parametros_de_siembra(client, con_430):
    r = client.post(URL, json={"bodega": " ab12 ", "nombre": " Canal Walmart "})
    assert r.status_code == 201, r.text
    nueva = r.json()
    assert nueva["bodega"] == "AB12" and nueva["nombre"] == "Canal Walmart" and nueva["activa"] is True
    assert nueva["tipos_venta"] == ["VTA ML", "VTA SHOPIFY", "VTA WALMART", "VTA PARIS"]
    assert (nueva["r_semanas"], nueva["ventana_meses"], nueva["nuevo_meses"], nueva["corte_a_pct"],
            nueva["corte_b_pct"], nueva["gestion_dias"]) == (1, 12, 6, 80, 95, 1)
    assert con_430.query(CanalDigitalPolitica).filter_by(bodega="AB12").count() == 27
    assert [b["bodega"] for b in client.get(URL).json()["bodegas"]] == ["430", "AB12"]
    reg = con_430.query(AuditoriaLog).filter_by(accion="canal_digital_bodega_nueva").one()
    assert reg.entidad_id == "AB12" and reg.usuario_email == "test@curifor.com" and "Canal Walmart" in reg.detalle


def test_sin_nombre_se_llama_canal_digital_y_el_codigo(client, con_430):
    r = client.post(URL, json={"bodega": "700"})
    assert r.status_code == 201 and r.json()["nombre"] == "Canal digital 700"


def test_crear_con_la_tabla_vacia_siembra_tambien_la_430(client, db_session):
    assert client.post(URL, json={"bodega": "500", "nombre": "Cinco"}).status_code == 201
    assert sorted(b.bodega for b in db_session.query(CanalDigitalBodega)) == ["430", "500"]
    assert [b["bodega"] for b in client.get(URL).json()["bodegas"]] == ["430", "500"]


@pytest.mark.parametrize("repetida", ["430", "500", " 500 "])
def test_un_codigo_que_ya_existe_da_409_y_no_cambia_nada(client, con_430, repetida):
    svc.asegurar_bodega(con_430, "500")
    antes = _conteos(con_430)
    r = client.post(URL, json={"bodega": repetida, "nombre": "Otra"})
    assert r.status_code == 409 and "ya existe" in r.json()["detail"]
    assert _conteos(con_430) == antes
    assert _fila(con_430, repetida.strip()).nombre != "Otra"


def test_el_codigo_repetido_se_detecta_aunque_venga_en_minusculas(client, con_430):
    assert client.post(URL, json={"bodega": "ab1"}).status_code == 201
    assert client.post(URL, json={"bodega": "AB1"}).status_code == 409
    assert client.post(URL, json={"bodega": "aB1"}).status_code == 409


def test_la_430_en_una_tabla_vacia_tambien_da_409(client, db_session):
    r = client.post(URL, json={"bodega": "430", "nombre": "Mi 430"})
    assert r.status_code == 409
    assert db_session.query(CanalDigitalBodega).one().nombre == "Canal digital 430"


@pytest.mark.parametrize("cuerpo,texto", [
    ({"bodega": ""}, "de 1 a 12 letras o números"), ({"bodega": "   "}, "de 1 a 12 letras o números"),
    ({"bodega": "AB CD"}, "de 1 a 12 letras o números"), ({"bodega": "A-1"}, "de 1 a 12 letras o números"),
    ({"bodega": "Ñ1"}, "de 1 a 12 letras o números"), ({"bodega": "１２３"}, "de 1 a 12 letras o números"),
    ({"bodega": "1234567890123"}, "de 1 a 12 letras o números"), ({"bodega": 500}, "de 1 a 12 letras o números"),
    ({"bodega": None}, "de 1 a 12 letras o números"), ({"nombre": "Sin codigo"}, "de 1 a 12 letras o números"),
    ({"bodega": "500", "nombre": ""}, "no puede quedar vacío"), ({"bodega": "500", "nombre": "  "}, "no puede quedar vacío"),
    ({"bodega": "500", "nombre": 7}, "debe ser un texto"), ({"bodega": "500", "nombre": "x" * 61}, "pasa de 60"),
    ({"bodega": "500", "r_semanas": 2}, "se ajustan después"),
])
def test_crear_con_datos_invalidos_da_400_y_no_crea_nada(client, con_430, cuerpo, texto):
    antes = _conteos(con_430)
    r = client.post(URL, json=cuerpo)
    assert texto in _problemas(r)
    assert _conteos(con_430) == antes


def test_el_codigo_de_12_caracteres_y_el_de_1_valen(client, con_430):
    assert client.post(URL, json={"bodega": "A1B2C3D4E5F6"}).status_code == 201
    assert client.post(URL, json={"bodega": "9"}).status_code == 201


def test_crear_pide_admin(client, con_430):
    _como("noadmin@curifor.com")
    antes = _conteos(con_430)
    r = client.post(URL, json={"bodega": "500", "nombre": "X"})
    assert r.status_code == 403
    assert _conteos(con_430) == antes


def test_no_hay_forma_de_borrar_una_bodega(client, con_430):
    assert client.delete(f"{URL}/430").status_code == 405
    assert client.delete(URL).status_code == 405
