# DOGC — verified service contracts, incomplete independent index reconciliation

Checkpoint: **2026-10-05 Europe/Rome**. **DOGC is not enabled as a dated collector. No DOGC project/event was inserted.**

## Evidence layers and status

| Layer | Observed result | Scope |
|---|---|---|
| Official navigation scripts | Run 37221624700 SUCCESS | Historical route discovery only |
| Actual service responses | Run 37241609987 SUCCESS | Monthly calendars, edition summaries and first search page |
| Full dated index audit | Run 37242571670 FAILURE | Calendar/edition traversal completed; search pagination repeated documents |
| Pagination diagnostics | Run 37242677858 SUCCESS | Original repeated IDs verified; request contract matches site JavaScript |
| Official full-search CSV probe | Run 37242776975 FAILURE | Read timeout; no export body acquired |

The checked summary is `docs/validation/2026-10-05-dogc-checkpoint.json`. It is a log-derived checkpoint, not a byte-identical copy of original artifact reports. A successful diagnostic is not a certified collector or complete coverage.

## Public hosts and read-only operations

Website: `https://dogc.gencat.cat`.
Service: `https://portaldogc.gencat.cat`.

The service host comes from the website's linked `constants.js` (`HOST_PRO`), not from an invented endpoint. Homepage hidden input fields corroborate calendar and search routes. The probe never invokes account, save-search or document-write functions.

Observed POST form operations:

```text
/eadop-rest/api/dogc/calendarDOGC
  month=<1-based month>, year=<year>, language=ca
/eadop-rest/api/dogc/summaryLastPublishedDOGC
  language=ca
/eadop-rest/api/dogc/summaryDOGC
  numDOGC=<number obtained from official calendar>, language=ca
```

Search uses JSON POST to `/eadop-rest/api/dogc/searchDOGC`, with explicit publication-date bounds, empty search words/descriptors, `current=false`, `noCurrent=false`, language `ca`, `orderBy=3`, page number and 50 results per page. No active-only filter is applied. The public JavaScript increments `inputParameters.page` and submits the same criteria; it does not use the returned search ID as a pagination cursor. That ID is used for source-provided downloads and saved-search operations.

## Verified TLS compatibility

The production service initially failed the default Python TLS handshake. A bounded transport audit identified a compatible standard cipher selection. `VerifiedDOGCTLSAdapter` uses `ssl.create_default_context()`, minimum TLS 1.2, security level 2, and:

```text
DEFAULT:!aNULL:!eNULL:!EXPORT:!RC4:!3DES:@SECLEVEL=2
```

Certificate and hostname checks remain enabled and are covered by regression tests. No `verify=False`, insecure curl option, obsolete TLS protocol or security-level downgrade is used. The adapter is mounted only for the observed DOGC service host.

## Actual service probe

Functional commit: **b9e0cb7076c84743ace93c658979f20af60c07dc**.
[Run **37241609987 — SUCCESS**](https://github.com/EmAnzi3/spain_renewables_radar/actions/runs/37241609987), job **111551279732**.
Artifact **11316863155**, `dogc-service-contract-output`.
Artifact SHA256: `74890e3dab0403fab010c66cbba9963e69b8bd65dcaa2fdfe3dc7be39c6476b2`.

The search declared **1,525 results** in the complete Spanish-day window **2026-09-05 through 2026-10-04**, but this probe downloaded only the first **50** search rows. Absence of an energy title in that first page is not absence of relevant publications in the window.

## Dated edition acquisition and annex handling

Current index-audit script: `scripts/audit_dogc_index.py`.
Current functional commit: **2f9ed2b8834572659bf0c158506885b6de6806f9**.
Tests: `tests/test_dogc_index_audit.py` (**26 focused cases**); the full run passed **268 unit/regression tests** before attempting live acquisition.

[Run **37242571670 — FAILURE**](https://github.com/EmAnzi3/spain_renewables_radar/actions/runs/37242571670), job **111554040872**.
[Artifact **11318310090**, `dogc-dated-index-output`](https://github.com/EmAnzi3/spain_renewables_radar/actions/runs/37242571670/artifacts/11318310090).
SHA256: `384c1dbe9469351661368d87cde2fe483e8144603860e049548fcf0fbafacf7e`.

The audit traversed **all 30 calendar days**, acquiring summaries for **20 principal editions and three same-day official annexes**: `9747A`, `9755A`, `9759A`. The other ten days had no edition according to the calendar. Weekend publication is allowed when the official calendar says so; weekday heuristics are not used.

A summary response may contain its principal edition and annexes. Accepted annexes must have the exact base number plus a single letter, the matching `Annex X` title, the same verified publication date and a corroborating official PDF download link with that exact `dogcId`. Principal edition presence is required. Duplicate headers, wrong dates/links, unrelated editions and unreadable titles fail validation. Each disposition retains principal/annex scope independently; no annex is silently dropped or relabeled as the principal edition.

The saved `edition_index.json` and raw responses are partial evidence. **They do not mean the independent whole-index gate passed.** PDF URLs were indexed but document bodies were not downloaded or interpreted in this work block.

## Precise remaining failure: repeated search results

The search service reported 1,525 rows. Requests for pages 1–5 each returned 50 rows. Page 5 repeated seven IDs already observed:

```text
1055509
1055510
1055513
1055514
1055515
1055516
1055518
```

The audit stopped rather than removing duplicates and claiming completeness: duplicates can conceal omitted results. `search_index.json`, final reconciliation and the energy candidate list were not completed by this failed run. No number of unique energy projects or relevant notices has been certified.

[Diagnostic **37242677858 — SUCCESS**](https://github.com/EmAnzi3/spain_renewables_radar/actions/runs/37242677858), job **111554341716**, downloaded the preceding audit's artifact, checked its raw hashes, confirmed the repeated IDs and read the public JavaScript pagination contract. Requests matched that contract. The service's internal reason for repeated results remains unknown; unstable ordering is a possible explanation, not an established fact.

Diagnostic artifact: **11318380143**, `dogc-pagination-contract-output`.
SHA256: `fcacedfa67b85ccdd09d3a0903aa2b201c3d338cd55138bcf9b1320fd2f6b2c9`.

## Whole-search CSV alternative: attempted, not acquired

[Probe **37242776975 — FAILURE**](https://github.com/EmAnzi3/spain_renewables_radar/actions/runs/37242776975), job **111554626159**, code **a3491f9e3b23a731dd2be879303c93242d62f615**.

A fresh search returned HTTP 200 and an official `urlCSVDownloadSearch`. The probe validated HTTPS, host `portaldogc.gencat.cat`, path `/utilsEADOP/AppJava/ExcelProviderServlet`, matching returned `idSearch`, `portal=dogc` and `typeDownload=csv`. It then requested that exact URL with certificate verification, redirect checks and a size limit.

The export GET raised **ReadTimeout after 40 seconds** before a usable response body was received. **No CSV was acquired, no schema was verified and no export parser was integrated.** This was a timeout, not evidence of an authorization denial.

Artifact **11317908762**, `dogc-pagination-contract-output`, contains the successful search-response bytes only. SHA256: `fb25b144ad83ffcda729db53da607931361e2c3f113ee3e3cc0aba088530c583`.

## Next implementation boundary

Resolve deterministic full-search acquisition and reconcile it to the complete dated edition set. Candidate approaches to verify, not implemented guarantees: the returned whole-search export with an explicit bounded timeout/retry budget, or non-overlapping official search partitions with independent count/identity reconciliation. Do not add a guessed pagination cursor, relax duplicate detection or call a failed attempt zero results.

If choosing a narrower summaries-only acquisition contract instead, explicitly document and validate that scope with repeatable original acquisition; do not label it as the missing independent search comparison.

Only after the index contract is validated: acquire relevant original document bodies, distinguish current operative decisions from historical recitals, split genuinely separate projects, extract fields with source evidence, link to the Catalunya inventory by official document/exact reference, then run parser tests, live smoke and full backfill before enabling the collector.

The standalone Catalunya inventory is already validated and must remain separate. No dates, capacity, permits, contractors or cross-source matches may be invented to fill the remaining DOGC gap. The production registry still has **12 operational collectors**, not 13.
