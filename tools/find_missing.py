"""Busca de nuevo los registros de alojamientos que fallan (Baleares, Castilla-La Mancha, Navarra, Galicia):
lee las páginas y APIs de cada portal, saca los enlaces a ficheros, prueba a descargarlos
y deja el resultado en data/missing.json (estado, tamaño, primera línea) para elegir la dirección buena."""
import json, os, re, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor
UA = {"User-Agent": "Mozilla/5.0 (HotelesCS-catalogo/1.0; datos abiertos)", "Accept": "*/*"}
def get(url, timeout=60, cap=3_000_000):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.status, r.headers.get("Content-Type", ""), r.read(cap), r.geturl()
out = {"pages": {}, "probes": []}
FILE = re.compile(r"""(?:href|url)["']?\s*[:=]\s*["']([^"'<>\s]+?\.(?:csv|geojson|json|xlsx?|ods|zip)(?:\?[^"'<>\s]*)?)["']""", re.I)
PAGES = [
 "https://intranet.caib.es/opendatacataleg/api/3/action/package_search?q=allotjaments&rows=100",
 "https://intranet.caib.es/opendatacataleg/api/3/action/package_search?q=establiments%20turistics&rows=100",
 "https://intranet.caib.es/opendatacataleg/ca/dataset/groups/allotjaments-turistics-mallorca",
 "https://intranet.caib.es/opendatacataleg/dataset/?tags=allotjaments",
 "https://intranet.caib.es/opendatacataleg/group/turismo",
 "https://catalegdades.caib.cat/",
 "https://catalegdades.caib.cat/api/3/action/package_search?q=allotjaments&rows=100",
 "https://datosabiertos.castillalamancha.es/node/282/revisions/683/view",
 "https://datosabiertos.castillalamancha.es/dataset/albergues-tur%C3%ADsticos-de-castilla-la-mancha",
 "https://datosabiertos.castillalamancha.es/dataset/alojamientos-tur%C3%ADsticos-hoteleros-de-castilla-la-mancha",
 "https://datosabiertos.castillalamancha.es/dataset/alojamientos-de-turismo-rural-de-castilla-la-mancha",
 "https://datos.gob.es/apidata/catalog/dataset/a08002880-establecimientos-de-alojamiento-turistico-de-castilla-la-mancha.json",
 "https://datos.gob.es/apidata/catalog/dataset/a08002880-alojamientos-de-turismo-rural-de-castilla-la-mancha.json",
 "https://datos.gob.es/apidata/catalog/dataset/a08002880-albergues-turisticos-de-castilla-la-mancha.json",
 "https://datos.gob.es/apidata/catalog/dataset/a04003003-alojamientos-turisticos-mallorca.json",
]
urls = set(["https://datosabiertos.castillalamancha.es/sites/datosabiertos.castillalamancha.es/files/01%20ESTABLECIMIENTOS%20HOTELEROS.csv",
  "https://datosabiertos.castillalamancha.es/sites/datosabiertos.castillalamancha.es/files/01%20ESTABLECIMIENTOS%20HOTELEROS_0.csv",
  "https://datosabiertos.castillalamancha.es/sites/datosabiertos.castillalamancha.es/files/01%20HOTELES.csv",
  "http://datosabiertos.navarra.es/datastore/dump/5527debf-7e72-4f9e-8e12-b562f3027fc2?format=csv",
  "https://abertos.xunta.gal/catalogo/cultura-ocio-deporte/-/dataset/0022/rexistro-empresas-actividades-turisticas/103/acceso-aos-datos.csv"])
for u in PAGES:
    try:
        st, ct, b, fin = get(u, 60, 20_000_000); t = b.decode("utf-8", "replace")
        found = set(urllib.parse.urljoin(fin, x.replace("\\/", "/")) for x in FILE.findall(t))
        out["pages"][u] = {"status": st, "bytes": len(b), "links": sorted(found)[:200]}
        urls |= set(x for x in found if re.search(r"allotj|aloj|hotel|hostal|albergue|rural|turis|establec", x, re.I))
    except Exception as e: out["pages"][u] = {"error": repr(e)[:200]}
def probe(u):
    try:
        st, ct, b, fin = get(u, 120)
        return {"url": u, "final": fin, "status": st, "type": ct, "bytes": len(b), "first": b[:300].decode("utf-8", "replace")}
    except Exception as e: return {"url": u, "error": repr(e)[:200]}
with ThreadPoolExecutor(8) as ex: out["probes"] = list(ex.map(probe, sorted(urls)[:200]))
os.makedirs("data", exist_ok=True)
json.dump(out, open("data/missing.json", "w"), ensure_ascii=False, indent=1)
print(len(out["probes"]), "probes")
