"""Gives every town in hotels-es.json its province, so the app can show "Cullera (Valencia)".
Town list: INE municipalities (data/municipios.csv, from codeforspain/ds-organizacion-administrativa).
A town the list does not know (a beach resort, a village inside a municipality) gets the province of the
nearest known town in the same region, or of the nearest provincial capital if there is none.
Writes provincias.json: {"<town>|<region>": "<province>"} with the same normalisation as the app (lowercase, no accents)."""
import csv, json, math, re, unicodedata, collections

def norm(s):
    s = unicodedata.normalize("NFD", str(s or "").lower())
    return "".join(c for c in s if not unicodedata.combining(c)).strip()

# id: (short name, region as written in the catalogue, capital lat, lon)
P = {"01":("Álava","País Vasco",42.847,-2.672),"02":("Albacete","Castilla-La Mancha",38.994,-1.858),"03":("Alicante","C. Valenciana",38.345,-0.481),
"04":("Almería","Andalucía",36.834,-2.464),"05":("Ávila","Castilla y León",40.656,-4.700),"06":("Badajoz","Extremadura",38.879,-6.970),
"07":("Baleares","Baleares",39.570,2.650),"08":("Barcelona","Cataluña",41.387,2.170),"09":("Burgos","Castilla y León",42.344,-3.697),
"10":("Cáceres","Extremadura",39.475,-6.372),"11":("Cádiz","Andalucía",36.527,-6.289),"12":("Castellón","C. Valenciana",39.986,-0.051),
"13":("Ciudad Real","Castilla-La Mancha",38.985,-3.927),"14":("Córdoba","Andalucía",37.888,-4.779),"15":("A Coruña","Galicia",43.362,-8.411),
"16":("Cuenca","Castilla-La Mancha",40.070,-2.137),"17":("Girona","Cataluña",41.979,2.821),"18":("Granada","Andalucía",37.177,-3.599),
"19":("Guadalajara","Castilla-La Mancha",40.633,-3.167),"20":("Gipuzkoa","País Vasco",43.318,-1.981),"21":("Huelva","Andalucía",37.261,-6.945),
"22":("Huesca","Aragón",42.140,-0.408),"23":("Jaén","Andalucía",37.779,-3.785),"24":("León","Castilla y León",42.599,-5.567),
"25":("Lleida","Cataluña",41.617,0.620),"26":("La Rioja","La Rioja",42.465,-2.445),"27":("Lugo","Galicia",43.012,-7.556),
"28":("Madrid","Madrid",40.417,-3.704),"29":("Málaga","Andalucía",36.721,-4.421),"30":("Murcia","Murcia",37.992,-1.131),
"31":("Navarra","Navarra",42.817,-1.643),"32":("Ourense","Galicia",42.336,-7.864),"33":("Asturias","Asturias",43.362,-5.849),
"34":("Palencia","Castilla y León",42.010,-4.533),"35":("Las Palmas","Canarias",28.124,-15.430),"36":("Pontevedra","Galicia",42.431,-8.644),
"37":("Salamanca","Castilla y León",40.970,-5.663),"38":("Santa Cruz de Tenerife","Canarias",28.464,-16.251),"39":("Cantabria","Cantabria",43.462,-3.810),
"40":("Segovia","Castilla y León",40.948,-4.118),"41":("Sevilla","Andalucía",37.389,-5.984),"42":("Soria","Castilla y León",41.764,-2.464),
"43":("Tarragona","Cataluña",41.119,1.245),"44":("Teruel","Aragón",40.345,-1.106),"45":("Toledo","Castilla-La Mancha",39.863,-4.027),
"46":("Valencia","C. Valenciana",39.470,-0.376),"47":("Valladolid","Castilla y León",41.652,-4.724),"48":("Bizkaia","País Vasco",43.263,-2.935),
"49":("Zamora","Castilla y León",41.503,-5.745),"50":("Zaragoza","Aragón",41.649,-0.889),"51":("Ceuta","Ceuta",35.889,-5.321),"52":("Melilla","Melilla",35.292,-2.938)}
REG_ALIAS = {"catalunya":"cataluña","comunitat valenciana":"c. valenciana","comunidad valenciana":"c. valenciana","illes balears":"baleares",
  "islas baleares":"baleares","comunidad de madrid":"madrid","region de murcia":"murcia","principado de asturias":"asturias",
  "euskadi":"pais vasco","comunidad foral de navarra":"navarra","castilla - la mancha":"castilla-la mancha"}
def reg(r):
    r = norm(r); return norm(REG_ALIAS.get(r, r))

def variants(name):
    out = set()
    for part in re.split(r"\s*/\s*", name):
        part = part.strip(); out.add(norm(part))
        m = re.match(r"^(.*?)(?:,\s*|\s*\()(el|la|los|las|l'|els|les|o|a|os|as|lo)\)?$", part, re.I)   # "Palmas de Gran Canaria, Las"
        if m: out.add(norm(m.group(2) + ("" if m.group(2).endswith("'") else " ") + m.group(1)))
    return out

towns = collections.defaultdict(set)
for row in csv.DictReader(open("data/municipios.csv", encoding="utf-8")):
    for v in variants(row["nombre"]): towns[v].add(row["provincia_id"])

def nearest(lat, lon, region):
    c = [k for k, p in P.items() if reg(p[1]) == region] or list(P)
    return min(c, key=lambda k: (P[k][2]-lat)**2 + ((P[k][3]-lon)*math.cos(math.radians(lat)))**2)

cat = json.load(open("hotels-es.json", encoding="utf-8"))
try: cat = json.load(open("hotels-extra.json", encoding="utf-8")) + cat
except Exception: pass
pts = collections.defaultdict(list)
for x in cat:
    if x[4] and x[6] is not None: pts[(x[4], x[5])].append((float(x[6]), float(x[7])))
out, known, todo = {}, [], []
for (city, region), ll in pts.items():
    if norm(city) == "gibraltar": continue
    r = reg(region); lat = sorted(a for a, b in ll)[len(ll)//2]; lon = sorted(b for a, b in ll)[len(ll)//2]
    ids = set()
    for v in variants(city): ids |= towns.get(v, set())
    same = [i for i in ids if reg(P[i][1]) == r]
    key = norm(city) + "|" + norm(region)
    if same:
        pid = same[0] if len(same) == 1 else min(same, key=lambda k: (P[k][2]-lat)**2 + (P[k][3]-lon)**2)
        out[key] = P[pid][0]; known.append((r, lat, lon, pid))
    else: todo.append((key, r, lat, lon))
byreg = collections.defaultdict(list)
for r, lat, lon, pid in known: byreg[r].append((lat, lon, pid))
for key, r, lat, lon in todo:
    near = byreg.get(r)
    pid = min(near, key=lambda t: (t[0]-lat)**2 + ((t[1]-lon)*math.cos(math.radians(lat)))**2)[2] if near else nearest(lat, lon, r)
    out.setdefault(key, P[pid][0])
hit, miss = len(known), len(todo)
json.dump(out, open("provincias.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"), sort_keys=True)
print(f"provincias.json: {len(out)} towns, {hit} from INE list, {miss} by nearest known town")
