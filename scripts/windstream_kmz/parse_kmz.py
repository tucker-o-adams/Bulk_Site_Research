# -*- coding: utf-8 -*-
"""Extract point placemarks (sites) from a KMZ into CSV. Local only."""
import zipfile, xml.etree.ElementTree as ET, csv, sys
from collections import Counter

K = '{http://www.opengis.net/kml/2.2}'
SRC = r'C:\Users\tucke\Downloads\WS Targeted Sites Overview 26.8.20.kmz'
OUT = r'C:\Users\tucke\AppData\Local\Temp\claude\C--Users-tucke-OneDrive-Documents-Claude-Projects-TBDI-Modeling-Mireye\069ba4fb-4a95-4044-854a-837cbdc98b0b\scratchpad\ws_sites.csv'

kml = zipfile.ZipFile(SRC).read('doc.kml').decode('utf-8', 'replace')
root = ET.fromstring(kml)

rows = []

def walk(el, folder):
    for child in el:
        if child.tag == K + 'Folder':
            nm = child.find(K + 'name')
            walk(child, nm.text if nm is not None else folder)
        elif child.tag == K + 'Placemark':
            nm = child.find(K + 'name')
            name = (nm.text or '').strip() if nm is not None else ''
            pt = child.find('.//' + K + 'Point/' + K + 'coordinates')
            if pt is None:
                continue  # skip rings / linestrings / polygons
            parts = pt.text.strip().split(',')
            lng, lat = float(parts[0]), float(parts[1])
            data = {}
            for sd in child.iter(K + 'SimpleData'):
                data[sd.get('name')] = (sd.text or '').strip()
            for d in child.iter(K + 'Data'):
                v = d.find(K + 'value')
                data[d.get('name')] = (v.text or '').strip() if v is not None else ''
            rows.append({
                'folder': folder,
                'name': name,
                'lat': lat,
                'lng': lng,
                'address': data.get('Address', ''),
            })
        else:
            walk(child, folder)

walk(root, '')

print('POINT PLACEMARKS:', len(rows))
for k, v in Counter(r['folder'] for r in rows).items():
    print(f'  {k}: {v}')

with open(OUT, 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=['folder', 'name', 'lat', 'lng', 'address'])
    w.writeheader()
    w.writerows(rows)
print('wrote', OUT)

print('\n--- all sites ---')
for r in rows:
    print(f"{r['folder'][:22]:22} | {r['name'][:40]:40} | {r['lat']:.5f}, {r['lng']:.5f} | {r['address'][:50]}")
