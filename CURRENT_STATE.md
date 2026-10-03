# CURRENT STATE — Spain Renewables Radar

## Stato certificato

Il radar è operativo su **7 bollettini ufficiali** più due enrichment nazionali gratuiti.

### Collector attivi

- BOE
- BOCYL — Castilla y León
- BOA — Aragón
- BOJA — Andalucía
- DOCM — Castilla-La Mancha
- DOE — Extremadura
- BORM — Región de Murcia, tramite il dataset ufficiale Open Data degli indici del bollettino

### Enrichment attivi

- REE accesso/capacità per nodo;
- MITECO registro produzione.

Nessun aggregatore commerciale è usato.

## Ultima validazione 30 giorni

Run: **37108715840 — SUCCESS**

- 102 progetti;
- 124 eventi;
- 0 errori source/day;
- BOE 42;
- BOCYL 15;
- BOA 24;
- BOJA 7;
- DOCM 17;
- DOE 8;
- BORM 11;
- REE: 931 nodi, snapshot 2026-10-01;
- MITECO: 71.727 impianti, snapshot 2026-10-03;
- matching MITECO esatti conservativi: 8;
- campi mancanti: nome 1, MW 23, provincia 4, expediente 14.

## Quality gate

Ultimo esito certificato:

- **ERROR: 0**
- **WARN: 1**
- **INFO: 41**

Il solo WARN sul nome è una pubblicazione BOCYL che raggruppa **due parchi fotovoltaici senza fornire denominazioni individuali**. Il radar conserva correttamente il nome vuoto invece di inventarlo.

Generati automaticamente:
- `reports/quality_issues_latest.csv`
- `reports/quality_issues_latest.html`

Correzioni consolidate:
- falsi positivi Catasto/policy generiche BOE esclusi;
- gigafactory batterie per veicoli BOA esclusa;
- storage non energetico DOCM escluso;
- centri rifiuti/riciclo pannelli DOE esclusi;
- nomi BESS/ibridi prioritari rispetto agli impianti preesistenti;
- virgolette tipografiche spagnole gestite;
- potenze in kW convertite in MW;
- fonti regionali vincolate alla propria CCAA;
- BORM acquisito da JSON ufficiale Open Data, evitando il blocco anti-bot del sito documentale.

## Problemi aperti

- 23 progetti non riportano MW nella fonte disponibile;
- 4 progetti non hanno provincia estraibile;
- 14 progetti non riportano expediente;
- matching MITECO resta volutamente conservativo;
- EPC/BoP richiede enrichment separato da fonti pubbliche;
- DOGV corrente risponde 403 dal runner GitHub: non viene dichiarato implementato senza endpoint ufficiale stabile.

## Prossimi passi

1. aggiungere il prossimo collector regionale solo dopo validazione live, con BOCM come candidato prioritario per la disponibilità di sumari XML/RSS;
2. enrichment geografico comune→provincia;
3. scoring commerciale e vista provinciale;
4. enrichment EPC/BoP;
5. continuare a ridurre gli INFO senza inventare dati mancanti.
