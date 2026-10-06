"""Dated DOGC collector with independent daily-index reconciliation and PDF evidence.

Energy proceedings become events. Municipal project leads, corrections and
excluded subjects remain fully inventoried, not forced into energy permits.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, timezone
import hashlib
import html
import json
import os
from pathlib import Path
import uuid
from zoneinfo import ZoneInfo

from app.catalunya_inventory import atomic_json
from app.dogc_projection import events_from_record
from app.dogc_semantics import classify_document
from app.enrichment.ine_municipalities import INE_MUNICIPALITIES_URL, parse_ine_municipalities
from scripts.acquire_dogc_bodies import BodyClient, extract_pages
from scripts.audit_dogc_index import Client, ENERGY, parse_calendar, parse_summary, summary_scopes
from scripts.reconcile_dogc_daily import daily_parameters, parse_complete_day, require_same_index, verify_contract


class DOGCCollector:
    code = 'DOGC'

    def __init__(self, timeout=30, user_agent='SpainRenewablesRadar/0.7', output='reports/dogc', *, catalog=None):
        self.output=Path(output);self.output.mkdir(parents=True,exist_ok=True)
        self.generation=self.output/'snapshots'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8])
        self.generation.mkdir(parents=True)
        self.index=Client(self.generation/'index_raw');self.bodies=BodyClient(self.generation/'pdf_raw')
        self.index.session.headers['User-Agent']=user_agent;self.bodies.session.headers['User-Agent']=user_agent
        self.timeout=timeout;self.catalog=catalog;self.catalog_evidence=None
        self.calendar={};self.days={};self.records={};self.metadata={};self.projected={};self.contract_verified=False
        self.audit={'source_code':self.code,'head_sha':os.getenv('GITHUB_SHA'),'run_id':os.getenv('GITHUB_RUN_ID'),
            'generation':str(self.generation.relative_to(self.output)),'days':{},'complete':False,
            'scope':'dated energy proceedings; municipal leads/corrections retained separately',
            'source_catalog':None,'project_count_claimed':False}

    def _ensure_catalog(self):
        if self.catalog is not None:return
        response=self.index.session.get(INE_MUNICIPALITIES_URL,timeout=(8,max(45,self.timeout)),allow_redirects=False)
        try:
            response.raise_for_status()
            if response.status_code!=200:raise ValueError('INE catalogue redirected or returned unexpected status')
            raw=response.content
            if len(raw)>20_000_000:raise ValueError('INE catalogue exceeds size bound')
            rows=parse_ine_municipalities(json.loads(raw))
            if len(rows)<7000 or len({r.code for r in rows})!=len(rows):raise ValueError('INE catalogue incomplete or repeated codes')
            sha=hashlib.sha256(raw).hexdigest();(self.generation/'ine_municipalities.json').write_bytes(raw)
            self.catalog=rows
            self.catalog_evidence={'source_code':'INE_MUNICIPALITIES','url':INE_MUNICIPALITIES_URL,'sha256':sha,
                'bytes':len(raw),'records':len(rows),'retrieved_at':datetime.now(timezone.utc).isoformat()}
            self.audit['source_catalog']=self.catalog_evidence
        finally:response.close()

    def _month(self,day):
        if not self.contract_verified:
            verify_contract(self.index);self.contract_verified=True
        month=(day.year,day.month)
        if month not in self.calendar:
            data=self.index.post(f'calendar:{day.year}:{day.month}','calendarDOGC',form={'year':day.year,'month':day.month,'language':'ca'})
            self.calendar[month]=parse_calendar(data,*month)
        return self.calendar[month]

    def collect_day(self,day):
        stamp=day.isoformat()
        if stamp in self.days:return self.days[stamp]
        if stamp in self.audit['days'] and self.audit['days'][stamp]['status']=='ERROR':
            raise RuntimeError(self.audit['days'][stamp]['error'])
        stats={'status':'ERROR','complete_calendar_day':day<datetime.now(ZoneInfo('Europe/Madrid')).date(),
               'index_dispositions':0,'title_candidates':0,'energy_documents':0,'energy_events':0,'municipal_leads':0,'corrections':0,'excluded':0,'review_required':0}
        try:
            if day>datetime.now(ZoneInfo('Europe/Madrid')).date():raise ValueError('Future publication day')
            edition=self._month(day)[day];entries={};annexes=[]
            if edition:
                payload=self.index.post('edition:'+stamp,'summaryDOGC',form={'numDOGC':edition,'language':'ca'})
                entries=parse_summary(payload,edition,day)
                annexes=[scope for scope,_ in summary_scopes(payload,edition,day) if scope!=edition]
            search=self.index.post('daily:'+stamp,'searchDOGC',payload=daily_parameters(day))
            require_same_index(entries,parse_complete_day(search,day))
            stats.update(edition=edition,annexes=annexes,index_dispositions=len(entries),daily_index_reconciled=True)
            atomic_json(self.generation/(stamp+'.index.json'),list(entries.values()))
            events=[];metadata={}
            for candidate in entries.values():
                if not ENERGY.search(candidate['title']):continue
                stats['title_candidates']+=1
                raw,acquired=self.bodies.get_pdf(candidate)
                parsed=extract_pages(raw,candidate)
                if not parsed['publication_evidence_complete'] or parsed['empty_text_pages']:
                    raise ValueError('DOGC original PDF masthead/text incomplete: '+candidate['document_id'])
                candidate=dict(candidate,pdf_sha256=acquired['sha256'],retrieved_at=acquired['retrieved_at'],
                    source_pdf_url=acquired.get('final_url',candidate['source_url']))
                pages_file=candidate['document_id']+'.pages.json';atomic_json(self.generation/pages_file,parsed)
                record=classify_document(candidate,parsed['pages'])
                self.records[candidate['document_id']]={'candidate':candidate,'classification':record,'pages_file':pages_file,
                    'pdf_file':'pdf_raw/'+acquired['sha256']+'.pdf','acquisition':acquired}
                if record['category']=='REVIEW_REQUIRED':
                    stats['review_required']+=1
                    raise ValueError('DOGC new wording requires review: '+candidate['document_id'])
                if record['category']=='ENERGY_PROJECT':self._ensure_catalog()
                projections=events_from_record(record,parsed['pages'],self.catalog or [])
                if projections:
                    stats['energy_documents']+=1
                    for event,evidence in projections:
                        if event.external_id in metadata:
                            raise ValueError('DOGC repeated projected event identity')
                        events.append(event);metadata[event.external_id]=evidence;stats['energy_events']+=1
                elif record['category']=='MUNICIPAL_PROJECT':stats['municipal_leads']+=1
                elif record['category']=='CORRECTION':stats['corrections']+=1
                elif record['category']=='OUT_OF_SCOPE':stats['excluded']+=1
            if stats['title_candidates']!=sum(stats[k] for k in ('energy_documents','municipal_leads','corrections','excluded')):
                raise ValueError('DOGC source documents not fully accounted for')
            self.metadata.update(metadata);self.projected.update({e.external_id:asdict(e) for e in events})
            self.days[stamp]=events;stats['status']='OK'
            return events
        except Exception as exc:
            stats['error']=str(exc);raise
        finally:
            self.audit['days'][stamp]=stats;self._save()

    def _save(self):
        self.audit['complete']=bool(self.audit['days']) and all(d['status']=='OK' for d in self.audit['days'].values())
        self.audit['totals']={key:sum(day.get(key,0) for day in self.audit['days'].values()) for key in
             ('index_dispositions','title_candidates','energy_documents','energy_events','municipal_leads','corrections','excluded','review_required')}
        self.audit['updated_at']=datetime.now(timezone.utc).isoformat()
        atomic_json(self.generation/'coverage.json',self.audit);atomic_json(self.output/'coverage.json',self.audit)
        atomic_json(self.generation/'documents.json',list(self.records.values()))
        atomic_json(self.generation/'projected_events.json',list(self.projected.values()))
        atomic_json(self.generation/'event_metadata.json',self.metadata)
        categories={'municipal_leads':'MUNICIPAL_PROJECT','corrections':'CORRECTION','excluded':'OUT_OF_SCOPE','unresolved':'REVIEW_REQUIRED'}
        for filename,category in categories.items():
            atomic_json(self.generation/(filename+'.json'),[r['classification'] for r in self.records.values() if r['classification']['category']==category])
        self._render()

    def _render(self):
        esc=lambda value:html.escape(str(value or ''),quote=True)
        rows=[]
        for identity,item in sorted(self.records.items()):
            r=item['classification'];event=self.projected.get(identity,{})
            if r.get('named_asset_group'):
                group=r['named_asset_group']
                event={'power_mw':str(group['plant_count'])+' impianti × '+group['per_plant_power_mw']+' MW ciascuno'}
            rows.append('<tr><td>'+esc(r['publication_date'])+'</td><td>'+esc(r['category'])+'</td><td>'+esc(r['event'])+
                '</td><td>'+esc((r['project_name'] or{}).get('value') or r['source_title'])+'</td><td>'+esc(event.get('power_mw'))+
                '</td><td>'+esc(event.get('province'))+'</td><td><a href="'+esc(str(self.generation.relative_to(self.output))+'/'+item['pdf_file'])+'">PDF originale</a></td></tr>')
        page='<!doctype html><html lang="it"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>DOGC — acquisizione</title><style>body{font:16px/1.5 system-ui;margin:24px}main{max-width:1400px;margin:auto}.scroll{overflow:auto}table{border-collapse:collapse;min-width:800px}td,th{padding:10px;text-align:left;border-bottom:1px solid #ddd;vertical-align:top}</style><main><h1>DOGC — atti e opportunità da verificare</h1><p>Solo i procedimenti energetici entrano come eventi nel radar. I progetti comunali rimangono lead separati: un’approvazione locale non è un’autorizzazione energetica. Le rettifiche non creano impianti nuovi. MW vuoti significa dato non determinabile, non zero.</p><p>Esito acquisizione: <b>'+('COMPLETA' if self.audit['complete'] else 'INCOMPLETA')+'</b>. <a href="coverage.json">Controlli e conteggi</a></p><div class="scroll"><table><tr><th>Data</th><th>Categoria</th><th>Decisione della fonte</th><th>Nome / oggetto originale</th><th>MW selezionati</th><th>Provincia</th><th>Fonte</th></tr>'+''.join(rows)+'</table></div></main></html>'
        (self.output/'index.html').write_text(page,encoding='utf-8')

    def persist_metadata(self,conn):
        conn.execute('''CREATE TABLE IF NOT EXISTS regional_public_metadata (
            source_code TEXT NOT NULL,external_id TEXT NOT NULL,project_key TEXT NOT NULL,
            web_publication_date TEXT NOT NULL,source_url TEXT NOT NULL,evidence_json TEXT NOT NULL,
            PRIMARY KEY(source_code,external_id),FOREIGN KEY(project_key) REFERENCES projects(project_key))''')
        conn.execute('''CREATE TABLE IF NOT EXISTS dogc_document_observations (
            external_id TEXT PRIMARY KEY,publication_date TEXT NOT NULL,source_url TEXT NOT NULL,
            pdf_sha256 TEXT NOT NULL,category TEXT NOT NULL,event TEXT NOT NULL,record_json TEXT NOT NULL)''')
        for identity,item in self.records.items():
            record=item['classification'];old=conn.execute('SELECT pdf_sha256 FROM dogc_document_observations WHERE external_id=?',(identity,)).fetchone()
            if old and old['pdf_sha256']!=record['pdf_sha256']:raise ValueError('Previously acquired DOGC document changed; review required')
            conn.execute('INSERT OR IGNORE INTO dogc_document_observations VALUES (?,?,?,?,?,?,?)',
                (identity,record['publication_date'],record['source_url'],record['pdf_sha256'],record['category'],record['event'],json.dumps(record,ensure_ascii=False)))
        for identity,evidence in self.metadata.items():
            event=conn.execute("SELECT * FROM events WHERE source_code='DOGC' AND external_id=?",(identity,)).fetchone()
            document_id=evidence.get('source_document_id',identity)
            record=self.records[document_id]['classification']
            if event is None or event['url']!=record['source_url'] or event['publication_date']!=record['publication_date']:
                raise ValueError('DOGC source evidence is not tied to its immutable event')
            evidence=dict(evidence,geographic_catalog=self.catalog_evidence)
            conn.execute('''INSERT INTO regional_public_metadata VALUES (?,?,?,?,?,?)
                ON CONFLICT(source_code,external_id) DO UPDATE SET project_key=excluded.project_key,evidence_json=excluded.evidence_json''',
                ('DOGC',identity,event['project_key'],record['publication_date'],record['source_url'],json.dumps(evidence,ensure_ascii=False)))
            geo=evidence['extraction']['geography']
            if geo['status'] in ('RESOLVED','MULTI_PROVINCE'):
                conn.execute('''INSERT INTO project_geo_enrichment
                    (project_key,municipalities_json,provinces_json,province,ccaa,status,source_code,source_url,reference_date)
                    VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(project_key) DO NOTHING''',
                    (event['project_key'],json.dumps([t['name'] for t in geo['municipalities']],ensure_ascii=False),
                     json.dumps(geo['provinces'],ensure_ascii=False),event['province'],'Cataluña',geo['status'],
                     'DOGC',record['source_url'],record['publication_date']))
        conn.commit();self._save()

    def close(self):
        self.index.session.close();self.bodies.session.close()
