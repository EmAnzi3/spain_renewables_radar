"""Official Spanish territorial hierarchy for display: 50 provinces + Ceuta/Melilla -> CCAA.

Derived data only (dato derivato): the database keeps the extracted values. Province spellings
from different bulletins (Castelló/Castellón, València/Valencia, ...) are shown under one
canonical name, and a project's comunidad autónoma is derived from its province when the source
gives none. When the extracted province contradicts the comunidad autónoma stated by the source
scope (e.g. a Catalan DOGC act whose municipality was matched to "Illes Balears"), the source
is kept and the province is withheld and flagged for review instead of being guessed.
"""
from __future__ import annotations

PROVINCE_CCAA = {
    "Almería": "Andalucía", "Cádiz": "Andalucía", "Córdoba": "Andalucía", "Granada": "Andalucía",
    "Huelva": "Andalucía", "Jaén": "Andalucía", "Málaga": "Andalucía", "Sevilla": "Andalucía",
    "Huesca": "Aragón", "Teruel": "Aragón", "Zaragoza": "Aragón",
    "Asturias": "Asturias",
    "Illes Balears": "Illes Balears",
    "Las Palmas": "Canarias", "Santa Cruz de Tenerife": "Canarias",
    "Cantabria": "Cantabria",
    "Ávila": "Castilla y León", "Burgos": "Castilla y León", "León": "Castilla y León",
    "Palencia": "Castilla y León", "Salamanca": "Castilla y León", "Segovia": "Castilla y León",
    "Soria": "Castilla y León", "Valladolid": "Castilla y León", "Zamora": "Castilla y León",
    "Albacete": "Castilla-La Mancha", "Ciudad Real": "Castilla-La Mancha", "Cuenca": "Castilla-La Mancha",
    "Guadalajara": "Castilla-La Mancha", "Toledo": "Castilla-La Mancha",
    "Barcelona": "Cataluña", "Girona": "Cataluña", "Lleida": "Cataluña", "Tarragona": "Cataluña",
    "Alicante": "Comunitat Valenciana", "Castellón": "Comunitat Valenciana", "Valencia": "Comunitat Valenciana",
    "Badajoz": "Extremadura", "Cáceres": "Extremadura",
    "A Coruña": "Galicia", "Lugo": "Galicia", "Ourense": "Galicia", "Pontevedra": "Galicia",
    "Madrid": "Madrid",
    "Murcia": "Murcia",
    "Navarra": "Navarra",
    "Álava": "País Vasco", "Bizkaia": "País Vasco", "Gipuzkoa": "País Vasco",
    "La Rioja": "La Rioja",
    "Ceuta": "Ceuta", "Melilla": "Melilla",
}

PROVINCE_ALIASES = {
    "Alicante/Alacant": "Alicante", "Alacant": "Alicante",
    "Castelló": "Castellón", "Castellón/Castelló": "Castellón", "Castelló de la Plana": "Castellón",
    "València": "Valencia", "Valencia/València": "Valencia",
    "Araba/Álava": "Álava", "Araba": "Álava", "Alava": "Álava",
    "Vizcaya": "Bizkaia", "Guipúzcoa": "Gipuzkoa", "Guipuzcoa": "Gipuzkoa",
    "Lérida": "Lleida", "Gerona": "Girona", "La Coruña": "A Coruña", "Coruña": "A Coruña", "Orense": "Ourense",
    "Baleares": "Illes Balears", "Islas Baleares": "Illes Balears", "Balears": "Illes Balears",
    "Navarra/Nafarroa": "Navarra", "Principado de Asturias": "Asturias", "Región de Murcia": "Murcia",
    "Comunidad de Madrid": "Madrid", "Avila": "Ávila", "Caceres": "Cáceres", "Cadiz": "Cádiz",
    "Cordoba": "Córdoba", "Jaen": "Jaén", "Malaga": "Málaga", "Almeria": "Almería", "Leon": "León",
}

CCAA_ALIASES = {
    "Catalunya": "Cataluña", "Comunidad Valenciana": "Comunitat Valenciana", "Comunitat valenciana": "Comunitat Valenciana",
    "Comunidad de Madrid": "Madrid", "Región de Murcia": "Murcia", "Principado de Asturias": "Asturias",
    "Comunidad Foral de Navarra": "Navarra", "Islas Baleares": "Illes Balears", "Baleares": "Illes Balears",
    "Euskadi": "País Vasco", "Aragon": "Aragón", "Andalucia": "Andalucía",
}


def canonical_province(name: str | None) -> str | None:
    if not name:
        return None
    name = " ".join(str(name).split())
    return PROVINCE_ALIASES.get(name, name)


def canonical_ccaa(name: str | None) -> str | None:
    if not name:
        return None
    name = " ".join(str(name).split())
    return CCAA_ALIASES.get(name, name)


def normalize_row(row: dict) -> list[dict]:
    """Normalise province/CCAA display fields of a portal row in place; return WARN flags."""
    flags = []
    source_ccaa = canonical_ccaa(row.get("ccaa"))
    provinces = [canonical_province(p) for p in (row.get("provinces") or ([row["province"]] if row.get("province") else []))]
    provinces = list(dict.fromkeys(p for p in provinces if p))
    if source_ccaa:
        kept = [p for p in provinces if PROVINCE_CCAA.get(p) in (None, source_ccaa)]
        dropped = [p for p in provinces if p not in kept]
        if dropped:
            flags.append({"severity": "WARN", "code": "PROVINCE_OUTSIDE_SOURCE_CCAA",
                          "detail": f"Provincia estratta {', '.join(dropped)} non appartiene a {source_ccaa} "
                                    f"(comunità della fonte): provincia non mostrata, da verificare sull'atto."})
        provinces = kept
    ccaas = {PROVINCE_CCAA[p] for p in provinces if p in PROVINCE_CCAA}
    ccaa = source_ccaa or (next(iter(ccaas)) if len(ccaas) == 1 else None)
    row["provinces"] = provinces
    row["province"] = provinces[0] if len(provinces) == 1 else None
    row["ccaa"] = ccaa
    return flags
