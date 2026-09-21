# -*- coding: utf-8 -*-
import zipfile, xml.etree.ElementTree as ET, math

K = '{http://www.opengis.net/kml/2.2}'
kml = zipfile.ZipFile(r'C:\Users\tucke\Downloads\WS Targeted Sites Overview 26.8.20.kmz').read('doc.kml').decode('utf-8', 'replace')
root = ET.fromstring(kml)

def ring_area(ring):
    R = 6378137.0
    if ring[0] != ring[-1]: ring = ring + [ring[0]]
    t = 0.0
    for i in range(len(ring) - 1):
        x1, y1 = math.radians(ring[i][0]), math.radians(ring[i][1])
        x2, y2 = math.radians(ring[i+1][0]), math.radians(ring[i+1][1])
        t += (x2 - x1) * (2 + math.sin(y1) + math.sin(y2))
    return abs(t * R * R / 2.0)

for pm in root.iter(K + 'Placemark'):
    poly = pm.find(f'.//{K}Polygon')
    if poly is None: continue
    nm = pm.find(K + 'name')
    coords = poly.find(f'.//{K}coordinates').text.split()
    ring = [(float(c.split(',')[0]), float(c.split(',')[1])) for c in coords]
    m2 = ring_area(ring)
    lons = [p[0] for p in ring]; lats = [p[1] for p in ring]
    print('NAME:', (nm.text or '').strip())
    print(f'  vertices: {len(ring)}')
    print(f'  area: {m2:,.1f} m2 = {m2/4046.856:.4f} acres = {m2*10.7639:,.0f} sqft')
    print(f'  centroid approx: {sum(lats)/len(lats):.6f}, {sum(lons)/len(lons):.6f}')
    print(f'  bbox: lat {min(lats):.6f}..{max(lats):.6f}  lng {min(lons):.6f}..{max(lons):.6f}')
    # distance from the NRFDOHXA site point
    slat, slng = 41.31474448, -81.53703932
    clat, clng = sum(lats)/len(lats), sum(lons)/len(lons)
    dlat = (clat - slat) * 111320
    dlng = (clng - slng) * 111320 * math.cos(math.radians(slat))
    print(f'  centroid is {math.hypot(dlat, dlng):.0f} m from the NRFDOHXA site point')
