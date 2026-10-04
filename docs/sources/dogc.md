# DOGC — public navigation checkpoint, 4 October 2026

## Evidence acquired

[Run 37221624700 — SUCCESS](https://github.com/EmAnzi3/spain_renewables_radar/actions/runs/37221624700), code `adf38e1386bb91e73748b8403bf26a06e5266a40`, retrieved the official homepage and all six expected, publicly linked navigation scripts. Artifact **11310224498**, `dogc-public-navigation-probe-output`, contains original bytes and retrieval/hash audit.

The earlier navigation probe found the homepage but selected no application scripts. It was replaced with explicit checks for the expected linked asset names, so an empty script selection is not accepted as completed navigation analysis.

**This is not a DOGC collector or a thirty-day backfill. No actual search/calendar API response, dated result inventory or legal document extraction has yet been certified. DOGC remains implemented=false.**

Homepage: `https://dogc.gencat.cat/ca/inici/`.

Public scripts verified under `https://dogc.gencat.cat/web/system/modules/cat.gencat.wcmResponsive.formatters.httpFetch/resources/`:

- `common/js/constants.js`
- `common/js/functionsCommons.js`
- `common/js/functionsFilterResultCommons.js`
- `fpca_calendari_dogc/js/fpca_calendari_dogc.js`
- `fpca_cerca_resultats_dogc/js/fpca_cerca_resultats_dogc.js`
- `fpca_sumari_ultim_DOGC_publicat/js/fpca_sumari_ultim_DOGC_publicat.js`

## Observed routes and next verification

Public code declares `/eadop-rest/api/dogc/calendarDOGC` and `/eadop-rest/api/dogc/summaryDOGC`, along with read-only lists for sections, document types and issuing authorities. Search code contains publicationDateInitial/publicationDateFinal, language, page and numResultsByPage, and receives resultSearch records. The complete query route and request method must be resolved from the publicly declared hidden inputs and actual AJAX call structure before making requests. Merely seeing an endpoint string does not establish its response schema or accessibility.

Only read-only public acquisition is needed. Do not call saved-search or saved-document write endpoints. Do not add credentials, payment providers or commercial aggregators. Public JavaScript is preserved as evidence; potential authentication values are not printed in reports.

The permit-discovery adapter must verify complete date ranges, pagination counts, original document identity, publication dates and administrative meaning before it is enabled. A public-information search with a default current/open-only filter must not silently exclude withdrawn or denied projects. Empty HTML application shells are not evidence of zero results.

The related Catalunya wind/PV datasets are a different source family: see [catalunya.md](catalunya.md). Their dataset-update timestamps and environmental-panel meeting dates cannot replace DOGC publication dates or prove that authorization was granted. Exact project/document references will be needed to link the snapshot and the dated administrative feed conservatively.
