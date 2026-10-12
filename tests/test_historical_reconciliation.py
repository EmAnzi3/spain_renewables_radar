import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from app.historical_backfill import scan_source
from app.parser import ParsedEvent
from scripts.reconcile_historical_batches import validate_bundle,aggregate,output_reports


def event(day, identity, name='FV La Puebla 3', project_key='unique-fv'):
    return ParsedEvent('BOE',identity,str(day),name,
        'https://www.boe.es/diario_boe/txt.php?id='+identity,
        'Official full text '+name,'PV',150.08,name,'Jinko Greenfield Spain 1, S.L.',
        'PFot-EXACT','Huelva','Andalucía','PRIOR_AUTH','AUTHORIZED',project_key)

class Stub:
    def __init__(self,events):
        self.events=events
    def collect_day(self,day):
        return self.events[day]
    def close(self):
        pass

class HistoricalAggregateTests(unittest.TestCase):
    def make_bundle(self,root,day,identity='BOE-A-2026-13561',name='FV La Puebla 3',project_key='single'):
        events={day:[event(day,identity,name,project_key)]}
        scan_source(source='BOE',start=day,end=day,out=root,collector=Stub(events),clock=date(2026,10,12))
        folder=root/('BOE_'+str(day)+'_'+str(day))
        self.assertTrue(validate_bundle(folder)[0]['complete'])
        return folder

    def test_identical_id_from_repeated_source_window_is_one_observation(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=date(2026,6,22);root=Path(tmp)
            f=self.make_bundle(root/'first',d)
            g=self.make_bundle(root/'second',d)
            result=aggregate([f,g])
            self.assertEqual(result['scanned_bundle_count'],2)
            self.assertEqual(result['unique_official_event_ids'],1)
            self.assertEqual(result['provisional_named_project_groups'],1)
            self.assertFalse(result['all_regions_certified'])
            output_reports(result,root/'report')
            self.assertTrue((root/'report/index.html').exists())

    def test_same_identity_with_different_legal_text_is_quarantined(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=date(2026,6,22);root=Path(tmp)
            f=self.make_bundle(root/'first',d)
            g=self.make_bundle(root/'second',d)
            s=g/'events.json'
            data=json.loads(s.read_text());data[0]['raw_text']+=' CHANGED'
            s.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,'digest'):
                validate_bundle(g)
            # Original-day digest is binding; do not accept tampered replay.

    def test_distinct_sources_or_ids_never_deduplicated_by_similar_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=date(2026,6,22);root=Path(tmp)
            f=self.make_bundle(root/'first',d,'BOE-A-2026-1',project_key='key-1')
            g=self.make_bundle(root/'second',d,'BOE-A-2026-2',project_key='key-2')
            result=aggregate([f,g])
            self.assertEqual(result['unique_official_event_ids'],2)
            self.assertEqual(result['provisional_named_project_groups'],2)

    def test_conflicting_names_same_key_are_explicitly_reviewed(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=date(2026,6,22);root=Path(tmp)
            f=self.make_bundle(root/'first',d,'BOE-A-2026-1',name='FV La Puebla 3',project_key='shared')
            g=self.make_bundle(root/'second',d,'BOE-A-2026-2',name='FV La Puebla 4',project_key='shared')
            result=aggregate([f,g])
            self.assertEqual(result['unique_official_event_ids'],2)
            self.assertEqual(result['provisional_named_project_groups'],0)
            self.assertEqual(len(result['project_identity_conflicts']),1)

    def test_missing_or_extra_event_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=date(2026,6,22);root=Path(tmp)
            f=self.make_bundle(root,d)
            (f/'events.json').write_text('[]')
            with self.assertRaisesRegex(ValueError,'count'):validate_bundle(f)

    def test_duplicate_bundle_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=date(2026,6,22);root=Path(tmp)
            f=self.make_bundle(root,d)
            with self.assertRaisesRegex(ValueError,'Duplicate'):aggregate([f,f])
