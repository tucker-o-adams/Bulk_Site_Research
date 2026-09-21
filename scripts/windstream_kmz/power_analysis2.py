# -*- coding: utf-8 -*-
"""Correlate utility-implied load vs genset nameplate vs rack count."""
import openpyxl, statistics
from collections import defaultdict

P = r'C:\Users\tucke\OneDrive\Documents\Claude\Projects\TBDI Modeling\Mireye\TBDI Windstream Top 200 COs v6.29.26 vTA.xlsx'
wb = openpyxl.load_workbook(P, data_only=True)

ws = wb['COs_Asset_List']
h = {ws.cell(1, c).value: c for c in range(1, ws.max_column + 1)}
gens = defaultdict(float)
runt = defaultdict(list)
for r in range(2, ws.max_row + 1):
    clli = ws.cell(r, h['CLLI - A']).value
    model = (ws.cell(r, h['Asset Model']).value or '').upper()
    if not clli or 'GENERATOR' not in model:
        continue
    try:
        gens[clli] += float(ws.cell(r, h['KW']).value)
    except (TypeError, ValueError):
        pass
    rt = ws.cell(r, h['Generator Run Time (Hours)']).value
    if isinstance(rt, (int, float)):
        runt[clli].append(rt)

ws2 = wb['Top 200 COs']
h2 = {ws2.cell(1, c).value: c for c in range(1, ws2.max_column + 1)}
PRICE = {'KY': .073, 'GA': .0684, 'OH': .0995, 'TX': .0633, 'AR': .062, 'IA': .0626}

pairs_gen, pairs_rack, wpsf = [], [], []
rows = []
for r in range(2, ws2.max_row + 1):
    clli = ws2.cell(r, h2['CLLI']).value
    if not clli:
        continue
    def f(n):
        c = h2.get(n)
        try:
            return float(ws2.cell(r, c).value)
        except (TypeError, ValueError):
            return None
    st = ws2.cell(r, h2['State']).value
    util, sqft, racks = f('KOIOS - UTILITIES 2025'), f('Square Ft-Interior'), f('Rack Count')
    pr = PRICE.get(st)
    avg = (util / pr / 8760) if (util and pr and util > 0) else None
    gkw = gens.get(clli) or None
    rows.append((clli, st, sqft, racks, avg, gkw))
    if avg and gkw:
        pairs_gen.append((avg, gkw))
    if avg and racks:
        pairs_rack.append((avg, racks))
    if avg and sqft:
        wpsf.append(avg * 1000 / sqft)

print('=== A. genset nameplate vs utility-implied average load ===')
r_ = [g / a for a, g in pairs_gen]
print(f'  n={len(pairs_gen)}   genset_kW / avg_kW : median {statistics.median(r_):.2f}x '
      f'| p25 {statistics.quantiles(r_, n=4)[0]:.2f}x | p75 {statistics.quantiles(r_, n=4)[2]:.2f}x')

print('\n=== B. implied load per rack ===')
rr = [a / k for a, k in pairs_rack if k > 0]
print(f'  n={len(rr)}   avg_kW per rack : median {statistics.median(rr):.2f} kW '
      f'| p25 {statistics.quantiles(rr, n=4)[0]:.2f} | p75 {statistics.quantiles(rr, n=4)[2]:.2f}')

print('\n=== C. actual measured power density (W per interior sqft) ===')
print(f'  n={len(wpsf)}   median {statistics.median(wpsf):.1f} W/sqft '
      f'| p25 {statistics.quantiles(wpsf, n=4)[0]:.1f} | p75 {statistics.quantiles(wpsf, n=4)[2]:.1f}')
print(f'  (TA model assumes 187.5 W/sqft)')

print('\n=== D. generator run-time hours (are they emergency-only?) ===')
allrt = [x for v in runt.values() for x in v]
print(f'  n={len(allrt)}  median {statistics.median(allrt):.0f} h | max {max(allrt):.0f} h')

print('\n=== E. portfolio totals ===')
tot_gen = sum(g for _, _, _, _, _, g in rows if g)
tot_avg = sum(a for _, _, _, _, a, _ in rows if a)
tot_sqft = sum(s for _, _, s, _, _, _ in rows if s)
print(f'  sum genset nameplate : {tot_gen/1000:,.1f} MW across {sum(1 for x in rows if x[5])} sites')
print(f'  sum utility-implied  : {tot_avg/1000:,.1f} MW across {sum(1 for x in rows if x[4])} sites')
print(f'  sum interior sqft    : {tot_sqft:,.0f} -> TA model would imply {tot_sqft*0.1875/1000:,.0f} MW')
