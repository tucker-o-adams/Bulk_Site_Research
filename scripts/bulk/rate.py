# -*- coding: utf-8 -*-
"""Rate every site in a batch (design_site_rating.md, method in rating_rules.py): the seven dimension scores with
their confidence, evidence and reason, the screeners, the indicated priority, the named adjustments and the assigned
priority. Writes <batch>/ratings.csv.

    .venv_fema/Scripts/python.exe scripts/bulk/rate.py Outputs/<batch>/

Reads what the pipeline already has: input/evidence_checked.csv (broker facts and tags), broker_summary.csv (location
status, from memo.py), sites.csv (our checks). Judgement readings the rubric needs and code cannot make (zoning class,
local news, named upgrades, site-control calls, named adjustments) come from input/rating_readings.json, written in
session. The FCC fiber-provider proxy is queried (cached) for sites without a fiber quote.
"""
import argparse, csv, json, math, os, re, sys, urllib.parse
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from memo import Broker, rd, num                                              # noqa: E402
from rating_rules import (power_score, capped, indicated_priority, assigned_priority,   # noqa: E402
                          METHOD_VERSION, IMPORTANT, SUPPORTING)
from cache import Cache, coord_key                                            # noqa: E402

CACHE = os.path.join(os.path.dirname(os.path.dirname(HERE)), 'data', 'cache')
FCC = ('https://services8.arcgis.com/peDZJliSvYims39Q/arcgis/rest/services/'
       'FCC_Broadband_Data_Collection_December_2024_View/FeatureServer/5/query')
TYPICAL = {'substation': (3e6, 8e6), 'transformer': (0.3e6, 2e6)}      # 2025-26 typical costs (design note, Investment)
SEASON = {'spring': 4, 'summer': 7, 'fall': 10, 'autumn': 10, 'winter': 1}
DIMS = ('power', 'investment', 'land', 'site_control', 'community', 'connectivity', 'market')
# the thresholds the sensitivity check moves (rating_sensitivity.py); the defaults are the method's values
PARAMS = {'c0_months': 12, 'c1_months': 36, 'full_mw': 5, 'mid_mw': 3, 'land_ac_per_mw': 0.5, 'texas_audit': True}


def months_until(text, as_of):
    """Months from as_of to the date in a broker timing text; 0 for 'immediate'; None when no date can be read."""
    t = (text or '').lower()
    if re.search(r'\bimmediate|\bnow\b', t):
        return 0
    m = re.search(r'\bq([1-4])\s*(20\d\d)', t)
    if m:
        y, mo = int(m.group(2)), {1: 2, 2: 5, 3: 8, 4: 11}[int(m.group(1))]
    else:
        m = re.search(r'\b(spring|summer|fall|autumn|winter)\b[^0-9]*(20\d\d)', t) or re.search(r'\b(end)-(20\d\d)', t)
        if m:
            y, mo = int(m.group(2)), SEASON.get(m.group(1), 12)
        else:
            m = re.search(r'(20\d\d)\s*[-–]\s*(\d\d)\b', t)                 # '2027-28' / '2030-31': the later year
            if m:
                y, mo = int(m.group(1)[:2] + m.group(2)), 6
            else:
                m = re.search(r'(20\d\d)', t)
                if not m:
                    return None
                y, mo = int(m.group(1)), 6
    return max(0, (y - as_of.year) * 12 + (mo - as_of.month))


def _certainty(months, tag, date_tag, requested, timing_text):
    if months is None:
        return 'C2' if requested and re.search(r'near-term|study', timing_text or '', re.I) else 'C3' if requested else 'C2'
    if months > PARAMS['c1_months']:
        return 'C3'
    if requested:
        return 'C2'
    if tag == 'confirmed_written' and date_tag == 'confirmed_written' and months <= PARAMS['c0_months']:
        return 'C0'
    if tag in ('confirmed_written', 'confirmed_prescreen', 'utility_estimate'):
        return 'C1'                               # MW from the utility, date credible (or broker-dated but within the window)
    return 'C2'


def rate_power(br, as_of):
    """(score, confidence, MW counted, reason). Amount x certainty grid (rating_rules.power_score). Phased power: each
    phase is scored on the MW available by its date, and the best phase counts (design note, Power: 'phased power
    scores on the MW available by each date')."""
    mw, kind, tag, txt = br.mw()
    if mw is None:
        return None, 'none', None, 'no MW stated'
    requested = kind in ('request', 'up_to')
    phases = []                                   # (MW, timing evidence row)
    full = br.first('power_timing', 'full_available') or br.first('power_timing', 'available')
    if full:
        phases.append((mw, full))
    init_t, init_mw = br.first('power_timing', 'initial_available'), br.first('power_capacity', 'mw_initial', ('actual',))
    if init_t and init_mw:
        phases.append((num(init_mw['value']), init_t))
    if not phases:
        phases.append((mw, None))
    best = None
    for p_mw, t in phases:
        months = months_until(t['value'], as_of) if t else None
        c = _certainty(months, tag, t['tag_norm'] if t else '', requested, (t or {}).get('value'))
        s = power_score(p_mw, c, full_mw=PARAMS['full_mw'], mid_mw=PARAMS['mid_mw'])
        cand = (s or 0, p_mw, c, months, t)
        if best is None or cand[0] > best[0]:
            best = cand
    s, p_mw, c, months, t = best
    conf = {'C0': 'high', 'C1': 'medium'}.get(c, 'low')
    when = f"{t['value']} (~{months} mo)" if t and months is not None else (t['value'] if t else 'no date')
    phase = f" (phase: {p_mw:g} MW)" if p_mw != mw else ''
    return s, conf, mw, f"{txt} [{tag or 'untagged'}]; {when}{phase} -> {c}"


def fcc_fiber(la, ln, cache):
    q = {'geometry': f'{ln},{la}', 'geometryType': 'esriGeometryPoint', 'inSR': 4326, 'spatialRel': 'esriSpatialRelIntersects',
         'distance': 2000, 'units': 'esriSRUnit_Meter', 'outFields': 'UniqueProvidersFiber', 'returnGeometry': 'false', 'f': 'json'}
    resp, _, err = cache.get_json('fiber', coord_key(la, ln, 'fcc_bdc_h3_2km'), FCC + '?' + urllib.parse.urlencode(q))
    if err:
        return None
    return max([f['attributes'].get('UniqueProvidersFiber') or 0 for f in (resp or {}).get('features', [])] or [0])


def rate_batch(b):
    """Rate every site of a batch folder; returns the ratings.csv rows."""
    inp = os.path.join(b, 'input')
    readings = json.load(open(os.path.join(inp, 'rating_readings.json'), encoding='utf-8'))
    as_of = date.fromisoformat(readings['as_of'])
    ev_by = {}
    for r in rd(os.path.join(inp, 'evidence_checked.csv')):
        ev_by.setdefault(r['site_id'], []).append(r)
    summ = {r['site_id']: r for r in rd(os.path.join(b, 'broker_summary.csv'))}
    S = {r['site_id']: r for r in rd(os.path.join(b, 'sites.csv'))}
    ids = list(summ)
    cache = Cache(CACHE)
    rows = []
    for sid in ids:
        br, s, st = Broker(ev_by.get(sid, [])), S.get(sid, {}), summ[sid]['location_status']
        confirmed = st in ('confirmed', 'confirmed_partial')
        out, why = {}, {}
        # ---- Power
        ps, pc, mw_counted, pr = rate_power(br, as_of)
        out['power'], why['power'] = (ps, pc), pr
        div = max(2.0, mw_counted or 0)
        # ---- Investment to ready
        items, usd, kinds = [], 0.0, set()
        nrc = br.first('fiber', 'nrc_usd')
        if nrc:
            usd += num(nrc['value']); items.append(f"fiber build ${num(nrc['value']) / 1e6:,.2f}M"); kinds.add('fiber')
        for v, unit, note in readings.get('known_costs', {}).get(sid, []):
            usd += v * (div if unit == 'per_mw' else 1); items.append(note); kinds.add('utility')
        unknown_cost = False
        for k, note in readings.get('named_upgrades', {}).get(sid, []):
            if k in TYPICAL:
                lo, hi = TYPICAL[k]
                usd += (lo + hi) / 2; items.append(f"{note}: typical ${lo / 1e6:g}-{hi / 1e6:g}M"); kinds.add('typical')
            else:
                unknown_cost = True; items.append(note)
        if items:
            per = usd / div
            sc = 5 if per <= 0.1e6 else 4 if per <= 0.25e6 else 3 if per <= 1e6 else 2 if per <= 3.4e6 else 1
            conf = 'medium' if 'utility' in kinds and 'typical' not in kinds and not unknown_cost else 'low'
            out['investment'] = (sc, conf)
            why['investment'] = f"${per / 1e6:,.2f}M/MW over {div:g} MW: " + '; '.join(items) + (' (+ costs not stated)' if unknown_cost else '')
        else:
            out['investment'], why['investment'] = (None, 'none'), 'nothing stated'
        # ---- Land and buildability (slope / soils not measured yet: acreage only, cap 4)
        ba, _ = br.acres()
        note = summ[sid].get('location_note', '')
        carve = 'carve-out' in note
        parent_expo = ((num(s.get('fp_sfha_pct')) or 0) + (num(s.get('fp_nwi_pct')) or 0)) / 100
        target = mw_counted or 0                    # v1.0: land need from the MW counted in Power, not a broker "target"
        need = max(1.0, PARAMS['land_ac_per_mw'] * target)
        if confirmed or (ba and (st != 'no_site' or sid in readings.get('land_from_stated', []))):
            acres = ba if (ba and st != 'confirmed') else num(s.get('parcel_acres_gis')) or ba
            # v1.0: a carve-out whose position in the parent is unknown keeps its stated acres (the parent's flood share is noted)
            expo = parent_expo if confirmed and not carve else 0
            build = acres * (1 - min(1, expo)) if acres else None
            if build is None:
                out['land'], why['land'] = (None, 'none'), 'no acreage'
            else:
                ratio = build / need
                sc = 4 if ratio >= 1 else 3
                conf = 'medium' if confirmed else 'low'
                out['land'] = (sc, conf)
                why['land'] = (f"buildable {build:,.1f} ac ({acres:,.1f} ac less {100 * expo:,.0f} % flood / wetland) vs need {need:,.1f} ac "
                               f"({target:g} MW): {ratio:,.1f}x; slope / soils not measured"
                               + (f"; carve-out: parent parcel {100 * parent_expo:,.0f} % flood / wetland, position not stated" if carve else '')
                               + ('' if confirmed else '; site not confirmed, exposure not checked'))
        else:
            out['land'], why['land'] = (None, 'none'), 'no site'
        # ---- Site control
        stage = br.stage()
        if sid in readings.get('site_control', {}):
            sc, note = readings['site_control'][sid]
            out['site_control'], why['site_control'] = (sc, 'medium'), note
        else:
            q = ' '.join(r['quote'] for r in br.get('site_control', 'stage'))
            sc = {'under_contract': 5, 'owner_identified': 3, 'tract_identified': 3, 'no_site_yet': 1, 'no_site_control': 1}.get(stage)
            if stage == 'loi_or_negotiating':
                sc = 4 if re.search(r'\bLOI\b', q) else 3
            out['site_control'] = (sc, 'medium' if sc else 'none')
            why['site_control'] = f"{stage}: \"{q}\""
        # ---- Community and entitlements
        cr = readings.get('community', {}).get(sid, {})
        zc, news = cr.get('zoning'), cr.get('news', 'none')
        if zc or news != 'none':
            homes = num(s.get('hu_within_0_5mi')) if confirmed else None
            near = [num(s.get(f)) for f in ('school_nearest_m', 'worship_nearest_m', 'hospital_nearest_m', 'nursing_home_nearest_m')
                    if confirmed and s.get(f)]
            rec = min(near) if near else (None if not confirmed else 99999)
            if news == 'moratorium':
                sc = 1
            elif zc == 'rezoning' or news == 'negative' or (rec is not None and rec <= 305) or (homes is not None and homes > 500):
                sc = 2
            elif zc in ('conditional', 'unclear') or news == 'mixed' or (homes is not None and homes > 100):
                sc = 3
            elif (zc in ('by_right', 'no_zoning') and rec is not None and rec > 805 and homes is not None and homes <= 25):
                sc = 5
            else:
                sc = 4
            # v1.0 confidence: receptors on a confirmed site are our measure (high); zoning follows its evidence tag
            # ("no zoning authority" is a legal fact, high); the lower applies. Sourced local news is medium or better.
            ztag = (br.first('zoning_neighbours', 'zoning') or {}).get('tag_norm', '')
            zconf = 'high' if zc == 'no_zoning' or ztag == 'confirmed_written' else 'low' if zc == 'unclear' else 'medium'
            order = ['none', 'low', 'medium', 'high']
            conf = zconf if confirmed else min(zconf, 'medium', key=order.index)     # not confirmed: capped at 4
            if news in ('moratorium', 'negative'):
                conf = max(conf, 'medium', key=order.index)
            out['community'] = (sc, conf)
            rtxt = 'no receptor within the search radius' if rec == 99999 else f"nearest receptor {rec:,.0f} m" if rec is not None else ''
            why['community'] = (f"{zc or 'zoning not stated'}; news {news}" + (f"; {rtxt}, {homes:g} homes in 0.5 mi" if confirmed and rec is not None and homes is not None else '; receptors not checked (site not confirmed)')
                                + (f" ({cr['note']})" if cr.get('note') else ''))
        else:
            out['community'], why['community'] = (None, 'none'), 'nothing stated'
        # ---- Connectivity
        fs = br.first('fiber', 'status')
        if fs and fs['value'] == 'quoted':
            carriers = {r['value'] for r in br.get('fiber', 'carrier')}
            routes = bool(br.first('fiber', 'route2_ft'))
            level = (br.first('fiber', 'quote_level') or {}).get('value', '')
            sc = 5 if len(carriers) >= 2 else 4 if routes else 3
            conf = 'medium' if re.search(r'1|desktop', level, re.I) or not level else 'high'
            out['connectivity'], why['connectivity'] = (sc, conf), f"{len(carriers)} carrier(s) quoted ({', '.join(carriers)}), {'two routes' if routes else 'one route'}, {level or 'level not stated'}"
        else:
            n = fcc_fiber(float(s['lat']), float(s['lng']), cache) if s.get('lat') else None
            if n is None:
                out['connectivity'], why['connectivity'] = (None, 'none'), 'no quote; FCC proxy unavailable'
            else:
                out['connectivity'] = (3 if n >= 2 else 2 if n == 1 else 1, 'low')
                why['connectivity'] = f"no quote; FCC proxy: {n} fiber provider(s) within 2 km" + ('' if confirmed else ' of the placed point')
        # ---- Market position
        m1 = num(s.get('metro_1m_nearest_m')); m250 = num(s.get('metro_250k_nearest_m')); hub = num(s.get('dc_hub_nearest_m'))
        if m1 is not None or m250 is not None:
            km1 = m1 / 1000 if m1 is not None else 9e9; km250 = m250 / 1000 if m250 is not None else 9e9; kh = hub / 1000 if hub is not None else 9e9
            sc = (5 if km1 <= 10 and kh <= 25 else 4 if km1 <= 25 and kh <= 50 else 3 if km1 <= 50 or km250 <= 25 else 2 if km1 <= 100 else 1)
            out['market'] = (sc, 'high' if confirmed else 'medium')
            why['market'] = f"1M+ metro {km1:,.0f} km, hub {kh:,.0f} km" + ('' if confirmed else ' (from the placed point)')
        else:
            out['market'], why['market'] = (None, 'none'), 'not measured'
        # ---- Screeners
        scr = {'site_risk': 'not_assessed', 'control_blocked': 'passed'}
        clear = (num(s.get('parcel_acres_gis')) or 0) * (1 - min(1, parent_expo))
        if st == 'confirmed' or (st == 'confirmed_partial' and not carve):
            # v1.0: a multi-parcel site passes when the parcel we checked clears the minimum on its own
            scr['site_risk'] = 'failed' if clear < 1.0 and st == 'confirmed' else 'passed' if clear >= 1.0 else 'not_assessed'
        elif carve and clear < 1.0:
            scr['site_risk'] = 'failed'              # the whole parent parcel fails
        # ---- priority
        ind, reasons, flags = indicated_priority(out, scr)
        adj = [tuple(x) for x in readings.get('adjustments', {}).get(sid, [])]
        audit_mw = readings.get('audit_mw', {}).get(sid, mw_counted or 0)   # v1.0: MW per interconnection request
        if PARAMS['texas_audit'] and audit_mw >= 25:
            adj.append((-1, f'Texas grid audit: {audit_mw:g} MW request (>= 25 MW) while the PUCT / ERCOT audit is open'))
        asg = assigned_priority(ind, adj)
        row = {'site_id': sid, 'location_status': st, 'method_version': METHOD_VERSION, 'as_of': readings['as_of']}
        for d in DIMS:
            sc_, cf = out[d]
            row[f'{d}_score'] = capped(sc_, cf) if sc_ is not None else ''
            row[f'{d}_conf'] = cf
            row[f'{d}_reason'] = why[d]
        row.update(screener_site_risk=scr['site_risk'], screener_control=scr['control_blocked'], indicated=ind,
                   indicated_reasons=' | '.join(reasons), flags=' | '.join(flags),
                   adjustments=' | '.join(f"{'+' if d > 0 else '-'}1 {r}" for d, r in adj), assigned=asg)
        rows.append(row)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('batch')
    a = ap.parse_args()
    b = a.batch.rstrip('/\\')
    rows = rate_batch(b)
    cols = list(rows[0])
    with open(os.path.join(b, 'ratings.csv'), 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(rows)
    print(f"{'site':7} {'status':18} " + ' '.join(f'{d[:5]:>5}' for d in DIMS) + '  indicated  -> assigned')
    for r in rows:
        print(f"{r['site_id']:7} {r['location_status']:18} " + ' '.join(f"{str(r[d + '_score']) or 'U':>5}" for d in DIMS)
              + f"  {r['indicated']:10} -> {r['assigned']}")
    print(f"wrote {os.path.join(b, 'ratings.csv')}")


if __name__ == '__main__':
    main()
