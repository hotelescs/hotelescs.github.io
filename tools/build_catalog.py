"""Builds hotels-es.json (every lodging in Spain from OpenStreetMap) from one or more .osm.pbf files.

Row format: [osmKey, name, typeCode, street, city, region, lat, lon, stars]
typeCode: H hotel, A apartamento, S hostal/pensión/albergue, M motel, P aparthotel, R residencia
Usage: python tools/build_catalog.py hotels-es.json spain.osm.pbf canarias.osm.pbf
"""
import json, math, re, sys
import osmium

TY = {'hotel': 'H', 'apartment': 'A', 'guest_house': 'S', 'hostel': 'S', 'motel': 'M'}
PROV = {  # first two digits of the postcode -> comunidad
 '01':'País Vasco','20':'País Vasco','48':'País Vasco','02':'Castilla-La Mancha','13':'Castilla-La Mancha','16':'Castilla-La Mancha','19':'Castilla-La Mancha','45':'Castilla-La Mancha',
 '03':'C. Valenciana','12':'C. Valenciana','46':'C. Valenciana','04':'Andalucía','11':'Andalucía','14':'Andalucía','18':'Andalucía','21':'Andalucía','23':'Andalucía','29':'Andalucía','41':'Andalucía',
 '05':'Castilla y León','09':'Castilla y León','24':'Castilla y León','34':'Castilla y León','37':'Castilla y León','40':'Castilla y León','42':'Castilla y León','47':'Castilla y León','49':'Castilla y León',
 '06':'Extremadura','10':'Extremadura','07':'Baleares','08':'Cataluña','17':'Cataluña','25':'Cataluña','43':'Cataluña','15':'Galicia','27':'Galicia','32':'Galicia','36':'Galicia',
 '22':'Aragón','44':'Aragón','50':'Aragón','26':'La Rioja','28':'Madrid','30':'Murcia','31':'Navarra','33':'Asturias','35':'Canarias','38':'Canarias','39':'Cantabria','51':'Ceuta','52':'Melilla'}

def region_of(pc):
    m = re.match(r'\s*(\d{5})\b', pc or '')
    return PROV.get(m.group(1)[:2]) if m else None

class H(osmium.SimpleHandler):
    def __init__(self):
        super().__init__(); self.items = {}; self.places = []
    def add(self, key, tags, lat, lon):
        name = (tags.get('name') or '').strip()
        if not name or lat is None: return
        t = tags.get('tourism')
        if t in TY: ty = TY[t]
        elif tags.get('amenity') == 'student_accommodation' or tags.get('building') == 'dormitory': ty = 'R'
        else: return
        if re.search(r'apar?t[ah]*otel|apartahotel', name, re.I): ty = 'P'
        elif re.search(r'residencia|colegio mayor|living', name, re.I) and ty in 'AS': ty = 'R'
        street = tags.get('addr:street', '')
        if street and tags.get('addr:housenumber'): street += ', ' + tags.get('addr:housenumber')
        pc = tags.get('addr:postcode', '')
        if pc and not re.match(r'\s*\d{5}\b', pc): return            # foreign postcode: outside Spain
        if pc and not region_of(pc): return
        self.items[key] = [key, name, ty, street, tags.get('addr:city', ''), region_of(pc) or '', round(lat, 5), round(lon, 5), tags.get('stars', '')]
    def node(self, n):
        tg = n.tags
        if tg.get('place') in ('city', 'town', 'village') and tg.get('name'):
            self.places.append((n.location.lat, n.location.lon, tg.get('name'), tg.get('place'), region_of(tg.get('addr:postcode', ''))))
        if 'tourism' in tg or 'amenity' in tg or 'building' in tg:
            self.add('n%d' % n.id, dict(tg), n.location.lat, n.location.lon)
    def way(self, w):
        tg = w.tags
        if not ('tourism' in tg or 'amenity' in tg or 'building' in tg): return
        pts = [(nd.location.lat, nd.location.lon) for nd in w.nodes if nd.location.valid()]
        if pts: self.add('w%d' % w.id, dict(tg), sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))

def grid(points, f):
    G = {}
    for p in points: G.setdefault((int(p[0] * f), int(p[1] * f)), []).append(p)
    return G

def nearest(G, f, lat, lon, ok, rng=3):
    best, bd = None, 9e9; gx, gy = int(lat * f), int(lon * f); c = math.cos(math.radians(lat))
    for dx in range(-rng, rng + 1):
        for dy in range(-rng, rng + 1):
            for p in G.get((gx + dx, gy + dy), []):
                if not ok(p): continue
                d = (p[0] - lat) ** 2 + ((p[1] - lon) * c) ** 2
                if d < bd: bd, best = d, p
    return best

def main(out, files):
    h = H()
    for f in files: h.apply_file(f, locations=True)
    rows = list(h.items.values())
    # city: addr:city, else nearest town/village
    PG = grid(h.places, 20)
    for r in rows:
        if not r[4]:
            p = nearest(PG, 20, r[6], r[7], lambda p: True)
            if p: r[4] = p[2]
    # region: from postcode, else from the nearest lodging (or place) whose region is known
    known = [(r[6], r[7], r[5]) for r in rows if r[5]] + [(p[0], p[1], p[4]) for p in h.places if p[4]]
    KG = grid(known, 10)
    for r in rows:
        if not r[5]:
            p = nearest(KG, 10, r[6], r[7], lambda p: True, rng=4)
            r[5] = p[2] if p else ''
    rows = [r for r in rows if r[5]]
    rows.sort(key=lambda x: (x[5], x[4], x[1]))
    json.dump(rows, open(out, 'w'), ensure_ascii=False, separators=(',', ':'))
    from collections import Counter
    print(len(rows), 'alojamientos'); print(sorted(Counter(r[5] for r in rows).items()))

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2:])
