# -*- coding: utf-8 -*-
"""Build the Windstream 200 regression fixture in the bulk input format.

Reads the broker workbook (Top 200 COs sheet) and the broker KMZ site list
(ws_broker_sites.csv, from scripts/windstream_kmz/parse_kmz.py), writes
scripts/bulk/fixtures/windstream_200.csv with:
    site_id = CLLI, lat/lng, name = Site_Number, address, state, county (blank),
    group = Interesting | Top | Other, plus pass-through: city, land_ownership,
    asset_type, primary_use, rack_count
"""
import csv, os, sys
import openpyxl

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
XLSX = os.path.join(ROOT, 'Windstream site data', 'TBDI Windstream Top 200 COs v6.29.26 vTA.xlsx')
BROKER = os.path.join(ROOT, 'Windstream site data', 'ws_broker_sites.csv')
OUT = os.path.join(HERE, 'windstream_200.csv')

grp = {}
for r in csv.DictReader(open(BROKER, encoding='utf-8')):
    f = r['folder'].strip()
    if f == 'Interesting Sites':
        grp[r['name'].strip()] = 'Interesting'
    elif f == 'Top Sites' and r['name'].strip() not in grp:
        grp[r['name'].strip()] = 'Top'

wb = openpyxl.load_workbook(XLSX, read_only=True, data_only=True)
ws = wb['Top 200 COs']
rows = ws.iter_rows(values_only=True)
hdr = [str(h).strip() if h is not None else '' for h in next(rows)]
ix = {h: i for i, h in enumerate(hdr)}
out = []
for r in rows:
    clli = r[ix['CLLI']]
    if not clli:
        continue
    out.append({
        'site_id': clli, 'lat': r[ix['LAT']], 'lng': r[ix['LONG']],
        'name': r[ix['Site_Number']] or '', 'address': r[ix['Address']] or '',
        'state': r[ix['State']] or '', 'county': '', 'group': grp.get(clli, 'Other'), 'notes': '',
        'city': r[ix['City']] or '', 'land_ownership': r[ix['Land_Ownership']] or '',
        'asset_type': r[ix['Asset_Type']] or '', 'primary_use': r[ix['Primary_Use']] or '',
        'rack_count': r[ix['Rack Count']] if r[ix['Rack Count']] is not None else '',
    })
cols = ['site_id', 'lat', 'lng', 'name', 'address', 'state', 'county', 'group', 'notes',
        'city', 'land_ownership', 'asset_type', 'primary_use', 'rack_count']
with open(OUT, 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(out)
from collections import Counter
print(f'wrote {OUT}: {len(out)} sites; groups {dict(Counter(o["group"] for o in out))}')
