import csv
from collections import Counter
p = r'C:\Users\tucke\OneDrive\Documents\Claude\Projects\TBDI Modeling\Mireye\WS_Top200_Transmission_Distance.csv'
rows = [r for r in csv.DictReader(open(p, encoding='utf-8-sig')) if r['nearest_tx_line_m']]

def kv(r):
    try: return float(r['voltage_kv'])
    except (TypeError, ValueError): return None

vals = [kv(r) for r in rows]
under = [v for v in vals if v is not None and 0 < v < 100]
over  = [v for v in vals if v is not None and v >= 100]
neg   = [v for v in vals if v is not None and v <= 0]
none_ = [v for v in vals if v is None]

print(f'rows with a nearest line: {len(rows)}')
print(f'  nearest line UNDER 100 kV : {len(under)}   <-- proves sub-100kV lines are included')
print(f'  nearest line >= 100 kV    : {len(over)}')
print(f'  voltage <= 0 (unpublished): {len(neg)}')
print(f'  voltage blank/non-numeric : {len(none_)}')

print('\ndistinct nearest-line voltages found:')
for v, n in sorted(Counter(v for v in vals if v is not None).items()):
    print(f'   {v:8.0f} kV : {n:3} sites')

# how often does using only >=100kV change the answer?
diff = 0
for r in rows:
    try:
        a = float(r['nearest_tx_line_m']); b = float(r['nearest_100kv_plus_m'])
    except (TypeError, ValueError):
        continue
    if b - a > 50:
        diff += 1
print(f'\nsites where nearest >=100kV line is >50 m farther than nearest line of any voltage: {diff}')
