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
               (TxGIO StratMap). Esri rings are converted to GeoJSON here.
  * `wms`      OGC WMS `GetFeatureInfo` as JSON, for a GeoServer that publishes
               parcels "view only or through OGC WMS" (OKMaps). One request per
               site, never a harvest.
A service may name a `vintage` field: statewide layers are compiled from counties
refreshed at different times, so the county's own date beats the layer's.

`parcel_owner_check` compares the owner (and parcel id, so a public-utility
numbering convention like Houston GA's `-PU` counts) against the expected owner
given by `run.py --expected-owner` or an `expected_owner` input column. For a
portfolio batch the owner of record is the cheapest evidence that the pin landed
on the right parcel; anything else is flagged for a person to look at.
"""
import math, re, urllib.parse
from datetime import datetime, timezone
from cache import coord_key
from geom import arcgis_query, geojson_polygon_dist_m, ring_contains
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
          'parcel_acres_input', 'parcel_apn_matches_input', 'parcel_owner_check', 'parcel_vertices', 'parcel_status']

# A returned polygon that does not contain the pin is accepted only this close to it - a WMS pixel
# tolerance (OKMaps returned VIANOK05's parcel 0.6 m off the pin; a GetFeatureInfo pixel is ~1 m) -
# and says so in its note. Not more: a geocoded pin sits on the street centreline, and in NJ testing
# the nearest parcel to "2 Broad St, Bloomfield" (13 m) was the neighbour, the right one 15.9 m away.
# Street-centreline pins need an address match (BACKLOG parcel approach D), not a bigger radius.
NEAR_M = 2

# Regex for the owner a portfolio's parcels should carry; set by run.py --expected-owner.
# An `expected_owner` column in the input CSV overrides it per site.
EXPECTED_OWNER = None


def request_url(svc, la, ln):
    """The URL that asks a registered service for the polygon at one point, by its protocol."""
    proto = svc.get('protocol', 'query')
    if proto == 'identify':
        d = 0.001
        return (f"{svc['base']}/identify?f=json&geometryType=esriGeometryPoint&sr=4326&tolerance=0"
                f"&layers=all:{svc['layer']}&returnGeometry=true&geometry={ln},{la}"
                f"&mapExtent={ln - d},{la - d},{ln + d},{la + d}&imageDisplay=400,400,96")
    if proto == 'wms':
        d = 0.0005                     # GeoServer answers only at a street-level scale
        lyr = urllib.parse.quote(str(svc['layer']))
        return (f"{svc['base']}?SERVICE=WMS&VERSION=1.1.1&REQUEST=GetFeatureInfo&SRS=EPSG:4326"
                f"&BBOX={ln - d},{la - d},{ln + d},{la + d}&WIDTH=101&HEIGHT=101&X=50&Y=50"
                f"&LAYERS={lyr}&QUERY_LAYERS={lyr}&STYLES=&INFO_FORMAT=application/json&FEATURE_COUNT=5")
    return arcgis_query(f"{svc['base']}/{svc['layer']}", la, ln, '*', geometry=True, fmt='geojson', precision=7)


def esri_polygon(g):
    """Esri JSON rings -> GeoJSON Polygon/MultiPolygon. Esri outer rings run clockwise, holes counter-clockwise."""
    polys = []
    for r in (g or {}).get('rings') or []:
        r = [(p[0], p[1]) for p in r]
        signed = sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(r, r[1:]))
        if signed <= 0 or not polys:
            polys.append([r])
        else:
            polys[-1].append(r)
    if not polys:
        return {}
    return {'type': 'Polygon', 'coordinates': polys[0]} if len(polys) == 1 else {'type': 'MultiPolygon', 'coordinates': polys}


def features(resp, svc):
    """GeoJSON-style features from any protocol's response."""
    if svc.get('protocol') == 'identify':
        return [{'geometry': esri_polygon(r.get('geometry')), 'properties': r.get('attributes') or {}}
                for r in (resp or {}).get('results') or [] if r.get('layerId') == svc['layer']]
    return (resp or {}).get('features') or []


def as_date(v):
    """A source's date value (epoch ms, '20250201', ISO timestamp, or a year) as an ISO date string."""
    if v in (None, '', 'Null'):
        return None
    if isinstance(v, (int, float)) and v > 1e11:
        return datetime.fromtimestamp(v / 1000, tz=timezone.utc).date().isoformat()
    s = str(v).strip()
    if re.fullmatch(r'\d{8}', s):
        return f'{s[:4]}-{s[4:6]}-{s[6:]}'
    m = re.match(r'\d{4}-\d{2}-\d{2}', s)
    return m.group(0) if m else s


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


def resolve(la, ln, cache):
    """County -> registered service -> the parcel polygon at the point, through the shared cache.

    `run` turns every stage into Values; `footprint.py`, `kmz.py` and `figure.py` need only the
    polygon, and must get the very one the workbook measured. `stage` is one of
    county_failed, no_county, unregistered, excluded, parcel_failed, no_polygon, ok."""
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
    # A statewide layer can carry counties we may not use (TxGIO's licensed CAD datasets).
    excl = (svc.get('exclude') or {}).get(str(geoid)) if scope == 'statewide' else None
    if excl:
        return {**r, 'stage': 'excluded', 'exclusion': excl}
    resp, f2, e2 = cache.get_json(NAME, coord_key(la, ln, f"parcel_{scope}"), request_url(svc, la, ln))
    if e2:
        return {**r, 'stage': 'parcel_failed', 'error': e2}
    r['fetched_parcel'] = f2
    feats = features(resp, svc)
    hits = [f for f in feats if contains(f.get('geometry') or {}, ln, la)]
    if hits:
        return {**r, 'stage': 'ok', 'feature': hits[0], 'hits': len(hits), 'near_m': None}
    near = sorted(((geojson_polygon_dist_m(f.get('geometry'), ln, la), i) for i, f in enumerate(feats)
                   if (f.get('geometry') or {}).get('coordinates')))
    if near and near[0][0] <= NEAR_M:
        return {**r, 'stage': 'ok', 'feature': feats[near[0][1]], 'hits': 1, 'near_m': round(near[0][0], 1)}
    return {**r, 'stage': 'no_polygon', 'nearest_m': round(near[0][0], 1) if near else None}


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
    if r['stage'] == 'excluded':
        why = f"{svc.get('name')} excludes {cname} County ({geoid}): {r['exclusion'].get('reason')}"
        return out + [absent(f, SOURCE, LYR, METHOD, note=why, vintage='2025') for f in FIELDS[2:-1]] + \
            [mk('parcel_status', 'unresolved: county excluded from the statewide layer', SOURCE, LYR, '2025', why)]

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
            f"; the nearest returned polygon is {r['nearest_m']:,.1f} m away (over {NEAR_M} m, so it may be a neighbour - check by hand)"
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
        f"; the polygon does not contain the pin - it is {r['near_m']} m away (within the {NEAR_M} m tolerance)"
        if r.get('near_m') is not None else '')

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
            mk('parcel_status', 'ok', src, url, vint, note)]
    return out
