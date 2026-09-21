# -*- coding: utf-8 -*-
"""Census Bureau batch geocoder: free, no key, up to 10,000 addresses per request.

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
import csv, io, time, urllib.request, uuid

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
