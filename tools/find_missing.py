"""Busca de nuevo los registros de alojamientos que fallan (Baleares, Castilla-La Mancha, Navarra, Galicia):
pregunta a datos.gob.es y a los portales de cada comunidad por sus ficheros actuales, prueba a descargar cada uno
y deja el resultado en data/missing.json (estado, tamaño, primera línea) para elegir la dirección buena."""
import json, os, re, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor
UA = {"User-Agent": "HotelesCS-catalogo/1.0 (datos abiertos)", "Accept": "*/*"}
def get(url, timeout=60, cap=3_000_000):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.status, r.headers.get("Content-Type", ""), r.read(cap)
def js(url):
    try: return json.loads(get(url, 60, 30_000_000)[2])
    except Exception as e: return {"_error": repr(e)[:200]}
def title_of(it):
    t = it.get("title")
    if isinstance(t, str): return t
    if isinstance(t, dict): return t.get("_value", "")
    v = [x for x in (t or []) if isinstance(x, dict)]
    return " | ".join(x.get("_value", "") for x in v)
out = {"datasets": [], "probes": [], "portals": {}}
WANT = re.compile(r"allotjament|alojamient|hotel|hostal|albergue|turismo rural|casas rurales|aloxament|establecimientos tur|empresas tur|rexistro", re.I)
PUB = re.compile(r"balear|caib|castilla-la mancha|castilla la mancha|navarra|galicia|xunta|mallorca|menorca|eivissa|ibiza|formentera", re.I)
urls = set()
for w in ["allotjaments", "alojamientos", "hoteles", "establecimientos turisticos", "turismo rural", "aloxamentos", "albergues", "registro turismo", "empresas turisticas"]:
    for page in range(0, 6):
        d = js("https://datos.gob.es/apidata/catalog/dataset/title/%s.json?_pageSize=50&_page=%d" % (urllib.parse.quote(w), page))
        items = (d.get("result") or {}).get("items") or []
        if not items: break
        for it in items:
            t = title_of(it); pub = json.dumps(it.get("publisher", ""))
            if not WANT.search(t) or not PUB.search(t + " " + pub + " " + it.get("_about", "")): continue
            dists = it.get("distribution") or []
            if isinstance(dists, dict): dists = [dists]
            ds = [{"url": x.get("accessURL"), "format": json.dumps(x.get("format"))[:80]} for x in dists if isinstance(x, dict)]
            out["datasets"].append({"title": t, "about": it.get("_about"), "publisher": pub[:120], "dist": ds})
            for x in ds:
                if x["url"]: urls.add(x["url"])
# portal APIs
for name, u in [("caib-socrata", "https://catalegdades.caib.cat/api/catalog/v1?q=allotjaments&limit=50"),
                ("caib-socrata2", "https://catalegdades.caib.cat/api/catalog/v1?q=establiments%20turistics&limit=50"),
                ("clm-ckan", "https://datosabiertos.castillalamancha.es/api/3/action/package_search?q=alojamiento&rows=50"),
                ("clm-ckan2", "https://datosabiertos.castillalamancha.es/api/3/action/package_search?q=hoteles&rows=50"),
                ("nav-ckan", "https://datosabiertos.navarra.es/api/3/action/package_search?q=alojamientos&rows=50"),
                ("gal-ckan", "https://abertos.xunta.gal/api/3/action/package_search?q=turismo&rows=50")]:
    d = js(u); out["portals"][name] = d if "_error" in d else None
    res = d.get("results") or (d.get("result") or {}).get("results") or []
    for r in res:
        if "resource" in r:   # socrata
            rid = r["resource"].get("id"); nm = r["resource"].get("name", "")
            out["datasets"].append({"title": nm, "about": r.get("link"), "publisher": name, "dist": [{"url": "https://catalegdades.caib.cat/api/views/%s/rows.csv?accessType=DOWNLOAD" % rid, "format": "csv"}]})
            if WANT.search(nm): urls.add("https://catalegdades.caib.cat/api/views/%s/rows.csv?accessType=DOWNLOAD" % rid)
        else:
            if not WANT.search(r.get("title", "") + " " + r.get("notes", "")[:200]): continue
            ds = [{"url": x.get("url"), "format": x.get("format")} for x in r.get("resources", [])]
            out["datasets"].append({"title": r.get("title"), "about": r.get("name"), "publisher": name, "dist": ds})
            for x in ds:
                if x["url"]: urls.add(x["url"])
def probe(u):
    try:
        st, ct, b = get(u, 120)
        first = b[:300].decode("utf-8", "replace").replace("\n", "\\n")
        return {"url": u, "status": st, "type": ct, "bytes": len(b), "first": first}
    except Exception as e: return {"url": u, "error": repr(e)[:200]}
with ThreadPoolExecutor(8) as ex: out["probes"] = list(ex.map(probe, sorted(urls)[:150]))
os.makedirs("data", exist_ok=True)
json.dump(out, open("data/missing.json", "w"), ensure_ascii=False, indent=1)
print(len(out["datasets"]), "datasets,", len(out["probes"]), "probes")
