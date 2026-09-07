# -*- coding: utf-8 -*-
"""Saca de la plataforma los productos que ya no estan en el maestro.

No se fia de una lista guardada: compara lo que hay en produccion contra los
codigos del Excel actual (seed/lista.csv) y borra la diferencia. Asi el
resultado es el mismo aunque el Excel se haya recortado en varias pasadas.
"""
import csv, json, sys
from push_precios import Api, env_de

LOTE = 500

e = env_de(r"C:\Users\icalderon\dev\Sugerencia-SaaS-para-sucursales\.env")
api = Api(e["PLATAFORMA_API_URL"])
api.login(e["PLATAFORMA_EMAIL"], e["PLATAFORMA_PASSWORD"])

excel = {f["producto"].strip() for f in csv.DictReader(open("seed/lista.csv", encoding="utf-8"), delimiter=";") if f["producto"].strip()}
print(f"codigos en el Excel: {len(excel):,}")

en_prod, page = set(), 1
while True:
    r = api._req("GET", f"/api/precios?limit=2000&page={page}&sort=producto")
    en_prod |= {i["producto"] for i in r["items"]}
    if page == 1: print(f"productos en la plataforma: {r['total']:,}")
    if len(r["items"]) < 2000: break
    page += 1
    print(f"   leidos {len(en_prod):,}", end="\r", flush=True)
print(f"leidos de la plataforma: {len(en_prod):,}          ")

sobran = sorted(en_prod - excel)
faltan = sorted(excel - en_prod)
print(f"\nsobran en la plataforma (se borran): {len(sobran):,}")
print(f"faltan en la plataforma (no se tocan aca): {len(faltan):,}")
if faltan[:5]: print("   ejemplos que faltan:", faltan[:5])
if not sobran:
    print("nada que borrar"); sys.exit(0)
if "--simular" in sys.argv:
    print("SIMULACION: no borro nada. Ejemplos:", sobran[:5]); sys.exit(0)

tot = {"eliminados": 0, "overrides_eliminados": 0, "overrides_conservados": 0}
conservados = []
for i in range(0, len(sobran), LOTE):
    r = api.post("/api/admin/precios/eliminar", {"productos": sobran[i:i + LOTE]})
    for k in tot: tot[k] += r.get(k, 0)
    conservados += r.get("conservados", [])
    print(f"   lote {i // LOTE + 1}/{-(-len(sobran) // LOTE)}: {r['eliminados']} borrados", end="\r", flush=True)
print(f"\n\nRESULTADO: {json.dumps(tot, ensure_ascii=False)}")
if conservados:
    print(f"conservados por tener precio fijo o congelado ({len(conservados)}): {conservados[:20]}")
r = api._req("GET", "/api/precios/resumen")
print(f"\nplataforma ahora: {r['productos']:,} productos   (Excel: {len(excel):,})")
