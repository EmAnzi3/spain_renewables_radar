# CURRENT STATE — Spain Renewables Radar

## Stato

MVP 0.1 operativo su GitHub con sorgente BOE ufficiale e gratuita.

## Funzionante

- schema SQLite con progetto unico + storico eventi;
- collector BOE basato sull'OpenData API ufficiale, con fallback HTML;
- parsing FV / eolico / BESS / ibrido;
- estrazione preliminare di MW, progetto, promotore, expediente e geografia;
- lifecycle amministrativo con distinzione fra:
  - PUBLIC_INFO
  - DIA
  - PRIOR_AUTH
  - CONSTRUCTION_AUTH
  - PUBLIC_UTILITY
  - EXPROPRIATION
  - WITHDRAWN
  - DENIED
- deduplica progetto/evento;
- report CSV + HTML delle variazioni;
- dashboard statica iniziale;
- BAT Windows;
- test offline e smoke test live GitHub Actions.

## Ultima validazione live

Run live BOE: 37066642276 — SUCCESS.

Finestra 30/09/2026–02/10/2026:
- 6 eventi renewable utili individuati;
- 0 giorni in errore;
- escluso correttamente un falso positivo di procurement FV;
- localizzazioni corrette per Eclipse Solar, Vientos del Cid I, ALSA, PSF Ronda 3 ed Elawan Olmedo I;
- PE Conca de Barberà I resta con provincia non attribuita: scelta fail-safe, perché il BOE coinvolge più territori e non esplicita una singola provincia nel titolo.

Unit test run: 37066642228 — SUCCESS.

## Strategia attuale

Solo fonti free of charge:
1. BOE/OpenData ufficiale;
2. bollettini ufficiali delle 17 CCAA;
3. REE per accesso/connessione;
4. MITECO per registro impianti;
5. fonti pubbliche aziendali per EPC/BoP.

Nessun aggregatore commerciale è usato come sorgente o dipendenza.

## Problemi aperti

- geografia multi-provincia e progetti senza provincia esplicita: serve enrichment comune→provincia;
- potenza può cambiare tra eventi successivi: va preservato lo storico e scelta la misura più autorevole;
- EPC/BoP non è normalmente presente nei bollettini e richiederà enrichment separato;
- i collector regionali non sono ancora implementati.

## Prossimo blocco tecnico

1. BOCYL;
2. BOA;
3. BOJA;
4. metriche coverage per fonte;
5. backfill BOE storico;
6. REE;
7. MITECO;
8. mappa provinciale;
9. enrichment EPC/BoP.
