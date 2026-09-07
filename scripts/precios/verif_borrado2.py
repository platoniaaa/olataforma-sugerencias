# -*- coding: utf-8 -*-
"""Verifica el borrado: nada se movio salvo las filas que debian irse."""
import zipfile, re, html, codecs, json, hashlib
A, B = "base_borrado.xlsx", "salida_borrado.xlsx"
HOJA = "Lista sin duplicados"
RE_ROW  = re.compile(r'<row [^>]*?r="(\d+)"[^>]*?>.*?</row>|<row [^>]*?r="(\d+)"[^>]*?/>', re.S)
RE_CELL = re.compile(r'<c ([^>]*?)(?:/>|>(.*?)</c>)', re.S)

def abrir(P):
    Z = zipfile.ZipFile(P)
    sx = Z.read("xl/sharedStrings.xml").decode("utf-8","ignore")
    sst = [html.unescape("".join(re.findall(r"<t[^>]*>(.*?)</t>", s, re.S)))
           for s in re.findall(r"<si>(.*?)</si>", sx, re.S)]
    rels = Z.read("xl/_rels/workbook.xml.rels").decode("utf-8")
    mp = {m.group(1):m.group(2) for m in re.finditer(r'Id="(rId\d+)"[^>]*Target="([^"]+)"', rels)}
    wb = Z.read("xl/workbook.xml").decode("utf-8","ignore")
    rid = re.search(r'<sheet name="%s"[^>]*r:id="(rId\d+)"'%re.escape(HOJA), wb).group(1)
    return Z, sst, "xl/"+mp[rid].lstrip("/")

def val(body, attrs, sst):
    if body is None: return ""
    t = re.search(r"<is>.*?<t[^>]*>(.*?)</t>", body, re.S)
    if t: return html.unescape(t.group(1))
    v = re.search(r"<v>(.*?)</v>", body, re.S)
    if not v: return ""
    if 't="s"' in attrs:
        i = int(v.group(1)); return sst[i] if i < len(sst) else ""
    return html.unescape(v.group(1))

def leer(P, saltar=None):
    """Devuelve (lista de codigos, hash por columna de los VALORES, formulas de muestra)."""
    Z, sst, SH = abrir(P)
    cods = []; h = {}; muestra = {}
    dec = codecs.getincrementaldecoder("utf-8")(); resto=""
    with Z.open(SH) as fh:
        while True:
            ch = fh.read(24<<20)
            t = resto + dec.decode(ch, not ch); fin=0
            for mr in RE_ROW.finditer(t):
                fin = mr.end()
                nf = int(mr.group(1) or mr.group(2))
                if nf == 1: continue
                if saltar and nf in saltar: continue
                cel = {}
                for mc in RE_CELL.finditer(mr.group(0)):
                    ra = re.search(r'r="([A-Z]+)\d+"', mc.group(1))
                    if not ra: continue
                    cel[ra.group(1)] = (val(mc.group(2), mc.group(1), sst), mc.group(2) or "")
                cod = cel.get("B",("",""))[0].strip()
                if not cod: continue
                cods.append(cod)
                for c,(v,_) in cel.items():
                    if c not in h: h[c] = hashlib.md5()
                    h[c].update(("%s\x1f%s\x1e" % (c, v)).encode("utf-8"))
                if len(muestra) < 3 and cod:
                    f = cel.get("AV",("",""))[1]
                    mf = re.search(r'<f[^>]*>(.*?)</f>', f, re.S)
                    if mf: muestra[cod] = (nf, mf.group(1)[:110])
            resto = t[fin:] if fin else t
            if not ch: break
    Z.close()
    return cods, {k:v.hexdigest() for k,v in h.items()}, muestra

borrar = set(json.load(open("sinventa_rows.json")))
print("leyendo original (saltando las que deben irse)...")
ca, ha, ma = leer(A, saltar=borrar)
print("leyendo resultado...")
cb, hb, mb = leer(B)
print(f"\ncodigos esperados : {len(ca):,}")
print(f"codigos obtenidos : {len(cb):,}")
print(f"lista identica y en el mismo orden: {ca == cb}")
if ca != cb:
    sa, sb = set(ca), set(cb)
    print("  faltan de mas :", list(sa-sb)[:10])
    print("  sobran        :", list(sb-sa)[:10])
print(f"\nhash por columna (valores) sobre las filas que quedan:")
cols = sorted(set(ha)|set(hb), key=lambda c:(len(c),c))
malas = [c for c in cols if ha.get(c) != hb.get(c)]
for c in cols:
    ok = "IGUAL" if ha.get(c)==hb.get(c) else "*** DISTINTO ***"
    if ha.get(c)!=hb.get(c) or c in ("B","E","G","X","AM","AN","AR","AS","AV","AZ"):
        print(f"   {c:<4} {ok}")
print(f"\ncolumnas con diferencia: {len(malas)}  {malas}")
print("\nformula AV, antes y despues (misma fila logica):")
for k in list(ma)[:3]:
    print(f"   {k}\n      antes  (fila {ma[k][0]}): {ma[k][1]}")
    if k in mb: print(f"      despues(fila {mb[k][0]}): {mb[k][1]}")
# resto del zip
Za, Zb = zipfile.ZipFile(A), zipfile.ZipFile(B)
_,_,SH = abrir(A)
na = {i.filename for i in Za.infolist()}; nb = {i.filename for i in Zb.infolist()}
print(f"\npartes solo en el original: {sorted(na-nb)}")
print(f"partes solo en el nuevo   : {sorted(nb-na)}")
dif = [n for n in sorted(na&nb) if n not in (SH,"[Content_Types].xml") and Za.read(n)!=Zb.read(n)]
print(f"otras partes del zip que cambiaron: {dif if dif else 'ninguna'}")
Za.close(); Zb.close()
