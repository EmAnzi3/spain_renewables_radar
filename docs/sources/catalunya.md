# Catalunya — public source discovery checkpoint

## Verified evidence, 4 October 2026

Probe: [37221339629 — SUCCESS](https://github.com/EmAnzi3/spain_renewables_radar/actions/runs/37221339629), code `e9b3043a5fe55111e3f801140a728f41d840171f`.

Artifact: `catalunya-public-probe-output`, ID `11310348543`, contains the complete original response bytes, acquisition URLs/times/SHA-256, rows, diagnostic groups, metadata and summary. Count and dataset-version checks were made before and after collection. No project or administrative event was created by this probe.

The datasets are linked directly by the [Generalitat environmental viewer](https://mediambient.gencat.cat/es/05_ambits_dactuacio/avaluacio_ambiental/energies_renovables/visor/index.html).

| Observation | Wind `dh5g-4nit` | PV `ggx8-jkp4` |
|---|---:|---:|
| Complete source rows | 137 | 358 |
| Exact application-reference + name groups, diagnostic only | 37 | 315 |
| Groups represented by multiple municipal rows | 14 | 28 |
| Rows without application reference | 78 | 4 |
| Rows with source power equal to zero | 50 | 37 |
| Exact duplicate rows | 0 | 0 |
| Groups with conflicting positive MW values | 0 | 0 |
| References used by different names | 0 | 1 |
| Latest environmental meeting date present | 2024-01-26 | 2026-08-06 |
| Meeting-dated rows in 2026-09-04 through 2026-10-03 | 0 | 0 |

Source dataset-update timestamps are **2026-09-28 08:47:13 UTC** for wind and **08:48:11 UTC** for PV. These timestamps concern the datasets, not individual projects, permits or publication dates.

Rows by source state, **not deduplicated project counts**:

- Wind: Autoritzat 10, En servei 78, En tramitació 27, No autoritzat 22.
- PV: Autoritzat 130, En servei 13, En tramitació 193, No autoritzat 21, Desistit 1.

## Material interpretation rules

1. A row can describe a project's municipality, rather than a distinct plant. Never count every row as a project or sum repeated project-wide MW. The same application/name may have one positive MW row and a secondary municipality row with zero. Preserve every original row and all municipality membership; do not present these zeros as zero-capacity plants.
2. An application reference alone is not always a unique plant identifier: the PV snapshot includes a reference associated with different names. Preserve explicit asset scope and keep ambiguous groupings in review. The diagnostic group counts above are not certified unique opportunities.
3. `data_pon_ncia` is an environmental-panel meeting date. It is not a web-publication date, construction authorization date or work start date. Current `estat` and `sentit_acord` are source assertions, not dated events to be manufactured.
4. `En servei` denotes an operating plant in the source. Do not put it among prospective construction opportunities merely because it was first downloaded today. Missing application references remain missing; they are not reconstructed from the promoter.
5. Use the top-level metadata whose `id` matches the requested dataset. The wind metadata response contains nested legacy information about another dataset; it must not overwrite the actual wind schema or data version. Preserve the raw response, but do not republish unrelated administrative account metadata in user-facing reports.
6. Snapshot staleness and incomplete temporal coverage must be visible. No recent `data_pon_ncia` entries does not mean there are no recent renewable projects or DOGC publications in Catalunya.
7. Source-reported nominal MW, land area and municipality fields remain separate. Owner/promoter is not EPC. A source snapshot must not overwrite an existing project's administrative lifecycle based only on approximate name matching.

## Next implementation boundary

The next module should persist a complete, repeatable snapshot with original evidence, deterministic scoped identities, municipality-level membership, explicit missing fields and changes relative to the preceding snapshot. The first snapshot is a BASELINE, not hundreds of new announcements. Current-state opportunities may be shown as an undated source inventory, separately from the dated administrative feed.

The dated DOGC publications require their own verified acquisition path and matching evidence; dataset timestamps cannot substitute for it. No Catalunya collector is enabled in `config/sources.json` by this checkpoint, and DOGC remains unimplemented. Official BESS or other additional datasets must be independently discovered and probed; coverage must not be inferred from the existence of the viewer.

## Official endpoints actually acquired

- `https://analisi.transparenciacatalunya.cat/api/views/dh5g-4nit.json`
- `https://analisi.transparenciacatalunya.cat/resource/dh5g-4nit.json?$select=count(*)`
- `https://analisi.transparenciacatalunya.cat/resource/dh5g-4nit.json?$limit=10000`
- `https://analisi.transparenciacatalunya.cat/api/views/ggx8-jkp4.json`
- `https://analisi.transparenciacatalunya.cat/resource/ggx8-jkp4.json?$select=count(*)`
- `https://analisi.transparenciacatalunya.cat/resource/ggx8-jkp4.json?$limit=10000`

The request limit is a bounded probe safeguard, not a silent pagination limit. A count at or above that limit, a changed source version, missing required fields or a count mismatch fails the probe.
