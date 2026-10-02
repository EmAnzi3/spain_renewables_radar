# CURRENT STATE — Spain Renewables Radar

## Stato certificato

Il radar è operativo su **6 bollettini ufficiali** più due enrichment nazionali gratuiti.

### Collector attivi

- BOE
- BOCYL — Castilla y León
- BOA — Aragón
- BOJA — Andalucía
- DOCM — Castilla-La Mancha
- DOE — Extremadura

### Enrichment attivi

- REE accesso/capacità per nodo;
- MITECO registro produzione.

Nessun aggregatore commerciale è usato.

## Ultima validazione 30 giorni

Run: **37072608960 — SUCCESS**

- 99 progetti;
- 123 eventi;
- 0 errori source/day;
- BOE 44;
- BOCYL 16;
- BOA 27;
- BOJA 7;
- DOCM 19;
- DOE 10;
- MITECO: 71.727 impianti;
- REE: 931 nodi;
- campi mancanti prima del quality gate: nome 4, MW 25, provincia 6, expediente 26.

Correzioni validate:
- `PSF Puerto Real`: 133,5708 MW, non 5.708 MW;
- `Terrapower Generación`: nome e 44,16 MW corretti;
- `Atalaya`: Badajoz e fase PERMITTING, evitando un falso BLOCKED dovuto a riferimenti storici nel testo;
- autoconsumo escluso dal BOE;
- geografia dei collector regionali vincolata alla rispettiva CCAA.

## Quality gate

Generati automaticamente:
- `reports/quality_issues_latest.csv`
- `reports/quality_issues_latest.html`

Flag:
- nome progetto mancante;
- nome sospetto/generico;
- MW mancanti o anomali;
- provincia mancante;
- expediente mancante.

I flag non riscrivono i dati.

## Problemi aperti

- alcuni nomi progetto restano estratti in modo imperfetto nei documenti più complessi;
- geografia multi-provincia richiede enrichment comune→provincia;
- alcune pubblicazioni non riportano MW o expediente;
- matching MITECO è volutamente conservativo;
- EPC/BoP richiede enrichment separato da fonti pubbliche;
- DOGV corrente risponde 403 dal runner GitHub: non è dichiarato implementato finché non troviamo un endpoint ufficiale stabile.

## Prossimi passi

1. ridurre i record quality WARN/ERROR del backfill;
2. aggiungere un altro collector regionale solo dopo validazione live;
3. enrichment geografico comune→provincia;
4. scoring commerciale e vista provinciale;
5. enrichment EPC/BoP.
