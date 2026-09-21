import csv, os
BASE = r'C:\Users\tucke\OneDrive\Documents\Claude\Projects\TBDI Modeling\Mireye'
p = os.path.join(BASE, 'WS_Sites_Parcel_Sizes_FINAL.csv')
rows = list(csv.DictReader(open(p, encoding='utf-8-sig')))
ok = [r for r in rows if r['status'] == 'ok']
bad = [r for r in rows if r['status'] != 'ok']
print(f'total {len(rows)} | resolved {len(ok)} | unresolved {len(bad)}\n')

print('RESOLVED — has a queryable source (polygon retrievable):')
for r in sorted(ok, key=lambda x: (x['state'], x['clli'])):
    src = r['source']
    kind = 'ArcGIS' if src.startswith('http') else 'n/a'
    print(f"  {r['clli']:10} {r['state']} {r['county'][:11]:11} {float(r['acres_gis']):8.3f} ac  {kind}")

print('\nUNRESOLVED — no polygon available:')
for r in sorted(bad, key=lambda x: (x['state'], x['clli'])):
    print(f"  {r['clli']:10} {r['state']} {r['county'][:11]:11} {r['notes'][:58]}")

# any manual data filled in?
ws = os.path.join(BASE, 'WS_Sites_Manual_Lookup_Worksheet.csv')
if os.path.exists(ws):
    print('\nMANUAL WORKSHEET progress:')
    for r in csv.DictReader(open(ws, encoding='utf-8-sig')):
        filled = [k for k in ('acres_deeded','parcel_id','owner') if (r.get(k) or '').strip()]
        if filled:
            print(f"  {r['clli']:10} filled: {filled}  parcel_id={r.get('parcel_id')}  acres={r.get('acres_deeded')}")
