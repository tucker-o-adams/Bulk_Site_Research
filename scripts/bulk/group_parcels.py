# -*- coding: utf-8 -*-
"""Group an owner's parcel KMZ into sites (2026-10-07). A site is a set of parcels that touch or
lie within --gap metres of each other (default 50 m, Tucker 2026-10-07: a road or rail right-of-way between two parcels of the same
operation). Owner names and parcel types are NOT used to group: one operation's parcels carry the names of the
companies that bought them over the years, and a cement plant's quarry may be filed as aggregates.

    .venv_fema/Scripts/python.exe scripts/bulk/group_parcels.py <parcels.kmz> <batch>/input/ [--gap 50]

Reads Placemarks with ExtendedData (TYPE, STATE_PROVINCE, OWNER_NAME, PROPERTY_NAME, PID_PIN_APN, GIS_AREA_ACRES)
and Polygon / MultiGeometry outlines. Writes to the output folder:

    parcels_grouped.csv   one row per parcel, with its site_id
    sites_grouped.csv     one row per site: state, types, parcel count, acres, a pin inside the largest piece
    sites_grouped.kmz     site outlines in state folders (parcel outlines inside each site, off)
    group_parcels.json    counts, the gap used, and the site count at other gaps for comparison

Acres are measured on the merged outline in CONUS Albers (EPSG:5070), so a parcel listed twice or two overlapping
parcels are counted once. listed_acres is the sum of the file's own GIS_AREA_ACRES, for comparison.
"""
import argparse, html, json, os, zipfile
import xml.etree.ElementTree as ET
import geopandas as gpd
import pandas as pd
from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import unary_union
from shapely.validation import make_valid

K = '{http://www.opengis.net/kml/2.2}'
SQM_PER_ACRE = 4046.8564
COMPARE_GAPS = [0, 30, 50, 100, 250]
ABBR = {'ALABAMA': 'AL', 'ARIZONA': 'AZ', 'ARKANSAS': 'AR', 'CALIFORNIA': 'CA', 'COLORADO': 'CO', 'CONNECTICUT': 'CT',
        'DELAWARE': 'DE', 'FLORIDA': 'FL', 'GEORGIA': 'GA', 'IDAHO': 'ID', 'ILLINOIS': 'IL', 'INDIANA': 'IN', 'IOWA': 'IA',
        'KANSAS': 'KS', 'KENTUCKY': 'KY', 'LOUISIANA': 'LA', 'MAINE': 'ME', 'MARYLAND': 'MD', 'MASSACHUSETTS': 'MA',
        'MICHIGAN': 'MI', 'MINNESOTA': 'MN', 'MISSISSIPPI': 'MS', 'MISSOURI': 'MO', 'MONTANA': 'MT', 'NEBRASKA': 'NE',
        'NEVADA': 'NV', 'NEW HAMPSHIRE': 'NH', 'NEW JERSEY': 'NJ', 'NEW MEXICO': 'NM', 'NEW YORK': 'NY',
        'NORTH CAROLINA': 'NC', 'NORTH DAKOTA': 'ND', 'OHIO': 'OH', 'OKLAHOMA': 'OK', 'OREGON': 'OR',
        'PENNSYLVANIA': 'PA', 'RHODE ISLAND': 'RI', 'SOUTH CAROLINA': 'SC', 'SOUTH DAKOTA': 'SD', 'TENNESSEE': 'TN',
        'TEXAS': 'TX', 'UTAH': 'UT', 'VERMONT': 'VT', 'VIRGINIA': 'VA', 'WASHINGTON': 'WA', 'WASHINGTON DC': 'DC',
        'WEST VIRGINIA': 'WV', 'WISCONSIN': 'WI', 'WYOMING': 'WY'}
TYPE_COLOR = {'Cement': 'ff4d50c0', 'Aggregates & Materials': 'ffbd814f', 'Building Envelope': 'ff4696f7', 'Mixed': 'ff00ffff'}


def read_kmz(path):
    z = zipfile.ZipFile(path)
    root = ET.fromstring(z.read(next(n for n in z.namelist() if n.endswith('.kml'))))

    def ring(e):
        return [tuple(map(float, c.split(',')[:2])) for c in e.findtext(f'{K}LinearRing/{K}coordinates').split()]

    rows, geoms = [], []
    for pm in root.iter(K + 'Placemark'):
        rows.append({d.get('name'): (d.findtext(K + 'value') or '').strip() for d in pm.iter(K + 'Data')})
        polys = [Polygon(ring(p.find(K + 'outerBoundaryIs')), [ring(h) for h in p.findall(K + 'innerBoundaryIs')])
                 for p in pm.iter(K + 'Polygon')]
        geoms.append(make_valid(MultiPolygon(polys)))
    g = gpd.GeoDataFrame(rows, geometry=geoms, crs=4326)
    g['listed_acres'] = pd.to_numeric(g.get('GIS_AREA_ACRES'), errors='coerce')
    return g


def label(g, gap):
    """Connected components of 'within gap metres'. g is in a metric CRS. Returns a component number per row."""
    # only one side is buffered, so by the full gap (+0.5 m: shared edges digitized a hair apart still touch)
    near = gpd.sjoin(g[['geometry']], g[['geometry']].set_geometry(g.buffer(gap + 0.5)), predicate='intersects')
    parent = list(range(len(g)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for a, b in zip(near.index, near.index_right):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    return pd.Series([find(i) for i in range(len(g))], index=g.index)


def join(values, limit=None):
    seen = list(dict.fromkeys(v for v in values if v))
    if limit and len(seen) > limit:
        return '; '.join(seen[:limit]) + f'; +{len(seen) - limit} more'
    return '; '.join(seen)


def sites_from(g, comp):
    rows = []
    for _, p in g.groupby(comp):
        shape = unary_union(list(p.geometry))
        pieces = list(getattr(shape, 'geoms', [shape]))
        pin = gpd.GeoSeries([max(pieces, key=lambda x: x.area).representative_point()], crs=5070).to_crs(4326).iloc[0]
        by_state = p.assign(a=p.area).groupby('STATE_PROVINCE').a.sum().sort_values(ascending=False)
        types = sorted(set(p.TYPE))
        rows.append({'state': ABBR.get(by_state.index[0], by_state.index[0]),
                     'other_states': join(ABBR.get(s, s) for s in by_state.index[1:]),
                     'type': types[0] if len(types) == 1 else 'Mixed', 'types': join(types),
                     'parcels': len(p), 'acres': round(shape.area / SQM_PER_ACRE, 1),
                     'listed_acres': round(p.listed_acres.sum(), 1),
                     'largest_parcel_acres': round(p.area.max() / SQM_PER_ACRE, 1), 'pieces': len(pieces),
                     'span_km': round(max(shape.bounds[2] - shape.bounds[0], shape.bounds[3] - shape.bounds[1]) / 1000, 2),
                     'lat': round(pin.y, 6), 'lng': round(pin.x, 6),
                     'property_names': join(p.PROPERTY_NAME), 'owner_names': join(p.OWNER_NAME, 5),
                     'apns': join(p.PID_PIN_APN, 10), '_rows': list(p.index), '_shape': shape})
    s = pd.DataFrame(rows).sort_values(['state', 'acres'], ascending=[True, False]).reset_index(drop=True)
    s.insert(0, 'site_id', [f'{st}-{i + 1:03d}' for st, i in zip(s.state, s.groupby('state').cumcount())])
    return s


def write_kmz(path, title, sites, g84):
    def coords(poly):
        return ' '.join(f'{x:.7f},{y:.7f},0' for x, y in poly.exterior.coords), \
               [' '.join(f'{x:.7f},{y:.7f},0' for x, y in r.coords) for r in poly.interiors]

    def polys_xml(shape):
        out = []
        for poly in getattr(shape, 'geoms', [shape]):
            if poly.geom_type != 'Polygon':
                continue
            outer, holes = coords(poly)
            out.append('<Polygon><outerBoundaryIs><LinearRing><coordinates>' + outer + '</coordinates></LinearRing></outerBoundaryIs>'
                       + ''.join(f'<innerBoundaryIs><LinearRing><coordinates>{h}</coordinates></LinearRing></innerBoundaryIs>' for h in holes)
                       + '</Polygon>')
        return '<MultiGeometry>' + ''.join(out) + '</MultiGeometry>'

    def table(pairs):
        return '<![CDATA[<table border="1" cellpadding="2" style="border-collapse:collapse;font-size:11px">' + ''.join(
            f'<tr><td><b>{html.escape(k)}</b></td><td>{html.escape(str(v))}</td></tr>' for k, v in pairs) + '</table>]]>'

    styles = ''.join(f'<Style id="{t.split()[0]}"><LineStyle><color>{c}</color><width>2</width></LineStyle>'
                     f'<PolyStyle><color>40{c[2:]}</color></PolyStyle></Style>' for t, c in TYPE_COLOR.items())
    styles += '<Style id="parcel"><LineStyle><color>ffffffff</color><width>1</width></LineStyle><PolyStyle><fill>0</fill></PolyStyle></Style>'
    parts = [f'<?xml version="1.0" encoding="UTF-8"?><kml xmlns="{K[1:-1]}"><Document><name>{html.escape(title)}</name>{styles}']
    for st, ss in sites.groupby('state'):
        parts.append(f'<Folder><name>{st} ({len(ss)} sites)</name>')
        for _, s in ss.iterrows():
            shape84 = gpd.GeoSeries([s._shape], crs=5070).to_crs(4326).iloc[0]
            info = [('Site', s.site_id), ('Type', s.types), ('Parcels', s.parcels), ('Acres (merged outline)', s.acres),
                    ('Acres (listed, summed)', s.listed_acres), ('Separate pieces', s.pieces), ('Property names', s.property_names),
                    ('Owner names', s.owner_names), ('Parcel IDs', s.apns), ('Pin', f'{s.lat}, {s.lng}')]
            parts.append(f'<Folder><name>{s.site_id} · {s.acres:,.0f} ac · {s.parcels} parcels</name>'
                         f'<Placemark><name>{s.site_id}</name><description>{table(info)}</description>'
                         f'<styleUrl>#{s.type.split()[0]}</styleUrl>{polys_xml(shape84)}</Placemark>'
                         '<Folder><name>Parcels</name><visibility>0</visibility>')
            for i in s._rows:
                r = g84.loc[i]
                parts.append(f'<Placemark><name>{html.escape(r.PID_PIN_APN or r.OWNER_NAME)}</name><visibility>0</visibility>'
                             f'<description>{table([("Owner", r.OWNER_NAME), ("Type", r.TYPE), ("Parcel ID", r.PID_PIN_APN), ("Listed acres", r.listed_acres)])}</description>'
                             f'<styleUrl>#parcel</styleUrl>{polys_xml(r.geometry)}</Placemark>')
            parts.append('</Folder></Folder>')
        parts.append('</Folder>')
    parts.append('</Document></kml>')
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('doc.kml', ''.join(parts))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('kmz')
    ap.add_argument('out')
    ap.add_argument('--gap', type=float, default=50)
    ap.add_argument('--title', default='Parcels grouped into sites')
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    g84 = read_kmz(a.kmz)
    g = g84.to_crs(5070)
    compare = {str(x): int(label(g, x).nunique()) for x in COMPARE_GAPS}
    sites = sites_from(g, label(g, a.gap))

    site_of = {i: sid for sid, rows in zip(sites.site_id, sites._rows) for i in rows}
    parcels = g84.drop(columns='geometry').assign(site_id=[site_of[i] for i in g84.index],
                                                  measured_acres=(g.area / SQM_PER_ACRE).round(2))
    parcels.to_csv(os.path.join(a.out, 'parcels_grouped.csv'), index=False)
    sites.drop(columns=['_rows', '_shape']).to_csv(os.path.join(a.out, 'sites_grouped.csv'), index=False)
    write_kmz(os.path.join(a.out, 'sites_grouped.kmz'), a.title, sites, g84)

    summary = {'source': os.path.basename(a.kmz), 'gap_m': a.gap, 'parcels': len(g84), 'sites': len(sites),
               'sites_at_other_gaps': compare, 'acres_merged': round(sites.acres.sum()),
               'acres_listed': round(g84.listed_acres.sum()), 'mixed_type_sites': int((sites.type == 'Mixed').sum()),
               'multi_state_sites': int((sites.other_states != '').sum())}
    json.dump(summary, open(os.path.join(a.out, 'group_parcels.json'), 'w'), indent=2)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
