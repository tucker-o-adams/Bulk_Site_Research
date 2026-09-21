# -*- coding: utf-8 -*-
"""Pull the parcel polygon under each Interesting Site's pin from the county GIS
service recorded in WS_Sites_Parcel_Sizes_FINAL.csv, and freeze them as GeoJSON.

Same point-in-polygon query add_parcels.py ran live on 2026-08-24. Only rows with
status == ok and an http source are queryable (34 of 45); the other 11 have no
public parcel service (7 GA qPublic counties, 3 KY PVA, 1 TX).

Run from the project root:
    .venv_fema/Scripts/python.exe scripts/windstream_kmz/fetch_parcel_polygons.py
"""
import csv, json, os, sys, time, urllib.parse, urllib.request
from datetime import datetime, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
PARCEL_CSV = os.path.join(ROOT, 'Outputs', 'Excel outputs', 'WS_Sites_Parcel_Sizes_FINAL.csv')
OUT_DIR = os.path.join(ROOT, 'Windstream site data')
OUT_GEOJSON = os.path.join(OUT_DIR, 'parcel_polygons.geojson')
OUT_META = os.path.join(OUT_DIR, 'parcel_polygons.meta.json')
UA = {'User-Agent': 'Mozilla/5.0'}


def jget(u, t=50, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=t) as r:
                return json.loads(r.read().decode('utf-8', 'replace'))
        except Exception as e:
            if i == tries - 1:
                return {'__error__': str(e)[:160]}
            time.sleep(1.5)


def main():
    rows = [r for r in csv.DictReader(open(PARCEL_CSV, encoding='utf-8-sig'))
            if r['status'] == 'ok' and r['source'].startswith('http')]
    print(f'sites with a queryable parcel source: {len(rows)}')

    feats, failed = [], []
    for i, r in enumerate(rows, 1):
        geom = json.dumps({'x': float(r['lng']), 'y': float(r['lat']),
                           'spatialReference': {'wkid': 4326}})
        u = (r['source'] + '/query?f=geojson&outFields=*&returnGeometry=true'
             '&geometryType=esriGeometryPoint&inSR=4326&outSR=4326'
             '&spatialRel=esriSpatialRelIntersects&geometry=' + urllib.parse.quote(geom))
        res = jget(u)
        fl = (res or {}).get('features') or [] if isinstance(res, dict) else []
        if not fl:
            failed.append((r['clli'], str(res)[:100] if not isinstance(res, dict) or '__error__' in res
                           else 'no geometry returned'))
            print(f"   {r['clli']}: no geometry")
            continue
        f = fl[0]
        g = f.get('geometry') or {}
        if g.get('type') not in ('Polygon', 'MultiPolygon'):
            failed.append((r['clli'], f"geometry type {g.get('type')}")); continue
        # keep the county's attributes, but prefix ours so they never collide
        props = {'_clli': r['clli'], '_parcel_id': r['parcel_id'], '_county': r['county'],
                 '_state': r['state'], '_source': r['source'],
                 '_acres_gis': r['acres_gis'], '_acres_stated': r['acres_stated']}
        props.update({k: v for k, v in (f.get('properties') or {}).items()})
        feats.append({'type': 'Feature', 'geometry': g, 'properties': props})
        if i % 10 == 0:
            print(f'  {i}/{len(rows)}  polygons: {len(feats)}', flush=True)

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_GEOJSON, 'w', encoding='utf-8') as f:
        json.dump({'type': 'FeatureCollection', 'features': feats}, f, separators=(',', ':'))
    meta = {'fetched_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'queryable_sites': len(rows), 'polygons': len(feats), 'failed': failed,
            'sources': sorted({r['source'] for r in rows})}
    with open(OUT_META, 'w', encoding='utf-8') as f:
        json.dump(meta, f, indent=1)
    print(f'\nwrote {OUT_GEOJSON}  ({len(feats)} polygons)')
    if failed:
        print(f'  FAILED: {failed}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
