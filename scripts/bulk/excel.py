# -*- coding: utf-8 -*-
"""Write a batch's workbook from its run outputs.

    .venv_fema/Scripts/python.exe scripts/bulk/excel.py Outputs/<batch>/ [--name <title>]

Reads sites.csv, provenance.csv, run.json (Supporting outputs/) and, when the broker text has been extracted and
checked, input/site_list.csv and input/evidence_checked.csv; writes <batch>.xlsx at the top of the batch folder:

    Sites           our checks: one row per site; producer bands over field names; absent cells
                    shaded gray and failed cells red so a blank is never read as zero
    Broker says     the broker's statements, one row per site grouped by market, in the summary memo's
                    words (broker_facts.py): site control, MW and its confidence, timing, connection,
                    cost, fiber, acreage, zoning, flood claims, caveats. Never merged with our checks
    Broker evidence every broker statement: value, kind, confidence, the verbatim quote and its cell
    Gaps            every absent / failed value with the source's note
    Sources      one row per producer: source, URL, vintage, method, fields, tallies
    Provenance   the full site x field table, filterable
    Run          input file and hash, run time, counts, rejected rows
"""
import argparse, csv, json, os, sys
from collections import Counter, defaultdict
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from sites import REQUIRED, OPTIONAL          # noqa: E402
from batch_paths import support, publish      # noqa: E402
from broker_facts import (Broker, STAGE, TAG_FULL, MW_KIND, rd, tagged, market_of)   # noqa: E402

BAND_TITLES = {
    'transmission': 'Transmission (HIFLD)', 'substations': 'Substations (HIFLD)', 'flood': 'Flood at the pin (FEMA NFHL)',
    'wetlands': 'Wetlands at and near the pin (USFWS NWI)', 'metro': 'Metro (Census urban areas)', 'datacenter': 'Data centers (PeeringDB)',
    'housing': 'Housing (Census 2020 blocks)', 'schools': 'Schools (NCES)', 'worship': 'Places of worship (HIFLD)',
    'healthcare': 'Nursing homes & hospitals (CMS)', 'parcel': 'Parcel (county / state GIS)',
    'footprint': 'Site footprint: outline, parcel, else square around pin',
    'homes': 'Homes (FEMA USA Structures)', 'usable': 'Usable land and pads (product profile)',
    'power_site': 'Power from the site edge (HIFLD)', 'sensitive': 'Schools, worship, healthcare from the site edge',
    'utility': 'Serving utility and average price (EIA 861)', 'hazards': 'Natural hazard ratings (FEMA National Risk Index)',
    'superfund': 'EPA Superfund (NPL) sites',
}
FP_FLOOD = ['fp_flood_pct_any_zone', 'fp_sfha_pct', 'fp_sfha_acres', 'fp_flood_pct_floodway', 'fp_flood_pct_ve', 'fp_flood_pct_v',
            'fp_flood_pct_ae', 'fp_flood_pct_ah', 'fp_flood_pct_ao', 'fp_flood_pct_a', 'fp_flood_pct_ar', 'fp_flood_pct_a99',
            'fp_flood_pct_x_levee', 'fp_flood_pct_x_500yr', 'fp_flood_pct_x_minimal', 'fp_flood_pct_d_undetermined',
            'fp_flood_pct_other', 'fp_flood_pct_unmapped', 'fp_floodway_acres', 'fp_flood_unmapped_acres', 'fp_flood_zones']
FP_NWI = ['fp_nwi_acres', 'fp_nwi_pct', 'fp_nwi_types']
BAND_COLORS = ['1F3864', '2E5A46', '7A4A00', '4A235A', '0B5345', '6E2C00', '1B4F72', '4D5656', '5B2C6F', '145A32',
               '78281F', '1A5276', '3D3D3D']      # one per band: Site + 12 producers
# Broker says: (band, [(header, width)]); the band titles name the summary memo's Appendix A / B column they match
BROKER_BANDS = [('Site', [('site_id', 9), ('name', 30), ('market', 20)]),
                ('Site control (Appendix A; owner: Appendix B)', [('site control', 18), ('about the owner', 30)]),
                ('Power, timing, utility (Appendix A)', [('MW', 7), ('MW kind', 13), ('MW confidence', 16), ('headline MW', 20), ('timing', 30),
                                                         ('connection / utility', 30), ('¢/kWh', 20)]),
                ('Fiber (Appendix A)', [('fiber', 30)]),
                ('Land', [('acres', 16), ('zoning', 40)]),
                ('Flood', [('flood claims', 40)]),
                ('Caveats and other notes (Appendix A)', [('caveats and other notes', 70)])]
BROKER_COLORS = ['1F3864', '833C0B', 'C55A11', '833C0B', 'C55A11', '833C0B', 'C55A11']     # Site, then broker bands in two browns
EVIDENCE_COLS = ['site_id', 'dimension', 'field', 'value', 'unit', 'kind', 'confidence', 'tag_raw', 'quote', 'source_cell', 'column',
                 'note', 'dup_sites']

FILL_ABSENT = PatternFill('solid', fgColor='E7E6E6')
FILL_FAILED = PatternFill('solid', fgColor='F8CBAD')
FILL_NA = PatternFill('solid', fgColor='DDEBF7')          # not_assessable: location too rough for this field
FILL_HDR = PatternFill('solid', fgColor='D9D9D9')
THIN = Side(style='thin', color='BFBFBF')
RULE = Border(top=Side(style='medium', color='000000'))   # between markets, as in the memo's tables
FONT_HDR = Font(bold=True)
FONT_BAND = Font(bold=True, color='FFFFFF')
WRAP = Alignment(wrap_text=True, vertical='top')


def num(v):
    """CSV strings back to numbers where they are numbers; booleans to True/False."""
    if v is None or v == '':
        return None
    if v in ('True', 'False'):
        return v == 'True'
    try:
        f = float(v)
        return int(f) if f.is_integer() and '.' not in v else f
    except ValueError:
        return v


def autosize(ws, min_w=8, max_w=60):
    widths = defaultdict(int)
    for row in ws.iter_rows(values_only=True):
        for i, v in enumerate(row, 1):
            if v is not None:
                widths[i] = max(widths[i], min(max_w, len(str(v))))
    for i, w in widths.items():
        ws.column_dimensions[get_column_letter(i)].width = max(min_w, w + 2)


def confidence(tag):
    return TAG_FULL.get(tag, tag) or 'untagged'


def bands_header(ws, bands, colors, row=2):
    """A colored band row over a bold header row (the Sites layout)."""
    col = 1
    for bi, (title, cols) in enumerate(bands):
        c0 = col
        for h, w in cols:
            cell = ws.cell(row + 1, col, h)
            cell.font = FONT_HDR; cell.fill = FILL_HDR; cell.alignment = Alignment(wrap_text=True, vertical='bottom')
            ws.column_dimensions[get_column_letter(col)].width = w
            col += 1
        ws.merge_cells(start_row=row, start_column=c0, end_row=row, end_column=col - 1)
        cell = ws.cell(row, c0, title); cell.font = FONT_BAND; cell.alignment = Alignment(horizontal='center')
        cell.fill = PatternFill('solid', fgColor=colors[bi % len(colors)])
    return col - 1


def broker_sheets(wb, b, name):
    """'Broker says' and 'Broker evidence' from the checked broker-text extraction, or None when there is none. The
    wording is broker_facts.py's, the same as the summary memo's; nothing from our checks is mixed in."""
    inp = os.path.join(b, 'input')
    ev, sites_list = rd(os.path.join(inp, 'evidence_checked.csv')), rd(os.path.join(inp, 'site_list.csv'))
    ck = os.path.join(inp, 'extract_check.json')
    if not ev or not sites_list:
        print('  no broker sheets: input/evidence_checked.csv or input/site_list.csv not found (broker text not extracted)')
        return None
    if not (os.path.exists(ck) and json.load(open(ck, encoding='utf-8')).get('ok')):
        print('  no broker sheets: extract_check.py has not passed for this batch')
        return None
    ev_by = defaultdict(list)
    for r in ev:
        ev_by[r['site_id']].append(r)
    market = {s['site_id']: market_of(s['section']) for s in sites_list}
    markets = list(dict.fromkeys(market[s['site_id']] for s in sites_list))
    ids = [s['site_id'] for m in markets for s in sites_list if market[s['site_id']] == m]   # grouped by market, as Appendix A
    sname = {s['site_id']: s['name'] for s in sites_list}

    # ------------------------------------------------------------------ Broker says
    ws = wb.create_sheet('Broker says', 1)
    ws.cell(1, 1, f'{name} — {len(ids)} sites — BROKER-STATED, NOT OUR CHECK: every value is what the broker says '
                  '(input/evidence_checked.csv, quotes checked word for word); our checks are on Sites. Same words as the summary '
                  'memo: confidence in parentheses is confirmed = confirmed in writing, pre-screen = confirmed at pre-screen, '
                  'utility est. = utility estimate (verbal), broker est. = broker estimate, pending. "headline MW", "timing" and '
                  '"connection / utility", read together, are the memo\'s "Power, timing, utility" cell. Every statement, with its '
                  'quote: Broker evidence.').font = Font(italic=True)
    ncol = bands_header(ws, BROKER_BANDS, BROKER_COLORS)
    for r, sid in enumerate(ids, 4):
        br = Broker(ev_by[sid])
        v, k, t, txt = br.mw()
        row = [sid, sname[sid], market[sid], STAGE.get(br.stage(), br.stage()), br.owner(),
               v, MW_KIND.get(k, ''), confidence(t) if t else '', tagged(txt, t) if t else txt, br.timing(), br.connection(), br.cost(),
               br.fiber() or '—', br.acres()[1], br.zoning(), '\n'.join(br.flood_claims()), '\n'.join(br.caveats())]
        for c, x in enumerate(row, 1):
            cell = ws.cell(r, c, x if x != '' else None)
            cell.alignment = WRAP
            if r > 4 and market[sid] != market[ids[r - 5]]:
                cell.border = RULE
        if isinstance(v, float):
            ws.cell(r, 6).number_format = '#,##0.0'
    ws.freeze_panes = 'B4'
    ws.auto_filter.ref = f'A3:{get_column_letter(ncol)}{3 + len(ids)}'
    ws.row_dimensions[3].height = 30

    # ------------------------------------------------------------------ Broker evidence
    be = wb.create_sheet('Broker evidence', 2)
    be.cell(1, 1, f'{name} — {len(ev)} broker statements — BROKER-STATED, NOT OUR CHECK. One row per statement: value as extracted, '
                  'kind (actual / target / range_low / range_high / text), confidence on one scale (tag_raw = the broker\'s own words), the '
                  'verbatim quote and the cell it came from. dup_sites: the same cell is shared by these sites (market-level, not '
                  'site-level, evidence).').font = Font(italic=True)
    for c, h in enumerate(EVIDENCE_COLS, 1):
        cell = be.cell(2, c, h); cell.font = FONT_HDR; cell.fill = FILL_HDR
    order = {sid: i for i, sid in enumerate(ids)}
    for r in sorted(ev, key=lambda r: order.get(r['site_id'], len(order))):     # stable: file order within a site
        be.append([num(r['value']) if h == 'value' else confidence(r['tag_norm']) if h == 'confidence' else r.get(h) or None
                   for h in EVIDENCE_COLS])
    be.freeze_panes = 'B3'; be.auto_filter.ref = f'A2:{get_column_letter(len(EVIDENCE_COLS))}{2 + len(ev)}'
    autosize(be, max_w=60)
    be.column_dimensions['A'].width = 10       # not the legend's width
    return len(ids), len(ev)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('batch')
    ap.add_argument('--name', default=None)
    a = ap.parse_args()
    b = a.batch.rstrip('/\\')
    name = a.name or os.path.basename(b)
    sites = list(csv.DictReader(open(support(b, 'sites.csv'), encoding='utf-8-sig')))
    prov = list(csv.DictReader(open(support(b, 'provenance.csv'), encoding='utf-8-sig')))
    run = json.load(open(support(b, 'run.json'), encoding='utf-8'))
    if not sites:
        raise SystemExit(f"{b}: sites.csv has no sites - every input row was rejected; see sites_rejected in run.json")
    status = {(p['site_id'], p['field']): p for p in prov}
    producers = run['producers']            # name -> {source, url, vintage, fields, status_counts}

    wb = Workbook()

    # ------------------------------------------------------------------ Sites
    ws = wb.active; ws.title = 'Sites'
    site_cols = ['site_id', 'lat', 'lng'] + [c for c in OPTIONAL if any(s.get(c) for s in sites)]
    # G: every row says which basis its answers rest on. A site with no parcel boundary is not a
    # blank row - its values are real, measured over the square around the pin (footprint
    # producer) or, in a batch run without it, at the pin.
    has_fp = any(s.get('fp_basis') for s in sites)
    has_parcel = has_fp or any('parcel_status' in s for s in sites)
    if has_parcel:
        for s in sites:
            s['basis'] = (s.get('fp_basis') or 'no footprint - rerun') if has_fp else \
                'parcel boundary' if s.get('parcel_status') == 'ok' else 'point only'
        site_cols.insert(1, 'basis')
    prod_fields = [f for p in producers.values() for f in p['fields']]
    extra_cols = [c for c in sites[0].keys() if c not in site_cols and c not in prod_fields and c not in OPTIONAL]
    # the footprint's flood and wetland shares sit with the Flood and Wetlands groups, right after their pin values
    moved = {'flood': ('Flood across the whole site (FEMA NFHL; % of site acres)', FP_FLOOD),
             'wetlands': ('Wetlands across the whole site (USFWS NWI; % of site acres)', FP_NWI)}
    moved = {k: v for k, v in moved.items() if k in producers and 'footprint' in producers}
    gone = {f for _, fs in moved.values() for f in fs}
    bands = [('Site', site_cols + extra_cols)]
    for n, p in producers.items():
        bands.append((BAND_TITLES.get(n, n), [f for f in p['fields'] if n != 'footprint' or f not in gone]))
        if n in moved:
            bands.append(moved[n])
    legend = (f'{name} — {len(sites)} sites — run {run["run_at"][:16].replace("T", " ")} UTC — distances in meters '
              '(1 mi = 1,609 m) — gray = source confirmed nothing there (absent), red = source failed (see Gaps), '
              'blue = not assessable: the site is located only to a landmark, ZIP or county (location_tier L3-L5)')
    if has_fp:
        legend += ('   |   basis: "parcel boundary" = a parcel polygon resolved; the fp_* footprint columns (flood zones, SFHA, '
                   'floodway, wetland acres) are measured over that parcel. "<n> m square" = no parcel resolved, so the fp_* '
                   'columns are measured over a square centered on the pin - 200 m x 200 m (9.88 ac), or sized to acres_stated '
                   'when the input gives a larger acreage - ground around the site, '
                   'not a parcel, and no parcel acreage is claimed. Point columns (fema_*, nwi_*) are always at the pin.')
    elif has_parcel:
        legend += ('   |   basis: "parcel boundary" = a parcel polygon resolved, so acreage and any parcel-clipped '
                   'figure describe the site; "point only" = no parcel service is registered for that county, so every '
                   'value is measured at the pin (flood zone at the pin, nearest wetland from the pin) and no acreage is claimed')
    ws.cell(1, 1, legend).font = Font(italic=True)
    col = 1
    for bi, (title, fields) in enumerate(bands):
        c0 = col
        for f in fields:
            ws.cell(3, col, f).font = FONT_HDR
            ws.cell(3, col).fill = FILL_HDR
            ws.cell(3, col).alignment = Alignment(wrap_text=True, vertical='bottom')
            col += 1
        ws.merge_cells(start_row=2, start_column=c0, end_row=2, end_column=col - 1)
        cell = ws.cell(2, c0, title); cell.font = FONT_BAND; cell.alignment = Alignment(horizontal='center')
        cell.fill = PatternFill('solid', fgColor=BAND_COLORS[bi % len(BAND_COLORS)])
    all_fields = [f for _, fs in bands for f in fs]
    for r, s in enumerate(sites, 4):
        for c, f in enumerate(all_fields, 1):
            v = num(s.get(f))
            cell = ws.cell(r, c, v)
            st = status.get((s['site_id'], f))
            if st:
                if st['status'] == 'absent':
                    cell.fill = FILL_ABSENT
                elif st['status'] == 'failed':
                    cell.fill = FILL_FAILED
                elif st['status'] == 'not_assessable':
                    cell.fill = FILL_NA
            if isinstance(v, float):
                cell.number_format = '#,##0.0'
            elif isinstance(v, int) and not isinstance(v, bool) and f not in ('lat', 'lng'):
                cell.number_format = '#,##0'
    ws.freeze_panes = ws.cell(4, len(site_cols) + 1)
    ws.auto_filter.ref = f'A3:{get_column_letter(len(all_fields))}{3 + len(sites)}'
    ws.row_dimensions[3].height = 45
    autosize(ws, max_w=28)
    for c in range(1, len(all_fields) + 1):
        ws.column_dimensions[get_column_letter(c)].width = min(ws.column_dimensions[get_column_letter(c)].width, 18)

    broker = broker_sheets(wb, b, name)

    # ------------------------------------------------------------------ Gaps
    g = wb.create_sheet('Gaps')
    g.append(['site_id', 'field', 'status', 'note', 'source'])
    for cell in g[1]:
        cell.font = FONT_HDR; cell.fill = FILL_HDR
    gaps = [p for p in prov if p['status'] in ('absent', 'failed')]
    for p in sorted(gaps, key=lambda p: (p['status'] != 'failed', p['site_id'], p['field'])):
        g.append([p['site_id'], p['field'], p['status'], p['note'], p['source']])
        if p['status'] == 'failed':
            for cell in g[g.max_row]:
                cell.fill = FILL_FAILED
    g.freeze_panes = 'A2'; g.auto_filter.ref = g.dimensions
    autosize(g, max_w=90)

    # ------------------------------------------------------------------ Sources
    so = wb.create_sheet('Sources')
    so.append(['producer', 'source', 'source_url', 'vintage', 'method', 'fields', 'ok', 'absent', 'failed', 'manual', 'not_assessable', 'note'])
    for cell in so[1]:
        cell.font = FONT_HDR; cell.fill = FILL_HDR
    by_prod = defaultdict(list)
    for p in prov:
        by_prod[p['field']].append(p)
    for n, p in producers.items():
        rows = [r for f in p['fields'] for r in by_prod.get(f, [])]
        vint = Counter(r['vintage'] for r in rows if r['vintage']).most_common(1)
        method = Counter(r['method'] for r in rows if r['method']).most_common(1)
        notes = Counter(r['note'] for r in rows if r['note'] and r['status'] == 'ok').most_common(1)
        sc = p['status_counts']
        so.append([n, p['source'], p['url'], p.get('vintage') or (vint[0][0] if vint else ''), method[0][0] if method else '',
                   ', '.join(p['fields']), sc.get('ok', 0), sc.get('absent', 0), sc.get('failed', 0), sc.get('manual', 0), sc.get('not_assessable', 0),
                   notes[0][0] if notes else ''])
    for row in so.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = WRAP
    autosize(so, max_w=70)

    # ------------------------------------------------------------------ Provenance
    pv = wb.create_sheet('Provenance')
    cols = ['site_id', 'field', 'value', 'status', 'source', 'source_url', 'vintage', 'fetched_at', 'method', 'note']
    pv.append(cols)
    for cell in pv[1]:
        cell.font = FONT_HDR; cell.fill = FILL_HDR
    for p in prov:
        pv.append([num(p['value']) if c == 'value' else p.get(c) for c in cols])
    pv.freeze_panes = 'A2'; pv.auto_filter.ref = pv.dimensions
    autosize(pv, max_w=50)

    # ------------------------------------------------------------------ Run
    rn = wb.create_sheet('Run')
    rn.append(['key', 'value'])
    for cell in rn[1]:
        cell.font = FONT_HDR; cell.fill = FILL_HDR
    for k, v in [('batch', name), ('run_at (UTC)', run['run_at']), ('elapsed_s', run['elapsed_s']),
                 ('input file', run['input']['path']), ('input sha256', run['input']['sha256']),
                 ('sites accepted', run['sites_accepted']), ('sites rejected', len(run['sites_rejected'])),
                 ('producers', ', '.join(producers)), ('provenance rows', len(prov)),
                 ('absent values', sum(1 for p in prov if p['status'] == 'absent')),
                 ('failed values', sum(1 for p in prov if p['status'] == 'failed')),
                 ('cache hits / misses', f"{run['cache']['hits']} / {run['cache']['misses']}"),
                 ('broker statements', f'{broker[1]} (input/evidence_checked.csv; Broker says, Broker evidence)' if broker else
                                       'none: broker text not extracted and checked'),
                 ('status meanings', 'ok = source returned a value; absent = source confirmed nothing there (an answer, not an error); '
                                     'failed = source unreachable, value null; manual = supplied by a person')]:
        rn.append([k, v])
    for n, sid, why in run['sites_rejected']:
        rn.append([f'rejected row {n}', f'{sid}: {why}'])
    autosize(rn, max_w=100)

    from memo import BRITISH        # American spelling in everything a reader sees (memo.py warns the same way)
    brit = {sh.title: sorted({m.group(0) for row in sh.iter_rows(values_only=True) for v in row if isinstance(v, str)
                              for m in BRITISH.finditer(v)}) for sh in wb.worksheets}
    out = publish(b, f'{name}.xlsx', wb.save)
    found = ['{}: {}'.format(k, ', '.join(v)) for k, v in brit.items() if v]
    if found:
        print(f"  workbook: British spellings (ours to fix, or in the source text): {'; '.join(found)}")
    print(f'wrote {out}: Sites {len(sites)} rows x {len(all_fields)} cols | '
          + (f'Broker says {broker[0]} rows | Broker evidence {broker[1]} | ' if broker else '') + f'Gaps {len(gaps)} | Sources {len(producers)} | Provenance {len(prov)}')


if __name__ == '__main__':
    main()
