# CURRENT STATE — Spain Renewables Radar

## Ultima certificazione integrata — 4 ottobre 2026

- **Run 37193300195 — SUCCESS**, codice **18518b1580380b0bb31c1e3cd9112da365682b0c**.
- Finestra completa **4 settembre–3 ottobre 2026**.
- **11 collector integrati**, 30 giorni per ciascuno, smoke live, **157 test** e controlli di identità, provenienza e replay superati.
- **218 schede progetto / 224 eventi**. Non sono 218 opportunità commerciali attive.
- **0 errori fonte/giorno**; quality gate **0 ERROR / 3 WARN / 109 INFO**.
- Mancanti: nome **2**, MW **58**, provincia singola **8**, expediente **41**.
- Gli 8 casi senza provincia singola sono multi-provincia: **0 province realmente irrisolte**.
- **36 province** nella vista; **618,26 MW multi-provincia** separati. I **30 MW di gruppo SABIA 20260224** non sono ripartiti né duplicati arbitrariamente.
- REE: **931 nodi**, snapshot 2026-10-01. Registro MITECO: **71.727 impianti**, acquisizione 2026-10-04, **8 match esatti** conservativi.
- Replay idempotente: nessun nuovo progetto/evento; provenienza degli eventi completa.
- Artifact **11299699083**, `backfill-30d-output`, nel run certificato.

Il run precedente 37190197264 (200 schede/206 eventi, dieci fonti) è superato da questa certificazione. Il pacchetto locale `spain_radar_gva_preview_55ecc9d.zip` è superato: **non applicarlo su main**.

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
| GVA_PUBLIC | 18 |
| MITECO_SABIA | 53 |

## Fonti operative e limiti

Gli otto bollettini sono operativi, insieme a SABIA, Andalucía e Comunitat Valenciana. INE, REE e RAIPEE sono enrichment, non ulteriori collector di discovery.

**SABIA**: 1.659 pratiche inventariate e dettagli acquisiti, cinque tipi (FTV 770, EOL 433, EOM 74, HIB 343, ALM 39), senza filtro di stato. Nella finestra, 31 pratiche producono 53 schede impianto. Milestone datati **ENTRY/CONSULT** soltanto: non sono date web né nuove autorizzazioni dedotte dall'etichetta corrente. Le potenze dei gruppi non vengono duplicate. Gli indici vengono verificati live; i dettagli in cache conservano data originale e vengono riparsati, con campione live forzato.

**AND_PUBLIC**: 13.633 record nell'archivio; **25 lacune nei metadati della fonte**, conservate e visibili nel report. Acquisizione valida non significa metadati completi. Le richieste non diventano autorizzazioni leggendo allegati storici.

**GVA_PUBLIC: ATTIVO e validato**, indipendente dal DOGV. Validazione dedicata **37192271844**; integrazione **37193300195**. Archivio di **533 pubblicazioni / 27 pagine**; nella finestra **22 pubblicazioni**, di cui **18 eventi**, 3 atti solo rete e 1 non pertinente. Stati: **11 BLOCKED, 5 AUTHORIZED, 2 EARLY**. Decisioni: 6 PROCEDURE_ENDED, 5 CONSTRUCTION_AUTH, 4 WITHDRAWN, 1 DENIED, 2 PUBLIC_INFO. Le chiusure di procedimento non sono rinunce o autorizzazioni inventate.

GVA conserva i PDF originali; i campi sono estratti dalle **prime due pagine** degli atti principali, senza OCR. Allegati tecnici indicizzati, non tutti acquisiti. Tre flag preservati: potenze multi-componente non sommate, contrasto di potenza tra titolo/atto, atto solo immagine. Nessuna potenza scelta arbitrariamente in presenza di conflitto. Il DOGV resta non implementato: **GVA_PUBLIC non equivale a DOGV**.

**BORM**: 4.794 righe nell'indice ufficiale; acquisizione live unica nel run/attempt, riutilizzata nel medesimo backfill conservando bytes, hash e data. Nel run certificato: **2026-10-04T09:48:35.974263+00:00**, un tentativo. Durata massima snapshot un'ora, nessun riutilizzo da run precedenti. Errori persistenti, HTML invece di JSON o righe malformate non diventano risultati vuoti.

**BOCYL**: ID della singola disposizione, non della sola edizione; recuperati atti prima collassati. Riparazione delle identità pregresse con backup e invarianti sui contenuti originali.

## Lavoro corrente — Galicia

Probe ufficiale **37193602560 — SUCCESS**: 298 voci consultazioni, 123 autorizzazioni, 66 documentazione ambientale (**487 record**, non progetti unici). Riconciliate tutte le **50 pagine**. Sette gruppi hanno titoli ripetuti fra archivi. Nessuna data web verificata; nessun atto con data riconosciuta nella finestra di 30 giorni. Non interpretare questo risultato come assenza di progetti recenti in Galicia.

Aggiunto **app.galicia_archive**, inventario completo aggiornabile con snapshot/differenze, acquisizione di tutte le schede HTML, originali con hash/data, report JSON/CSV/HTML e audit esplicito della finestra. In validazione live tramite **galicia-archive-validation**. Il primo snapshot è BASELINE, non centinaia di nuove opportunità; una scheda non più presente è NOT_SEEN, non WITHDRAWN. Data atto, periodo consultazione e date desunte dai link DOG rimangono separate da date di pubblicazione web ignote.

Questo modulo è **separato dalla pipeline amministrativa** e non incrementa gli 11 collector certificati. Il gate di inventario non è un backfill storico certificato delle pubblicazioni web. Gli allegati sono indicizzati, non scaricati. La copertura quotidiana della Galicia richiede ancora il completamento del collegamento alle pubblicazioni datate del DOG o altra fonte ufficiale con date verificabili.

## Sequenza approvata

1. SABIA integrato, nei limiti dei milestone dichiarati.
2. Portali regionali energia/información pública: Andalucía e GVA operativi; Galicia in lavorazione; altri da acquisire e validare.
3. Dieci bollettini autonomici ancora mancanti, incluso DOGV.
4. PLACSP e consultazioni preliminari.
5. IDAE e BDNS/SNPSAP.
6. Concorsi/assegnazioni di capacità MITECO/ITJ.
7. CNMC distribuzione come contesto, non inventario progetti.
8. Ricerca esterna EPC/BoP dopo l'estensione delle fonti di discovery.

## Vincoli

Solo fonti ufficiali/gratuite; nessun aggregatore commerciale. Owner/promotore distinto da EPC. REE è contesto rete. Scoring separato dal lifecycle. Mai inventare nomi, MW, provincia, expediente, date o stato. Preservare external_id, URL, date e raw_text. I flag espongono dubbi, non correggono automaticamente i dati. Il gate strutturale non certifica la perfezione semantica di ciascun campo. Il layer EPC/BoP rimane presente ma non inventa contractor; nel run certificato non risultano evidenze esplicite. Dashboard e aggregati separano MW sconosciuti, multi-provincia e potenze di gruppo non allocate.
