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

Three ways to ask a service for the polygon at a point (`service.protocol`):
  * `query`    (default) ArcGIS layer `/query`, returned as GeoJSON.
  * `identify` ArcGIS MapServer `/identify`, for a service that disables `/query`
               (TxGIO StratMap). Esri rings are converted to GeoJSON by tbdi-geo.
  * `wms`      OGC WMS `GetFeatureInfo` as JSON, for a GeoServer that publishes
               parcels "view only or through OGC WMS" (OKMaps). One request per
               site, never a harvest.
Building the request, reading any protocol's answer and picking the parcel under the pin are tbdi-geo's
`parcels` (shared with tbdi-pasa).
A service may name a `vintage` field: statewide layers are compiled from counties
refreshed at different times, so the county's own date beats the layer's.

`parcel_owner_check` compares the owner (and parcel id, so a public-utility
numbering convention like Houston GA's `-PU` counts) against the expected owner
given by `run.py --expected-owner` or an `expected_owner` input column. For a
portfolio batch the owner of record is the cheapest evidence that the pin landed
on the right parcel; anything else is flagged for a person to look at.
"""
import math, re
from cache import coord_key
from geom import arcgis_query
from provenance import Value, absent, failed, now_iso
import registry
from tbdi_geo import parcels
from tbdi_geo import registry as shared

NAME = 'parcel'
TIGER = shared.layer_url('census-tigerweb')      # tbdi-geo source registry
LYR = TIGER
SOURCE = 'County / state GIS parcel services (registry) + Census TIGERweb counties'
VINTAGE = None
METHOD = ('Census TIGERweb county at the point, then the registered county (or statewide) parcel service '
          'queried point-in-polygon; area on the WGS84 ellipsoid from the returned boundary')
NOTE = ('one point landing in one polygon - confirm the APN against the assessor; a facility spanning several '
        'parcels makes this acreage a floor')

FIELDS = ['parcel_county', 'parcel_county_geoid', 'parcel_source_scope', 'parcel_service_name',
          'parcel_apn', 'parcel_owner', 'parcel_address', 'parcel_acres_gis', 'parcel_acres_stated_by_county',
          'parcel_acres_input', 'parcel_apn_matches_input', 'parcel_owner_check', 'parcel_vertices', 'parcel_use', 'parcel_status']

# A returned polygon that does not contain the pin is accepted only within tbdi-geo's parcels.NEAR_M (2 m, a WMS
# pixel) and says so in its note. Not more: a geocoded pin sits on the street centreline. Street-centreline pins
# need an address match (BACKLOG parcel approach D), not a bigger radius.
NEAR_M = parcels.NEAR_M

# Regex for the owner a portfolio's parcels should carry; set by run.py --expected-owner.
# An `expected_owner` column in the input CSV overrides it per site.
EXPECTED_OWNER = None


def request_url(svc, la, ln):
    """The URL that asks a registered service for the polygon at one point, by its protocol (tbdi-geo parcels).
    precision=7 (query only) rounds the returned boundary to ~1 cm; acreage is measured on that boundary."""
    return parcels.request_url(svc, ln, la, precision=7)


def features(resp, svc):
    """GeoJSON-style features from any protocol's response (tbdi-geo parcels)."""
    return parcels.features(svc, resp)


as_date = parcels.as_date


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


def vertices(g):
    polys = [g['coordinates']] if g.get('type') == 'Polygon' else g.get('coordinates', []) if g.get('type') == 'MultiPolygon' else []
    return sum(len(r) - 1 for rings in polys for r in rings)


def owner_check(site, svc, owner, apn, mk):
    """'expected owner' / 'different owner - review' / 'no owner in source - review' /
    'not checkable: source has no owner field' (Ohio's aggregation omits owners by design)."""
    pat = (site.extra or {}).get('expected_owner') or EXPECTED_OWNER
    if not pat:
        return absent('parcel_owner_check', 'input CSV', '', METHOD,
                      note='no expected owner given (run.py --expected-owner, or an expected_owner column)')
    why = f'owner and parcel id checked against /{pat}/'
    if re.search(pat, f"{owner or ''} {apn or ''}", re.I):
        return mk('expected owner', why)
    if not registry.field(svc, 'owner'):
        return mk('not checkable: source has no owner field', why + '; confirm the APN with the assessor instead')
    if not str(owner or '').strip():
        return mk('no owner in source - review', why + '; the service carries no owner for this parcel')
    return mk('different owner - review', why + '; the pin may be on a neighbouring parcel')


INTERNAL_ONLY = 'INTERNAL USE ONLY (licensed county)'


def internal_note(r, cname=None):
    """'; INTERNAL USE ONLY ...' for a parcel from a county the statewide layer's licence excludes, else ''."""
    if not r.get('exclusion'):
        return ''
    cname = cname or (r.get('county') or {}).get('NAME') or r['exclusion'].get('county')
    cname = cname if str(cname).endswith('County') else f'{cname} County'
    return (f"; INTERNAL USE ONLY: {cname} is a licensed dataset in {r['svc'].get('name')} (its licence does "
            f"not extend to TBDI); used for internal screening by decision 2026-09-23 - not for external "
            f"deliverables; register the county appraisal district's own service before this parcel leaves TBDI")


def resolve(la, ln, cache):
    """County -> registered service -> the parcel polygon at the point, through the shared cache.

    `run` turns every stage into Values; `footprint.py`, `kmz.py` and `figure.py` need only the
    polygon, and must get the very one the workbook measured. `stage` is one of
    county_failed, no_county, unregistered, parcel_failed, no_polygon, ok. `exclusion` is set when the
    county is on the statewide layer's exclude list: the parcel is still used, marked internal-only (internal_note)."""
    r = {'stage': None, 'error': None, 'county': None, 'svc': None, 'scope': None, 'entry': None,
         'exclusion': None, 'feature': None, 'hits': 0, 'fetched_county': None, 'fetched_parcel': None}

    # ---- 1. county
    cty, f1, e1 = cache.get_json(NAME, coord_key(la, ln, 'county'), arcgis_query(TIGER, la, ln, 'GEOID,NAME,STATE,COUNTY'))
    if e1:
        return {**r, 'stage': 'county_failed', 'error': e1}
    feats = (cty or {}).get('features') or []
    if not feats:
        return {**r, 'stage': 'no_county'}
    r['county'] = feats[0]['attributes']
    r['fetched_county'] = f1
    geoid, sfips = r['county'].get('GEOID'), r['county'].get('STATE')

    # ---- 2. parcel service from the registry
    svc, scope, entry = registry.for_county(geoid, sfips)
    r.update(svc=svc, scope=scope, entry=entry)
    if not svc:
        return {**r, 'stage': 'unregistered'}
    # A statewide layer can carry counties whose licence does not extend to us (TxGIO's licensed CAD
    # datasets). Tucker, 2026-09-23: use the shape when the service returns it, for internal work only -
    # the exclusion rides along on the result so every value and figure is marked INTERNAL USE ONLY.
    excl = (svc.get('exclude') or {}).get(str(geoid)) if scope == 'statewide' else None
    r['exclusion'] = excl
    resp, f2, e2 = cache.get_json(NAME, coord_key(la, ln, f"parcel_{scope}"), request_url(svc, la, ln))
    if e2:
        return {**r, 'stage': 'parcel_failed', 'error': e2}
    r['fetched_parcel'] = f2
    feats = features(resp, svc)
    feat, hits, off_m = parcels.at_point(feats, ln, la)
    if feat is None:
        return {**r, 'stage': 'no_polygon', 'nearest_m': off_m}
    # notes give the offset to 0.1 m, measured afresh rather than re-rounding tbdi-geo's 0.01 m
    d = parcels.distance_m(feat.get('geometry'), ln, la)
    near_m = round(d, 1) if d > 0 else None
    return {**r, 'stage': 'ok', 'feature': feat, 'hits': hits, 'near_m': near_m}


def run(site, cache):
    la, ln = site.lat, site.lng
    fetched = now_iso()
    r = resolve(la, ln, cache)

    # ---- 1. county
    if r['stage'] == 'county_failed':
        return [failed(f, SOURCE, TIGER, METHOD, f"TIGERweb county query: {r['error']}") for f in FIELDS]
    if r['stage'] == 'no_county':
        return [absent(f, SOURCE, TIGER, METHOD, note='no US county contains this point', vintage='2025') for f in FIELDS]
    a = r['county']
    geoid, cname = a.get('GEOID'), a.get('NAME')
    fetched = r['fetched_county'] or fetched

    def mk(fld, val, src, url, vint, note=NOTE):
        return Value(fld, val, src, url, METHOD, vintage=vint, fetched_at=fetched, note=note)

    out = [mk('parcel_county', cname, 'Census TIGERweb Counties', TIGER, '2025', 'county by spatial query, not inferred from coordinates'),
           mk('parcel_county_geoid', geoid, 'Census TIGERweb Counties', TIGER, '2025', 'county by spatial query, not inferred from coordinates')]

    # ---- 2. parcel service from the registry
    svc, scope, entry = r['svc'], r['scope'], r['entry']
    if r['stage'] == 'unregistered':
        why = (f'no parcel service registered for {cname} County ({geoid}); run '
               f'scripts/bulk/reference/discover_parcel_service.py --geoid {geoid} and review the proposal')
        return out + [absent(f, SOURCE, LYR, METHOD, note=why, vintage='2025') for f in FIELDS[2:-1]] + \
            [mk('parcel_status', 'unresolved: no registered service', SOURCE, LYR, '2025', why)]
    url = svc['base'] if svc.get('protocol') == 'wms' else f"{svc['base']}/{svc['layer']}"
    # The vintage on a value is the data's, not the day a person reviewed the service: an
    # Iowa 2017 snapshot reviewed in 2026 must not carry a 2026 vintage.
    vint = svc.get('data_vintage') or entry.get('reviewed') or svc.get('reviewed')
    src = f"{svc.get('name')} ({svc.get('owner')})"
    if r['stage'] == 'parcel_failed':
        return out + [failed(f, src, url, METHOD, r['error']) for f in FIELDS[2:]]
    fetched = r['fetched_parcel'] or fetched
    if r['stage'] == 'no_polygon':
        why = f'{svc.get("name")} returned no parcel polygon containing the point' + (
            f"; the nearest returned polygon is {r['nearest_m']:,.1f} m away (over {NEAR_M:g} m, so it may be a neighbour - check by hand)"
            if r.get('nearest_m') is not None else '')
        return out + [absent(f, src, url, METHOD, note=why, vintage=vint) for f in FIELDS[2:-1]] + \
            [mk('parcel_status', 'unresolved: no polygon at the point', src, url, vint, why)]

    f = r['feature']
    g = f.get('geometry') or {}
    p = f.get('properties') or {}
    vint = as_date(registry.pick(p, svc, 'vintage')) or vint
    apn = registry.pick(p, svc, 'apn')
    owner = registry.pick(p, svc, 'owner')
    acres_gis = geometry_area_m2(g) / 4046.8564224
    stated = registry.pick(p, svc, 'acres')
    try:
        stated = float(stated) if stated not in (None, '') else None
    except (TypeError, ValueError):
        stated = None
    note = NOTE + (f"; {r['hits']} parcels returned for one point" if r['hits'] > 1 else '') + (
        f"; the polygon does not contain the pin - it is {r['near_m']} m away (within the {NEAR_M:g} m tolerance)"
        if r.get('near_m') is not None else '') + internal_note(r, cname)

    out += [mk('parcel_source_scope', scope, src, url, vint, note),
            mk('parcel_service_name', svc.get('name'), src, url, vint, note),
            mk('parcel_apn', apn, src, url, vint, note),
            mk('parcel_owner', owner, src, url, vint, note),
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
    out.append(owner_check(site, svc, owner, apn, lambda val, why: mk('parcel_owner_check', val, src, url, vint, why)))
    out += [mk('parcel_vertices', vertices(g), src, url, vint, note),
            mk('parcel_use', INTERNAL_ONLY if r.get('exclusion') else 'open', src, url, vint, note),
            mk('parcel_status', 'ok', src, url, vint, note)]
    return out
