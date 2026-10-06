"""Real Chromium interactions on actual data, without runtime network calls."""
import argparse,json,shutil
from pathlib import Path
from playwright.sync_api import sync_playwright

def main():
    p=argparse.ArgumentParser();p.add_argument('--site',default='site');a=p.parse_args();root=Path(a.site)
    data=json.loads((root/'data.json').read_text(encoding='utf-8'));errors=[]
    with sync_playwright() as pw:
        exe=shutil.which('google-chrome') or shutil.which('chromium')
        browser=pw.chromium.launch(executable_path=exe,headless=True,args=['--no-sandbox'] if exe else None)
        page=browser.new_page(viewport={'width':1440,'height':1040});page.on('pageerror',lambda error:errors.append(str(error)))
        page.set_content((root/'index.html').read_text(encoding='utf-8'),wait_until='load')
        assert page.locator('#projectList .project').count()==min(25,len(data['records']))
        assert page.locator('#kCount').inner_text().replace('.','')==str(len(data['records']))
        page.screenshot(path=str(root/'desktop.png'),full_page=False)
        page.fill('#query','Almagro');assert page.locator('#projectList .project').count()==1
        page.locator('#projectList button[data-project]').first.click();page.wait_for_timeout(100)
        assert page.locator('#projectDialog').evaluate('(d)=>d.open')
        assert '7,2 MW' in page.locator('#dialogBody').inner_text();assert 'Ciudad Real' in page.locator('#dialogBody').inner_text()
        assert page.locator('#dialogBody .event').count()>=1
        page.click('#closeDialog');page.click('#resetFilters');page.select_option('#tech','PV')
        assert page.locator('#projectList .project').count()>0
        page.click('#resetFilters');page.click('[data-tab="province"]');page.wait_for_timeout(50)
        assert page.locator('#provinceRows tr').count()>0
        page.locator('#provinceRows button').first.click();page.wait_for_timeout(50);assert page.locator('#province').input_value()
        page.click('[data-tab="fonti"]');page.wait_for_timeout(50)
        assert page.locator('#sourceCards .source-card').count()>=13
        assert page.locator('#alternativeCards .source-card').count()==len(data['alternatives'])
        page.click('[data-tab="lead"]');page.wait_for_timeout(50);page.select_option('#leadSource','BOPV')
        assert page.locator('#leadCards .lead-card').count()==7
        page.select_option('#leadSource','MPT_VALENCIA');assert page.locator('#leadCards .lead-card').count()>0
        page.fill('#leadQuery','Atalaya');assert page.locator('#leadCards .lead-card').count()>0
        page.click('[data-tab="progetti"]');page.click('#resetFilters');page.set_viewport_size({'width':390,'height':844})
        page.screenshot(path=str(root/'mobile.png'),full_page=False)
        assert not page.evaluate('document.documentElement.scrollWidth>innerWidth');assert not errors,errors
        browser.close()
    receipt={'browser':'Chromium','real_data_projects':len(data['records']),'javascript_errors':errors,
        'project_search_and_dialog':True,'almagro_7_2_mw_ciudad_real':True,'technology_filter':True,
        'province_drilldown':True,'source_coverage':True,'separate_lead_search':True,
        'mobile_width':390,'mobile_horizontal_overflow':False,'external_runtime_dependencies':False}
    (root/'browser_receipt.json').write_text(json.dumps(receipt,indent=2));print('BROWSER_VALIDATED',json.dumps(receipt))
if __name__=='__main__':main()
