# -*- coding: utf-8 -*-
"""Inventory every geometry type in the KMZ."""
import zipfile, xml.etree.ElementTree as ET
from collections import Counter

K = '{http://www.opengis.net/kml/2.2}'
SRC = r'C:\Users\tucke\Downloads\WS Targeted Sites Overview 26.8.20.kmz'
kml = zipfile.ZipFile(SRC).read('doc.kml').decode('utf-8', 'replace')
root = ET.fromstring(kml)

GEOMS = ['Point', 'LineString', 'LinearRing', 'Polygon', 'MultiGeometry', 'Model', 'Track']
print('Geometry element counts across whole document:')
for g in GEOMS:
    n = len(root.findall(f'.//{K}{g}'))
    if n:
        print(f'  {g:15} {n}')

print('\nPer-placemark geometry, grouped by folder:')
rows = []
def walk(el, folder):
    for ch in el:
        if ch.tag == K + 'Folder':
            nm = ch.find(K + 'name')
            walk(ch, nm.text if nm is not None else folder)
        elif ch.tag == K + 'Placemark':
            nm = ch.find(K + 'name')
            kinds = [g for g in GEOMS if ch.find(f'.//{K}{g}') is not None]
            rows.append((folder, (nm.text or '').strip(), '+'.join(kinds) or 'NONE'))
        else:
            walk(ch, folder)
walk(root, '(root)')

for folder in dict.fromkeys(r[0] for r in rows):
    c = Counter(r[2] for r in rows if r[0] == folder)
    print(f'  {folder:34} {dict(c)}')

print('\nNon-Point placemarks:')
for f, n, k in rows:
    if k != 'Point':
        print(f'  [{f}] {n[:50]:50} -> {k}')

# does any polygon exist that could be a site boundary?
polys = root.findall(f'.//{K}Polygon')
print(f'\nPolygon count: {len(polys)}')
