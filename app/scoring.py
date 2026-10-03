from __future__ import annotations

from datetime import date

STAGE_POINTS = {
    "EARLY": 5,
    "PERMITTING": 20,
    "AUTHORIZED": 32,
    "PRECONSTRUCTION": 40,
    "BLOCKED": 0,
}


def _mw_points(power_mw):
    if power_mw is None:
        return 0
    if power_mw >= 100:
        return 20
    if power_mw >= 50:
        return 16
    if power_mw >= 10:
        return 10
    return 5


def _age_points(last_seen, as_of):
    if not last_seen:
        return 0, None
    try:
        seen = date.fromisoformat(str(last_seen)[:10])
    except ValueError:
        return 0, None
    age = max((as_of - seen).days, 0)
    if age <= 30:
        return 10, age
    if age <= 90:
        return 6, age
    if age <= 180:
        return 3, age
    return 0, age


def score_project(
    project,
    *,
    event_types=(),
    ree_context_available=False,
    epc_status="EPC_UNKNOWN",
    work_window_known=False,
    as_of=None,
):
    """Commercial priority score; it never mutates administrative lifecycle."""
    as_of = as_of or date.today()
    stage = project.get("commercial_stage") or "EARLY"
    if stage == "BLOCKED":
        return {
            "score": 0,
            "priority": "BLOCKED",
            "epc_status": epc_status,
            "age_days": None,
            "components": {"lifecycle": 0},
        }

    components = {
        "lifecycle": STAGE_POINTS.get(stage, 0),
        "mw": _mw_points(project.get("power_mw")),
    }

    event_types = set(event_types or ())
    if "EXPROPRIATION" in event_types:
        components["advanced_milestone"] = 15
    elif "CONSTRUCTION_AUTH" in event_types:
        components["advanced_milestone"] = 12
    else:
        components["advanced_milestone"] = 0

    age_pts, age_days = _age_points(project.get("last_seen"), as_of)
    components["recency"] = age_pts

    technology = project.get("technology")
    components["technology"] = 5 if technology in {"BESS", "HYBRID"} else (3 if technology in {"PV", "WIND"} else 0)
    components["ree_context"] = 5 if ree_context_available else 0
    components["work_window"] = 5 if work_window_known else 0

    # EPC unknown is only a small commercial signal: the contracting slot may
    # still be addressable. The EPC enrichment layer will refine this later.
    components["epc"] = 5 if epc_status == "EPC_UNKNOWN" else (2 if epc_status == "EPC_CANDIDATE" else 0)

    score = min(sum(components.values()), 100)
    if score >= 70:
        priority = "A"
    elif score >= 50:
        priority = "B"
    elif score >= 30:
        priority = "C"
    else:
        priority = "D"
    return {
        "score": score,
        "priority": priority,
        "epc_status": epc_status,
        "age_days": age_days,
        "components": components,
    }
