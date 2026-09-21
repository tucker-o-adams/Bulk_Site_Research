# -*- coding: utf-8 -*-
"""Inside folder F, add a sub-folder holding only the 'Interesting Sites' subset,
same per-site structure (site marker + its identified nearest line)."""
import csv, html, os, zipfile
import xml.etree.ElementTree as ET

K = 'http://www.opengis.net/kml/2.2'
ET.register_namespace('', K)
NS = '{%s}' % K
from paths import COMBINED_KMZ, TX_CSV, WS_SITES_CSV
KMZ = COMBINED_KMZ
TXCSV = TX_CSV
WSSITES = WS_SITES_CSV   # extracted from the broker KMZ by parse_kmz.py

def esc(v):
    return html.escape('' if v is None else str(v))

# ---- the 45 Interesting Sites CLLIs
interesting = []
for r in csv.DictReader(open(WSSITES, encoding='utf-8')):
    if r['folder'].strip() == 'Interesting Sites':
        interesting.append(r['name'].strip())
interesting = sorted(set(interesting))
print(f'Interesting Sites in original KMZ: {len(interesting)}')

tx = {s['CLLI']: s for s in csv.DictReader(open(TXCSV, encoding='utf-8-sig'))}

root = ET.fromstring(zipfile.ZipFile(KMZ).read('doc.kml').decode('utf-8', 'replace'))
doc = root.find(NS + 'Document')

# ---- locate folder F and harvest the already-built per-site folders
Fnode = None
for f in doc.findall(NS + 'Folder'):
    nm = f.find(NS + 'name')
    if nm is not None and (nm.text or '').startswith('F. Site-by-site'):
        Fnode = f
        break
if Fnode is None:
    raise SystemExit('folder F not found')

# map CLLI -> existing per-site folder element (nested one level under state folders)
existing = {}
for stf in Fnode.findall(NS + 'Folder'):
    for sitef in stf.findall(NS + 'Folder'):
        nm = sitef.find(NS + 'name')
        if nm is None:
            continue
        clli = (nm.text or '').split('—')[0].strip()
        existing[clli] = sitef
print(f'per-site folders available in F: {len(existing)}')

have = [c for c in interesting if c in existing]
missing = [c for c in interesting if c not in existing]
print(f'  matched: {len(have)}   no transmission data: {len(missing)} {missing}')

# ---- build the subset folder
SUB = ET.Element(NS + 'Folder')
ET.SubElement(SUB, NS + 'name').text = f'** Interesting Sites only ({len(have)}) **'
ET.SubElement(SUB, NS + 'visibility').text = '0'
ET.SubElement(SUB, NS + 'open').text = '0'
ET.SubElement(SUB, NS + 'description').text = (
    'The 45-site "Interesting Sites" subset from the original WS overview KMZ, '
    'with each site paired to its identified nearest transmission line. '
    'Same content as the state folders below, filtered to this list.')

by_state = {}
for clli in have:
    stt = (tx.get(clli) or {}).get('State') or '??'
    by_state.setdefault(stt, []).append(clli)

for stt in sorted(by_state):
    clis = sorted(by_state[stt])
    SF = ET.SubElement(SUB, NS + 'Folder')
    ET.SubElement(SF, NS + 'name').text = f'{stt} ({len(clis)})'
    ET.SubElement(SF, NS + 'open').text = '0'
    for clli in clis:
        # deep copy so the original folders stay intact
        SF.append(ET.fromstring(ET.tostring(existing[clli])))

# insert as the first sub-folder of F
kids = list(Fnode)
idx = next((i for i, ch in enumerate(kids) if ch.tag == NS + 'Folder'), len(kids))
Fnode.insert(idx, SUB)

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
print('  subset by state:', {k: len(v) for k, v in sorted(by_state.items())})
