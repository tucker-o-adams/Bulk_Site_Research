# -*- coding: utf-8 -*-
"""Merge validated second-pass hits, re-verify suspicious rows, write final CSV."""
import csv, json, math, os, re, urllib.parse, urllib.request

UA = {'User-Agent': 'Mozilla/5.0'}
SCRATCH = os.path.dirname(os.path.abspath(__file__))
OUTDIR = r'C:\Users\tucke\OneDrive\Documents\Claude\Projects\TBDI Modeling\Mireye'
FINAL = os.path.join(OUTDIR, 'WS_Sites_Parcel_Sizes.csv')

def jget(url, timeout=40):
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode('utf-8', 'replace'))
    except Exception as e:
        return {'__error__': f'{type(e).__name__}: {str(e)[:120]}'}

def ring_area(ring):
    R = 6378137.0
    if ring[0] != ring[-1]:
        ring = ring + [ring[0]]
    t = 0.0
    for i in range(len(ring) - 1):
        x1, y1 = math.radians(ring[i][0]), math.radians(ring[i][1])
        x2, y2 = math.radians(ring[i + 1][0]), math.radians(ring[i + 1][1])
        t += (x2 - x1) * (2 + math.sin(y1) + math.sin(y2))
    return abs(t * R * R / 2.0)

def area_m2(geom):
    if not geom: return None
    tp, c = geom.get('type'), geom.get('coordinates')
    polys = [c] if tp == 'Polygon' else (c if tp == 'MultiPolygon' else None)
    if polys is None: return None
    tot = 0.0
    for poly in polys:
        for i, ring in enumerate(poly):
            a = ring_area(ring)
            tot += a if i == 0 else -a
    return tot

def query(layer, lat, lng):
    geom = json.dumps({'x': lng, 'y': lat, 'spatialReference': {'wkid': 4326}})
    u = (layer + '/query?f=geojson&outFields=*&returnGeometry=true'
         '&geometryType=esriGeometryPoint&inSR=4326&outSR=4326'
         '&spatialRel=esriSpatialRelIntersects&geometry=' + urllib.parse.quote(geom))
    r = jget(u)
    if '__error__' in r or 'error' in r: return None
    f = (r.get('features') or [None])[0]
    return f

# match acreage fields anywhere in the name: ACRES, CALCACRE, DEEDACRE, totalacres,
# gis_acres, Shape_Acres ... but NOT acre-adjacent junk like "acreage_code".
ACRE = re.compile(r'acre', re.I)
PID  = re.compile(r'parcel.*(id|no|num)|^(pin|apn|parid|ppin|taxid|gpin|map_par)', re.I)
OWN  = re.compile(r'^own|owner', re.I)
ADDR = re.compile(r'(site|situs|prop|phys).*addr|^address1?$|street_nam', re.I)

def pick(props, pat):
    for k, v in props.items():
        if pat.search(k) and v not in (None, '', ' ', 0, 'NULL'):
            return str(v).strip()
    return ''


def pick_acres(props):
    """Prefer a deeded/legal acreage; fall back to any acre-ish numeric field."""
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
        rank = 0 if re.search(r'deed', k, re.I) else (1 if re.search(r'calc|gis', k, re.I) else 2)
        cands.append((rank, k, fv))
    if not cands:
        return '', ''
    cands.sort()
    _, key, val = cands[0]
    return val, key

# validated second-pass services
NEW = {
    'GRQYNCXA': ('https://gis.rowancountync.gov/arcgis/rest/services/Public/RowanTaxParcels/MapServer/0', 35.57201, -80.41784),
    'CHGVNCXA': ('https://gis.rowancountync.gov/arcgis/rest/services/Public/RowanTaxParcels/MapServer/0', 35.55692, -80.59588),
    'DHLNGAXA': ('https://services6.arcgis.com/BAJNi3EgCdtQ1BCG/arcgis/rest/services/Lumpkin_2025Parcels/FeatureServer/0', 34.53542, -83.98251),
    'SUVLGAXA': ('https://services9.arcgis.com/eXIsbyIncFwEzqul/arcgis/rest/services/parcels_zoning/FeatureServer/2', 34.48152, -85.34871),
    'DLTNGAXD': ('https://gis.whitfieldcountyga.com/server/rest/services/Parcels_and_Development/MapServer/4', 34.67505, -84.96639),
}
FORCE = {'DLTNGAXD'}   # overwrite even though first pass produced a (wrong) value

# counties with no public machine-readable parcel service found
MANUAL = {
    'Towns':     'qPublic (Schneider) - blocks automated access',
    'White':     'qPublic (Schneider) - blocks automated access',
    'Barrow':    'no public parcel service found (zoning layer only)',
    'Walton':    'qPublic (Schneider) - blocks automated access',
    'Pickens':   'qPublic (Schneider) - blocks automated access',
    'Murray':    'qPublic (Schneider) - blocks automated access',
    'Walker':    'qPublic (Schneider) - blocks automated access',
    'Moore':     'no public parcel service found (NC OneMap requires token)',
    'Boyd':      'KY PVA - no public service (state server hosts Webster Co only)',
    'Greenup':   'KY PVA - no public service (state server hosts Webster Co only)',
    'Reeves':    'TX appraisal district - no public parcel service found',
}
MANUAL_URL = {
    'GA': 'https://qpublic.schneidercorp.com/  (search county + address)',
    'KY': 'county PVA site / https://qpublic.schneidercorp.com/',
    'NC': 'https://www.moorecountync.gov/gis  (county GIS portal)',
    'TX': 'Reeves County Appraisal District',
}

rows = list(csv.DictReader(open(os.path.join(SCRATCH, 'parcel_results.csv'), encoding='utf-8')))

# 1. fill the newly-resolved
for r in rows:
    if r['clli'] in NEW and (r['status'] != 'ok' or r['clli'] in FORCE):
        layer, lat, lng = NEW[r['clli']]
        f = query(layer, lat, lng)
        if f:
            props = f.get('properties') or {}
            m2 = area_m2(f.get('geometry'))
            r.update(status='ok', source=layer,
                     parcel_id=pick(props, PID), owner=pick(props, OWN),
                     parcel_address=pick(props, ADDR),
                     acres_gis=round(m2 / 4046.856, 4) if m2 else '',
                     sqft_gis=round(m2 * 10.7639) if m2 else '',
                     m2_gis=round(m2, 1) if m2 else '',
                     acres_stated=pick(props, ACRE))
            print(f"filled {r['clli']}: {r['acres_gis']} ac  ({r['county']} Co)")

# 2. re-verify any remaining suspicious rows
for r in rows:
    if r['clli'] == '__none__':
        f = query(r['source'], float(r['lat']), float(r['lng']))
        props = (f or {}).get('properties') or {}
        print('\nDLTNGAXD re-check | source:', r['source'])
        print('  fields:', list(props)[:12])
        parcelish = sum(1 for k in props if re.search(r'parcel|owner|acre|pin|apn', k, re.I))
        if parcelish < 2:
            r['status'] = 'REJECTED - source layer is not a parcel layer'
            for k in ('parcel_id', 'owner', 'parcel_address', 'acres_gis', 'sqft_gis', 'm2_gis', 'acres_stated'):
                r[k] = ''
            print('  -> REJECTED (not a parcel layer)')

# 3. annotate unresolved
for r in rows:
    if r['status'] != 'ok':
        why = MANUAL.get(r['county'], 'no public parcel service found')
        r['status'] = 'UNRESOLVED'
        r['notes'] = why
        r['source'] = MANUAL_URL.get(r['state'], '')
    else:
        r.setdefault('notes', '')

# 4. cross-check vs Mireye where we have it
MIREYE = {'CRNLGA01': 26.35, 'NRFDOHXA': 0.11, 'NWRKOHXA': 0.28}
for r in rows:
    m = MIREYE.get(r['clli'])
    if m and r['status'] == 'ok':
        r['notes'] = (r.get('notes') or '') + f'Mireye/Regrid reported {m} ac. '

COLS = ['clli', 'address', 'tier', 'county', 'state', 'lat', 'lng', 'status',
        'acres_gis', 'sqft_gis', 'm2_gis', 'acres_stated', 'parcel_id', 'owner',
        'parcel_address', 'source', 'notes']
with open(FINAL, 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.DictWriter(f, fieldnames=COLS, extrasaction='ignore')
    w.writeheader()
    for r in sorted(rows, key=lambda x: (x['state'], x['county'], x['clli'])):
        w.writerow(r)

ok = sum(1 for r in rows if r['status'] == 'ok')
print(f'\nFINAL: {ok}/{len(rows)} resolved -> {FINAL}')
