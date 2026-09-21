# -*- coding: utf-8 -*-
"""Substations near the site, from the HIFLD Electric Substations layer (mirror).

One point query within RADIUS_M, then straight-line distances locally:
  * nearest substation of any type/voltage
  * nearest with MAX_VOLT >= 100 kV, and >= 230 kV
  * count and max voltage within 10 km (the two fields Mireye also reports)

Caveats that travel with every row (tbdi-pasa D-015): HIFLD Open was retired
by DHS in Aug 2025; this ArcGIS layer is a mirror last edited 2021-02-25, older
than the transmission-lines layer. Provenance is per row — the layer's own
SOURCE says whether a record came from utility data, imagery, or OpenStreetMap,
and MAX_INFER = Y means the voltage was inferred from connected lines. TYPE is
SUBSTATION or TAP (a line tap, not a facility). -999999 is HIFLD's "not
published" sentinel and is normalised to null here.
"""
from datetime import datetime, timezone
from cache import coord_key
from geom import arcgis_query, point_dist_m
from provenance import Value, absent, failed, now_iso

NAME = 'substations'
LYR = ('https://services5.arcgis.com/HDRa0B57OVrv2E1q/ArcGIS/rest/services/'
       'Electric_Substations/FeatureServer/0')
SOURCE = 'HIFLD Electric Substations (ArcGIS mirror of retired HIFLD Open)'
VINTAGE = '2021-02-25'          # layer editingInfo.dataLastEditDate, checked 2026-09-21
RADIUS_M = 15000
COUNT_M = 10000
OUT_FIELDS = 'ID,NAME,TYPE,STATUS,MAX_VOLT,MIN_VOLT,MAX_INFER,MIN_INFER,LINES,SOURCE,SOURCEDATE,VAL_DATE,CITY,STATE'
METHOD = (f'HIFLD substations within {RADIUS_M} m of the site point; straight-line distance to each; '
          f'nearest of any type, nearest >= 100 kV and >= 230 kV by MAX_VOLT; count and max MAX_VOLT within {COUNT_M} m')
NOTE = 'HIFLD mirror (dataset retired Aug 2025, layer edited 2021-02); per-row SOURCE may be OpenStreetMap; TAP = line tap, not a facility'

FIELDS = ['sub_nearest_m', 'sub_nearest_name', 'sub_nearest_type', 'sub_nearest_max_kv', 'sub_nearest_min_kv',
          'sub_nearest_kv_inferred', 'sub_nearest_lines', 'sub_nearest_status', 'sub_nearest_source',
          'sub_nearest_id',
          'sub_100kv_nearest_m', 'sub_100kv_nearest_name', 'sub_100kv_max_kv', 'sub_100kv_lines',
          'sub_230kv_nearest_m', 'sub_230kv_nearest_name', 'sub_230kv_max_kv',
          f'sub_count_within_{COUNT_M // 1000}km', f'sub_max_kv_within_{COUNT_M // 1000}km']


def _kv(v):
    try:
        v = float(v)
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


def _shown(name):
    n = (name or '').strip()
    return n if n and not n.upper().startswith(('UNKNOWN', 'NOT AVAIL')) else (f'[unnamed {n}]' if n else '[unnamed]')


def run(site, cache):
    la, ln = site.lat, site.lng
    url = arcgis_query(LYR, la, ln, OUT_FIELDS, distance_m=RADIUS_M, geometry=True, fmt='geojson')
    resp, fetched, err = cache.get_json(NAME, coord_key(la, ln, f'r{RADIUS_M}'), url)
    if err:
        return [failed(f, SOURCE, LYR, METHOD, err) for f in FIELDS]
    fetched = fetched or now_iso()

    def mk(fld, val, note=NOTE):
        return Value(fld, val, SOURCE, LYR, METHOD, vintage=VINTAGE, fetched_at=fetched, note=note)

    subs = []
    for f in resp.get('features') or []:
        g = f.get('geometry') or {}
        if g.get('type') != 'Point':
            continue
        x, y = g['coordinates'][0], g['coordinates'][1]
        p = f.get('properties') or {}
        subs.append((point_dist_m(ln, la, x, y), p))
    subs.sort(key=lambda s: s[0])
    if not subs:
        return [absent(f, SOURCE, LYR, METHOD, note=f'no substation within {RADIUS_M} m', vintage=VINTAGE)
                for f in FIELDS]

    d, p = subs[0]
    out = [mk('sub_nearest_m', round(d, 1)), mk('sub_nearest_name', _shown(p.get('NAME'))),
           mk('sub_nearest_type', p.get('TYPE')), mk('sub_nearest_max_kv', _kv(p.get('MAX_VOLT'))),
           mk('sub_nearest_min_kv', _kv(p.get('MIN_VOLT'))), mk('sub_nearest_kv_inferred', p.get('MAX_INFER')),
           mk('sub_nearest_lines', p.get('LINES')), mk('sub_nearest_status', p.get('STATUS')),
           mk('sub_nearest_source', p.get('SOURCE')), mk('sub_nearest_id', p.get('ID'))]

    for thr, tag, cols in ((100, '100kv', ('sub_100kv_nearest_m', 'sub_100kv_nearest_name', 'sub_100kv_max_kv', 'sub_100kv_lines')),
                           (230, '230kv', ('sub_230kv_nearest_m', 'sub_230kv_nearest_name', 'sub_230kv_max_kv'))):
        hit = next(((dd, pp) for dd, pp in subs if (_kv(pp.get('MAX_VOLT')) or 0) >= thr), None)
        if hit:
            dd, pp = hit
            vals = [round(dd, 1), _shown(pp.get('NAME')), _kv(pp.get('MAX_VOLT')), pp.get('LINES')]
            out += [mk(c, v) for c, v in zip(cols, vals)]
        else:
            out += [absent(c, SOURCE, LYR, METHOD, note=f'no substation with MAX_VOLT >= {thr} kV within {RADIUS_M} m '
                           '(voltage is unpublished for many records)', vintage=VINTAGE) for c in cols]

    within = [(dd, pp) for dd, pp in subs if dd <= COUNT_M]
    kvs = [_kv(pp.get('MAX_VOLT')) for _, pp in within if _kv(pp.get('MAX_VOLT'))]
    out += [mk(f'sub_count_within_{COUNT_M // 1000}km', len(within)),
            mk(f'sub_max_kv_within_{COUNT_M // 1000}km', max(kvs)) if kvs else
            absent(f'sub_max_kv_within_{COUNT_M // 1000}km', SOURCE, LYR, METHOD,
                   note=f'no published voltage on any substation within {COUNT_M} m', vintage=VINTAGE)]
    return out
