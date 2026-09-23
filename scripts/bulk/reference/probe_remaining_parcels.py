"""Probe candidate parcel sources at every site the registry does not resolve.

Evidence for a person to review, never a registration: writes one row per site to
data/reference/parcel-proposals/remaining-probe.csv with the first source that
returned a polygon, its parcel id and owner, and whether the owner looks like the
site's own operator. Sources come from the 2026-09-22 prior-art research recorded
in scripts/bulk/BACKLOG.md (statewide TX/AR/OK layers, Schneider's open WFS host,
OpenAddresses parcel sources, regional-commission hosts).

    .venv_fema/Scripts/python.exe scripts/bulk/reference/probe_remaining_parcels.py Outputs/<batch> [--expected-owner REGEX]

The operator pattern defaults to the batch's own `expected_owner` in run.json (the one run.py was given);
with neither, `operator_owner` is left blank.
"""
import argparse
import csv
import json
import re
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'data/reference/parcel-proposals/remaining-probe.csv'
UA = {'User-Agent': 'TBDI-bulk-research/1.0'}

STRATMAP = 'https://feature.geographic.texas.gov/arcgis/rest/services/Parcels/stratmap_land_parcels_48_most_recent/MapServer'
ARKANSAS = 'https://gis.arkansas.gov/arcgis/rest/services/FEATURESERVICES/Planning_Cadastre/FeatureServer/6'
OKMAPS = 'https://okmaps.org/geoserver/wms'
WFS = 'https://wfs.schneidercorp.com/arcgis/rest/services/'

# County layers verified live 2026-09-22 (ArcGIS query endpoints), keyed by (state, county).
COUNTY = {
    ('GA', 'Baldwin County'): 'https://services7.arcgis.com/Da8HZMsU25Hzzob3/arcgis/rest/services/Parcels_Feb2026/FeatureServer/0',
    ('GA', 'Ben Hill County'): 'https://www.sgrcmaps.com/alma/rest/services/BenHill/Property/MapServer/2',
    ('GA', 'Berrien County'): 'https://www.sgrcmaps.com/arcgis/rest/services/Berrien/TaxParcelBoundaries/MapServer/2',
    ('GA', 'Cook County'): 'https://www.sgrcmaps.com/alma/rest/services/Cook/CookParcels/MapServer/1',
    ('GA', 'Franklin County'): WFS + 'FranklinCountyGA_WFS/MapServer/0',
    ('GA', 'Grady County'): WFS + 'GradyCountyGA_WFS/MapServer/0',
    ('GA', 'Habersham County'): WFS + 'HabershamCountyGA_WFS/MapServer/4',
    ('GA', 'Houston County'): 'https://services1.arcgis.com/Ug5xGQbHsD8zuZzM/arcgis/rest/services/HoustonCoParcels_withOwner/FeatureServer/0',
    ('GA', 'Macon County'): 'https://services1.arcgis.com/Ug5xGQbHsD8zuZzM/arcgis/rest/services/Parcels12_2018/FeatureServer/0',
    ('GA', 'Meriwether County'): 'https://services9.arcgis.com/Xv8vRekQ4FVHSSIe/arcgis/rest/services/MeriwetherParcels/FeatureServer/0',
    ('GA', 'Screven County'): 'https://maps.crc.ga.gov/crcarcgis/rest/services/Screven/ScrevenParcels/MapServer/0',
    ('GA', 'Telfair County'): 'https://services5.arcgis.com/HHvUPZ2XuLOAJxjR/arcgis/rest/services/Telfair_County_Wide_View/FeatureServer/15',
    ('GA', 'Walker County'): 'https://services.arcgis.com/UnTXoPXBYERF0OH6/arcgis/rest/services/Walker_Parcels_2026LLLT/FeatureServer/4',
    ('GA', 'White County'): 'https://services1.arcgis.com/Ug5xGQbHsD8zuZzM/arcgis/rest/services/Cleveland_Water_2023_WFL1/FeatureServer/8',
    ('GA', 'Wilcox County'): 'https://services5.arcgis.com/HHvUPZ2XuLOAJxjR/arcgis/rest/services/Wilcox_County_Wide_View/FeatureServer/12',
    ('GA', 'Whitfield County'): 'https://gis.whitfieldcountyga.com/server/rest/services/Parcels_and_Development/MapServer/4',
    ('KY', 'Bullitt County'): WFS + 'BullittCountyKY_WFS/MapServer/0',
    ('KY', 'Hardin County'): WFS + 'HardinCountyKY_WFS/MapServer/0',
    ('KY', 'Madison County'): 'https://arcserver.madisoncountyky.us/arcgis/rest/services/County_Web_Maps/County_Parcels/MapServer/1',
    ('AL', 'Jefferson County'): 'https://jccgis.jccal.org/server/rest/services/Basemap/Parcels/MapServer/0',
    ('AL', 'St. Clair County'): 'https://map.stclairco.com/arcgis/rest/services/PublicParcelViewerStPln/MapServer/57',
}
# Caveats a reviewer must see next to the hit.
CAVEAT = {
    ('GA', 'Macon County'): '2018 snapshot',
    ('GA', 'Grady County'): '2017 parcels, no owner field',
    ('GA', 'Meriwether County'): 'published by an individual AGOL account; publisher unverified',
    ('GA', 'Walker County'): 'Lula Lake Land Trust copy hosted by UT-Chattanooga',
    ('GA', 'Screven County'): 'Coastal Regional Commission host',
    ('GA', 'Telfair County'): 'Heart of Georgia Altamaha RC, TaxParcels25: geometry only, no parcel id or owner',
    ('GA', 'Wilcox County'): 'Heart of Georgia Altamaha RC, TaxParcels_25: geometry and acres only, no parcel id or owner',
    ('GA', 'White County'): 'City of Cleveland water map (2023), city parcels only; TAX_CLASS U = utility',
}
OPERATOR = None       # set in main(): --expected-owner, else the batch's run.json expected_owner
OWNER_KEY = re.compile(r'^(owner|owners|owner_?name|ownername|name_?1?|lastname|own_?name)$', re.I)
PID_KEY = re.compile(r'^(parcel_?(no|id|num)?|parcelid|parcelno|pin|prop_id|pid)$', re.I)

S = requests.Session()
S.headers.update(UA)


def pick(attrs, key):
    for k, v in attrs.items():
        if key.match(k) and v not in (None, '', ' ', 0, '0'):
            return str(v).strip()
    return ''


def arcgis_query(url, lat, lng):
    p = dict(geometry=f'{lng},{lat}', geometryType='esriGeometryPoint', inSR=4326,
             spatialRel='esriSpatialRelIntersects', outFields='*', returnGeometry='false', f='json')
    j = S.get(url + '/query', params=p, timeout=60).json()
    if 'error' in j:
        raise RuntimeError(j['error'].get('message'))
    fs = j.get('features', [])
    return fs[0]['attributes'] if fs else None


def stratmap(lat, lng):
    d = .001
    p = dict(geometry=f'{lng},{lat}', geometryType='esriGeometryPoint', sr=4326, layers='all', tolerance=0,
             mapExtent=f'{lng-d},{lat-d},{lng+d},{lat+d}', imageDisplay='400,400,96', returnGeometry='false', f='json')
    res = S.get(STRATMAP + '/identify', params=p, timeout=60).json().get('results', [])
    return res[0]['attributes'] if res else None


def okmaps(lat, lng):
    d = .0005
    p = dict(SERVICE='WMS', VERSION='1.1.1', REQUEST='GetFeatureInfo', SRS='EPSG:4326',
             BBOX=f'{lng-d},{lat-d},{lng+d},{lat+d}', WIDTH=101, HEIGHT=101, X=50, Y=50,
             LAYERS='ogi_wms:Statewide_Parcels', QUERY_LAYERS='ogi_wms:Statewide_Parcels', STYLES='',
             INFO_FORMAT='application/json', FEATURE_COUNT=1)
    fs = S.get(OKMAPS, params=p, timeout=60).json().get('features', [])
    return fs[0]['properties'] if fs else None


def sources(state, county):
    if state == 'TX':
        yield 'TxGIO StratMap Land Parcels (statewide)', STRATMAP, stratmap
    if state == 'AR':
        yield 'Arkansas GIS Office Planning_Cadastre/6 (statewide)', ARKANSAS, lambda a, b: arcgis_query(ARKANSAS, a, b)
    if state == 'OK':
        yield 'OKMaps Statewide_Parcels WMS (statewide)', OKMAPS, okmaps
    url = COUNTY.get((state, county))
    if url:
        yield f'{county} layer', url, lambda a, b: arcgis_query(url, a, b)


def main(batch, expected_owner=None):
    global OPERATOR
    if not expected_owner:
        run = Path(batch) / 'run.json'
        expected_owner = json.load(open(run, encoding='utf-8')).get('expected_owner') if run.exists() else None
    OPERATOR = re.compile(expected_owner, re.I) if expected_owner else None
    print(f'operator pattern: {expected_owner or "(none - operator_owner left blank)"}')
    rows = list(csv.DictReader(open(Path(batch) / 'sites.csv', encoding='utf-8-sig')))
    todo = [r for r in rows if r['parcel_status'] != 'ok']
    out = []
    for r in todo:
        st, co = r['state'], r['parcel_county']
        rec = dict(site_id=r['site_id'], state=st, county=co, city=r['city'], address=r['address'],
                   source='', url='', result='no candidate source', parcel_id='', owner='',
                   operator_owner='', caveat=CAVEAT.get((st, co), ''))
        for name, url, fn in sources(st, co):
            rec.update(source=name, url=url)
            try:
                a = fn(float(r['lat']), float(r['lng']))
            except Exception as e:
                rec['result'] = f'error: {str(e)[:80]}'
                continue
            if not a:
                rec['result'] = 'no polygon at point'
                continue
            rec.update(result='hit', parcel_id=pick(a, PID_KEY), owner=pick(a, OWNER_KEY))
            rec['operator_owner'] = 'yes' if OPERATOR and OPERATOR.search(rec['owner'] + ' ' + rec['parcel_id']) else ''
            break
        out.append(rec)
        print(st, co, r['site_id'], rec['result'], rec['owner'][:40], rec['operator_owner'])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    hits = [o for o in out if o['result'] == 'hit']
    by_state = {}
    for o in out:
        s = by_state.setdefault(o['state'], [0, 0, 0])
        s[0] += 1
        s[1] += o['result'] == 'hit'
        s[2] += o['operator_owner'] == 'yes'
    print(f'\n{len(hits)}/{len(out)} hit; {sum(o["operator_owner"] == "yes" for o in hits)} with operator-looking owner -> {OUT}')
    for s, (n, h, op) in sorted(by_state.items()):
        print(f'  {s}: {h}/{n} hit, {op} operator owner')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('batch')
    ap.add_argument('--expected-owner', default=None, help="regex; default: the batch's run.json expected_owner")
    a = ap.parse_args()
    main(a.batch, a.expected_owner)
