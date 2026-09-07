# -*- coding: utf-8 -*-
"""Borra filas del maestro conservando TODO lo demas byte a byte.

  - solo toca la hoja 'Lista sin duplicados'
  - renumera las filas que quedan y corrige las referencias de fila de las formulas
  - expande las compartidas a formulas normales (renumerar rompe los bloques si=);
    la maestra de cada bloque se registra aunque su fila se borre
  - saca calcChain.xml (queda desfasado; Excel lo regenera) y su Override
  - quita <dimension> del encabezado: Excel la recalcula
  - el resto del zip se copia tal cual
"""
import zipfile, re, json, sys, os, codecs

SRC, OUT = sys.argv[1], sys.argv[2]
HOJA = "Lista sin duplicados"

borrar = set(json.load(open(sys.argv[3])))
print(f"filas a borrar: {len(borrar):,}")

RE_ROW  = re.compile(r'<row [^>]*?r="(\d+)"[^>]*?>.*?</row>|<row [^>]*?r="(\d+)"[^>]*?/>', re.S)
RE_CELL = re.compile(r'<c ([^>]*?)(?:/>|>(.*?)</c>)', re.S)
RE_REF  = re.compile(r'(\$?[A-Z]{1,3})(\d+)')
RE_STR  = re.compile(r'"[^"]*"')

def trad(f, viejo, nuevo):
    """Referencias de fila RELATIVAS viejo->nuevo. No toca lo absoluto ni las comillas."""
    if not f or viejo == nuevo:
        return f
    out, pos = [], 0
    for m in RE_STR.finditer(f):
        out.append(RE_REF.sub(lambda x: (x.group(1)+str(nuevo)) if int(x.group(2)) == viejo else x.group(0), f[pos:m.start()]))
        out.append(m.group(0)); pos = m.end()
    out.append(RE_REF.sub(lambda x: (x.group(1)+str(nuevo)) if int(x.group(2)) == viejo else x.group(0), f[pos:]))
    return "".join(out)

zin  = zipfile.ZipFile(SRC)
rels = zin.read("xl/_rels/workbook.xml.rels").decode("utf-8")
mp   = {m.group(1): m.group(2) for m in re.finditer(r'Id="(rId\d+)"[^>]*Target="([^"]+)"', rels)}
wb   = zin.read("xl/workbook.xml").decode("utf-8", "ignore")
rid  = re.search(r'<sheet name="%s"[^>]*r:id="(rId\d+)"' % re.escape(HOJA), wb).group(1)
SH   = "xl/" + mp[rid].lstrip("/")
print("hoja objetivo:", SH)

maestras = {}
n_leidas = n_esc = n_borr = 0
n_huerfanas = 0
COMP = re.compile(r'<f([^>]*?)(?:/>|>(.*?)</f>)', re.S)

zout = zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=6)
wb_pend = None
for zi in zin.infolist():
    if zi.filename == "xl/workbook.xml":
        wb_pend = (zi, zin.read(zi).decode("utf-8")); continue
    if zi.filename == "xl/calcChain.xml":
        print("  - calcChain.xml eliminado"); continue
    if zi.filename == "[Content_Types].xml":
        d = zin.read(zi).decode("utf-8")
        d = re.sub(r'<Override PartName="/xl/calcChain\.xml"[^>]*?/>', "", d)
        zout.writestr(zi, d.encode("utf-8")); continue
    if zi.filename != SH:
        zout.writestr(zi, zin.read(zi)); continue

    with zin.open(zi) as fh, zout.open(zi, "w") as fo:
        dec = codecs.getincrementaldecoder("utf-8")(); resto = ""; cab = True
        while True:
            ch = fh.read(24 << 20)
            t = resto + dec.decode(ch, not ch)
            if cab:
                i = t.find("<sheetData>")
                if i < 0:
                    resto = t
                    if not ch: break
                    continue
                enc = re.sub(r'<dimension ref="[^"]*"\s*/>', "", t[:i + 11])
                fo.write(enc.encode("utf-8")); t = t[i + 11:]; cab = False
            fin = 0; buf = []
            for mr in RE_ROW.finditer(t):
                fin = mr.end()
                nf = int(mr.group(1) or mr.group(2))
                n_leidas += 1
                fila = mr.group(0)
                quitar = nf in borrar
                # registrar maestras de bloques compartidos SIEMPRE, aunque la fila se borre
                for mc in RE_CELL.finditer(fila):
                    body = mc.group(2)
                    if not body or "t=\"shared\"" not in body: continue
                    mf = COMP.search(body)
                    if mf and mf.group(2):
                        msi = re.search(r'si="(\d+)"', mf.group(1))
                        mr2 = re.search(r'r="[A-Z]+(\d+)"', mc.group(1))
                        if msi and mr2: maestras[msi.group(1)] = (mf.group(2), int(mr2.group(1)))
                if quitar:
                    n_borr += 1; continue
                n_esc += 1
                nuevo = n_esc
                def _cel(mc):
                    global n_huerfanas
                    attrs, body = mc.group(1), mc.group(2)
                    ref = re.search(r'r="([A-Z]+)(\d+)"', attrs)
                    if not ref: return mc.group(0)
                    col, fv = ref.group(1), int(ref.group(2))
                    attrs = attrs.replace(f'r="{col}{fv}"', f'r="{col}{nuevo}"', 1)
                    if body is None: return f"<c {attrs}/>"
                    mf = COMP.search(body)
                    if mf:
                        fattr, ftxt = mf.group(1), mf.group(2)
                        if 't="shared"' in fattr:
                            msi = re.search(r'si="(\d+)"', fattr)
                            si = msi.group(1) if msi else None
                            if ftxt:
                                nf_ = trad(ftxt, fv, nuevo)
                            else:
                                base, bf = maestras.get(si, (None, None))
                                if base is None:
                                    n_huerfanas += 1
                                    return f"<c {attrs}>{body}</c>"
                                nf_ = trad(base, bf, nuevo)
                            body = body[:mf.start()] + f"<f>{nf_}</f>" + body[mf.end():]
                        elif ftxt:
                            body = body[:mf.start()] + f"<f{fattr}>{trad(ftxt, fv, nuevo)}</f>" + body[mf.end():]
                    return f"<c {attrs}>{body}</c>"
                fila = re.sub(r'r="\d+"', f'r="{nuevo}"', fila, count=1)
                buf.append(RE_CELL.sub(_cel, fila))
            if buf: fo.write("".join(buf).encode("utf-8"))
            resto = t[fin:] if fin else t
            if not ch:
                j = resto.find("</sheetData>")
                cola = resto[j:] if j >= 0 else "</sheetData></worksheet>"
                cola = re.sub(r'(<autoFilter ref="A1:[A-Z]+)\d+(")', lambda m: m.group(1)+str(n_esc)+m.group(2), cola)
                fo.write(cola.encode("utf-8"))
                break
if wb_pend:
    zi_wb, d = wb_pend
    d = re.sub(r"(\$A\$1:\$[A-Z]+\$)\d+", lambda m: m.group(1)+str(n_esc), d)
    zout.writestr(zi_wb, d.encode("utf-8"))
zout.close(); zin.close()
print(f"\nfilas leidas  : {n_leidas:,}")
print(f"filas borradas: {n_borr:,}")
print(f"filas escritas: {n_esc:,}")
print(f"formulas compartidas huerfanas: {n_huerfanas:,}  (debe ser 0)")
print(f"bloques compartidos registrados: {len(maestras):,}")
print(f"salida: {OUT}  ({os.path.getsize(OUT)/1024/1024:.1f} MB)")
