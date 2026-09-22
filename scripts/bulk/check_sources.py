# -*- coding: utf-8 -*-
"""Check every external source this pipeline depends on, before a run trusts it.

    .venv_fema/Scripts/python.exe scripts/bulk/check_sources.py [--record] [--json]

Why this exists (the argument is tbdi-pasa's, in `tools/admin/sources.py`, and
this project has now lived it twice): **HIFLD Open did not go stale — DHS shut
it down in August 2025 and it vanished.** Two county parcel services, Habersham
and Union GA, disappeared between Aug and Sep 2026 while the pipeline that used
them looked exactly as confident as before. A refresh schedule does not detect
that. So this checks for *change*, not age:

  * does the service still answer, and is it still the same layer
  * record count, against the count last recorded (a layer that quietly loses
    half its records is the failure that actually happens)
  * the source's own data vintage, against what the producer claims
  * the fields the producer reads, still present by name

`data/reference/source-baseline.json` holds the last recorded state. `--record`
writes it (do that when the drift has been reviewed and is expected). Without
`--record`, nothing is written and the exit code is 1 if anything drifted, so
this can gate a batch.
"""
import argparse, importlib, json, os, sys, urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import registry                                  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
BASELINE = os.path.join(ROOT, 'data', 'reference', 'source-baseline.json')
UA = {'User-Agent': 'Mozilla/5.0 (TBDI bulk site research)'}
PRODUCERS = ['transmission', 'substations', 'flood', 'wetlands', 'metro', 'datacenter',
             'housing', 'schools', 'worship', 'healthcare', 'parcel']


def g(u, t=60):
    try:
        return json.loads(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=t).read())
    except Exception as e:
        return {'__error__': f'{type(e).__name__}: {str(e)[:120]}'}


def check_layer(url, want_fields=()):
    """One ArcGIS layer: reachable, name, vintage, record count, fields present."""
    m = g(url + '?f=json')
    if m.get('__error__'):
        return {'ok': False, 'error': m['__error__']}
    if m.get('error'):
        return {'ok': False, 'error': str(m['error'])[:140]}
    ei = m.get('editingInfo') or {}
    vint = None
    if ei.get('dataLastEditDate'):
        vint = datetime.fromtimestamp(ei['dataLastEditDate'] / 1000, tz=timezone.utc).date().isoformat()
    c = g(url + '/query?where=1%3D1&returnCountOnly=true&f=json')
    fields = [f['name'] for f in m.get('fields', [])]
    # Case-insensitive, like registry.pick: TxGIO names its fields 'prop_id' but identify returns 'PROP_ID'.
    have = {f.lower() for f in fields} | {(f.get('alias') or '').lower() for f in m.get('fields', [])}
    missing = [f for f in want_fields if f and f.lower() not in have]
    return {'ok': True, 'name': m.get('name'), 'vintage': vint,
            'records': c.get('count') if isinstance(c, dict) else None,
            'fields_missing': missing, 'field_count': len(fields)}


def check_wms(base, layer, point, want_fields=()):
    """A WMS parcel layer (OKMaps): no record count or edit date to read, so ask for the
    feature at a known point and check it still comes back with the fields we read."""
    if not point:
        return {'ok': False, 'error': 'no check_point registered for this WMS service'}
    la, ln = point
    d = 0.0005
    u = (f'{base}?SERVICE=WMS&VERSION=1.1.1&REQUEST=GetFeatureInfo&SRS=EPSG:4326'
         f'&BBOX={ln - d},{la - d},{ln + d},{la + d}&WIDTH=101&HEIGHT=101&X=50&Y=50&LAYERS={layer}'
         f'&QUERY_LAYERS={layer}&STYLES=&INFO_FORMAT=application/json&FEATURE_COUNT=1')
    r = g(u)
    if r.get('__error__'):
        return {'ok': False, 'error': r['__error__']}
    feats = r.get('features') or []
    if not feats:
        return {'ok': False, 'error': f'no feature at the check point {la},{ln}'}
    props = feats[0].get('properties') or {}
    return {'ok': True, 'name': layer, 'vintage': None, 'records': None,
            'fields_missing': [f for f in want_fields if f and f not in props], 'field_count': len(props)}


def targets():
    """Every layer the pipeline reads, from the producers themselves and the registry."""
    out = []
    sys.path.insert(0, os.path.join(HERE, 'producers'))
    for n in PRODUCERS:
        try:
            mod = importlib.import_module(f'producers.{n}')
        except Exception as e:
            out.append({'key': f'producer:{n}', 'error': f'import failed: {e}'}); continue
        urls = []
        for attr in ('LYR', 'PUB', 'PRV', 'WET', 'STATUS', 'IMGYR', 'NFHL', 'TIGER'):
            u = getattr(mod, attr, None)
            if isinstance(u, str) and u.startswith('http') and '/rest/services' in u:
                urls.append((attr, u))
        for attr, u in urls:
            if not u.rstrip('/').split('/')[-1].isdigit():
                u = u.rstrip('/') + '/0' if 'MapServer' not in u else u
            out.append({'key': f'{n}:{attr}', 'url': u, 'source': getattr(mod, 'SOURCE', ''),
                        'claimed_vintage': getattr(mod, 'VINTAGE', None)})
    reg = registry.load()
    for st, e in (reg.get('statewide') or {}).items():
        s = e['service']
        wms = s.get('protocol') == 'wms'
        out.append({'key': f'parcel:statewide:{e.get("state", st)}', 'url': s['base'] if wms else f"{s['base']}/{s['layer']}",
                    'source': s.get('name'), 'claimed_vintage': e.get('reviewed'),
                    'want_fields': [v for v in (s.get('fields') or {}).values()],
                    'wms': (s['layer'], s.get('check_point')) if wms else None})
    for geoid, e in (reg.get('counties') or {}).items():
        s = e['service']
        out.append({'key': f'parcel:county:{geoid} {e.get("county", "")}', 'url': f"{s['base']}/{s['layer']}",
                    'source': s.get('name'), 'claimed_vintage': e.get('reviewed'),
                    'want_fields': [v for v in (s.get('fields') or {}).values()]})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--record', action='store_true', help='write the current state as the new baseline')
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args()
    base = json.load(open(BASELINE, encoding='utf-8')) if os.path.exists(BASELINE) else {}
    now, drift = {}, []
    for t in targets():
        k = t['key']
        if t.get('error'):
            drift.append((k, t['error'])); print(f'  FAIL {k}: {t["error"]}'); continue
        r = check_wms(t['url'], *t['wms'], t.get('want_fields') or ()) if t.get('wms') else \
            check_layer(t['url'], t.get('want_fields') or ())
        now[k] = {**r, 'url': t['url'], 'checked_at': datetime.now(timezone.utc).isoformat(timespec='seconds')}
        b = base.get(k) or {}
        flags = []
        if not r['ok']:
            flags.append(f'UNREACHABLE: {r["error"]}')
        else:
            if r['fields_missing']:
                flags.append(f'FIELDS GONE: {r["fields_missing"]}')
            if b.get('records') and r.get('records') is not None:
                d = r['records'] - b['records']
                if abs(d) > max(50, 0.05 * b['records']):
                    flags.append(f'RECORDS {b["records"]:,} -> {r["records"]:,} ({d:+,})')
            if b.get('vintage') and r.get('vintage') and b['vintage'] != r['vintage']:
                flags.append(f'VINTAGE {b["vintage"]} -> {r["vintage"]}')
            if b.get('name') and r.get('name') and b['name'] != r['name']:
                flags.append(f'LAYER RENAMED {b["name"]!r} -> {r["name"]!r}')
        status = 'DRIFT' if flags else ('new ' if not b else 'ok  ')
        if flags:
            drift.append((k, '; '.join(flags)))
        print(f'  {status} {k:44} {r.get("name") or "":28} '
              f'{(str(r.get("records")) + " rec") if r.get("records") is not None else "":>14} {r.get("vintage") or "":>11}'
              + (('  <- ' + '; '.join(flags)) if flags else ''))
    if a.record:
        os.makedirs(os.path.dirname(BASELINE), exist_ok=True)
        json.dump(now, open(BASELINE, 'w', encoding='utf-8'), indent=1)
        print(f'\nrecorded baseline: {BASELINE} ({len(now)} sources)')
    print(f'\n{len(now)} sources checked, {len(drift)} drifted or failed')
    if a.json:
        print(json.dumps({'drift': drift, 'now': now}, indent=1))
    return 1 if drift and not a.record else 0


if __name__ == '__main__':
    sys.exit(main())
