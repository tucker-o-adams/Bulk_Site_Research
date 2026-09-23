# -*- coding: utf-8 -*-
"""Build the Windstream 200 regression fixture in the bulk input format.

Reads the broker workbook (Top 200 COs sheet), writes
scripts/bulk/fixtures/windstream_200.csv with:
    site_id = CLLI, lat/lng, name = Site_Number, address, state, county (blank),
    plus pass-through: city, land_ownership, asset_type, primary_use, rack_count.
    No `group`: the broker's Interesting / Top / Other split is no longer used
    (dropped 2026-09-23), so the KMZ and workbook show one flat site list.
"""
import csv, os, sys
import openpyxl

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
XLSX = os.path.join(ROOT, 'Windstream site data', 'TBDI Windstream Top 200 COs v6.29.26 vTA.xlsx')
OUT = os.path.join(HERE, 'windstream_200.csv')

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
        'state': r[ix['State']] or '', 'county': '', 'notes': '',
        'city': r[ix['City']] or '', 'land_ownership': r[ix['Land_Ownership']] or '',
        'asset_type': r[ix['Asset_Type']] or '', 'primary_use': r[ix['Primary_Use']] or '',
        'rack_count': r[ix['Rack Count']] if r[ix['Rack Count']] is not None else '',
    })
cols = ['site_id', 'lat', 'lng', 'name', 'address', 'state', 'county', 'notes',
        'city', 'land_ownership', 'asset_type', 'primary_use', 'rack_count']
with open(OUT, 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(out)
print(f'wrote {OUT}: {len(out)} sites')
