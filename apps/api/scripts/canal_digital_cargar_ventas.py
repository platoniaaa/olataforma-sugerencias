"""Lee los respaldos anuales de ventas (Excel) y arma la venta semanal del canal.

Es lo que `venta_historica` no trae: tipo de venta y fecha del dia. La regla vive en
`src.canal_digital.ventas_semanales` (la misma que usa la plataforma); aqui solo se leen
los Excel y se entrega el resultado.

Por defecto NO publica nada: escribe un CSV con las filas y muestra el resumen. Para
publicar, el motor llama como admin (variables CANAL_DIGITAL_API y CANAL_DIGITAL_TOKEN, nunca
por argumento) a uno de dos endpoints:

  --publicar         POST /api/canal-digital/ventas: las filas ya agregadas.
  --publicar-lineas  POST /api/canal-digital/lineas: las lineas del ERP, UN envio por mes (el
                     endpoint reemplaza el periodo que viene) y la plataforma recalcula la venta
                     completa, de modo que una devolucion de un mes encuentre su venta de otro mes.

    python scripts/canal_digital_cargar_ventas.py --carpeta "<...>/Bases de datos/Ventas" \
        --anios 2025 2026 --salida ventas_canal.csv
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from src.canal_digital.ventas_semanales import (  # noqa: E402
    TIPOS_VENTA_DEFECTO, LineaVenta, agregar, indice_originales, normalizar_codigo, normalizar_numero,
)

COLS = {
    "periodo": "Periodo", "tipo_docto": "tipoDocto", "numero": "Numero", "fecha": "Fecha",
    "tipo_venta": "Tipo-Venta", "producto": "Producto", "cantidad": "Cantidad", "costo": "Costo Neto",
    "doc_ref": "Documento Referencia", "nro_doc_ref": "Nro Documento Referencia",
}


def _num(v) -> float:
    if v is None or isinstance(v, bool):
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(".", "").replace(",", ".").strip())
    except ValueError:
        return 0.0


def _fecha(v) -> dt.date | None:
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    if isinstance(v, (int, float)):  # serial de Excel
        return (dt.datetime(1899, 12, 30) + dt.timedelta(days=float(v))).date()
    t = str(v or "").strip()
    for f in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(t[:10], f).date()
        except ValueError:
            pass
    return None


def leer_archivo(ruta: pathlib.Path, tipos_venta) -> tuple[list[LineaVenta], dict]:
    """Las lineas del canal de un respaldo. Lee en modo read_only (no carga el libro entero)."""
    import openpyxl

    tipos = set(tipos_venta)
    wb = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
    out: list[LineaVenta] = []
    resumen = {"filas_leidas": 0, "sin_fecha": 0, "sin_producto": 0}
    try:
        it = wb[wb.sheetnames[0]].iter_rows(values_only=True)
        cab = [str(c).strip() if c is not None else "" for c in next(it)]
        faltan = [n for k, n in COLS.items() if k not in ("doc_ref", "nro_doc_ref") and n not in cab]
        if faltan:
            raise ValueError(f"{ruta.name}: faltan columnas {faltan}")
        ix = {k: cab.index(n) if n in cab else None for k, n in COLS.items()}
        for row in it:
            resumen["filas_leidas"] += 1
            if not row:
                continue
            tv = str(row[ix["tipo_venta"]] or "").strip()
            if tv not in tipos:
                continue
            f = _fecha(row[ix["fecha"]])
            if f is None:
                resumen["sin_fecha"] += 1
                continue
            prod = normalizar_codigo(row[ix["producto"]])
            if prod is None:
                resumen["sin_producto"] += 1
                continue
            g = lambda k: row[ix[k]] if ix[k] is not None else None  # noqa: E731
            out.append(LineaVenta(
                periodo=str(g("periodo")).strip().split(".")[0],
                tipo_docto=str(g("tipo_docto") or "").strip(),
                numero=normalizar_numero(g("numero")),
                fecha=f, tipo_venta=tv, producto=prod,
                cantidad=_num(g("cantidad")), costo_neto=_num(g("costo")),
                doc_ref=str(g("doc_ref") or "").strip(), nro_doc_ref=normalizar_numero(g("nro_doc_ref")),
            ))
    finally:
        wb.close()
    return out, resumen


def _enviar(ruta: str, cuerpo: dict) -> dict:
    base = os.environ.get("CANAL_DIGITAL_API", "").rstrip("/")
    token = os.environ.get("CANAL_DIGITAL_TOKEN", "")
    if not base or not token:
        raise SystemExit("Faltan las variables CANAL_DIGITAL_API y CANAL_DIGITAL_TOKEN (no se pasan por argumento).")
    req = urllib.request.Request(
        f"{base}{ruta}",
        data=json.dumps(cuerpo).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise SystemExit(f"{ruta} respondio {e.code}: {e.read().decode('utf-8', 'replace')[:500]}")


def publicar(filas: list[dict], bodega: str) -> dict:
    return _enviar("/api/canal-digital/ventas", {"bodega": bodega, "filas": filas})


def linea_a_dict(l: LineaVenta) -> dict:
    """La linea con los nombres del contrato de POST /api/canal-digital/lineas."""
    return {
        "periodo": l.periodo, "tipo_docto": l.tipo_docto, "numero": l.numero, "fecha": l.fecha.isoformat(),
        "tipo_venta": l.tipo_venta, "producto": l.producto, "cantidad": l.cantidad, "costo_neto": l.costo_neto,
        "doc_ref": l.doc_ref, "nro_doc_ref": l.nro_doc_ref,
    }


def lineas_por_mes(lineas: list[LineaVenta], desde_periodo: str | None = None) -> dict[str, list[dict]]:
    """periodo -> sus lineas en formato del contrato. El endpoint reemplaza el periodo entero: un mes no se parte.

    Con `desde_periodo` los meses anteriores no se envian: tienen que estar ya cargados en la plataforma para que
    una devolucion de un mes nuevo encuentre su venta. Las lineas sin periodo YYYYMM se dejan fuera.
    """
    por_mes: dict[str, list[dict]] = {}
    for l in lineas:
        if len(l.periodo) != 6 or not l.periodo.isdigit():
            continue
        if desde_periodo and l.periodo < desde_periodo:
            continue
        por_mes.setdefault(l.periodo, []).append(linea_a_dict(l))
    return dict(sorted(por_mes.items()))


def publicar_lineas(por_mes: dict[str, list[dict]], bodega: str) -> list[dict]:
    """Un envio por mes, del mas antiguo al mas nuevo. Devuelve la respuesta de cada uno."""
    respuestas = []
    for periodo, lineas in por_mes.items():
        r = _enviar("/api/canal-digital/lineas", {"bodega": bodega, "lineas": lineas})
        print(f"  {periodo}: {r['lineas_cargadas']:,} lineas ({r['lineas_ignoradas']:,} ignoradas), "
              f"{r['filas_venta']:,} filas de venta", flush=True)
        respuestas.append(r)
    return respuestas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--carpeta", required=True, help="carpeta con los respaldos anuales (Ventas)")
    ap.add_argument("--anios", nargs="+", required=True, help="anios a leer, ej. 2025 2026")
    ap.add_argument("--desde-periodo", help="solo cargar periodos >= YYYYMM (los anteriores sirven solo para ubicar originales)")
    ap.add_argument("--bodega", default="430")
    ap.add_argument("--salida", help="CSV con las filas resultantes")
    ap.add_argument("--publicar", action="store_true", help="enviar las filas agregadas a /ventas (admin)")
    ap.add_argument("--publicar-lineas", action="store_true",
                    help="enviar las lineas del ERP a /lineas, un envio por mes (admin); la plataforma arma la venta")
    a = ap.parse_args()
    if a.publicar and a.publicar_lineas:
        ap.error("--publicar y --publicar-lineas no se combinan: elige uno")

    carpeta = pathlib.Path(a.carpeta)
    lineas: list[LineaVenta] = []
    for anio in a.anios:
        archivos = [p for p in carpeta.glob("*.xlsx") if anio in p.name and not p.name.startswith("~$")
                    and "Lubricantes" not in p.name and "frontera" not in p.name]
        if not archivos:
            raise SystemExit(f"No hay respaldo de {anio} en {carpeta}")
        for p in archivos:
            print(f"Leyendo {p.name} ...", flush=True)
            l, r = leer_archivo(p, TIPOS_VENTA_DEFECTO)
            print(f"  {r['filas_leidas']:,} filas, {len(l):,} del canal ({r})")
            lineas += l
    originales = indice_originales(lineas, TIPOS_VENTA_DEFECTO)
    periodos = None
    if a.desde_periodo:
        periodos = sorted({l.periodo for l in lineas if l.periodo >= a.desde_periodo})
    res = agregar(lineas, TIPOS_VENTA_DEFECTO, originales, periodos)
    print(f"Filas: {len(res.filas):,}; unidades netas {res.unidades_netas:,.0f}")
    for k, v in sorted(res.estadisticas.items()):
        print(f"  {k}: {v}")
    filas = [f.__dict__ for f in res.filas]
    if a.salida:
        with open(a.salida, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(filas[0].keys()))
            w.writeheader()
            w.writerows(filas)
        print("CSV:", a.salida)
    if a.publicar:
        print("Publicado:", publicar(filas, a.bodega))
    elif a.publicar_lineas:
        por_mes = lineas_por_mes(lineas, a.desde_periodo)
        print(f"Publicando lineas de {len(por_mes)} meses ...")
        publicar_lineas(por_mes, a.bodega)
        print("Publicado.")
    else:
        print("No se publico nada (falta --publicar o --publicar-lineas).")


if __name__ == "__main__":
    main()
