# CURRENT STATE — Spain Renewables Radar

## Ultima certificazione integrata — 4 ottobre 2026

Run **37190197264 — SUCCESS**; codice **352f236ad70c9d14769ff8ce4cde473919117025**.
Finestra completa: **4 settembre–3 ottobre 2026**.
Sono passati test, smoke a dieci fonti, backfill 30 giorni, gate qualità/copertura, verifica provenienza e replay idempotente.

- **200 schede progetto, 206 eventi**; non equivalgono a 200 opportunità commerciali attive.
- **0 errori fonte/giorno**; 30 giorni controllati per ciascuno dei 10 collector.
- Quality gate: **0 ERROR, 2 WARN, 103 INFO**.
- Campi mancanti: nome **2**, MW **54**, provincia singola **8**, expediente **41**.
- Gli 8 casi senza provincia singola sono multi-provincia: **0 province realmente irrisolte** nel dataset certificato.
- **33 province** nella vista, **618,26 MW multi-provincia** tenuti separati; 30 MW di gruppo SABIA 20260224 non ripartiti arbitrariamente sui singoli impianti.
- REE: **931 nodi**, snapshot 2026-10-01. Registro MITECO: **71.727 impianti**, acquisizione 2026-10-04, **8 match esatti** conservativi.
- Identificativi verificati; campi di provenienza completi; nessun nuovo evento/progetto al replay.
- Artifact: **11299001705**, nome **backfill-30d-output**, nel run sopra.

### Eventi per fonte

| Fonte | Eventi |
|---|---:|
| BOE | 41 |
| BOCYL | 36 |
| BOA | 21 |
| BOJA | 7 |
| DOCM | 17 |
| DOE | 8 |
| BORM | 11 |
| BOCM | 4 |
| AND_PUBLIC | 8 |
| MITECO_SABIA | 53 |

## Fonti operative e limiti

Gli 8 bollettini restano operativi. Sono integrati anche SABIA e il portale regionale Andalucía.

**SABIA**: 1.659 pratiche inventariate e dettagli acquisiti, cinque tipi (FTV 770, EOL 433, EOM 74, HIB 343, ALM 39), senza filtro sullo stato corrente. Nella finestra, 31 pratiche amministrative producono 53 schede impianto. Eventi limitati alle date effettive ENTRY/CONSULT: non sono date di pubblicazione web né nuove autorizzazioni dedotte dall'etichetta di stato. Le potenze dei gruppi non vengono duplicate sui componenti. Gli indici sono verificati live; i dettagli in cache conservano la loro data originale e vengono riparsati, con campione live forzato.

**AND_PUBLIC**: archivio di 13.633 record; **25 lacune nei metadati della fonte** conservate e visibili nel report dedicato. Il gate di acquisizione è verde ma i metadati dell'archivio non sono completi. Le richieste in informazione pubblica non diventano concessioni leggendo allegati storici.

**BORM**: indice ufficiale di 4.794 righe. Nel run certificato è stato scaricato live una volta e riutilizzato per il backfill dello stesso run. Originale 2026-10-04T08:50:33.155344+00:00; hash, bytes e data conservati. Cache circoscritta a run/attempt, durata massima un'ora; nessun riutilizzo di un run precedente. Errore persistente, HTML al posto del JSON o righe malformate non diventano risultati vuoti.

**BOCYL**: identificativo completo della disposizione, non della sola edizione. La correzione ha recuperato pubblicazioni prima collassate; vecchie identità riparate con backup e invarianti sui contenuti originali.

## Lavoro corrente — portali regionali

**GVA_PUBLIC / Comunitat Valenciana: collector in validazione, NON ancora attivato nel registry/pipeline.**
Fonte indipendente dal DOGV: portale ufficiale mediambient.gva.es, información pública de energía.
Probe inventario **37186210816**: 533 pubblicazioni, 27 pagine, 22 pubblicazioni nella finestra. Probe atti **37186563752**, audit semantico **37190420365**. Questi probe non sono da soli una certificazione del collector.

Aggiunti codice reale e test per: conteggi/paginazione, ID e data web originali, richieste vs concessioni, rinunce/dinieghi/chiusure del procedimento, potenza installata vs accesso/picco/batterie, discrepanze titolo-atto, preservazione degli originali e assenza di duplicati. Gli atti di sola rete restano nell'inventario, non diventano impianti di generazione. Le chiusure per perdita/desaparición sobrevenida sono PROCEDURE_ENDED/BLOCKED, non autorizzazioni né rinunce inventate.

I PDF originali sono conservati integralmente; estrazione campi dalle prime due pagine degli atti principali, senza OCR. Allegati tecnici indicizzati come link, senza rivendicare acquisizione integrale di ogni progetto. Un PDF solo immagine resta segnalato; si usa il titolo solo dove esplicito. Nessuna potenza scelta automaticamente in presenza di conflitto.

Prima dell'attivazione devono passare test, smoke live (con campione positivo datato), backfill 30 giorni e 0 errori strutturali. Poi nuova certificazione integrata con undici fonti.

## Priorità approvate

1. SABIA: integrazione sopra, continuare a mantenere esplicito il perimetro dei milestone.
2. Portali regionali energía/información pública: Andalucía operativa; GVA in validazione; prossimi da sottoporre a probe e gate.
3. Dieci bollettini autonomici mancanti. DOGV rimane non implementato: il portale GVA non equivale al collector DOGV.
4. PLACSP e consultazioni preliminari.
5. IDAE e BDNS/SNPSAP.
6. Concorsi/assegnazioni di capacità MITECO/ITJ.
7. CNMC distribuzione come contesto, non inventario di progetti.
8. Ricerca esterna EPC/BoP solo dopo l'estensione delle fonti di discovery.

## Vincoli e qualità

Solo fonti ufficiali/gratuite, nessun aggregatore commerciale. Owner/promotore distinto dall'EPC. REE è contesto rete, non conferma del singolo progetto. Score commerciale separato dal lifecycle. Mai inventare nomi, MW, provincia, expediente o stato; preservare external_id, URL, date e raw_text. I flag segnalano dubbi, non correggono automaticamente dati.

Il gate strutturale non certifica la perfezione semantica di ogni campo estratto: rimangono nomi da affinare e informazioni mancanti. EPC/BoP dispone del layer separato di evidenze; non viene inventato un contractor quando manca una dichiarazione esplicita. Dashboard e vista provinciale mantengono MW sconosciuti, multi-provincia e potenze non allocate separati.
