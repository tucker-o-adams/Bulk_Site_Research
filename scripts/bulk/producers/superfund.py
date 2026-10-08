# -*- coding: utf-8 -*-
"""EPA Superfund National Priorities List (NPL) sites near the site footprint (2026-10-08).

EPA publishes each NPL site as one point (its location), not its boundary, so "on the site" means the point falls inside
the footprint; a large NPL site whose point lies outside can still reach onto the land - read the distance with that in
mind. Measured from the footprint edge (producers/footprint.py: intake outline, parcel or square). NPL only: brownfields
and hazardous-waste (RCRA) sites are separate EPA layers, not checked here.

Distances follow the Phase I environmental site assessment standard (ASTM E1527-21 minimum search distances, from the
property boundary; 2026-10-08): an active NPL site within 1 mile, a deleted (cleaned-up) NPL site within 0.5 mile, and
anything on the site. A proposed NPL site is counted as active. The nearest site within 5 km stays as context.
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
NOTE = 'NPL sites are points, not boundaries; NPL only (no brownfields or RCRA); 1 mi / 0.5 mi per ASTM E1527-21 search distances'
ACTIVE_M, DELETED_M = 1609.344, 804.672        # ASTM E1527-21: 1 mile (NPL), 0.5 mile (deleted NPL)
FIELDS = ['npl_on_site', 'npl_active_within_1mi', 'npl_deleted_within_half_mi', 'npl_nearest_m', 'npl_nearest_name',
          'npl_nearest_status']


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
    deleted = lambda p: 'DELETED' in (p.get('Status') or '').upper()
    out = [mk('npl_on_site', bool(pts) and pts[0][0] == 0),
           mk('npl_active_within_1mi', sum(1 for dd, p in pts if dd <= ACTIVE_M and not deleted(p))),
           mk('npl_deleted_within_half_mi', sum(1 for dd, p in pts if dd <= DELETED_M and deleted(p)))]
    if not pts or pts[0][0] > SEARCH_M:
        why = f'no NPL site within {SEARCH_M:,} m of the site'
        return out + [absent(f, SOURCE, LYR, METHOD, note=why) for f in FIELDS[3:]]
    d0, p0 = pts[0]
    return out + [mk('npl_nearest_m', round(d0, 1)), mk('npl_nearest_name', p0.get('Site_Name')), mk('npl_nearest_status', p0.get('Status'))]
