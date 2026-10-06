# DOCM — battery-addition scope and reviewed legacy repair

## Verified case

Official HTML consulted: `https://docm.jccm.es/docm/verArchivoHtml.do?ruta=2026%2F10%2F05%2Fhtml%2F2026_7037.html&tipo=rutaDocm`.

Document **DOCM-2026-7037**, publication **2026-10-05**, dossier **13270209226**. The source describes an application for a battery addition to an existing PV plant. The source HTML itself states that the signed PDF is the authentic legal version; the collector preserves the consulted official HTML and its URL and does not claim to have reverified the signed PDF in this repair.

Correct interpretation: **BESS Almagro I**, **7.2 MW battery active power**, Almagro / Ciudad Real / Castilla-La Mancha, PUBLIC_INFO / EARLY. Existing PV **7.4 MW** and post-hybrid total **14.6 MW** are not the battery capacity. **5.016 MWh per container**, apparent power and access power remain separate. No construction dates or EPC are inferred.

## Implementation

Functional commit **61f98ce053d8dc3527d6f03d7e6f9446747595e4**. `app.docm_storage.storage_evidence` requires an explicit battery-addition title, a uniquely named technical block and an unambiguous active-power statement inside that block. It uses source wording rather than a lookup of document IDs. Missing, repeated or conflicting blocks cannot borrow the existing PV capacity. Exact quantity spans and the original raw-text digest are retained.

The collector applies `project_storage` after its existing general parser. The project identity remains stable via the source dossier. INE fallback supports singular and plural municipality phrases; it does not use the promoter address and does not overwrite validated multi-province evidence.

## Controlled correction of previously stored data

The migration is **not** driven by a generic quality flag. Only the reviewed original with SHA256 **ba5450fe79437e90326a3082f63b76b0ed0af7a887c099bc833c9a6143019a65**, the exact old values and a single-event project can be repaired automatically. It creates a SQLite backup, logs the previous event/project projection and uses one transaction. Unknown prior state, changed source or a shared project stops for review.

Invariant fields: event ID, source code, external ID, project key, publication date, title, source URL, raw text and creation timestamp. Lifecycle is not modified. Event geography remains source-specific; INE enriches the project separately. A second execution performs zero further corrections. Read-only `validate_docm_storage` checks the resulting projection and metadata against the source.

On a local copy of the previous full-run database, only project **822a676aca030c14a431** changed: name, HYBRID→BESS, 7.4→7.2 MW and missing province→Ciudad Real. The immutable-event fingerprint remained **9fad6c796e87080b41432b4ba2559be33349b26eeebb38c0f3624a13703e5f85**. This is migration testing, not a new thirteen-source live acquisition.

## Validation

**37420987930 — SUCCESS**, code **b9752fcc8b5f492bc97f03ccdf83b1857de1b039**, window **2026-09-06–2026-10-05**: **30 DOCM days, 18 projects/events, zero source-day errors, zero structural errors**. The artifact database and source replay confirm the corrected fields and idempotency. Artifact **11392454466**, **78,157 bytes**, SHA256 **ecd62b74531b5a322e8ee4ba1e3c594b9b96c94bda8681f0f47ba986a52fea6e**, downloaded and checked.

The ordinary suite contains **530 tests**, including **22 new DOCM regressions**. The separate full run **37418379045** remains unsuccessful because GVA failed during smoke; the DOCM-only gate is explicitly labeled **DOCM_ONLY_NOT_THIRTEEN_SOURCE_CERTIFICATION**.
