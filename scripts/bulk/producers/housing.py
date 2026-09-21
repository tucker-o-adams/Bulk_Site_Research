# -*- coding: utf-8 -*-
"""Residential context from Census 2020 blocks: housing units and population
in the block under the pin and within 0.5 mi and 1 mi.

Method: one TIGERweb query for blocks within 1 mi (+ margin) of the point,
attributes only. A block is counted inside a radius when its Census internal
point (INTPTLAT/INTPTLON) is inside — whole or not at all. Blocks are small in
built-up areas (a city block) and large in the country (a square mile or
more), so the rural figures are coarse and the block-at-point row shows how
much area that one block covers. Raw counts only; no density class until the
thresholds are agreed.
"""
import math
from cache import coord_key
from geom import arcgis_query, point_dist_m
from provenance import Value, absent, failed, now_iso

NAME = 'housing'
LYR = 'https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/tigerWMS_Census2020/MapServer/10'
SOURCE = 'Census TIGERweb 2020 Census Blocks (HU100 housing units, POP100 population)'
VINTAGE = '2020'
HALF_MI, ONE_MI = 804.672, 1609.344
SEARCH_M = 2400          # 1 mi plus margin so large rural blocks' internal points are seen
METHOD = ('TIGERweb 2020 blocks within 1 mi of the point: HU100/POP100 summed over blocks whose Census internal '
          'point lies within 0.5 mi / 1 mi (blocks counted whole); the block containing the point reported separately')
NOTE = 'raw Census 2020 counts; rural blocks are large, so sums are coarse there and block-at-point area is given'

FIELDS = ['hu_block_at_point', 'pop_block_at_point', 'block_at_point_acres', 'hu_within_0_5mi', 'pop_within_0_5mi',
          'hu_within_1mi', 'pop_within_1mi', 'blocks_within_1mi']


def run(site, cache):
    la, ln = site.lat, site.lng
    at, f1, e1 = cache.get_json(NAME, coord_key(la, ln, 'blk'), arcgis_query(LYR, la, ln, 'GEOID,HU100,POP100,AREALAND'))
    near, f2, e2 = cache.get_json(NAME, coord_key(la, ln, f'r{SEARCH_M}'),
                                  arcgis_query(LYR, la, ln, 'GEOID,HU100,POP100,AREALAND,INTPTLAT,INTPTLON', distance_m=SEARCH_M))
    fetched = f2 or f1 or now_iso()

    def mk(fld, val, note=NOTE):
        return Value(fld, val, SOURCE, LYR, METHOD, vintage=VINTAGE, fetched_at=fetched, note=note)

    out = []
    if e1:
        out += [failed(f, SOURCE, LYR, METHOD, e1) for f in FIELDS[:3]]
    else:
        feats = (at or {}).get('features') or []
        if feats:
            a = feats[0]['attributes']
            out += [mk('hu_block_at_point', a.get('HU100')), mk('pop_block_at_point', a.get('POP100')),
                    mk('block_at_point_acres', round((a.get('AREALAND') or 0) / 4046.8564, 1))]
        else:
            out += [absent(f, SOURCE, LYR, METHOD, note='no 2020 block at the point', vintage=VINTAGE) for f in FIELDS[:3]]
    if e2:
        out += [failed(f, SOURCE, LYR, METHOD, e2) for f in FIELDS[3:]]
        return out
    hu5 = pop5 = hu1 = pop1 = n1 = 0
    for f in (near or {}).get('features') or []:
        a = f['attributes']
        try:
            d = point_dist_m(ln, la, float(a['INTPTLON']), float(a['INTPTLAT']))
        except (TypeError, ValueError, KeyError):
            continue
        if d <= ONE_MI:
            hu1 += a.get('HU100') or 0; pop1 += a.get('POP100') or 0; n1 += 1
            if d <= HALF_MI:
                hu5 += a.get('HU100') or 0; pop5 += a.get('POP100') or 0
    out += [mk('hu_within_0_5mi', hu5), mk('pop_within_0_5mi', pop5), mk('hu_within_1mi', hu1),
            mk('pop_within_1mi', pop1), mk('blocks_within_1mi', n1)]
    return out
