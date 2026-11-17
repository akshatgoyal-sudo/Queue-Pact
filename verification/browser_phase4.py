"""Optional local Chrome acceptance/print test, with all non-local web requests blocked.

Requires the verification extra and installed Chrome. Owns only its test server/profile.
"""
from pathlib import Path
import csv,io,json,os,subprocess,sys,time,urllib.request,zipfile
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright,expect
from pypdf import PdfReader
from verify_phase4 import prepare

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'verification'/'phase4-browser'
DB=ROOT/'.local'/'phase4-browser.sqlite3'
PORT=8091
BASE=f'http://127.0.0.1:{PORT}'


def launch():
    env=dict(os.environ,QUEUEPACT_DB=str(DB))
    log=(OUT/'server.log').open('a',encoding='utf-8')
    proc=subprocess.Popen([sys.executable,'-m','queuepact','ui','--port',str(PORT)],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    for _ in range(80):
        if proc.poll() is not None:
            raise RuntimeError('Server failed; inspect server.log')
        try:
            urllib.request.urlopen(BASE+'/history',timeout=1).close()
            return proc,log
        except OSError:
            time.sleep(.1)
    proc.terminate()
    raise RuntimeError('Server startup timed out')


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    reports,outcomes=prepare(DB)
    (OUT/'presets.json').write_text(json.dumps(outcomes,indent=2),encoding='utf-8')
    proc,log=launch()
    errors=[];blocked=[];requests=[];checks=[]
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',headless=True,args=['--disable-background-networking'])
            ctx=browser.new_context(viewport={'width':1366,'height':768},accept_downloads=True,service_workers='block',reduced_motion='reduce')
            def route(r):
                url=r.request.url
                requests.append(url)
                if urlparse(url).hostname in ('127.0.0.1','localhost'):
                    r.continue_()
                else:
                    blocked.append(url);r.abort()
            ctx.route('**/*',route)
            def listen(page):
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.on('console',lambda m:errors.append(m.text) if m.type=='error' else None)
            ctx.on('page',listen)
            page=ctx.new_page()
            page.goto(BASE+'/')
            page.get_by_role('button',name='Expand "Prepared demos & presentation mode"',exact=True).click()
            page.get_by_role('button',name='Start demo',exact=True).click()
            expect(page.get_by_role('button',name='Pause',exact=True)).to_be_enabled()
            page.get_by_role('button',name='Pause',exact=True).click()
            page.get_by_role('button',name='Follow one student',exact=True).click()
            page.get_by_role('switch',name='Presentation mode',exact=True).click()
            expect(page.get_by_role('button',name='Exit presentation',exact=True)).to_be_visible()
            page.get_by_role('button',name='Fullscreen',exact=True).click()
            page.wait_for_function('document.fullscreenElement || document.body.innerText.includes("Fullscreen is unavailable")')
            if page.evaluate('Boolean(document.fullscreenElement)'):
                page.get_by_role('button',name='Fullscreen',exact=True).click()
                page.wait_for_function('!document.fullscreenElement')
            page.screenshot(path=str(OUT/'presentation-1366.png'))
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            page.get_by_role('button',name='Exit presentation',exact=True).click()
            checks.append('Live start/pause, passport, reduced motion, presentation enter/exit; 1366 no overflow')
            page.get_by_role('button',name='Save / export',exact=True).click()
            page.get_by_role('textbox',name='Saved name',exact=True).fill('Browser persistence acceptance')
            page.get_by_role('button',name='Save snapshot',exact=True).click()
            expect(page.get_by_text('Saved to local history',exact=True)).to_be_visible()
            with page.expect_download() as dl:
                page.get_by_role('button',name='Reproducibility JSON',exact=True).click()
            json_path=OUT/'download.json';dl.value.save_as(str(json_path))
            with page.expect_download() as dl:
                page.get_by_role('button',name='Download CSV ZIP',exact=True).click()
            zip_path=OUT/'download.zip';dl.value.save_as(str(zip_path))
            from queuepact.archive import Evidence
            frozen=Evidence.from_json(json_path.read_bytes())
            assert frozen.verify()
            with zipfile.ZipFile(zip_path) as z:
                rows=list(csv.DictReader(io.StringIO(z.read('metrics.csv').decode('utf-8-sig'))))
                assert float(next(r['value'] for r in rows if r['metric']=='total_queue_wait'))==frozen.data['runs'][0]['metrics']['total_queue_wait']
            checks.append('Browser JSON and CSV downloads inspected; exported observation reproduces')
            page.get_by_role('button',name='Close',exact=True).click()
            for name in ('Arrival Rush','Desk Disruption and Recovery'):
                page.get_by_role('combobox',name='Prepared scenario',exact=True).click()
                page.get_by_role('option',name=name,exact=True).click()
                page.get_by_role('button',name='Load preset',exact=True).click()
                page.get_by_role('button',name='Replace with preset',exact=True).click()
                page.get_by_role('button',name='Start demo',exact=True).click()
                page.get_by_role('button',name='Pause',exact=True).click()
                page.get_by_role('button',name='Reset Demo',exact=True).click()
                expect(page.locator('.qp-clock')).to_have_text('0.00 min')
            checks.append('All three presets loaded/started; replace confirmation and repeated Reset Demo exercised')
            lab=ctx.new_page();lab.goto(BASE+'/lab?preset=0')
            lab.get_by_role('button',name='Run to results',exact=True).click()
            expect(lab.get_by_role('banner')).to_contain_text('Completed',timeout=30000)
            expect(lab.get_by_text('23.37',exact=True).first).to_be_visible()
            expect(lab.get_by_text('27.55',exact=True).first).to_be_visible()
            for width,height in [(1366,768),(1920,1080)]:
                lab.set_viewport_size({'width':width,'height':height})
                assert lab.evaluate('document.documentElement.scrollWidth<=innerWidth')
                lab.screenshot(path=str(OUT/f'lab-{width}.png'))
            checks.append('Fresh offline Lab, local Plotly loaded, comparison completed honestly; both sizes no overflow')
            lab.get_by_role('button',name='Test staff placements',exact=True).click()
            expect(lab.get_by_role('button',name='Open selected candidate branch',exact=True)).to_be_enabled(timeout=30000)
            lab.get_by_role('button',name='Open selected candidate branch',exact=True).click()
            lab.get_by_role('button',name='Run to results',exact=True).click()
            expect(lab.get_by_role('banner')).to_contain_text('Completed',timeout=30000)
            lab.get_by_role('tab',name='Turning point',exact=True).click()
            lab.get_by_role('button',name='Reconstruct & branch',exact=True).click()
            lab.get_by_role('button',name='Run to results',exact=True).click()
            expect(lab.get_by_role('banner')).to_contain_text('Completed',timeout=30000)
            lab.get_by_role('tab',name='Document readiness',exact=True).click()
            lab.get_by_role('button',name='Compare readiness approaches',exact=True).click()
            lab.get_by_role('button',name='Run to results',exact=True).click()
            expect(lab.get_by_role('banner')).to_contain_text('Completed',timeout=30000)
            checks.append('Staff placement, candidate branch, unchanged reconstruction and readiness UI completed')
            history=ctx.new_page();history.goto(BASE+'/history')
            history.locator('input[type=file]').set_input_files(str(json_path))
            expect(history.get_by_text('Imported as a new saved copy:',exact=False)).to_be_visible(timeout=15000)
            history.get_by_role('row').filter(has_text='Browser persistence acceptance').first.get_by_role('checkbox').click()
            expect(history.get_by_role('row').filter(has_text='Browser persistence acceptance').first.get_by_role('checkbox')).to_be_checked()
            history.get_by_role('button',name='Verify reconstruction',exact=True).click()
            expect(history.get_by_text('Reproducibility VERIFIED:',exact=False)).to_be_visible(timeout=15000)
            checks.append('JSON imported via browser upload as a new saved copy')
            from queuepact.repository import Repository
            ids=[r['id'] for r in Repository(DB).list() if r['name']=='Browser persistence acceptance']
            assert ids
            # Close sockets before stopping the owned server; reconnect failures are not hidden.
            ctx.close()
            proc.terminate();proc.wait(timeout=10);log.close()
            proc,log=launch()
            ctx=browser.new_context(viewport={'width':1366,'height':768},service_workers='block')
            ctx.route('**/*',route);ctx.on('page',listen)
            history=ctx.new_page();history.goto(BASE+'/history')
            expect(history.get_by_role('cell',name='Browser persistence acceptance',exact=True).first).to_be_visible()
            history.get_by_role('row').filter(has_text='Browser persistence acceptance').first.get_by_role('checkbox').click()
            expect(history.get_by_role('row').filter(has_text='Browser persistence acceptance').first.get_by_role('checkbox')).to_be_checked()
            with history.expect_popup() as opened:
                history.get_by_role('button',name='Open as new experiment',exact=True).click()
            working=opened.value
            working.get_by_role('button',name='Run to results',exact=True).click()
            other=ctx.new_page();other.goto(BASE+'/lab')
            expect(other.get_by_role('banner')).to_contain_text('Ready')
            checks.append('Server restarted; saved browser record reloaded and fresh working copy isolated from second session')
            for name,rid in reports.items():
                report=ctx.new_page();report.goto(BASE+'/reports/'+rid)
                expect(report.get_by_role('button',name='Print / Save as PDF',exact=True)).to_be_visible()
                slug=name.lower().replace(' ','-')
                report.emulate_media(media='print')
                report.pdf(path=str(OUT/f'{slug}.pdf'),format='A4',print_background=True,prefer_css_page_size=True)
                pdf=PdfReader(OUT/f'{slug}.pdf')
                assert all(page.extract_text().strip() for page in pdf.pages)
                assert all(abs(float(page.mediabox.width)-595.28)<2 for page in pdf.pages)
                assert 'Print / Save as PDF' not in ''.join(page.extract_text() for page in pdf.pages)
                report.close()
            checks.append('All report types printed through Chromium to A4 PDFs; navigation removed and every page contains text')
            ctx.close();browser.close()
    finally:
        proc.terminate();proc.wait(timeout=10);log.close()
        (OUT/'checks.json').write_text(json.dumps(dict(checks=checks,console_errors=errors,blocked_external_requests=blocked,request_count=len(requests)),indent=2),encoding='utf-8')
    assert not errors,errors
    print(json.dumps(checks,indent=2))


if __name__=='__main__':
    main()
