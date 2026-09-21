# -*- coding: utf-8 -*-
"""Nearest large metro, from Census TIGERweb 2020 Urban Areas.

"Large" is a population threshold on the urban area's 2020 count (POP100):
  * >= 250,000  regional metro (Canton, Youngstown, Des Moines ...)
  * >= 1,000,000  major metro (Cleveland, Atlanta, Houston, Chicago ...)

Distance is straight-line from the site to the urban area's boundary — 0 when
the site is inside it — not to a city hall or centroid, and not driving time
(which runs 20-40 % longer on ordinary road networks). Urban areas are the
Census's built-up footprint, which is what "how far to the metro" usually
means on the ground; they are not MSAs/CBSAs (county-based, much larger).

Two TIGERweb calls: the urban area containing the point (any size), and every
urban area >= 250k within SEARCH_M with geometry simplified to ~100 m.
"""
from cache import coord_key
from geom import arcgis_query, geojson_polygon_dist_m
from provenance import Value, absent, failed, now_iso

NAME = 'metro'
LYR = 'https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Urban/MapServer/0'
SOURCE = 'Census TIGERweb 2020 Urban Areas (POP100 = Census 2020 count)'
VINTAGE = '2020'
SEARCH_M = 300000
REGIONAL = 250000
MAJOR = 1000000
METHOD = (f'TIGERweb 2020 Urban Areas: the area containing the point; all areas with POP100 >= {REGIONAL:,} '
          f'within {SEARCH_M // 1000} km (geometry simplified ~100 m); straight-line distance to the area boundary, 0 if inside')
NOTE = 'straight-line to the urban-area boundary, not driving distance; urban areas are built-up footprints, not MSAs'

FIELDS = ['metro_urban_area_at_point', 'metro_urban_area_at_point_pop',
          'metro_250k_nearest_name', 'metro_250k_nearest_m', 'metro_250k_nearest_pop',
          'metro_1m_nearest_name', 'metro_1m_nearest_m', 'metro_1m_nearest_pop']


def _clean(n):
    return (n or '').replace(' Urban Area', '').strip()


def run(site, cache):
    la, ln = site.lat, site.lng
    at, f1, e1 = cache.get_json(NAME, coord_key(la, ln, 'at'),
                                arcgis_query(LYR, la, ln, 'NAME,GEOID,POP100'))
    big, f2, e2 = cache.get_json(NAME, coord_key(la, ln, f'r{SEARCH_M // 1000}km_{REGIONAL}'),
                                 arcgis_query(LYR, la, ln, 'NAME,GEOID,POP100', distance_m=SEARCH_M, geometry=True,
                                              fmt='geojson', where=f'POP100 >= {REGIONAL}', precision=5, max_offset_m=100))
    fetched = f2 or f1 or now_iso()

    def mk(fld, val, note=NOTE):
        return Value(fld, val, SOURCE, LYR, METHOD, vintage=VINTAGE, fetched_at=fetched, note=note)

    out = []
    if e1:
        out += [failed(f, SOURCE, LYR, METHOD, e1) for f in FIELDS[:2]]
    else:
        feats = (at or {}).get('features') or []
        if feats:
            a = feats[0].get('attributes') or {}
            out += [mk('metro_urban_area_at_point', _clean(a.get('NAME'))), mk('metro_urban_area_at_point_pop', a.get('POP100'))]
        else:
            out += [absent(f, SOURCE, LYR, METHOD, note='point is outside every 2020 urban area (rural)', vintage=VINTAGE)
                    for f in FIELDS[:2]]

    if e2:
        out += [failed(f, SOURCE, LYR, METHOD, e2) for f in FIELDS[2:]]
        return out
    scored = []
    for f in (big or {}).get('features') or []:
        p = f.get('properties') or {}
        scored.append((geojson_polygon_dist_m(f.get('geometry'), ln, la), _clean(p.get('NAME')), p.get('POP100') or 0))
    scored.sort(key=lambda s: s[0])
    for thr, tag in ((REGIONAL, '250k'), (MAJOR, '1m')):
        hit = next((s for s in scored if s[2] >= thr), None)
        cols = (f'metro_{tag}_nearest_name', f'metro_{tag}_nearest_m', f'metro_{tag}_nearest_pop')
        if hit:
            out += [mk(cols[0], hit[1]), mk(cols[1], round(hit[0])), mk(cols[2], hit[2])]
        else:
            out += [absent(c, SOURCE, LYR, METHOD, note=f'no urban area with POP100 >= {thr:,} within {SEARCH_M // 1000} km',
                           vintage=VINTAGE) for c in cols]
    return out
