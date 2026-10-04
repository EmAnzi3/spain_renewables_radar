import csv
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from app.dashboard import HTML
from app.reporting import geography_accounting, build_province_view_from_rows, write_changes
from app.collectors.sabia import events_from_detail
from test_sabia_assets import BY_CODE


class DashboardSemanticsTests(unittest.TestCase):
    def test_source_milestone_is_not_exported_as_web_publication_date(self):
        detail=dict(BY_CODE['20260236'],entry_date='2026-09-20',raw_text='Exact source')
        event=events_from_detail(detail,'FTV',detail['source_url'])[0]
        with tempfile.TemporaryDirectory() as tmp:
            output,_=write_changes([event],tmp)
            with output.open(encoding='utf-8-sig',newline='') as stream:
                row=list(csv.DictReader(stream))[0]
            self.assertEqual(row['publication_date'],'')
            self.assertEqual(row['event_date'],'2026-09-20')
            self.assertEqual(row['date_basis'],'ENTRY_DATE')

    def test_geography_accounting_does_not_hide_or_double_count_multi_province(self):
        rows=[{'province':'Madrid','provinces':['Madrid'],'technology':'PV','power_mw':10},
              {'province':None,'provinces':['Madrid','Guadalajara'],'power_mw':40},
              {'province':None,'provinces':[],'power_mw':20},
              {'province':'Cuenca','provinces':['Cuenca'],'power_mw':None,'source_group_id':'group','group_unallocated_power_mw':30},
              {'province':'Cuenca','provinces':['Cuenca'],'power_mw':None,'source_group_id':'group','group_unallocated_power_mw':30}]
        summary=geography_accounting(rows)
        self.assertEqual(summary['multi_province_known_mw'],40)
        self.assertEqual(summary['unknown_province_known_mw'],20)
        self.assertEqual(summary['source_group_unallocated_mw'],{'group':30})
        self.assertEqual(sum(r['known_mw'] for r in build_province_view_from_rows(rows)),10)

    @unittest.skipUnless(shutil.which('node'),'Node is used only for optional dashboard JS regression tests')
    def test_browser_helpers_escape_sources_filter_numbers_and_aggregate_safely(self):
        script=HTML.split('<script>',1)[1].split('</script>',1)[0]
        assertions="""
const assert=require('node:assert/strict');
assert.equal(esc('<script>&'), '&lt;script&gt;&amp;');
assert.equal(link('javascript:alert(1)','x'),'—');
assert(link('https://www.boe.es/x','<img>').includes('&lt;img&gt;'));
assert.equal(validMW({power_mw:null}),false);
assert.equal(validMW({power_mw:NaN}),false);
assert.equal(validMW({power_mw:10}),true);
const result=provinceSummary([
 {province:'Madrid',provinces:['Madrid'],technology:'PV',commercial_stage:'EARLY',power_mw:10},
 {province:'Madrid',provinces:['Madrid'],technology:'WIND',commercial_stage:'BLOCKED',power_mw:null},
 {province:'Madrid',provinces:['Madrid','Guadalajara'],technology:'PV',power_mw:100}]);
assert.equal(result.length,1);assert.equal(result[0].projects,2);
assert.equal(result[0].known_mw,10);assert.equal(result[0].projects_without_mw,1);
assert.equal(result[0].blocked,1);
"""
        prelude="const document={getElementById:()=>({}),querySelectorAll:()=>[]};const fetch=()=>new Promise(()=>{});\n"
        result=subprocess.run([shutil.which('node'),'-'],input=prelude+script+assertions,text=True,capture_output=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)

if __name__=='__main__':unittest.main()
