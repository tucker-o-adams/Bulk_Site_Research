# -*- coding: utf-8 -*-
"""Build the two CMS reference files the `healthcare` producer reads.

  data/reference/cms_nursing_homes.csv   CMS Provider Data Catalog "Provider Information"
                                         (dataset 4pq5-n9py): name, address, beds, ownership,
                                         overall rating, CMS's own latitude/longitude + footnote
  data/reference/cms_hospitals.csv       CMS "Hospital General Information" (dataset xubh-q36u):
                                         name, address, type, ownership, emergency services —
                                         addresses only, so geocoded here with the Census batch
                                         geocoder (match quality kept per row)
  data/reference/cms_reference.meta.json vintages, counts, geocode match tallies

Run when a fresh vintage is wanted (CMS updates monthly):
    .venv_fema/Scripts/python.exe scripts/bulk/reference/fetch_cms_reference.py
"""
import csv, io, json, os, sys, urllib.request
from collections import Counter
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from geocode import geocode_batch, BENCHMARK          # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
OUT_DIR = os.path.join(ROOT, 'data', 'reference')
API = 'https://data.cms.gov/provider-data/api/1'
NH_ID, HOSP_ID = '4pq5-n9py', 'xubh-q36u'
UA = {'User-Agent': 'Mozilla/5.0 (TBDI bulk site research)'}


def dataset(ident):
    meta = json.loads(urllib.request.urlopen(urllib.request.Request(f'{API}/metastore/schemas/dataset/items/{ident}', headers=UA), timeout=60).read())
    url = meta['distribution'][0]['downloadURL']
    raw = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=600).read().decode('utf-8-sig', 'replace')
    rows = list(csv.DictReader(io.StringIO(raw)))
    # CMS download files use display names ("Provider Name"); normalise to the API's snake_case
    norm = lambda k: (k or '').strip().lower().replace('/', '').replace(' ', '_')
    rows = [{norm(k): v for k, v in r.items()} for r in rows]
    return meta, url, rows


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    meta = {'built_at': datetime.now(timezone.utc).isoformat(timespec='seconds')}

    # ---- nursing homes: CMS supplies coordinates
    m, url, rows = dataset(NH_ID)
    keep = ['cms_certification_number_ccn', 'provider_name', 'provider_address', 'citytown', 'state', 'zip_code',
            'countyparish', 'ownership_type', 'provider_type', 'number_of_certified_beds', 'overall_rating',
            'latitude', 'longitude', 'geocoding_footnote']
    ccn_key = next((k for k in rows[0] if k.startswith('cms_certification_number')), None)
    with open(os.path.join(OUT_DIR, 'cms_nursing_homes.csv'), 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f); w.writerow(keep)
        n = 0
        for r in rows:
            r = dict(r); r['cms_certification_number_ccn'] = r.get(ccn_key, '')
            if not r.get('latitude') or not r.get('longitude'):
                continue
            w.writerow([r.get(k, '') for k in keep]); n += 1
    meta['nursing_homes'] = {'dataset': NH_ID, 'title': m.get('title'), 'modified': m.get('modified'), 'download': url,
                             'rows': len(rows), 'with_coordinates': n, 'coordinates_from': 'CMS (latitude/longitude columns)'}
    print(f'nursing homes: {len(rows)} rows, {n} with coordinates (CMS {m.get("modified")})')

    # ---- hospitals: addresses only -> Census batch geocoder
    m, url, rows = dataset(HOSP_ID)
    recs = [(r.get('facility_id') or str(i), r.get('address'), r.get('citytown'), r.get('state'), r.get('zip_code'))
            for i, r in enumerate(rows)]
    print(f'hospitals: {len(rows)} rows; geocoding {len(recs)} addresses via Census {BENCHMARK} ...', flush=True)
    geo = geocode_batch(recs)
    keep = ['facility_id', 'facility_name', 'address', 'citytown', 'state', 'zip_code', 'countyparish', 'hospital_type',
            'hospital_ownership', 'emergency_services', 'hospital_overall_rating', 'latitude', 'longitude',
            'geocode_match', 'geocode_match_type', 'geocode_matched_address']
    tally = Counter(); n = 0
    with open(os.path.join(OUT_DIR, 'cms_hospitals.csv'), 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f); w.writerow(keep)
        for i, r in enumerate(rows):
            fid = r.get('facility_id') or str(i)
            g = geo.get(fid, {})
            tally[g.get('match', 'No_Response')] += 1
            if g.get('lat') is None:
                continue
            row = dict(r); row.update(latitude=g['lat'], longitude=g['lng'], geocode_match=g['match'],
                                     geocode_match_type=g['match_type'], geocode_matched_address=g['matched_address'])
            w.writerow([row.get(k, '') for k in keep]); n += 1
    meta['hospitals'] = {'dataset': HOSP_ID, 'title': m.get('title'), 'modified': m.get('modified'), 'download': url,
                         'rows': len(rows), 'with_coordinates': n, 'coordinates_from': f'Census batch geocoder ({BENCHMARK})',
                         'geocode_tally': dict(tally)}
    print(f'hospitals: {n}/{len(rows)} geocoded; {dict(tally)}')

    with open(os.path.join(OUT_DIR, 'cms_reference.meta.json'), 'w', encoding='utf-8') as f:
        json.dump(meta, f, indent=1)
    print(f'wrote {OUT_DIR}')


if __name__ == '__main__':
    main()
