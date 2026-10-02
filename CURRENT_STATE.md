# CURRENT STATE — Spain Renewables Radar

## Stato

MVP 0.1 inizializzato su GitHub.

## Funzionante

- schema SQLite;
- collector BOE;
- parsing tecnologico/geografico base;
- lifecycle amministrativo;
- dedup evento/progetto;
- report modifiche;
- dashboard statica iniziale;
- BAT Windows;
- test offline.

## Strategia attuale

Solo fonti free of charge:
1. bollettini ufficiali;
2. REE per accesso/connessione;
3. MITECO per registro impianti;
4. fonti pubbliche aziendali per EPC/BoP.

## Prossimi passi

1. validare BOE su 7/30 giorni reali;
2. misurare precisione/recall manualmente su campione;
3. implementare BOCYL, BOA e BOJA;
4. aggiungere metriche di coverage per fonte;
5. integrare REE senza falsi match progetto-nodo;
6. costruire mappa provinciale;
7. enrichment EPC/BoP.
