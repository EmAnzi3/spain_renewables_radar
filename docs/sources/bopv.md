# BOPV — official dated index reconciliation

Checkpoint **2026-10-06**. **BOPV remains disabled** in the ordinary registry. This module creates no project or administrative event.

## Completed acquisition evidence

Run **37420987792 — SUCCESS**, code **b9752fcc8b5f492bc97f03ccdf83b1857de1b039**. Window **2026-09-06–2026-10-05**:

- **306 unique dispositions**, all **31 pages** of the official publication-date search;
- calendars for both months and every summary of the **21 published editions**;
- all **30 days** accounted for, including **nine source-declared no-edition days**;
- complete equality of disposition identities and titles, with **zero omissions and conflicts**;
- **five candidate HTML bodies**, publication mastheads, identities, titles and edition numbers verified;
- original-byte receipts preserved; downloaded archive checked and **62 original responses** hashed locally, with all summaries rebuilt and compared.

Artifact **11393276447**, **753,694 bytes**, SHA256 **35f211924f8309c2b14a8e7d6990cbd70ee86e77d076db97671ffb7d9bd8a885**. Earlier source discovery runs **37402681950** and **37405285898** remain historical evidence; the new run adds complete index reconciliation. Tests: ordinary suite 530, plus **26 BOPV contract tests**.

## Actual source contract

Source host **www.euskadi.eus**, official BOPV entry point `/bopv2/datos/Ultimo.shtml`. Month calendars expose literal Spanish `diasHabilitados` and `enlaces` arrays, explicit year/month and edition basenames. Edition pages are requested in the observed year/month directory and independently checked against their own masthead and signed-PDF link. Days are not guessed from weekdays. Unexpected structure or missing coverage fails rather than returning an empty success.

Summary source IDs and displayed disposition numbers must agree. Spanish article paths use `/bopv2/datos/YYYY/MM/YYNNNNNa.shtml`; the search emits an equivalent `/web01-bopv/es/` prefix. The exact observed presentation flags `BOPV_NOT_IN_PORTAL`, `BOPV_HIDE_CALENDAR`, `R01HNoPortal=true` are permitted without altering the saved URL. Unknown, duplicated or changed parameters are rejected.

Historical pages reuse the masthead CSS class for sidebar search headings: only one actual edition masthead is accepted. Inline superscript markup is extracted without inserting false spaces inside units such as m3/año. This changes text extraction, not source wording; raw HTML remains intact, and changed quantities/titles still fail comparison.

The search and summaries are separate source representations, not two independent publishers. The reconciliation validates the acquired index in this window; it is not proof that every renewable opportunity appears in title-keyword selection or that every future edition will have identical structure.

## Candidate scope to implement next

The five verified original publications are:

| Source identity | Publication date | Subject to classify |
|---|---|---|
| 2026/04004 | 2026-09-24 | Hernani I–II cluster; two parks require separate identities and owner evidence |
| 2026/03989 | 2026-09-23 | Regina Solar and Nova Solar; separate project sections and dossiers |
| 2026/03988 | 2026-09-23 | Coalsema; industrial self-consumption, existing cogeneration, PV and BESS components |
| 2026/03987 | 2026-09-23 | Pe Pando; public information, not an authorization grant; do not invent an expediente |
| 2026/03902 | 2026-09-16 | Mendi environmental decision; full operative conditions must remain distinct from construction authorization |

These are **five administrative publications, not five unique project opportunities**. The bodies have been read for development scoping, but a reusable semantic classifier, per-project projection and collector validation are not yet complete. Do not publish inferred scalar MW, EPC assignments or construction dates. Supplier/model references are not EPC contract evidence. Coalsema's self-consumption/multi-component scope must be handled explicitly rather than silently excluded or combined.

## Code and output

`.github/scripts/reconcile_bopv_index.py` and `.github/scripts/probe_bopv_dates.py`, with dedicated workflow `.github/workflows/bopv-index-reconciliation.yml`. Source-contract tests stay in `.github/tests/test_bopv*.py`, separate from the dependency-free runner-recovery policy tests.

Artifact folders: `bopv_date_probe/` (search pages, original bodies and source receipts) and `bopv_reconciliation/` (calendar/summary originals, all dispositions, 30-day coverage, candidate date checks and audit). The audit explicitly retains `collector_implemented=false`, `events_created=0`, `source_semantics_validated=false`.

Next steps: source-scoped semantic rules and regression fixtures; separate multi-project identity and quantity handling; actual daily collector; live smoke and thirty-day backfill; integrated validation with all existing sources before activation. No new source was enabled by this checkpoint.
