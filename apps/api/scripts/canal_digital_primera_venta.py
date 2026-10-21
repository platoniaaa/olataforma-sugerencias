"""Calcula la primera venta de cada padre en TODA la empresa (para marcar NUEVO).

Lee ventas 2024 (solo periodo), 2025 y 2026 (fecha) ya cacheadas en parquet y el mapa
codigo->padre del cruce 3. Escribe canal_digital_primera_venta_empresa.csv en la carpeta de datos.
"""
import argparse, datetime as dt, pathlib, re
import pandas as pd

NC = {"NC CLIENTE S/T", "NC-ELECTR REPTO", "NC SEGURO S/T", "NC LIQ FACT", "NC-ELECTR GD_FAC"}
ap = argparse.ArgumentParser()
ap.add_argument("--cache", required=True); ap.add_argument("--datos", required=True)
a = ap.parse_args(); cache = pathlib.Path(a.cache); datos = pathlib.Path(a.datos)
norm = lambda s: re.sub(r"\s+", " ", str(s).strip()).upper()
mapa = pd.read_csv(datos / "canal_digital_cruce3.csv")[["codigo", "padre"]].drop_duplicates("codigo")
padre_de = dict(zip(mapa.codigo, mapa.padre))
primera = {}
def ver(cod, f):
    p = padre_de.get(cod, cod)
    if p not in primera or f < primera[p]:
        primera[p] = f
d24 = pd.read_parquet(cache.parent / "2024_min.parquet")
d24 = d24[~d24.tipoDocto.isin(NC)]
d24["q"] = pd.to_numeric(d24.Cantidad, errors="coerce")
for per, prod in d24.loc[d24.q > 0, ["Periodo", "Producto"]].drop_duplicates().itertuples(index=False):
    per = str(per); ver(norm(prod), dt.date(int(per[:4]), int(per[4:6]), 1))
for y in (2025, 2026):
    v = pd.read_parquet(cache / f"ventas_{y}.parquet")
    v = v[~v.tipo_docto.isin(NC)]
    v["q"] = pd.to_numeric(v.cantidad, errors="coerce")
    v["f"] = pd.to_datetime(v.fecha, errors="coerce").dt.date
    v = v[(v.q > 0) & v.f.notna()]
    for cod, f in v.groupby("producto_norm").f.min().items():
        ver(cod, f)
pd.DataFrame({"padre": list(primera), "primera_venta_empresa": [x.isoformat() for x in primera.values()]}) \
  .to_csv(datos / "canal_digital_primera_venta_empresa.csv", index=False)
print(len(primera), "padres")
