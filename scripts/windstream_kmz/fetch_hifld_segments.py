# -*- coding: utf-8 -*-
"""Pull HIFLD transmission-line segments within RADIUS m of each site and freeze
them as GeoJSON in the project, so the KMZ build never depends on a prior KMZ.

Source: the full national HIFLD/EIA layer (94,619 segments incl. sub-100 kV).
Same query build_kmz.py used on 2026-08-24; segments are deduped by HIFLD ID.

Run from the project root:
    .venv_fema/Scripts/python.exe scripts/windstream_kmz/fetch_hifld_segments.py
"""
import csv, json, os, sys, time, urllib.parse, urllib.request
from datetime import datetime, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
SITES_CSV = os.path.join(ROOT, 'Outputs', 'Excel outputs', 'WS_Top200_Transmission_Distance.csv')
OUT_DIR = os.path.join(ROOT, 'Windstream site data')
OUT_GEOJSON = os.path.join(OUT_DIR, 'hifld_tx_segments_5km.geojson')
OUT_META = os.path.join(OUT_DIR, 'hifld_tx_segments_5km.meta.json')
# Second product: the specific segments the Transmission_Distance CSV names as each
# site's nearest line (any voltage) and nearest >=100 kV line. tx_distance.py found
# those with a 15 km query, so some lie outside the 5 km set above.
OUT_NEAREST = os.path.join(OUT_DIR, 'hifld_tx_nearest_segments.geojson')

LYR = ('https://services2.arcgis.com/FiaPA4ga0iQKduv3/arcgis/rest/services/'
       'US_Electric_Power_Transmission_Lines/FeatureServer/0')
FIELDS = 'VOLTAGE,VOLT_CLASS,OWNER,STATUS,TYPE,ID,SUB_1,SUB_2,INFERRED,SOURCEDATE'
RADIUS = 5000  # metres
UA = {'User-Agent': 'Mozilla/5.0'}


def jget(u, t=60, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=t) as r:
                return json.loads(r.read().decode('utf-8', 'replace'))
        except Exception as e:
            if i == tries - 1:
                return {'__error__': str(e)[:160]}
            time.sleep(1.5)


def query_near(lat, lng):
    geom = json.dumps({'x': lng, 'y': lat, 'spatialReference': {'wkid': 4326}})
    u = (LYR + f'/query?f=geojson&outFields={FIELDS}'
         '&returnGeometry=true&geometryType=esriGeometryPoint&inSR=4326&outSR=4326'
         f'&distance={RADIUS}&units=esriSRUnit_Meter&spatialRel=esriSpatialRelIntersects'
         '&geometry=' + urllib.parse.quote(geom))
    return jget(u)


def query_by_ids(ids):
    """Fetch segments by HIFLD ID in chunks; returns {id: feature}."""
    got = {}
    ids = sorted(set(str(i) for i in ids if i))
    for k in range(0, len(ids), 100):
        chunk = ids[k:k + 100]
        where = 'ID IN (' + ','.join(chunk) + ')'
        u = (LYR + f'/query?f=geojson&outFields={FIELDS}&returnGeometry=true&outSR=4326'
             '&where=' + urllib.parse.quote(where))
        r = jget(u)
        if not isinstance(r, dict) or '__error__' in r or 'error' in r:
            print(f'  by-ID chunk {k // 100} failed: {str(r)[:120]}')
            continue
        for f in r.get('features') or []:
            lid = (f.get('properties') or {}).get('ID')
            if lid is not None:
                got[str(lid)] = f
    return got


def main():
    sites = list(csv.DictReader(open(SITES_CSV, encoding='utf-8-sig')))
    print(f'sites: {len(sites)}  radius: {RADIUS} m  layer: {LYR}')

    layer_meta = jget(LYR + '?f=json')

    # ---- part 2: named nearest segments, by ID ----
    want = set()
    for s in sites:
        for col in ('line_id', 'line_id_100plus'):
            if s.get(col):
                want.add(str(int(float(s[col]))))
    print(f'named nearest-line IDs in CSV: {len(want)}')
    named = query_by_ids(want)
    missing_ids = sorted(want - set(named))
    with open(OUT_NEAREST, 'w', encoding='utf-8') as f:
        json.dump({'type': 'FeatureCollection', 'features': list(named.values())}, f,
                  separators=(',', ':'))
    print(f'wrote {OUT_NEAREST}  ({len(named)} segments; missing IDs: {missing_ids})')

    # ---- part 1: everything within RADIUS of any site ----
    features = {}          # HIFLD ID -> feature
    per_site = {}          # CLLI -> [ids]
    errors = []
    for i, s in enumerate(sites, 1):
        clli = s['CLLI']
        try:
            la, ln = float(s['lat']), float(s['lng'])
        except (TypeError, ValueError):
            errors.append((clli, 'bad coordinate')); continue
        r = query_near(la, ln)
        if not isinstance(r, dict) or '__error__' in r or 'error' in r:
            errors.append((clli, str(r)[:120])); continue
        ids = []
        for f in r.get('features') or []:
            p = f.get('properties') or {}
            lid = p.get('ID')
            if lid is None:
                continue
            ids.append(lid)
            if lid not in features:
                features[lid] = f
        per_site[clli] = ids
        if i % 25 == 0:
            print(f'  {i}/{len(sites)}  unique segments so far: {len(features)}', flush=True)

    os.makedirs(OUT_DIR, exist_ok=True)
    fc = {'type': 'FeatureCollection', 'features': list(features.values())}
    with open(OUT_GEOJSON, 'w', encoding='utf-8') as f:
        json.dump(fc, f, separators=(',', ':'))

    kv = {}
    for f in features.values():
        v = (f.get('properties') or {}).get('VOLTAGE')
        try:
            v = float(v)
        except (TypeError, ValueError):
            v = None
        band = ('not_published' if v is None or v <= 0 else
                'sub100' if v < 100 else '100-161' if v < 200 else
                '230-287' if v < 300 else '345' if v < 400 else '500+')
        kv[band] = kv.get(band, 0) + 1

    meta = {
        'fetched_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'source': LYR,
        'source_layer_name': layer_meta.get('name'),
        'source_data_last_edit': layer_meta.get('editingInfo', {}).get('dataLastEditDate'),
        'radius_m': RADIUS,
        'sites_queried': len(sites),
        'sites_ok': len(per_site),
        'sites_failed': errors,
        'unique_segments': len(features),
        'segments_by_voltage_band': kv,
        'nearest_segments_file': os.path.basename(OUT_NEAREST),
        'nearest_segments_requested': len(want),
        'nearest_segments_fetched': len(named),
        'nearest_segments_missing_ids': missing_ids,
        'segment_ids_per_site': per_site,
    }
    with open(OUT_META, 'w', encoding='utf-8') as f:
        json.dump(meta, f, indent=1)

    print(f'\nwrote {OUT_GEOJSON}  ({os.path.getsize(OUT_GEOJSON)/1e6:.1f} MB)')
    print(f'wrote {OUT_META}')
    print(f'  sites ok {len(per_site)}/{len(sites)}   unique segments {len(features)}')
    print(f'  by voltage band: {kv}')
    if errors:
        print(f'  FAILED sites: {errors}')
    return 0 if not errors else 1


if __name__ == '__main__':
    sys.exit(main())
