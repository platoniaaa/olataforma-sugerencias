"""Arma el Excel de la PRIMERA VERSION (provisoria) de Canal Digital para la bodega 430.

Lee los CSV que dejaron los cruces 1 a 7 (carpeta de datos), calcula con el nucleo puro
`src.canal_digital` (el mismo que usara la plataforma) y escribe un libro con:
  Leeme, Vista principal, Resumen por cluster, Politica, Paso a paso, Validaciones,
  Sin movimiento con stock, Excepciones.

Solo lectura: no toca la base, la plataforma ni ningun archivo existente.

Uso (desde apps/api):
    python scripts/canal_digital_excel.py --datos C:/ruta/canal-digital-datos --salida salida.xlsx
Requiere pandas y xlsxwriter (herramienta de analisis, no es dependencia de la API).
"""
from __future__ import annotations

import argparse
import datetime as dt
import pathlib
import sys
from collections import Counter

import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from src.canal_digital.clasificacion import (  # noqa: E402
    ESTADO_CLASIFICADO, ESTADO_NUEVO, ESTADO_SIN_MOVIMIENTO, ParametrosClasificacion,
    VentaProducto, clasificar, ejecutar_validaciones, resumen_por_cluster,
)
from src.canal_digital.corrida import DatosProducto, correr  # noqa: E402
from src.canal_digital.paso_a_paso import explicar_producto, texto_completo  # noqa: E402
from src.canal_digital.politica import CLUSTERS, MODO_FORMULA, politica_provisoria  # noqa: E402
from src.canal_digital.reposicion import (  # noqa: E402
    EntradaReposicion, ParametrosReposicion, calcular_reposicion,
)

PREFIJO = "canal_digital_"
FECHA_STOCK = "19-10-2026"
FIN_VENTANA = dt.date(2026, 9, 30)
FECHA_REFERENCIA = dt.date(2026, 10, 1)
MESES = [f"{2025 + (9 + i) // 12}{(9 + i) % 12 + 1:02d}" for i in range(12)]  # 202510 .. 202609
ETIQUETAS_MES = ["oct-25", "nov-25", "dic-25", "ene-26", "feb-26", "mar-26",
                 "abr-26", "may-26", "jun-26", "jul-26", "ago-26", "sep-26"]
N_SEMANAS = 52
GESTION_DIAS = 1          # decision 9: +1 dia de gestion
EXCLUIR_PRODUCTOS = ("CUP000492",)       # decision 3: sin costo ni ficha
EXCLUIR_TIPO_DOCTO = ("SALIDA ACCESORIOS",)  # decision 3: no es venta


def leer(datos: pathlib.Path, nombre: str, **kw) -> pd.DataFrame:
    return pd.read_csv(datos / f"{PREFIJO}{nombre}.csv", **kw)


def bloque_semana(fecha: dt.date, inicio: dt.date) -> int | None:
    k = (fecha - inicio).days // 7
    return k if 0 <= (fecha - inicio).days and k < N_SEMANAS else None


def cargar(datos: pathlib.Path):
    c1 = leer(datos, "cruce1")
    excep = c1[c1.producto_norm.isin(EXCLUIR_PRODUCTOS) | c1.tipo_docto.isin(EXCLUIR_TIPO_DOCTO)].copy()
    c1 = c1.drop(excep.index).copy()
    mapa = leer(datos, "cruce3")[["codigo", "padre"]].drop_duplicates("codigo")
    padre_de = dict(zip(mapa.codigo, mapa.padre))
    c1["padre"] = c1.producto_norm.map(lambda c: padre_de.get(c, c))
    pv = leer(datos, "primera_venta_empresa")
    primera = {r.padre: dt.date.fromisoformat(r.primera_venta_empresa) for r in pv.itertuples()}
    return c1, excep, padre_de, primera


def series(c1: pd.DataFrame):
    """Unidades y valor por mes (nota/venta en su mes) y unidades por semana por padre."""
    mes_u = c1.pivot_table(index="padre", columns="periodo", values="unid_neta", aggfunc="sum", fill_value=0)
    mes_v = c1.pivot_table(index="padre", columns="periodo", values="costo_firmado", aggfunc="sum", fill_value=0)
    for m in MESES:
        for t in (mes_u, mes_v):
            if int(m) not in t.columns:
                t[int(m)] = 0
    mes_u = mes_u[[int(m) for m in MESES]]
    mes_v = mes_v[[int(m) for m in MESES]]

    inicio = FIN_VENTANA - dt.timedelta(days=N_SEMANAS * 7 - 1)
    sem = {p: [0.0] * N_SEMANAS for p in mes_u.index}
    fuera = 0.0
    for r in c1.itertuples():
        f = dt.date.fromisoformat(r.fecha)
        if r.unid_bruta:
            k = bloque_semana(f, inicio)
            if k is None:
                fuera += r.unid_bruta
            else:
                sem[r.padre][k] += r.unid_bruta
        if r.unid_devuelta:
            fo = dt.date.fromisoformat(r.fecha_original) if isinstance(r.fecha_original, str) else f
            if fo > f:
                fo = f
            k = bloque_semana(fo, inicio)
            if k is None:
                fuera -= r.unid_devuelta
            else:
                sem[r.padre][k] -= r.unid_devuelta
    return mes_u, mes_v, sem, inicio, fuera


def construir(datos: pathlib.Path):
    c1, excep, padre_de, primera = cargar(datos)
    mes_u, mes_v, sem, inicio_sem, fuera_sem = series(c1)
    c4 = leer(datos, "cruce4").set_index("padre")
    c5 = leer(datos, "cruce5_ancho")
    c6 = leer(datos, "cruce6").set_index("padre")
    c7 = leer(datos, "cruce7_producto").set_index("padre")
    st = c5[c5.en_universo].set_index("padre")

    padres = sorted(mes_u.index)
    parametros = ParametrosClasificacion()
    pol = politica_provisoria()
    prep = ParametrosReposicion()

    datos_p = []
    for p in padres:
        s = st.loc[p] if p in st.index else None
        tr = c6.loc[p] if p in c6.index else None
        l7 = c7.loc[p] if p in c7.index else None
        if l7 is not None:
            dias = float(l7.lt_prom5_con_tope_o_respaldo_dias) + GESTION_DIAS
            cat = str(l7.categoria_lt)
            prov = str(l7.proveedor_id) if pd.notna(l7.proveedor_id) else ""
            lt_motor = float(l7.lt_motor_dias) if pd.notna(l7.lt_motor_dias) else None
            origen = f"{cat}; promedio de las ultimas 5 recepciones (sin las de 30 dias o mas) + {GESTION_DIAS} dia de gestion"
            if cat.startswith("sin proveedor"):
                origen = f"respaldo 3 dias + {GESTION_DIAS} dia de gestion (sin proveedor)"
        else:
            dias, cat, prov, lt_motor = 3.0 + GESTION_DIAS, "sin datos de compras", "", None
            origen = f"respaldo 3 dias + {GESTION_DIAS} dia de gestion (sin datos de compras)"
        costo = c4.costo_actual.get(p) if p in c4.index else None
        costo = float(costo) if costo is not None and pd.notna(costo) else None
        vig = str(c4.vigencia_costo_actual.get(p)) if p in c4.index else ""
        datos_p.append(DatosProducto(
            codigo=p,
            descripcion=str(c4.descripcion.get(p, "")) if p in c4.index else "",
            codigos_vendidos=str(c4.codigos_vendidos.get(p, p)) if p in c4.index else p,
            unidades_mes=[float(x) for x in mes_u.loc[p]], valor_mes=[float(x) for x in mes_v.loc[p]],
            primera_venta=primera.get(p), unidades_semana=sem[p],
            plazo_dias=dias, plazo_origen=origen, plazo_confianza=cat, proveedor=prov, plazo_motor_dias=lt_motor,
            stock_disponible=float(s.stock_BODEGA_ML) if s is not None else 0.0,
            stock_aparte=float(s.stock_BODEGA_ML_FULL) if s is not None else 0.0,
            stock_cd=float(s.stock_CD_REPUESTOS) if s is not None else 0.0,
            transito=float(tr.transito_r1_d1) if tr is not None else 0.0,
            transito_430_cd=float(tr.transito_r1_d2) if tr is not None else 0.0,
            transito_cualquier_destino=float(tr.transito_r1_d3) if tr is not None else 0.0,
            costo_actual=costo,
            costo_respaldo="sin respaldo de stock" if "sin stock" in vig
            else ("sin costo" if costo is None else "con stock del 19-oct"),
        ))
    corrida = correr(datos_p, pol, FECHA_REFERENCIA, parametros, prep)
    res = corrida.clasificacion

    filas, reposiciones, sugerido_pesos = [], {}, {}
    for pc in corrida.productos:
        dp = pc.datos
        p = dp.codigo
        c = res.producto(p)
        r, fila_pol = pc.reposicion, pc.fila_politica
        stock_ml, stock_full, stock_cd = dp.stock_disponible, dp.stock_aparte, dp.stock_cd
        t430, t430cd, tany = dp.transito, dp.transito_430_cd, dp.transito_cualquier_destino
        dias, cat, prov, lt_motor = dp.plazo_dias, dp.plazo_confianza, dp.proveedor, dp.plazo_motor_dias
        costo, pesos = dp.costo_actual, pc.sugerido_pesos
        vig = "sin stock" if dp.costo_respaldo == "sin respaldo de stock" else dp.costo_respaldo
        reposiciones[p] = (r, fila_pol, dp)
        sugerido_pesos[p] = pesos
        filas.append({
            "Producto (padre)": p,
            "Descripción": c4.descripcion.get(p, "") if p in c4.index else "",
            "Códigos vendidos": c4.codigos_vendidos.get(p, p) if p in c4.index else p,
            "Estado": c.estado,
            "Cluster": c.cluster or "",
            "Frecuencia": c.letra_frecuencia or "",
            "Piezas": c.clase_piezas or "",
            "Valor": c.clase_valor or "",
            "Meses con venta": c.meses_con_venta,
            "Unidades 12m": float(c.unidades_ventana),
            "Valor 12m ($, costo del período)": float(c.valor_ventana),
            "Primera venta empresa": c.primera_venta.isoformat() if c.primera_venta else "",
            "Acum. unidades antes (%)": float(c.acum_antes_unidades) if c.acum_antes_unidades is not None else None,
            "Acum. valor antes (%)": float(c.acum_antes_valor) if c.acum_antes_valor is not None else None,
            "Modo": r.modo or "",
            "Nivel de servicio": r.nivel_servicio,
            "z": r.z,
            "Demanda semanal D": r.demanda_semanal,
            "Desv. semanal σ": r.sigma_semanal,
            "Plazo L (días)": dias,
            "Plazo L (semanas)": dias / 7,
            "Plazo del motor (días, solo comparar)": lt_motor,
            "Proveedor": prov,
            "Confianza del plazo": cat,
            "Stock de seguridad SS": r.stock_seguridad,
            "Nivel objetivo S": r.nivel_objetivo,
            "Stock BODEGA ML (disponible 430)": stock_ml,
            "Stock ML-FULL (aparte, no suma)": stock_full,
            "Stock CD (informativo)": stock_cd,
            "Tránsito a la 430": t430,
            "Tránsito a 430 + CD (informativo)": t430cd,
            "Tránsito a cualquier destino (informativo)": tany,
            "Comprometido": r.comprometido_rotulo,
            "Posición de inventario": r.posicion,
            "Necesidad bruta": r.sugerido_bruto,
            "Mínimo de compra": r.minimo_compra,
            "Múltiplo": r.multiplo,
            "SUGERIDO (unidades)": r.sugerido,
            "Costo actual unitario ($)": costo,
            "Sugerido ($)": pesos,
            "Costo": "sin respaldo de stock" if "sin stock" in vig else ("sin costo" if costo is None else "con stock del 19-oct"),
            "Motivo": r.motivo,
            "Avisos": " | ".join(r.banderas),
        })
    vista = pd.DataFrame(filas)
    return dict(c1=c1, excep=excep, padre_de=padre_de, res=res, pol=pol, vista=vista, reps=reposiciones,
                sugerido_pesos=sugerido_pesos, c5=c5, c4=c4, c1_all_units=float(c1.unid_neta.sum()),
                fuera_sem=fuera_sem, inicio_sem=inicio_sem, parametros=parametros, c7=c7)


def hojas(d, destino: pathlib.Path):
    res, pol, vista = d["res"], d["pol"], d["vista"]
    resumen = resumen_por_cluster(res, d["sugerido_pesos"])
    pagos = vista.groupby("Cluster").agg(
        piden=("SUGERIDO (unidades)", lambda s: int((s > 0).sum())),
        unidades_sug=("SUGERIDO (unidades)", "sum"),
    )
    validaciones = ejecutar_validaciones(
        res, mapa_padre=d["padre_de"], total_unidades_universo=d["c1_all_units"],
    )
    extra = []
    ult = ETIQUETAS_MES[-1]
    ult_u = sum(float(p.unidades_mes[-1]) for p in res.productos)
    extra.append(("El último mes cerrado (sep-26) tiene ventas", ult_u > 0, f"{ult_u:g} unidades netas en {ult}"))
    ok_stock = abs(vista["Stock BODEGA ML (disponible 430)"].sum() - 5240) < 1e-6
    extra.append(("Stock BODEGA ML del universo = 5.240 u (cruce 5)", ok_stock,
                  f"{vista['Stock BODEGA ML (disponible 430)'].sum():g} u"))
    sin_prov = int((vista["Confianza del plazo"].str.startswith("sin")).sum())
    extra.append(("Plazo: productos con respaldo (sin proveedor)", True, f"{sin_prov} productos (dato de aviso, no error)"))
    total_sem = sum(sum(v) for v in d["reps"].values() for v in [v[2].unidades_semana])
    extra.append(("Serie semanal vs. neto mensual (diferencia = 1.er día + devoluciones de ventas anteriores)", True,
                  f"semanal {total_sem:g} u; mensual {d['c1_all_units']:g} u; fuera de las 52 semanas {d['fuera_sem']:g} u"))

    with pd.ExcelWriter(destino, engine="xlsxwriter") as xw:
        wb = xw.book
        h = wb.add_format({"bold": True, "bg_color": "#1F3A4D", "font_color": "white", "text_wrap": True,
                           "valign": "top", "border": 1})
        gris = wb.add_format({"bg_color": "#F2F2F2"})
        wrap = wb.add_format({"text_wrap": True, "valign": "top"})
        negr = wb.add_format({"bold": True, "font_size": 14})
        pct = wb.add_format({"num_format": "0.0%"})
        n0 = wb.add_format({"num_format": "#,##0"})
        n2 = wb.add_format({"num_format": "#,##0.00"})
        ok_f = wb.add_format({"bg_color": "#C6EFCE"})
        mal_f = wb.add_format({"bg_color": "#FFC7CE"})
        amar = wb.add_format({"bg_color": "#FFF2CC", "text_wrap": True, "valign": "top"})

        # ---- Leeme
        ws = wb.add_worksheet("Leeme"); xw.sheets["Leeme"] = ws
        ws.set_column(0, 0, 150)
        lineas = leeme_lineas(d, vista)
        for i, (txt, estilo) in enumerate(lineas):
            ws.write(i, 0, txt, {"t": negr, "p": amar, "n": wrap}[estilo])

        # ---- Vista principal
        vista.to_excel(xw, sheet_name="Vista principal", index=False, startrow=1, header=False)
        ws = xw.sheets["Vista principal"]
        for j, col in enumerate(vista.columns):
            ws.write(0, j, col, h)
            ancho = 14
            if col == "Descripción":
                ancho = 34
            elif col in ("Códigos vendidos", "Avisos", "Confianza del plazo", "Comprometido"):
                ancho = 30
            elif col == "Producto (padre)":
                ancho = 20
            ws.set_column(j, j, ancho, pct if "(%)" in col else None)
        for col in ("Unidades 12m", "Valor 12m ($, costo del período)", "Sugerido ($)", "Costo actual unitario ($)"):
            j = list(vista.columns).index(col); ws.set_column(j, j, 16, n0)
        for col in ("Demanda semanal D", "Desv. semanal σ", "Plazo L (días)", "Plazo L (semanas)", "Stock de seguridad SS",
                    "Nivel objetivo S", "Posición de inventario", "Necesidad bruta", "z", "Plazo del motor (días, solo comparar)"):
            j = list(vista.columns).index(col); ws.set_column(j, j, 14, n2)
        ws.set_row(0, 48)
        ws.freeze_panes(1, 2)
        ws.autofilter(0, 0, len(vista), len(vista.columns) - 1)
        j = list(vista.columns).index("SUGERIDO (unidades)")
        ws.conditional_format(1, j, len(vista), j, {"type": "cell", "criteria": ">", "value": 0, "format": ok_f})

        # ---- Resumen por cluster
        filas = []
        for r in resumen:
            f = pol.fila(r.cluster)
            filas.append({
                "Cluster": r.cluster, "Frecuencia": r.cluster[0], "Piezas": r.cluster[1], "Valor": r.cluster[2],
                "Productos": r.n_productos, "Unidades 12m": float(r.unidades), "% unidades": float(r.pct_unidades),
                "Valor 12m ($)": float(r.valor), "% valor": float(r.pct_valor),
                "Modo": f.modo, "Nivel de servicio": f.nivel_servicio, "z": f.z, "Mínimo fijo": f.minimo_fijo,
                "Productos que piden": int(pagos.piden.get(r.cluster, 0)),
                "Unidades sugeridas": float(pagos.unidades_sug.get(r.cluster, 0)),
                "Sugerido ($)": float(r.sugerido_pesos or 0),
            })
        rc = pd.DataFrame(filas)
        tot = {"Cluster": "TOTAL", "Productos": rc["Productos"].sum(), "Unidades 12m": rc["Unidades 12m"].sum(),
               "% unidades": rc["% unidades"].sum(), "Valor 12m ($)": rc["Valor 12m ($)"].sum(),
               "% valor": rc["% valor"].sum(), "Productos que piden": rc["Productos que piden"].sum(),
               "Unidades sugeridas": rc["Unidades sugeridas"].sum(), "Sugerido ($)": rc["Sugerido ($)"].sum()}
        rc = pd.concat([rc, pd.DataFrame([tot])], ignore_index=True)
        rc.to_excel(xw, sheet_name="Resumen por cluster", index=False, startrow=1, header=False)
        ws = xw.sheets["Resumen por cluster"]
        for j, col in enumerate(rc.columns):
            ws.write(0, j, col, h); ws.set_column(j, j, 15)
        for col in ("% unidades", "% valor", "Nivel de servicio"):
            j = list(rc.columns).index(col); ws.set_column(j, j, 13, pct)
        for col in ("Unidades 12m", "Valor 12m ($)", "Unidades sugeridas", "Sugerido ($)"):
            j = list(rc.columns).index(col); ws.set_column(j, j, 16, n0)
        ws.set_row(0, 32); ws.freeze_panes(1, 1)
        n = len(rc)
        ws.write(n + 2, 0, "Los % son sobre los productos CLASIFICADOS (no incluyen NUEVO ni SIN MOVIMIENTO). "
                 "El cluster es Frecuencia-Piezas-Valor. Los 27 siempre aparecen, tengan o no productos.", wrap)

        # ---- Politica
        pdf = pd.DataFrame([{
            "Bodega": f.bodega, "Cluster": f.cluster, "Frecuencia": f.frecuencia, "Piezas": f.piezas, "Valor": f.valor,
            "Modo": f.modo, "Nivel de servicio": f.nivel_servicio, "z": f.z, "Mínimo fijo": f.minimo_fijo,
            "Estado": "PROVISORIA (valores del brief, por confirmar)",
        } for f in pol.filas])
        pdf.to_excel(xw, sheet_name="Política", index=False, startrow=1, header=False)
        ws = xw.sheets["Política"]
        for j, col in enumerate(pdf.columns):
            ws.write(0, j, col, h); ws.set_column(j, j, 16 if col != "Estado" else 44)
        j = list(pdf.columns).index("Nivel de servicio"); ws.set_column(j, j, 16, pct)
        ws.freeze_panes(1, 2)
        ws.write(len(pdf) + 2, 0,
                 "Modos: formula = S = D x (L + R) + z x σ x raíz(L + R); contra_pedido = no se repone (sugerido 0); "
                 "minimo_fijo = si la posición es 0 o menos se pide el mínimo fijo. R = 1 semana. Cambiar un valor aquí "
                 "no recalcula este Excel: hay que volver a generarlo.", wrap)

        # ---- Paso a paso
        ws = wb.add_worksheet("Paso a paso"); xw.sheets["Paso a paso"] = ws
        ws.set_column(0, 0, 120)
        fila_x = 0
        elegidos = elegir_pasos(d)
        ws.write(fila_x, 0, "Paso a paso de 3 productos, con los números reales. Cada uno muestra cómo sale su "
                 "cluster y su sugerido.", negr); fila_x += 2
        for etiqueta, p in elegidos:
            r, fila_pol, _ = d["reps"][p]
            pasos = explicar_producto(res, p, r, fila_pol, etiquetas_meses=ETIQUETAS_MES)
            ws.write(fila_x, 0, f"{etiqueta}: {p}", h); fila_x += 1
            ws.write(fila_x, 0, texto_completo(pasos), wrap)
            ws.set_row(fila_x, 15 * (texto_completo(pasos).count("\n") + 3))
            fila_x += 2

        # ---- Validaciones
        filas = [(v.nombre, "OK" if v.ok else "FALLA", v.detalle) for v in validaciones]
        filas += [(n, "OK" if ok else "FALLA", det) for n, ok, det in extra]
        vd = pd.DataFrame(filas, columns=["Validación", "Resultado", "Detalle"])
        vd.to_excel(xw, sheet_name="Validaciones", index=False, startrow=1, header=False)
        ws = xw.sheets["Validaciones"]
        for j, col in enumerate(vd.columns):
            ws.write(0, j, col, h)
        ws.set_column(0, 0, 60); ws.set_column(1, 1, 12); ws.set_column(2, 2, 120, wrap)
        ws.conditional_format(1, 1, len(vd), 1, {"type": "cell", "criteria": "==", "value": '"OK"', "format": ok_f})
        ws.conditional_format(1, 1, len(vd), 1, {"type": "cell", "criteria": "==", "value": '"FALLA"', "format": mal_f})

        # ---- Sin movimiento con stock (decision 11)
        c5 = d["c5"]
        sm = c5[~c5.en_universo].copy()
        vendidos = set(d["c1"].padre)
        sm = sm[(sm.stock_BODEGA_ML > 0) | (sm.stock_BODEGA_ML_FULL > 0)]
        sm_df = pd.DataFrame({
            "Producto (padre)": sm.padre, "Descripción": sm.descripcion,
            "Stock BODEGA ML": sm.stock_BODEGA_ML, "Stock ML-FULL": sm.stock_BODEGA_ML_FULL,
            "Stock CD (informativo)": sm.stock_CD_REPUESTOS,
            "Valor stock ML ($)": sm.valor_stock_ML, "Caso": sm.caso,
        }).sort_values("Valor stock ML ($)", ascending=False)
        sm_df.to_excel(xw, sheet_name="Sin movimiento con stock", index=False, startrow=1, header=False)
        ws = xw.sheets["Sin movimiento con stock"]
        for j, col in enumerate(sm_df.columns):
            ws.write(0, j, col, h); ws.set_column(j, j, 18 if j != 1 else 40)
        ws.set_column(5, 5, 18, n0); ws.freeze_panes(1, 1)
        ws.autofilter(0, 0, len(sm_df), len(sm_df.columns) - 1)
        ws.write(len(sm_df) + 2, 0, "Productos con stock en ML o ML-FULL y sin venta digital en 12 meses: quedan fuera de los "
                 "clusters y sin sugerido de compra. No se distingue aquí cuáles vendieron por otro canal (pendiente).", wrap)

        # ---- Excepciones
        ex = d["excep"][["fecha", "tipo_docto", "numero", "local", "tipo_venta", "producto_norm", "unid_neta"]].copy()
        ex["motivo"] = ex.apply(
            lambda r: "producto sin costo ni ficha (CUP000492)" if r.producto_norm in EXCLUIR_PRODUCTOS
            else "no es una venta (salida de accesorios)", axis=1)
        ex.to_excel(xw, sheet_name="Excepciones", index=False, startrow=1, header=False)
        ws = xw.sheets["Excepciones"]
        for j, col in enumerate(ex.columns):
            ws.write(0, j, col, h); ws.set_column(j, j, 20)
        ws.write(len(ex) + 2, 0, "Líneas excluidas del universo. Pendiente: una factura a un cliente del propio grupo (11 u "
                 "en total junto con la de accesorios) que aún no está identificada en la lista.", wrap)
    return validaciones, extra


def leeme_lineas(d, vista):
    res = d["res"]
    est = Counter(vista["Estado"])
    pide = int((vista["SUGERIDO (unidades)"] > 0).sum())
    L = [
        ("CANAL DIGITAL - BODEGA 430 - PRIMERA VERSIÓN PROVISORIA", "t"),
        (f"Generado el {dt.date.today().strftime('%d-%m-%Y')}. Ventas oct-2025 a sep-2026 (el archivo termina el 30-09; "
         f"octubre no está). Stock del {FECHA_STOCK}. Todo está calculado en solo lectura: no se cambió nada en la plataforma.", "n"),
        ("", "n"),
        ("QUÉ HAY EN CADA HOJA", "t"),
        ("Vista principal: una fila por producto (padre), con su cluster, la demanda, el plazo, el stock, la posición y el "
         "SUGERIDO. Es el detalle de todo lo demás.", "n"),
        ("Resumen por cluster: los 27 clusters con sus productos, unidades, valor, política y lo que sugieren.", "n"),
        ("Política: las 27 filas de política (modo, nivel de servicio, z). Son los valores del brief, PROVISORIOS.", "n"),
        ("Paso a paso: 3 productos explicados con los números reales.", "n"),
        ("Validaciones: las pruebas que cuadran los números. Si alguna dice FALLA, no confiar en el libro.", "n"),
        ("Sin movimiento con stock: productos con stock en ML o ML-FULL y sin venta digital (fuera de los clusters).", "n"),
        ("Excepciones: líneas de venta que se sacaron del universo y por qué.", "n"),
        ("", "n"),
        ("CIFRAS", "t"),
        (f"Productos (padres) en el universo: {len(vista)}. CLASIFICADOS {est.get(ESTADO_CLASIFICADO, 0)}, "
         f"NUEVO {est.get(ESTADO_NUEVO, 0)} (es un máximo: las ventas cargadas parten en enero 2024), "
         f"SIN MOVIMIENTO {est.get(ESTADO_SIN_MOVIMIENTO, 0)}.", "n"),
        (f"Productos que hoy piden reposición: {pide}. Unidades sugeridas: {vista['SUGERIDO (unidades)'].sum():,.0f}. "
         f"Valor al costo actual: $ {vista['Sugerido ($)'].sum():,.0f}.", "n"),
        ("", "n"),
        ("PROVISORIO - ESTO NO ESTÁ CONFIRMADO (marcado para tu OK)", "t"),
        ("1) La política de los 27 clusters (modo, nivel de servicio, z, mínimo fijo) son los valores del brief.", "p"),
        ("2) Semana: bloques de 7 días terminados el 30-09-2026 (52 semanas). El 1-oct-2025 queda fuera de la serie semanal "
         "(sí cuenta en la clasificación mensual). Si prefieres semana calendario lunes-domingo, se cambia.", "p"),
        ("3) El comprometido NO existe en el ERP: se muestra \"0 (sin dato)\". Mínimo de compra y múltiplo no existen en "
         "ninguna fuente: se usa 1 y 1 por defecto, con aviso en la columna Avisos. El sugerido puede salir alto o bajo "
         "para productos con pedido mínimo real.", "p"),
        ("4) Tránsito: solo OC con destino 430 (hoy es 0). Las otras columnas son informativas y no suman. Los traslados "
         "desde el CD no figuran en ningún reporte, así que la posición es solo stock.", "p"),
        ("5) ML-FULL va aparte y no suma al disponible de la 430. Si la venta se despacha desde ahí, el sugerido de los "
         "49 productos más vendidos sale inflado. Hay que confirmarlo con quien opera Mercado Libre.", "p"),
        ("6) Plazo L = promedio de las últimas 5 recepciones del proveedor, ignorando las de 30 días o más, más 1 día de "
         "gestión; respaldo de 3 días. Confianza baja en los productos sin proveedor o con menos de 5 recepciones "
         "(columna Confianza del plazo).", "p"),
        ("7) Valor: costo del período para la letra de Valor; costo actual del padre para valorizar el sugerido. "
         "Los 62 productos agotados quedan rotulados \"sin respaldo de stock\".", "p"),
        ("8) Devoluciones: restan en el mes de la nota para la clasificación y en la semana de la venta original para "
         "la demanda semanal.", "p"),
        ("9) Liquidaciones (LIQ FACT) cuentan como venta: pesan 19,6 % de las unidades. Sin ellas, 23 productos cambian de letra.", "p"),
        ("10) El mapa de padres es una réplica de las funciones del motor, no una corrida de producción de hoy.", "p"),
        ("11) \"Primera venta en la empresa: 2024-01-01\" solo significa \"en enero de 2024 o antes\": las ventas cargadas parten ahí. "
         "Por eso NUEVO es un máximo y no se puede ver más atrás.", "p"),
        ("", "n"),
        ("QUÉ FALTA (no está en esta versión)", "t"),
        ("Pantallas web y tablas de la plataforma; comprometido, mínimos y múltiplos reales; traslados desde el CD; "
         "ventas de octubre en adelante; confirmar la política con Abastecimiento.", "n"),
    ]
    return L


def elegir_pasos(d):
    reps, res = d["reps"], d["res"]
    clasif = [p for p in res.productos if p.estado == ESTADO_CLASIFICADO]
    clasif.sort(key=lambda p: -p.unidades_ventana)
    out = []
    pide = [p for p in clasif if reps[p.codigo][0].modo == MODO_FORMULA and reps[p.codigo][0].sugerido > 0]
    if pide:
        out.append(("Caso 1: producto de alta rotación que pide", pide[0].codigo))
    otro = [p for p in clasif if reps[p.codigo][0].modo != MODO_FORMULA]
    if otro:
        out.append(("Caso 2: producto que no sigue la fórmula", otro[len(otro) // 2].codigo))
    cubierto = [p for p in clasif if reps[p.codigo][0].modo == MODO_FORMULA and reps[p.codigo][0].sugerido == 0]
    if cubierto:
        out.append(("Caso 3: producto cubierto (no pide)", cubierto[len(cubierto) // 3].codigo))
    for p in res.productos:
        if len(out) >= 3:
            break
        if p.estado != ESTADO_CLASIFICADO and p.codigo not in [x[1] for x in out]:
            out.append((f"Producto {p.estado}", p.codigo))
    return out[:3]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--datos", required=True)
    ap.add_argument("--salida", required=True)
    a = ap.parse_args()
    d = construir(pathlib.Path(a.datos))
    validaciones, extra = hojas(d, pathlib.Path(a.salida))
    for v in validaciones:
        print(("OK   " if v.ok else "FALLA"), v.nombre, "-", v.detalle)
    for n, ok, det in extra:
        print(("OK   " if ok else "FALLA"), n, "-", det)
    print("Escrito:", a.salida)


if __name__ == "__main__":
    main()
