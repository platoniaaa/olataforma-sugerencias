"""Una regla recurrente que termina por fecha deja de sumar ese dia, no nunca.

Hasta el 19-10 la regla se apagaba sola al pasar su fecha de termino, pero su ultima
instancia quedaba vigente, sin vencimiento, sumando a la compra, y ninguna pestana la
mostraba (Recurrentes lista solo las activas). En produccion: 15 u en TALCA desde el
01-06 por una regla que termino el 07-06. Ademas se aceptaba una fecha de termino ya
pasada: la regla nacia apagada y dejaba igual su instancia.
"""
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from src.models import SugerenciaManual, SugerenciaRecurrente
from src.schemas import RecurrenteCreate
from src.services import recurrentes_service
from src.services.calendario import TZ_CHILE

PAR = {"producto": "20 BXO5W30AA", "sucursal_id": "LINDEROS"}


def _vigentes(db_session, rec_id: str) -> list[SugerenciaManual]:
    return list(db_session.scalars(
        select(SugerenciaManual).where(
            SugerenciaManual.recurrente_id == rec_id,
            SugerenciaManual.archivada.is_(False),
        )
    ).all())


def _carro_aceite(client) -> float:
    """El seed pide 6 u netas de este aceite; lo que sobre es de la regla."""
    carros = client.get("/api/compras/carros").json()["carros"]
    return sum(
        linea["cantidad"] for c in carros for linea in c["lineas"]
        if linea["producto"] == PAR["producto"]
    )


def _regla(db_session, fecha_fin: date, cada_dias: int = 7) -> SugerenciaRecurrente:
    return recurrentes_service.crear(
        db_session,
        RecurrenteCreate(modo="individual", unidades=15, cada_dias=cada_dias,
                         fecha_fin=fecha_fin, **PAR),
    )


def test_la_ultima_instancia_deja_de_sumar_cuando_la_regla_termina(client, db_session):
    """Regla de 15 u cada 7 dias por 30 dias, con el cron simulado dia a dia."""
    hoy = date.today()
    rec = _regla(db_session, fecha_fin=hoy + timedelta(days=30))
    assert _carro_aceite(client) == 21

    for dia in range(1, 31):
        recurrentes_service.procesar(db_session, hoy + timedelta(days=dia))
    db_session.refresh(rec)
    # El dia 28 fue su ultima ejecucion: ya no le toca otra antes del dia 30, asi
    # que se apago. Pero hasta el dia 30 inclusive su instancia sigue valiendo.
    assert rec.activa is False
    assert len(_vigentes(db_session, rec.id)) == 1
    assert _carro_aceite(client) == 21

    recurrentes_service.procesar(db_session, hoy + timedelta(days=31))
    assert _vigentes(db_session, rec.id) == []
    assert _carro_aceite(client) == 6


def test_las_instancias_vencen_solas_al_terminar_el_dia_en_chile(db_session):
    """No dependen del cron: dejan de sumar a la hora exacta aunque nadie las archive."""
    fin = date.today() + timedelta(days=10)
    rec = _regla(db_session, fecha_fin=fin)
    [instancia] = _vigentes(db_session, rec.id)
    esperado = datetime(fin.year, fin.month, fin.day, tzinfo=TZ_CHILE) + timedelta(days=1)
    expira = instancia.expira_en
    if expira.tzinfo is None:  # SQLite la devuelve sin zona
        expira = expira.replace(tzinfo=timezone.utc)
    assert expira == esperado.astimezone(timezone.utc)


def test_sin_fecha_de_termino_la_instancia_no_vence(db_session):
    rec = recurrentes_service.crear(
        db_session, RecurrenteCreate(modo="individual", unidades=5, cada_dias=7, **PAR)
    )
    [instancia] = _vigentes(db_session, rec.id)
    assert instancia.expira_en is None


def test_una_regla_que_termina_antes_de_su_segundo_ciclo_suma_hasta_ese_dia(
    client, db_session
):
    """Cada 7 dias hasta dentro de 3: nace apagada (no le toca otra ejecucion), y su
    unica instancia tiene que valer esos 3 dias. Archivarla al apagarla la dejaria
    sin ningun efecto."""
    hoy = date.today()
    rec = _regla(db_session, fecha_fin=hoy + timedelta(days=3))
    assert rec.activa is False
    for dia in range(0, 4):
        recurrentes_service.procesar(db_session, hoy + timedelta(days=dia))
        assert len(_vigentes(db_session, rec.id)) == 1, f"se archivo el dia {dia}"
    assert _carro_aceite(client) == 21
    recurrentes_service.procesar(db_session, hoy + timedelta(days=4))
    assert _vigentes(db_session, rec.id) == []


def test_procesar_limpia_la_instancia_huerfana_de_antes_del_arreglo(client, db_session):
    """El caso de produccion: regla apagada que termino hace meses, con su instancia
    vigente y sin vencimiento (se creo antes de que existiera `expira_en`)."""
    hace_meses = date.today() - timedelta(days=134)
    rec = SugerenciaRecurrente(
        tenant_id="curifor", modo="individual", unidades=15, cada_dias=7,
        fecha_fin=hace_meses, proxima_ejecucion=hace_meses + timedelta(days=1),
        activa=False, creado_por="test@curifor.com", **PAR,
    )
    db_session.add(rec)
    db_session.flush()
    db_session.add(SugerenciaManual(
        tenant_id="curifor", unidades=15, creado_por="recurrente", recurrente_id=rec.id,
        **PAR,
    ))
    db_session.commit()
    assert _carro_aceite(client) == 21

    r = client.post("/api/admin/procesar-recurrentes")
    assert r.status_code == 200
    assert r.json()["instancias_de_reglas_apagadas"] == 1
    assert _vigentes(db_session, rec.id) == []
    assert _carro_aceite(client) == 6
    # Llamarlo de nuevo no hace nada.
    assert client.post("/api/admin/procesar-recurrentes").json()[
        "instancias_de_reglas_apagadas"] == 0


def test_una_regla_activa_no_pierde_su_instancia(client, db_session):
    rec = recurrentes_service.crear(
        db_session, RecurrenteCreate(modo="individual", unidades=5, cada_dias=7, **PAR)
    )
    recurrentes_service.procesar(db_session, date.today() + timedelta(days=1))
    assert len(_vigentes(db_session, rec.id)) == 1
    assert _carro_aceite(client) == 11


def test_no_se_acepta_una_fecha_de_termino_pasada(client, db_session):
    ayer = date.today() - timedelta(days=1)
    r = client.post(
        "/api/sugerencias-manuales/recurrentes",
        json={"modo": "individual", "unidades": 5, "cada_dias": 7,
              "fecha_fin": ayer.isoformat(), **PAR},
    )
    assert r.status_code == 422
    assert "ya pasó" in r.json()["detail"]
    assert db_session.query(SugerenciaRecurrente).count() == 0
    assert db_session.query(SugerenciaManual).count() == 0


def test_una_fecha_pasada_no_cierra_lo_que_habia(client, db_session):
    """Con "reemplazar" el modal cierra lo cargado antes de crear la regla. Si la regla
    se rechaza, lo de antes tiene que seguir sumando."""
    client.post("/api/sugerencias-manuales", json={**PAR, "unidades": 4})
    r = client.post(
        "/api/sugerencias-manuales/recurrentes",
        json={"modo": "individual", "unidades": 5, "cada_dias": 7, "reemplazar": True,
              "fecha_fin": (date.today() - timedelta(days=2)).isoformat(), **PAR},
    )
    assert r.status_code == 422
    assert _carro_aceite(client) == 10


def test_terminar_hoy_si_se_acepta(client):
    r = client.post(
        "/api/sugerencias-manuales/recurrentes",
        json={"modo": "individual", "unidades": 5, "cada_dias": 7,
              "fecha_fin": date.today().isoformat(), **PAR},
    )
    assert r.status_code == 201, r.text
    assert _carro_aceite(client) == 11
