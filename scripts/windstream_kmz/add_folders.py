# -*- coding: utf-8 -*-
"""Add to the combined KMZ:
   D. Nearest transmission line per site (single folder, not split by voltage)
      - the identified nearest segment for each site
      - a connector from each site to the nearest point on that segment
   E. Interesting Sites (45) promoted to top level
"""
import csv, html, json, math, os, zipfile
import xml.etree.ElementTree as ET

K = 'http://www.opengis.net/kml/2.2'
ET.register_namespace('', K)
NS = '{%s}' % K
from paths import COMBINED_KMZ, TX_CSV, BROKER_KMZ, HIFLD_5KM, HIFLD_NEAREST, load_geojson_lines
COMBINED = COMBINED_KMZ
TXCSV = TX_CSV
ORIG = BROKER_KMZ

def esc(v):
    return html.escape('' if v is None else str(v))

def foot(px, py, ax, ay, bx, by):
    """Nearest point on segment AB to P, plus distance in metres."""
    k = math.cos(math.radians(py))
    AX, AY = (ax - px) * 111320 * k, (ay - py) * 110540
    BX, BY = (bx - px) * 111320 * k, (by - py) * 110540
    dx, dy = BX - AX, BY - AY
    if dx == 0 and dy == 0:
        t = 0.0
    else:
        t = max(0.0, min(1.0, ((0 - AX) * dx + (0 - AY) * dy) / (dx * dx + dy * dy)))
    fx, fy = AX + t * dx, AY + t * dy
    return (px + fx / (111320 * k), py + fy / 110540), math.hypot(fx, fy)

sites = list(csv.DictReader(open(TXCSV, encoding='utf-8-sig')))
print(f'sites: {len(sites)}')

# Candidate segments frozen from the HIFLD source: everything within 5 km of any site
# plus the specific segments tx_distance.py identified as nearest (some lie 5-14 km out).
cand = load_geojson_lines(HIFLD_5KM, HIFLD_NEAREST)
print(f'candidate segments: {len(cand)}')

nearest = {}   # clli -> dict(props, parts, footpoint, dist)
for i, s in enumerate(sites, 1):
    if not s['nearest_tx_line_m']:
        continue
    la, ln = float(s['lat']), float(s['lng'])
    best = None
    for lid, (props, parts) in cand.items():
        for part in parts:
            for j in range(len(part) - 1):
                fp, dd = foot(ln, la, part[j][0], part[j][1], part[j+1][0], part[j+1][1])
                if best is None or dd < best['dist']:
                    best = dict(dist=dd, foot=fp, props=props, parts=parts)
    if best:
        nearest[s['CLLI']] = best
        if str(best['props'].get('ID')) != str(int(float(s['line_id']))):
            print(f"  NOTE {s['CLLI']}: geometry-nearest ID {best['props'].get('ID')} != CSV line_id {s['line_id']}")
    if i % 40 == 0:
        print(f'  {i}/{len(sites)}', flush=True)

print(f'nearest lines resolved: {len(nearest)}')

# ---------- load combined doc ----------
z = zipfile.ZipFile(COMBINED)
root = ET.fromstring(z.read('doc.kml').decode('utf-8', 'replace'))
doc = root.find(NS + 'Document')

# styles for the new folder
for sid, colour, width in [('nearLine', 'ff00ffff', 4.0), ('connector', 'ffffffff', 2.0)]:
    st = ET.SubElement(doc, NS + 'Style', {'id': sid})
    ls = ET.SubElement(st, NS + 'LineStyle')
    ET.SubElement(ls, NS + 'color').text = colour
    ET.SubElement(ls, NS + 'width').text = str(width)

# ---------- D. nearest line per site ----------
D = ET.SubElement(doc, NS + 'Folder')
ET.SubElement(D, NS + 'name').text = 'D. Nearest transmission line per site'
ET.SubElement(D, NS + 'description').text = (
    'The single line segment identified as nearest to each site, all voltages together. '
    'Connectors show the straight-line gap from site to the nearest point on that line.')

seg_f = ET.SubElement(D, NS + 'Folder')
ET.SubElement(seg_f, NS + 'name').text = f'Identified nearest segments ({len(nearest)})'
con_f = ET.SubElement(D, NS + 'Folder')
ET.SubElement(con_f, NS + 'name').text = f'Site \u2192 line connectors ({len(nearest)})'

by_row = {s['CLLI']: s for s in sites}
for clli, b in sorted(nearest.items()):
    s = by_row[clli]
    p = b['props']
    nm = ' - '.join(x for x in [(p.get('SUB_1') or '').strip(), (p.get('SUB_2') or '').strip()]
                    if x and not x.upper().startswith(('UNKNOWN', 'NOT AVAIL')))
    kv = p.get('VOLTAGE')
    kvtxt = f'{kv:g} kV' if isinstance(kv, (int, float)) and kv > 0 else 'kV n/p'
    desc = (f"<b>{esc(clli)}</b> nearest line<br/>Distance: {b['dist']:.0f} m "
            f"({b['dist']*3.28084:.0f} ft)<br/>Voltage: {esc(kv)} ({esc(p.get('VOLT_CLASS'))})<br/>"
            f"Circuit: {esc(nm) or '(unnamed)'}<br/>Line ID: {esc(p.get('ID'))}<br/>"
            f"Owner: {esc(p.get('OWNER'))}<br/>Type: {esc(p.get('TYPE'))}<br/>"
            f"Status: {esc(p.get('STATUS'))}<br/>Attributes inferred: {esc(p.get('INFERRED'))}")

    pm = ET.SubElement(seg_f, NS + 'Placemark')
    ET.SubElement(pm, NS + 'name').text = f'{clli} — {kvtxt} @ {b["dist"]:.0f} m'
    ET.SubElement(pm, NS + 'styleUrl').text = '#nearLine'
    ET.SubElement(pm, NS + 'description').text = desc
    mg = ET.SubElement(pm, NS + 'MultiGeometry')
    for part in b['parts']:
        lsx = ET.SubElement(mg, NS + 'LineString')
        ET.SubElement(lsx, NS + 'tessellate').text = '1'
        ET.SubElement(lsx, NS + 'coordinates').text = ' '.join(f'{c[0]},{c[1]},0' for c in part)

    cm = ET.SubElement(con_f, NS + 'Placemark')
    ET.SubElement(cm, NS + 'name').text = f'{clli} — {b["dist"]:.0f} m'
    ET.SubElement(cm, NS + 'styleUrl').text = '#connector'
    ET.SubElement(cm, NS + 'description').text = desc
    cls = ET.SubElement(cm, NS + 'LineString')
    ET.SubElement(cls, NS + 'tessellate').text = '1'
    fx, fy = b['foot']
    ET.SubElement(cls, NS + 'coordinates').text = f"{s['lng']},{s['lat']},0 {fx},{fy},0"

# ---------- E. Interesting Sites promoted ----------
orig = ET.fromstring(zipfile.ZipFile(ORIG).read('doc.kml').decode('utf-8', 'replace'))
E = ET.SubElement(doc, NS + 'Folder')
ET.SubElement(E, NS + 'name').text = 'E. Interesting Sites (45)'
n_e = 0
for f in orig.iter(NS + 'Folder'):
    nm_el = f.find(NS + 'name')
    if nm_el is not None and (nm_el.text or '').strip() == 'Interesting Sites':
        for pm in f.findall(NS + 'Placemark'):
            E.append(pm)
            n_e += 1
        break
print(f'Interesting Sites promoted: {n_e}')

OUT = COMBINED
data = ET.tostring(root, encoding='utf-8', xml_declaration=True)
try:
    zf = zipfile.ZipFile(OUT, 'w', zipfile.ZIP_DEFLATED)
except PermissionError:
    OUT = OUT.replace('.kmz', '_v2.kmz')
    zf = zipfile.ZipFile(OUT, 'w', zipfile.ZIP_DEFLATED)
with zf as z2:
    z2.writestr('doc.kml', data)
print(f'\nwrote {OUT}  ({os.path.getsize(OUT)/1024:.0f} KB)')
t = zipfile.ZipFile(OUT).read('doc.kml').decode('utf-8')
ET.fromstring(t)
print(f'  XML OK | folders={t.count("<Folder")} | placemarks={t.count("<Placemark")}')
