from __future__ import annotations

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
PROVINCES = sorted(PROVINCE_TO_CCAA, key=len, reverse=True)

def find_province(text: str) -> tuple[str | None, str | None]:
    low=(text or "").casefold()
    for province in PROVINCES:
        if province.casefold() in low:
            return province, PROVINCE_TO_CCAA[province]
    return None, None
