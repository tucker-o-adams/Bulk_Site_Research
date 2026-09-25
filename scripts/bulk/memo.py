# -*- coding: utf-8 -*-
"""The two batch memos (outputs beside the workbook and the KMZ), both internal Word documents. MEMOS.md is the spec.

    .venv_fema/Scripts/python.exe scripts/bulk/memo.py Outputs/<batch>/ --name <Title>

  <Title>_confirmation_memo.docx   Location confirmation. (A) how sure we are that the tool has each site's location,
                                   one of five statuses (location_status.py); (B) a question, with options, for each
                                   site a person can settle. Sites already certain, and sites with too little to find,
                                   ask nothing. Exhibits only for the sites with a question (Appendix A)
  <Title>_summary_memo.docx        Portfolio summary: the narrative, the portfolio at a glance, one block per site with
                                   what the broker says beside what we found, data-handling notes, method and sources
  broker_summary.csv               one row per site: key broker-stated facts, their tags and the location status

Built only from files already on disk: the run (sites.csv, provenance.csv, run.json), the broker-text extraction
(input/: evidence_checked.csv, clues_checked.csv, sites_in.csv, extract_*.json) and the exhibits' own results
(figures/<site>_parcel_check.json, <site>_candidates.json). Every number is computed here, so the memos are
reproducible. The one hand-written part is the summary narrative, input/memo_narrative.md (written in the Claude
Code session). No scores, no GO / REVIEW / NO-GO until approved thresholds exist.
"""
import argparse, csv, json, os, re, sys
from collections import Counter, defaultdict, OrderedDict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from docx_lite import Doc          # noqa: E402
from broker_text import broker_words   # noqa: E402
import location_status as LS       # noqa: E402

TAG = {'confirmed_written': 'confirmed', 'confirmed_prescreen': 'pre-screen', 'utility_estimate': 'utility est.',
       'broker_estimate': 'broker est.', 'pending': 'pending', 'untagged': ''}
STAGE = OrderedDict([('under_contract', 'Under contract'), ('loi_or_negotiating', 'LOI / negotiating'), ('owner_identified', 'Owner identified, no terms'),
                     ('tract_identified', 'Tract identified, no terms'), ('no_site_yet', 'No site yet (searching)'), ('no_site_control', 'No site control (stated)')])
TIER = OrderedDict([('L1', 'Parcel'), ('L2', 'Point on the site'), ('L3', 'Near a named substation, intersection or landmark'),
                    ('L4', 'Within a ZIP'), ('L5', 'Within a county'), ('', 'No location')])
SITE_LEVEL = LS.SITE_LEVEL
GREY = '595959'
BOX = '☐'


def rd(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def num(v):
    try:
        return float(str(v).replace(',', ''))
    except (TypeError, ValueError):
        return None


def dist(v):
    x = num(v)
    if x is None:
        return '—'
    return f'{x:,.0f} m' if x < 1000 else f'{x / 1000:,.1f} km'


def g(v, suffix=''):
    x = num(v)
    if x is None:
        return '—' if v in (None, '') else str(v)
    return (f'{x:,.0f}' if abs(x) >= 100 or x.is_integer() else f'{x:,.1f}') + suffix


def tagged(value, tag):
    t = TAG.get(tag, tag)
    return f'{value} ({t})' if t else str(value)


class Broker:
    """Key broker-stated facts for one site, from evidence_checked.csv."""
    def __init__(self, rows):
        self.rows = rows

    def get(self, dim, fld, kinds=None):
        return [r for r in self.rows if r['dimension'] == dim and r['field'] == fld and (kinds is None or r['kind'] in kinds)]

    def first(self, dim, fld, kinds=None):
        x = self.get(dim, fld, kinds)
        return x[0] if x else None

    def mw(self):
        """(headline MW, kind, tag, text): an actual figure first, then a target/request, then an 'up to'."""
        for fld, kinds, label in (('mw', ('actual',), ''), ('mw_full', ('actual',), ''), ('mw', ('target',), 'requested '), ('mw', ('range_high',), 'up to ')):
            r = self.first('power_capacity', fld, kinds)
            if r:
                return num(r['value']), ('actual' if not label else 'request' if label.startswith('req') else 'up_to'), r['tag_norm'], f"{label}{g(r['value'])} MW"
        return None, None, None, '—'

    def timing(self):
        for fld in ('available', 'initial_available', 'full_available'):
            r = self.first('power_timing', fld)
            if r:
                full = self.first('power_timing', 'full_available')
                txt = r['value'] + (f"; full {full['value']}" if fld == 'initial_available' and full else '')
                return tagged(txt, r['tag_norm'])
        return ''

    def connection(self):
        u = self.first('power_connection', 'utility')
        kv = self.first('power_connection', 'voltage_kv')
        sub = self.first('power_connection', 'substation')
        st = self.first('power_connection', 'substation_status')
        parts = [u['value'] if u else '', f"{g(kv['value'])} kV" if kv else '',
                 (f"sub {sub['value']}" + (' (new)' if st and st['value'] == 'new_or_planned' and '(new)' not in sub['value'] else '')) if sub else '']
        return ' · '.join(p for p in parts if p)

    def fiber(self):
        s = self.first('fiber', 'status')
        if not s:
            return ''
        if s['value'] != 'quoted':
            return s['value'].replace('_', ' ')
        nrc = self.first('fiber', 'nrc_usd'); r1 = self.first('fiber', 'route1_ft'); r2 = self.first('fiber', 'route2_ft')
        c = self.first('fiber', 'carrier')
        return (f"{c['value'] if c else ''} build ${num(nrc['value']) / 1e6:,.2f}M" if nrc else 'quoted') + \
               (f"; routes {g(r1['value'])} / {g(r2['value'])} ft" if r1 and r2 else '')

    def acres(self):
        a = self.first('acreage', 'acres', ('actual',))
        if a:
            return num(a['value']), tagged(f"{g(a['value'])} ac", a['tag_norm'])
        t = self.first('acreage', 'acres', ('target',))
        return None, (f"target ~{g(t['value'])} ac" if t else '')

    def stage(self):
        r = self.first('site_control', 'stage')
        return r['value'] if r else ''

    def constraints(self):
        return [r['value'] for r in self.get('grid_constraints', 'constraint')]

    def flood_claims(self):
        return [r['value'] for r in self.get('flood_wetlands', 'claim')]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('batch')
    ap.add_argument('--name', default=None)
    a = ap.parse_args()
    b = a.batch.rstrip('/\\'); name = a.name or os.path.basename(b)
    inp = os.path.join(b, 'input')
    sites_list = rd(os.path.join(inp, 'site_list.csv'))
    ev = rd(os.path.join(inp, 'evidence_checked.csv'))
    located = {r['site_id']: r for r in rd(os.path.join(inp, 'sites_in.csv'))}
    run_sites = {r['site_id']: r for r in rd(os.path.join(b, 'sites.csv'))}
    run = json.load(open(os.path.join(b, 'run.json'), encoding='utf-8'))
    cells_info = json.load(open(os.path.join(inp, 'extract_cells.json'), encoding='utf-8'))
    check = json.load(open(os.path.join(inp, 'extract_check.json'), encoding='utf-8'))
    if not check.get('ok'):
        raise SystemExit('extract_check.py has not passed for this batch')
    narrative_path = os.path.join(inp, 'memo_narrative.md')
    narrative = open(narrative_path, encoding='utf-8').read() if os.path.exists(narrative_path) else ''

    ev_by = defaultdict(list)
    for r in ev:
        ev_by[r['site_id']].append(r)
    figdir = os.path.join(b, 'figures')

    def jload(n):
        f = os.path.join(figdir, n)
        return json.load(open(f, encoding='utf-8')) if os.path.exists(f) else None

    def pmap(sid):
        for n in (f'{sid}_parcels_site_internal.png', f'{sid}_parcels_site.png', f'{sid}_location_internal.png', f'{sid}_location.png'):
            if os.path.exists(os.path.join(figdir, n)):
                return os.path.join(figdir, n)
        return None

    def small(path, width=2000):
        """A 2000 px JPEG copy for embedding (the 4800 px PNG originals would make a ~35 MB .docx). Returns (path, (w, h))."""
        from PIL import Image
        out = os.path.join(figdir, 'memo', os.path.splitext(os.path.basename(path))[0] + '.jpg')
        if not os.path.exists(out) or os.path.getmtime(out) < os.path.getmtime(path):
            os.makedirs(os.path.dirname(out), exist_ok=True)
            im = Image.open(path).convert('RGB')
            im.thumbnail((width, width))
            im.save(out, quality=80, optimize=True)
        with Image.open(out) as im:
            return out, im.size

    ids = [s['site_id'] for s in sites_list]
    sname = {s['site_id']: s['name'] for s in sites_list}
    B = {sid: Broker(ev_by[sid]) for sid in ids}
    market = {s['site_id']: s['section'].split(' (')[0].split(' · ')[0].title().replace('Msa', 'MSA') for s in sites_list}
    tier = {sid: (located.get(sid) or {}).get('location_tier', '') for sid in ids}
    basis = {sid: (located.get(sid) or {}).get('location_basis', '') for sid in ids}
    R = lambda sid, f: (run_sites.get(sid) or {}).get(f, '')

    # ---------------------------------------------------------------- location status (location_status.py)
    st, pcs = {}, {}
    for sid in ids:
        L, br = located.get(sid, {}), B[sid]
        ba, _ = br.acres()
        pcs[sid] = jload(f'{sid}_parcel_check.json') if tier[sid] in SITE_LEVEL else None
        if tier[sid] in SITE_LEVEL and pcs[sid] and 'status' not in pcs[sid].get('verdict', {}):
            raise SystemExit(f'{sid}_parcel_check.json predates location statuses: rerun figure.py --layers parcels for it')
        st[sid] = LS.classify(tier[sid], br.stage(), bool(ba), basis[sid], L.get('location_radius_m'), pc=pcs[sid],
                              cands=jload(f'{sid}_candidates.json') if tier[sid] in ('L3', 'L4', 'L5') else None, acres=ba)
    order = list(LS.STATUS)
    by_status = OrderedDict((k, [sid for sid in ids if st[sid]['status'] == k]) for k in order)
    ask = [sid for sid in by_status['needs_input']]
    exhibits = [sid for sid in ask if pmap(sid)]
    anum = {sid: f'A.{i}' for i, sid in enumerate(exhibits, 1)}

    def slabel(sid):
        return LS.label(st[sid]['status'], st[sid].get('note'))

    def fill(sid):
        return LS.colours(st[sid]['status'])[0]

    # ---------------------------------------------------------------- numbers for the summary
    stages = Counter(B[sid].stage() for sid in ids)
    mw_rows = {sid: B[sid].mw() for sid in ids}
    mw_conf = sum(v for v, k, t, _ in mw_rows.values() if v and k == 'actual' and t == 'confirmed_written')
    mw_other = sum(v for v, k, t, _ in mw_rows.values() if v and k == 'actual' and t != 'confirmed_written')
    mw_req = sum(v for v, k, t, _ in mw_rows.values() if v and k in ('request', 'up_to'))
    by_market = defaultdict(lambda: [0, 0.0])
    for sid in ids:
        by_market[market[sid]][0] += 1
        v, k, t, _ = mw_rows[sid]
        if v and k == 'actual':
            by_market[market[sid]][1] += v
    internal = [sid for sid in ids if R(sid, 'parcel_use').startswith('INTERNAL')]
    no_control = sum(n for s_, n in stages.items() if s_ != 'under_contract')
    stamp = f"INTERNAL — TBDI · {run['run_at'][:10]} · source {cells_info['source']} (sha256 {cells_info['source_sha256'][:12]}…)"
    counts = '; '.join(f"{LS.STATUS[k]['label'] if k != 'confirmed_partial' else 'Confirmed with a carve-out or several parcels'} {len(v)}"
                       for k, v in by_status.items() if v)

    # ---------------------------------------------------------------- broker_summary.csv
    bs_cols = ['site_id', 'name', 'market', 'site_control', 'mw_headline', 'mw_kind', 'mw_tag', 'timing', 'connection', 'fiber',
               'acres_broker', 'grid_constraints', 'flood_claims', 'location_tier', 'location_basis', 'location_status', 'location_note']
    with open(os.path.join(b, 'broker_summary.csv'), 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=bs_cols); w.writeheader()
        for sid in ids:
            br = B[sid]
            v, k, t, _ = mw_rows[sid]
            w.writerow({'site_id': sid, 'name': sname[sid], 'market': market[sid], 'site_control': br.stage(), 'mw_headline': v, 'mw_kind': k, 'mw_tag': t,
                        'timing': br.timing(), 'connection': br.connection(), 'fiber': br.fiber(), 'acres_broker': br.acres()[1],
                        'grid_constraints': ' | '.join(br.constraints()), 'flood_claims': ' | '.join(br.flood_claims()),
                        'location_tier': tier[sid], 'location_basis': basis[sid], 'location_status': st[sid]['status'], 'location_note': st[sid].get('note', '')})

    # ================================================================ 1. confirmation memo
    d = Doc(f'{name} location confirmation')
    d.title_block(f'{name}: location confirmation', stamp)
    d.para('This memo does two things. It states how sure we are that the tool has the right location for each site, and it asks you to settle the '
           'locations that a short answer can settle. Sites whose location is already certain, and sites with too little information to find, need '
           'nothing from you.')
    d.para([('Bottom line: ', 'b'), (f"{len(ids)} sites. {counts}.", '')] +
           ([(f" {len(ask)} question{'s' if len(ask) != 1 else ''} for you under Needs your input.", 'b')] if ask else [(' Nothing needs your input.', 'b')]))

    d.heading('Location status', 1)
    defs = [('confirmed', "the broker's pin (or parcel number) sits in a parcel that matches the stated size, and nothing the broker says contradicts it."),
            ('confirmed_partial', 'the pin is trusted and the size difference is explained: a carve-out (stated by the broker, or probable), so the site is part '
                                  'of the parcel, or a site that spans several parcels. Parcel figures describe the parcel, not exactly the site.'),
            ('needs_input', 'borderline: the evidence points more than one way, and a person can settle it from a short list.'),
            ('not_locatable', 'too little to find the parcel: only a ZIP or county with no tract names, or a named anchor with no acreage to search by (or too '
                              'many parcels of that size).'),
            ('no_site', 'the broker says no site is identified yet: a power position with a search area. Nothing to locate.')]
    for k, txt in defs:
        f_, ink = LS.colours(k)
        lab = 'Confirmed: carve-out / several parcels' if k == 'confirmed_partial' else LS.STATUS[k]['label']
        d.banner([(lab, 'b'), (f' — {txt}', '')], f_, ink, size=17)
    rows, cells, rules = [], {}, []
    for k in order:
        for j, sid in enumerate(by_status[k]):
            if j == 0 and rows:
                rules.append(len(rows))
            tb = TIER.get(tier[sid], '')
            rows.append([f'**{sid}**', f'**{slabel(sid)}**', f"{basis[sid] or tb}", st[sid]['assessment'] +
                         (f" See Needs your input{' and Appendix ' + anum[sid] if sid in anum else ''}." if k == 'needs_input' else '')])
            cells[(len(rows) - 1, 1)] = fill(sid)
    d.table(['Site', 'Status', 'Located by', 'Why'], rows, [0.6, 1.35, 1.55, 3.5], size=15, shade_cells=cells, rule_rows=rules)

    d.heading('Needs your input', 1)
    if not ask:
        d.para('Nothing: every site is either confirmed or has too little information to locate.')
    for sid in ask:
        f_, ink = LS.colours('needs_input')
        d.banner([(f'{sid}  ', 'b'), (sname[sid], '')], f_, ink, size=22)
        d.para(st[sid]['assessment'])
        words = broker_words(b, sid)
        if words:
            d.para([('What the broker says about the location (verbatim):', 'b')], size=18)
            for lab, txt in words:
                d.bullet([(f'{lab}: ', 'i'), (f'“{txt}”', '')])
        d.para([(st[sid]['question'] or 'Is the location right?', 'b')] + ([(f'  Exhibit: Appendix {anum[sid]}.', '')] if sid in anum else []))
        for o in st[sid]['options']:
            d.para([(f'{BOX}  ', ''), (o, '')])
        d.para([('Notes: ', 'b'), ('_' * 70, '')], color='7F7F7F')

    d.heading('How the status is set', 1)
    for txt in ('A precise broker pin is trusted. When the parcel under it is within 15 % of the stated acreage, it is the site: neighbouring parcels are '
                'not offered instead.',
                'A stated site much smaller than the parcel under the pin is a carve-out of it (stated or probable); a larger one spans several parcels. '
                'Both are confirmed, noted as such: nothing contradicts the broker.',
                'A question is asked only when the evidence points more than one way and a short list can settle it: an approximate pin whose parcel does not '
                'match (every parcel of about the stated size near the pin, and near a substation the broker says the site adjoins, is listed), a substation '
                'claim that contradicts a precise pin, a site placed near a named anchor with 1–5 parcels of the stated size around it, or a site the broker '
                'names only by its tracts\' owners with 1–5 parcels under those names of about the stated size (searched in the county\'s own parcel '
                'records, within the ZIP plus 2 km). No combinations of parcels are guessed, and the tool picks none.',
                'A site known only by its ZIP or county, or by an anchor without an acreage to search by, is not locatable; a row the broker marks "no site '
                'yet" has nothing to locate.',
                'Sources: the broker list (quotes checked word for word), county and state parcel layers (TxGIO StratMap; county services for owner-name '
                'searches; licensed-county parcels are internal use only), HIFLD substations (2021), Census TIGER and geocoder, OpenStreetMap. The rules are in scripts/bulk/MEMOS.md.'):
        d.bullet(txt)

    if exhibits:
        d.landscape()
        d.heading('Appendix A: Exhibits', 1)
        d.para('One page per site with a question. The banner colour is the location status. Parcel maps: the parcel under the broker\'s coordinate in '
               'dark red, candidate parcels of the stated size in orange, lettered as in the question, the substation the broker names as a purple square; '
               'a red dot marks the pin only when the broker gave a precise one. Maps carry owner names: internal.', size=17, color=GREY)
        wl = d.usable_width_in()
        for n_, sid in enumerate(exhibits):
            if n_:
                d.page_break()
            f_, ink = LS.colours(st[sid]['status'])
            d.banner([(f"{anum[sid]}  {sid}  {sname[sid]}", 'b'), (f"   —   {slabel(sid)}", '')], f_, ink, size=24)
            sp, spx = small(pmap(sid))
            d.image(sp, min(wl, 8.6), px=spx, caption=f"{os.path.basename(pmap(sid))}: full resolution in figures/")
    out1 = os.path.join(b, f'{name}_confirmation_memo.docx')
    d.save(out1)

    # ================================================================ 2. summary memo
    d = Doc(f'{name} portfolio summary')
    d.title_block(f'{name}: portfolio summary', stamp)
    d.para([('Status: ', 'b'), ('no screening verdicts. Thresholds for this portfolio are not yet approved, so no site is scored or ranked; '
                                'this memo reports facts and their sources. Location confidence is in the separate location confirmation memo.', '')],
           color='C00000')
    d.heading('Summary', 1)
    if narrative.strip():
        for block in re.split(r'\n\s*\n', narrative.strip()):
            lines = [l for l in block.splitlines() if not l.startswith('#')]
            if lines and all(l.lstrip().startswith(('- ', '* ')) for l in lines):
                for l in lines:
                    d.bullet(l.lstrip()[2:])
            elif lines:
                d.para(' '.join(l.strip() for l in lines))
    else:
        d.para('(Narrative not written yet: add input/memo_narrative.md in the Claude Code session and rerun memo.py.)', italic=True, color='7F7F7F')

    d.heading('Portfolio at a glance', 1)
    d.bullet(f'**{len(ids)} sites** in the list: ' + ', '.join(f'{m} {n}' for m, (n, _) in by_market.items()) + '.')
    d.bullet(f'**Site control: {no_control} of {len(ids)} sites have none.** ' + '; '.join(f'{STAGE[s_]} {stages[s_]}' for s_ in STAGE if stages[s_]) + '.')
    d.bullet(f'**Location:** {counts}. Details and questions in the location confirmation memo.')
    d.bullet(f'**Broker-stated power:** {g(mw_conf)} MW stated available and confirmed in writing; {g(mw_other)} MW stated available at lower confidence '
             f'(pre-screen, utility or broker estimate); {g(mw_req)} MW requested or "up to". By market (stated available): ' +
             ', '.join(f'{m} {g(v)} MW' for m, (_, v) in by_market.items()) + '. All figures are the broker\'s; deliverable MW is not something this tool estimates.')
    nq = sum(1 for sid in ids if B[sid].first('fiber', 'status') and B[sid].first('fiber', 'status')['value'] == 'quoted')
    ngc = sum(1 for sid in ids if B[sid].constraints())
    d.bullet(f'**Fiber:** {nq} of {len(ids)} sites carry a carrier quote (broker-stated, not a proximity measure).')
    d.bullet(f'**Grid caveats:** the broker states limits beyond the MW figure (timing gates, interruptible service, upstream work) for {ngc} sites; they are '
             f'shown in each site\'s block. Silence elsewhere means not provided, not "none".')

    d.landscape()
    wl = d.usable_width_in()
    d.heading('Site by site', 1)
    d.para('One block per site: what the broker says (its confidence tag in brackets) beside what we found in free public sources. Parcel, flood, wetland and '
           'housing checks need the site itself, so they appear only for confirmed sites; for a site placed near a named substation, power distances '
           'are measured from that point (~). A blank means nothing stated or nothing measurable, not zero.', size=17, color=GREY)
    rows, cells, rules = [], {}, []
    for sid in ids:
        br, t, sl = B[sid], tier[sid], tier[sid] in SITE_LEVEL
        ok_site = sl and st[sid]['status'] in ('confirmed', 'confirmed_partial')
        v, k, tg, txt = mw_rows[sid]
        pc = pcs[sid] or {}
        sc = pc.get('substation') or {}
        sub_near = (f"nearest: {R(sid, 'sub_nearest_name')} {g(R(sid, 'sub_nearest_max_kv'))} kV, "
                    + ('the anchor' if t == 'L3' and basis[sid].startswith('HIFLD substation') else f"{dist(R(sid, 'sub_nearest_m'))}" + ('' if sl else ' ~'))) \
            if R(sid, 'sub_nearest_name') and t in SITE_LEVEL + ('L3',) else ''
        if sc.get('text'):
            sub_near = (sub_near + '. ' if sub_near else '') + sc['text']
        blk = [('Location', f"{basis[sid] or 'none'}", f'**{slabel(sid)}**'),
               ('Site control', STAGE.get(br.stage(), br.stage()), ''),
               ('Acreage', br.acres()[1], (f"parcel {g(R(sid, 'parcel_acres_gis'))} ac" + (' (internal)' if sid in internal else '')) if ok_site and R(sid, 'parcel_acres_gis') else ''),
               ('Power', (tagged(txt, tg) if tg else txt if txt != '—' else '') + (f"; {br.timing()}" if br.timing() else ''), ''),
               ('Connection', br.connection(), sub_near),
               ('Transmission', '', (f"{g(R(sid, 'tx_voltage_kv'))} kV line, {dist(R(sid, 'tx_nearest_m'))}" + ('' if sl else ' ~')) if R(sid, 'tx_nearest_m') and t in SITE_LEVEL + ('L3',) else ''),
               ('Flood', '; '.join(br.flood_claims()), f"zone {R(sid, 'fema_flood_zone') or '—'} at the pin; {g(R(sid, 'fp_sfha_pct'))} % of the parcel in the SFHA" if ok_site else ''),
               ('Wetlands', '', f"{g(R(sid, 'fp_nwi_pct'))} % of the parcel (NWI)" if ok_site and R(sid, 'fp_nwi_pct') != '' else ''),
               ('Fiber', br.fiber(), ''),
               ('Grid caveats', '\n'.join(br.constraints()), ''),
               ('Homes within 1 mi', '', g(R(sid, 'hu_within_1mi')) if ok_site and R(sid, 'hu_within_1mi') != '' else '')]
        first = True
        for topic, said, found in blk:
            if not (said or found) and topic != 'Location':
                continue
            if first:
                if rows:
                    rules.append(len(rows))
                rows.append([f"**{sid}**\n{market[sid]}", topic, said, found])
                cells[(len(rows) - 1, 3)] = fill(sid)
                first = False
            else:
                rows.append(['', topic, said, found])
    widths = [1.0, 1.15, 3.6, 3.75]
    d.table(['Site', 'Topic', 'Broker says', 'We found'], rows, [w * wl / sum(widths) for w in widths], size=15, shade_cells=cells, rule_rows=rules)

    d.portrait()
    d.heading('Data handling notes', 1)
    notes = []
    if internal:
        notes.append(f"**Licensed-county parcels:** {', '.join(internal)}. The parcel comes from a licensed county dataset: internal use only; register the "
                     f"county's own service before any figure from it leaves TBDI.")
    blank = [sid for sid in ids if tier[sid] in SITE_LEVEL and R(sid, 'parcel_status') == 'ok' and not R(sid, 'parcel_owner').strip()]
    if blank:
        notes.append(f"**No owner in the parcel record:** {', '.join(blank)}.")
    for sid in ids:
        m = re.search(r'ZIP (\d{5}), not the stated (\d{5})', (located.get(sid) or {}).get('location_check', ''))
        if m and tier[sid] in SITE_LEVEL:
            notes.append(f"**{sid}:** the broker's pin is in ZIP {m.group(1)}, not the stated {m.group(2)} (mailing ZIPs often differ from Census ZIP areas; "
                         f"not treated as a contradiction).")
        for o in ((located.get(sid) or {}).get('location_other') or '').split(' | '):
            mm = re.match(r'Census geocoder: (.+) is ([\d,]+) m away', o)
            if mm and num(mm.group(2)) > 150 and tier[sid] in SITE_LEVEL:
                notes.append(f"**{sid}:** the listing address geocodes {mm.group(2)} m from the broker's pin (rural address points are interpolated; "
                             f"the pin is used).")
    for n_ in notes or ['None.']:
        d.bullet(n_)

    d.heading('Method, sources and gaps', 1)
    d.heading('How the broker list was read', 2)
    d.bullet(f"{cells_info['cells']} cells read from {cells_info['sites']} sites through a checked column map "
             f"({cells_info['cells_copied']} cells are identical across sites: market-level, not site-level, evidence).")
    d.bullet(f"{check['evidence_rows']} evidence rows and {check['clue_rows']} location clues extracted in-session; every quote was verified "
             f"word for word against its source cell (extract_check.py, {len(check['errors'])} errors, {len(check['warnings'])} warnings).")
    d.bullet('Confidence tags normalised to one scale: confirmed in writing > confirmed at pre-screen > utility estimate (verbal) > broker estimate > pending.')
    d.bullet('Locations: coordinates as given; named existing substations looked up in HIFLD; intersections computed from Census TIGER roads; '
             'landmarks from OpenStreetMap; ZIP and county centroids otherwise. Each candidate is checked against the stated county and ZIP.')
    d.heading('Sources (free / public)', 2)
    rows = [[n, p['source'], str(p.get('vintage') or ''), ', '.join(f'{k} {v}' for k, v in p['status_counts'].items())] for n, p in run['producers'].items()]
    d.table(['Producer', 'Source', 'Vintage', 'Status counts'], rows, [1.0, 3.6, 0.8, 1.6], size=15)
    d.heading('Not in this tool', 2)
    for t in ('Deliverable MW / power availability: proximity facts only; capacity is a utility study.',
              'Jurisdictional wetland or flood determinations: NWI and FEMA NFHL are screening layers.',
              'County politics, incentives, moratoriums; planned data-centre developments (Baxtel is context only, not copied).',
              'Screening verdicts: none until thresholds for this portfolio are approved.'):
        d.bullet(t)
    out2 = os.path.join(b, f'{name}_summary_memo.docx')
    d.save(out2)
    print(f"wrote {out1} ({len(ask)} questions, {len(exhibits)} exhibits), {out2} and {os.path.join(b, 'broker_summary.csv')}")
    for k, v in by_status.items():
        shown = [f"{s_} ({st[s_]['note']})" if st[s_].get('note') else s_ for s_ in v]
        print(f"  {LS.label(k)}{' (partial)' if k == 'confirmed_partial' else ''}: {', '.join(shown) or '-'}")


if __name__ == '__main__':
    main()
