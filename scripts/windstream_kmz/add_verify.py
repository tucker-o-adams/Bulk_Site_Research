# -*- coding: utf-8 -*-
"""Add folder F: per-site verification folders (site marker + its nearest line), grouped by state.
Reuses the segments already embedded in folder D, so no re-querying and guaranteed consistency."""
import csv, html, os, re, zipfile
import xml.etree.ElementTree as ET

K = 'http://www.opengis.net/kml/2.2'
ET.register_namespace('', K)
NS = '{%s}' % K
BASE = r'C:\Users\tucke\OneDrive\Documents\Claude\Projects\TBDI Modeling\Mireye'
COMBINED = os.path.join(BASE, 'TBDI_WS_Combined.kmz')
TXCSV = os.path.join(BASE, 'WS_Top200_Transmission_Distance.csv')

def esc(v):
    return html.escape('' if v is None else str(v))

sites = {s['CLLI']: s for s in csv.DictReader(open(TXCSV, encoding='utf-8-sig'))}

root = ET.fromstring(zipfile.ZipFile(COMBINED).read('doc.kml').decode('utf-8', 'replace'))
doc = root.find(NS + 'Document')

# ---- harvest the already-built nearest segments from folder D
segs = {}
for f in doc.iter(NS + 'Folder'):
    nm = f.find(NS + 'name')
    if nm is None or not (nm.text or '').startswith('Identified nearest segments'):
        continue
    for pm in f.findall(NS + 'Placemark'):
        pnm = pm.find(NS + 'name')
        if pnm is None:
            continue
        clli = (pnm.text or '').split('—')[0].strip()
        segs[clli] = pm
    break
print(f'segments harvested from folder D: {len(segs)}')

# style for the verification marker (distinct from other site pins)
st = ET.SubElement(doc, NS + 'Style', {'id': 'verifySite'})
ics = ET.SubElement(st, NS + 'IconStyle')
ET.SubElement(ics, NS + 'scale').text = '1.2'
ET.SubElement(ics, NS + 'color').text = 'ff00ff00'
icon = ET.SubElement(ics, NS + 'Icon')
ET.SubElement(icon, NS + 'href').text = 'http://maps.google.com/mapfiles/kml/paddle/grn-circle.png'

F = ET.SubElement(doc, NS + 'Folder')
ET.SubElement(F, NS + 'name').text = 'F. Site-by-site verification'
ET.SubElement(F, NS + 'visibility').text = '0'
ET.SubElement(F, NS + 'open').text = '0'
ET.SubElement(F, NS + 'description').text = (
    'One folder per site: the site marker and the single transmission line identified as its '
    'nearest. Tick one folder at a time to spot-check. Double-click a folder to fly to it. '
    'Note: HIFLD line geometry is national-scale, so a line may render 20-50 m off the '
    'visible towers - look for gross errors (wrong side of town, a closer line missed), '
    'not small offsets.')

by_state = {}
for clli, s in sites.items():
    if clli in segs:
        by_state.setdefault(s['State'] or '??', []).append(clli)

total = 0
for stt in sorted(by_state):
    clis = sorted(by_state[stt])
    SF = ET.SubElement(F, NS + 'Folder')
    ET.SubElement(SF, NS + 'name').text = f'{stt} ({len(clis)})'
    ET.SubElement(SF, NS + 'open').text = '0'
    for clli in clis:
        s = sites[clli]
        try:
            la, ln = float(s['lat']), float(s['lng'])
            dist = float(s['nearest_tx_line_m'])
        except (TypeError, ValueError):
            continue
        kv = s.get('voltage_kv')
        try:
            kvf = float(kv)
            kvtxt = f'{kvf:g} kV' if kvf > 0 else 'kV n/p'
        except (TypeError, ValueError):
            kvtxt = 'kV n/p'

        SITEF = ET.SubElement(SF, NS + 'Folder')
        ET.SubElement(SITEF, NS + 'name').text = f'{clli} — {kvtxt} @ {dist:.0f} m'
        ET.SubElement(SITEF, NS + 'visibility').text = '0'
        # camera framing: wide enough to hold site + line
        look = ET.SubElement(SITEF, NS + 'LookAt')
        ET.SubElement(look, NS + 'longitude').text = str(ln)
        ET.SubElement(look, NS + 'latitude').text = str(la)
        ET.SubElement(look, NS + 'altitude').text = '0'
        ET.SubElement(look, NS + 'heading').text = '0'
        ET.SubElement(look, NS + 'tilt').text = '0'
        ET.SubElement(look, NS + 'range').text = str(max(400.0, dist * 4.0))
        ET.SubElement(look, NS + 'altitudeMode').text = 'relativeToGround'

        pm = ET.SubElement(SITEF, NS + 'Placemark')
        ET.SubElement(pm, NS + 'name').text = f'{clli} (site)'
        ET.SubElement(pm, NS + 'styleUrl').text = '#verifySite'
        ET.SubElement(pm, NS + 'description').text = (
            f"<b>{esc(clli)}</b> ({esc(s['State'])})<br/>"
            f"Nearest line: <b>{dist:.0f} m</b> ({dist*3.28084:.0f} ft)<br/>"
            f"Voltage: {esc(kv)} [{esc(s.get('voltage_basis'))}]<br/>"
            f"Circuit: {esc(s.get('line_name')) or '(unnamed)'} id={esc(s.get('line_id'))}<br/>"
            f"Owner: {esc(s.get('owner'))}<br/>"
            f"Attrs inferred: {esc(s.get('attrs_inferred'))}<br/>"
            f"Nearest &ge;100kV: {esc(s.get('nearest_100kv_plus_m'))} m @ {esc(s.get('kv_100plus'))} kV")
        pt = ET.SubElement(pm, NS + 'Point')
        ET.SubElement(pt, NS + 'coordinates').text = f'{ln},{la},0'

        # deep-copy the harvested segment placemark
        SITEF.append(ET.fromstring(ET.tostring(segs[clli])))
        total += 1

print(f'per-site folders built: {total} across {len(by_state)} states')

OUT = COMBINED
data = ET.tostring(root, encoding='utf-8', xml_declaration=True)
try:
    zf = zipfile.ZipFile(OUT, 'w', zipfile.ZIP_DEFLATED)
except PermissionError:
    OUT = OUT.replace('.kmz', '_v2.kmz')
    zf = zipfile.ZipFile(OUT, 'w', zipfile.ZIP_DEFLATED)
with zf as z:
    z.writestr('doc.kml', data)
t = zipfile.ZipFile(OUT).read('doc.kml').decode('utf-8')
ET.fromstring(t)
print(f'\nwrote {OUT} ({os.path.getsize(OUT)/1024:.0f} KB)')
print(f'  XML OK | folders={t.count("<Folder")} | placemarks={t.count("<Placemark")}')
