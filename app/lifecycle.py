from __future__ import annotations

def classify_event(text: str) -> str:
    t=" ".join((text or "").casefold().split())
    if any(x in t for x in ("se desestima","desestima la solicitud","deniega","denegación","denegacion")):
        return "DENIED"
    if any(x in t for x in ("desistimiento","se tiene por desist","renuncia")):
        return "WITHDRAWN"
    if any(x in t for x in ("levantamiento de actas previas","actas previas a la ocupación","actas previas a la ocupacion","actas de pago","levantamiento de actas de pago")):
        return "EXPROPRIATION"
    if any(x in t for x in (
        "modificación del proyecto","modificacion del proyecto",
        "modifican las condiciones de la declaración de impacto ambiental",
        "modifican las condiciones de la declaracion de impacto ambiental",
        "modificación de la instalación","modificacion de la instalacion",
    )):
        return "MODIFICATION"
    # A public-information notice can mention DIA/AAP/AAC/DUP as the object
    # of the request. It is not the grant of those milestones.
    if "información pública" in t or "informacion publica" in t:
        return "PUBLIC_INFO"
    if ("declaración" in t or "declaracion" in t) and "impacto ambiental" in t:
        return "DIA"
    if "autorización administrativa de construcción" in t or "autorizacion administrativa de construccion" in t:
        if any(x in t for x in ("otorga","concede","autoriza")):
            return "CONSTRUCTION_AUTH"
    if "autorización administrativa previa" in t or "autorizacion administrativa previa" in t:
        if any(x in t for x in ("otorga","concede","autoriza")):
            return "PRIOR_AUTH"
    if "utilidad pública" in t or "utilidad publica" in t:
        if any(x in t for x in ("declara","otorga","concede")) and "solicitud" not in t:
            return "PUBLIC_UTILITY"
    return "OTHER"

def commercial_stage(event_type: str) -> str:
    if event_type in {"DENIED","WITHDRAWN","PROCEDURE_ENDED"}:
        return "BLOCKED"
    if event_type=="EXPROPRIATION":
        return "PRECONSTRUCTION"
    if event_type in {"CONSTRUCTION_AUTH","PUBLIC_UTILITY"}:
        return "AUTHORIZED"
    if event_type in {"PRIOR_AUTH","DIA","MODIFICATION"}:
        return "PERMITTING"
    return "EARLY"

STAGE_RANK={"BLOCKED":-1,"EARLY":0,"PERMITTING":1,"AUTHORIZED":2,"PRECONSTRUCTION":3}
