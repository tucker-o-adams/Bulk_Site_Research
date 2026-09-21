import time, json
from playwright.sync_api import sync_playwright

URL = 'https://hazards.fema.gov/femaportal/wps/portal/NFHLWMS'
log = []
t0 = time.time()
with sync_playwright() as p:
    br = p.chromium.launch(headless=True)
    ctx = br.new_context(viewport={'width': 1920, 'height': 1080})
    pg = ctx.new_page()
    pg.on('console', lambda m: log.append('console:%s:%s' % (m.type, m.text[:160])))
    try:
        r = pg.goto(URL, wait_until='domcontentloaded', timeout=90000)
        log.append('goto status=%s url=%s' % (r.status if r else None, pg.url))
    except Exception as e:
        log.append('goto FAILED %s: %s' % (type(e).__name__, str(e)[:300]))
    time.sleep(6)
    log.append('final url: %s' % pg.url)
    log.append('title: %s' % pg.title())
    pg.screenshot(path='out/_probe_landing.png', full_page=False)
    body = pg.inner_text('body')[:3000]
    log.append('--- BODY TEXT ---\n' + body)
    # collect links & iframes
    links = pg.eval_on_selector_all('a', "els=>els.map(e=>[e.innerText.trim().slice(0,60), e.href]).filter(x=>x[1])")
    log.append('--- LINKS (%d) ---' % len(links))
    for t, h in links[:40]:
        log.append('  %-45s %s' % (t, h))
    frames = [f.url for f in pg.frames]
    log.append('--- FRAMES ---\n' + '\n'.join(frames))
    br.close()
open('out/step6_probe.txt', 'w', encoding='utf-8').write('\n'.join(log))
print('\n'.join(log)[:6000])
print('\nelapsed %.1fs' % (time.time() - t0))
