# -*- coding: utf-8 -*-
"""Fetch parcel polygons for the resolved sites and add them to the KMZ:
   - into each per-site verification folder in F (so you see parcel + site + line together)
   - plus a standalone 'Parcel boundaries' folder."""
import csv, html, json, os, time, urllib.parse, urllib.request, zipfile
import xml.etree.ElementTree as ET

K = 'http://www.opengis.net/kml/2.2'
ET.register_namespace('', K)
NS = '{%s}' % K
UA = {'User-Agent': 'Mozilla/5.0'}
BASE = r'C:\Users\tucke\OneDrive\Documents\Claude\Projects\TBDI Modeling\Mireye'
KMZ = os.path.join(BASE, 'TBDI_WS_Combined_2.kmz')
PARCEL = os.path.join(BASE, 'WS_Sites_Parcel_Sizes_FINAL.csv')

def jget(u, t=50, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=t) as r:
                return json.loads(r.read().decode('utf-8', 'replace'))
        except Exception:
            if i == tries - 1:
                return None
            time.sleep(1.5)

def esc(v):
    return html.escape('' if v is None else str(v))

rows = [r for r in csv.DictReader(open(PARCEL, encoding='utf-8-sig'))
        if r['status'] == 'ok' and r['source'].startswith('http')]
print(f'sites with a queryable parcel source: {len(rows)}')

polys = {}
for i, r in enumerate(rows, 1):
    geom = json.dumps({'x': float(r['lng']), 'y': float(r['lat']),
                       'spatialReference': {'wkid': 4326}})
    u = (r['source'] + '/query?f=geojson&outFields=*&returnGeometry=true'
         '&geometryType=esriGeometryPoint&inSR=4326&outSR=4326'
         '&spatialRel=esriSpatialRelIntersects&geometry=' + urllib.parse.quote(geom))
    res = jget(u)
    feats = ((res or {}).get('features') or [])
    if not feats:
        print(f"   {r['clli']}: no geometry returned")
        continue
    g = feats[0].get('geometry') or {}
    if g.get('type') == 'Polygon':
        rings = [g['coordinates']]
    elif g.get('type') == 'MultiPolygon':
        rings = g['coordinates']
    else:
        continue
    polys[r['clli']] = (rings, r)
    if i % 10 == 0:
        print(f'  {i}/{len(rows)}  polygons: {len(polys)}', flush=True)

print(f'polygons retrieved: {len(polys)}')

root = ET.fromstring(zipfile.ZipFile(KMZ).read('doc.kml').decode('utf-8', 'replace'))
doc = root.find(NS + 'Document')

st = ET.SubElement(doc, NS + 'Style', {'id': 'parcelPoly'})
ls = ET.SubElement(st, NS + 'LineStyle')
ET.SubElement(ls, NS + 'color').text = 'ff00ff00'      # green outline
ET.SubElement(ls, NS + 'width').text = '3'
ps = ET.SubElement(st, NS + 'PolyStyle')
ET.SubElement(ps, NS + 'color').text = '3300ff00'      # 20% green fill
ET.SubElement(ps, NS + 'fill').text = '1'
ET.SubElement(ps, NS + 'outline').text = '1'

def make_poly_pm(clli, rings, r):
    pm = ET.Element(NS + 'Placemark')
    ET.SubElement(pm, NS + 'name').text = f"{clli} parcel — {r['acres_gis']} ac"
    ET.SubElement(pm, NS + 'styleUrl').text = '#parcelPoly'
    stated = r.get('acres_stated') or ''
    warn = ''
    try:
        if stated and abs(float(stated) - float(r['acres_gis'])) / float(stated) > 0.25:
            warn = '<br/><b style="color:#c00">CONFLICT: GIS vs county acreage differ &gt;25%</b>'
    except (TypeError, ValueError, ZeroDivisionError):
        pass
    ET.SubElement(pm, NS + 'description').text = (
        f"<b>{esc(clli)}</b> parcel<br/>{esc(r.get('address'))}<br/>"
        f"{esc(r.get('county'))} Co, {esc(r.get('state'))}<br/><br/>"
        f"GIS area: <b>{esc(r.get('acres_gis'))} ac</b> ({esc(r.get('sqft_gis'))} sq ft)<br/>"
        f"County stated: {esc(stated)} [{esc(r.get('acres_stated_field'))}]<br/>"
        f"Parcel ID: {esc(r.get('parcel_id'))}<br/>Owner: {esc(r.get('owner'))}<br/>"
        f"<i>Single parcel at the site pin — an assemblage will show the building "
        f"extending beyond this boundary.</i>{warn}")
    mg = ET.SubElement(pm, NS + 'MultiGeometry')
    for poly in rings:
        pg = ET.SubElement(mg, NS + 'Polygon')
        ET.SubElement(pg, NS + 'tessellate').text = '1'
        ob = ET.SubElement(pg, NS + 'outerBoundaryIs')
        lr = ET.SubElement(ob, NS + 'LinearRing')
        ET.SubElement(lr, NS + 'coordinates').text = ' '.join(f'{c[0]},{c[1]},0' for c in poly[0])
        for hole in poly[1:]:
            ib = ET.SubElement(pg, NS + 'innerBoundaryIs')
            lr2 = ET.SubElement(ib, NS + 'LinearRing')
            ET.SubElement(lr2, NS + 'coordinates').text = ' '.join(f'{c[0]},{c[1]},0' for c in hole)
    return pm

# ---- 1. standalone folder
G = ET.SubElement(doc, NS + 'Folder')
ET.SubElement(G, NS + 'name').text = f'G. Parcel boundaries ({len(polys)} of 45)'
ET.SubElement(G, NS + 'visibility').text = '0'
ET.SubElement(G, NS + 'description').text = (
    'County GIS parcel polygons for the Interesting Sites. 11 sites have no public '
    'parcel service (7 GA on qPublic, 3 KY PVA, 1 TX) and are absent here. '
    'Each polygon is the SINGLE parcel under the site pin, not the full assemblage.')
for clli in sorted(polys):
    rings, r = polys[clli]
    G.append(make_poly_pm(clli, rings, r))

# ---- 2. drop a copy into each per-site verification folder
Fnode = next((f for f in doc.findall(NS + 'Folder')
              if (f.find(NS + 'name') is not None
                  and (f.find(NS + 'name').text or '').startswith('F. Site-by-site'))), None)
added = 0
if Fnode is not None:
    for stf in Fnode.iter(NS + 'Folder'):
        nm = stf.find(NS + 'name')
        if nm is None:
            continue
        clli = (nm.text or '').split('—')[0].strip()
        if clli in polys and stf.find(NS + 'Point') is None:
            # only site folders (they contain a Placemark named "<CLLI> (site)")
            names = [(p.find(NS + 'name').text or '') for p in stf.findall(NS + 'Placemark')
                     if p.find(NS + 'name') is not None]
            if any(n.endswith('(site)') for n in names):
                rings, r = polys[clli]
                stf.append(make_poly_pm(clli, rings, r))
                added += 1
print(f'parcel polygons added into per-site folders: {added}')

data = ET.tostring(root, encoding='utf-8', xml_declaration=True)
OUT = KMZ
try:
    zf = zipfile.ZipFile(OUT, 'w', zipfile.ZIP_DEFLATED)
except PermissionError:
    OUT = OUT.replace('.kmz', '_new.kmz')
    zf = zipfile.ZipFile(OUT, 'w', zipfile.ZIP_DEFLATED)
with zf as z:
    z.writestr('doc.kml', data)
t = zipfile.ZipFile(OUT).read('doc.kml').decode('utf-8')
ET.fromstring(t)
print(f'\nwrote {OUT} ({os.path.getsize(OUT)/1024:.0f} KB)')
print(f'  XML OK | folders={t.count("<Folder")} | placemarks={t.count("<Placemark")}')
