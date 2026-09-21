import time
from playwright.sync_api import sync_playwright

log = []
targets = [
    ('msc_nfhl', 'https://msc.fema.gov/nfhl'),
    ('geoplatform', 'https://hazards-fema.maps.arcgis.com/apps/webappviewer/index.html?id=8b0adb51996444d4879338b5529aa9cd'),
]
with sync_playwright() as p:
    br = p.chromium.launch(headless=True)
    for tag, url in targets:
        t0 = time.time()
        ctx = br.new_context(viewport={'width': 1920, 'height': 1080})
        pg = ctx.new_page()
        try:
            r = pg.goto(url, wait_until='domcontentloaded', timeout=120000)
            log.append('[%s] goto status=%s' % (tag, r.status if r else None))
        except Exception as e:
            log.append('[%s] goto FAILED %s: %s' % (tag, type(e).__name__, str(e)[:250]))
            ctx.close(); continue
        try:
            pg.wait_for_load_state('networkidle', timeout=60000)
        except Exception as e:
            log.append('[%s] networkidle timeout (continuing)' % tag)
        time.sleep(8)
        log.append('[%s] final url: %s' % (tag, pg.url))
        log.append('[%s] title: %s' % (tag, pg.title()))
        pg.screenshot(path='out/_probe_%s.png' % tag)
        # inputs
        ins = pg.eval_on_selector_all('input,textarea',
              "els=>els.map(e=>[e.id,e.name,e.type,e.placeholder,e.className].map(v=>v||'').join(' | '))")
        log.append('[%s] INPUTS (%d):' % (tag, len(ins)))
        for i in ins[:25]:
            log.append('    ' + i)
        btns = pg.eval_on_selector_all('button,[role=button],a[title]',
              "els=>els.map(e=>((e.title||'')+' / '+(e.getAttribute('aria-label')||'')+' / '+(e.innerText||'').trim().slice(0,40)).trim()).filter(s=>s.replace(/[\\/ ]/g,'').length>0)")
        log.append('[%s] BUTTONS (%d): %s' % (tag, len(btns), ' ;; '.join(btns[:35])))
        log.append('[%s] elapsed %.1fs' % (tag, time.time() - t0))
        ctx.close()
    br.close()
open('out/step6_probe2.txt', 'w', encoding='utf-8').write('\n'.join(log))
print('\n'.join(log))
