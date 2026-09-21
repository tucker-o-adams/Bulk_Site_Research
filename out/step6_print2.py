import time, json, os
from playwright.sync_api import sync_playwright

LAT, LON = 39.8199842, -104.8936070
VURL = ('https://hazards-fema.maps.arcgis.com/apps/webappviewer/index.html?'
        'id=8b0adb51996444d4879338b5529aa9cd&center=%f,%f&level=16' % (LON, LAT))
log = []; res = {}; T0 = time.time()


def L(m):
    log.append('[%6.1fs] %s' % (time.time() - T0, m)); print(log[-1], flush=True)


def dismiss(pg):
    n = 0
    for _ in range(6):
        hit = False
        loc = pg.locator('button:has-text("OK"), .jimu-btn:has-text("OK")')
        for i in range(min(loc.count(), 5)):
            try:
                el = loc.nth(i)
                if el.is_visible():
                    el.click(timeout=4000, force=True); n += 1; hit = True; time.sleep(1.2)
            except Exception:
                pass
        if not hit:
            break
    return n


with sync_playwright() as p:
    br = p.chromium.launch(headless=True)
    ctx = br.new_context(viewport={'width': 1920, 'height': 1080}, accept_downloads=True)
    pg = ctx.new_page(); pg.set_default_timeout(60000)
    net = []
    pg.on('response', lambda r: net.append([r.status, r.url[:190]])
          if any(k in r.url for k in ('GPServer', 'FIRMette', 'firmette', '.pdf')) else None)
    pg.goto(VURL, wait_until='domcontentloaded')
    try:
        pg.wait_for_load_state('networkidle', timeout=90000)
    except Exception:
        pass
    time.sleep(18); L('dismissed %d dialogs' % dismiss(pg)); time.sleep(6)

    # open the panel and CONFIRM it is open
    for attempt in range(3):
        pg.locator('[title="NFHL Print Tool"]').first.click(timeout=25000, force=True)
        time.sleep(7)
        open_now = pg.locator(':text("To print NFHL FIRMette or Full FIRM")').first
        vis = open_now.count() > 0 and open_now.is_visible()
        L('attempt %d: print panel visible = %s' % (attempt + 1, vis))
        if vis:
            break
    pg.screenshot(path='out/_pr_panel.png')

    # enumerate every visible element in the panel with a bounding box
    ctrls = pg.eval_on_selector_all(
        'div,button,input,span,a',
        """els=>els.filter(e=>{const r=e.getBoundingClientRect();
             return r.width>10&&r.height>8&&r.left<430&&r.top>90&&r.top<900&&e.children.length<3;})
           .map(e=>{const r=e.getBoundingClientRect();
             return {t:(e.innerText||e.value||'').trim().slice(0,26),id:e.id||'',
                     x:Math.round(r.left+r.width/2),y:Math.round(r.top+r.height/2),
                     w:Math.round(r.width),h:Math.round(r.height)};})
           .filter(o=>o.t||o.id)""")
    L('panel controls:')
    for c in ctrls:
        L('   %s' % json.dumps(c))
    res['panel_controls'] = ctrls

    # set the coordinates in the two NumberTextBoxes
    try:
        pg.fill('#dijit_form_NumberTextBox_0', str(LAT), timeout=10000)
        pg.fill('#dijit_form_NumberTextBox_1', str(LON), timeout=10000)
        L('set lat/lon boxes to %s / %s' % (LAT, LON))
        res['coords_set'] = True
    except Exception as e:
        L('could not set lat/lon boxes: %s' % str(e)[:180]); res['coords_set'] = False

    # click the Run control by its measured position
    run = [c for c in ctrls if c['t'].lower() == 'run']
    res['print_ok'] = False; res['print_file'] = None
    if not run:
        L('NO "Run" control present in the panel')
    else:
        c = run[0]
        L('Run control at (%d,%d)' % (c['x'], c['y']))
        try:
            with pg.expect_download(timeout=180000) as dl:
                pg.mouse.click(c['x'], c['y'])
                L('clicked Run; waiting for a download')
            d = dl.value
            res['print_file'] = 'out/nfhl_viewer_print_%s' % d.suggested_filename
            d.save_as(res['print_file']); res['print_ok'] = True
            L('DOWNLOAD -> %s (%d bytes)' % (res['print_file'], os.path.getsize(res['print_file'])))
        except Exception as e:
            L('no download: %s' % str(e)[:170])
            time.sleep(60)
            pg.screenshot(path='out/_pr_after_run.png')
            L('panel text now: %s' % pg.inner_text('body')[:400].replace('\n', ' | '))
            links = pg.eval_on_selector_all('a', "els=>els.map(e=>e.href).filter(h=>/\\.(pdf|png|jpg)/i.test(h))")
            L('pdf/img links: %s' % links[:5])
            if links:
                import requests
                rr = requests.get(links[0], timeout=240)
                res['print_file'] = 'out/nfhl_viewer_print.' + links[0].split('?')[0].split('.')[-1]
                open(res['print_file'], 'wb').write(rr.content); res['print_ok'] = True
                L('FETCHED -> %s (%d bytes)' % (res['print_file'], len(rr.content)))
    L('FIRMette/GP network calls: %s' % json.dumps(net[-8:]))
    res['net'] = net[-15:]
    pg.screenshot(path='out/_pr_final.png')
    br.close()

res['total_s'] = round(time.time() - T0, 1)
open('out/step6_print2_log.txt', 'w', encoding='utf-8').write('\n'.join(log))
json.dump(res, open('out/step6_print2.json', 'w'), indent=2)
L('TOTAL %.1fs' % res['total_s'])
