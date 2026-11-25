"""Busca en datos.gob.es (catálogo nacional de datos abiertos) conjuntos de datos de alojamientos turísticos
y apunta sus ficheros descargables y las columnas de cada uno en data/discovery.json."""
import csv, io, json, os, re, sys, urllib.parse, urllib.request
os.makedirs("data", exist_ok=True)

UA = {"User-Agent": "HotelesCS-catalogo/1.0 (datos abiertos)"}
def get(url, n=None):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read(n) if n else r.read()

KW = ["alojamientos", "hoteles", "establecimientos hoteleros", "alojamientos turisticos", "apartamentos turisticos",
      "registro de turismo", "turismo rural", "albergues", "hostales", "campings", "viviendas turisticas", "pensiones"]
found = {}
for kw in KW:
    for page in range(0, 6):
        u = "https://datos.gob.es/apidata/catalog/dataset/keyword/%s.json?_pageSize=50&_page=%d" % (urllib.parse.quote(kw), page)
        try: js = json.loads(get(u))
        except Exception as e: print("ERR", kw, page, e); break
        items = js.get("result", {}).get("items", [])
        if not items: break
        for it in items:
            t = it.get("title"); t = t if isinstance(t, str) else " | ".join(x.get("_value", "") if isinstance(x, dict) else str(x) for x in (t or []))
            if not re.search(r"aloja|hotel|hostal|apartament|turis|albergue|pensi|camping|rural", t, re.I): continue
            dist = it.get("distribution") or []
            if isinstance(dist, dict): dist = [dist]
            files = []
            for d in dist:
                url = d.get("accessURL") if isinstance(d, dict) else None
                fmt = d.get("format", {}) if isinstance(d, dict) else {}
                fmt = fmt.get("value", "") if isinstance(fmt, dict) else str(fmt)
                if url: files.append({"url": url, "format": fmt})
            pub = it.get("publisher"); pub = pub if isinstance(pub, str) else json.dumps(pub)[:120]
            found[it.get("_about")] = {"title": t, "publisher": pub, "files": files}
print(len(found), "datasets")

# Peek at CSV/JSON headers so the merge script can be written against real columns
for k, v in found.items():
    for f in v["files"]:
        if not re.search(r"csv|json", f["format"] + f["url"], re.I): continue
        try:
            raw = get(f["url"], 200000)
            if re.search(r"json", f["format"] + f["url"], re.I):
                j = json.loads(raw) if raw.strip()[:1] in (b"[", b"{") else None
                f["peek"] = (json.dumps(j, ensure_ascii=False)[:600] if j is not None else raw[:400].decode("utf-8", "replace"))
            else:
                txt = raw.decode("utf-8-sig", "replace") if b"\xc3" in raw[:5000] or raw[:3] == b"\xef\xbb\xbf" else raw.decode("latin-1")
                lines = txt.splitlines()
                f["peek"] = "\n".join(lines[:3])[:800]
                f["rows_in_first_200kb"] = len(lines)
        except Exception as e:
            f["peek_error"] = str(e)[:200]

json.dump(found, open("data/discovery.json", "w"), ensure_ascii=False, indent=1)
