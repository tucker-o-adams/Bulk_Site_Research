# -*- coding: utf-8 -*-
"""
Parcel-size lookup for WS targeted sites, from free public GIS only.

Pipeline:
  A. county/state for each point  -> US Census Geocoder (free, no key)
  B. parcel service per county    -> known registry, else ArcGIS Online auto-discovery
  C. point-in-polygon query       -> ArcGIS REST /query, geometry returned as GeoJSON
  D. area                         -> geodesic area computed locally (projection-independent)

Every output row records the exact service URL used as its source.
"""
import csv, json, math, os, re, sys, time, urllib.parse, urllib.request

UA = {'User-Agent': 'Mozilla/5.0 (TBDI parcel research)'}
SCRATCH = os.path.dirname(os.path.abspath(__file__))
SITES_CSV = os.path.join(SCRATCH, 'ws_sites.csv')
CACHE = os.path.join(SCRATCH, 'parcel_cache.json')


def fetch(url, timeout=45):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', 'replace')


def jget(url, timeout=45):
    try:
        return json.loads(fetch(url, timeout))
    except Exception as e:
        return {'__error__': f'{type(e).__name__}: {str(e)[:160]}'}


# ---------------------------------------------------------------- geodesic area
def ring_area(ring):
    """Spherical excess area of a WGS84 lon/lat ring, in square meters."""
    R = 6378137.0
    if ring[0] != ring[-1]:
        ring = ring + [ring[0]]
    tot = 0.0
    for i in range(len(ring) - 1):
        x1, y1 = math.radians(ring[i][0]), math.radians(ring[i][1])
        x2, y2 = math.radians(ring[i + 1][0]), math.radians(ring[i + 1][1])
        tot += (x2 - x1) * (2 + math.sin(y1) + math.sin(y2))
    return abs(tot * R * R / 2.0)


def geojson_area_m2(geom):
    """Outer rings minus holes, for Polygon or MultiPolygon."""
    if not geom:
        return None
    t, c = geom.get('type'), geom.get('coordinates')
    polys = [c] if t == 'Polygon' else (c if t == 'MultiPolygon' else None)
    if polys is None:
        return None
    total = 0.0
    for poly in polys:
        for i, ring in enumerate(poly):
            a = ring_area(ring)
            total += a if i == 0 else -a
    return total


# ---------------------------------------------------------------- A. county
def census_county(lat, lng):
    url = ('https://geocoding.geo.census.gov/geocoder/geographies/coordinates'
           f'?x={lng}&y={lat}&benchmark=Public_AR_Current&vintage=Current_Current'
           '&layers=Counties&format=json')
    r = jget(url)
    try:
        c = r['result']['geographies']['Counties'][0]
        return c['BASENAME'], c['STATE'], c['COUNTY']
    except Exception:
        return None, None, None


STATE_FIPS = {'01': 'AL', '05': 'AR', '12': 'FL', '13': 'GA', '19': 'IA', '21': 'KY',
              '37': 'NC', '39': 'OH', '45': 'SC', '47': 'TN', '48': 'TX', '51': 'VA'}


# ---------------------------------------------------------------- B. services
# Known-good statewide services (verified by hand before this run).
STATEWIDE = {
    'OH': ('https://services2.arcgis.com/MlJ0G8iWUyC7jAmu/arcgis/rest/services/'
           'OhioStatewidePacels_full_view/FeatureServer/0'),
}

# Candidate NC layers to test at runtime (root reported no layer list).
NC_CANDIDATES = [
    'https://services.nconemap.gov/secure/rest/services/NC1Map_Parcels/FeatureServer/0',
    'https://services.nconemap.gov/secure/rest/services/NC1Map_Parcels/FeatureServer/1',
    'https://services.nconemap.gov/secure/rest/services/NC1Map_Parcels/MapServer/0',
    'https://services.nconemap.gov/secure/rest/services/NC1Map_Parcels/MapServer/1',
]

PARCEL_WORDS = re.compile(r'parcel|cadastr|tax\s*map|property', re.I)
BAD_WORDS = re.compile(r'zoning|flood|soil|address|road|boundar|district|school|voting|'
                       r'wetland|contour|building|point', re.I)


def agol_candidates(county, state_abbr, limit=12):
    """Search ArcGIS Online for a parcel feature/map service in this county."""
    out = []
    queries = [
        f'{county} County {state_abbr} parcels',
        f'{county} {state_abbr} tax parcels',
    ]
    for q in queries:
        url = ('https://www.arcgis.com/sharing/rest/search?f=json&num=%d&q=' % limit
               + urllib.parse.quote(q + ' (type:"Feature Service" OR type:"Map Service")'))
        r = jget(url)
        for it in r.get('results', []) or []:
            u, title = it.get('url'), it.get('title') or ''
            if not u or not PARCEL_WORDS.search(title) or BAD_WORDS.search(title):
                continue
            if '/FeatureServer' in u or '/MapServer' in u:
                out.append((title, u))
    seen, ded = set(), []
    for t, u in out:
        if u not in seen:
            seen.add(u); ded.append((t, u))
    return ded


def layer_urls(service_url):
    """Expand a service root into candidate polygon layer URLs."""
    if re.search(r'/(FeatureServer|MapServer)/\d+$', service_url):
        return [service_url]
    meta = jget(service_url + '?f=json')
    lyrs = meta.get('layers') or []
    urls = []
    for L in lyrs:
        gt = (L.get('geometryType') or '')
        nm = (L.get('name') or '')
        if gt and 'Polygon' not in gt:
            continue
        if BAD_WORDS.search(nm):
            continue
        urls.append(f"{service_url}/{L.get('id')}")
    if not urls:
        urls = [f'{service_url}/0', f'{service_url}/1']
    return urls[:6]


# ---------------------------------------------------------------- C. query
def query_point(layer_url, lat, lng, timeout=45):
    geom = json.dumps({'x': lng, 'y': lat, 'spatialReference': {'wkid': 4326}})
    url = (layer_url + '/query?f=geojson&outFields=*&returnGeometry=true'
           '&geometryType=esriGeometryPoint&inSR=4326&outSR=4326'
           '&spatialRel=esriSpatialRelIntersects&geometry=' + urllib.parse.quote(geom))
    r = jget(url, timeout)
    if '__error__' in r or 'error' in r:
        return None, (r.get('__error__') or json.dumps(r.get('error'))[:120])
    feats = r.get('features') or []
    if not feats:
        return None, 'no feature at point'
    return feats[0], None


ACRE_KEYS = re.compile(r'^(gis_?)?(calc_?)?acre', re.I)
ID_KEYS = re.compile(r'parcel.*(id|no|num)|^(pin|apn|parid|ppin|taxid|gpin)', re.I)
OWNER_KEYS = re.compile(r'owner|ownname|own1|deed', re.I)
ADDR_KEYS = re.compile(r'(site|situs|prop|phys).*addr|^address|^saddr', re.I)


def pick(props, pattern):
    for k, v in props.items():
        if pattern.search(k) and v not in (None, '', ' ', 0):
            return str(v).strip()
    return ''


# ---------------------------------------------------------------- main
def main():
    sites = list(csv.DictReader(open(SITES_CSV, encoding='utf-8')))
    # unique sites (Top Sites is a subset of Interesting Sites)
    uniq, seen = [], set()
    for s in sites:
        key = (s['name'], s['lat'], s['lng'])
        if key in seen:
            continue
        seen.add(key)
        s['tier'] = 'Top Site' if any(
            x['name'] == s['name'] and x['folder'] == 'Top Sites' for x in sites) else 'Interesting'
        uniq.append(s)
    print(f'unique sites: {len(uniq)}')

    cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
    svc_cache = cache.setdefault('services', {})   # "COUNTY,ST" -> layer url or ""
    rows = []

    for i, s in enumerate(uniq, 1):
        lat, lng = float(s['lat']), float(s['lng'])
        county, sf, cf = census_county(lat, lng)
        st = STATE_FIPS.get(sf or '', '')
        ckey = f'{county},{st}'
        print(f"[{i:2}/{len(uniq)}] {s['name']:10} {county} Co, {st}", flush=True)

        # --- resolve a layer for this county
        layer = svc_cache.get(ckey)
        tried = []
        if layer is None:
            cands = []
            if st in STATEWIDE:
                cands.append(('STATEWIDE', STATEWIDE[st]))
            if st == 'NC':
                cands += [('NC OneMap', u) for u in NC_CANDIDATES]
            for title, svc in agol_candidates(county or '', st):
                for lu in layer_urls(svc):
                    cands.append((title, lu))
            layer = ''
            for title, lu in cands[:14]:
                feat, err = query_point(lu, lat, lng)
                tried.append(f'{lu} -> {"OK" if feat else err}')
                if feat:
                    layer = lu
                    break
            svc_cache[ckey] = layer
            json.dump(cache, open(CACHE, 'w'), indent=1)

        rec = dict(clli=s['name'], address=s['address'], tier=s['tier'],
                   lat=lat, lng=lng, county=county or '', state=st)

        if not layer:
            rec.update(status='NO SERVICE FOUND', source=''); rows.append(rec)
            print('        no parcel service found'); continue

        feat, err = query_point(layer, lat, lng)
        if not feat:
            rec.update(status=f'NO PARCEL AT POINT ({err})', source=layer); rows.append(rec)
            print('        no parcel at point'); continue

        props = feat.get('properties') or {}
        m2 = geojson_area_m2(feat.get('geometry'))
        stated = pick(props, ACRE_KEYS)
        rec.update(
            status='ok',
            parcel_id=pick(props, ID_KEYS),
            owner=pick(props, OWNER_KEYS),
            parcel_address=pick(props, ADDR_KEYS),
            acres_gis=round(m2 / 4046.856, 4) if m2 else '',
            sqft_gis=round(m2 * 10.7639) if m2 else '',
            m2_gis=round(m2, 1) if m2 else '',
            acres_stated=stated,
            source=layer,
        )
        rows.append(rec)
        print(f"        {rec['acres_gis']} ac | id={rec['parcel_id']} | {rec['owner'][:32]}")

    cols = ['clli', 'address', 'tier', 'lat', 'lng', 'county', 'state', 'status',
            'parcel_id', 'owner', 'parcel_address', 'acres_gis', 'sqft_gis', 'm2_gis',
            'acres_stated', 'source']
    out = os.path.join(SCRATCH, 'parcel_results.csv')
    with open(out, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction='ignore')
        w.writeheader()
        for r in rows:
            w.writerow(r)
    ok = sum(1 for r in rows if r.get('status') == 'ok')
    print(f'\nDONE: {ok}/{len(rows)} resolved -> {out}')


if __name__ == '__main__':
    main()
