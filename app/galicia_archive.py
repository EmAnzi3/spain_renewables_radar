"""Official Xunta generation archives, kept separate from dated project events.

An initial inventory is a baseline, NOT a batch of new commercial opportunities.
Act dates, consultation periods and DOG-link dates are not web publication dates.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import re
import time
import unicodedata
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT = "https://economia.xunta.gal/es/transparencia/informacion-publica/"
ARCHIVES = {
    "consultations": ROOT + "en-tramitacion/instalacions-de-xeracion",
    "authorizations": ROOT + "autorizacions-administrativas/instalacions-de-xeracion",
    "environmental": ROOT + "documentacion-ambiental/impacto-ambiental/instalacions-xeracion",
}
MONTHS = {
    "enero": 1, "xaneiro": 1, "febrero": 2, "febreiro": 2, "marzo": 3,
    "abril": 4, "mayo": 5, "maio": 5, "junio": 6, "xuno": 6, "julio": 7,
    "xullo": 7, "agosto": 8, "septiembre": 9, "setembro": 9, "octubre": 10,
    "outubro": 10, "noviembre": 11, "novembro": 11, "diciembre": 12, "decembro": 12,
}


def folded(value):
    return " ".join("".join(c for c in unicodedata.normalize("NFKD", value)
                            if not unicodedata.combining(c)).casefold().split())


def official_page(url):
    p = urlsplit(url)
    if (p.scheme != "https" or p.hostname != "economia.xunta.gal"
            or p.username or p.password or p.port not in (None, 443)
            or not p.path.startswith("/es/transparencia/informacion-publica/")):
        raise ValueError("Unexpected official archive URL")
    return url


def source_id(url):
    values = [v for k, v in parse_qsl(urlsplit(official_page(url)).query) if k == "content"]
    if len(values) != 1 or not re.fullmatch(r"expediente_[A-Za-z0-9_-]+\.(?:xml|html)", values[0]):
        raise ValueError("Missing or ambiguous original archive identity")
    return values[0]


def act_date(title):
    m = re.match(r"^(?:acuerdo|acordo|resolucion|anuncio)\s+(?:de|do)\s+(\d{1,2})\s+de\s+([a-z]+)\s+de\s+(20\d\d)", folded(title))
    if not m or m[2] not in MONTHS:
        return None
    return date(int(m[3]), MONTHS[m[2]], int(m[1])).isoformat()


def parse_index(raw, url, namespace):
    soup = BeautifulSoup(raw, "html.parser")
    declared = re.search(r"(?:consulta|disponibles?)\s+(\d+)\s+expedientes", soup.get_text(" ", strip=True), re.I)
    if not declared:
        raise ValueError("Archive count missing; not a valid empty result")
    rows, paging = [], {}
    for a in soup.select("a.contedor__env__resultado[href]"):
        link = official_page(urljoin(url, a["href"]))
        title = a.get_text(" ", strip=True)
        if not title:
            raise ValueError("Empty official disposition title")
        identity = source_id(link)
        rows.append({"source_code": "XUNTA_PUBLIC", "source_namespace": namespace,
                     "external_id": identity, "record_key": namespace + ":" + identity,
                     "url": link, "title": title, "act_date": act_date(title),
                     "web_publication_date": None})
    if len({r["record_key"] for r in rows}) != len(rows):
        raise ValueError("Duplicate archive identities")
    for a in soup.select("a[href]"):
        link = urljoin(url, a["href"])
        args = dict(parse_qsl(urlsplit(link).query))
        if "page" in args and args["page"].isdigit():
            paging[int(args["page"])] = official_page(link)
    total = int(declared[1])
    if total < len(rows) or (total and not rows):
        raise ValueError("Archive count and page contents disagree")
    return total, rows, paging


def parse_detail(raw, row):
    soup = BeautifulSoup(raw, "html.parser")
    headings = soup.select("h1,h2,h3")
    if not any(folded(h.get_text(" ", strip=True)) == folded(row["title"]) for h in headings):
        raise ValueError("Detail title does not match index: " + row["url"])
    for tag in soup.select("script,style,nav,header,footer"):
        tag.decompose()
    text = soup.get_text("\n", strip=True)
    period = re.search(r"(?:consulta|consultas)\s*:\s*(\d{2}/\d{2}/\d{4})\s*[-–]\s*(\d{2}/\d{2}/\d{4})", text, re.I)
    dates = [datetime.strptime(v, "%d/%m/%Y").date().isoformat() for v in period.groups()] if period else [None, None]
    if dates[0] and dates[0] > dates[1]:
        raise ValueError("Reversed consultation interval")
    documents = {}
    for a in soup.select("a[href]"):
        target = urljoin(row["url"], a["href"])
        p = urlsplit(target)
        if p.scheme not in ("http", "https"):
            continue
        if not (".pdf" in p.path.lower() or "/dog/Publicados/" in p.path or p.hostname == "descargas.xunta.es"):
            continue
        m = re.search(r"/dog/Publicados/(\d{4})/(\d{8})/([^/]+)$", p.path)
        link_date = None
        if m:
            link_date = datetime.strptime(m[2], "%Y%m%d").date().isoformat()
            if not link_date.startswith(m[1]):
                raise ValueError("Inconsistent DOG URL date")
        documents[target] = {"url": target, "label": a.get_text(" ", strip=True),
                             "dog_date_from_link": link_date,
                             "document_downloaded": False, "publication_verified": False}
    flags = ["WEB_PUBLICATION_DATE_UNKNOWN"]
    if not row["act_date"]:
        flags.append("ACT_DATE_UNRESOLVED")
    out = dict(row, consultation_start=dates[0], consultation_end=dates[1],
               documents=sorted(documents.values(), key=lambda x: x["url"]),
               raw_text=text, flags=flags)
    # No lifecycle, MW or contractor is inferred from an archive category.
    return out


def semantic_digest(row):
    fields = ("record_key", "url", "title", "act_date", "web_publication_date",
              "consultation_start", "consultation_end", "documents")
    payload = {k: row.get(k) for k in fields}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def reconcile(previous, current):
    if not current.get("complete"):
        raise ValueError("Incomplete snapshot cannot replace the baseline")
    new = {r["record_key"]: r for r in current["records"]}
    if len(new) != len(current["records"]):
        raise ValueError("Duplicate snapshot identities")
    if previous is None:
        return {"mode": "BASELINE", "baseline_records": len(new), "newly_observed": [], "changed": [], "not_seen": []}
    if previous.get("source") != "XUNTA_PUBLIC" or not previous.get("complete"):
        raise ValueError("Invalid previous snapshot")
    old = {r["record_key"]: r for r in previous["records"]}
    if len(old) != len(previous["records"]):
        raise ValueError("Duplicate previous snapshot identities")
    return {"mode": "DELTA", "baseline_records": len(new),
            "newly_observed": sorted(new.keys() - old.keys()),
            "changed": sorted(k for k in new.keys() & old.keys() if semantic_digest(new[k]) != semantic_digest(old[k])),
            "not_seen": sorted(old.keys() - new.keys())}


class GaliciaArchive:
    def __init__(self, output_dir, *, session=None, timeout=40, pause=.15):
        self.output = Path(output_dir)
        self.output.mkdir(parents=True, exist_ok=True)
        self.session = session or requests.Session()
        self.timeout, self.pause = timeout, pause
        if session is None:
            self.session.headers["User-Agent"] = "SpainRenewablesRadar/0.5 (official public archive)"
            self.session.mount("https://", HTTPAdapter(max_retries=Retry(
                total=2, connect=1, read=1, status=2, backoff_factor=1,
                status_forcelist=(429,500,502,503,504), allowed_methods=frozenset({"GET"}))))
        self.acquisitions = []

    def get(self, url):
        official_page(url)
        # Redirects are followed only after checking their destination.
        for _ in range(5):
            response = self.session.get(url, timeout=(8, self.timeout), allow_redirects=False, stream=True)
            if response.status_code in (301,302,303,307,308):
                location = response.headers.get("Location")
                response.close()
                if not location:
                    raise ValueError("Redirect without destination")
                url = official_page(urljoin(url, location))
                continue
            try:
                response.raise_for_status()
                parts, size = [], 0
                for part in response.iter_content(65536):
                    size += len(part)
                    if size > 4_000_000:
                        raise ValueError("Archive HTML response exceeds size limit")
                    parts.append(part)
                raw = b"".join(parts)
            finally:
                response.close()
            if b"<html" not in raw.lower():
                raise ValueError("Expected HTML document")
            digest = hashlib.sha256(raw).hexdigest()
            (self.output / (digest + ".html")).write_bytes(raw)
            self.acquisitions.append({"url": url, "bytes": len(raw), "sha256": digest,
                                      "retrieved_at": datetime.now(timezone.utc).isoformat()})
            time.sleep(self.pause)
            return raw, url
        raise ValueError("Too many archive redirects")

    def collect(self):
        rows, archives = [], {}
        for namespace, root in ARCHIVES.items():
            raw, url = self.get(root)
            total, first, pages = parse_index(raw, url, namespace)
            count = (total + len(first) - 1) // len(first) if first else 1
            if count > 120 or (count > 1 and 2 not in pages):
                raise ValueError("Archive pagination cannot be reconciled")
            records = list(first)
            for page in range(2, count + 1):
                p = urlsplit(pages[2])
                args = [(k, str(page) if k == "page" else v) for k,v in parse_qsl(p.query)]
                target = urlunsplit((p.scheme,p.netloc,p.path,urlencode(args),""))
                raw, url = self.get(target)
                observed, items, _ = parse_index(raw, url, namespace)
                if observed != total or len(items) != min(len(first), total - (page - 1)*len(first)):
                    raise ValueError("Archive page count changed")
                records.extend(items)
            if len(records) != total or len({r["record_key"] for r in records}) != total:
                raise ValueError("Archive accounting mismatch")
            for row in records:
                raw, _ = self.get(row["url"])
                rows.append(parse_detail(raw, row))
                if len(rows) % 50 == 0:
                    print("DETAIL_PROGRESS", len(rows), flush=True)
            raw, url = self.get(root)
            observed, recheck, _ = parse_index(raw, url, namespace)
            if observed != total or recheck != first:
                raise ValueError("Archive changed during acquisition")
            archives[namespace] = {"records": total, "pages": count, "details": len(records)}
            print("ARCHIVE_COMPLETE", namespace, json.dumps(archives[namespace]), flush=True)
        return {"source": "XUNTA_PUBLIC", "schema_version": 1, "complete": True,
                "retrieved_at": datetime.now(timezone.utc).isoformat(), "archives": archives,
                "records": rows, "acquisitions": self.acquisitions,
                "coverage_scope": "Complete current archive and HTML details; attachments indexed, not downloaded",
                "historical_web_backfill_certified": False, "project_events_created": 0}


def write_outputs(snapshot, changes, out_dir, end):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    start = end - timedelta(days=29)
    records = snapshot["records"]
    days = [{"date": (start+timedelta(days=i)).isoformat(),
             "dated_acts_in_current_inventory": sum(r["act_date"] == (start+timedelta(days=i)).isoformat() for r in records),
             "historical_web_coverage": "NOT_CERTIFIED"} for i in range(30)]
    dates = [r["act_date"] for r in records if r["act_date"]]
    summary = {"source_inventory_complete": True, "records": len(records),
               "details": len(records), "archives": snapshot["archives"],
               "act_date_max": max(dates) if dates else None,
               "unknown_act_dates": sum(r["act_date"] is None for r in records),
               "unknown_web_publication_dates": sum(r["web_publication_date"] is None for r in records),
               "documents_indexed": sum(len(r["documents"]) for r in records),
               "identical_title_groups": sum(n>1 for n in Counter(folded(r["title"]) for r in records).values()),
               "window_start": start.isoformat(), "window_end": end.isoformat(),
               "dated_acts_in_window": sum(start.isoformat() <= r["act_date"] <= end.isoformat() for r in records if r["act_date"]),
               "project_events_created": 0, "historical_web_backfill_certified": False,
               "source_warnings": ["WEB_PUBLICATION_DATES_UNAVAILABLE", "ARCHIVE_IS_NOT_A_COMPLETE_CURRENT_DOG_FEED"]}
    if not summary["dated_acts_in_window"]:
        summary["source_warnings"].append("NO_RECENT_DATED_ACTS_IN_ARCHIVE")
    for name, data in (("inventory",snapshot),("changes",changes),("summary",summary),("window_audit",days)):
        (out/(name+".json")).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    fields = ["source_namespace","external_id","title","act_date","web_publication_date","url"]
    with (out/"inventory.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in records:
            # Avoid spreadsheet formula execution when opening downloaded CSVs.
            writer.writerow({k:("'"+str(row[k]) if str(row.get(k) or "").startswith(("=","+","-","@")) else row.get(k)) for k in fields})
    esc = lambda value: html.escape(str(value or "—"), quote=True)
    body = "".join("<tr>"+"".join("<td>"+esc(row.get(k))+"</td>" for k in fields)+"</tr>" for row in records)
    (out/"index.html").write_text("<!doctype html><html lang='it'><meta charset='utf-8'><title>Galicia — inventario ufficiale</title><style>body{font-family:Arial;margin:24px}table{border-collapse:collapse;width:100%}td,th{padding:8px;border:1px solid #ddd;text-align:left;overflow-wrap:anywhere}section{overflow:auto}</style><h1>Galicia — archivio ufficiale</h1><p>Inventario documentale, non nuove opportunità. Date degli atti distinte dalle date di pubblicazione web, non disponibili. Nessun evento amministrativo creato. Gli allegati sono indicizzati, non acquisiti.</p><p>Record: "+str(len(records))+" · Ultimo atto datato: "+esc(summary["act_date_max"])+"</p><section><table><thead><tr>"+"".join("<th>"+esc(k)+"</th>" for k in fields)+"</tr></thead><tbody>"+body+"</tbody></table></section></html>", encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="reports/galicia_archive")
    parser.add_argument("--baseline", default="data/galicia_archive_baseline.json")
    parser.add_argument("--until", type=date.fromisoformat)
    args = parser.parse_args()
    end = args.until or (datetime.now(ZoneInfo("Europe/Madrid")).date()-timedelta(days=1))
    baseline = Path(args.baseline)
    previous = json.loads(baseline.read_text(encoding="utf-8")) if baseline.exists() else None
    collector = GaliciaArchive(Path(args.output)/"raw")
    try:
        snapshot = collector.collect()
        changes = reconcile(previous, snapshot)
        replay = reconcile(snapshot, snapshot)
        if any(replay[k] for k in ("newly_observed","changed","not_seen")):
            raise ValueError("Snapshot replay is not idempotent")
        summary = write_outputs(snapshot, changes, args.output, end)
        baseline.parent.mkdir(parents=True, exist_ok=True)
        tmp = baseline.with_suffix(".tmp")
        tmp.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
        tmp.replace(baseline)
        print("GALICIA_INVENTORY", json.dumps(summary, ensure_ascii=False), flush=True)
        print("SNAPSHOT_REPLAY", json.dumps({"idempotent":True,"changes_mode":changes["mode"]}), flush=True)
    except Exception as exc:
        out = Path(args.output);out.mkdir(parents=True, exist_ok=True)
        (out/"failure.json").write_text(json.dumps({"complete":False,"error":str(exc),"baseline_preserved":True,"acquisitions":collector.acquisitions},ensure_ascii=False,indent=2),encoding="utf-8")
        raise


if __name__ == "__main__":
    main()
