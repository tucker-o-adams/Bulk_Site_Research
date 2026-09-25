# -*- coding: utf-8 -*-
"""Turn the location clues read from a broker list into a point, a precision tier and a radius per site.

    .venv_fema/Scripts/python.exe scripts/bulk/locate.py Outputs/<batch>/input/ [--state TX]

Reads site_list.csv and clues_checked.csv (extract_check.py output: clues that passed the verbatim-quote
check) and writes sites_in.csv, the run.py input, plus locate.json with every candidate tried.

Tiers (design_incomplete_inputs.md, Part 1). The site gets the best tier among candidates that land in the
county the broker states; each candidate also reports whether it lands in the stated ZIP.

    L1 parcel   APN found in a registered county parcel service that accepts attribute queries
    L2 point    broker coordinate (100 m; 'approx' 500 m) or a Census-geocoded street address (100 m)
    L3 anchor   existing substation named by the broker, found by name in HIFLD (2 km); a road intersection
                computed from Census TIGER road lines within the stated ZIP (2 km); a landmark found in
                OpenStreetMap Nominatim (2 km). An anchor may sit just over a county line: it passes when it is
                in the stated county or within its radius of it
    L4 area     ZIP (ZCTA) centroid, radius from its area
    L5 county   county centroid, radius from its area

run.py then runs only the producers the tier supports (tiers.py); the rest are `not_assessable`.
Planned substations (not in the 2021 HIFLD layer), owner / tract names and corridors are recorded as
unresolved clues for the memo's verification list - never guessed into a point.
"""
import argparse, csv, json, math, os, re, sys, time, urllib.parse
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from cache import Cache                     # noqa: E402
from geom import arcgis_query, point_dist_m, polygon_dist_m  # noqa: E402
from shapely.geometry import LineString  # noqa: E402
from shapely.ops import unary_union  # noqa: E402
import registry                             # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
SUBS = 'https://services5.arcgis.com/HDRa0B57OVrv2E1q/ArcGIS/rest/services/Electric_Substations/FeatureServer/0'
ZCTA = 'https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/PUMA_TAD_TAZ_UGA_ZCTA/MapServer/1'
COUNTY = 'https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/State_County/MapServer/1'
GEOCODER = 'https://geocoding.geo.census.gov/geocoder/locations/onelineaddress'
NOMINATIM = 'https://nominatim.openstreetmap.org/search'
ROADS = 'https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Transportation/MapServer'
ROAD_LAYERS = (2, 6, 8)       # primary, secondary, local
NAME = 'locate'
FIPS = {'AL': '01', 'AK': '02', 'AZ': '04', 'AR': '05', 'CA': '06', 'CO': '08', 'CT': '09', 'DE': '10', 'DC': '11', 'FL': '12', 'GA': '13',
        'HI': '15', 'ID': '16', 'IL': '17', 'IN': '18', 'IA': '19', 'KS': '20', 'KY': '21', 'LA': '22', 'ME': '23', 'MD': '24', 'MA': '25',
        'MI': '26', 'MN': '27', 'MS': '28', 'MO': '29', 'MT': '30', 'NE': '31', 'NV': '32', 'NH': '33', 'NJ': '34', 'NM': '35', 'NY': '36',
        'NC': '37', 'ND': '38', 'OH': '39', 'OK': '40', 'OR': '41', 'PA': '42', 'RI': '44', 'SC': '45', 'SD': '46', 'TN': '47', 'TX': '48',
        'UT': '49', 'VT': '50', 'VA': '51', 'WA': '53', 'WV': '54', 'WI': '55', 'WY': '56'}
TIER_ORDER = ['L1', 'L2', 'L3', 'L4', 'L5']
RADIUS = {'coordinate': 100, 'coordinate_approx': 500, 'street_address': 100, 'substation_name': 2000, 'intersection': 2000, 'landmark': 2000}
SITES_IN_COLUMNS = ['site_id', 'name', 'lat', 'lng', 'state', 'county', 'acres_stated', 'market', 'notes',
                    'location_tier', 'location_basis', 'location_radius_m', 'location_check', 'location_other', 'location_unresolved']


def q(text):
    return re.sub(r'[^a-z0-9]+', '_', text.lower()).strip('_')[:80]


def centroid(rings):
    pts = [p for r in rings for p in r]
    return sum(p[1] for p in pts) / len(pts), sum(p[0] for p in pts) / len(pts)


def ring_area_km2(rings, lat):
    k = math.cos(math.radians(lat))
    tot = 0.0
    for r in rings[:1]:
        tot += abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(r, r[1:]))) / 2
    return tot * 111.32 * 110.54 * k


class Resolver:
    def __init__(self, cache, state):
        self.c, self.state, self.sfips = cache, state, FIPS.get(state, '')

    def get(self, key, url):
        resp, _, err = self.c.get_json(NAME, key, url)
        return resp, err

    # ---- area polygons
    def county(self, name):
        where = f"STATE='{self.sfips}' AND UPPER(NAME)='{name.upper()} COUNTY'"
        r, err = self.get(f'county_{self.state}_{q(name)}', f'{COUNTY}/query?f=json&outFields=GEOID,NAME&returnGeometry=true&outSR=4326&where={urllib.parse.quote(where)}')
        fs = (r or {}).get('features') or []
        if not fs:
            return None
        rings = fs[0]['geometry']['rings']; la, ln = centroid(rings)
        return {'geoid': fs[0]['attributes']['GEOID'], 'lat': la, 'lng': ln, 'rings': rings,
                'radius_m': round(1000 * math.sqrt(ring_area_km2(rings, la) / math.pi))}

    def zcta(self, z):
        r, err = self.get(f'zcta_{z}', f"{ZCTA}/query?f=json&outFields=ZCTA5&returnGeometry=true&outSR=4326&where={urllib.parse.quote(f'ZCTA5={chr(39)}{z}{chr(39)}')}")
        fs = (r or {}).get('features') or []
        if not fs:
            return None
        rings = fs[0]['geometry']['rings']; la, ln = centroid(rings)
        xs = [p[0] for r in rings for p in r]; ys = [p[1] for r in rings for p in r]
        return {'lat': la, 'lng': ln, 'bbox': (min(xs), min(ys), max(xs), max(ys)), 'rings': rings,
                'radius_m': round(1000 * math.sqrt(ring_area_km2(rings, la) / math.pi))}

    def county_at(self, la, ln):
        r, _ = self.get(f'countyat_{la:.5f}_{ln:.5f}', arcgis_query(COUNTY, la, ln, 'GEOID,NAME'))
        fs = (r or {}).get('features') or []
        return fs[0]['attributes']['NAME'].replace(' County', '') if fs else None

    def zip_at(self, la, ln):
        r, _ = self.get(f'zipat_{la:.5f}_{ln:.5f}', arcgis_query(ZCTA, la, ln, 'ZCTA5'))
        fs = (r or {}).get('features') or []
        return fs[0]['attributes']['ZCTA5'] if fs else None

    # ---- point clues
    def substation(self, name):
        where = f"STATE='{self.state}' AND UPPER(NAME) LIKE '%{name.upper().replace(chr(39), '')}%'"
        r, err = self.get(f'sub_{self.state}_{q(name)}', f"{SUBS}/query?f=json&outFields=NAME,COUNTY,MAX_VOLT,STATUS,TYPE&returnGeometry=true&outSR=4326&where={urllib.parse.quote(where)}")
        if err:
            return [], err
        return [{'lat': f['geometry']['y'], 'lng': f['geometry']['x'], 'label': f"HIFLD substation {f['attributes']['NAME']} ({f['attributes'].get('MAX_VOLT')} kV, {f['attributes'].get('STATUS')})",
                 'county_attr': (f['attributes'].get('COUNTY') or '').title()} for f in (r or {}).get('features') or []], None

    def address(self, text):
        u = f"{GEOCODER}?address={urllib.parse.quote(text)}&benchmark=Public_AR_Current&format=json"
        r, err = self.get(f'addr_{q(text)}', u)
        ms = ((r or {}).get('result') or {}).get('addressMatches') or []
        return [{'lat': m['coordinates']['y'], 'lng': m['coordinates']['x'], 'label': f"Census geocoder: {m['matchedAddress']}"} for m in ms[:3]], err

    def nominatim(self, text):
        u = f"{NOMINATIM}?q={urllib.parse.quote(text)}&format=json&limit=3&countrycodes=us"
        cached = os.path.exists(self.c.path(NAME, f'osm_{q(text)}'))
        r, err = self.get(f'osm_{q(text)}', u)
        if not cached:
            time.sleep(1.1)                 # Nominatim usage policy: at most 1 request a second
        return [{'lat': float(m['lat']), 'lng': float(m['lon']), 'label': 'OpenStreetMap: ' + ', '.join(m.get('display_name', '').split(', ')[:2])}
                for m in (r or [])], err

    def intersection(self, text, bbox):
        """'Main St & 2nd St, Town, ST' -> where the two named TIGER road lines cross inside bbox."""
        m = re.match(r'\s*(.+?)\s*(?:&|\band\b|/|@)\s*(.+?)\s*(?:,|$)', text)
        if not m or not bbox:
            return [], 'intersection text not "A & B, City" or no ZIP area to search in'
        env = ','.join(f'{v:.5f}' for v in bbox)
        lines = []
        for road in (m.group(1), m.group(2)):
            geoms = []
            for lid in ROAD_LAYERS:
                where = "UPPER(NAME)='" + road.upper().replace("'", '') + "'"
                u = (f"{ROADS}/{lid}/query?f=json&outFields=NAME&returnGeometry=true&outSR=4326&inSR=4326&geometryType=esriGeometryEnvelope"
                     f"&spatialRel=esriSpatialRelIntersects&geometry={env}&where={urllib.parse.quote(where)}")
                r, err = self.get(f'road_{lid}_{q(road)}_{q(env)}', u)
                if err:
                    return [], err
                geoms += [LineString(p) for f in (r or {}).get('features') or [] for p in f['geometry']['paths'] if len(p) > 1]
            if not geoms:
                return [], f'no TIGER road named {road!r} in the ZIP area'
            lines.append(unary_union(geoms))
        x = lines[0].intersection(lines[1])
        pts = [g for g in getattr(x, 'geoms', [x]) if not g.is_empty]
        if not pts:
            return [], f'{m.group(1)!r} and {m.group(2)!r} do not cross in the ZIP area'
        cx = unary_union(pts).centroid
        spread = max(point_dist_m(cx.x, cx.y, g.centroid.x, g.centroid.y) for g in pts)
        if spread > 500:
            return [], f'{m.group(1)!r} and {m.group(2)!r} cross at {len(pts)} places up to {spread:,.0f} m apart - ambiguous'
        return [{'lat': cx.y, 'lng': cx.x, 'label': f'TIGER roads: {m.group(1)} x {m.group(2)}'}], None

    def apn(self, apn, county_geoid):
        svc, scope, _ = registry.for_county(county_geoid, self.sfips)
        if not svc or svc.get('protocol', 'query') != 'query' or not registry.field(svc, 'apn'):
            return [], f"no registered parcel service for county {county_geoid} that accepts attribute queries"
        where = f"{registry.field(svc, 'apn')}='{apn}'"
        r, err = self.get(f'apn_{county_geoid}_{q(apn)}', f"{svc['base']}/{svc['layer']}/query?f=json&outFields=*&returnGeometry=true&outSR=4326&where={urllib.parse.quote(where)}")
        out = []
        for f in (r or {}).get('features') or []:
            la, ln = centroid(f['geometry']['rings'])
            out.append({'lat': la, 'lng': ln, 'label': f"{svc.get('name')} APN {apn}"})
        return out, err


def locate_site(site, clues, R):
    by = defaultdict(list)
    for c in clues:
        by[c['clue_type']].append(c)
    county = by['county'][0]['value'] if by['county'] else ''
    zip_ = by['zip'][0]['value'] if by['zip'] else ''
    cty = R.county(county) if county else None
    cands, unresolved, log = [], [], []

    def add(tier, clue, pt, radius, basis):
        cands.append({'tier': tier, 'clue': clue['clue_type'], 'lat': round(pt['lat'], 6), 'lng': round(pt['lng'], 6), 'radius_m': radius,
                      'basis': basis, 'quote': clue['quote'], 'source_cell': clue['source_cell']})

    for c in by['apn']:
        pts, err = R.apn(c['value'], cty['geoid']) if cty else ([], 'no county to look the APN up in')
        add('L1', c, pts[0], 50, pts[0]['label']) if len(pts) == 1 else unresolved.append(f"APN {c['value']}: {err or f'{len(pts)} matches'}")
    for c in by['coordinate'] + by['coordinate_approx']:
        la, ln = (float(x) for x in c['value'].split(','))
        add('L2', c, {'lat': la, 'lng': ln}, RADIUS[c['clue_type']], 'broker coordinate' + (' (approximate)' if c['clue_type'] == 'coordinate_approx' else ''))
    for c in by['street_address']:
        pts, err = R.address(c['value'])
        add('L2', c, pts[0], RADIUS['street_address'], pts[0]['label']) if pts else unresolved.append(f"address {c['value']!r}: {err or 'no Census match'}")
    for c in by['substation_name']:
        pts, err = R.substation(c['value'])
        inc = [p for p in pts if county and p['county_attr'].lower() == county.lower()]
        use = inc or pts
        if len(use) == 1 or (len(inc) >= 1 and len(set((round(p['lat'], 3), round(p['lng'], 3)) for p in inc)) == 1):
            add('L3', c, use[0], RADIUS['substation_name'], use[0]['label'])
        elif use:
            unresolved.append(f"substation {c['value']!r}: {len(use)} HIFLD matches{' in ' + county + ' County' if inc else ''} - ambiguous: " +
                              '; '.join(p['label'] for p in use[:4]))
        else:
            unresolved.append(f"substation {c['value']!r}: {err or 'no HIFLD match in ' + R.state}")
    z = R.zcta(zip_) if zip_ else None
    for c in by['intersection']:
        pts, err = R.intersection(c['value'], z['bbox'] if z else None)
        add('L3', c, pts[0], RADIUS['intersection'], pts[0]['label']) if pts else unresolved.append(f"intersection {c['value']!r}: {err}")
    for c in by['landmark']:
        pts, err = R.nominatim(c['value'])
        add('L3', c, pts[0], RADIUS[c['clue_type']], pts[0]['label']) if pts else unresolved.append(f"{c['clue_type']} {c['value']!r}: {err or 'no OpenStreetMap match'}")
    for c in by['substation_planned']:
        unresolved.append(f"planned substation {c['value']!r}: not in HIFLD (2021); location unknown")
    for c in by['owner_name']:
        unresolved.append(f"owner/tract name {c['value']!r}: search the county parcel records by hand (candidate list, not an answer)")
    for c in by['corridor'] + by['area_name']:
        unresolved.append(f"{c['clue_type'].replace('_', ' ')} {c['value']!r}: context only")
    if zip_:
        if z:
            add('L4', by['zip'][0], z, z['radius_m'], f'ZIP {zip_} (ZCTA centroid)')
    if cty:
        add('L5', by['county'][0], cty, cty['radius_m'], f'{county} County centroid')

    # cross-check each candidate against the stated county and ZIP
    for k in cands:
        if k['tier'] in ('L4', 'L5'):
            k['check'] = 'area centroid'; k['ok'] = True; continue
        got_c = R.county_at(k['lat'], k['lng'])
        got_z = R.zip_at(k['lat'], k['lng'])
        same = not county or (got_c or '').lower() == county.lower()
        near = (not same and k['tier'] == 'L3' and cty is not None
                and polygon_dist_m([[tuple(p) for p in r] for r in cty['rings']], k['lng'], k['lat']) <= k['radius_m'])
        k['ok'] = same or near
        parts = [f"in {got_c} County" + ('' if same else f", within {k['radius_m']:,} m of {county} County" if near else f' - NOT the stated {county} County')]
        if zip_:
            parts.append('in stated ZIP' if got_z == zip_ else f'ZIP {got_z}, not the stated {zip_}')
        k['check'] = '; '.join(parts)
    ok = [k for k in cands if k['ok']]
    best = min(ok, key=lambda k: TIER_ORDER.index(k['tier'])) if ok else None
    for k in cands:
        if not k['ok']:
            unresolved.append(f"{k['clue']} {k['basis']!r} rejected: {k['check']}")
    other = []
    if best:
        for k in ok:
            if k is not best and k['tier'] in ('L1', 'L2', 'L3'):
                d = point_dist_m(best['lng'], best['lat'], k['lng'], k['lat'])
                other.append(f"{k['basis']} is {d:,.0f} m away")
    acres = next((c['value'] for c in by['acreage']), '')
    notes = [] if best else ['no location clue resolved']
    return best, cands, unresolved, other, acres, notes, county


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('input_dir')
    ap.add_argument('--state', default='', help='default state when a site has no state clue (the column map default_state)')
    a = ap.parse_args()
    d = a.input_dir
    rd = lambda n: list(csv.DictReader(open(os.path.join(d, n), encoding='utf-8-sig')))
    chk = json.load(open(os.path.join(d, 'extract_check.json'), encoding='utf-8'))
    if not chk.get('ok'):
        raise SystemExit('extract_check.py has not passed for this batch; fix the extraction first')
    sites, clues = rd('site_list.csv'), rd('clues_checked.csv')
    by_site = defaultdict(list)
    for c in clues:
        by_site[c['site_id']].append(c)
    cache = Cache(os.path.join(ROOT, 'data', 'cache'))
    out, log = [], {}
    tiers = defaultdict(int)
    for s in sites:
        cl = by_site[s['site_id']]
        st = next((c['value'] for c in cl if c['clue_type'] == 'state'), a.state).upper()
        R = Resolver(cache, st)
        best, cands, unresolved, other, acres, notes, county = locate_site(s, cl, R)
        tier = best['tier'] if best else ''
        tiers[tier or 'none'] += 1
        out.append({'site_id': s['site_id'], 'name': s['name'], 'lat': best['lat'] if best else '', 'lng': best['lng'] if best else '',
                    'state': st, 'county': county, 'acres_stated': acres, 'market': s['section'], 'notes': '; '.join(notes),
                    'location_tier': tier, 'location_basis': best['basis'] if best else '', 'location_radius_m': best['radius_m'] if best else '',
                    'location_check': best['check'] if best else '', 'location_other': ' | '.join(other), 'location_unresolved': ' | '.join(unresolved)})
        log[s['site_id']] = {'chosen': best, 'candidates': cands, 'unresolved': unresolved}
        print(f"  {s['site_id']:8s} {tier or '--':3s} {(best or {}).get('basis', 'no location')[:70]:70s} {(best or {}).get('check', '')}")
    with open(os.path.join(d, 'sites_in.csv'), 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=SITES_IN_COLUMNS); w.writeheader(); w.writerows(out)
    json.dump({'tiers': dict(tiers), 'sites': log}, open(os.path.join(d, 'locate.json'), 'w', encoding='utf-8'), indent=1)
    print(f"{len(out)} sites -> sites_in.csv | tiers {dict(sorted(tiers.items()))} | cache hits {cache.hits} / misses {cache.misses}")


if __name__ == '__main__':
    main()
