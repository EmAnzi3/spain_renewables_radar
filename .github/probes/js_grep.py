"""Download a SPA page and its scripts; report lines mentioning endpoints/templates."""
import json, re, sys
from urllib.parse import urljoin
import requests
UA = "SpainRenewablesRadar/0.1 (+https://github.com/EmAnzi3/spain_renewables_radar)"
PAT = re.compile(r"https?://[a-z0-9.-]+/[a-z0-9/_-]*(?:api|backend|rest|services)[a-z0-9/_-]*|environment|apiUrl|urlBase|backend|\.json|\.csv|\.xml|/api/|/rest|services/|backend|baseUrl|apiUrl|endpoint|sumari|datos|dades", re.I)
out = {}
for page in sys.argv[2:]:
    res = {"scripts": {}}
    try:
        html = requests.get(page, headers={"User-Agent": UA}, timeout=60).text
        res["page_hits"] = sorted(set(m.strip()[:300] for m in re.findall(r"[^\n]*(?:%s)[^\n]*" % PAT.pattern, html, re.I)))[:80]
        base = re.search(r'<base href="([^"]+)"', html)
        root = urljoin(page, base.group(1)) if base else page
        srcs = [urljoin(root, s) for s in re.findall(r'''<script[^>]*\bsrc=["']?([^"' >]+)''', html)]
        res["srcs"] = srcs
        for s in srcs[:60]:
            if "googleapis" in s or "fontawesome" in s: continue
            try:
                js = requests.get(s, headers={"User-Agent": UA}, timeout=60).text
            except Exception as e:
                res["scripts"][s] = [f"ERR {e}"]; continue
            hits = []
            for m in re.finditer(PAT, js):
                hits.append(js[max(0, m.start() - 120):m.end() + 160].replace("\n", " "))
            res["scripts"][s] = hits[:40]
    except Exception as e:
        res["error"] = str(e)
    out[page] = res
json.dump(out, open(sys.argv[1], "w"), ensure_ascii=False, indent=1)
print({k: len(v["scripts"]) for k, v in out.items()})
