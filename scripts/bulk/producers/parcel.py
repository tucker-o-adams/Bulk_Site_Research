# -*- coding: utf-8 -*-
"""The legal parcel under the site pin: boundary, area, APN, owner.

Everything else in this pipeline is point-based ("the pin is in Zone X").
This is what makes statements about the *site* possible — buildable acres, a
parcel-clipped flood or wetland figure, the outline on the map.

Two steps:
  1. county   Census TIGERweb State_County: the county GEOID containing the point.
              Never inferred from coordinates alone (tbdi-pasa's rule).
  2. parcel   the county's (or state's) parcel service from `registry.py`,
              queried point-in-polygon. No registry entry -> `unresolved`, with
              the county named so discovery can be run for it.

Ported from tbdi-pasa `pasa_geo/core.parcel_at_point` and `pasa_geo/county`;
the geometry maths is local (geom.py) rather than geopandas so a batch run
stays dependency-light. Area is computed on the WGS84 ellipsoid.

Three honest limits, carried on every row:
  * **The address/point-to-parcel link is one point landing in one polygon.**
    Confirm the APN against the assessor (or the client's own APN) before the
    geometry is relied on. `parcel_apn_matches_input` does that check when the
    input CSV supplies an `apn`.
  * A parcel is not a site. A facility may span several parcels, in which case
    this acreage is a floor.
  * County services are unstable — two vanished mid-project in Sep 2026 — so a
    vintage and the service URL travel with every value.
"""
import math
from cache import coord_key
from geom import arcgis_query, ring_contains
from provenance import Value, absent, failed, now_iso
import registry

NAME = 'parcel'
TIGER = 'https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/State_County/MapServer/1'
LYR = TIGER
SOURCE = 'County / state GIS parcel services (registry) + Census TIGERweb counties'
VINTAGE = None
METHOD = ('Census TIGERweb county at the point, then the registered county (or statewide) parcel service '
          'queried point-in-polygon; area on the WGS84 ellipsoid from the returned boundary')
NOTE = ('one point landing in one polygon - confirm the APN against the assessor; a facility spanning several '
        'parcels makes this acreage a floor')

FIELDS = ['parcel_county', 'parcel_county_geoid', 'parcel_source_scope', 'parcel_service_name',
          'parcel_apn', 'parcel_owner', 'parcel_address', 'parcel_acres_gis', 'parcel_acres_stated_by_county',
          'parcel_acres_input', 'parcel_apn_matches_input', 'parcel_vertices', 'parcel_status']


def ring_area_m2(ring):
    """Spherical excess area of a closed ring of (lng, lat), in m^2."""
    R = 6378137.0
    if ring[0] != ring[-1]:
        ring = list(ring) + [ring[0]]
    t = 0.0
    for i in range(len(ring) - 1):
        x1, y1 = math.radians(ring[i][0]), math.radians(ring[i][1])
        x2, y2 = math.radians(ring[i + 1][0]), math.radians(ring[i + 1][1])
        t += (x2 - x1) * (2 + math.sin(y1) + math.sin(y2))
    return abs(t * R * R / 2.0)


def polygon_area_m2(rings):
    """Outer ring minus holes."""
    if not rings:
        return 0.0
    return max(0.0, ring_area_m2(rings[0]) - sum(ring_area_m2(h) for h in rings[1:]))


def geometry_area_m2(g):
    if not g:
        return 0.0
    if g.get('type') == 'Polygon':
        return polygon_area_m2(g['coordinates'])
    if g.get('type') == 'MultiPolygon':
        return sum(polygon_area_m2(p) for p in g['coordinates'])
    return 0.0


def contains(g, lng, lat):
    polys = [g['coordinates']] if g.get('type') == 'Polygon' else g.get('coordinates', []) if g.get('type') == 'MultiPolygon' else []
    for rings in polys:
        if ring_contains(rings[0], lng, lat) and not any(ring_contains(h, lng, lat) for h in rings[1:]):
            return True
    return False


def vertices(g):
    polys = [g['coordinates']] if g.get('type') == 'Polygon' else g.get('coordinates', []) if g.get('type') == 'MultiPolygon' else []
    return sum(len(r) - 1 for rings in polys for r in rings)


def run(site, cache):
    la, ln = site.lat, site.lng
    fetched = now_iso()

    # ---- 1. county
    cty, f1, e1 = cache.get_json(NAME, coord_key(la, ln, 'county'), arcgis_query(TIGER, la, ln, 'GEOID,NAME,STATE,COUNTY'))
    if e1:
        return [failed(f, SOURCE, TIGER, METHOD, f'TIGERweb county query: {e1}') for f in FIELDS]
    feats = (cty or {}).get('features') or []
    if not feats:
        return [absent(f, SOURCE, TIGER, METHOD, note='no US county contains this point', vintage='2025') for f in FIELDS]
    a = feats[0]['attributes']
    geoid, cname, sfips = a.get('GEOID'), a.get('NAME'), a.get('STATE')
    fetched = f1 or fetched

    def mk(fld, val, src, url, vint, note=NOTE):
        return Value(fld, val, src, url, METHOD, vintage=vint, fetched_at=fetched, note=note)

    out = [mk('parcel_county', cname, 'Census TIGERweb Counties', TIGER, '2025', 'county by spatial query, not inferred from coordinates'),
           mk('parcel_county_geoid', geoid, 'Census TIGERweb Counties', TIGER, '2025', 'county by spatial query, not inferred from coordinates')]

    # ---- 2. parcel service from the registry
    svc, scope, entry = registry.for_county(geoid, sfips)
    if not svc:
        why = (f'no parcel service registered for {cname} County ({geoid}); run '
               f'scripts/bulk/reference/discover_parcel_service.py --geoid {geoid} and review the proposal')
        return out + [absent(f, SOURCE, LYR, METHOD, note=why, vintage='2025') for f in FIELDS[2:12]] + \
            [mk('parcel_status', 'unresolved: no registered service', SOURCE, LYR, '2025', why)]

    url = f"{svc['base']}/{svc['layer']}"
    # The vintage on a value is the data's, not the day a person reviewed the service: an
    # Iowa 2017 snapshot reviewed in 2026 must not carry a 2026 vintage.
    vint = svc.get('data_vintage') or entry.get('reviewed') or svc.get('reviewed')
    src = f"{svc.get('name')} ({svc.get('owner')})"
    resp, f2, e2 = cache.get_json(NAME, coord_key(la, ln, f"parcel_{scope}"),
                                  arcgis_query(url, la, ln, '*', geometry=True, fmt='geojson', precision=7))
    if e2:
        return out + [failed(f, src, url, METHOD, e2) for f in FIELDS[2:]]
    fetched = f2 or fetched
    hits = [f for f in (resp or {}).get('features') or [] if contains(f.get('geometry') or {}, ln, la)] or \
           [(resp or {}).get('features') or []][0][:1]
    if not hits:
        why = f'{svc.get("name")} returned no parcel polygon containing the point'
        return out + [absent(f, src, url, METHOD, note=why, vintage=vint) for f in FIELDS[2:12]] + \
            [mk('parcel_status', 'unresolved: no polygon at the point', src, url, vint, why)]

    f = hits[0]
    g = f.get('geometry') or {}
    p = f.get('properties') or {}
    apn = registry.pick(p, svc, 'apn')
    acres_gis = geometry_area_m2(g) / 4046.8564224
    stated = registry.pick(p, svc, 'acres')
    try:
        stated = float(stated) if stated not in (None, '') else None
    except (TypeError, ValueError):
        stated = None
    note = NOTE + (f'; {len(hits)} parcels returned for one point' if len(hits) > 1 else '')

    out += [mk('parcel_source_scope', scope, src, url, vint, note),
            mk('parcel_service_name', svc.get('name'), src, url, vint, note),
            mk('parcel_apn', apn, src, url, vint, note),
            mk('parcel_owner', registry.pick(p, svc, 'owner'), src, url, vint, note),
            mk('parcel_address', registry.pick(p, svc, 'address'), src, url, vint, note),
            mk('parcel_acres_gis', round(acres_gis, 4), src, url, vint, note)]
    out.append(mk('parcel_acres_stated_by_county', round(stated, 4), src, url, vint, note) if stated is not None
               else absent('parcel_acres_stated_by_county', src, url, METHOD, note='the service publishes no acreage field', vintage=vint))
    # input cross-checks
    if site.acres_stated is not None:
        out.append(mk('parcel_acres_input', site.acres_stated, 'input CSV', '', None,
                      'supplied by the client; compare with parcel_acres_gis'))
    else:
        out.append(absent('parcel_acres_input', 'input CSV', '', METHOD, note='no acres_stated in the input CSV'))
    if site.apn:
        norm = lambda s: ''.join(ch for ch in str(s).upper() if ch.isalnum())
        out.append(mk('parcel_apn_matches_input', bool(apn) and norm(apn) == norm(site.apn), src, url, vint,
                      'the assessor is the authority; a mismatch means the pin may be on the wrong parcel'))
    else:
        out.append(absent('parcel_apn_matches_input', 'input CSV', '', METHOD, note='no apn in the input CSV to check against'))
    out += [mk('parcel_vertices', vertices(g), src, url, vint, note),
            mk('parcel_status', 'ok', src, url, vint, note)]
    return out
