"""Adds the official tourism registries (open data of each comunidad, cabildo or ayuntamiento) to hotels-es.json.

Each registry entry is matched against what is already in the catalogue (OpenStreetMap, then earlier registries):
same name (fuzzy) within ~1 km, or in the same town when the registry has no coordinates. Only new places are added.
Entries without coordinates go to their postcode centre or their town centre (from OpenStreetMap).
Tourist flats (VUT/HUT/vivienda vacacional), campings, caravan areas and agencies are left out on purpose.

Usage: python tools/merge_registries.py hotels-es.json        (needs hotels-es.json.places from build_catalog.py)
Writes the merged hotels-es.json and data/registros.json (counts per source and region).
"""
import csv, io, json, math, os, re, ssl, sys, time, unicodedata, urllib.parse, urllib.request, zipfile
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher

UA = {"User-Agent": "HotelesCS-catalogo/1.0 (datos abiertos)"}
NA = {"cl": "Cataluña", "cn": "Canarias", "pv": "País Vasco", "ex": "Extremadura", "cv": "C. Valenciana", "mu": "Murcia",
      "ar": "Aragón", "cy": "Castilla y León", "na": "Navarra", "ga": "Galicia", "md": "Madrid", "as": "Asturias", "an": "Andalucía", "ib": "Baleares", "cm": "Castilla-La Mancha"}

# code, region, default type, url(s) (first that works), extra options
SOURCES = [
 ("cat", "cl", "H", ["https://analisi.transparenciacatalunya.cat/api/v3/views/t2h3-cgys/export.csv?accessType=DOWNLOAD"], {}),
 ("can-hot", "cn", "H", ["https://datos.canarias.es/catalogos/general/dataset/429db33d-cbce-4920-b1b6-b4dde9e5f90f/resource/87741d75-2ce2-4a45-8131-ad8263257664/download/establecimientos-hoteleros-inscritos-en-el-registro-general-turistico-de-canarias.csv",
                         "https://datos.canarias.es/catalogos/general/dataset/429db33d-cbce-4920-b1b6-b4dde9e5f90f/resource/d98f6ce7-e045-4d1b-9c8c-0b4233b4889a/download/establecimientos-hoteleros-inscritos-en-el-registro-general-turistico-de-canarias.json"], {}),
 ("can-ext", "cn", "A", ["https://datos.canarias.es/catalogos/general/dataset/1364104c-b86c-4ab9-8ef5-12fdf399aa01/resource/d98c2617-db26-4d15-8ee4-3b2da1130bd0/download/establecimientos-extrahoteleros-sin-viviendas-vacacionales-inscritos-en-el-registro-general-turi.csv"], {}),
 ("can-alojatur", "cn", "H", ["https://datos.canarias.es/catalogos/estadisticas/dataset/46b11d54-6efc-42d7-8de7-7f849168cbe5/resource/01215581-33a6-4b4e-a6f5-f0eb6c120a40/download/alojatur_2026.csv"], {}),
 ("tenerife", "cn", "H", ["https://datos.tenerife.es/ckan/dataset/d9cffe8d-3ff5-43b4-864a-b246c8b98cb7/resource/539bc405-514f-4966-ad7f-2437eaaefe73/download/alojamientos-turisticos-y-agencias-de-viajes-en-tenerife.csv"], {}),
 ("tenerife2", "cn", "H", ["https://datos.tenerife.es/ckan/dataset/253d5bb2-c6ec-4b9c-a02c-397ba128ad59/resource/4c045ca7-e1be-48cf-b3e9-dbd9dce58212/download/alojamientos-turisticos-de-tenerife.csv"], {}),
 ("lapalma", "cn", "H", ["https://www.opendatalapalma.es/datasets/5066d53b830746e5977e51c475b4cc6f_0.geojson"], {"utm": 28}),
 ("eus-hot", "pv", "H", ["https://opendata.euskadi.eus/contenidos/ds_recursos_turisticos/hoteles_de_euskadi/opendata/alojamientos.geojson"], {}),
 ("eus-all", "pv", "H", ["https://opendata.euskadi.eus/contenidos/ds_recursos_turisticos/alojamiento_de_euskadi/opendata/alojamientos.geojson"], {}),
 ("eus-rur", "pv", "S", ["https://opendata.euskadi.eus/contenidos/ds_recursos_turisticos/alojamientos_rurales_euskadi/opendata/alojamientos.geojson"], {}),
 ("eus-alb", "pv", "S", ["https://opendata.euskadi.eus/contenidos/ds_recursos_turisticos/albergues_de_euskadi/opendata/alojamientos.geojson"], {}),
 ("ext-hot", "ex", "H", ["https://www.juntaex.es/documents/77055/5801338/AlojamientosHoteleros.csv"], {}),
 ("ext-apt", "ex", "A", ["https://www.juntaex.es/documents/77055/5801338/AptosTuristicos.csv"], {}),
 ("ext-rur", "ex", "S", ["https://www.juntaex.es/documents/77055/5801338/AlojamientosRurales.csv"], {}),
 ("ext-alb", "ex", "S", ["https://www.juntaex.es/documents/77055/5801338/Albergues.xlsx", "https://www.juntaex.es/documents/77055/5801338/Albergues.csv"], {}),
 ("gva-hot", "cv", "H", ["https://dadesobertes.gva.es/dataset/247d0314-ecb0-4d25-a0f3-bd3d977fc911/resource/71d330c9-85e9-4ad5-94b6-95a07e6c2d51/download/listarthoteles_20260317.json"], {"ckan": ("https://dadesobertes.gva.es", "247d0314-ecb0-4d25-a0f3-bd3d977fc911")}),
 ("gva-rur", "cv", "S", ["https://dadesobertes.gva.es/dataset/981cda16-b6a5-428e-920a-729cb153f9b8/resource/6b31800d-f2e8-4e99-ad4d-913aa71ad1dc/download/lista-de-casas-rurales.csv"], {}),
 ("gva-alb", "cv", "S", ["https://dadesobertes.gva.es/dataset/7b1766e8-cd5a-41fd-8867-825b0d6a74ce/resource/2ccc33a9-0e63-4bcd-a3af-f5b94c5787d0/download/lista-de-albergues.csv"], {}),
 ("cas-hot", "cv", "H", ["https://dipcas.opendatasoft.com/api/v2/catalog/datasets/hoteles/exports/csv"], {}),
 ("cas-hs", "cv", "S", ["https://dipcas.opendatasoft.com/api/v2/catalog/datasets/hostales/exports/csv"], {}),
 ("cas-rur", "cv", "S", ["https://dipcas.opendatasoft.com/api/v2/catalog/datasets/casas-rurales/exports/csv"], {}),
 ("mur-hot", "mu", "H", ["http://nexo.carm.es/nexo/archivos/recursos/opendata/csv/Hoteles.csv"], {"utm": 30}),
 ("mur-ha", "mu", "P", ["http://nexo.carm.es/nexo/archivos/recursos/opendata/csv/HotelApartamento.csv"], {"utm": 30}),
 ("mur-apt", "mu", "A", ["http://nexo.carm.es/nexo/archivos/recursos/opendata/csv/ApartamentosTursticos.csv"], {"utm": 30}),
 ("mur-hs", "mu", "S", ["http://nexo.carm.es/nexo/archivos/recursos/opendata/csv/Hostales.csv"], {"utm": 30}),
 ("mur-pen", "mu", "S", ["http://nexo.carm.es/nexo/archivos/recursos/opendata/csv/Pensiones.csv"], {"utm": 30}),
 ("mur-alb", "mu", "S", ["http://nexo.carm.es/nexo/archivos/recursos/opendata/csv/Albergues.csv"], {"utm": 30}),
 ("mur-rur", "mu", "S", ["http://nexo.carm.es/nexo/archivos/recursos/opendata/csv/CasasRurales.csv"], {"utm": 30}),
 ("ara-hot", "ar", "H", ["https://opendata.aragon.es/GA_OD_Core/download?resource_id=65&formato=csv"], {}),
 ("ara-apt", "ar", "A", ["https://opendata.aragon.es/GA_OD_Core/download?resource_id=66&formato=csv"], {}),
 ("ara-rur", "ar", "S", ["https://opendata.aragon.es/GA_OD_Core/download?resource_id=73&formato=csv"], {}),
 ("ara-alb", "ar", "S", ["https://opendata.aragon.es/GA_OD_Core/download?resource_id=64&formato=csv"], {}),
 ("cyl-hot", "cy", "H", ["https://datosabiertos.jcyl.es/web/jcyl/risp/es/turismo/alojamientos_hoteleros/1284211831639.csv"], {}),
 ("cyl-apt", "cy", "A", ["https://datosabiertos.jcyl.es/web/jcyl/risp/es/turismo/apartamentos/1284211832109.csv"], {}),
 ("cyl-alb", "cy", "S", ["https://datosabiertos.jcyl.es/web/jcyl/risp/es/turismo/albergues_turisticos/1284211830763.csv"], {}),
 ("cyl-rur", "cy", "S", ["https://datosabiertos.jcyl.es/web/jcyl/risp/es/turismo/turismo_rural/1284211842462.csv"], {}),
 ("nav-all", "na", "H", ["https://datosabiertos.navarra.es/datastore/dump/5527debf-7e72-4f9e-8e12-b562f3027fc2?format=csv&bom=True"], {}),
 ("nav-hot", "na", "H", ["https://datosabiertos.navarra.es/datastore/dump/623f1d34-6ef3-4591-bbc0-6a71ff867ad1?format=csv&bom=True"], {}),
 ("nav-apt", "na", "A", ["https://datosabiertos.navarra.es/datastore/dump/e761b1ec-23ed-4523-bf56-d8f7a338ae3c?format=csv&bom=True"], {}),
 ("nav-alb", "na", "S", ["https://datosabiertos.navarra.es/datastore/dump/95ca4059-d22d-4dbe-86d8-f05dc5a20c3f?format=csv&bom=True"], {}),
 ("nav-rur", "na", "S", ["https://datosabiertos.navarra.es/datastore/dump/74e164d1-a0a4-485f-993c-15befc3b04b7?format=csv&bom=True"], {}),
 ("and", "an", "H", ["https://datos.juntadeandalucia.es/api/v0/openrta/all?format=csv", "https://datos.juntadeandalucia.es/api/v0/openrta/all?format=json"], {"utm": 30}),
 ("bal-mal", "ib", "H", ["https://intranet.caib.es/opendatacataleg/files/dataset/allotjaments_turistics_mallorca/allotjaments_turistics_mallorca.geojson",
                         "https://intranet.caib.es/opendatacataleg/files/dataset/allotjaments_turistics_mallorca/allotjaments_turistics_mallorca.csv"], {"utm": 31}),
 ("bal-men", "ib", "H", ["https://intranet.caib.es/opendatacataleg/files/dataset/allotjaments_turistics_menorca/allotjaments_turistics_menorca.geojson",
                         "https://intranet.caib.es/opendatacataleg/files/dataset/allotjaments_turistics_menorca/allotjaments_turistics_menorca.csv"], {"utm": 31}),
 ("clm-hot", "cm", "H", ["https://datosabiertos.castillalamancha.es/node/1601/download", "https://datosabiertos.castillalamancha.es/sites/datosabiertos.castillalamancha.es/files/Hoteles.csv"], {}),
 ("clm-rur", "cm", "S", ["https://datosabiertos.castillalamancha.es/sites/datosabiertos.castillalamancha.es/files/Alojamientos%20rurales.csv"], {}),
 ("clm-alb", "cm", "S", ["https://datosabiertos.castillalamancha.es/sites/datosabiertos.castillalamancha.es/files/Albergues.csv"], {}),
 ("gal", "ga", "H", ["https://abertos.xunta.gal/catalogo/cultura-ocio-deporte/-/dataset/0022/rexistro-empresas-actividades-turisticas/103/acceso-aos-datos.csv",
                     "https://abertos.xunta.gal/catalogo/cultura-ocio-deporte/-/dataset/0022/rexistro-empresas-actividades-turisticas/101/acceso-aos-datos.xlsx"], {}),
 ("vigo", "ga", "H", ["https://datos.vigo.org/data/turismo/poi-hoteles-es.csv"], {}),
 ("mad", "md", "H", ["https://datos.comunidad.madrid/dataset/ef437c50-5b26-4843-92c3-d8eef5507fac/resource/260e80ac-2062-41f6-9f96-4902675b1078/download/alojamientos_turisticos.csv",
                     "https://datos.comunidad.madrid/dataset/ef437c50-5b26-4843-92c3-d8eef5507fac/resource/20237d3a-718f-4179-9631-fc2f4a9fe566/download/alojamientos_turisticos.json"], {}),
 ("aviles", "as", "H", ["https://datos.aviles.es/datastore/dump/18dbf57e-71a0-4ea9-9402-8b7e727d434c?format=csv&bom=True"], {}),
 ("gijon", "as", "H", ["https://opendata.gijon.es/descargar.php?id=736&tipo=CSV"], {}),
]

# ---------- download + parse ----------
def fetch(url, tries=3):
    url = urllib.parse.quote(url, safe=":/?&=%#+,;@!$'()*~")
    last = None
    for i in range(tries):
        for ctx in (None, "loose"):
            try:
                c = None
                if ctx == "loose":   # some public portals serve an incomplete certificate chain; data is public and read-only
                    c = ssl.create_default_context(); c.check_hostname = False; c.verify_mode = ssl.CERT_NONE
                req = urllib.request.Request(url, headers=UA)
                with urllib.request.urlopen(req, timeout=180, context=c) as r:
                    return r.read()
            except urllib.error.HTTPError as e:
                last = e
                if e.code in (403, 404, 410): raise
                break
            except Exception as e:
                last = e
                if "CERTIFICATE" not in repr(e): break
        time.sleep(5 * (i + 1))
    raise last

def parse(raw, url):
    s = url.lower()
    if raw[:2] == b"PK":
        try:
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True)
            rows = list(wb.active.iter_rows(values_only=True))
            hi = next((i for i, r in enumerate(rows[:15]) if sum(1 for c in r if isinstance(c, str)) >= 3), 0)
            hdr = [str(c) for c in rows[hi]]
            return [dict(zip(hdr, r)) for r in rows[hi + 1:]]
        except Exception:
            z = zipfile.ZipFile(io.BytesIO(raw)); n = z.namelist()[0]; return parse(z.read(n), n)
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
    if st.startswith("jsonCallback("): st = st[len("jsonCallback("):].rstrip().rstrip(");")
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
            return []
        return js
    if st[:1] == "<": raise ValueError("html/xml instead of data")
    first = txt.split("\n", 1)[0]
    dl = max(";,\t|", key=first.count)
    rows = list(csv.DictReader(io.StringIO(txt), delimiter=dl))
    if len(rows) and len(rows[0]) == 1:   # whole lines quoted: unwrap and parse again
        txt2 = "\n".join(l[1:-1].replace('""', '"') if l.startswith('"') and l.endswith('"') else l for l in txt.splitlines())
        rows = list(csv.DictReader(io.StringIO(txt2), delimiter=max(";,\t|", key=txt2.split("\n", 1)[0].count)))
    return rows

def ckan_latest(base, pkg):
    js = json.loads(fetch(base + "/api/3/action/package_show?id=" + pkg))
    res = [r for r in js["result"]["resources"] if (r.get("format") or "").lower() in ("json", "csv") and "diccion" not in (r.get("name") or "").lower()]
    res.sort(key=lambda r: r.get("last_modified") or r.get("created") or "", reverse=True)
    return [r["url"] for r in res[:2]]

def load(src):
    code, reg, dty, urls, opt = src
    errs = []
    if "ckan" in opt:
        try: urls = ckan_latest(*opt["ckan"]) + urls
        except Exception as e: errs.append("ckan " + repr(e)[:120])
    for u in urls:
        try:
            rows = [r for r in parse(fetch(u), u) if isinstance(r, dict)]
            if rows: return code, rows, u, errs
            errs.append(u[:80] + " empty")
        except Exception as e:
            errs.append(u[:80] + " " + repr(e)[:160])
    return code, [], None, errs

# ---------- normalising ----------
def strip(s): return "".join(c for c in unicodedata.normalize("NFD", str(s or "")) if unicodedata.category(c) != "Mn").lower().strip()
def colkey(c): return re.sub(r"[^a-z0-9]+", "_", strip(c)).strip("_")
def val(r): return {colkey(k): ("" if v is None else str(v).strip()) for k, v in r.items() if k is not None}

NAME = ["retol", "nombre_alojamiento", "nombre_de_la_vivienda", "establecimiento_nombre_comercial", "nombre_comercial", "nombre_establecimiento", "denominacion", "documentname",
        "nombre", "name", "etiqueta", "title", "titulo", "nome", "nome_comercial", "rotulo", "denominacion_comercial"]
TYPE = ["tipus_establiment", "object_type", "group", "alojamiento_tipo", "actividad_sigla", "tipo_vivienda", "tipo_establecimiento_categoria", "grup", "modalitat", "establecimiento_tipologia", "establecimiento_modalidad", "nom_tipo", "tipo_recurso",
        "tipo_establecimiento", "tipologia", "tipo", "modalidad", "grupo", "lodgingtype", "actividad_tipo", "subcategoria", "clase", "categoria_establecimiento"]
CITY = ["municipi", "localidad_establecimiento", "direccion_municipio_nombre", "municipio_nombre", "nom_municipio", "municipio", "municipality", "concello", "localidad", "localitat", "poblacion", "locality"]
ADDR = ["direccion_establecimiento", "establishment_address", "adreca_establiment", "adreca", "direccion", "domicilio", "address", "direccion_completa", "enderezo", "adreca"]
PC = ["codi_postal", "postal_code", "codigo_postal_establecimiento", "cdpostal", "direccion_codigo_postal", "codigo_postal", "cod_postal", "c_postal", "cp", "c_p", "postalcode", "postcode", "codpostal"]
CAT = ["categoria", "categories", "category", "nom_categor", "clasificacion", "establecimiento_clasificacion", "categoria_establecimiento"]
STAT = ["estat", "estado", "situacion", "estado_actual"]
LAT = ["latitud", "coord_y", "latitude", "lat", "coordenada_y", "y"]
LON = ["longitud", "coord_x", "longitude", "lon", "lng", "coordenada_x", "x"]

def pick(v, keys):
    for k in keys:
        if v.get(k): return v[k]
    return ""

SKIP = re.compile(r"vivienda[s]? (vacacional|de uso tur|turistic|tur[ií]stica)|habitatge|\bhut\b|\bvut\b|\bvv\b|\bvt\b|\bvft\b|vivenda|camping|c[aà]mping|campament|autocaravan|area de acampada|agencia|ag[eè]ncia|turismo activo|refugi|caravan|lloguer|estada tur|\betv\b|fines turistic|pernocta|vivienda de uso|vivienda turistica|vivienda turística|bungalow park|empresa|guia|restaura|cafeter|llars compartides|informador|oficina de turismo|puerto deportivo|administracion|cerrado sin actividad", re.I)
CLOSED = re.compile(r"baja|baixa|cese|cesad|cerrad|revocad|anulad|inactiv|extingu|clausur", re.I)

def classify(typ, name, cat, default):
    t = strip(typ + " " + cat); n = strip(name)
    if SKIP.search(t): return None
    if re.search(r"apart\s*-?\s*hotel|apartahotel|hotel[- ]?apartament|hotel apartament|^ha$|\bha\b", t + " " + n): return "P"
    if re.search(r"motel", t + " " + n): return "M"
    if re.search(r"colegio mayor|residencia universitari|residencia de estudiantes|residencia juvenil", t) or (re.fullmatch(r"\s*residencias?\s*", t)): return "R"
    if re.search(r"hostal|pension|pensio|fonda|casa de huesped|hospedaje|albergue|alberg|aterpe|rural|agroturism|casa de aldea|posada|hosteria|hospederia|\bhs\b|\bhr\b|\bp\b|\bcr\b|\btr\b|\bal\b|turismo de interior|landa|masia|masoveria|fogar|casa de turismo", t):
        return "H" if re.search(r"hotel rural|hotel", t) and not re.search(r"hostal", t) else "S"
    if re.search(r"apartament|apartamento|ap\b|\bat\b|villa|bungalow|extrahotel|estudio", t): return "A"
    if re.search(r"hotel|parador|hotel-|^h$|\bh\b|establiments? hotelers?|hotelera|balneario", t): return "H"
    return default

def stars_of(cat, ty):
    c = strip(cat)
    m = re.search(r"([1-5])\s*(estrell|estrel|\*|e\b|stars?|estrelas?|llaves?|claus?)", c) or re.match(r"^\s*([1-5])\s*$", c)
    if not m:
        m2 = re.search(r"(un|una|dos|tres|cuatro|cinco)\s+estrell", c)
        if m2: return str(["un", "dos", "tres", "cuatro", "cinco"].index(m2.group(1).replace("una", "un")) + 1)
        m3 = re.fullmatch(r"\s*(\*{1,5})\s*", c) or re.search(r"/(\*{1,5})\s*$", c)
        return str(len(m3.group(1))) if m3 and ty in "HPM" else ""
    return m.group(1) if ty in "HPM" else ""

def tonum(x):
    try: return float(str(x).replace(",", "."))
    except Exception: return None

def utm_to_ll(x, y, zone):
    from pyproj import Transformer
    return Transformer.from_crs("EPSG:%d" % (25800 + zone), "EPSG:4326", always_xy=True).transform(x, y)[::-1]
def merc_to_ll(x, y):
    lon = x / 6378137 * 180 / math.pi
    lat = (2 * math.atan(math.exp(y / 6378137)) - math.pi / 2) * 180 / math.pi
    return lat, lon

def in_spain(lat, lon): return lat is not None and lon is not None and 27.4 < lat < 44.0 and -18.5 < lon < 4.6

def coords(v, raw, reg, opt):
    lat = tonum(pick(v, LAT)); lon = tonum(pick(v, LON))
    g = raw.get("_geom")
    if (lat is None or lon is None or lat == 0) and g:
        try:
            gg = g if isinstance(g, list) else json.loads(g)
            while isinstance(gg[0], list): gg = gg[0]
            lon, lat = float(gg[0]), float(gg[1])
        except Exception: pass
    if (lat is None or lat == 0) and v.get("localizacion"):
        m = re.search(r"lon:\s*(-?\d+\.\d+).*lat:\s*(-?\d+\.\d+)", v["localizacion"], re.I)
        if m: lon, lat = float(m.group(1)), float(m.group(2))
    if (lat is None or lat == 0) and v.get("ubicacion"):
        m = re.match(r"\s*(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)", v["ubicacion"])
        if m: lat, lon = float(m.group(1)), float(m.group(2))
    if lat is None or lon is None or (lat == 0 and lon == 0):
        x, y = tonum(v.get("utm_x")), tonum(v.get("utm_y"))
        if x and y: lat, lon = x, y
        else: return None, None
    if abs(lat) > 90 or abs(lon) > 180:          # projected coordinates
        a, b = lat, lon
        if a < 0 or b < 0:                      # web mercator
            x, y = (a, b) if abs(a) < abs(b) else (b, a)
            lat, lon = merc_to_ll(x, y) if abs(x) < 2.2e6 else (None, None)
        else:
            x, y = (a, b) if a < b else (b, a)    # easting is the small one, northing the big one
            try: lat, lon = utm_to_ll(x, y, opt.get("utm") or (28 if reg == "cn" else 30))
            except Exception: return None, None
    if not in_spain(lat, lon) and in_spain(lon, lat): lat, lon = lon, lat
    return (round(lat, 5), round(lon, 5)) if in_spain(lat, lon) else (None, None)

def nice(s):
    s = re.sub(r"\s+", " ", str(s or "")).strip(" ,.-")
    if s.isupper() and len(s) > 3:
        s = " ".join(w if re.fullmatch(r"[IVX]{1,4}[,.]?|[A-Z]{1,2}\d+", w) else w.capitalize() for w in s.split(" "))
        s = re.sub(r"(?<=\s)(De|Del|La|Las|Los|El|Y|En|I|D'|L')(?=\s)", lambda m: m.group(1).lower(), s)
    return s

def fix_city(c):
    c = nice(c.split("/")[0].split("|")[0].strip())
    m = re.match(r"^(.*),\s*(El|La|Los|Las|L'|Els|Les|O|A|Os|As|Es|Sa|Ses)$", c, re.I)
    if m: c = (m.group(2).capitalize() + ("" if m.group(2).endswith("'") else " ") + m.group(1)).strip()
    return c

GENERIC = set("hotel hoteles hostal hostales hs hr h pension pensio apartamentos apartamento apartaments apartament apart apartahotel aparthotel albergue alberg aterpetxea casa rural rurales turismo residencia hostel suites the de del la las los el y and en a l d s sl sa sll hotel-restaurante restaurante c b rooms inn spa resort boutique".split())
def nkey(name):
    toks = [t for t in re.split(r"[^a-z0-9]+", strip(name)) if t and t not in GENERIC]
    return " ".join(toks)
def same(a, b):
    if not a or not b: return False
    if a == b: return True
    ta, tb = set(a.split()), set(b.split())
    if ta and tb and len(ta & tb) / min(len(ta), len(tb)) >= 0.99 and min(len(ta), len(tb)) >= 1 and (len(ta & tb) >= 2 or max(len(x) for x in ta & tb) >= 5): return True
    return SequenceMatcher(None, a, b).ratio() >= 0.86

# ---------- street-level positions from CartoCiudad (official free geocoder of the IGN), cached in data/geocache.json ----------
def geocode(rows, budget=2700):
    path = "data/geocache.json"
    cache = json.load(open(path)) if os.path.exists(path) else {}
    t0 = time.time(); fails = [0]; asked = [0]
    def one(r):
        key = r[3] + "|" + r[4]
        if key in cache or time.time() - t0 > budget or (asked[0] > 30 and fails[0] == asked[0]): return
        asked[0] += 1
        try:
            q = urllib.parse.quote(r[3] + ", " + r[4])
            js = json.loads(urllib.request.urlopen(urllib.request.Request("https://www.cartociudad.es/geocoder/api/geocoder/find?q=" + q, headers=UA), timeout=30).read() or b"{}")
            lat, lon = js.get("lat"), js.get("lng")
            muni = strip(js.get("muni") or "")
            ok = lat and lon and in_spain(lat, lon) and js.get("type") in ("portal", "callejero", "Vial", "toponimo", "poblacion") and (
                not muni or set(re.split(r"[^a-z]+", muni)) & set(re.split(r"[^a-z]+", strip(r[4]))) - {"", "de", "la", "el", "del", "les", "els"})
            cache[key] = [round(lat, 5), round(lon, 5), js.get("type")] if ok else None
        except Exception:
            fails[0] += 1
    with ThreadPoolExecutor(6) as ex: list(ex.map(one, rows))
    better = 0
    for r in rows:
        c = cache.get(r[3] + "|" + r[4])
        if c and c[2] in ("portal", "callejero", "Vial"):
            r[6], r[7] = c[0], c[1]; r.pop(); better += 1
    json.dump(cache, open(path, "w"), ensure_ascii=False, separators=(",", ":"))
    print("geocoder: %d preguntas, %d fallos, %d con calle exacta de %d aproximados, %.0fs" % (asked[0], fails[0], better, len(rows), time.time() - t0))

# ---------- main ----------
def main(path):
    rows = json.load(open(path))
    rows = [r for r in rows if not str(r[0]).startswith("x")]            # drop registry rows of a previous run
    side = json.load(open(path + ".places")) if os.path.exists(path + ".places") else {"places": [], "pcs": {}}
    W = {"city": 0, "town": 1, "village": 2}
    town = {}
    for lat, lon, name, kind in side["places"]:
        k = strip(name)
        if k not in town or W.get(kind, 3) < W.get(town[k][2], 3): town[k] = (lat, lon, kind)
    pcs = side["pcs"]

    G = defaultdict(list); BYCITY = defaultdict(lambda: defaultdict(set))
    def index(r):
        nk = nkey(r[1])
        if r[6] is not None: G[(int(r[6] * 100), int(r[7] * 100))].append((r[6], r[7], nk))
        bc = BYCITY[strip(r[4])]
        for t in nk.split() or [""]: bc[t].add(nk)
    for r in rows: index(r)
    def dup(nk, lat, lon, city, exact):
        if exact:
            gx, gy = int(lat * 100), int(lon * 100); c = math.cos(math.radians(lat))
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for p in G.get((gx + dx, gy + dy), []):
                        if ((p[0] - lat) ** 2 + ((p[1] - lon) * c) ** 2) ** .5 * 111 < 1.2 and same(nk, p[2]): return True
        bc = BYCITY.get(strip(city))
        if not bc: return False
        cand = set().union(*[bc.get(t, set()) for t in nk.split() or [""]])
        return any(same(nk, o) for o in cand)

    with ThreadPoolExecutor(8) as ex: loaded = list(ex.map(load, SOURCES))
    report = []; added_all = []
    for (code, reg, dty, urls, opt), (_, raw_rows, used, errs) in zip(SOURCES, loaded):
        st = Counter(); types = Counter(); seen = set()
        for raw in raw_rows:
            v = val(raw)
            name = nice(pick(v, NAME))
            if not name or len(name) < 3: st["sin nombre"] += 1; continue
            if CLOSED.search(pick(v, STAT)): st["de baja"] += 1; continue
            if re.match(r"(VT|VUT|HUT|VV|VFT|VUT)\b", v.get("signatura", "").upper()): st["excluido (VUT, camping...)"] += 1; continue
            typ = " ".join(v.get(k, "") for k in TYPE if v.get(k))
            types[typ[:60]] += 1
            ty = classify(typ, name, pick(v, CAT), dty)
            if not ty: st["excluido (VUT, camping...)"] += 1; continue
            city = fix_city(pick(v, CITY))
            if code == "cat" and not city: continue
            addr = pick(v, ADDR)
            if not addr and v.get("nom_de_la_via"):
                addr = " ".join(x for x in (v.get("tipus_de_via", ""), v.get("nom_de_la_via", ""))) + (", " + v["numero"] if v.get("numero") else "")
            if not addr and v.get("via_nombre"): addr = (v.get("via_tipo", "").capitalize() + " " + v["via_nombre"]).strip() + (", " + v["numero"] if v.get("numero") else "")
            if not addr and v.get("via"): addr = (v.get("tipo_via", "") + " " + v["via"]).strip() + (", " + v["no"] if v.get("no") else "")
            addr = nice(addr)
            pc = re.sub(r"\.0$", "", pick(v, PC)).strip()
            if re.fullmatch(r"\d{4}", pc): pc = "0" + pc
            lat, lon = coords(v, raw, reg, opt); exact = lat is not None
            if not exact:
                if pc[:5] in pcs: lat, lon = pcs[pc[:5]]
                elif strip(city) in town: lat, lon = town[strip(city)][:2]
                else:
                    t2 = strip(re.sub(r"\s*\(.*\)", "", city))
                    if t2 in town: lat, lon = town[t2][:2]
                    else: st["sin ubicación"] += 1; continue
            nk = nkey(name) or strip(name)
            k2 = (nk, strip(city))
            if k2 in seen: st["repetido en la fuente"] += 1; continue
            seen.add(k2)
            if dup(nk, lat, lon, city, exact): st["ya estaba"] += 1; continue
            rid = "x" + code + ":" + re.sub(r"[^A-Za-z0-9-]", "", str(raw.get("Número inscripció") or v.get("signatura") or v.get("establecimiento_id") or v.get("codigo") or v.get("id") or v.get("idpoi") or len(added_all)))[:24]
            r = [rid, name, ty, addr, city, NA[reg], lat, lon, stars_of(pick(v, CAT), ty)]
            if not exact: r.append(1)     # 10th field: position is approximate (town or postcode centre)
            rows.append(r); index(r); added_all.append(r); st["añadido" + ("" if exact else " (ubicación aproximada)")] += 1
        report.append({"fuente": code, "region": NA[reg], "url": used, "filas": len(raw_rows), "resultado": dict(st), "errores": errs,
                       "tipos": dict(types.most_common(25)), "columnas": list(raw_rows[0].keys())[:40] if raw_rows else [],
                       "ejemplo": {str(k): str(x)[:60] for k, x in list(raw_rows[0].items())[:25]} if raw_rows else {}})
        print("%-13s %-14s filas=%-6d %s %s" % (code, NA[reg], len(raw_rows), dict(st), ("ERR " + " | ".join(errs)) if not raw_rows else ""))
    geocode([r for r in added_all if len(r) > 9 and r[3]])
    # stable ids: avoid collisions
    ids = Counter(r[0] for r in rows)
    for i, r in enumerate(added_all):
        if ids[r[0]] > 1: r[0] = r[0] + "-" + str(i)
    rows.sort(key=lambda x: (x[5], x[4], x[1]))
    json.dump(rows, open(path, "w"), ensure_ascii=False, separators=(",", ":"))
    os.makedirs("data", exist_ok=True)
    reg_count = Counter(r[5] for r in added_all)
    json.dump({"total": len(rows), "añadidos": len(added_all), "por_region": dict(sorted(reg_count.items())), "fuentes": report},
              open("data/registros.json", "w"), ensure_ascii=False, indent=1)
    print(len(rows), "alojamientos en total;", len(added_all), "nuevos de registros oficiales"); print(sorted(reg_count.items()))

if __name__ == "__main__":
    main(sys.argv[1])
