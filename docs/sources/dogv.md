# DOGV — Diari Oficial de la Generalitat Valenciana

Collector: `app/collectors/dogv.py` · codice `DOGV` · promosso a fonte certificata ordinaria il 15/10/2026.

## Endpoint ufficiali (backend del portale https://dogv.gva.es/dogv-portal-frontend)
| Uso | Richiesta |
|---|---|
| Giorni di pubblicazione | `GET /dogv-portal/dogv/calendar?startDate=YYYY-MM-DD&endDate=YYYY-MM-DD` |
| Sommario del giorno | `GET /dogv-portal/dogv?date=YYYY-MM-DD&lang=es` |
| Testo integrale | `GET /dogv-portal/disposicion/{id}?lang=es` |

Le date sono in formato ISO: `dd/mm/yyyy` restituisce l'errore applicativo 440.

## Regole
- Fail-closed: errori HTTP, risposte non JSON o schema inatteso marcano il giorno come ERROR. Un giorno senza bollettino nel calendario è OK con zero candidati.
- Solo disposizioni con `fechaPublicacion` uguale al giorno richiesto.
- Rilevanza: fotovoltaico, eolico, accumulo, ibridazione e repowering. Sono esclusi contratti, bandi, aiuti, autoconsumo e pianificazione urbanistica generale.
- Identità: CVE ufficiale (`DOGV-AAAA-NNNNN`). URL: PDF ufficiale `https://dogv.gva.es/datos/...`.
- Perimetro territoriale: Comunitat Valenciana (`REGIONAL_SOURCE_SCOPE`).

## Validazione storica
Run `claude-targeted-backfill` 38718120382 e 38718461294, ottobre 2024 – settembre 2026:
- 24 mesi su 24 con tutti i giorni acquisiti;
- 8 mesi certificati; 16 bocciati solo dal gate qualità su singoli record (nome impianto non estratto o 0 MW);
- 467 atti energetici.

## Limiti noti
- I numeri `esBis` (bollettini straordinari) sono registrati nell'audit. Va ancora verificato che il sommario per data includa sempre le disposizioni dei numeri bis.
