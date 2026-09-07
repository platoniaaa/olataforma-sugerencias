# -*- coding: utf-8 -*-
"""Semillas del modulo de precios, desde el maestro limpio. Solo lectura del xlsx."""
import zipfile, re, html, codecs, csv, datetime
M="salida2025.xlsx"; E0=datetime.date(1899,12,30)
RE_ROW=re.compile(r'<row [^>]*?r="(\d+)"[^>]*?>.*?</row>',re.S)
RE_CELL=re.compile(r'<c ([^>]*?)(?:/>|>(.*?)</c>)',re.S)
Z=zipfile.ZipFile(M)
sx=Z.read("xl/sharedStrings.xml").decode("utf-8","ignore")
sst=[html.unescape("".join(re.findall(r"<t[^>]*>(.*?)</t>",s,re.S))) for s in re.findall(r"<si>(.*?)</si>",sx,re.S)]
def val(b,a):
    if b is None: return ""
    t=re.search(r"<is>.*?<t[^>]*>(.*?)</t>",b,re.S)
    if t: return html.unescape(t.group(1))
    v=re.search(r"<v>(.*?)</v>",b,re.S)
    if not v: return ""
    if 't="s"' in a:
        i=int(v.group(1)); return sst[i] if i<len(sst) else ""
    return html.unescape(v.group(1))
def num(s):
    s=(s or "").strip().replace(",",".")
    try: return float(s)
    except ValueError: return None
def fecha(s):
    d=num(s)
    return (E0+datetime.timedelta(days=int(d))).isoformat() if d and 20000<d<60000 else ""
rels=Z.read("xl/_rels/workbook.xml.rels").decode("utf-8")
mp={m.group(1):m.group(2) for m in re.finditer(r'Id="(rId\d+)"[^>]*Target="([^"]+)"',rels)}
wb=Z.read("xl/workbook.xml").decode("utf-8","ignore")
def hoja(n):
    r=re.search(r'<sheet name="%s"[^>]*r:id="(rId\d+)"'%re.escape(n),wb)
    return "xl/"+mp[r.group(1)].lstrip("/") if r else None
def filas(nombre):
    SH=hoja(nombre); dec=codecs.getincrementaldecoder("utf-8")(); resto=""
    with Z.open(SH) as fh:
        while True:
            ch=fh.read(24<<20); t=resto+dec.decode(ch,not ch); fin=0
            for mr in RE_ROW.finditer(t):
                fin=mr.end(); c={}
                for mc in RE_CELL.finditer(mr.group(0)):
                    ra=re.search(r'r="([A-Z]+)\d+"',mc.group(1))
                    if ra: c[ra.group(1)]=(val(mc.group(2),mc.group(1)), "<f" in (mc.group(2) or ""))
                yield int(mr.group(1)), c
            resto=t[fin:] if fin else t
            if not ch: break
def csvw(nombre, cab, filas_):
    with open(f"seed/{nombre}.csv","w",newline="",encoding="utf-8") as fh:
        w=csv.writer(fh, delimiter=";"); w.writerow(cab); n=0
        for f in filas_: w.writerow(f); n+=1
    print(f"{nombre:<20} {n:>7,} filas")
# --- lista principal
def lista():
    for nf,c in filas("Lista sin duplicados"):
        if nf==1: continue
        g=lambda k:(c.get(k,("",False))[0] or "").strip()
        p=g("B")
        if not p: continue
        # 'manual' = la celda tiene valor y no formula (lo escribio una persona)
        tipo_manual = bool(g("AN")) and not c.get("AN",("",False))[1]
        proc_manual = bool(g("AR")) and not c.get("AR",("",False))[1]
        yield [p,g("C"),g("AM"),g("AN"),int(tipo_manual),g("T"),g("AR"),int(proc_manual),
               num(g("X")) or 0, num(g("G")) or 0, num(g("E")) or 0, num(g("F")) or 0,
               g("AT"), num(g("AU")) or "", 1 if g("AZ") else 0, g("AY"),
               fecha(g("BA")), fecha(g("AO")), fecha(g("AP")), num(g("AV")) if g("AV") else ""]
csvw("lista",["producto","glosa","rubro","tipo","tipo_manual","procedencia_maestro","procedencia_final","proc_manual",
              "costo","precio_erp","stock","stock_proyectado","obs_precio","precio_fijo","congelar","estado",
              "ultima_venta","ult_recep_importado","ult_pe_nacional","precio_optimo_excel"], lista())
# --- hojas de configuracion, tal cual
def simple(nombre, cols, saltar=1):
    for nf,c in filas(nombre):
        if nf<=saltar: continue
        f=[(c.get(k,("",False))[0] or "").strip() for k in cols]
        if any(f): yield f
csvw("politica",["tipo","procedencia","factor","clave","descuento_max","margen_post"], simple("Politica",["A","B","C","D","E","F"]))
csvw("rubros",["rubro","tipo","procedencia_forzada"], simple("Rubros",["A","B","C"]))
csvw("no_productos",["producto","motivo"], simple("No_Productos",["A","B"]))
csvw("precios_sugeridos",["producto","precio_sin_iva","precio_con_iva","proveedor"], simple("Precios_Sugeridos",["A","B","C","D"]))
csvw("parametros",["clave","valor"], simple("Parametros",["A","B"],0))
csvw("tipos_producto",["tipo","descripcion"], simple("Tipos_Producto",["A","B"]))
Z.close()
print("\nmuestra politica:"); print(open("seed/politica.csv",encoding="utf-8").read()[:600])
print("\nmuestra parametros:"); print(open("seed/parametros.csv",encoding="utf-8").read()[:400])
print("\nmuestra precios_sugeridos:"); print("".join(open("seed/precios_sugeridos.csv",encoding="utf-8").readlines()[:4]))
