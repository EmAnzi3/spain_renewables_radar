# Catalunya — repeatable official inventory

Checkpoint: **2026-10-05 Europe/Rome**. This is a standalone inventory, not a dated project-event collector.

## Official source and original discovery

The Generalitat environmental portal links both datasets:

- Origin: `https://mediambient.gencat.cat/es/05_ambits_dactuacio/avaluacio_ambiental/energies_renovables/visor/index.html`
- Wind: `dh5g-4nit`, Parcs eòlics de Catalunya.
- Photovoltaic: `ggx8-jkp4`, Plantes solars fotovoltaiques a Catalunya.
- Dataset API host: `analisi.transparenciacatalunya.cat`.

Historical discovery run **37221339629 — SUCCESS** acquired the complete datasets, not only sample rows. The retained probe found 137 wind rows and 358 PV rows, with source update times 2026-09-28T08:47:13Z and 2026-09-28T08:48:11Z respectively. Some wind metadata contained nested legacy PV metadata: only matching top-level dataset identity, fields and version are interpreted. Nested legacy information and contact details are not used as project evidence.

The PV dataset's declared scope is ground-mounted plants above 100 kW nominal, including projects in processing and operation; operational coverage has its own historical limitations. Do not interpret this inventory as all Spanish renewable projects or all construction opportunities.

## Implemented module and live validation

- Module: **`app/catalunya_inventory.py`**.
- Windows launcher: **`aggiorna_inventario_catalogna.bat`**.
- Functional commit: **b9e0cb7076c84743ace93c658979f20af60c07dc**.
- [Validation run **37241609997 — SUCCESS**](https://github.com/EmAnzi3/spain_renewables_radar/actions/runs/37241609997), job **111551279565**.
- **242 unit/regression tests passed in that run**, followed by two independent live acquisitions with page size 100, before/after source count/version checks, original-byte reconstruction, baseline/delta verification and idempotent replay.
- [Artifact **11317693006**, `catalunya-inventory-output`](https://github.com/EmAnzi3/spain_renewables_radar/actions/runs/37241609997/artifacts/11317693006).
- Artifact SHA256: `b9f1361f7dc9bcad1f3aa5dda633015befc26e98d0e224841b3f927ad7833ee8`.
- Original certification: `reports/catalunya_inventory_validation/certification.json` in the artifact.
- Checked summary: `docs/validation/2026-10-05-catalunya-inventory.json` (explicitly a verified log-derived summary, not a byte-identical artifact copy).

Acquisition timestamps are preserved as **2026-10-04T22:51:50.223538+00:00** and **2026-10-04T22:51:55.947367+00:00**, both on October 5 in Europe/Rome. Both produced semantic content hash `11eae40638bd7b3a78f1da3b5bf54b6f1dd2430dfd88d012d45fd7d964c628e4`. First mode BASELINE; second DELTA with **zero newly observed, changed or not-seen groups**. No project events were created.

| Inventory measure | Wind | PV |
|---|---:|---:|
| Original municipal rows | 137 | 358 |
| Diagnostic groups, including unresolved rows | 115 | 319 |
| Exact reference-and-name groups | 37 | 315 |
| Unreferenced rows kept separate | 78 | 4 |
| Groups spanning multiple municipal rows | 14 | 28 |
| Groups without determinable positive capacity | 28 | 0 |

**495 municipal rows and 434 diagnostic groups are not a certified unique-project count.** In particular, 82 rows lack a reference and are not merged just because names resemble one another. One PV reference is used for two different names: both groups remain separate and flagged.

## Acquisition contract

The module rechecks that the official environmental page still links both dataset identities. It validates top-level metadata and the field types, retains all reported columns and uses the actual accepted SoQL projection:

```text
$select=:id AS socrata_row_id, <explicit official column names>
$order=:id
$limit=<bounded page size>
$offset=<page offset>
```

The originally attempted trailing wildcard projection was rejected by the service and corrected using observed error/response evidence. A regression test protects the accepted explicit-column form. New valid source columns remain included; unsafe or colliding identifiers cause failure.

The collector checks exact page lengths, unique source row IDs across pages, total row count, and metadata/count stability after acquiring both datasets. It stores original bytes with SHA256, request URL and real retrieval time. The verification step reconstructs rows from those original pages and validates the complete count/version proof, rather than trusting generated reports alone.

Transport has bounded retries and size limits. Redirects or non-public/unexpected destinations require review. An HTTP 403 is not retried or bypassed. A response/contract error is not a valid empty dataset.

## Identity, quantities and dates

Grouping uses **dataset + exact administrative reference + exact name**. Without a reference, a source row remains a separate unresolved record. Technical Socrata row IDs are preserved as provenance but excluded from semantic comparison because a publisher can replace rows without changing their content. Source field changes are not silently ignored.

All municipalities and original municipal values are retained. Province attribution uses the source municipality code prefix only when its format is valid; unresolved codes are flagged. A promoter address is not used as the plant location.

Repeated total plant MW, total site area and total turbine count are counted once within an exact group, not summed across municipalities. Distinct conflicting positive values remain unresolved. Source zeros remain in the original rows, and an unknown positive project capacity is not published as zero capacity. Municipal area/turbine figures remain separate from plant totals.

State labels are source assertions, not freshly issued permits. `data_pon_ncia` is an environmental meeting date, not a publication date. Dataset modification times are not individual-project publication times. Publication date, authorization date, work start/end and EPC contractor remain unset. Operating plants are not relabeled as new construction opportunities.

## Persistence and reports

```bat
aggiorna_inventario_catalogna.bat
```

Or, using the configured project environment:

```bat
.\.venv\Scripts\python.exe -m app.catalunya_inventory
```

Default report: `reports/catalunya_inventory/index.html`.
Default state: `data/catalunya_inventory_baseline.json`.
Last attempt status: `reports/catalunya_inventory/run_status.json`.

Each timestamped snapshot retains `inventory.json`, `inventory.csv`, `index.html`, `changes.json`, `metrics.json` and original response files. HTML escapes source text; CSV protects against formula interpretation. The report provides text search over names, municipalities and references.

The baseline is protected by an exclusive writer lock and atomic JSON replacement. Failed acquisition/validation does not replace the last valid baseline. Each completed snapshot is independently retained. The launcher opens the report only after success. Read `run_status.json` to distinguish a failed latest attempt from an older valid report. There is no new scheduler or automatic public-dashboard publication.

BASELINE means initial inventory, not new opportunities. DELTA reports newly observed/changed/not-seen records; NOT_SEEN does not prove withdrawal. Changes to unreferenced rows can appear as disappearance plus a newly observed row because a safe project identity is missing; no false identity continuity is invented.

## Boundary with the dated DOGC collector

This inventory module does **not** itself create dated events. The independent **DOGC collector is now implemented and included in the thirteen-source ordinary pipeline**, validated by integrated run **37350555017** on code **ca598cc0f1e685652c6af58c83c85f6186fafd9e**. The daily-index reconciliation and semantic classification have been completed; see `dogc.md` and `../validation/2026-10-05-thirteen-source.json`. The former statement that DOGC reconciliation remained unresolved is superseded.

The completed DOGC collector does not turn this inventory's dataset or meeting dates into project publication dates. Linking inventories to dated events still requires official document identity or exact reference evidence and separate validation. No automatic fuzzy cross-source merge was added.
