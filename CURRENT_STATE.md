# CURRENT STATE — Spain Renewables Radar

## Stato certificato

Il radar è operativo su **8 bollettini ufficiali** più due enrichment nazionali gratuiti.

### Collector attivi

- BOE — nazionale
- BOCYL — Castilla y León
- BOA — Aragón
- BOJA — Andalucía
- DOCM — Castilla-La Mancha
- DOE — Extremadura
- BORM — Región de Murcia, tramite dataset ufficiale Open Data degli indici
- BOCM — Comunidad de Madrid, tramite fonte ufficiale per data/XML

### Enrichment attivi

- REE — capacità/accesso per nodo;
- MITECO RAIPEE — registro produzione.

Nessun aggregatore commerciale è usato.

## Ultima validazione 30 giorni

Run: **37114835344 — SUCCESS**

- **107 progetti**
- **129 eventi amministrativi**
- BOE 42
- BOCYL 15
- BOA 24
- BOJA 7
- DOCM 17
- DOE 8
- BORM 11
- BOCM 5
- REE: **931 nodi**, snapshot 2026-10-01
- MITECO: **71.727 impianti**, snapshot 2026-10-03
- matching MITECO esatti conservativi: **8**
- campi mancanti: nome 1, MW 26, provincia 4, expediente 14

Il workflow è verde. Nel backfill sono rimasti **2 source/day warning transitori di rete BOA** (timeout/remote disconnect) non trasformati in dati inventati; il collector dispone già di retry. Lo smoke test più recente sullo stesso head è verde e senza errori.

## Quality gate

Ultimo conteggio sul backfill:

- **ERROR: 0**
- **WARN: 1**
- **INFO: 44**

Il solo WARN sul nome è una pubblicazione BOCYL che raggruppa due parchi fotovoltaici senza fornire denominazioni individuali. Il radar conserva correttamente il nome vuoto.

Generati automaticamente:

- `reports/quality_issues_latest.csv`
- `reports/quality_issues_latest.html`
- `reports/coverage_latest.csv`
- `reports/coverage_latest.html`

Correzioni consolidate:

- falsi positivi Catasto/policy generiche BOE esclusi;
- gigafactory batterie per veicoli BOA esclusa;
- storage non energetico DOCM escluso;
- centri rifiuti/riciclo pannelli DOE esclusi;
- nomi BESS/ibridi prioritari rispetto agli impianti preesistenti;
- virgolette tipografiche spagnole gestite;
- potenze in kW convertite in MW;
- fonti regionali vincolate alla propria CCAA;
- BORM acquisito da JSON ufficiale Open Data, evitando il blocco anti-bot del sito documentale;
- BOCM acquisito dalla fonte ufficiale per data/XML;
- `Expte.` gestito come variante di expediente;
- retry aggiunto alle chiamate BOA per errori transitori.

## Problemi aperti

- 26 progetti non riportano MW nella fonte disponibile;
- 4 progetti non hanno provincia estraibile;
- 14 progetti non riportano expediente;
- matching MITECO resta volutamente conservativo;
- EPC/BoP richiede enrichment separato da fonti pubbliche;
- DOGV corrente risponde 403 dal runner GitHub: non dichiararlo implementato senza endpoint ufficiale stabile;
- il backfill BOA può ancora produrre sporadici warning di rete su singoli giorni, pur con retry.

## Prossimi passi

1. **enrichment geografico comune → provincia** per ridurre i 4 missing senza euristiche rischiose;
2. **scoring commerciale** separato dal lifecycle amministrativo;
3. **vista/mappa provinciale** con MW per tecnologia e maturità;
4. **enrichment EPC/BoP** da fonti pubbliche gratuite;
5. aggiungere il prossimo collector regionale solo dopo probe + test + validazione 30 giorni;
6. continuare a ridurre gli INFO senza inventare dati mancanti.

## Vincoli

- fonti ufficiali/gratuite come primary source;
- nessun Sondeva o aggregatore commerciale;
- meglio campo vuoto che dato inventato;
- owner/promotore ed EPC sono entità diverse;
- REE per nodo/CCAA è contesto rete, non conferma automatica del singolo progetto;
- un progetto resta una sola entità e accumula eventi successivi.
