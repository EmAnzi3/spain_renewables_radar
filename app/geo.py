from __future__ import annotations
import re

PROVINCE_TO_CCAA = {
    "A Coruña":"Galicia","Lugo":"Galicia","Ourense":"Galicia","Pontevedra":"Galicia",
    "Asturias":"Asturias","Cantabria":"Cantabria",
    "Álava":"País Vasco","Araba":"País Vasco","Bizkaia":"País Vasco","Vizcaya":"País Vasco","Gipuzkoa":"País Vasco","Guipúzcoa":"País Vasco",
    "Navarra":"Navarra","La Rioja":"La Rioja",
    "Huesca":"Aragón","Teruel":"Aragón","Zaragoza":"Aragón",
    "Barcelona":"Catalunya","Girona":"Catalunya","Lleida":"Catalunya","Tarragona":"Catalunya",
    "Burgos":"Castilla y León","León":"Castilla y León","Palencia":"Castilla y León","Salamanca":"Castilla y León","Segovia":"Castilla y León","Soria":"Castilla y León","Valladolid":"Castilla y León","Zamora":"Castilla y León","Ávila":"Castilla y León",
    "Madrid":"Madrid",
    "Albacete":"Castilla-La Mancha","Ciudad Real":"Castilla-La Mancha","Cuenca":"Castilla-La Mancha","Guadalajara":"Castilla-La Mancha","Toledo":"Castilla-La Mancha",
    "Alicante":"Comunitat Valenciana","Alicante/Alacant":"Comunitat Valenciana","Castellón":"Comunitat Valenciana","Castelló":"Comunitat Valenciana","Valencia":"Comunitat Valenciana","València":"Comunitat Valenciana",
    "Badajoz":"Extremadura","Cáceres":"Extremadura",
    "Murcia":"Murcia",
    "Almería":"Andalucía","Cádiz":"Andalucía","Córdoba":"Andalucía","Granada":"Andalucía","Huelva":"Andalucía","Jaén":"Andalucía","Málaga":"Andalucía","Sevilla":"Andalucía",
    "Illes Balears":"Illes Balears","Baleares":"Illes Balears",
    "Las Palmas":"Canarias","Santa Cruz de Tenerife":"Canarias",
    "Ceuta":"Ceuta","Melilla":"Melilla",
}

def find_province(text: str) -> tuple[str | None, str | None]:
    value=text or ""
    # Prefer explicit administrative location over incidental mentions in
    # company names, addresses or CCAA names such as "Castilla y León".
    candidates=[]
    for province,ccaa in PROVINCE_TO_CCAA.items():
        esc=re.escape(province)
        strong=[
            rf"provincia\s+de\s+{esc}\b",
            rf"provincia\s*[:\-]\s*{esc}\b",
            rf"\(\s*{esc}\s*\)",
        ]
        for pattern in strong:
            m=re.search(pattern,value,re.I)
            if m:
                candidates.append((m.start(),-len(province),province,ccaa))
                break
    if candidates:
        _,_,province,ccaa=min(candidates)
        return province,ccaa

    # Single-province autonomous communities: a regional authority in the
    # title is already sufficient geographic evidence and avoids picking
    # a promoter's notification address from the body.
    uniprovincial=[
        ("Principado de Asturias","Asturias","Asturias"),
        ("Gobierno de Cantabria","Cantabria","Cantabria"),
        ("Comunidad de Madrid","Madrid","Madrid"),
        ("Región de Murcia","Murcia","Murcia"),
        ("Comunidad Foral de Navarra","Navarra","Navarra"),
        ("Gobierno de La Rioja","La Rioja","La Rioja"),
        ("Illes Balears","Illes Balears","Illes Balears"),
        ("Islas Baleares","Illes Balears","Illes Balears"),
        ("Ciudad de Ceuta","Ceuta","Ceuta"),
        ("Ciudad de Melilla","Melilla","Melilla"),
    ]
    low=value.casefold()
    for marker,province,ccaa in uniprovincial:
        if marker.casefold() in low:
            return province,ccaa
    return None,None
