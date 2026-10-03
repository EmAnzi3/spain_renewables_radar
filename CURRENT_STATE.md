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

## Validazione 30 giorni

Baseline precedente: **37114835344 — workflow SUCCESS**, ma con **2 source/day error BOA**. Dopo l'introduzione del gate rigoroso questo run NON va più considerato una certificazione completa di coverage.

Nuova validazione rigorosa in corso:
- **run 37115752500**
- head: **eb3dd110762c65d290a61d911f288540e301fe41**
- regola: il workflow fallisce se anche una sola sorgente/giorno non viene acquisita.

Smoke test rigoroso già certificato:
- **run 37115696021 — SUCCESS**
- ultimi 3 giorni
- **0 source/day errors**
- REE: 931 nodi
- MITECO: 71.727 impianti

### Baseline quantitativa precedente (37114835344)

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

Questi numeri restano il riferimento quantitativo finché il run rigoroso 37115752500 non termina. Il gate ora impedisce di definire "verde" un backfill con coverage incompleta.

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
- BOA può ancora produrre errori transitori di rete su singoli giorni; ora vengono trattati come **failure del validation gate**, non come semplice warning verde.

## Prossimi passi

1. **attendere/verificare il run rigoroso 37115752500**: deve chiudere con 0 source/day errors; in caso contrario correggere la sorgente che fallisce e rilanciare;
2. **enrichment geografico comune → provincia** per ridurre i 4 missing senza euristiche rischiose;
3. **scoring commerciale** separato dal lifecycle amministrativo;
4. **vista/mappa provinciale** con MW per tecnologia e maturità;
5. **enrichment EPC/BoP** da fonti pubbliche gratuite;
6. prossimo collector regionale consigliato: **DOG Galicia** (alto valore eolico), solo dopo probe + test + validazione 30 giorni;
7. continuare a ridurre gli INFO e i nomi sospetti senza inventare dati mancanti.

## Vincoli

- fonti ufficiali/gratuite come primary source;
- nessun Sondeva o aggregatore commerciale;
- meglio campo vuoto che dato inventato;
- owner/promotore ed EPC sono entità diverse;
- REE per nodo/CCAA è contesto rete, non conferma automatica del singolo progetto;
- un progetto resta una sola entità e accumula eventi successivi.
