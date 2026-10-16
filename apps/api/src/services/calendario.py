"""Fechas en hora de Chile y dias habiles.

Dos piezas que antes vivian repetidas o mal:

- `dias_habiles_entre` estaba dentro de `routers/auditoria.py` (el aviso de
  "sugerido desactualizado"). Fuentes de datos la necesita para medir la edad de
  cada archivo, asi que se saco aca y auditoria la importa.
- `hoy_chile` existe porque `datetime.now(timezone.utc).date()` se equivoca de dia
  todas las noches: desde las 21:00 hora de Chile (20:00 en horario de verano),
  en UTC ya es el dia siguiente. Un semaforo que a las 22:00 dice "el archivo es de
  ayer" sobre un archivo de hoy es un semaforo que nadie mira.

Feriados: no se consideran (solo sabados y domingos), igual que el motor.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

TZ_CHILE = ZoneInfo("America/Santiago")


def dias_habiles_entre(desde: date, hasta: date) -> int:
    """Dias habiles transcurridos entre dos fechas (sabados y domingos no cuentan).

    Se cuenta en dias HABILES y no en horas porque la tarea corre de lunes a
    viernes: contando horas, todos los lunes avisaria que los datos son "de hace
    3 dias" cuando en realidad la ultima corrida fue la que correspondia. Un aviso
    que se equivoca todos los lunes es un aviso que nadie mira.
    """
    if hasta <= desde:
        return 0
    dias = 0
    cursor = desde
    while cursor < hasta:
        cursor += timedelta(days=1)
        if cursor.weekday() < 5:  # 0=lunes .. 4=viernes
            dias += 1
    return dias


def ahora_chile() -> datetime:
    """La hora actual en Chile (con zona horaria)."""
    return datetime.now(TZ_CHILE)


def hoy_chile() -> date:
    """La fecha de hoy en Chile, no en UTC."""
    return ahora_chile().date()


def a_chile(dt: datetime) -> datetime:
    """Pasa una fecha a hora de Chile. Una fecha sin zona se toma como UTC, que es
    como la devuelve SQLite (Postgres la devuelve con zona)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(TZ_CHILE)


def inicio_del_dia_chile(dia: date) -> datetime:
    """Las 00:00 de ese dia en Chile, expresadas en UTC (para comparar en la base)."""
    return datetime(dia.year, dia.month, dia.day, tzinfo=TZ_CHILE).astimezone(timezone.utc)
