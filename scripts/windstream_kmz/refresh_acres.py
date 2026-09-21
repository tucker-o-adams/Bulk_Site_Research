# -*- coding: utf-8 -*-
"""Re-read acres_stated for every resolved row using the corrected field matcher."""
import csv, json, re, urllib.parse, urllib.request

UA = {'User-Agent': 'Mozilla/5.0'}
CSVP = r'C:\Users\tucke\OneDrive\Documents\Claude\Projects\TBDI Modeling\Mireye\WS_Sites_Parcel_Sizes.csv'
ACRE = re.compile(r'acre', re.I)

def jget(u, t=40):
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=t) as r:
            return json.loads(r.read().decode('utf-8', 'replace'))
    except Exception as e:
        return {'__error__': str(e)[:110]}

def pick_acres(props):
    cands = []
    for k, v in props.items():
        if not ACRE.search(k) or v in (None, '', ' ', 'NULL'):
            continue
        try:
            fv = float(v)
        except (TypeError, ValueError):
            continue
        if fv <= 0:
            continue
        rank = 0 if re.search(r'deed', k, re.I) else (1 if re.search(r'calc|gis|total', k, re.I) else 2)
        cands.append((rank, k, fv))
    if not cands:
        return '', ''
    cands.sort()
    return cands[0][2], cands[0][1]

rows = list(csv.DictReader(open(CSVP, encoding='utf-8-sig')))
changed = 0
for r in rows:
    if r['status'] != 'ok' or not r['source'].startswith('http'):
        continue
    geom = json.dumps({'x': float(r['lng']), 'y': float(r['lat']), 'spatialReference': {'wkid': 4326}})
    u = (r['source'] + '/query?f=geojson&outFields=*&returnGeometry=false'
         '&geometryType=esriGeometryPoint&inSR=4326&spatialRel=esriSpatialRelIntersects'
         '&geometry=' + urllib.parse.quote(geom))
    res = jget(u)
    feats = (res.get('features') or []) if isinstance(res, dict) else []
    if not feats:
        continue
    props = feats[0].get('properties') or {}
    val, field = pick_acres(props)
    old = (r.get('acres_stated') or '').strip()
    r['acres_stated'] = val if val != '' else ''
    r['acres_stated_field'] = field
    if str(val) != old:
        changed += 1
        print(f"  {r['clli']:10} {r['county'][:11]:11} {old or '-':>10} -> {val or '-':<10} ({field or 'none'})")

COLS = ['clli', 'address', 'tier', 'county', 'state', 'lat', 'lng', 'status',
        'acres_gis', 'sqft_gis', 'm2_gis', 'acres_stated', 'acres_stated_field',
        'parcel_id', 'owner', 'parcel_address', 'source', 'notes']
target = CSVP
try:
    fh = open(target, 'w', newline='', encoding='utf-8-sig')
except PermissionError:
    target = CSVP.replace('.csv', '_v2.csv')
    print(f'\n(original locked by Excel -> writing {target})')
    fh = open(target, 'w', newline='', encoding='utf-8-sig')
with fh as f:
    w = csv.DictWriter(f, fieldnames=COLS, extrasaction='ignore')
    w.writeheader()
    for r in rows:
        w.writerow(r)
print('wrote', target)

have = sum(1 for r in rows if r['status'] == 'ok' and (r.get('acres_stated') or '').strip())
print(f'\nchanged {changed} rows | acres_stated now populated on {have}/32 resolved')
