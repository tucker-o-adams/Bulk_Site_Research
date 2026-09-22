# -*- coding: utf-8 -*-
"""Propose a parcel service for a county. Never writes the registry itself.

    .venv_fema/Scripts/python.exe scripts/bulk/reference/discover_parcel_service.py \
        --geoid 17197 [--county "Will County" --state IL] [--probe 41.45,-88.08]

Writes `data/reference/parcel-proposals/<geoid>.json` for a person to review.
Nothing here is used by a run until someone moves the chosen service into
`data/reference/parcel-services.json`.

Why propose and not register (ported argument from tbdi-pasa
`tools/admin/county_discover.py`): the same search that finds the county GIS
org also finds a parcel layer owned by a private individual, and a county org
may publish both `Parcels` and `Parcels_Public` with nothing in the metadata
saying which the assessor treats as current. A script that picked one would be
guessing, and the guess would arrive wearing a citation. A wrong parcel
silently poisons buildable acres, the flood and wetland clips, and the map
outline. Cheap to review, expensive to get wrong.

Prior art first (added 2026-09-22, see BACKLOG "Parcel prior-art research"):

  0. **OpenAddresses** — its `sources/us/<st>/<county>.json` files carry a person-
     curated `parcels` layer URL for 1,140 US sources (GA 94, AL 38, TX 24, ...),
     keyed by Census GEOID. Checked before any search. The URLs rot (7 of 17
     checked in GA were dead), so each is probed, and its host is enumerated
     either way — a renamed service usually still sits on the same org.
  0a. **NSGIC Parcel Portal** (2025) — one row per county: whether parcels are
     public (`PRCLACCS` Y/I/N), the steward, and view/download/API URLs. Its
     status is written into the proposal for the reviewer; an API URL becomes a
     candidate.

Then the searches, because AGOL indexes only what a publisher registered there and a
county that self-hosts and never registered is invisible to a search:

  1. **AGOL search** for items whose title names parcels.
  1a. **ArcGIS Hub dataset API** (`hub.arcgis.com/api/v3/datasets`) — a different
     index that reaches open-data portals AGOL item search does not. It is how
     Nebraska's statewide parcels and several state clearinghouse layers surface.
  2. **Web maps and apps** — a county that never registered a *service* has very
     often published a *viewer*. Searching AGOL for the county's web maps and
     apps and reading each item's `data` yields the `url` of every operational
     layer it draws, which is the county's real parcel service whatever host it
     sits on (Tulsa County's parcels are served by INCOG, a regional council).
  3. **Host enumeration** — take the `/rest/services` root of any service URL
     found (or one given with `--server`) and list every service on it, folders
     included. This is what reaches a county's own server. Ported from
     tbdi-pasa `county_discover.org_root` / `enumerate_services`, whose comments
     record why: Williamson County TX publishes from `gis.wilco.org/ags/rest/
     services` (instance named `ags`, no org segment) and its appraisal district
     from a separate host; Henrico County VA serves plain http and refuses https;
     an on-premises server often lists zero services at the root and everything
     under folders, so a root-only listing looks like a publisher with nothing.

Ranking: owner first (an organisation whose name looks like the county or state
beats a well-titled layer owned by an individual), then layer name, then whether
the fields a parcel needs are present, then whether a probe point returns
exactly one polygon.
"""
import argparse, json, os, re, sys, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from geom import arcgis_query                     # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
OUT_DIR = os.path.join(ROOT, 'data', 'reference', 'parcel-proposals')
AGOL = 'https://www.arcgis.com/sharing/rest/search'
# Esri's own basemaps answer a point query anywhere on earth and are never parcels.
BASEMAP_HOSTS = ('services.arcgisonline.com', 'basemaps.arcgis.com', 'tiles.arcgis.com')
UA = {'User-Agent': 'Mozilla/5.0 (TBDI bulk site research)'}
# Short, ambiguous names are matched exactly only: 'pid' as a substring matches
# ZIP_ID and would have registered a ZIP-code layer as parcels (Boyd County KY, 2026-09-22).
EXACT_ONLY = {'pin', 'apn', 'pid', 'zip', 'gpin', 'taxid', 'map_id'}
FIELD_HINTS = {'apn': ('parcel_id', 'parcelid', 'parcelno', 'parcel_no', 'parcelnumb', 'parcelnumber',
                       'accountno', 'acctnum', 'pin', 'apn', 'pid', 'gpin', 'taxid'),
               'owner': ('owner', 'ownername', 'owner_name', 'own_name', 'deeded_owner', 'taxpayer'),
               'acres': ('acres', 'gis_acres', 'acreage', 'calc_acres', 'deed_acres', 'area_acres'),
               'address': ('situs', 'address', 'site_addr', 'prop_addr', 'full_address', 'location')}


def g(url, timeout=60):
    try:
        return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read())
    except Exception as e:
        return {'__error__': f'{type(e).__name__}: {str(e)[:140]}'}


def looks_official(owner, county, state):
    o = (owner or '').lower()
    bits = [b for b in re.split(r'\W+', (county or '').lower()) if b and b not in ('county', 'parish')]
    return (any(b in o for b in bits) or (state or '').lower() in o
            or any(k in o for k in ('gis', 'county', 'city of', 'state of', 'dot', 'planning')))


def score(item, county, state):
    s, why = 0, []
    if looks_official(item.get('owner'), county, state):
        s += 50; why.append(f"owner {item.get('owner')!r} looks official")
    else:
        why.append(f"owner {item.get('owner')!r} not obviously the authority")
    title = (item.get('title') or '').lower()
    if 'parcel' in title:
        s += 20; why.append('title names parcels')
    if any(k in title for k in ('tax', 'cadastral', 'property')):
        s += 5
    if any(k in title for k in ('historic', 'archive', 'old', 'test', 'draft', '2019', '2020')):
        s -= 25; why.append('title suggests an archive or draft')
    return s, why


def probe_layer(base, layer, probe):
    """Fields, and what a point query returns. Returns (meta, probe_result)."""
    m = g(f'{base}/{layer}?f=json')
    fields = [f['name'] for f in m.get('fields', [])] if isinstance(m, dict) else []
    res = {}
    if probe and fields:
        lat, lng = probe
        r = g(arcgis_query(f'{base}/{layer}', lat, lng, '*', geometry=False))
        res = {'features': len(r.get('features', []))} if 'features' in r else {'error': str(r)[:160]}
    # exact name first, then substring — 'ParcelNo' and 'PARCEL_ID' must both match,
    # while 'PAR_TYPE' must not
    def best(hints, extra=()):
        norm = lambda x: x.lower().replace('_', '').replace(' ', '')
        for h in hints:
            for f in fields:
                if norm(f) == norm(h):
                    return f
        for h in hints:
            if h in EXACT_ONLY:
                continue                      # exact match already tried; substring is unsafe
            for f in fields:
                if norm(h) in norm(f):
                    return f
        for k in extra:
            for f in fields:
                if k in norm(f):
                    return f
        return None

    guess = {'apn': best(FIELD_HINTS['apn'], ('parcelno', 'parcelnum', 'parcelid', 'accountno')),
             'owner': best(FIELD_HINTS['owner']),
             'acres': best(FIELD_HINTS['acres']),
             'address': best(FIELD_HINTS['address'])}
    return {'name': m.get('name'), 'geometryType': m.get('geometryType'), 'fields': fields,
            'field_guess': guess, 'probe': res}


def layer_points(pl):
    """Points a probed layer earns, and why. A layer that answers at the point but has no
    parcel-like field is a basemap or a boundary layer, not parcels: the probe is only
    evidence when the attributes are too."""
    pts, why = 0, []
    fg = pl.get('field_guess') or {}
    has_apn, has_attr = bool(fg.get('apn')), bool(fg.get('apn') or fg.get('owner') or fg.get('acres'))
    if (pl.get('geometryType') or '') not in ('esriGeometryPolygon', ''):
        return -40, [f"geometry is {pl.get('geometryType')}, not polygons"]
    if has_apn:
        pts += 15; why.append(f"has a parcel-id field ({fg['apn']})")
    if fg.get('owner'):
        pts += 5
    if fg.get('acres'):
        pts += 5
    n = (pl.get('probe') or {}).get('features')
    if n == 1 and has_attr:
        pts += 30; why.append('exactly one polygon at the probe point')
    elif n == 1 and not has_attr:
        pts -= 30; why.append('answers at the probe point but carries no parcel attributes - a basemap or boundary layer')
    elif n == 0:
        pts -= 20; why.append('no feature at the probe point (wrong county, or a filtered extract)')
    elif isinstance(n, int) and n > 1:
        why.append(f'{n} features at the probe point')
    return pts, why


def org_root(url):
    """The `/rest/services` root for a service URL, hosted or on-premises.

    Accepts http as well as https (Henrico County VA refuses https) and any
    instance name (`/arcgis/`, `/ags/`, `/server/`), with or without an org
    segment. Ported from tbdi-pasa.
    """
    m = re.match(r'(https?://[^/]+(?:/[^/?#]+)*?/rest/services)(?:/|$)', url or '')
    return m.group(1) if m else None


def enumerate_services(root):
    """Every FeatureServer/MapServer under a root, folders included.

    An on-premises server usually lists nothing at the root and everything under
    folders, so a root-only listing reads as "publisher with nothing to offer".
    """
    j = g(root + '?f=json', timeout=90)
    if j.get('__error__'):
        return [], j['__error__']
    if j.get('status') == 'error' or j.get('error'):
        return [], '; '.join(j.get('messages') or [str(j.get('error'))[:80]])
    out = [(e['name'], e.get('type')) for e in j.get('services', [])]
    for folder in j.get('folders', []):
        fj = g(f'{root}/{folder}?f=json', timeout=90)
        if fj.get('__error__'):
            continue
        out += [(e['name'], e.get('type')) for e in fj.get('services', [])]
    # ArcGIS Online lists a hosted layer twice, as FeatureServer and as MapServer; the hosted
    # MapServer answers /query with "Invalid URL", which scored real parcel layers as broken
    # (the Charlton GA and UT-Chattanooga layers, 2026-09-22). Keep the FeatureServer.
    feature = {n for n, k in out if k == 'FeatureServer'}
    return [(n, k) for n, k in out if k == 'FeatureServer' or (k == 'MapServer' and n not in feature)], None


OA_DIR = 'https://api.github.com/repos/openaddresses/openaddresses/contents/sources/us/{st}'
OA_RAW = 'https://raw.githubusercontent.com/openaddresses/openaddresses/master/sources/us/{st}/{name}'
NSGIC = 'https://services5.arcgis.com/fmKivMCp6fwbWbeE/arcgis/rest/services/2025_NSGIC_Parcel_Portal/FeatureServer/0'
USPS = {'01': 'al', '02': 'ak', '04': 'az', '05': 'ar', '06': 'ca', '08': 'co', '09': 'ct', '10': 'de', '11': 'dc',
        '12': 'fl', '13': 'ga', '15': 'hi', '16': 'id', '17': 'il', '18': 'in', '19': 'ia', '20': 'ks', '21': 'ky',
        '22': 'la', '23': 'me', '24': 'md', '25': 'ma', '26': 'mi', '27': 'mn', '28': 'ms', '29': 'mo', '30': 'mt',
        '31': 'ne', '32': 'nv', '33': 'nh', '34': 'nj', '35': 'nm', '36': 'ny', '37': 'nc', '38': 'nd', '39': 'oh',
        '40': 'ok', '41': 'or', '42': 'pa', '44': 'ri', '45': 'sc', '46': 'sd', '47': 'tn', '48': 'tx', '49': 'ut',
        '50': 'vt', '51': 'va', '53': 'wa', '54': 'wv', '55': 'wi', '56': 'wy'}


def letters(s):
    return re.sub(r'[^a-z]', '', (s or '').lower().replace(' county', '').replace(' parish', ''))


def layer_candidate(url, probe, score, why, title, owner, typ, item=None):
    """Probe one layer URL (…/FeatureServer/3) and wrap it as a scored candidate, or None if dead."""
    base, lid = url.rstrip('/').rsplit('/', 1)
    if not lid.isdigit():
        base, lid = url.rstrip('/'), 0
    meta = g(f'{base}/{lid}?f=json')
    if meta.get('__error__') or meta.get('error'):
        print(f'    dead: {url[:90]} ({meta.get("__error__") or str(meta.get("error"))[:60]})')
        return None
    pl = probe_layer(base, int(lid), probe)
    pts, pwhy = layer_points(pl)
    return {'score': score + pts, 'why': why + pwhy, 'title': title, 'owner': owner, 'type': typ,
            'url': base, 'modified': None, 'item': item,
            'layers': [{'layer': int(lid), 'layer_name': pl.get('name'), 'points': pts, **pl}]}


def from_openaddresses(geoid, probe):
    """Candidates from OpenAddresses' person-curated parcel sources for this county (and the
    state's statewide file). Returns (candidates, urls_seen) — dead URLs still name a host
    worth enumerating."""
    st = USPS.get(str(geoid)[:2])
    if not st:
        return [], []
    listing = g(OA_DIR.format(st=st))
    names = [x['name'] for x in listing] if isinstance(listing, list) else []
    if not names:
        print(f'  openaddresses: directory listing unavailable ({str(listing)[:80]})')
        return [], []
    # The county file is usually named for the county ('ben_hill.json', 'lasalle.json'); its
    # coverage GEOID is what decides. Scan every file only when no name matches.
    src0 = g(f'https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/State_County/MapServer/1/query'
             f'?f=json&where=GEOID%3D%27{geoid}%27&outFields=BASENAME&returnGeometry=false')
    base = letters(((src0.get('features') or [{}])[0].get('attributes') or {}).get('BASENAME'))
    named = [n for n in names if letters(n[:-5]) == base]
    order = [n for n in names if n == 'statewide.json'] + (named or [n for n in names if n.endswith('.json')
                                                                   and not n.startswith('city_of_') and n != 'statewide.json'])
    cands, seen, found_county = [], [], False
    for name in order:
        if found_county and name != 'statewide.json':
            break
        src = g(OA_RAW.format(st=st, name=name))
        if name == 'statewide.json':
            scope = 'statewide'
        elif ((src.get('coverage') or {}).get('US Census') or {}).get('geoid') != str(geoid):
            continue
        else:
            scope, found_county = 'county', True
        for lyr in ((src or {}).get('layers') or {}).get('parcels') or []:
            u = lyr.get('data')
            if not u or lyr.get('protocol') != 'ESRI':
                continue
            seen.append(u)
            print(f'  openaddresses {st}/{name} parcels: {u}')
            c = layer_candidate(u, probe, 55, [f'listed as parcels in OpenAddresses sources/us/{st}/{name} '
                                                f'({scope}; person-curated)'],
                                f'OA {st}/{name} {lyr.get("name", "")}', u.split('/')[2], f'from openaddresses ({scope})',
                                item=f'https://github.com/openaddresses/openaddresses/blob/master/sources/us/{st}/{name}')
            if c:
                pid = (lyr.get('conform') or {}).get('pid')
                l0 = c['layers'][0]
                if isinstance(pid, str) and pid in l0['fields']:
                    l0['field_guess']['apn'] = pid       # OA's curated mapping beats our name heuristics
                cands.append(c)
    print(f'  openaddresses candidates: {len(cands)} (from {len(seen)} listed URLs)')
    return cands, seen


def nsgic_status(geoid, probe):
    """The county's row in the NSGIC 2025 Parcel Portal, and a candidate for its API URL if any."""
    r = g(f'{NSGIC}/query?f=json&where=GEOID%3D%27{geoid}%27&outFields=*&returnGeometry=false')
    feats = r.get('features') or []
    if not feats:
        print(f'  nsgic: no row for {geoid} ({r.get("__error__") or r.get("error") or "not found"})')
        return None, []
    a = feats[0]['attributes']
    status = {k: a.get(k) for k in ('PRCLACCS', 'PROGRAM', 'STEWARD', 'VIEWURL', 'DLDURL', 'APIURL', 'UPDATEFREQ')}
    print(f"  nsgic: access={a.get('PRCLACCS')} steward={a.get('STEWARD')!r} api={a.get('APIURL')!r}")
    api = a.get('APIURL') or ''
    cands = []
    if '/rest/services' in api:
        c = layer_candidate(api, probe, 50, [f"NSGIC 2025 Parcel Portal API URL (steward {a.get('STEWARD')!r})"],
                            'NSGIC API URL', api.split('/')[2], 'from nsgic')
        if c:
            cands.append(c)
    return status, cands


HUB = 'https://hub.arcgis.com/api/v3/datasets'


def from_hub(county, state, probe, limit=12):
    """Candidates from the ArcGIS Hub dataset index (open-data portals, not just AGOL items)."""
    out = []
    for q in (f'{county} {state or ""} parcels', f'{state or ""} statewide parcels'):
        r = g(f'{HUB}?q={urllib.parse.quote(q)}&page[size]={limit}')
        if r.get('__error__'):
            print(f'  hub search failed: {r["__error__"]}')
            continue
        for d in (r.get('data') or []):
            a = d.get('attributes') or {}
            u, nm = a.get('url'), str(a.get('name') or '')
            if not u or not any(k in nm.lower() for k in ('parcel', 'cadas', 'property')):
                continue
            if any(h in u for h in BASEMAP_HOSTS) or any(c.get('url') == u for c in out):
                continue
            pl = probe_layer(u.rsplit('/', 1)[0], u.rsplit('/', 1)[-1], probe) if u.rstrip('/').split('/')[-1].isdigit()                 else probe_layer(u, 0, probe)
            pts, why = layer_points(pl)
            src = a.get('source') or a.get('orgContactEmail') or ''
            c = {'score': 45 + pts, 'why': [f'ArcGIS Hub dataset {nm!r} (source {src})'] + why,
                 'title': nm, 'owner': str(src)[:40], 'type': 'from hub', 'url': u, 'modified': a.get('modified'),
                 'item': a.get('landingPage'),
                 'layers': [{'layer': 0, 'layer_name': nm, 'points': pts, **pl}]}
            out.append(c)
    print(f'  hub candidates: {len(out)}')
    return out


WEBMAP_TYPES = ('Web Map', 'Web Mapping Application', 'Web Experience', 'Instant App', 'Dashboard')


def layer_urls_from_item(item_id, depth=0, seen=None):
    """Every /rest/services URL an AGOL web map or app references, following nested items once."""
    seen = seen if seen is not None else set()
    if item_id in seen or depth > 1:
        return []
    seen.add(item_id)
    d = g(f'https://www.arcgis.com/sharing/rest/content/items/{item_id}/data?f=json')
    out, nested = [], []

    def walk(o):
        if isinstance(o, dict):
            u = o.get('url')
            if isinstance(u, str) and '/rest/services' in u:
                out.append(u)
            iid = o.get('itemId')
            if isinstance(iid, str) and iid != item_id:
                nested.append(iid)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(d)
    for iid in nested[:6]:
        out += layer_urls_from_item(iid, depth + 1, seen)
    return out


def from_webmaps(county, state, probe, limit=8):
    """Candidates from the layer URLs inside the county's own web maps and apps."""
    q = urllib.parse.quote(f'{county} {state or ""} type:({" OR ".join(chr(34) + t + chr(34) for t in WEBMAP_TYPES)})')
    res = g(f'{AGOL}?f=json&num={limit}&sortField=numviews&sortOrder=desc&q={q}')
    items = res.get('results') or []
    print(f'  web maps/apps found: {len(items)}')
    urls, by_url = [], {}
    for it in items:
        for u in layer_urls_from_item(it.get('id')):
            base = u.rstrip('/')
            if base not in by_url:
                by_url[base] = it
                urls.append(base)
    urls = [u for u in urls if not any(h in u for h in BASEMAP_HOSTS)]
    parcelish = [u for u in urls if any(k in u.lower() for k in ('parcel', 'cadas', 'property', 'taxlot'))]
    print(f'  layer URLs referenced: {len(urls)} ({len(parcelish)} parcel-ish)')
    cands = []
    for u in (parcelish or urls)[:12]:
        meta = g(u + '?f=json')
        if meta.get('__error__') or meta.get('error'):
            print(f'    dead: {u[:78]} ({meta.get("__error__") or "service error"})')
            continue
        layers = [(l['id'], l['name']) for l in (meta.get('layers') or [])
                  if any(k in (l['name'] or '').lower() for k in ('parcel', 'cadas', 'property'))]
        if not layers and meta.get('geometryType'):        # the URL already names a layer
            layers = [(None, meta.get('name'))]
        elif not layers:
            layers = [(l['id'], l['name']) for l in (meta.get('layers') or [])][:2]
        src = by_url.get(u, {})
        c = {'score': 45, 'why': [f'referenced by the web map {src.get("title", "?")!r} (owner {src.get("owner")})'],
             'title': meta.get('name') or u.rsplit('/', 2)[-2], 'owner': u.split('/')[2], 'type': 'from web map',
             'url': u if layers and layers[0][0] is None else u, 'modified': None,
             'item': f"https://www.arcgis.com/home/item.html?id={src.get('id')}" if src.get('id') else None, 'layers': []}
        best_pts = None
        for lid, lname in layers[:3]:
            target = u if lid is None else f'{u}/{lid}'
            pl = probe_layer(target.rsplit('/', 1)[0] if lid is None else u, target.rsplit('/', 1)[-1] if lid is None else lid, probe)
            pts, why = layer_points(pl)
            if best_pts is None or pts > best_pts:      # score the service by its best layer, not the sum
                best_pts = pts
                c['why'] = c['why'][:1] + why
            c['layers'].append({'layer': lid if lid is not None else int(target.rsplit('/', 1)[-1]),
                                'layer_name': lname, 'points': pts, **pl})
        c['score'] += best_pts or 0
        if c['layers']:
            cands.append(c)
    return cands


def from_host(root, county, state, probe):
    """Candidates from every parcel-ish service on one host."""
    svcs, err = enumerate_services(root)
    if err:
        print(f'  host {root}: {err}')
        return []
    print(f'  host {root}: {len(svcs)} services')
    cands = []
    for name, kind in svcs:
        short = name.split('/')[-1].lower()
        if not any(k in short for k in ('parcel', 'cadas', 'property', 'taxlot', 'landrecord')):
            continue
        url = f'{root}/{name}/{kind}'
        meta = g(url + '?f=json')
        layers = [(l['id'], l['name']) for l in (meta.get('layers') or [])
                  if any(k in (l['name'] or '').lower() for k in ('parcel', 'cadas', 'property'))] or                  [(l['id'], l['name']) for l in (meta.get('layers') or [])][:2]
        c = {'score': 50, 'why': [f'published by the host {root.split("/")[2]} itself'],
             'title': name, 'owner': root.split('/')[2], 'type': kind, 'url': url,
             'modified': None, 'item': None, 'layers': []}
        if any(k in short for k in ('historic', 'archive', 'old')):
            c['score'] -= 40; c['why'].append('name suggests an archive')
        best_pts = None
        for lid, lname in layers[:3]:
            pl = probe_layer(url, lid, probe)
            pts, why = layer_points(pl)
            if best_pts is None or pts > best_pts:
                best_pts = pts
                c['why'] = c['why'][:1] + why
            c['layers'].append({'layer': lid, 'layer_name': lname, 'points': pts, **pl})
        c['score'] += best_pts or 0
        if c['layers']:
            cands.append(c)
    return cands


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--geoid', required=True)
    ap.add_argument('--county'); ap.add_argument('--state')
    ap.add_argument('--probe', help='lat,lng inside the county to test a point query')
    ap.add_argument('--server', action='append', default=[],
                    help='a known ArcGIS host or service URL to enumerate (repeatable); use when AGOL has nothing')
    a = ap.parse_args()
    probe = tuple(float(x) for x in a.probe.split(',')) if a.probe else None
    county, state = a.county, a.state
    if not county:
        r = g(f'https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/State_County/MapServer/1/query'
              f'?f=json&where=GEOID%3D%27{a.geoid}%27&outFields=NAME,STATE,BASENAME&returnGeometry=false')
        at = (r.get('features') or [{}])[0].get('attributes', {})
        county = at.get('NAME') or at.get('BASENAME')
    state = state or (USPS.get(a.geoid[:2]) or '').upper() or None

    # ---- prior art first: OpenAddresses' curated parcel sources, and NSGIC's county status
    oa_cands, oa_urls = from_openaddresses(a.geoid, probe)
    nsgic, ns_cands = nsgic_status(a.geoid, probe)

    q = urllib.parse.quote(f'{county} {state or ""} parcels type:("Feature Service" OR "Map Service")')
    res = g(f'{AGOL}?f=json&num=40&sortField=numviews&sortOrder=desc&q={q}')
    if res.get('__error__') or res.get('error'):
        print(f'AGOL search failed: {res.get("__error__") or res.get("error")}', file=sys.stderr)
    cands = []
    for it in res.get('results', []):
        s, why = score(it, county, state)
        cands.append({'score': s, 'why': why, 'title': it.get('title'), 'owner': it.get('owner'),
                      'type': it.get('type'), 'url': it.get('url'), 'modified': it.get('modified'),
                      'item': f"https://www.arcgis.com/home/item.html?id={it.get('id')}"})
    cands.sort(key=lambda c: -c['score'])
    for c in cands[:6]:
        if not c.get('url'):
            continue
        meta = g(c['url'] + '?f=json')
        layers = [(l['id'], l['name']) for l in (meta.get('layers') or []) if 'parcel' in (l['name'] or '').lower()] \
            or [(l['id'], l['name']) for l in (meta.get('layers') or [])][:3]
        c['layers'] = []
        for lid, lname in layers[:3]:
            pl = probe_layer(c['url'], lid, probe)
            if pl['field_guess'].get('apn'):
                c['score'] += 15
            if pl.get('probe', {}).get('features') == 1:
                c['score'] += 15
            c['layers'].append({'layer': lid, 'layer_name': lname, **pl})
    cands += oa_cands + ns_cands

    # ---- ArcGIS Hub index
    cands += from_hub(county, state, probe)

    # ---- web maps and apps: the county's viewers name their own layers
    cands += from_webmaps(county, state, probe)

    # ---- host enumeration: the AGOL hits' own roots, plus anything --server named
    # OpenAddresses URLs come first even when dead: a renamed service usually sits on the same host.
    roots = []
    for u in a.server + oa_urls + [c.get('url') for c in cands if c.get('url')]:
        r = org_root(u)
        if r and r not in roots:
            roots.append(r)
    for r in roots[:6]:
        cands += from_host(r, county, state, probe)

    cands.sort(key=lambda c: -c['score'])
    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, f'{a.geoid}.json')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump({'geoid': a.geoid, 'county': county, 'state': state, 'probe': a.probe,
                   'note': 'PROPOSAL ONLY - a person reviews this and moves the chosen service into parcel-services.json. '
                           'Nothing here is used by a run.',
                   'nsgic_2025': nsgic,
                   'openaddresses_urls': oa_urls,
                   'candidates': cands[:10]}, f, indent=1)
    print(f'wrote {out}')
    for c in cands[:5]:
        print(f"  {c['score']:4}  {c['title'][:52]:52} owner={c['owner'][:22]:22} layers="
              f"{[(l['layer'], l['layer_name'], l['field_guess'].get('apn'), l.get('probe')) for l in c.get('layers', [])]}")
    best = cands[0] if cands else None
    if not best or best['score'] < 65 or not any(l.get('probe', {}).get('features') == 1 for l in (best.get('layers') or [])):
        print('\nNothing here looks like the county itself answering at the probe point. Before registering any of'
              '\nthese, check the county GIS department\'s own ArcGIS server — commonly'
              '\n  https://gis.<county>.<state>.us/arcgis/rest/services   or   https://maps.<county>gov.../arcgis/rest/services'
              '\nA layer owned by a soil district, a consultant, or another state\'s county is a copy of unknown age.')
    print('\nReview one, then add it to data/reference/parcel-services.json under "counties".')


if __name__ == '__main__':
    main()
