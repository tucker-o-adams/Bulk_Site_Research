# -*- coding: utf-8 -*-
import json, urllib.parse, urllib.request
UA = {'User-Agent': 'Mozilla/5.0'}
def jget(u, t=45):
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=t) as r:
            return json.loads(r.read().decode('utf-8', 'replace'))
    except Exception as e:
        return {'__error__': str(e)[:120]}

L = ('https://services1.arcgis.com/Hp6G80Pky0om7QvQ/arcgis/rest/services/'
     'Electric_Power_Transmission_Lines/FeatureServer/0')

print('total features:', jget(L + '/query?f=json&where=1%3D1&returnCountOnly=true').get('count'))
for w in ['VOLTAGE < 100', 'VOLTAGE >= 100', 'VOLTAGE < 0', 'VOLTAGE = 69', 'VOLTAGE BETWEEN 1 AND 99']:
    c = jget(L + '/query?f=json&returnCountOnly=true&where=' + urllib.parse.quote(w))
    print(f'  {w:28} -> {c.get("count", c.get("__error__"))}')

print('\nVOLT_CLASS distribution:')
r = jget(L + '/query?f=json&where=1%3D1&outFields=VOLT_CLASS&returnDistinctValues=true&returnGeometry=false')
vals = sorted({(f['attributes'].get('VOLT_CLASS') or 'NULL') for f in (r.get('features') or [])})
print('  ', vals)

# Is there a fuller national layer that includes sub-100kV?
print('\n=== alternates that may include <100 kV ===')
for u in ['https://services2.arcgis.com/FiaPA4ga0iQKduv3/arcgis/rest/services/US_Electric_Power_Transmission_Lines/FeatureServer/0',
          'https://services2.arcgis.com/LYMgRMwHfrWWEg3s/arcgis/rest/services/HIFLD_US_Electric_Power_Transmission_Lines/FeatureServer/0']:
    m = jget(u + '?f=json')
    if '__error__' in m or 'error' in m:
        print('  FAIL', u[:92]); continue
    tot = jget(u + '/query?f=json&where=1%3D1&returnCountOnly=true').get('count')
    sub = jget(u + '/query?f=json&returnCountOnly=true&where=' + urllib.parse.quote('VOLTAGE < 100 AND VOLTAGE > 0')).get('count')
    print(f'  OK {m.get("name")}: total={tot} sub100kV={sub}')
    print(f'     {u}')
