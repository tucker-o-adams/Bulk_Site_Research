# -*- coding: utf-8 -*-
"""Schools near the site, from NCES EDGE school-location services.

Public schools: Common Core of Data, 2024-25 (102,178 points).
Private schools: Private School Universe Survey, 2023-24 (22,510 points).
NCES geocodes each school's physical address; points are annual and
authoritative for K-12. Colleges are not included.
"""
from cache import coord_key
from geom import arcgis_query
from provenance import Value, absent, failed, now_iso
from producers.pointsets import score_points, counts

NAME = 'schools'
PUB = 'https://nces.ed.gov/opengis/rest/services/K12_School_Locations/EDGE_GEOCODE_PUBLICSCH_2425/MapServer/0'
PRV = 'https://nces.ed.gov/opengis/rest/services/K12_School_Locations/EDGE_GEOCODE_PRIVATESCH_2324/MapServer/0'
LYR = PUB
SOURCE = 'NCES EDGE school locations (public 2024-25, private 2023-24)'
VINTAGE = '2024-25 public / 2023-24 private'
SEARCH_M = 5000
METHOD = (f'NCES public and private school points within {SEARCH_M} m; straight-line distance; '
          'nearest of either type; counts within 0.5 mi and 1 mi')
NOTE = 'K-12 only (no colleges); NCES-geocoded physical addresses'

FIELDS = ['school_nearest_m', 'school_nearest_name', 'school_nearest_type', 'school_nearest_city',
          'schools_within_0_5mi', 'schools_within_1mi', 'public_schools_within_1mi', 'private_schools_within_1mi']


def run(site, cache):
    la, ln = site.lat, site.lng
    pub, f1, e1 = cache.get_json(NAME, coord_key(la, ln, f'pub{SEARCH_M}'),
                                 arcgis_query(PUB, la, ln, 'NAME,CITY,STATE', distance_m=SEARCH_M, geometry=True, fmt='geojson'))
    prv, f2, e2 = cache.get_json(NAME, coord_key(la, ln, f'prv{SEARCH_M}'),
                                 arcgis_query(PRV, la, ln, 'NAME,CITY,STATE', distance_m=SEARCH_M, geometry=True, fmt='geojson'))
    fetched = f1 or f2 or now_iso()
    if e1 and e2:
        return [failed(f, SOURCE, LYR, METHOD, f'public: {e1}; private: {e2}') for f in FIELDS]
    note = NOTE + ('; private-school service failed this run' if e2 else '; public-school service failed this run' if e1 else '')

    def mk(fld, val):
        return Value(fld, val, SOURCE, LYR, METHOD, vintage=VINTAGE, fetched_at=fetched, note=note)

    scored = []
    if not e1:
        scored += [(d, p, n, 'public') for d, p, n in score_points((pub or {}).get('features') or [], la, ln, lambda p: p.get('NAME'))]
    if not e2:
        scored += [(d, p, n, 'private') for d, p, n in score_points((prv or {}).get('features') or [], la, ln, lambda p: p.get('NAME'))]
    scored.sort(key=lambda s: s[0])
    if not scored:
        out = [absent(f, SOURCE, LYR, METHOD, note=f'no school within {SEARCH_M} m', vintage=VINTAGE) for f in FIELDS[:4]]
        return out + [mk(f, 0) for f in FIELDS[4:]]
    d, p, n, t = scored[0]
    c5, c1 = counts(scored)
    return [mk('school_nearest_m', round(d)), mk('school_nearest_name', n), mk('school_nearest_type', t),
            mk('school_nearest_city', p.get('CITY')), mk('schools_within_0_5mi', c5), mk('schools_within_1mi', c1),
            mk('public_schools_within_1mi', sum(1 for s in scored if s[3] == 'public' and s[0] <= 1609.344)),
            mk('private_schools_within_1mi', sum(1 for s in scored if s[3] == 'private' and s[0] <= 1609.344))]
