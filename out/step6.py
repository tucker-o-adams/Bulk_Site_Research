import time, json, os
from playwright.sync_api import sync_playwright

LAT, LON = 39.8199842, -104.8936070
APPID = '8b0adb51996444d4879338b5529aa9cd'
ENTRY = 'https://hazards.fema.gov/femaportal/wps/portal/NFHLWMS'
VURL = 'https://hazards-fema.maps.arcgis.com/apps/webappviewer/index.html?id=%s&center=%f,%f&level=16' % (APPID, LON, LAT)
log = []; res = {}; T0 = time.time()


def L(m):
    log.append('[%6.1fs] %s' % (time.time() - T0, m)); print(log[-1], flush=True)


def dismiss(pg, tries=6):
    """Close the CBRS alert + the welcome splash, which block all other clicks."""
    n = 0
    for _ in range(tries):
        clicked = False
        for sel in ['div[role=dialog] .jimu-btn:has-text("OK")', 'button:has-text("OK")',
                    '.jimu-btn:has-text("OK")', '.dijitDialog .jimu-btn']:
            try:
                loc = pg.locator(sel)
                for i in range(min(loc.count(), 4)):
                    el = loc.nth(i)
                    if el.is_visible():
                        el.click(timeout=4000, force=True); n += 1; clicked = True
                        time.sleep(1.5)
            except Exception:
                pass
        if not clicked:
            break
    L('dismissed %d modal dialog button(s)' % n)
    return n


with sync_playwright() as p:
    br = p.chromium.launch(headless=True)
    ctx = br.new_context(viewport={'width': 1920, 'height': 1080}, accept_downloads=True)
    pg = ctx.new_page(); pg.set_default_timeout(60000)

    t = time.time()
    r = pg.goto(ENTRY, wait_until='domcontentloaded')
    L('ENTRY %s -> HTTP %s (%.1fs) - documentation page, not the viewer' % (ENTRY, r.status, time.time() - t))
    res['entry_status'] = r.status
    href = pg.eval_on_selector_all('a', "els=>{const a=els.find(e=>e.innerText.trim()=='NFHL Viewer');return a?a.href:null}")
    L('followed its "NFHL Viewer" link -> %s' % href)
    r = pg.goto(href, wait_until='domcontentloaded')
    L('%s -> redirected to %s' % (href, pg.url))
    res['followed_link'] = href; res['redirect_to'] = pg.url

    t = time.time()
    pg.goto(VURL, wait_until='domcontentloaded')
    try:
        pg.wait_for_load_state('networkidle', timeout=90000)
    except Exception:
        L('networkidle timeout (continuing)')
    pg.wait_for_selector('#esri_dijit_Search_0_input', timeout=90000)
    time.sleep(14)
    dismiss(pg)
    time.sleep(4)
    res['render_s'] = round(time.time() - t, 1)
    L('viewer loaded + map rendered (%.1fs)' % res['render_s'])
    pg.screenshot(path='out/_v_after_dismiss.png')

    # ---------- search ----------
    t = time.time(); res['search_ok'] = False
    try:
        q = '%.6f, %.6f' % (LAT, LON)
        box = pg.locator('#esri_dijit_Search_0_input')
        box.click(timeout=20000); box.fill('')
        box.type(q, delay=40)
        L('typed "%s" into the viewer search box' % q)
        time.sleep(4)
        pg.keyboard.press('Enter')
        time.sleep(14)
        L('search submitted; box reads "%s"' % box.input_value())
        pops = pg.locator('.esriPopupWrapper:visible, .esriPopup:visible').count()
        L('visible result popup elements: %d' % pops)
        res['search_ok'] = True
        res['search_popup_count'] = pops
        pg.screenshot(path='out/_v_after_search.png')
    except Exception as e:
        L('SEARCH FAILED %s: %s' % (type(e).__name__, str(e)[:220]))
    res['search_s'] = round(time.time() - t, 1)

    # ---------- screenshot at the required framing ----------
    t = time.time()
    pg.goto(VURL, wait_until='domcontentloaded')
    try:
        pg.wait_for_load_state('networkidle', timeout=90000)
    except Exception:
        pass
    time.sleep(16); dismiss(pg); time.sleep(6)
    pg.screenshot(path='out/nfhl_viewer_screenshot.png', full_page=True)
    res['screenshot_kb'] = round(os.path.getsize('out/nfhl_viewer_screenshot.png') / 1024, 1)
    L('full-page screenshot -> out/nfhl_viewer_screenshot.png (%.0f KB, %.1fs)' % (res['screenshot_kb'], time.time() - t))

    # ---------- NFHL Print Tool ----------
    t = time.time(); res['print_ok'] = False; res['print_file'] = None
    try:
        pg.locator('[title="NFHL Print Tool"]').first.click(timeout=25000)
        L('opened NFHL Print Tool')
        time.sleep(5)
        # 1) activate the pin tool (first icon button in the widget panel)
        pins = pg.locator('.jimu-widget-print .drawBox, [title*="pin" i], .esriCTPrintPin, .jimu-widget button')
        clicked_pin = False
        for sel in ['div[data-dojo-attach-point="pinBtn"]', '.esriCTPinButton', '[title="Pin"]',
                    '.jimu-widget .jimu-btn img', 'img[src*="pin"]']:
            try:
                el = pg.locator(sel).first
                if el.count() and el.is_visible():
                    el.click(timeout=6000); clicked_pin = True
                    L('clicked pin control via selector %s' % sel); break
            except Exception:
                pass
        if not clicked_pin:
            # fall back: the two small buttons under the instructions - take the first
            btns = pg.locator('div[role=dialog] button, .jimu-widget button')
            L('pin control not found by name; widget has %d buttons, clicking the first' % btns.count())
            try:
                btns.first.click(timeout=6000); clicked_pin = True
            except Exception as e:
                L('fallback pin click failed: %s' % str(e)[:120])
        res['pin_clicked'] = clicked_pin
        time.sleep(2)
        # 2) click the map centre to drop the pin
        pg.mouse.click(1150, 560)
        L('clicked map at (1150,560) to drop the print pin')
        time.sleep(6)
        pg.screenshot(path='out/_v_print_pin.png')
        # 3) press Execute
        ex = None
        for sel in ['div[role=button]:has-text("Execute")', 'button:has-text("Execute")',
                    '.jimu-btn:has-text("Execute")', 'text=Execute']:
            try:
                el = pg.locator(sel).first
                if el.count() and el.is_visible():
                    ex = el; break
            except Exception:
                pass
        if ex is None:
            L('no Execute button visible; widget body text follows')
            L(pg.inner_text('.jimu-widget, div[role=dialog]')[:600].replace('\n', ' | '))
        else:
            try:
                with pg.expect_download(timeout=150000) as dl:
                    ex.click()
                    L('clicked Execute; waiting for download')
                d = dl.value
                res['print_file'] = 'out/nfhl_viewer_print_%s' % d.suggested_filename
                d.save_as(res['print_file']); res['print_ok'] = True
                L('download saved -> %s (%d bytes)' % (res['print_file'], os.path.getsize(res['print_file'])))
            except Exception as e:
                L('no browser download event: %s' % str(e)[:160])
                time.sleep(30)
                pg.screenshot(path='out/_v_print_output.png')
                links = pg.eval_on_selector_all('a', "els=>els.map(e=>e.href).filter(h=>/\\.(pdf|png|jpg)/i.test(h))")
                L('output links: %s' % links[:4])
                if links:
                    import requests
                    rr = requests.get(links[0], timeout=240)
                    res['print_file'] = 'out/nfhl_viewer_print.' + links[0].split('?')[0].split('.')[-1]
                    open(res['print_file'], 'wb').write(rr.content)
                    res['print_ok'] = True
                    L('fetched print output -> %s (%d bytes)' % (res['print_file'], len(rr.content)))
    except Exception as e:
        L('PRINT TOOL FAILED %s: %s' % (type(e).__name__, str(e)[:300]))
    res['print_s'] = round(time.time() - t, 1)
    pg.screenshot(path='out/_v_final.png')
    br.close()

res['total_s'] = round(time.time() - T0, 1)
open('out/step6_log.txt', 'w', encoding='utf-8').write('\n'.join(log))
json.dump(res, open('out/step6.json', 'w'), indent=2)
L('TOTAL %.1fs' % res['total_s'])
