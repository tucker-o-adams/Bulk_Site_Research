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

Homes near the footprint (BACKLOG 9j, 2026-10-07), Census context only - the home distance rules use actual
homes (producers/homes.py, FEMA USA Structures):
    hu_near_review/pass housing units within the profile's receptor distances of the site footprint (intake outline,
                        parcel or square; default 1,000 / 2,000 ft): each 2020 block's HU100 split by the share of
                        its area inside the distance. For an intake outline the site is taken out of each block
                        first. Block counts are spread evenly over large rural blocks, so these are estimates
"""
import math, urllib.parse
from shapely.geometry import shape
from shapely.ops import transform
from cache import coord_key
from geom import arcgis_envelope_query, arcgis_query, point_dist_m
from provenance import Value, absent, failed, now_iso
import product_profile as prof

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
          'hu_within_1mi', 'pop_within_1mi', 'blocks_within_1mi', 'hu_near_review', 'hu_near_pass']
HOME_FIELDS = FIELDS[8:]
PROFILE = None           # run.py sets the batch's product profile; None = product_profile.DEFAULTS distances
MARGIN_M = 300
METHOD_HOME = ('TIGERweb 2020 blocks with HU100 >= 1 intersecting the footprint bounding box grown by the pass distance '
               '+ 300 m (site taken out of each block for an intake outline); HU100 split by the share of each block '
               'area within the review / pass distance')


def receptor_m(p=None):
    p = p or PROFILE or prof.DEFAULTS
    return prof.m(p, 'receptor_review_ft'), prof.m(p, 'receptor_pass_ft')


def home_blocks(site, cache, fp):
    """Blocks with at least one home near a footprint: ([(HU100, off-site block geometry in footprint metres)], fetched, error)."""
    from producers import footprint
    _, pass_m = receptor_m()
    xmin, ymin, xmax, ymax = fp['m'].bounds
    grow = pass_m + MARGIN_M
    _, inv = footprint.projection(site.lat, site.lng)
    (x0, y0), (x1, y1) = inv(xmin - grow, ymin - grow), inv(xmax + grow, ymax + grow)
    url = arcgis_envelope_query(LYR, (x0, y0, x1, y1), 'GEOID,HU100') + '&where=' + urllib.parse.quote('HU100>0')
    key = coord_key(site.lat, site.lng, 'homes_' + '_'.join(str(round(v)) for v in (xmin - grow, ymin - grow, xmax + grow, ymax + grow)))
    resp, fetched, err = cache.get_json(NAME, key, url)
    if err:
        return None, fetched, err
    own = fp['m'] if fp['basis'] == footprint.BASIS_OUTLINE else None
    out = []
    for f in (resp or {}).get('features') or []:
        hu = (f.get('properties') or {}).get('HU100') or 0
        try:
            g = transform(fp['fwd'], shape(f['geometry']))
            g = g if g.is_valid else g.buffer(0)
        except Exception:
            continue
        if own is not None:
            g = g.difference(own)
        if hu > 0 and not g.is_empty:
            out.append((hu, g))
    return out, fetched, None


def _home_values(site, cache):
    from producers import footprint
    fp = footprint.shape_at(site.lat, site.lng, cache, site.acres_stated, site.outline)
    if fp['stage'] == 'failed':
        return [failed(f, SOURCE, LYR, METHOD_HOME, fp['error'] + '; rerun') for f in HOME_FIELDS]
    blocks, fetched, err = home_blocks(site, cache, fp)
    if err:
        return [failed(f, SOURCE, LYR, METHOD_HOME, err) for f in HOME_FIELDS]
    rev_m, pass_m = receptor_m()
    note = (f"from the {fp['basis']}; review {rev_m / prof.FT:,.0f} ft, pass {pass_m / prof.FT:,.0f} ft; Census estimate, "
            'context only - home distances come from actual homes (homes producer)')
    mk = lambda fld, val, n=note: Value(fld, val, SOURCE, LYR, METHOD_HOME, vintage=VINTAGE, fetched_at=fetched or now_iso(), note=n)
    if not blocks:
        why = f'no 2020 block with a home within {pass_m + MARGIN_M:,.0f} m of the footprint'
        return [mk('hu_near_review', 0, why), mk('hu_near_pass', 0, why)]
    def near(d):
        zone = fp['m'].buffer(d)                     # once per distance, not once per block
        return sum(hu * g.intersection(zone).area / g.area for hu, g in blocks if g.area > 0)
    return [mk('hu_near_review', round(near(rev_m), 1)),
            mk('hu_near_pass', round(near(pass_m), 1))]


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
        out += [failed(f, SOURCE, LYR, METHOD, e2) for f in FIELDS[3:8]]
        return out + _home_values(site, cache)
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
    return out + _home_values(site, cache)
