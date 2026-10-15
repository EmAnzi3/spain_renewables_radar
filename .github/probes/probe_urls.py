"""Generic reachability/shape probe for candidate official endpoints. Writes JSON results."""
import hashlib, json, re, sys, time
from urllib.parse import urljoin
import requests

UA = "SpainRenewablesRadar/0.1 (+https://github.com/EmAnzi3/spain_renewables_radar)"
KEY = re.compile(r"sumari|sumario|dades|datos|rss|xml|json|api|opendata|indice|index|boletin|butlleti|anuncio|anunci|calendar|calendari", re.I)

def probe(url):
    t0 = time.time(); r = {"url": url}
    try:
        resp = requests.get(url, headers={"User-Agent": UA, "Accept": "*/*"}, timeout=(10, 60), allow_redirects=True)
        body = resp.content
        r.update(status=resp.status_code, final_url=resp.url, content_type=resp.headers.get("content-type"),
                 bytes=len(body), sha256=hashlib.sha256(body).hexdigest(), seconds=round(time.time() - t0, 1))
        txt = body[:400000].decode(resp.encoding or "utf-8", errors="replace")
        r["head"] = txt[:3000]
        if "html" in (r["content_type"] or ""):
            links = sorted({urljoin(resp.url, h) for h in re.findall(r'''(?:href|src|action)=["']([^"'#]+)''', txt) if KEY.search(h)})
            r["links"] = links[:200]
    except Exception as e:
        r.update(error=f"{type(e).__name__}: {e}"[:400], seconds=round(time.time() - t0, 1))
    return r

if __name__ == "__main__":
    urls = [u.strip() for u in open(sys.argv[1]) if u.strip() and not u.startswith("#")]
    out = [probe(u) for u in urls]
    json.dump(out, open(sys.argv[2], "w"), ensure_ascii=False, indent=1)
    for r in out: print(r.get("status"), r.get("bytes"), r["url"], r.get("error", ""))
