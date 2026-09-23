# -*- coding: utf-8 -*-
"""Bulk site research: CSV of sites in -> per-site fields with provenance out.

    .venv_fema/Scripts/python.exe scripts/bulk/run.py --sites <in.csv> --out Outputs/<batch>/
        [--producers transmission,...]   default: all
        [--only SITE_ID,SITE_ID]         subset, for spot checks
        [--expected-owner REGEX]         owner a portfolio's parcels should carry (parcel_owner_check)

Writes into --out:
    sites.csv        one row per site: input columns + every producer field
    provenance.csv   one row per site x field: value, status, source, url, vintage, fetched_at, method
    run.json         inputs, counts, rejected rows, per-producer status tallies, cache hit/miss
    (raw service responses go to <repo>/data/cache/, shared across batches; rerun = offline)
"""
import argparse, csv, hashlib, importlib, json, os, re, sys, time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from sites import load_sites, REQUIRED, OPTIONAL          # noqa: E402
from cache import Cache                                     # noqa: E402
from provenance import PROVENANCE_COLUMNS, now_iso          # noqa: E402

ALL_PRODUCERS = ['transmission', 'substations', 'flood', 'wetlands', 'metro', 'datacenter',
                 'housing', 'schools', 'worship', 'healthcare', 'parcel', 'footprint']   # footprint reuses flood/wetlands/parcel answers


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--sites', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--producers', default=','.join(ALL_PRODUCERS))
    ap.add_argument('--only', default='')
    ap.add_argument('--workers', type=int, default=6, help='sites processed concurrently (I/O bound)')
    ap.add_argument('--expected-owner', default='',
                    help='regex for the owner of record a portfolio batch should show, e.g. '
                         '"windstream|kinetic|\\bcsl\\b"; an expected_owner input column overrides it per site')
    a = ap.parse_args()
    if a.expected_owner:
        try:
            re.compile(a.expected_owner)
        except re.error as e:
            raise SystemExit(f'--expected-owner is not a valid regex: {e}')

    t0 = time.time()
    os.makedirs(a.out, exist_ok=True)
    sites, rejected = load_sites(a.sites)
    if a.only:
        keep = set(x.strip() for x in a.only.split(',') if x.strip())
        unknown = keep - {s.site_id for s in sites}
        if unknown:
            print(f'  --only: not in the accepted sites (typo, or a rejected row?): {", ".join(sorted(unknown))}')
        sites = [s for s in sites if s.site_id in keep]
        if not sites:
            raise SystemExit('--only matched no accepted site; nothing to run')
    producers = [importlib.import_module(f'producers.{n.strip()}') for n in a.producers.split(',') if n.strip()]
    for p in producers:
        if hasattr(p, 'EXPECTED_OWNER') and a.expected_owner:
            p.EXPECTED_OWNER = a.expected_owner
    cache = Cache(os.path.join(os.path.dirname(os.path.dirname(HERE)), 'data', 'cache'))   # shared across batches
    print(f'sites: {len(sites)} accepted, {len(rejected)} rejected | producers: {[p.NAME for p in producers]}')
    for n, sid, why in rejected:
        print(f'  REJECTED row {n} {sid!r}: {why}')

    prov_rows, site_rows = [], []
    tally = {p.NAME: Counter() for p in producers}

    def one(s):
        row = {'site_id': s.site_id, 'lat': s.lat, 'lng': s.lng}
        for c in OPTIONAL:
            row[c] = getattr(s, c)
        row.update(s.extra)
        prov = []
        for p in producers:
            vals = p.run(s, cache)
            got = [v.field for v in vals]
            if got != list(p.FIELDS):
                raise SystemExit(f'{p.NAME} returned fields {got} != FIELDS {list(p.FIELDS)} for {s.site_id}')
            for v in vals:
                row[v.field] = v.value
                prov.append((p.NAME, v))
        return row, prov

    with ThreadPoolExecutor(max_workers=max(1, a.workers)) as ex:
        for i, (row, prov) in enumerate(ex.map(one, sites), 1):    # map preserves input order
            site_rows.append(row)
            for pname, v in prov:
                prov_rows.append(v.row(row['site_id']))
                tally[pname][v.status] += 1
            if i % 25 == 0 or i == len(sites):
                print(f'  {i}/{len(sites)}  cache hits {cache.hits} / misses {cache.misses}', flush=True)

    # --- sites.csv: fixed columns first, then pass-through, then producer fields in producer order
    cols = ['site_id', 'lat', 'lng'] + list(OPTIONAL)
    extra_cols = sorted({k for s in sites for k in s.extra})
    prod_cols = [f for p in producers for f in p.FIELDS]
    cols += extra_cols + prod_cols
    with open(os.path.join(a.out, 'sites.csv'), 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction='ignore')
        w.writeheader(); w.writerows(site_rows)
    with open(os.path.join(a.out, 'provenance.csv'), 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=PROVENANCE_COLUMNS, extrasaction='ignore')
        w.writeheader(); w.writerows(prov_rows)

    report = {
        'run_at': now_iso(), 'elapsed_s': round(time.time() - t0, 1),
        'input': {'path': os.path.abspath(a.sites),
                  'sha256': hashlib.sha256(open(a.sites, 'rb').read()).hexdigest()},
        'sites_accepted': len(sites), 'sites_rejected': [list(r) for r in rejected],
        'expected_owner': a.expected_owner or None,
        'producers': {p.NAME: {'source': p.SOURCE, 'url': p.LYR if hasattr(p, 'LYR') else None,
                               'vintage': getattr(p, 'VINTAGE', None), 'fields': list(p.FIELDS),
                               'status_counts': dict(tally[p.NAME])} for p in producers},
        'cache': {'hits': cache.hits, 'misses': cache.misses},
    }
    with open(os.path.join(a.out, 'run.json'), 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=1)
    print(f'\nwrote {a.out}: sites.csv ({len(site_rows)} rows), provenance.csv ({len(prov_rows)} rows), run.json')
    for p in producers:
        print(f'  {p.NAME}: {dict(tally[p.NAME])}')
    print(f'  {report["elapsed_s"]}s')


if __name__ == '__main__':
    main()
