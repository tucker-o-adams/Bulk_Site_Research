# -*- coding: utf-8 -*-
"""EPA Superfund National Priorities List (NPL) sites near the site footprint (2026-10-08).

EPA publishes each NPL site as one point (its location), not its boundary, so "on the site" means the point falls inside
the footprint; a large NPL site whose point lies outside can still reach onto the land - read the distance with that in
mind. Measured from the footprint edge (producers/footprint.py: intake outline, parcel or square). NPL only: brownfields
and hazardous-waste (RCRA) sites are separate EPA layers, not checked here.
"""
from shapely.geometry import Point
from cache import coord_key
from geom import arcgis_envelope_query
from provenance import Value, absent, failed, now_iso

NAME = 'superfund'
LYR = ('https://services.arcgis.com/cJ9YHowT8TU7DUyn/arcgis/rest/services/'
       'Superfund_National_Priorities_List_(NPL)_Sites_with_Status_Information/FeatureServer/0')
SOURCE = 'EPA Superfund National Priorities List sites (points)'
VINTAGE = None
SEARCH_M = 5000
METHOD = f"EPA NPL site points within the footprint's bounding box grown by {SEARCH_M} m; distance from the footprint edge"
NOTE = 'NPL sites are points, not boundaries; NPL only (no brownfields or RCRA)'
FIELDS = ['npl_on_site', 'npl_nearest_m', 'npl_nearest_name', 'npl_nearest_status', 'npl_within_5km']


def run(site, cache):
    from producers import footprint
    fp = footprint.shape_at(site.lat, site.lng, cache, site.acres_stated, site.outline)
    if fp['stage'] == 'failed':
        return [failed(f, SOURCE, LYR, METHOD, fp['error'] + '; rerun') for f in FIELDS]
    inv = footprint.projection(site.lat, site.lng)[1]
    x0, y0, x1, y1 = fp['m'].bounds
    (a, b), (c, d) = inv(x0 - SEARCH_M, y0 - SEARCH_M), inv(x1 + SEARCH_M, y1 + SEARCH_M)
    url = arcgis_envelope_query(LYR, (a, b, c, d), 'Site_Name,Status,Site_EPA_ID')
    key = coord_key(site.lat, site.lng, 'npl_' + '_'.join(str(round(v)) for v in (x0, y0, x1, y1)))
    resp, fetched, err = cache.get_json(NAME, key, url)
    if err:
        return [failed(f, SOURCE, LYR, METHOD, err) for f in FIELDS]
    mk = lambda fld, val: Value(fld, val, SOURCE, LYR, METHOD, fetched_at=fetched or now_iso(), note=NOTE)
    pts = []
    for f in (resp or {}).get('features') or []:
        g = f.get('geometry') or {}
        if g.get('type') == 'Point':
            x, y = fp['fwd'](*g['coordinates'][:2])
            pts.append((Point(x, y).distance(fp['m']), f.get('properties') or {}))
    pts.sort(key=lambda t: t[0])
    within = sum(1 for dd, _ in pts if dd <= SEARCH_M)
    if not pts or pts[0][0] > SEARCH_M:
        why = f'no NPL site within {SEARCH_M:,} m of the site'
        return [mk('npl_on_site', False)] + [absent(f, SOURCE, LYR, METHOD, note=why) for f in FIELDS[1:4]] + [mk('npl_within_5km', 0)]
    d0, p0 = pts[0]
    return [mk('npl_on_site', d0 == 0), mk('npl_nearest_m', round(d0, 1)), mk('npl_nearest_name', p0.get('Site_Name')),
            mk('npl_nearest_status', p0.get('Status')), mk('npl_within_5km', within)]
