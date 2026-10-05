from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import date

import requests

from app.geo import PROVINCE_TO_CCAA

INE_MUNICIPALITIES_URL = (
    "https://servicios.ine.es/wstempus/js/ES/VALORES_VARIABLE/19"
    "?clasif=121&det=2"
)

PROVINCE_CODE_TO_NAME = {
    "01": "Álava", "02": "Albacete", "03": "Alicante/Alacant", "04": "Almería",
    "05": "Ávila", "06": "Badajoz", "07": "Illes Balears", "08": "Barcelona",
    "09": "Burgos", "10": "Cáceres", "11": "Cádiz", "12": "Castellón",
    "13": "Ciudad Real", "14": "Córdoba", "15": "A Coruña", "16": "Cuenca",
    "17": "Girona", "18": "Granada", "19": "Guadalajara", "20": "Gipuzkoa",
    "21": "Huelva", "22": "Huesca", "23": "Jaén", "24": "León",
    "25": "Lleida", "26": "La Rioja", "27": "Lugo", "28": "Madrid",
    "29": "Málaga", "30": "Murcia", "31": "Navarra", "32": "Ourense",
    "33": "Asturias", "34": "Palencia", "35": "Las Palmas", "36": "Pontevedra",
    "37": "Salamanca", "38": "Santa Cruz de Tenerife", "39": "Cantabria",
    "40": "Segovia", "41": "Sevilla", "42": "Soria", "43": "Tarragona",
    "44": "Teruel", "45": "Toledo", "46": "Valencia", "47": "Valladolid",
    "48": "Bizkaia", "49": "Zamora", "50": "Zaragoza", "51": "Ceuta", "52": "Melilla",
}

LOCATION_ANCHOR_RE = re.compile(
    r"(?:t[eé]rminos?\s+municipales?\s+de|municipios?\s+de|ubicaci[oó]n\s*:|"
    r"emplazamiento\s*:|situad[oa]s?\s+en|ubicad[oa]s?\s+en)\s+"
    r"([^.;:\n]{2,260})",
    re.I,
)


def _norm(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r"[^a-zA-Z0-9]+", " ", value).strip().casefold()
    return re.sub(r"\s+", " ", value)


def _field(row: dict, *names: str):
    lowered = {str(k).casefold(): v for k, v in row.items()}
    for name in names:
        if name.casefold() in lowered:
            return lowered[name.casefold()]
    return None


@dataclass(frozen=True)
class Municipality:
    name: str
    code: str
    province: str
    ccaa: str


def parse_ine_municipalities(payload) -> list[Municipality]:
    if isinstance(payload, dict):
        rows = payload.get("Data") or payload.get("data") or payload.get("results") or []
    else:
        rows = payload or []
    out = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = _field(row, "Nombre", "name", "literal")
        code = _field(row, "Codigo", "Código", "code", "cod")
        if isinstance(code, (int, float)):
            code = str(int(code))
        code = re.sub(r"\D", "", str(code or ""))
        if not name or len(code) < 5:
            continue
        code = code.zfill(5)
        province = PROVINCE_CODE_TO_NAME.get(code[:2])
        if not province:
            continue
        ccaa = PROVINCE_TO_CCAA.get(province)
        if not ccaa:
            continue
        key = (_norm(str(name)), code)
        if key in seen:
            continue
        seen.add(key)
        out.append(Municipality(str(name).strip(), code, province, ccaa))
    return out


def fetch_ine_municipalities(timeout=30, user_agent="SpainRenewablesRadar/0.1"):
    session = requests.Session()
    session.headers.update({"User-Agent": user_agent})
    last_exc = None
    for _ in range(3):
        try:
            response = session.get(INE_MUNICIPALITIES_URL, timeout=timeout)
            response.raise_for_status()
            records = parse_ine_municipalities(response.json())
            if len(records) < 7000:
                raise ValueError(f"Catalogo INE incompleto: {len(records)} comuni")
            return records
        except Exception as exc:
            last_exc = exc
    raise RuntimeError(f"INE municipalities unavailable: {last_exc}")


def _location_chunks(text: str) -> list[str]:
    return [m.group(1) for m in LOCATION_ANCHOR_RE.finditer(text or "")]


def _aliases(name: str) -> set[str]:
    aliases = {_norm(name)}
    if "," in name:
        base, suffix = [x.strip() for x in name.rsplit(",", 1)]
        suffix_norm = _norm(suffix)
        if suffix_norm in {"la", "el", "las", "los", "a", "o"}:
            aliases.add(_norm(f"{suffix} {base}"))
            aliases.add(_norm(base))
    return {x for x in aliases if x}


def municipalities_in_text(text: str, catalog: list[Municipality], ccaa: str | None = None) -> list[Municipality]:
    chunks = [_norm(x) for x in _location_chunks(text)]
    if not chunks:
        return []
    matches = {}
    for municipality in catalog:
        if ccaa and municipality.ccaa != ccaa:
            continue
        for needle in _aliases(municipality.name):
            if len(needle) < 3:
                continue
            pattern = re.compile(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])")
            if any(pattern.search(chunk) for chunk in chunks):
                matches[municipality.code] = municipality
                break
    return sorted(matches.values(), key=lambda x: (x.province, x.name))


def enrich_missing_project_geography(conn, catalog: list[Municipality], source_url=INE_MUNICIPALITIES_URL):
    # Explicit multi-province evidence is not a missing single-province value.
    # Do not overwrite a validated source-specific geography with a fallback parse.
    projects = conn.execute(
        """SELECT project_key,province,ccaa FROM projects WHERE province IS NULL
           AND project_key NOT IN (SELECT project_key FROM project_geo_enrichment
               WHERE status='MULTI_PROVINCE')"""
    ).fetchall()
    enriched = 0
    multi = 0
    unresolved = 0
    details = []
    for project in projects:
        events = conn.execute(
            """SELECT title,raw_text FROM events
               WHERE project_key=? ORDER BY publication_date DESC,id DESC""",
            (project["project_key"],),
        ).fetchall()
        found = {}
        for event in events:
            text_value = f"{event['title'] or ''}\n{event['raw_text'] or ''}"
            for municipality in municipalities_in_text(text_value, catalog, project["ccaa"]):
                found[municipality.code] = municipality

        municipalities = sorted(found.values(), key=lambda x: (x.province, x.name))
        provinces = sorted({x.province for x in municipalities})
        ccaas = sorted({x.ccaa for x in municipalities})
        if len(provinces) == 1 and len(ccaas) == 1:
            status = "RESOLVED"
            province = provinces[0]
            ccaa = ccaas[0]
            conn.execute(
                """UPDATE projects
                   SET province=?,ccaa=COALESCE(ccaa,?)
                   WHERE project_key=? AND province IS NULL""",
                (province, ccaa, project["project_key"]),
            )
            enriched += 1
        elif len(provinces) > 1:
            status = "MULTI_PROVINCE"
            province = None
            ccaa = ccaas[0] if len(ccaas) == 1 else project["ccaa"]
            multi += 1
        else:
            status = "UNRESOLVED"
            province = None
            ccaa = project["ccaa"]
            unresolved += 1

        conn.execute(
            """INSERT INTO project_geo_enrichment
               (project_key,municipalities_json,provinces_json,province,ccaa,status,source_code,source_url,reference_date)
               VALUES (?,?,?,?,?,?,?,?,?)
               ON CONFLICT(project_key) DO UPDATE SET
                 municipalities_json=excluded.municipalities_json,
                 provinces_json=excluded.provinces_json,
                 province=excluded.province,
                 ccaa=excluded.ccaa,
                 status=excluded.status,
                 source_code=excluded.source_code,
                 source_url=excluded.source_url,
                 reference_date=excluded.reference_date,
                 enriched_at=CURRENT_TIMESTAMP""",
            (
                project["project_key"],
                json.dumps([x.name for x in municipalities], ensure_ascii=False),
                json.dumps(provinces, ensure_ascii=False),
                province,
                ccaa,
                status,
                "INE_MUNICIPALITIES",
                source_url,
                date.today().isoformat(),
            ),
        )
        details.append({
            "project_key": project["project_key"],
            "municipalities": [x.name for x in municipalities],
            "provinces": provinces,
            "status": status,
        })
    conn.commit()
    return {"resolved": enriched, "multi_province": multi, "unresolved": unresolved, "details": details}
