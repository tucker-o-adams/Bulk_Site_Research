# -*- coding: utf-8 -*-
"""Look for a *statewide* parcel service, state by state. The highest-value move.

    .venv_fema/Scripts/python.exe scripts/bulk/reference/sweep_statewide_parcels.py \
        --states IA,GA,KY,TX,OK,AR,AL --probes-from Outputs/windstream-200/sites.csv

One statewide hit covers every county in the state at once: Ohio's took minutes
and resolved 35 Windstream sites, Florida's 8. A county-by-county hunt costs a
person minutes each for one or two sites. So sweep the states first, always.

Three indexes are checked for each state, because each reaches publishers the
others miss:
  * **ArcGIS Hub datasets** — open-data portals (this is how Nebraska's statewide
    parcel service surfaces)
  * **AGOL item search** — what a publisher registered on ArcGIS Online
  * **known state GIS hosts** — a state that self-hosts and never registered

Every candidate is probed at real points inside the state (taken from a batch's
`sites.csv` with `--probes-from`, or given with `--probe`). A candidate counts
only when it returns exactly one polygon **and** carries parcel attributes: a
state boundary layer answers a point query too.

Output is a proposal per state in `data/reference/statewide-proposals/<ST>.json`.
Nothing is registered: a person reviews and moves the winner into
`data/reference/parcel-services.json` under `statewide`.
"""
import argparse, csv, json, os, sys, urllib.parse, urllib.request
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from geom import arcgis_query                                  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
OUT_DIR = os.path.join(ROOT, 'data', 'reference', 'statewide-proposals')
HUB = 'https://hub.arcgis.com/api/v3/datasets'
AGOL = 'https://www.arcgis.com/sharing/rest/search'
UA = {'User-Agent': 'Mozilla/5.0 (TBDI bulk site research)'}
BASEMAP_HOSTS = ('services.arcgisonline.com', 'basemaps.arcgis.com', 'tiles.arcgis.com')
NAMES = {'IA': 'Iowa', 'GA': 'Georgia', 'KY': 'Kentucky', 'TX': 'Texas', 'OK': 'Oklahoma',
         'AR': 'Arkansas', 'AL': 'Alabama', 'OH': 'Ohio', 'FL': 'Florida', 'VA': 'Virginia',
         'IL': 'Illinois', 'IN': 'Indiana', 'NE': 'Nebraska'}
# States that publish GIS from their own infrastructure. A state that self-hosts and never
# registered on AGOL is invisible to both indexes above; Nebraska proved the pattern.
STATE_HOSTS = {
    'IA': ['https://programs.iowadnr.gov/geospatial/rest/services'],
    'GA': ['https://services1.arcgis.com/f8Cj0h9wJ2sLNK3D/arcgis/rest/services'],
    'KY': ['https://kygisserver.ky.gov/arcgis/rest/services', 'https://maps.kytc.ky.gov/arcgis/rest/services'],
    'TX': ['https://feature.geographic.texas.gov/arcgis/rest/services',
           'https://services.arcgis.com/KTcxiTD9dsQw4r7Z/arcgis/rest/services'],
    'OK': ['https://okmaps.org/arcgis/rest/services'],
    'AR': ['https://gis.arkansas.gov/arcgis/rest/services'],
    'AL': ['https://services7.arcgis.com/BnpBxBnwMOnMIWuY/arcgis/rest/services'],
    'IL': ['https://maps.gis.illinois.gov/arcgis/rest/services'],
    'IN': ['https://gisdata.in.gov/arcgis/rest/services'],
    'NE': ['https://gis.ne.gov/Enterprise/rest/services'],
}
FIELD_HINTS = {'apn': ('parcel_id', 'parcelid', 'parcelno', 'parcel_no', 'parcelnumb', 'parcelnumber',
                       'accountno', 'pin', 'apn', 'pid', 'gpin'),
               'owner': ('owner', 'ownername', 'owner_name', 'own_name', 'taxpayer'),
               'acres': ('acres', 'gis_acres', 'acreage', 'calc_acres', 'deed_acres'),
               'address': ('situs', 'address', 'site_addr', 'prop_addr', 'full_address')}
EXACT_ONLY = {'pin', 'apn', 'pid', 'gpin'}


def g(u, t=45):
    try:
        return json.loads(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=t).read())
    except Exception as e:
        return {'__error__': f'{type(e).__name__}: {str(e)[:100]}'}


def guess_fields(fields):
    norm = lambda x: x.lower().replace('_', '').replace(' ', '')
    out = {}
    for role, hints in FIELD_HINTS.items():
        found = None
        for h in hints:
            found = next((f for f in fields if norm(f) == norm(h)), None)
            if found:
                break
        if not found:
            for h in hints:
                if h in EXACT_ONLY:
                    continue
                found = next((f for f in fields if norm(h) in norm(f)), None)
                if found:
                    break
        if found:
            out[role] = found
    return out


def probe(url, points):
    """Layer metadata plus how many of the state's probe points return exactly one polygon."""
    m = g(url + '?f=json')
    if m.get('__error__') or m.get('error') or not m.get('fields'):
        return None
    if (m.get('geometryType') or '') not in ('esriGeometryPolygon', ''):
        return None
    fields = [f['name'] for f in (m.get('fields') or [])]
    fg = guess_fields(fields)
    if not (fg.get('apn') or fg.get('owner') or fg.get('acres')):
        return None                    # a boundary layer answers a point query too
    hits, tried, sample = 0, 0, None
    for sid, la, ln in points:
        r = g(arcgis_query(url, la, ln, '*', geometry=False))
        tried += 1
        n = len(r.get('features', [])) if 'features' in r else -1
        if n == 1:
            hits += 1
            if sample is None:
                a = r['features'][0]['attributes']
                sample = {sid: {k: a.get(k) for k in fg.values() if k in a}}
    cnt = g(url + '/query?where=1%3D1&returnCountOnly=true&f=json')
    return {'url': url, 'name': m.get('name'), 'records': cnt.get('count') if isinstance(cnt, dict) else None,
            'fields_guess': fg, 'probe_hits': hits, 'probe_tried': tried, 'sample': sample,
            'score': round(100 * hits / max(1, tried)) + (10 if fg.get('apn') else 0) + (5 if fg.get('owner') else 0)}


def candidates_for(st, points):
    full = NAMES.get(st, st)
    urls = []

    def add(u, why):
        u = (u or '').rstrip('/')
        if u and not any(h in u for h in BASEMAP_HOSTS) and not any(u == x[0] for x in urls):
            urls.append((u, why))

    for q in (f'{full} statewide parcels', f'{full} parcels', f'{full} cadastral'):
        r = g(f'{HUB}?q={urllib.parse.quote(q)}&page[size]=12')
        for d in (r.get('data') or []):
            a = d.get('attributes') or {}
            if any(k in str(a.get('name', '')).lower() for k in ('parcel', 'cadas')):
                add(a.get('url'), f'ArcGIS Hub: {a.get("name")}')
    q = urllib.parse.quote(f'{full} parcels type:("Feature Service" OR "Map Service")')
    r = g(f'{AGOL}?f=json&num=20&sortField=numviews&sortOrder=desc&q={q}')
    for it in (r.get('results') or []):
        if 'parcel' in (it.get('title') or '').lower() and it.get('url'):
            add(it['url'], f'AGOL item: {it.get("title")} (owner {it.get("owner")})')
    for host in STATE_HOSTS.get(st, []):
        j = g(host + '?f=json')
        if j.get('__error__') or j.get('error'):
            continue
        svcs = [(e['name'], e.get('type')) for e in j.get('services', [])]
        for folder in j.get('folders', []):
            fj = g(f'{host}/{folder}?f=json')
            svcs += [(e['name'], e.get('type')) for e in fj.get('services', [])]
        for name, kind in svcs:
            if kind in ('FeatureServer', 'MapServer') and any(
                    k in name.split('/')[-1].lower() for k in ('parcel', 'cadas')):
                add(f'{host}/{name}/{kind}', f'state host {host.split("/")[2]}')
    return urls


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--states', required=True)
    ap.add_argument('--probes-from', help='a batch sites.csv; uses up to 4 real sites per state')
    ap.add_argument('--probe', action='append', default=[], help='ST:lat,lng (repeatable)')
    a = ap.parse_args()
    pts = defaultdict(list)
    if a.probes_from:
        for r in csv.DictReader(open(a.probes_from, encoding='utf-8-sig')):
            if r.get('state') and len(pts[r['state']]) < 4:
                pts[r['state']].append((r['site_id'], float(r['lat']), float(r['lng'])))
    for p in a.probe:
        st, ll = p.split(':'); la, ln = ll.split(',')
        pts[st].append(('given', float(la), float(ln)))

    os.makedirs(OUT_DIR, exist_ok=True)
    summary = []
    for st in [x.strip().upper() for x in a.states.split(',')]:
        points = pts.get(st) or []
        print(f'\n=== {st} ({NAMES.get(st, st)}) — {len(points)} probe points ===')
        if not points:
            print('  no probe points; skipped'); continue
        urls = candidates_for(st, points)
        print(f'  {len(urls)} candidate URLs')
        results = []
        for u, why in urls[:14]:
            for target in ([u] if u.rstrip('/').split('/')[-1].isdigit() else [f'{u}/0', f'{u}/1']):
                r = probe(target, points)
                if r:
                    r['why'] = why
                    results.append(r)
                    print(f"     {r['score']:>4} {str(r['name'])[:34]:34} {r['probe_hits']}/{r['probe_tried']} points"
                          f" {str(r['records']):>10} rec  {r['fields_guess']}")
                    break
        results.sort(key=lambda r: -r['score'])
        best = results[0] if results and results[0]['probe_hits'] == results[0]['probe_tried'] else None
        json.dump({'state': st, 'checked': len(urls), 'probe_points': points,
                   'note': 'PROPOSAL ONLY — a person reviews and moves the winner into parcel-services.json.',
                   'candidates': results[:8]},
                  open(os.path.join(OUT_DIR, f'{st}.json'), 'w', encoding='utf-8'), indent=1)
        summary.append((st, len(points), best))
        print(f"  -> {'STATEWIDE CANDIDATE: ' + best['url'] if best else 'no statewide layer answered every probe point'}")
    print('\n' + '=' * 60)
    for st, n, best in summary:
        print(f"  {st}  {'HIT  ' + str(best['name'])[:40] if best else 'none'}")
    print(f'\nproposals in {OUT_DIR}')


if __name__ == '__main__':
    main()
