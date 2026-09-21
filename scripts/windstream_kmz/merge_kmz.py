# -*- coding: utf-8 -*-
"""Merge the original WS KMZ + the transmission KMZ + parcel results into one KMZ."""
import csv, html, os, re, zipfile
import xml.etree.ElementTree as ET

K = 'http://www.opengis.net/kml/2.2'
ET.register_namespace('', K)
NS = '{%s}' % K

BASE = r'C:\Users\tucke\OneDrive\Documents\Claude\Projects\TBDI Modeling\Mireye'
SRC_ORIG = r'C:\Users\tucke\Downloads\WS Targeted Sites Overview 26.8.20.kmz'
SRC_TX = os.path.join(BASE, 'WS_Sites_and_Transmission.kmz')
PARCEL = os.path.join(BASE, 'WS_Sites_Parcel_Sizes_FINAL.csv')
OUT = os.path.join(BASE, 'TBDI_WS_Combined.kmz')


def read_kml(path):
    z = zipfile.ZipFile(path)
    name = next(n for n in z.namelist() if n.lower().endswith('.kml'))
    return ET.fromstring(z.read(name).decode('utf-8', 'replace'))


def esc(v):
    return html.escape('' if v is None else str(v))


# ---------- start a new document ----------
doc = ET.Element(NS + 'kml')
d = ET.SubElement(doc, NS + 'Document')
ET.SubElement(d, NS + 'name').text = 'TBDI Windstream — Combined'
ET.SubElement(d, NS + 'description').text = (
    'Merged: (1) original WS Targeted Sites overview incl. market distance rings and the '
    'hand-drawn Northfield 1-acre polygon; (2) 200 CO sites with nearby HIFLD transmission '
    'lines coloured by voltage; (3) county-GIS parcel results. '
    'Toggle folders in the Places panel. Site points appear in more than one folder by design.')

# ---------- carry over styles from both sources ----------
seen_styles = set()
for src in (SRC_TX, SRC_ORIG):
    root = read_kml(src)
    for tag in ('Style', 'StyleMap'):
        for st in root.iter(NS + tag):
            sid = st.get('id')
            if sid and sid not in seen_styles:
                seen_styles.add(sid)
                d.append(st)
print(f'styles carried over: {len(seen_styles)}')


def graft(src_path, folder_name, skip_folder_names=()):
    """Copy every folder from a source KML into a named wrapper folder."""
    root = read_kml(src_path)
    wrap = ET.SubElement(d, NS + 'Folder')
    ET.SubElement(wrap, NS + 'name').text = folder_name
    n_pm = 0
    for f in root.iter(NS + 'Folder'):
        nm_el = f.find(NS + 'name')
        nm = (nm_el.text or '').strip() if nm_el is not None else ''
        if nm in skip_folder_names:
            continue
        # only take folders that directly contain placemarks
        pms = f.findall(NS + 'Placemark')
        if not pms:
            continue
        sub = ET.SubElement(wrap, NS + 'Folder')
        ET.SubElement(sub, NS + 'name').text = nm or 'items'
        for pm in pms:
            sub.append(pm)
            n_pm += 1
    return n_pm


n1 = graft(SRC_TX, 'A. Sites + Transmission (HIFLD)')
print(f'transmission KMZ placemarks: {n1}')
n2 = graft(SRC_ORIG, 'B. Original WS Overview (rings, top sites, Northfield polygon)')
print(f'original KMZ placemarks: {n2}')

# ---------- parcel results as a third folder ----------
pf = ET.SubElement(d, NS + 'Folder')
ET.SubElement(pf, NS + 'name').text = 'C. Parcel results (county GIS)'
ET.SubElement(pf, NS + 'visibility').text = '0'
style = ET.SubElement(d, NS + 'Style', {'id': 'parcelPin'})
ic = ET.SubElement(ET.SubElement(style, NS + 'IconStyle'), NS + 'Icon')
ET.SubElement(ic, NS + 'href').text = 'http://maps.google.com/mapfiles/kml/shapes/square.png'

n3 = 0
if os.path.exists(PARCEL):
    for r in csv.DictReader(open(PARCEL, encoding='utf-8-sig')):
        try:
            la, ln = float(r['lat']), float(r['lng'])
        except (TypeError, ValueError):
            continue
        pm = ET.SubElement(pf, NS + 'Placemark')
        ET.SubElement(pm, NS + 'name').text = f"{r['clli']} — {r.get('acres_gis') or 'n/a'} ac"
        ET.SubElement(pm, NS + 'styleUrl').text = '#parcelPin'
        desc = (f"<b>{esc(r['clli'])}</b><br/>{esc(r.get('address'))}<br/>"
                f"{esc(r.get('county'))} Co, {esc(r.get('state'))}<br/><br/>"
                f"Parcel (GIS): <b>{esc(r.get('acres_gis'))} ac</b> "
                f"({esc(r.get('sqft_gis'))} sq ft)<br/>"
                f"County stated: {esc(r.get('acres_stated'))} "
                f"[{esc(r.get('acres_stated_field'))}]<br/>"
                f"Parcel ID: {esc(r.get('parcel_id'))}<br/>"
                f"Owner: {esc(r.get('owner'))}<br/>"
                f"Status: {esc(r.get('status'))}<br/>"
                f"<i>{esc(r.get('notes'))}</i>")
        ET.SubElement(pm, NS + 'description').text = desc
        pt = ET.SubElement(pm, NS + 'Point')
        ET.SubElement(pt, NS + 'coordinates').text = f'{ln},{la},0'
        n3 += 1
print(f'parcel placemarks: {n3}')

kml_bytes = ET.tostring(doc, encoding='utf-8', xml_declaration=True)
with zipfile.ZipFile(OUT, 'w', zipfile.ZIP_DEFLATED) as z:
    z.writestr('doc.kml', kml_bytes)

print(f'\nwrote {OUT}')
print(f'  size: {os.path.getsize(OUT)/1024:.0f} KB')
print(f'  total placemarks: {n1 + n2 + n3}')

# validate
zz = zipfile.ZipFile(OUT)
t = zz.read('doc.kml').decode('utf-8')
ET.fromstring(t)
print(f'  XML parses OK | folders: {t.count("<Folder")} | placemarks: {t.count("<Placemark")}')
