"""Segunda pasada: busca más registros oficiales de alojamientos en datos.gob.es (por título y por id),
descarga cada fichero candidato completo y anota columnas, número de filas y dos ejemplos en data/probe.json."""
import csv, io, json, os, re, sys, urllib.parse, urllib.request, zipfile
from concurrent.futures import ThreadPoolExecutor
os.makedirs("data", exist_ok=True)
UA = {"User-Agent": "HotelesCS-catalogo/1.0 (datos abiertos)"}
def get(url, timeout=90, cap=80_000_000):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(cap)

def title_of(it):
    t = it.get("title")
    if isinstance(t, str): return t
    if isinstance(t, dict): return t.get("_value", "")
    vals = [x for x in (t or []) if isinstance(x, dict)]
    es = [x["_value"] for x in vals if x.get("_lang") == "es"]
    return es[0] if es else " | ".join(x.get("_value", "") for x in vals)

WORDS = ["alojamiento", "alojamientos", "hotel", "hoteles", "hoteleros", "hoteleras", "apartamentos", "aparthoteles",
         "hostales", "albergues", "allotjaments", "allotjament", "establiments", "aloxamentos", "aloxamento",
         "establecementos", "ostatu", "registro turismo", "empresas turisticas", "actividades turisticas",
         "casas rurales", "turismo rural", "establecimientos turisticos", "oferta turistica", "hospedaje"]
IDS = ["a09002970-establecimientos-de-alojamiento-turistico-inscritos-en-el-registro-de-turismo-de-catalunya",
       "a12002994-registro-de-empresas-y-actividades-turisticas",
       "a15002917-establecimientos-hoteleros-en-activo-del-registro-de-turismo-de-navarra1",
       "a04003003-alojamientos-turisticos-de-menorca1", "a04003003-allotjaments-turistics-mallorca",
       "l01281150-alojamientos-turisticos"]
GOOD = re.compile(r"registr|inscrit|alojamientos? tur|hoteles de|hotels|hotelak|establecimientos? (hoteler|de alojamiento|tur)|allotjament|aloxament|alojamientos hoteleros|apartament|aparthotel|albergue|casas rurales|turismo rural en|alojamientos rurales|ostatu|landa|hostales|pensiones de la ciudad|lodgings|empresas y actividades|^alojamientos$|^hoteles$|oferta de alojamiento de", re.I)
BAD = re.compile(r"pernoct|viajer|encuesta|estad[ií]st|ocupaci|plazas|gasto|[ií]ndice|seg[uú]n|por meses|estancia|n[uú]mero|number|guests|average|overnight|precio|price|boletin|bolet[ií]n|pensiones contributivas|pensionist|beneficiari|evoluci|turistas|tourists|viviendas familiares|edificios|empleado", re.I)

found = {}
def add(it):
    k = it.get("_about") or it.get("identifier")
    if not k or k in found: return
    found[k] = it
for w in WORDS:
    for page in range(0, 8):
        u = "https://datos.gob.es/apidata/catalog/dataset/title/%s.json?_pageSize=50&_page=%d" % (urllib.parse.quote(w), page)
        try: items = json.loads(get(u)).get("result", {}).get("items", [])
        except Exception as e: print("ERR", w, page, e); break
        if not items: break
        for it in items: add(it)
for i in IDS:
    try:
        for it in json.loads(get("https://datos.gob.es/apidata/catalog/dataset/%s.json" % i)).get("result", {}).get("items", []): add(it)
    except Exception as e: print("ERR id", i, e)
print(len(found), "datasets in total")

cands = []
for k, it in found.items():
    t = title_of(it)
    if not GOOD.search(t) or BAD.search(t): continue
    dist = it.get("distribution") or []
    if isinstance(dist, dict): dist = [dist]
    files = []
    for d in dist:
        if not isinstance(d, dict): continue
        u = d.get("accessURL"); f = d.get("format", {})
        f = (f.get("value") if isinstance(f, dict) else str(f)) or ""
        if u: files.append((u, f))
    def score(x):
        s = (x[0] + " " + x[1]).lower()
        if "padding" in s or "jsonp" in s or "kml" in s or "sparql" in s or "/api" in s and "export" not in s: return 50
        for i, r in enumerate(["csv", "geo+json", "geojson", "json", "spreadsheetml", "xlsx", "excel", "xls"]):
            if r in s: return i
        return 40
    files.sort(key=score)
    pub = it.get("publisher"); pub = pub if isinstance(pub, str) else str(pub)
    cands.append({"id": k, "title": t, "publisher": pub.split("/")[-1], "files": files[:3]})
print(len(cands), "candidate registries")

def parse(raw, url, fmt):
    s = (url + fmt).lower()
    if raw[:2] == b"PK" and ("xls" in s or "spreadsheet" in s or b"xl/" in raw[:2000]):
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True)
        rows = list(wb.active.iter_rows(values_only=True))
        hi = next((i for i, r in enumerate(rows[:15]) if sum(1 for c in r if isinstance(c, str)) >= 3), 0)
        hdr = [str(c) for c in rows[hi]]
        return [dict(zip(hdr, r)) for r in rows[hi + 1:]]
    if raw[:2] == b"PK":
        z = zipfile.ZipFile(io.BytesIO(raw)); n = z.namelist()[0]; return parse(z.read(n), n, fmt)
    if raw[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        import xlrd
        sh = xlrd.open_workbook(file_contents=raw).sheet_by_index(0)
        rows = [sh.row_values(i) for i in range(sh.nrows)]
        hi = next((i for i, r in enumerate(rows[:15]) if sum(1 for c in r if isinstance(c, str) and c) >= 3), 0)
        return [dict(zip([str(c) for c in rows[hi]], r)) for r in rows[hi + 1:]]
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try: txt = raw.decode(enc); break
        except UnicodeDecodeError: continue
    st = txt.lstrip()
    if st[:1] in "[{":
        js = json.loads(st)
        if isinstance(js, dict):
            if "features" in js:
                return [dict(f.get("properties") or {}, _geom=(f.get("geometry") or {}).get("coordinates")) for f in js["features"]]
            if "fields" in js and "records" in js:
                names = [f["id"] for f in js["fields"]]; return [dict(zip(names, r)) for r in js["records"]]
            for key in ("data", "result", "records", "items", "results", "rows"):
                v = js.get(key)
                if isinstance(v, dict): v = v.get("records") or v.get("items")
                if isinstance(v, list): return v
            return [js]
        return js
    if st[:1] == "<": raise ValueError("html/xml")
    sample = txt[:20000]
    try: dl = csv.Sniffer().sniff(sample, delimiters=";,\t|").delimiter
    except Exception: dl = ";" if sample.count(";") > sample.count(",") else ","
    return list(csv.DictReader(io.StringIO(txt), delimiter=dl))

def probe(c):
    out = dict(c); out["result"] = []
    for u, f in c["files"]:
        try:
            raw = get(u)
            rows = parse(raw, u, f)
            rows = [r for r in rows if isinstance(r, dict)]
            out["result"].append({"url": u, "fmt": f, "bytes": len(raw), "n": len(rows),
                                  "cols": list(rows[0].keys()) if rows else [],
                                  "sample": [{k: (str(v)[:80] if v is not None else None) for k, v in r.items()} for r in rows[:2]]})
            if rows: break
        except Exception as e:
            out["result"].append({"url": u, "fmt": f, "error": repr(e)[:200]})
    return out

with ThreadPoolExecutor(8) as ex: res = list(ex.map(probe, cands))
res.sort(key=lambda r: -max([x.get("n", 0) for x in r["result"]] or [0]))
json.dump(res, open("data/probe.json", "w"), ensure_ascii=False, indent=1)
for r in res:
    best = max(r["result"], key=lambda x: x.get("n", 0), default={})
    print(best.get("n", "ERR"), "|", r["publisher"], "|", r["title"][:90])
