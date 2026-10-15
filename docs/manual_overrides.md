# Correzioni manuali dei dati di progetto

Quando un atto ufficiale non permette di estrarre automaticamente un dato (nome impianto, MW, promotore…), il record **viene comunque pubblicato** con l'avviso `MISSING_PROJECT_NAME` / `INVALID_POWER_MW` e compare in `da_verificare.csv`. Non blocca più l'aggiornamento.

## Come aggiungere un dato mancante (pochi minuti, nessuna nuova raccolta)
1. Apri `da_verificare.csv` (nell'artifact `radar-web-with-overrides` o nel portale): ogni riga ha già il `selector` e il link all'atto.
2. Verifica il dato sull'atto ufficiale.
3. Su GitHub modifica `config/manual_overrides.csv` (matita → aggiungi una riga → Commit):

```
selector,field,value,evidence_url,note,author,date
BOA:007961616,project_name,Nome dall'atto,https://www.boa.aragon.es/...,verificato pag. 2,FC,2026-10-15
```

4. Il commit avvia da solo `portal-apply-overrides`: ripristina l'ultimo database validato, applica le correzioni e rigenera il portale **senza interrogare le fonti** (pochi minuti).

## Regole
- `field`: `project_name`, `power_mw`, `promoter`, `province`, `ccaa`, `technology` (`PV|WIND|HYBRID|BESS`).
- `evidence_url` è obbligatorio: niente dati senza fonte.
- Gli atti originali (titolo, testo, URL, date) non vengono mai modificati. Le correzioni restano registrate in `manual_field_overrides` con valore precedente, fonte e autore, e compaiono nel portale (`manual_overrides`).
- Le correzioni vengono riapplicate a ogni esecuzione della pipeline, quindi una nuova raccolta non le sovrascrive. Un `selector` non ancora presente resta in attesa e si applica quando l'atto entra nel database.
