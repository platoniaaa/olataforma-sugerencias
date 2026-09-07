# -*- coding: utf-8 -*-
"""Los que se van: stock 0 + ultima venta anterior al 01-01-2025, menos los vivos.
   Se calcula sobre el maestro ACTUAL (ya recortado). Solo lectura del xlsx."""
import zipfile, re, html, codecs, json, datetime
from collections import Counter
from openpyxl import Workbook
M = "base2025.xlsx"; E0 = datetime.date(1899, 12, 30)
C2025 = (datetime.date(2025, 1, 1) - E0).days
C2024 = (datetime.date(2024, 1, 1) - E0).days
uv = json.load(open("ult_venta2.json")); LAX = uv["lax"]
RX = re.compile(r"^(\d{1,3})\s+")
def lax(s):
    s = (s or "").strip().upper()
    return re.sub(r"[^A-Z0-9]", "", RX.sub("", s))
def num(s):
    s = (s or "").strip().replace(",", ".")
    try: return float(s)
    except ValueError: return None
RE_ROW = re.compile(r'<row [^>]*?r="(\d+)"[^>]*?>.*?</row>', re.S)
RE_CELL = re.compile(r'<c ([^>]*?)(?:/>|>(.*?)</c>)', re.S)
Z = zipfile.ZipFile(M)
sx = Z.read("xl/sharedStrings.xml").decode("utf-8", "ignore")
sst = [html.unescape("".join(re.findall(r"<t[^>]*>(.*?)</t>", s, re.S))) for s in re.findall(r"<si>(.*?)</si>", sx, re.S)]
def val(b, a):
    if b is None: return ""
    t = re.search(r"<is>.*?<t[^>]*>(.*?)</t>", b, re.S)
    if t: return html.unescape(t.group(1))
    v = re.search(r"<v>(.*?)</v>", b, re.S)
    if not v: return ""
    if 't="s"' in a:
        i = int(v.group(1)); return sst[i] if i < len(sst) else ""
    return html.unescape(v.group(1))
rels = Z.read("xl/_rels/workbook.xml.rels").decode("utf-8")
mp = {m.group(1): m.group(2) for m in re.finditer(r'Id="(rId\d+)"[^>]*Target="([^"]+)"', rels)}
wb = Z.read("xl/workbook.xml").decode("utf-8", "ignore")
rid = re.search(r'<sheet name="Lista sin duplicados"[^>]*r:id="(rId\d+)"', wb).group(1)
d = Z.read("xl/" + mp[rid].lstrip("/")).decode("utf-8", "ignore")
Z.close()

tot = 0; r = Counter(); borrar = []; audit = []; anio = Counter()
for mr in RE_ROW.finditer(d):
    nf = int(mr.group(1))
    if nf == 1: continue
    c = {}
    for mc in RE_CELL.finditer(mr.group(0)):
        ra = re.search(r'r="([A-Z]+)\d+"', mc.group(1))
        if ra and ra.group(1) in ("B","C","E","F","G","X","AM","AN","AO","AP","AT","AU","AZ","BA"):
            c[ra.group(1)] = val(mc.group(2), mc.group(1))
    p = (c.get("B") or "").strip()
    if not p: continue
    tot += 1
    if (num(c.get("E","")) or 0) > 0: r["tiene stock"] += 1; continue
    d_ = num(c.get("BA",""))
    if d_ is None: r["sin venta registrada (ya no deberia haber)"] += 1; continue
    d_ = int(d_)
    if d_ >= C2025: r["vendio en 2025 o 2026"] += 1; continue
    # mismas excepciones que la vez pasada
    if LAX.get(lax(p), 0) >= C2025: r["vendio bajo otro rubro (se queda)"] += 1; continue
    if (num(c.get("F","")) or 0) > 0: r["en transito (se queda)"] += 1; continue
    cp = max([x for x in (num(c.get("AO","")), num(c.get("AP",""))) if x and 20000 < x < 60000] or [0])
    if cp >= C2024: r["comprado 2024+ (se queda)"] += 1; continue
    if (c.get("AZ") or "").strip() or (c.get("AT") or "").strip() or num(c.get("AU","")):
        r["con Congelar/Precio Fijo (se queda)"] += 1; continue
    r["SE BORRA"] += 1; borrar.append(nf)
    anio[(E0 + datetime.timedelta(days=d_)).year] += 1
    audit.append([p, c.get("C",""), c.get("AM",""), c.get("AN",""),
                  num(c.get("X","")) or 0, num(c.get("G","")) or 0,
                  (E0 + datetime.timedelta(days=d_))])
print(f"productos en el maestro: {tot:,}\n")
for k, v in r.most_common(): print(f"   {k:<42}{v:>8,}")
print(f"\nquedan: {tot - len(borrar):,}")
print("\npor anio de ultima venta:")
for a in sorted(anio): print(f"   {a}: {anio[a]:>6,}")
json.dump(borrar, open("rows_2025.json", "w"))
w = Workbook(write_only=True); s = w.create_sheet("Borrados sin venta desde 2025")
s.append(["Producto","Glosa","Rubro","Tipo","Costo","Precio venta ERP","Ultima venta"])
for a in audit: s.append(a)
w.save("BORRADOS sin venta desde 2025.xlsx")
print(f"\nguardado rows_2025.json ({len(borrar):,}) y BORRADOS sin venta desde 2025.xlsx")
