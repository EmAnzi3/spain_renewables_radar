# Strategia fonti — Spain Renewables Radar

## Principio

Il radar usa **solo fonti ufficiali o pubbliche gratuite**. Ogni evento deve conservare il link alla fonte originaria.

## Livello 1 — bollettini ufficiali

Target: BOE + 17 CCAA.

Ogni collector deve:
1. leggere una finestra temporale;
2. identificare candidati renewable;
3. mantenere ID e URL originali;
4. estrarre solo campi supportati dal documento;
5. produrre metriche letti/candidati/scartati/errori.

## Livello 2 — REE

Usare REE per:
- accesso/connessione;
- stato RdT/RdD quando disponibile;
- nodo/subestación;
- capacità aggregate.

Mai trasformare un valore aggregato per nodo o CCAA in una falsa conferma di un singolo progetto.

## Livello 3 — MITECO

Usare il registro amministrativo impianti per:
- validare impianti autorizzati/in esercizio;
- supportare geografia e potenza;
- distinguere pipeline da stock operativo.

## Livello 4 — EPC / BoP

Fonti pubbliche gratuite:
- comunicati EPC;
- comunicati developer;
- comunicati supplier;
- documenti di gara/pubblici;
- stampa di settore come segnale, da confermare.

Stati:
- EPC_CONFIRMED
- EPC_CANDIDATE
- EPC_UNKNOWN

## Definition of Done collector

- 30 giorni senza errori fatali;
- URL ufficiale e source ID preservati;
- niente duplicati nei run successivi;
- fixture + test;
- metriche di coverage;
- niente campi inventati.
