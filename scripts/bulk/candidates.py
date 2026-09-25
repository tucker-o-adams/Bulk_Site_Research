# -*- coding: utf-8 -*-
"""Candidate parcels for a site whose exact parcel is not known: every parcel of about the broker's stated acreage
inside the area the site can be in. Used for two cases (MEMOS.md, location status):

  * an approximate broker coordinate whose parcel does not match: search around the coordinate (its uncertainty
    radius) and, when the broker says the site is next to a named substation, around that substation too
  * a site placed only near a named substation or intersection (tier L3) whose tract the broker says is identified
    and whose acreage is stated: search the anchor's uncertainty circle

A third case, search_owner: a site the broker names only by its tracts' owners ('25 ac Smith + 23 ac Jones'),
placed within a ZIP (L4) or near an anchor (L3). Parcels under each name, within 15 % of the tract's acreage, inside
that area plus 2 km, from the county's owner-searchable service (data/reference/owner-search-services.json - a
separate, reviewed list: the statewide point layer, TxGIO identify, cannot filter by owner). The name's other parcels
there are kept as context (a larger one may hold the tract as a carve-out).

1-5 candidates make a question a person can answer (Needs confirmation); none, or more than that, leave the site
Not locatable. Nothing here picks a parcel: candidates are ranked for display only.

Parcels come from the county's registered service (registry.py). Services that cap an answer (TxGIO identify
stops at 2,000 records) are asked tile by tile, a tile split in four whenever it comes back at the cap.
Every answer goes through the shared cache; failures are never cached.
"""
import hashlib, json, math, os, re, urllib.parse

from shapely.geometry import shape, Point
from shapely.ops import transform
from pyproj import Transformer

from cache import coord_key
from producers import parcel as parcel_mod
import parcel_check
import registry

AC = 4046.8564224
TOL = 0.15              # a candidate is within 15 % of the stated acreage (the same test as a parcel match)
MAX_ASK = 5             # more candidates than this is not a question a person can answer from a list
CAP_FRACTION = 0.95     # an answer this close to the service's cap is treated as truncated and split
MIN_TILE_M = 150
# common areas of a subdivision (greenbelts, private streets, detention ponds) are never a site
COMMON_AREA = re.compile(r'\b(HOME ?OWNERS?|PROPERTY OWNERS|OWNERS ASS(OC|N)|HOA|COMMUNITY ASS(OC|N)|MASTER ASS(OC|N))', re.I)


def _tile_features(svc, bbox, cache, key_ll, depth=0, stats=None):
    """Every feature in a lng/lat bbox, splitting tiles that come back at the service's record cap."""
    url = parcel_check.request(svc, bbox)
    if not url:
        return None, f"parcel service protocol {svc.get('protocol')!r} cannot search an area"
    tag = hashlib.md5(repr([round(v, 6) for v in bbox]).encode()).hexdigest()[:10]
    resp, _, err = cache.get_json('parcel', coord_key(key_ll[0], key_ll[1], f'area_{tag}'), url)
    stats['requests'] += 1
    truncated = bool(err and 'truncated' in err)          # the cache refuses a capped answer it cannot page
    if err and not truncated:
        return None, err
    feats = [] if truncated else parcel_mod.features(resp, svc)
    cap = svc.get('max_records') or 2000
    w_m = (bbox[2] - bbox[0]) * 111320 * math.cos(math.radians((bbox[1] + bbox[3]) / 2))
    if truncated and w_m / 2 < MIN_TILE_M:
        return None, err
    if truncated or (len(feats) >= CAP_FRACTION * cap and w_m / 2 >= MIN_TILE_M):
        mx, my = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
        out = []
        for q in ((bbox[0], bbox[1], mx, my), (mx, bbox[1], bbox[2], my), (bbox[0], my, mx, bbox[3]), (mx, my, bbox[2], bbox[3])):
            f, e = _tile_features(svc, q, cache, key_ll, depth + 1, stats)
            if e:
                return None, e
            out += f
        return out, None
    return feats, None


def search(areas, acres, cache, substation=None, owner_like=None):
    """areas: [(lat, lng, radius_m)] - the site is somewhere in their union. acres: the broker's stated acreage.
    substation: {'name', 'lat', 'lng'} the broker says the site is next to (distance shown per candidate).
    owner_like: an owner name to rank first (e.g. the owner of the parcel under an approximate coordinate).
    Returns (result, error): result = {'n', 'candidates': [...], 'acres', 'areas', 'service', 'requests'}."""
    la0, ln0 = areas[0][0], areas[0][1]
    r = parcel_mod.resolve(la0, ln0, cache)
    svc = r.get('svc')
    if not svc:
        return None, f"no parcel service for this county ({r.get('stage')})"
    fwd = Transformer.from_crs('EPSG:4326', f'+proj=laea +lat_0={la0} +lon_0={ln0} +datum=WGS84 +units=m', always_xy=True).transform
    circles = [Point(*fwd(ln, la)).buffer(rad) for la, ln, rad in areas]
    stats = {'requests': 0}
    feats = []
    for la, ln, rad in areas:
        dlat, dlng = rad / 110540, rad / (111320 * max(0.2, math.cos(math.radians(la))))
        f, err = _tile_features(svc, (ln - dlng, la - dlat, ln + dlng, la + dlat), cache, (la, ln), stats=stats)
        if err:
            return None, err
        feats += f
    sub_pt = Point(*fwd(substation['lng'], substation['lat'])) if substation and substation.get('lat') is not None else None
    seen, out = set(), []
    for f in feats:
        g = f.get('geometry') or {}
        if not g.get('coordinates'):
            continue
        try:
            geom = shape(g)
            geom = geom if geom.is_valid else geom.buffer(0)
        except Exception:
            continue
        a = parcel_mod.geometry_area_m2(g) / AC
        if abs(a - acres) / acres > TOL:
            continue
        gm = transform(fwd, geom)
        if not any(gm.intersects(c) for c in circles):
            continue
        p = f.get('properties') or {}
        apn = registry.pick(p, svc, 'apn')
        k = (str(apn), round(a, 1))
        if k in seen:
            continue
        seen.add(k)
        owner = (registry.pick(p, svc, 'owner') or '').strip()
        if COMMON_AREA.search(owner):
            continue
        sub_m = round(gm.distance(sub_pt)) if sub_pt is not None else None
        out.append({'apn': apn, 'owner': owner, 'address': (registry.pick(p, svc, 'address') or '').strip(), 'acres': round(a, 2),
                    'diff_pct': round(100 * (a - acres) / acres), 'from_centre_m': round(gm.distance(Point(0, 0))),
                    'sub_m': sub_m, 'sub_adjacent': sub_m is not None and sub_m <= parcel_check.ADJ_M,
                    'same_owner': bool(owner_like) and parcel_check.same_owner(owner, owner_like), 'geom': geom})
    out.sort(key=lambda c: (not c['sub_adjacent'], not c['same_owner'], abs(c['diff_pct']), c['from_centre_m']))
    return {'n': len(out), 'candidates': out, 'acres': acres, 'areas': [list(x) for x in areas], 'service': svc.get('name'),
            'requests': stats['requests'], 'internal_only': bool(r.get('exclusion'))}, None


# ---------------------------------------------------------------- owner / tract-name search
OWNER_SERVICES = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'data', 'reference',
                              'owner-search-services.json')
OWNER_BUFFER_M = 2000       # beyond the area the site is known to be in (a ZIP's Census area is not its mailing area)


def owner_service(geoid):
    """The reviewed owner-searchable parcel service for a county GEOID, or None."""
    if not os.path.exists(OWNER_SERVICES):
        return None
    e = (json.load(open(OWNER_SERVICES, encoding='utf-8')).get('counties') or {}).get(str(geoid))
    return e['service'] if e else None


def search_owner(area, tracts, cache, svc, label):
    """Parcels under a name the broker gives for a tract ('25 ac Smith'), inside the area the site is known to be in.
    area: shapely lng/lat geometry (a ZIP polygon, an anchor circle); searched with OWNER_BUFFER_M around it.
    tracts: [{'name', 'acres'}] - acres may be None. svc: owner_service(). label: how the area is described.
    A candidate is a parcel under that name within 15 % of the tract's acreage (any size when none is stated); the
    name's other parcels in the area are kept as context (a larger one may hold the tract as a carve-out).
    Returns (result, error) with the same 'n' / 'candidates' shape as search(), plus kind='owner' and per-tract detail."""
    la0, ln0 = area.centroid.y, area.centroid.x
    fwd = Transformer.from_crs('EPSG:4326', f'+proj=laea +lat_0={la0} +lon_0={ln0} +datum=WGS84 +units=m', always_xy=True).transform
    area_m = transform(fwd, area).buffer(OWNER_BUFFER_M)
    inv = Transformer.from_crs(f'+proj=laea +lat_0={la0} +lon_0={ln0} +datum=WGS84 +units=m', 'EPSG:4326', always_xy=True).transform
    env = transform(inv, area_m).bounds
    f_ = svc['fields']
    out, cands = [], []
    for t in tracts:
        name = re.sub(r'[^A-Z ]', '', t['name'].upper()).strip()
        if len(name) < 3:
            continue
        q = urllib.parse.urlencode({'where': f"UPPER({f_['owner']}) LIKE '%{name}%'", 'outFields': ','.join(v for v in f_.values()),
                                    'geometry': ','.join(f'{v:.6f}' for v in env), 'geometryType': 'esriGeometryEnvelope', 'inSR': 4326,
                                    'spatialRel': 'esriSpatialRelIntersects', 'returnGeometry': 'true', 'outSR': 4326, 'f': 'geojson'})
        url = f"{svc['base']}/{svc['layer']}/query?{q}"
        tag = hashlib.md5(url.encode()).hexdigest()[:10]
        resp, _, err = cache.get_json('parcel', coord_key(la0, ln0, f'owner_{tag}'), url)
        if err:
            return None, err
        matches, others = [], []
        for feat in (resp or {}).get('features') or []:
            g = feat.get('geometry') or {}
            if not g.get('coordinates'):
                continue
            geom = shape(g)
            geom = geom if geom.is_valid else geom.buffer(0)
            gm = transform(fwd, geom)
            if not gm.intersects(area_m):
                continue
            p = feat.get('properties') or {}
            a = parcel_mod.geometry_area_m2(g) / AC
            c = {'apn': p.get(f_['apn']), 'owner': (p.get(f_['owner']) or '').strip(), 'address': (p.get(f_.get('address')) or '').strip(),
                 'legal': (p.get(f_.get('legal')) or '').strip(), 'acres': round(a, 2), 'tract': t['name'], 'tract_acres': t.get('acres'),
                 'diff_pct': round(100 * (a - t['acres']) / t['acres']) if t.get('acres') else None,
                 'outside_area_m': round(gm.distance(transform(fwd, area))), 'geom': geom}
            (matches if (not t.get('acres') or abs(a - t['acres']) / t['acres'] <= TOL) else others).append(c)
        matches.sort(key=lambda c: (abs(c['diff_pct'] or 0), c['outside_area_m']))
        others.sort(key=lambda c: -c['acres'])
        out.append({'name': t['name'], 'acres': t.get('acres'), 'matches': [{k: v for k, v in c.items() if k != 'geom'} for c in matches],
                    'others': [{k: v for k, v in c.items() if k != 'geom'} for c in others]})
        cands += matches
        for c in others:
            c['context'] = True
        t['_others'] = others
    return {'kind': 'owner', 'n': len(cands), 'candidates': cands, 'context': [c for t in tracts for c in t.pop('_others', [])],
            'tracts': out, 'area': f'{label}, plus {OWNER_BUFFER_M / 1000:g} km', 'service': svc.get('name'), 'areas': []}, None


def to_json(res):
    """Serialisable copy (geometry dropped)."""
    return {**{k: v for k, v in res.items() if k not in ('candidates', 'context')},
            'candidates': [{k: v for k, v in c.items() if k not in ('geom', 'utm')} for c in res['candidates']],
            'context': [{k: v for k, v in c.items() if k not in ('geom', 'utm')} for c in res.get('context') or []]}
