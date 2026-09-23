# -*- coding: utf-8 -*-
"""Census Bureau batch geocoder: free, no key, up to 10,000 addresses per request.

Command line - fill lat/lng for an address-only site list, before run.py:

    .venv_fema/Scripts/python.exe scripts/bulk/geocode.py <raw.csv> <sites_in.csv>

Reads `street, city, state, zip` columns, or one `address` column ("123 Main St, Town, ST 12345").
Rows that already have lat/lng are kept as they are. Adds `geocode_match`, `geocode_match_type`
and `geocode_matched_address`; an unmatched row keeps blank lat/lng, and run.py lists it as
rejected, so nothing is dropped silently.

Library:

    from geocode import geocode_batch
    rows = geocode_batch([(id, street, city, state, zip), ...])
    # -> {id: {'match': 'Match'|'No_Match'|'Tie', 'match_type': 'Exact'|'Non_Exact'|'',
    #          'matched_address': str, 'lng': float|None, 'lat': float|None,
    #          'tiger_line_id': str, 'side': str}}

Uses the Public_AR_Current benchmark (address ranges interpolated along TIGER
street segments). Precision is "on the right street, roughly the right spot" —
tens of metres typically — which is fine for nearest-facility distances and is
stated in the provenance of anything built on it. `match_type` = Non_Exact
means the geocoder had to relax the input (e.g. ZIP fixed); carry it as a note.

Docs: https://geocoding.geo.census.gov/geocoder/Geocoding_Services_API.html
"""
import csv, io, re, sys, time, urllib.request, uuid

URL = 'https://geocoding.geo.census.gov/geocoder/locations/addressbatch'
BENCHMARK = 'Public_AR_Current'
BATCH = 9000     # under the 10k limit


def _post_multipart(fields, file_field, file_name, file_bytes, timeout=900):
    boundary = uuid.uuid4().hex
    body = io.BytesIO()
    for k, v in fields.items():
        body.write(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    body.write(f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; filename="{file_name}"\r\n'
               'Content-Type: text/csv\r\n\r\n'.encode())
    body.write(file_bytes)
    body.write(f'\r\n--{boundary}--\r\n'.encode())
    req = urllib.request.Request(URL, data=body.getvalue(), headers={
        'Content-Type': f'multipart/form-data; boundary={boundary}', 'User-Agent': 'Mozilla/5.0 (TBDI bulk site research)'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', 'replace')


def geocode_batch(records, tries=3):
    """records: iterable of (id, street, city, state, zip). Returns {id: result}."""
    out = {}
    records = list(records)
    for k in range(0, len(records), BATCH):
        chunk = records[k:k + BATCH]
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator='\n')
        for rid, street, city, state, zp in chunk:
            w.writerow([rid, street or '', city or '', state or '', (zp or '')[:5]])
        text = None
        for i in range(tries):
            try:
                text = _post_multipart({'benchmark': BENCHMARK}, 'addressFile', 'addresses.csv', buf.getvalue().encode('utf-8'))
                break
            except Exception as e:
                if i == tries - 1:
                    raise
                time.sleep(5 * (i + 1))
        # response columns: id, input address, match, match_type, matched address, "lng,lat", tiger line id, side
        for row in csv.reader(io.StringIO(text)):
            if len(row) < 3:
                continue
            rid, match = row[0], row[2]
            res = {'match': match, 'match_type': row[3] if len(row) > 3 else '', 'matched_address': row[4] if len(row) > 4 else '',
                   'lng': None, 'lat': None, 'tiger_line_id': row[6] if len(row) > 6 else '', 'side': row[7] if len(row) > 7 else ''}
            if match == 'Match' and len(row) > 5 and ',' in row[5]:
                x, y = row[5].split(',')
                res['lng'], res['lat'] = float(x), float(y)
            out[rid] = res
    return out


def split_address(text):
    """(street, city, state, zip) from "street, city, ST 12345"; the whole string as street if it does not split."""
    parts = [p.strip() for p in (text or '').split(',') if p.strip()]
    if len(parts) >= 3:
        m = re.fullmatch(r'([A-Za-z]{2})\s*(\d{5})?(?:-\d{4})?', parts[-1])
        if m:
            return ', '.join(parts[:-2]), parts[-2], m.group(1).upper(), m.group(2) or ''
    if len(parts) >= 4 and re.fullmatch(r'\d{5}(?:-\d{4})?', parts[-1]) and re.fullmatch(r'[A-Za-z]{2}', parts[-2]):
        return ', '.join(parts[:-3]), parts[-3], parts[-2].upper(), parts[-1][:5]
    return text or '', '', '', ''


def main(src, dst):
    sys.path.insert(0, __file__.rsplit('geocode.py', 1)[0] or '.')
    from sites import _norm_header, ALIASES
    with open(src, encoding='utf-8-sig', newline='') as f:
        rdr = csv.DictReader(f)
        cols = list(rdr.fieldnames or [])
        rows = list(rdr)
    key = {}                                   # canonical name -> the file's own header
    for c in cols:
        h = _norm_header(c)
        h = {'zip_code': 'zip', 'zipcode': 'zip', 'postal_code': 'zip', 'street_address': 'street', 'st': 'state'}.get(h, h)
        key.setdefault(ALIASES.get(h, h), c)
    for need in ('site_id',):
        if need not in key:
            raise SystemExit(f'{src}: no site_id column (have {cols})')
    lat_c, lng_c = key.get('lat', 'lat'), key.get('lng', 'lng')
    todo = []
    for r in rows:
        if (r.get(lat_c) or '').strip() and (r.get(lng_c) or '').strip():
            continue
        if 'street' in key:
            parts = tuple((r.get(key[k]) or '').strip() if k in key else '' for k in ('street', 'city', 'state', 'zip'))
        elif 'address' in key:
            parts = split_address(r.get(key['address']))
        else:
            raise SystemExit(f'{src}: rows without lat/lng need street/city/state/zip or an address column')
        todo.append((r[key['site_id']].strip(), *parts))
    print(f'{len(rows)} rows, {len(todo)} to geocode')
    res = geocode_batch(todo) if todo else {}
    extra = ['geocode_match', 'geocode_match_type', 'geocode_matched_address']
    out_cols = cols + [c for c in (lat_c, lng_c) if c not in cols] + [c for c in extra if c not in cols]
    n_ok = 0
    for r in rows:
        g = res.get(r[key['site_id']].strip())
        if not g:
            continue
        r['geocode_match'], r['geocode_match_type'], r['geocode_matched_address'] = g['match'], g['match_type'], g['matched_address']
        if g['lat'] is not None:
            r[lat_c], r[lng_c] = g['lat'], g['lng']
            n_ok += 1
    with open(dst, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=out_cols, extrasaction='ignore')
        w.writeheader(); w.writerows(rows)
    print(f'wrote {dst}: {n_ok} of {len(todo)} geocoded; unmatched rows keep blank lat/lng (run.py will list them)')


if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2])
