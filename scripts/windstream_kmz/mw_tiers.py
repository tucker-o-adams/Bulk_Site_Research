import csv
from collections import Counter
p = r'C:\Users\tucke\OneDrive\Documents\Claude\Projects\TBDI Modeling\Mireye\WS_Top200_Transmission_Distance.csv'
rows = [r for r in csv.DictReader(open(p, encoding='utf-8-sig')) if r['nearest_tx_line_m']]

def num(v):
    try: return float(v)
    except (TypeError, ValueError): return None

print(f'sites with a nearest line: {len(rows)}\n')

# how far to a line of at least X kV?
for thresh in (69, 115, 138, 230):
    hits = []
    for r in rows:
        # nearest-any and nearest->=100kV are the two we stored
        kv_any, d_any = num(r['voltage_kv']), num(r['nearest_tx_line_m'])
        kv_hv,  d_hv  = num(r['kv_100plus']), num(r['nearest_100kv_plus_m'])
        best = None
        for kv, d in ((kv_any, d_any), (kv_hv, d_hv)):
            if kv is not None and d is not None and kv >= thresh:
                best = d if best is None else min(best, d)
        if best is not None:
            hits.append(best)
    w1 = sum(1 for d in hits if d <= 1000)
    w3 = sum(1 for d in hits if d <= 3000)
    w8 = sum(1 for d in hits if d <= 8000)
    print(f'>= {thresh:3} kV line known within...  1 km: {w1:3}   3 km: {w3:3}   8 km: {w8:3}   (any dist: {len(hits):3})')

print('\nNearest-line voltage tier (all 198):')
tiers = Counter()
for r in rows:
    kv = num(r['voltage_kv'])
    if kv is None or kv <= 0: t = 'unpublished'
    elif kv < 100: t = 'sub-100 kV (46-69)'
    elif kv < 130: t = '100-115 kV'
    elif kv < 200: t = '138-161 kV'
    else: t = '230 kV +'
    tiers[t] += 1
for t in ['sub-100 kV (46-69)', '100-115 kV', '138-161 kV', '230 kV +', 'unpublished']:
    print(f'   {t:20} {tiers[t]:3}')

print('\nAmong the 34 unpublished-voltage sites, is there a known >=100kV line nearby?')
unp = [r for r in rows if (num(r['voltage_kv']) or -1) <= 0]
got = [r for r in unp if num(r['nearest_100kv_plus_m']) is not None]
print(f'   {len(got)} of {len(unp)} have a known >=100 kV line within the 15 km search')
