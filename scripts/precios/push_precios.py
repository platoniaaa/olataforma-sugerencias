# -*- coding: utf-8 -*-
"""Sube la lista de precios del Excel a la plataforma, por la API (como hace el motor).

Lee los CSV de seed/ (los saco del maestro limpio con semillas.py) y los manda a
los endpoints de administracion, en este orden:

  1. politica    factores + rubros + no_productos      (no pisa si ya hay)
  2. cargar      la lista en tandas de 5.000 filas     (la 1a con reemplazar=true)
  3. politica    precios_sugeridos + rescate de lo que el Excel tenia a mano
  4. recalcular  aplica la regla con el stock/costo que tenga la plataforma

Uso:
    python push_precios.py --api http://localhost:8000 --email x --password y
    python push_precios.py --env "C:\\ruta\\.env"     (lee PLATAFORMA_API_URL/EMAIL/PASSWORD)

Nunca imprime la contrasena ni el token.
"""
import argparse, csv, json, os, ssl, sys, time
import urllib.request, urllib.error

# En la red de Curifor hay inspeccion TLS: el proxy corporativo firma los
# certificados con un CA propio, que esta en el almacen de Windows pero no en el
# bundle de Python. `truststore` valida contra ese almacen, asi que la conexion
# sigue verificada (NO se desactiva la verificacion). Fuera de la red, el
# contexto por defecto funciona igual.
try:
    import truststore
    CTX = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
except ImportError:
    CTX = None

SEED = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seed")
LOTE = 5000


def leer(nombre):
    with open(os.path.join(SEED, f"{nombre}.csv"), encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, delimiter=";"))


def env_de(path):
    vals = {}
    with open(path, encoding="utf-8") as fh:
        for l in fh:
            l = l.strip()
            if l and not l.startswith("#") and "=" in l:
                k, v = l.split("=", 1)
                vals[k.strip()] = v.strip().strip('"').strip("'")
    return vals


class Api:
    def __init__(self, base):
        self.base = base.rstrip("/")
        self.token = None

    def _req(self, metodo, ruta, cuerpo=None, timeout=600):
        datos = json.dumps(cuerpo).encode("utf-8") if cuerpo is not None else None
        req = urllib.request.Request(self.base + ruta, data=datos, method=metodo)
        req.add_header("Content-Type", "application/json")
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
                return json.loads(r.read().decode("utf-8") or "null")
        except urllib.error.HTTPError as e:
            detalle = e.read().decode("utf-8", "ignore")[:400]
            raise SystemExit(f"ERROR {e.code} en {metodo} {ruta}: {detalle}")

    def login(self, email, password):
        r = self._req("POST", "/api/auth/login", {"email": email, "password": password})
        self.token = r["token"]
        print(f"login OK como {r['email']} (admin={r.get('es_admin')})")
        if not r.get("es_admin"):
            raise SystemExit("El usuario no es admin: los endpoints de carga son /api/admin/*")

    def post(self, ruta, cuerpo):
        return self._req("POST", ruta, cuerpo)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api")
    ap.add_argument("--email")
    ap.add_argument("--password")
    ap.add_argument("--env", help=".env con PLATAFORMA_API_URL / PLATAFORMA_EMAIL / PLATAFORMA_PASSWORD")
    ap.add_argument("--solo-politica", action="store_true")
    ap.add_argument("--sin-recalcular", action="store_true")
    a = ap.parse_args()
    if a.env:
        e = env_de(a.env)
        a.api = a.api or e.get("PLATAFORMA_API_URL")
        a.email = a.email or e.get("PLATAFORMA_EMAIL")
        a.password = a.password or e.get("PLATAFORMA_PASSWORD")
    if not (a.api and a.email and a.password):
        raise SystemExit("Faltan --api/--email/--password (o --env)")

    api = Api(a.api)
    api.login(a.email, a.password)

    politica = leer("politica")
    rubros = leer("rubros")
    no_prod = [r["producto"] for r in leer("no_productos") if r.get("producto")]
    sugeridos = leer("precios_sugeridos")
    lista = leer("lista")
    t0 = time.time()

    # La hoja Rubros quedo desactualizada (dice "Sugerido" donde la columna Tipo
    # del Excel dice "Liviano" al 100%). La politica tiene que reflejar lo que la
    # lista usa de verdad: si el 90% o mas de un rubro tiene el mismo tipo en el
    # Excel, ese es el tipo del rubro. Lo que no calce despues queda como
    # override manual, que es lo que corresponde a una excepcion.
    from collections import Counter, defaultdict
    dist = defaultdict(Counter)
    for f in lista:
        dist[(f.get("rubro") or "").strip()][(f.get("tipo") or "").strip()] += 1
    ajustes = []
    for r_ in rubros:
        c = dist.get((r_.get("rubro") or "").strip())
        if not c:
            continue
        n = sum(c.values())
        may, nm = c.most_common(1)[0]
        if may and nm / n >= 0.9 and may.lower() != (r_.get("tipo") or "").strip().lower():
            ajustes.append((r_["rubro"], r_.get("tipo"), may, nm, n))
            r_["tipo"] = may
    vistos = {(r_.get("rubro") or "").strip() for r_ in rubros}
    for rubro, c in dist.items():
        if rubro and rubro not in vistos:
            may, nm = c.most_common(1)[0]
            if may and nm / sum(c.values()) >= 0.9:
                rubros.append({"rubro": rubro, "tipo": may, "procedencia_forzada": ""})
                ajustes.append((rubro, "(no estaba)", may, nm, sum(c.values())))
    if ajustes:
        print(f"rubros ajustados por mayoria del Excel ({len(ajustes)}):")
        for aj in ajustes:
            print(f"   rubro {aj[0]:<5} {str(aj[1]):<14} -> {aj[2]:<16} ({aj[3]:,} de {aj[4]:,})")

    print("1) politica ...", end=" ", flush=True)
    r = api.post("/api/admin/precios/politica", {
        "factores": [{"tipo": p["tipo"], "procedencia": p["procedencia"], "factor": p["factor"],
                      "descuento_max": p.get("descuento_max") or None, "margen_post": p.get("margen_post") or None}
                     for p in politica],
        "rubros": [{"rubro": r_["rubro"], "tipo": r_.get("tipo"), "procedencia_forzada": r_.get("procedencia_forzada")}
                   for r_ in rubros],
        "no_productos": no_prod,
    })
    print(r)
    if a.solo_politica:
        return

    print(f"2) lista: {len(lista):,} filas en tandas de {LOTE:,}")
    tot = 0
    for i in range(0, len(lista), LOTE):
        tanda = lista[i:i + LOTE]
        r = api.post("/api/admin/precios/cargar", {"filas": tanda, "reemplazar": i == 0})
        tot += r.get("cargados", 0)
        print(f"   tanda {i // LOTE + 1}: {r}", flush=True)
    print(f"   cargados en total: {tot:,}")

    print("3) precios sugeridos + rescate de clasificacion manual ...", end=" ", flush=True)
    r = api.post("/api/admin/precios/politica", {
        "precios_sugeridos": [{"producto": s["producto"], "precio_sin_iva": s["precio_sin_iva"]} for s in sugeridos],
        "conservar_clasificacion_excel": True,
    })
    print(r)

    if not a.sin_recalcular:
        print("4) recalcular ...", end=" ", flush=True)
        r = api.post("/api/precios/recalcular", None)
        print(r)
    print(f"listo en {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
