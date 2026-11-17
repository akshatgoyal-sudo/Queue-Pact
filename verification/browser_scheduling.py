"""Browser regression for explicit scheduling identities; private test database."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
import browser_phase4 as base
from queuepact.repository import Repository
from queuepact.archive import Evidence
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'verification'/'scheduling'/'browser';OUT.mkdir(parents=True,exist_ok=True)
base.OUT=OUT;base.DB=ROOT/'.local'/'scheduling-browser.sqlite3';base.PORT=8093;base.BASE='http://127.0.0.1:8093'

def choose(page,label,value):
 page.get_by_label(label,exact=True).click()
 page.get_by_role('option',name=value,exact=True).click()
 expect(page.get_by_role('option',name=value,exact=True)).not_to_be_visible()

def main():
 proc,log=base.launch();errors=[];checks=[]
 try:
  with sync_playwright() as p:
   browser=p.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',headless=True)
   ctx=browser.new_context(viewport={'width':1366,'height':768},accept_downloads=True)
   def listen(page):
    page.on('pageerror',lambda e:errors.append(str(e)));page.on('console',lambda m:errors.append(m.text) if m.type=='error' else None)
   ctx.on('page',listen)
   page=ctx.new_page();page.goto(base.BASE)
   page.get_by_role('button',name='Configure',exact=True).click()
   choose(page,'Scheduling policy','QueuePact v2 (experimental)')
   page.get_by_label('Students',exact=True).fill('6')
   page.get_by_role('button',name='Done',exact=True).click()
   choose(page,'Playback','20×')
   page.get_by_role('button',name='Start run',exact=True).click()
   page.get_by_role('button',name='Pause',exact=True).click()
   expect(page.get_by_text('Paused',exact=True)).to_be_visible()
   page.get_by_role('button',name='Resume',exact=True).click()
   expect(page.locator('header').get_by_text('Completed',exact=True)).to_be_visible(timeout=20000)
   expect(page.get_by_text('QueuePact v2 (experimental)',exact=True).first).to_be_visible()
   page.get_by_role('button',name='Save / export',exact=True).click()
   page.get_by_label('Saved name',exact=True).fill('Scheduling v2 evidence')
   page.get_by_role('button',name='Save snapshot',exact=True).click()
   expect(page.get_by_text('Saved immutable record',exact=False)).to_be_visible()
   with page.expect_download() as download:page.get_by_role('button',name='Reproducibility JSON',exact=True).click()
   download.value.save_as(OUT/'v2.json');evidence=Evidence.from_json((OUT/'v2.json').read_text(encoding='utf-8'))
   assert evidence.verify() and evidence.data['runs'][0]['record']['policy_version']==2
   assert evidence.data['runs'][0]['metrics']['unfinished']==0 and evidence.data['runs'][0]['metrics']['completed']==6
   with ctx.expect_page() as popup:page.get_by_role('button',name='View report',exact=True).click()
   report=popup.value;report.wait_for_load_state();expect(report.get_by_text('QueuePact v2 (experimental)',exact=True).first).to_be_visible();report.screenshot(path=str(OUT/'report.png'))
   page.get_by_role('button',name='Close',exact=True).click();page.get_by_role('button',name='Reset',exact=True).click()
   checks.append('Live v2 selection, completion, pause/resume/reset; saved JSON verifies explicit version 2; report labels experimental version')
   saved=Repository(base.DB).list()[0]['id']
   loaded=ctx.new_page();loaded.goto(base.BASE+'/lab?saved='+saved)
   expect(loaded.get_by_text('QueuePact v2 (experimental)',exact=True).first).to_be_visible()
   loaded.get_by_role('button',name='Run to results',exact=True).click()
   expect(loaded.locator('header').get_by_text('Completed',exact=True)).to_be_visible(timeout=20000)
   checks.append('Saved v2 opened as isolated working experiment and completed with v2 identity')
   for left in ('QueuePact v1','Ordinary'):
    lab=ctx.new_page();lab.goto(base.BASE+'/lab')
    choose(lab,'Left policy',left);choose(lab,'Right policy','QueuePact v2 (experimental)')
    lab.get_by_role('button',name='Start comparison',exact=True).click()
    lab.get_by_role('button',name='Run to results',exact=True).click()
    expect(lab.locator('header').get_by_text('Completed',exact=True)).to_be_visible(timeout=20000)
    expect(lab.locator('.lab-panel').get_by_text('QueuePact v2 (experimental)',exact=True).first).to_be_visible()
    assert lab.evaluate('document.documentElement.scrollWidth <= innerWidth')
    lab.screenshot(path=str(OUT/('v1-v2.png' if left=='QueuePact v1' else 'ordinary-v2.png')),full_page=True)
    checks.append(left+' vs v2 completed in two-panel layout; no horizontal overflow')
   browser.close()
 finally:
  proc.terminate();proc.wait(timeout=10);log.close()
  (OUT/'checks.json').write_text(json.dumps(dict(checks=checks,errors=errors),indent=2))
 assert not errors,errors
 print(checks)
if __name__=='__main__':main()
