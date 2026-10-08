# -*- coding: utf-8 -*-
"""The two batch memos (outputs beside the workbook and the KMZ), both internal Word documents. MEMOS.md is the spec.

    .venv_fema/Scripts/python.exe scripts/bulk/memo.py Outputs/<batch>/ --name <Title>

  <Title>_confirmation_memo.docx   Location confirmation. (A) how sure we are that the tool has each site's location,
                                   one of five statuses (location_status.py); (B) a question, with options, for each
                                   site a person can settle. Sites already certain, and sites with too little to find,
                                   ask nothing. Exhibits only for the sites with a question (Appendix A)
  <Title>_summary_memo.docx        Portfolio summary: the summary is the fixed topics, one section each (Priority ratings,
                                   Location confidence, Power, Fiber, Proximity, Neighbors, Flood, Ownership, Caveats and
                                   other); every table by market with a totals row; appendices: site by site, ownership and
                                   data handling, method and sources, ratings by site. MEMOS.md §3
  broker_summary.csv               one row per site: key broker-stated facts, their tags and the location status

Built only from files already on disk: the run (sites.csv, provenance.csv, run.json), the broker-text extraction
(input/: evidence_checked.csv, clues_checked.csv, sites_in.csv, extract_*.json) and the exhibits' own results
(figures/<site>_parcel_check.json, <site>_candidates.json). Every number is computed here, so the memos are
reproducible. The one hand-written part is the summary narrative, input/memo_narrative.md (written in the Claude
Code session). The priority ratings come from <batch>/ratings.csv (rate.py), refused unless rating_check.py passes.
No GO / REVIEW / NO-GO until approved thresholds exist.
"""
import argparse, csv, json, os, re, sys
from collections import Counter, defaultdict, OrderedDict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from docx_lite import Doc          # noqa: E402
from broker_text import broker_words   # noqa: E402
import location_status as LS       # noqa: E402
from batch_paths import support, publish   # noqa: E402
from broker_facts import TAG_FULL, STAGE, Broker, rd, num, g, tagged, market_of   # noqa: E402  (the broker wording, shared with excel.py)

TIER = OrderedDict([('L1', 'Parcel'), ('L2', 'Point on the site'), ('L3', 'Near a named substation, intersection or landmark'),
                    ('L4', 'Within a ZIP'), ('L5', 'Within a county'), ('', 'No location')])
SITE_LEVEL = LS.SITE_LEVEL
# the summary memo's fixed sections, in order - locked across reports (MEMOS.md §3); each takes a takeaway from input/memo_narrative.md
SUMMARY_SECTIONS = ('Priority ratings', 'Location confidence', 'Power', 'Fiber', 'Proximity', 'Neighbors', 'Flood', 'Ownership',
                    'Caveats and other')
PRIORITY_ORDER = ('High', 'Medium', 'Low', 'Insufficient information', 'Screened out')
PRIORITY_FILL = {'High': 'C6EFCE', 'Medium': 'FFEB9C', 'Low': 'F4CCCC', 'Insufficient information': 'E7E6E6', 'Screened out': 'BFBFBF'}
SCORE_FILL = {'5': 'C6EFCE', '4': 'E2EFDA', '3': 'FFF2CC', '2': 'FCE4D6', '1': 'F4CCCC', 'U': 'EDEDED'}
RATING_DIMS = (('power', 'Power'), ('investment', 'Invest-\nment'), ('land', 'Land'), ('site_control', 'Site\ncontrol'),
               ('community', 'Commu-\nnity'), ('connectivity', 'Connec-\ntivity'), ('market', 'Market'))
GREY = '595959'
# American spelling in everything a reader sees (Tucker, 2026-09-28): both memos are scanned for these after writing
BRITISH = re.compile(r'(?i)\b(\w*(?:centre|neighbour|colour|metre|licence|favour|behaviour|programme|catalogue|judgement)\w*|grey|'
                     r'(?:normal|organ|recogn|summar|priorit|minim|util|character|standard|categor|final|emphas)is(?:e|ed|es|ing|ation)|'
                     r'analys(?:e|ed|ing)|labelled|modelled|travelled|whilst|amongst)\b')
BOX = '☐'


def dist(v):
    x = num(v)
    if x is None:
        return '—'
    return f'{x:,.0f} m' if x < 1000 else f'{x / 1000:,.1f} km'


def save(d, path):
    """A primary output (batch_paths.publish): the previous version moves to Archive/; when it is open in Word (locked),
    the new one is written beside it as '<name> (new).docx'."""
    return publish(os.path.dirname(path), os.path.basename(path), d.save)


def british_words(path):
    """British spellings in a written .docx (BRITISH), for a warning."""
    import zipfile
    x = re.sub(r'<[^>]+>', ' ', zipfile.ZipFile(path).read('word/document.xml').decode('utf-8'))
    return sorted({m.group(0) for m in BRITISH.finditer(x)})


def narrative_sections(text):
    """input/memo_narrative.md split by '## <Section>' (MEMOS.md §5); one block per summary topic (SUMMARY_SECTIONS)."""
    secs, cur = {}, 'Summary'
    for line in (text or '').splitlines():
        m = re.match(r'##\s+(.+)', line)
        if m:
            cur = m.group(1).strip()
            continue
        if not line.startswith('#'):
            secs.setdefault(cur, []).append(line)
    joined = {k: '\n'.join(v).strip() for k, v in secs.items()}
    return {k: v for k, v in joined.items() if v}


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
    run_sites = {r['site_id']: r for r in rd(support(b, 'sites.csv'))}
    prov = {(r['site_id'], r['field']): r for r in rd(support(b, 'provenance.csv'))}
    run = json.load(open(support(b, 'run.json'), encoding='utf-8'))
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
    market = {s['site_id']: market_of(s['section']) for s in sites_list}
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
    with open(support(b, 'broker_summary.csv', write=True), 'w', newline='', encoding='utf-8-sig') as f:
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
    for txt in ('A precise broker pin is trusted. When the parcel under it is within 15 % of the stated acreage, it is the site: neighboring parcels are '
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
        d.para('One page per site with a question. The banner color is the location status. Parcel maps: the parcel under the broker\'s coordinate in '
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
    out1 = save(d, os.path.join(b, f'{name}_confirmation_memo.docx'))
    if british_words(out1):
        print(f"  confirmation memo: British spellings: {', '.join(british_words(out1))}")

    # ---------------------------------------------------------------- priority ratings (rate.py -> ratings.csv; rating_check.py); after broker_summary.csv, which rate.py reads
    rpath = support(b, 'ratings.csv')
    ratings = {r['site_id']: r for r in rd(rpath)} if os.path.exists(rpath) else {}
    if ratings:
        from rating_check import check_rows, row_inputs
        from rating_rules import priority_causes
        errs, review = check_rows(list(ratings.values()), {sid: st[sid]['status'] for sid in ids})
        errs += [f"{sid}: not rated" for sid in ids if sid not in ratings]
        if errs:
            raise SystemExit('ratings.csv fails rating_check.py (re-run rate.py, then fix):\n  ' + '\n  '.join(errs))
    else:
        review = []
        print('  summary memo: no ratings.csv - run rate.py, then memo.py again')
    rvers = sorted({r['method_version'] for r in ratings.values()})
    ras_of = sorted({r['as_of'] for r in ratings.values()})

    # ================================================================ 2. summary memo (MEMOS.md §3)
    # An overview for TBDI of what the portfolio offers. Fixed sections, same order every batch. Each opens with Claude's
    # takeaway (input/memo_narrative.md) and carries one small computed table as its evidence; detail is in the appendices.
    nsec = narrative_sections(narrative)
    missing_narr = [s_ for s_ in SUMMARY_SECTIONS if s_ not in nsec and s_ != 'Priority ratings']   # Priority ratings is all computed
    confirmed = [sid for sid in ids if tier[sid] in SITE_LEVEL and st[sid]['status'] in ('confirmed', 'confirmed_partial')]
    markets = list(by_market)
    n = len(ids)

    def bullets_of(section):
        """The '- ' lines of a section in input/memo_narrative.md; any other text is reported and left out (MEMOS.md §5)."""
        out, loose = [], []
        for line in nsec.get(section, '').splitlines():
            s_ = line.strip()
            (out if s_.startswith(('- ', '* ')) else loose if s_ else []).append(s_[2:] if s_.startswith(('- ', '* ')) else s_)
        if loose:
            print(f"  summary memo: '{section}' has text that is not a bullet; left out (the summary line is computed): {loose[0][:70]}")
        return out

    def say(section, lead, extra=()):
        """The section's fixed summary line (computed from a template, MEMOS.md §3) in bold, then its bullets: the session's
        bullets from input/memo_narrative.md, then any computed ones."""
        d.para([(lead, 'b')])
        bl = bullets_of(section) + list(extra)
        if section not in nsec and not extra:
            d.para(f'(Bullets not written: add "## {section}" to input/memo_narrative.md in the Claude Code session.)', italic=True, color='7F7F7F')
        for x in bl:
            d.bullet(x)

    def of(k, m, what):
        return f"{k} of {m} {what}"

    def kmr(xs):
        xs = sorted(x for x in xs if x is not None)
        return '—' if not xs else f"{xs[0]:,.0f} km" if round(xs[0]) == round(xs[-1]) else f"{xs[0]:,.0f}–{xs[-1]:,.0f} km"

    def note(txt):
        d.para(txt, size=16, color=GREY)

    def vals(sid, dim, fld):
        return [r['value'] for r in B[sid].get(dim, fld)]

    def rng(xs, fmt=lambda x: g(x)):
        xs = sorted(x for x in xs if x is not None)
        return '—' if not xs else fmt(xs[0]) if xs[0] == xs[-1] else f'{fmt(xs[0])}–{fmt(xs[-1])}'

    def km(x):
        return 'inside' if x == 0 else '<0.1 km' if x < 0.05 else f'{x:,.0f} km' if x >= 10 else f'{x:,.1f} km'

    def near(sid, fld):
        """A nearest-feature distance, or 'none within X km' when the source confirmed there is none in its search radius."""
        if R(sid, fld):
            return dist(R(sid, fld))
        pv = prov.get((sid, fld)) or {}
        m_ = re.search(r'within (\d+) m', pv.get('method', '') + ' ' + pv.get('note', ''))
        return f"none within {int(m_.group(1)) / 1000:g} km" if pv.get('status') == 'absent' and m_ else '—'

    def first_power(sid):
        """'now' or a year from the broker's availability text, else None."""
        tv = B[sid].first('power_timing', 'available') or B[sid].first('power_timing', 'initial_available')
        if not tv:
            return None
        if re.search(r'immediate|now\b', tv['value'], re.I):
            return 'now'
        m_ = re.search(r'\b(20\d\d)\b', tv['value'])
        return m_.group(1) if m_ else None

    def when(xs):
        xs = [x for x in xs if x]
        if not xs:
            return '—'
        ys = sorted(x for x in xs if x != 'now')
        lo = 'now' if 'now' in xs else ys[0]
        hi = ys[-1] if ys else 'now'
        return lo if lo == hi else f'{lo}–{hi}'

    def mw_split(ss):
        """(confirmed in writing, pre-screen or estimate, requested / up to) MW over sites."""
        c = [0.0, 0.0, 0.0]
        for sid in ss:
            v_, k_, t_, _ = mw_rows[sid]
            if v_:
                c[2 if k_ in ('request', 'up_to') else 0 if t_ == 'confirmed_written' else 1] += v_
        return c

    def mwtxt(x):
        return g(x) if x else '—'

    def cnt(x):
        return str(x) if x else '—'

    def by_msa(row_fn, total_fn):
        """Every summary table: one row per market (MSA), then a totals row (MEMOS.md §3)."""
        rows = [[f'**{m}**'] + row_fn([sid for sid in ids if market[sid] == m]) for m in markets]
        rows.append(['**Total**'] + [f'**{x}**' if x not in ('', '—') else x for x in total_fn(ids)])
        return rows

    fiber_q = lambda sid: (B[sid].first('fiber', 'status') or {}).get('value') == 'quoted'
    f1 = lambda sid, fld: num((B[sid].first('fiber', fld) or {}).get('value'))

    d = Doc(f'{name} portfolio summary')
    d.title_block(f'{name}: portfolio summary', stamp)
    d.para([('Status: ', 'b'), ('no screening verdicts. Thresholds for this portfolio are not yet approved; this memo describes what the portfolio offers. '
                                'The priority ratings are our internal attractiveness ratings (rating method '
                                f"{', '.join(rvers) or 'not run'}, draft: some thresholds still to confirm with TBDI). "
                                'Everything else is the broker\'s unless marked as our check.', '')], color='C00000')
    if missing_narr:
        print(f"  summary memo: no takeaway for {', '.join(missing_narr)} (input/memo_narrative.md)")

    # ---- Summary: one section per fixed topic (SUMMARY_SECTIONS), nothing above them; every table by market with a totals row
    d.heading('Summary', 1)

    # ---- Priority ratings (our rating, design_site_rating.md; counts of the assigned priority)
    d.heading('Priority ratings', 2)
    seg = OrderedDict((p_, defaultdict(list)) for p_ in PRIORITY_ORDER)
    for sid in ids:
        if sid in ratings:
            p_, cs_ = priority_causes(*row_inputs(ratings[sid])); c_ = ' → '.join(cs_)
            seg[p_][c_].append(sid)
    ptot = {p_: sum(len(v) for v in seg[p_].values()) for p_ in PRIORITY_ORDER}
    d.para([(' · '.join(f"{p_}: {ptot[p_]}" for p_ in PRIORITY_ORDER) if ratings else 'Not rated.', 'b')])
    for p_ in PRIORITY_ORDER:
        d.bullet([(f"{ptot[p_]} {p_}", 'b')])
        for c_, ss in sorted(seg[p_].items(), key=lambda kv: -len(kv[1])):
            d.bullet(f"{len(ss)} {c_}: {', '.join(ss)}", level=1)
    prow = lambda ms: [str(len(ms))] + [cnt(sum(1 for sid in ms if (ratings.get(sid) or {}).get('assigned') == p_)) for p_ in PRIORITY_ORDER]
    rows = by_msa(prow, prow)
    cells = {(i, 2 + j): PRIORITY_FILL[p_] for i in range(len(rows)) for j, p_ in enumerate(PRIORITY_ORDER)}
    d.table(['Market', 'Rows', 'High', 'Medium', 'Low', 'Insufficient\ninformation', 'Screened out'], rows,
            [1.6, 0.5, 0.8, 0.8, 0.8, 1.1, 0.95], size=15, shade_cells=cells)
    if ratings:
        note(f"Our rating (method {', '.join(rvers)}, as of {', '.join(ras_of)}; design_site_rating.md). Power sets the ceiling; weak important "
             f"dimensions step it down; caps and named adjustments follow. Counts are the assigned priority; under each, sites are grouped by every "
             f"step that moved them, in order. {len(review)} site(s) where the assigned priority differs from the indicated one go to a second review. "
             f"Scores by site: Appendix D; evidence and confidence for every score: ratings.csv.")
    else:
        note('Not rated for this batch: run rate.py, then memo.py again.')

    # ---- Location confidence (brief)
    d.heading('Location confidence', 2)
    say('Location confidence', of(sum(1 for sid in ids if st[sid]['status'] in ('confirmed', 'confirmed_partial')), n, 'rows confirmed on the map.'))
    keys = list(LS.STATUS)
    rows = by_msa(lambda ms: [str(len(ms))] + [cnt(sum(1 for sid in ms if st[sid]['status'] == k_)) for k_ in keys],
                  lambda ms: [str(len(ms))] + [cnt(sum(1 for sid in ms if st[sid]['status'] == k_)) for k_ in keys])
    cells = {(i, 2 + j): LS.colours(k_)[0] for i in range(len(rows)) for j, k_ in enumerate(keys)}
    d.table(['Market', 'Rows', 'Confirmed', 'Confirmed: carve-out /\nseveral parcels', 'Needs\nconfirmation', 'Not locatable', 'No site yet'], rows,
            [1.6, 0.5, 0.85, 1.25, 0.95, 0.9, 0.95], size=15, shade_cells=cells)

    # ---- Power
    d.heading('Power', 2)
    say('Power', f"{g(mw_conf + mw_other) or 0} MW stated available ({g(mw_conf) or 0} confirmed in writing); {g(mw_req) or 0} MW requested.")

    def power_row(ms):
        c = mw_split(ms)
        return [str(len(ms)), mwtxt(c[0]), mwtxt(c[1]), mwtxt(c[2]), rng([mw_rows[sid][0] for sid in ms if mw_rows[sid][0]]),
                when([first_power(sid) for sid in ms]), rng([num(x) for sid in ms for x in vals(sid, 'power_cost', 'cents_per_kwh')], lambda x: f'{x:.1f}')]
    d.table(['Market', 'Rows', 'MW confirmed\nin writing', 'MW pre-screen\n/ estimate', 'MW requested\n/ up to', 'MW per row', 'First power', '¢/kWh'],
            by_msa(power_row, power_row), [1.55, 0.45, 0.9, 0.95, 0.9, 0.75, 0.8, 0.7], size=15)
    note('All broker-stated. Deliverable MW is a utility study; this tool does not estimate it.')

    # ---- Fiber
    d.heading('Fiber', 2)
    say('Fiber', 'Quoted on ' + of(sum(1 for sid in ids if fiber_q(sid)), n, 'rows.'))

    def fiber_row(ms):
        q = [sid for sid in ms if fiber_q(sid)]
        return [f"{len(q)} of {len(ms)}", ', '.join(Counter(x for sid in q for x in vals(sid, 'fiber', 'carrier'))) or '—',
                rng([f1(sid, 'nrc_usd') for sid in q], lambda x: f'${x / 1e6:,.1f}M'), rng([f1(sid, 'mrc_usd') for sid in q], lambda x: f'${x / 1e3:,.1f}K'),
                rng([max(f1(sid, 'route1_ft') or 0, f1(sid, 'route2_ft') or 0) or None for sid in q], lambda x: f'{x:,.0f} ft')]
    d.table(['Market', 'Quoted', 'Carrier', 'Build (NRC)', 'Monthly (MRC)', 'Longer route'], by_msa(fiber_row, fiber_row), [1.7, 0.8, 0.9, 1.2, 1.2, 1.2], size=16)
    note('Broker-stated carrier quotes, not a proximity measure.')

    # ---- Proximity (our check; every row, measured from the placed point where the site is not confirmed)
    d.heading('Proximity', 2)
    kmc = lambda f: [num(R(sid, f)) / 1000 for sid in confirmed if R(sid, f) != '']
    say('Proximity', f"Confirmed sites: {kmr(kmc('metro_1m_nearest_m'))} from a 1M+ metro and {kmr(kmc('dc_nearest_m'))} from the nearest data center."
        if confirmed else 'No confirmed sites: distances are from placed points only.')

    def prox_row(ms):
        kmv = lambda sid, f: num(R(sid, f)) / 1000 if R(sid, f) != '' else None
        return [str(len(ms)), f"{sum(1 for sid in ms if sid in confirmed)} / {sum(1 for sid in ms if sid not in confirmed)}",
                rng([kmv(sid, 'metro_1m_nearest_m') for sid in ms], km), rng([kmv(sid, 'dc_nearest_m') for sid in ms], km),
                rng([kmv(sid, 'dc_hub_nearest_m') for sid in ms], km), rng([num(R(sid, 'dc_count_within_50km')) for sid in ms])]
    d.table(['Market', 'Rows', 'From site /\nplaced point', 'To 1M+ metro', 'Nearest data\ncenter', 'Nearest hub\n(20+ networks)', 'Data centers\nwithin 50 km'],
            by_msa(prox_row, prox_row), [1.6, 0.5, 0.9, 1.05, 1.05, 1.05, 0.85], size=15)
    note('Our check: Census 2020 urban areas (distance to the edge; "inside" = within it); PeeringDB data-center facilities. For rows without a confirmed '
         'site the distance is from where the site was placed (a named substation, an intersection or a ZIP center): market context, not a site measure.')

    # ---- Neighbors (our check, confirmed sites only; no table)
    d.heading('Neighbors', 2)
    say('Neighbors', of(sum(1 for sid in confirmed if (num(R(sid, 'hu_within_1mi')) or 0) > 100), len(confirmed),
                        'confirmed sites have more than 100 homes within 1 mile.'))
    note('Our check on the confirmed sites: Census 2020 housing, NCES schools, HIFLD places of worship, CMS hospitals and nursing homes. Per-site figures in Appendix A.')

    # ---- Flood (our check, confirmed sites only; no table)
    d.heading('Flood', 2)
    say('Flood', of(sum(1 for sid in confirmed if (num(R(sid, 'fp_sfha_pct')) or 0) > 0), len(confirmed),
                    'confirmed sites have part of the parcel in the FEMA flood zone.'))
    note('Our check on the confirmed sites (FEMA NFHL, USFWS NWI): screening layers, not determinations. For a carve-out or multi-parcel site the figures '
         'describe the parcel under the pin. Per-site figures in Appendix A.')

    # ---- Ownership (site control)
    d.heading('Ownership', 2)
    pk = [sid for sid in confirmed if B[sid].stage() in ('under_contract', 'loi_or_negotiating') and mw_rows[sid][1] == 'actual'
          and mw_rows[sid][2] == 'confirmed_written' and fiber_q(sid)]
    if not any(x.startswith('**Partial control:**') for x in bullets_of('Ownership')):
        print("  summary memo: Ownership needs a '- **Partial control:** ...' bullet (or '... None.') in input/memo_narrative.md")
    say('Ownership', of(sum(1 for sid in ids if B[sid].stage() in ('under_contract', 'loi_or_negotiating')), n,
                        'rows are under contract or at LOI / negotiating.'),
        [f"**Complete packages** (confirmed site, contract or LOI, MW confirmed in writing, fiber quote): {', '.join(pk) or 'None'}."])
    stg = list(STAGE)
    orow = lambda ms: [str(len(ms))] + [cnt(sum(1 for sid in ms if B[sid].stage() == s_)) for s_ in stg]
    d.table(['Market', 'Rows', 'Under\ncontract', 'LOI /\nnegotiating', 'Owner\nidentified', 'Tract\nidentified', 'No site yet', 'No site\ncontrol'],
            by_msa(orow, orow), [1.6, 0.5, 0.8, 0.9, 0.85, 0.85, 0.8, 0.75], size=15)
    note('Broker-stated site control. Owner of record on the confirmed sites: Appendix B.')

    # ---- Caveats and other
    d.heading('Caveats and other', 2)
    kc = len(bullets_of('Caveats and other'))
    say('Caveats and other', f"{kc} caveat{'' if kc == 1 else 's'} affect{'s' if kc == 1 else ''} the headline figures.")
    note('Every broker statement behind these is in Appendix A.')

    # ================================================================ appendices
    d.landscape()
    wl = d.usable_width_in()
    d.heading('Appendix A: Site by site', 1)
    note('One row per site, grouped by market. Broker-stated except Location (our status) and the three "ours" columns (our checks; Flood and Neighbors on '
         'confirmed sites only; Proximity from the placed point where the site is not confirmed, marked "placed").')
    rows, cells, rules = [], {}, []
    for m in markets:
        if rows:
            rules.append(len(rows))
        for sid in [s_ for s_ in ids if market[s_] == m]:
            br = B[sid]
            v_, k_, t_, txt = mw_rows[sid]
            ok = sid in confirmed
            kmv = lambda f: km(num(R(sid, f)) / 1000) if R(sid, f) != '' else '—'
            prox = f"metro {kmv('metro_1m_nearest_m')}\nDC {kmv('dc_nearest_m')}; hub {kmv('dc_hub_nearest_m')}" + ('' if ok else '\n(placed)')
            fl = (f"zone {R(sid, 'fema_flood_zone') or '—'}\nSFHA {g(R(sid, 'fp_sfha_pct'))} %\nwetland {g(R(sid, 'fp_nwi_pct'))} %") if ok else ''
            nb = (f"{g(R(sid, 'hu_within_1mi'))} homes in 1 mi\nschool {near(sid, 'school_nearest_m')}\nworship {near(sid, 'worship_nearest_m')}\n"
                  f"hospital {near(sid, 'hospital_nearest_m')}\nnursing home {near(sid, 'nursing_home_nearest_m')}") if ok else ''
            rows.append([f'**{sid}**', slabel(sid).replace('Confirmed: ', 'Conf.: '), STAGE.get(br.stage(), br.stage()),
                         (tagged(txt, t_) if t_ else txt) + (f"\n{br.timing()}" if br.timing() else '') + (f"\n{br.connection()}" if br.connection() else ''),
                         br.fiber() or '—', prox, fl, nb, '\n'.join(br.caveats())])
            cells[(len(rows) - 1, 1)] = fill(sid)
    widths = [0.55, 0.95, 0.9, 1.75, 1.1, 1.05, 0.85, 1.3, 1.95]
    d.table(['Site', 'Location', 'Site control', 'Power, timing, utility', 'Fiber', 'Proximity (ours)', 'Flood (ours)', 'Neighbors (ours)', 'Caveats and other notes'],
            rows, [w * wl / sum(widths) for w in widths], size=13, shade_cells=cells, rule_rows=rules)

    d.portrait()
    d.heading('Appendix B: Ownership and data handling', 1)
    rows = []
    for sid in confirmed:
        said = B[sid].owner() or '—'
        rows.append([f'**{sid}**', said, (R(sid, 'parcel_owner').strip() or '(none in the record)') + (' (internal)' if sid in internal else '')])
    if rows:
        note('Owner of record on the confirmed sites (county parcel data; for a carve-out, the owner of the parent parcel).')
        d.table(['Site', 'Broker says about the owner', 'Owner of record'], rows, [0.8, 2.6, 3.6], size=15)
    d.heading('Data handling', 2)
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

    d.heading('Appendix C: Method, sources and gaps', 1)
    d.heading('How the broker list was read', 2)
    d.bullet(f"{cells_info['cells']} cells read from {cells_info['sites']} sites through a checked column map "
             f"({cells_info['cells_copied']} cells are identical across sites: market-level, not site-level, evidence).")
    d.bullet(f"{check['evidence_rows']} evidence rows and {check['clue_rows']} location clues extracted in-session; every quote was verified "
             f"word for word against its source cell (extract_check.py, {len(check['errors'])} errors, {len(check['warnings'])} warnings).")
    d.bullet(f"Confidence tags normalized to one scale: {' > '.join(t for t in TAG_FULL.values() if t)}.")
    d.bullet('Locations: coordinates as given; named existing substations looked up in HIFLD; intersections computed from Census TIGER roads; '
             'landmarks from OpenStreetMap; ZIP and county centroids otherwise. Each candidate is checked against the stated county and ZIP.')
    d.heading('Sources (free / public)', 2)
    rows = [[n, p['source'], str(p.get('vintage') or ''), ', '.join(f'{k} {v}' for k, v in p['status_counts'].items())] for n, p in run['producers'].items()]
    d.table(['Producer', 'Source', 'Vintage', 'Status counts'], rows, [1.0, 3.6, 0.8, 1.6], size=15)
    d.heading('Not in this tool', 2)
    for t in ('Deliverable MW / power availability: proximity facts only; capacity is a utility study.',
              'Jurisdictional wetland or flood determinations: NWI and FEMA NFHL are screening layers.',
              'County politics, incentives, moratoriums; planned data-center developments (Baxtel is context only, not copied).',
              'Screening verdicts: none until thresholds for this portfolio are approved. The priority ratings (Appendix D) are our '
              'internal rating, not a screen against approved thresholds.'):
        d.bullet(t)

    # ---- Appendix D: ratings by site (landscape; evidence and confidence per score stay in ratings.csv)
    d.landscape()
    wl = d.usable_width_in()
    d.heading('Appendix D: Ratings by site', 1)
    if ratings:
        note(f"Method {', '.join(rvers)}, as of {', '.join(ras_of)} (design_site_rating.md). Scores 1–5; U = unknown. Confidence caps each score "
             f"(high 5, medium 4, low 3). Power is critical; Investment to ready, Land and buildability, Site control and Community are important; "
             f"Connectivity and Market position are supporting. Indicated = the rules; assigned = after named adjustments.")
        rows, cells, rules = [], {}, []
        for m in markets:
            if rows:
                rules.append(len(rows))
            for sid in [s_ for s_ in ids if market[s_] == m]:
                r = ratings[sid]
                scores = [r[f'{k}_score'] or 'U' for k, _ in RATING_DIMS]
                scr = f"Site risk: {r['screener_site_risk'].replace('_', ' ')}\nControl: {r['screener_control'].replace('_', ' ')}"
                adj = '\n'.join(a.replace('+1 ', '▲ ').replace('-1 ', '▼ ') for a in r['adjustments'].split(' | ') if a) or '—'
                why = '\n'.join(x for x in r['indicated_reasons'].split(' | ') + r['flags'].split(' | ') if x)
                rows.append([f'**{sid}**', slabel(sid).replace('Confirmed: ', 'Conf.: ')] + scores +
                            [scr, r['indicated'], adj, f"**{r['assigned']}**", why])
                i = len(rows) - 1
                cells[(i, 1)] = fill(sid)
                for j, s_ in enumerate(scores):
                    cells[(i, 2 + j)] = SCORE_FILL[s_]
                cells[(i, 10)] = PRIORITY_FILL[r['indicated']]
                cells[(i, 12)] = PRIORITY_FILL[r['assigned']]
        widths = [0.55, 0.9] + [0.5] * 7 + [0.95, 0.7, 1.45, 0.7, 2.0]
        d.table(['Site', 'Location'] + [h for _, h in RATING_DIMS] + ['Screeners', 'Indicated', 'Named adjustments', 'Assigned', 'Why (the rules)'],
                rows, [w * wl / sum(widths) for w in widths], size=13, shade_cells=cells, rule_rows=rules)
    else:
        note('Not rated for this batch: run rate.py, then memo.py again.')
    out2 = save(d, os.path.join(b, f'{name}_summary_memo.docx'))
    if british_words(out2):
        print(f"  summary memo: British spellings: {', '.join(british_words(out2))}")
    print(f"wrote {out1} ({len(ask)} questions, {len(exhibits)} exhibits), {out2} and {support(b, 'broker_summary.csv')}")
    for k, v in by_status.items():
        shown = [f"{s_} ({st[s_]['note']})" if st[s_].get('note') else s_ for s_ in v]
        print(f"  {LS.label(k)}{' (partial)' if k == 'confirmed_partial' else ''}: {', '.join(shown) or '-'}")


if __name__ == '__main__':
    main()
