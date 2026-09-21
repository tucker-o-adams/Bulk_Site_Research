# -*- coding: utf-8 -*-
"""Build a Google Earth KMZ: WS sites + nearby HIFLD transmission lines, styled by voltage."""
import csv, html, os, zipfile
from paths import TX_CSV, HIFLD_5KM, TX_KMZ, KMZ_OUT, load_geojson_lines

TXCSV = TX_CSV
OUT = TX_KMZ
RADIUS = 5000  # metres of line context around each site (radius used by fetch_hifld_segments.py)

# KML colours are aabbggrr (alpha, blue, green, red)
def style_for(kv):
    if kv is None:            return 'kvUnknown', '96b4b4b4', 2.0   # grey
    if kv < 100:              return 'kvSub100',  'ffb4b4b4', 2.4   # light grey
    if kv < 200:              return 'kv100',     'ff00d7ff', 3.0   # amber
    if kv < 300:              return 'kv230',     'ff0080ff', 3.4   # orange
    if kv < 400:              return 'kv345',     'ff0000ff', 4.0   # red
    return 'kv500', 'ffff00ff', 4.4                                 # magenta

STYLES = [('kvUnknown', '96b4b4b4', 2.0), ('kvSub100', 'ffb4b4b4', 2.4),
          ('kv100', 'ff00d7ff', 3.0), ('kv230', 'ff0080ff', 3.4),
          ('kv345', 'ff0000ff', 4.0), ('kv500', 'ffff00ff', 4.4)]

sites = list(csv.DictReader(open(TXCSV, encoding='utf-8-sig')))
print(f'sites: {len(sites)}')

# Segments within RADIUS of any site, frozen from the HIFLD source by fetch_hifld_segments.py
lines = load_geojson_lines(HIFLD_5KM)   # ID -> (props, [ [ (lng,lat), ... ], ... ])
print(f'unique transmission segments: {len(lines)}')

def esc(v):
    return html.escape('' if v is None else str(v))

def kvnum(p):
    try:
        v = float(p.get('VOLTAGE'))
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None

buf = []
buf.append('<?xml version="1.0" encoding="UTF-8"?>')
buf.append('<kml xmlns="http://www.opengis.net/kml/2.2"><Document>')
buf.append('<name>WS Sites + HIFLD Transmission</name>')
buf.append('<description><![CDATA[Windstream CO sites with nearby transmission lines. '
           'Lines from HIFLD US Electric Power Transmission Lines. '
           'Colour = voltage: grey &lt;100kV, amber 100-161kV, orange 230kV, red 345kV, magenta 500kV+. '
           'Dashed grey = voltage not published.]]></description>')

for sid, colour, width in STYLES:
    buf.append(f'<Style id="{sid}"><LineStyle><color>{colour}</color>'
               f'<width>{width}</width></LineStyle></Style>')
buf.append('<Style id="siteIcon"><IconStyle><scale>1.0</scale><color>ff00ffff</color>'
           '<Icon><href>http://maps.google.com/mapfiles/kml/shapes/placemark_circle.png</href></Icon>'
           '</IconStyle></Style>')

# --- sites folder
buf.append('<Folder><name>WS Sites (200)</name>')
for s in sites:
    try:
        la, ln = float(s['lat']), float(s['lng'])
    except (TypeError, ValueError):
        continue
    d = s.get('nearest_tx_line_m') or ''
    desc = (f"<b>{esc(s['CLLI'])}</b> ({esc(s['State'])})<br/>"
            f"Nearest line: {esc(d)} m ({esc(s.get('nearest_tx_line_ft'))} ft)<br/>"
            f"Voltage: {esc(s.get('voltage_kv'))} kV [{esc(s.get('voltage_basis'))}]<br/>"
            f"Line: {esc(s.get('line_name')) or '(unnamed)'} &nbsp;id={esc(s.get('line_id'))}<br/>"
            f"Owner: {esc(s.get('owner'))}<br/>"
            f"Nearest &ge;100kV: {esc(s.get('nearest_100kv_plus_m'))} m @ {esc(s.get('kv_100plus'))} kV")
    buf.append(f"<Placemark><name>{esc(s['CLLI'])}</name><styleUrl>#siteIcon</styleUrl>"
               f"<description><![CDATA[{desc}]]></description>"
               f"<Point><coordinates>{ln},{la},0</coordinates></Point></Placemark>")
buf.append('</Folder>')

# --- lines grouped by voltage tier
tiers = {}
for lid, (p, parts) in lines.items():
    sid, _, _ = style_for(kvnum(p))
    tiers.setdefault(sid, []).append((lid, p, parts))

TIER_LABEL = {'kv500': '500 kV +', 'kv345': '345 kV', 'kv230': '230-287 kV',
              'kv100': '100-161 kV', 'kvSub100': 'Under 100 kV', 'kvUnknown': 'Voltage not published'}
for sid in ['kv500', 'kv345', 'kv230', 'kv100', 'kvSub100', 'kvUnknown']:
    items = tiers.get(sid) or []
    if not items:
        continue
    buf.append(f'<Folder><name>Transmission - {TIER_LABEL[sid]} ({len(items)})</name>')
    for lid, p, parts in items:
        nm = ' - '.join(x for x in [(p.get('SUB_1') or '').strip(), (p.get('SUB_2') or '').strip()] if x)
        nm = nm or f"line {lid}"
        desc = (f"ID: {esc(lid)}<br/>Voltage: {esc(p.get('VOLTAGE'))} kV "
                f"({esc(p.get('VOLT_CLASS'))})<br/>Owner: {esc(p.get('OWNER'))}<br/>"
                f"Type: {esc(p.get('TYPE'))}<br/>Status: {esc(p.get('STATUS'))}<br/>"
                f"Attributes inferred: {esc(p.get('INFERRED'))}")
        buf.append(f'<Placemark><name>{esc(nm)[:60]}</name><styleUrl>#{sid}</styleUrl>'
                   f'<description><![CDATA[{desc}]]></description><MultiGeometry>')
        for part in parts:
            coords = ' '.join(f'{c[0]},{c[1]},0' for c in part)
            buf.append(f'<LineString><tessellate>1</tessellate><coordinates>{coords}</coordinates></LineString>')
        buf.append('</MultiGeometry></Placemark>')
    buf.append('</Folder>')

buf.append('</Document></kml>')
kml = '\n'.join(buf)

os.makedirs(KMZ_OUT, exist_ok=True)
with zipfile.ZipFile(OUT, 'w', zipfile.ZIP_DEFLATED) as z:
    z.writestr('doc.kml', kml)
print(f'\nwrote {OUT}')
print(f'  size: {os.path.getsize(OUT)/1024:.0f} KB')
print(f'  sites: {len(sites)} | line segments: {len(lines)}')
for sid in ['kv500','kv345','kv230','kv100','kvSub100','kvUnknown']:
    if tiers.get(sid):
        print(f'   {TIER_LABEL[sid]:24} {len(tiers[sid]):4}')
