# -*- coding: utf-8 -*-
"""Add Barrow GA + Moore NC, recompute, write final CSV."""
import csv, json, math, os, re, urllib.parse, urllib.request

UA = {'User-Agent': 'Mozilla/5.0'}
BASE = r'C:\Users\tucke\OneDrive\Documents\Claude\Projects\TBDI Modeling\Mireye'
SRC = os.path.join(BASE, 'WS_Sites_Parcel_Sizes_v2.csv')
OUT = os.path.join(BASE, 'WS_Sites_Parcel_Sizes_FINAL.csv')

def jget(u, t=40):
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=t) as r:
            return json.loads(r.read().decode('utf-8', 'replace'))
    except Exception as e:
        return {'__error__': str(e)[:110]}

def ring_area(ring):
    R = 6378137.0
    if ring[0] != ring[-1]: ring = ring + [ring[0]]
    t = 0.0
    for i in range(len(ring) - 1):
        x1, y1 = math.radians(ring[i][0]), math.radians(ring[i][1])
        x2, y2 = math.radians(ring[i+1][0]), math.radians(ring[i+1][1])
        t += (x2 - x1) * (2 + math.sin(y1) + math.sin(y2))
    return abs(t * R * R / 2.0)

def area_m2(g):
    if not g: return None
    tp, c = g.get('type'), g.get('coordinates')
    polys = [c] if tp == 'Polygon' else (c if tp == 'MultiPolygon' else None)
    if polys is None: return None
    tot = 0.0
    for poly in polys:
        for i, ring in enumerate(poly):
            a = ring_area(ring); tot += a if i == 0 else -a
    return tot

ACRE = re.compile(r'acre', re.I)
PID  = re.compile(r'parcel.*(id|no|num)|^(pin|apn|parid|gpin|map_par)', re.I)
OWN  = re.compile(r'^own|owner', re.I)
ADDR = re.compile(r'(site|situs|prop|phys).*addr|^address1?$|street_nam', re.I)

def pick(props, pat):
    for k, v in props.items():
        if pat.search(k) and v not in (None, '', ' ', 0, 'NULL'):
            return str(v).strip()
    return ''

def pick_acres(props):
    c = []
    for k, v in props.items():
        if not ACRE.search(k) or v in (None, '', ' ', 'NULL'): continue
        try: fv = float(v)
        except (TypeError, ValueError): continue
        if fv <= 0: continue
        rank = 0 if re.search(r'deed', k, re.I) else (1 if re.search(r'calc|gis|total', k, re.I) else 2)
        c.append((rank, k, fv))
    if not c: return '', ''
    c.sort(); return c[0][2], c[0][1]

NEW = {
    'WNDRGAXA': 'https://services5.arcgis.com/OVFGXfRTCVcPwl55/arcgis/rest/services/Barrow_Parcels_w_Owner/FeatureServer/0',
    'ABRDNCXA': 'https://services7.arcgis.com/WOKJvFrknOcT2chj/arcgis/rest/services/Accela_taxparcels/FeatureServer/0',
}

rows = list(csv.DictReader(open(SRC, encoding='utf-8-sig')))
for r in rows:
    if r['clli'] not in NEW: continue
    layer = NEW[r['clli']]
    geom = json.dumps({'x': float(r['lng']), 'y': float(r['lat']), 'spatialReference': {'wkid': 4326}})
    u = (layer + '/query?f=geojson&outFields=*&returnGeometry=true&geometryType=esriGeometryPoint'
         '&inSR=4326&outSR=4326&spatialRel=esriSpatialRelIntersects&geometry=' + urllib.parse.quote(geom))
    res = jget(u)
    feats = (res.get('features') or []) if isinstance(res, dict) else []
    if not feats:
        print(f'  {r["clli"]}: still no feature'); continue
    props = feats[0].get('properties') or {}
    m2 = area_m2(feats[0].get('geometry'))
    av, af = pick_acres(props)
    r.update(status='ok', source=layer, parcel_id=pick(props, PID), owner=pick(props, OWN),
             parcel_address=pick(props, ADDR),
             acres_gis=round(m2/4046.856, 4) if m2 else '', sqft_gis=round(m2*10.7639) if m2 else '',
             m2_gis=round(m2, 1) if m2 else '', acres_stated=av, acres_stated_field=af, notes='')
    print(f'  {r["clli"]} {r["county"]} Co: {r["acres_gis"]} ac | id={r["parcel_id"]} | {r["owner"][:30]}')

COLS = ['clli','address','tier','county','state','lat','lng','status','acres_gis','sqft_gis',
        'm2_gis','acres_stated','acres_stated_field','parcel_id','owner','parcel_address','source','notes']
with open(OUT, 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.DictWriter(f, fieldnames=COLS, extrasaction='ignore'); w.writeheader()
    for r in sorted(rows, key=lambda x: (x['state'], x['county'], x['clli'])): w.writerow(r)

ok = sum(1 for r in rows if r['status'] == 'ok')
print(f'\nFINAL: {ok}/{len(rows)} resolved -> {OUT}')
print('unresolved:', ', '.join(f"{r['clli']}({r['county']} {r['state']})" for r in rows if r['status'] != 'ok'))
