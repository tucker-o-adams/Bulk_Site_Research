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
        for sel in ['button:has-text("OK")', '.jimu-btn:has-text("OK")']:
            loc = pg.locator(sel)
            for i in range(min(loc.count(), 4)):
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
    reqs = []
    pg.on('response', lambda r: reqs.append((r.status, r.url)) if ('GPServer' in r.url or 'FIRMETTE' in r.url.upper()
                                                                  or r.url.lower().endswith('.pdf')) else None)
    pg.goto(VURL, wait_until='domcontentloaded')
    try:
        pg.wait_for_load_state('networkidle', timeout=90000)
    except Exception:
        pass
    time.sleep(16); L('dismissed %d dialogs' % dismiss(pg)); time.sleep(5)

    pg.locator('[title="NFHL Print Tool"]').first.click(timeout=25000)
    L('opened NFHL Print Tool'); time.sleep(6)

    # inspect the widget DOM
    dump = pg.eval_on_selector_all(
        '.jimu-widget input, .jimu-widget div[role=button], .jimu-widget .jimu-btn, .jimu-widget a',
        "els=>els.map((e,i)=>({i,tag:e.tagName,id:e.id||'',cls:(e.className||'').toString().slice(0,45),"
        "txt:(e.innerText||e.value||'').trim().slice(0,28),vis:!!(e.offsetParent)}))")
    L('widget controls:')
    for d in dump:
        if d['vis'] or d['id']:
            L('   %s' % json.dumps(d))

    # fill lat/lon directly
    filled = False
    for latsel, lonsel in [('#input_lat', '#input_lon'), ('input[id*=lat]', 'input[id*=lon]')]:
        try:
            a = pg.locator(latsel).first; b = pg.locator(lonsel).first
            if a.count() and b.count():
                a.fill(str(LAT), timeout=8000); b.fill(str(LON), timeout=8000)
                filled = True; L('filled %s=%s  %s=%s' % (latsel, LAT, lonsel, LON)); break
        except Exception as e:
            L('fill via %s failed: %s' % (latsel, str(e)[:120]))
    res['coords_filled'] = filled

    # pin tool then map click (belt and braces)
    try:
        pin = pg.locator('.jimu-widget img[src*="pin" i], .jimu-widget [class*="pin" i]').first
        if pin.count() and pin.is_visible():
            pin.click(timeout=6000); L('clicked pin tool'); time.sleep(2)
            pg.mouse.click(1150, 560); L('clicked map to place pin'); time.sleep(6)
    except Exception as e:
        L('pin step: %s' % str(e)[:150])

    pg.screenshot(path='out/_v_print_ready.png')

    # click Run
    res['print_ok'] = False; res['print_file'] = None
    try:
        run = pg.locator('.jimu-widget :text-is("Run"), div[role=button]:has-text("Run"), .jimu-btn:has-text("Run")').first
        L('Run control visible: %s' % (run.count() and run.is_visible()))
        try:
            with pg.expect_download(timeout=180000) as dl:
                run.click(timeout=15000); L('clicked Run, awaiting download')
            d = dl.value
            res['print_file'] = 'out/nfhl_viewer_print_%s' % d.suggested_filename
            d.save_as(res['print_file']); res['print_ok'] = True
            L('DOWNLOAD -> %s (%d bytes)' % (res['print_file'], os.path.getsize(res['print_file'])))
        except Exception as e:
            L('no download event: %s' % str(e)[:200])
            time.sleep(45)
            pg.screenshot(path='out/_v_print_output.png')
            try:
                out_tab = pg.locator(':text-is("Output")').first
                if out_tab.count():
                    out_tab.click(timeout=8000); L('switched to Output tab'); time.sleep(8)
                    pg.screenshot(path='out/_v_print_outputtab.png')
                    L('output tab text: %s' % pg.inner_text('.jimu-widget')[:500].replace('\n', ' | '))
            except Exception as e2:
                L('output tab: %s' % str(e2)[:150])
            links = pg.eval_on_selector_all('a', "els=>els.map(e=>e.href).filter(h=>/\\.(pdf|png|jpg)/i.test(h))")
            L('pdf/png links in DOM: %s' % links[:5])
            L('GP/PDF network responses seen: %s' % json.dumps(reqs[-12:]))
            if links:
                import requests
                rr = requests.get(links[0], timeout=240)
                res['print_file'] = 'out/nfhl_viewer_print.' + links[0].split('?')[0].split('.')[-1]
                open(res['print_file'], 'wb').write(rr.content); res['print_ok'] = True
                L('FETCHED -> %s (%d bytes)' % (res['print_file'], len(rr.content)))
    except Exception as e:
        L('RUN FAILED %s: %s' % (type(e).__name__, str(e)[:250]))
    res['network'] = reqs[-20:]
    res['total_s'] = round(time.time() - T0, 1)
    pg.screenshot(path='out/_v_print_final.png')
    br.close()

open('out/step6_print_log.txt', 'w', encoding='utf-8').write('\n'.join(log))
json.dump(res, open('out/step6_print.json', 'w'), indent=2)
L('TOTAL %.1fs' % res['total_s'])
