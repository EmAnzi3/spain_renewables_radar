# National historical backfill — evidence checkpoint, 15 October 2026

Branch: `feat/national-historical-backfill`. Approved window: **2024-10-01 through 2026-09-30**.
This checkpoint concerns the historical work branch, not publication or the operational database. No main merge, operational database replacement or website publication was performed. BOE 24-month completion was reported in the preceding checkpoint; its 24 artifacts were not re-audited in this session.

## Regional campaign actually started

[Run 38696867124](https://github.com/EmAnzi3/spain_renewables_radar/actions/runs/38696867124), code `b28874221a7f32fac67ffc4a64a9e4cbdb777b87`.

Workflow `.github/workflows/regional-historical-24-months.yml`, planner/auditor `scripts/regional_historical_campaign.py`. Eight sources: BOA, BOCYL, DOCM, DOE, BORM, BOCM, DOG, DOGC. This is a matrix of **192 source-months**, not 192 projects, and not all 17 autonomous communities.

The workflow tests every source in October 2024 and September 2026. After the pilot matrix finishes, original artifact verification unlocks the remaining 22 months independently for each source whose TWO pilots verify. A failed source does not cancel other sources. At most two regional collection jobs run simultaneously. The final audit records every expected month as VERIFIED, INCOMPLETE, INVALID_EVIDENCE or NOT_ATTEMPTED and fails on gaps. Missing months have null event counts, never zero.

The workflow does not merge or publish databases. Even a complete 192-cell result must retain `nationwide_historical_24_months_complete=false`. Inventory sources and unimplemented regions require their separate workflows/evidence.

## Four downloaded regional artifacts independently verified

Verification completed at **2026-10-15T07:19:30Z**. Original ZIP bytes and GitHub artifact digests matched. Safe extraction was followed by read-only SQLite integrity/foreign-key checks, exact source/event identity and counts, source-date bounds, immutable event evidence digest, complete daily coverage, quality counts, and every original report SHA256/inventory. **All checks passed**, with 12 original reports verified per shard.

| Source | Month | Artifact ID | Events | Projects in that shard | Source days OK | ERROR/WARN/INFO |
|---|---|---:|---:|---:|---:|---|
| BOA | 2024-10 | 11954826603 | 67 | 65 | 31/31 | 0/4/76 |
| BOA | 2026-09 | 11954741543 | 20 | 20 | 30/30 | 0/1/22 |
| BOCYL | 2024-10 | 11954526652 | 37 | 37 | 31/31 | 0/9/44 |
| BOCYL | 2026-09 | 11954976795 | 37 | 34 | 30/30 | 0/6/49 |

**161 administrative source events and 122 source-days** across these four shards. These are not 161 nationally deduplicated projects. No project total across months/sources has been certified. Field-quality warnings remain to be reviewed; structural PASS does not mean all promoters, powers or locations are known.

All four artifacts belong to run `38696867124`, head `b28874221a7f32fac67ffc4a64a9e4cbdb777b87`, attempt 1, names `regional-historical-SOURCE-MONTH-attempt-1`.

| Source/month | ZIP bytes | ZIP SHA256 | SQLite SHA256 |
|---|---:|---|---|
| BOA/2024-10 | 1125703 | 29c368bf9c5feeddac147df00297cff4c9c9a3f400da9ac088be89d748ec82a4 | a2f35ae97db228bfce52db80da557e92c3e1096c796eec845b32934a0f036a5d |
| BOA/2026-09 | 137100 | 091113ffd250701e1bb74883c9ce105cbcc632d96d178ae136148149475da35c | 619afcb5c8edd954b47546c8a56f16b1ee4b5ed6c0f93f0e38415f0d836b81e8 |
| BOCYL/2024-10 | 380506 | 529d842294b211a03c1311041f030501353b0a3948dc9dfd4d70334a3cd74261 | 76b3f4d9f94068ce1169a5d55224ec65b8e05897b2381675ebcac93c8b3b6f15 |
| BOCYL/2026-09 | 290220 | 69b09f02f080983e1e024481280f07b4639e97ddb3398d1848a1b5ce83e902da | 2bde50979e768e2bf28235287d951971a84013af637a7197a67fc123a5c9274b |

At the subsequent job-status read, DOCM and DOE September 2026 also had successful collection/upload steps, but their artifacts were NOT independently inspected in this session. DOCM, DOE and BORM October 2024 failed the acquisition step; their precise original errors still need diagnosis. Other pilots were running or queued. Do not extrapolate old-month failures from current-month success.

## BOJA: two distinct corrections and run scopes

1. Calendar fix + full replay: commit `1688189cd1fd525bbeffeb10e272a1dbaff8b5e9`, [run 38695997494](https://github.com/EmAnzi3/spain_renewables_radar/actions/runs/38695997494). This run does NOT contain the later transport/original-detail fix.
2. Transport and evidence fix: commit `6d5025c95fa85db63de563c68723319e3aac9fb5`. Bounded GET retries for transient connection/status failures; no conversion of HTTP400 into unverified zero-publication days, no bypass of restricted texts. Removed the catch-all fallback that substituted search metadata for a failed original detail request; missing identity, empty original text and exhausted network errors now remain explicit failures.
3. Full suite [run 38697414608](https://github.com/EmAnzi3/spain_renewables_radar/actions/runs/38697414608) SUCCESS. Live pilot [run 38697414742](https://github.com/EmAnzi3/spain_renewables_radar/actions/runs/38697414742) SUCCESS for BOJA and BOE July 2026 on the same `6d5025c9` code. BOJA job `116297236518` log confirms **683 tests PASS**, **7 events / 7 projects**, **31/31 source-days**, **0 failed days**, **0 ERROR / 1 WARN / 9 INFO**, no restricted bodies. The live original event digest remains `37f0e028fc21f95c0dd41b6082242f21920b0076ee390868a2656813d395be3d`.
4. Strict-body full replay queued: commit `dabd879d0c37a5912653e66fe730e572a0c1260c`, [run 38698193489](https://github.com/EmAnzi3/spain_renewables_radar/actions/runs/38698193489), observed PENDING behind the calendar-only campaign. Same concurrency group prevents parallel BOJA campaigns. Artifacts now use `boja-historical-MONTH-attempt-N`, preserving originals during reruns.

The 21 new tests comprise 15 campaign/provenance/digest tests and six BOJA transport/original-detail tests. The full 683-test suite was run on GitHub; local work tested those focused additions rather than the complete repository.

### Proven October 2024 BOJA gap

Old full-run job `116292580733` (run 38695997494) retained **4 events**, **30/31 days**, **3 restricted official bodies**, `certified=false`, `historical_body_coverage=PARTIAL_RESTRICTED`.
Failed day: **2024-10-05**, `Connection aborted / RemoteDisconnected`. The later bounded-retry fix addresses this class of transient transport failure, but only a new original acquisition can establish recovery. Restricted bodies are an independent limitation and must not be manufactured, inferred from summaries or retried endlessly.
Original failed artifact ID `11954490162`, 74551 bytes, ZIP SHA256 `1abb4254b816840b8cea57aa062b40ad49cca30d910f3830bd2d01c561c0aa9f`, SQLite SHA256 `6df7cee68e8fa655926abfddd47801b33783d04d5e9d8aac89f28a7348debd34`. These metrics and hashes were read from the job log, not independently verified by downloading that failed ZIP in this session.

## Continuation priorities

- Refresh actual branch head and run states before acting. Let the active regional campaign finish pilots and automatic continuation; do not launch duplicate full campaigns merely because it is running.
- Prefer the strict-body BOJA replay for final evidence. Never claim older pinned runs include a newer correction; rerunning a failed job uses its original revision. Keep source restrictions explicit and preserve valid observations separately from incomplete source-month certification.
- Diagnose original failed regional manifests/collector logs, especially DOCM/DOE/BORM October 2024. Retry bounded transient failures only; fix demonstrated collector/parse/archive-scope defects with focused regression tests and live proof. Check BORM annual-index scope rather than accepting an empty historic search as zero projects.
- Verify remaining artifact originals, preserve dated run/SHA/hash receipts and update coverage. Recover only missing/invalid scope; do not overwrite original artifacts or the operational database.
- After sufficient verified acquisition, produce a separate consolidated candidate with identity conflict review, event-level provenance, cross-source project deduplication and explicit promoter/power/location quality metrics. Preserve restricted and unresolved notices as leads, not verified permit/project facts.
- Full national certification remains **NOT achieved**. Nine implemented regional bulletin collectors are not all 17 autonomous communities. Preserve official/free-only scope, no fabricated EPC/promoter/power/municipality/date, MW versus MWh and source inventory dates versus administrative publication dates.
