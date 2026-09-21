# -*- coding: utf-8 -*-
"""Locate a public transmission-line feature service and test it."""
import json, urllib.parse, urllib.request

UA = {'User-Agent': 'Mozilla/5.0'}
def jget(u, t=35):
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=t) as r:
            return json.loads(r.read().decode('utf-8', 'replace'))
    except Exception as e:
        return {'__error__': str(e)[:130]}

print('=== AGOL search ===')
for q in ['title:"Electric Power Transmission Lines"',
          'Transmission Lines HIFLD type:"Feature Service"',
          'owner:eia_opendata transmission']:
    r = jget('https://www.arcgis.com/sharing/rest/search?f=json&num=8&q=' + urllib.parse.quote(q))
    print(f'\n  Q: {q}')
    for it in (r.get('results') or []):
        print(f"    {(it.get('title') or '')[:48]:48} | {(it.get('owner') or '')[:20]:20} | {(it.get('url') or '')[:88]}")

CANDS = [
 'https://services1.arcgis.com/Hp6G80Pky0om7QvQ/arcgis/rest/services/Electric_Power_Transmission_Lines/FeatureServer/0',
 'https://services7.arcgis.com/FGr1D95XCGALKXqM/arcgis/rest/services/Electric_Power_Transmission_Lines/FeatureServer/0',
 'https://atlas.eia.gov/server/rest/services/Hosted/Electric_Power_Transmission_Lines/FeatureServer/0',
]
print('\n=== probe candidates ===')
for u in CANDS:
    m = jget(u + '?f=json')
    if '__error__' in m or 'error' in m:
        print(f'  FAIL {u[:95]}')
        continue
    print(f'  OK   {m.get("name")} | geom={m.get("geometryType")} | maxRec={m.get("maxRecordCount")}')
    print(f'       {u}')
    print('       fields:', [f['name'] for f in (m.get('fields') or [])][:14])
