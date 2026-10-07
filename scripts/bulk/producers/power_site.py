# -*- coding: utf-8 -*-
"""Power measured from the site itself, not the pin (2026-10-07). The transmission and substation producers measure
from the pin; on a large site a line can cross the land while the pin sits far from it. Here distances run from the
site footprint's edge (producers/footprint.py: intake outline or parcel), 0 when the line or substation is on it.
A stand-in square is not the site, so for it the distances run from the pin, as before.

The voltages come from the product profile (product_profile.py; defaults 69 / 69 / 115 kV):
    power_line_min_kv       a line counts at this voltage or above. A line with no published voltage counts only when
                            its HIFLD voltage class is 100 kV or above - unknown is never assumed high enough
    power_sub_min_kv        a substation counts at this MAX_VOLT or above, IN SERVICE, and not a TAP (a line tap)
    power_115kv_sub_kv      the larger substation looked for alongside (115 kV+: a rough sign that more power could be added)

    pw_from                 'intake outline' / 'parcel boundary' / 'pin (no site outline)'
    line_crosses_site       any transmission line, any voltage, crossing the footprint
    line_kv_site_m, _kv     nearest qualifying line from the site edge, and its voltage
    sub_kv_site_m, _name, _kv          nearest qualifying substation from the site edge
    sub_115kv_site_m, _name, _kv       nearest 115 kV+ substation from the site edge

producers/usable.py repeats the three distances from the usable land (where a pad could go), from the same data.

Data: the transmission and substation producers' own answers around the pin (15 km). When the footprint reaches so
far from the pin that a closer feature could lie outside that answer, a bounding-box query over the footprint grown
by 15 km is used instead.
"""
import hashlib
from shapely.geometry import Point, shape
from shapely.ops import transform
from cache import coord_key
from geom import arcgis_envelope_query
from provenance import Value, absent, failed, now_iso
from producers import substations, transmission
import product_profile as prof

NAME = 'power_site'
LYR = transmission.LYR
SOURCE = 'HIFLD transmission lines and substations (ArcGIS mirrors), measured from the site footprint'
VINTAGE = None
PROFILE = None
METHOD = ('HIFLD lines and substations near the site (the 15 km answers around the pin, or a box over the footprint + 15 km when '
          'the footprint reaches past them); distance from the footprint edge, 0 when on the site; voltages from the profile')
NOTE = 'HIFLD mirrors (lines edited 2025-08, substations 2021-02); line geometry may sit 20-50 m off visible towers'
FIELDS = ['pw_from', 'line_crosses_site', 'line_kv_site_m', 'line_kv_site_kv', 'sub_kv_site_m', 'sub_kv_site_name', 'sub_kv_site_kv',
          'sub_115kv_site_m', 'sub_115kv_site_name', 'sub_115kv_site_kv']
HIGH_CLASSES = ('100', '220', '345', '500', '735', 'DC')     # HIFLD VOLT_CLASS bands at or above 100 kV


def kvs(p=None):
    p = p or PROFILE or prof.DEFAULTS
    return p['power_line_min_kv'], p['power_sub_min_kv'], p['power_115kv_sub_kv']


CLASS_KV = {'UNDER 100': 99, '100-161': 161, '220-287': 287, '345': 345, '500': 500, '735 AND ABOVE': 765, 'DC': 500}


def line_kv_for_row(props):
    """A line's voltage for right-of-way width: published VOLTAGE, else the top of its HIFLD class band (wider = safer),
    else None."""
    kv = transmission._kv(props)
    if kv is not None:
        return kv
    vc = (props.get('VOLT_CLASS') or '').upper().strip()
    return next((v for k, v in CLASS_KV.items() if vc.startswith(k)), None)


def row_width_m(props, p):
    """Total right-of-way width in metres for a line (profile line_row_width_ft bands), or 0 when not configured."""
    bands = p.get('line_row_width_ft')
    if not bands:
        return 0.0
    kv = line_kv_for_row(props)
    if kv is None:
        return (p.get('line_row_unknown_ft') or 0) * prof.FT
    width = 0
    for min_kv, ft in sorted(bands):
        if kv >= min_kv:
            width = ft
    return width * prof.FT


def line_ok(props, min_kv):
    kv = transmission._kv(props)
    if kv is not None:
        return kv >= min_kv
    vc = (props.get('VOLT_CLASS') or '').upper()
    return min_kv <= 100 and vc.startswith(HIGH_CLASSES)


def sub_ok(props, min_kv):
    kv = substations._kv(props.get('MAX_VOLT'))
    return (kv is not None and kv >= min_kv and (props.get('STATUS') or '').upper() == 'IN SERVICE'
            and (props.get('TYPE') or '').upper() != 'TAP')


def _features(site, cache, fp, reach_m):
    """(lines, subs, fetched, error): [(geometry in footprint metres, props)] each, from the pin answers or a box query."""
    la, ln = site.lat, site.lng
    out, fetched = {}, []
    for key, prod, url_pin, pin_key, fields in (
            ('lines', transmission, transmission.query_url(la, ln), coord_key(la, ln), transmission.OUT_FIELDS),
            ('subs', substations, None, coord_key(la, ln, f'r{substations.RADIUS_M}'), substations.OUT_FIELDS)):
        if reach_m is None:
            if url_pin is None:
                from geom import arcgis_query
                url_pin = arcgis_query(substations.LYR, la, ln, fields, distance_m=substations.RADIUS_M, geometry=True, fmt='geojson')
            resp, f, err = cache.get_json(prod.NAME, pin_key, url_pin)
        else:
            from producers import footprint
            inv = footprint.projection(la, ln)[1]
            x0, y0, x1, y1 = fp['m'].bounds
            (a, b), (c, d) = inv(x0 - reach_m, y0 - reach_m), inv(x1 + reach_m, y1 + reach_m)
            bb = (a, b, c, d)
            url = arcgis_envelope_query(prod.LYR, bb, fields, max_offset_m=5)
            k = coord_key(la, ln, 'sitebox_' + hashlib.md5(repr([round(v, 5) for v in bb]).encode()).hexdigest()[:10])
            resp, f, err = cache.get_json(prod.NAME, k, url, timeout=120)
        if err:
            return None, None, f, f'{key}: {err}'
        fetched.append(f)
        items = []
        for ft in (resp or {}).get('features') or []:
            try:
                g = transform(fp['fwd'], shape(ft['geometry']))
            except Exception:
                continue
            items.append((g, ft.get('properties') or {}))
        out[key] = items
    return out['lines'], out['subs'], max([x for x in fetched if x] or [None]), None


def near_site(site, cache, fp):
    """(lines, subs, fetched, error) complete enough to find the nearest feature to anywhere on the footprint: the pin
    answers when the footprint lies well inside them, else a box query over the footprint."""
    far = max(Point(0, 0).distance(Point(x, y)) for x, y in _corners(fp['m']))
    lines, subs, fetched, err = _features(site, cache, fp, None)
    if err:
        return lines, subs, fetched, err
    # a feature closer to the footprint than the nearest one found is within (that distance + far) of the pin;
    # when that exceeds the pin answer's radius, the answer may have missed it
    def complete(items):
        if not items:
            return far < 1
        d = min(g.distance(fp['m']) for g, _ in items)
        return d + far <= min(transmission.RADIUS_M, substations.RADIUS_M)
    if complete(lines) and complete(subs):
        return lines, subs, fetched, None
    return _features(site, cache, fp, transmission.RADIUS_M)


def _corners(g):
    x0, y0, x1, y1 = g.bounds
    return [(x0, y0), (x0, y1), (x1, y0), (x1, y1)]


def nearest(items, target, ok):
    """(distance m, geometry, props) of the nearest item passing ok(props) to target geometry, or None."""
    best = None
    for g, p in items:
        if not ok(p):
            continue
        d = g.distance(target)
        if best is None or d < best[0]:
            best = (d, g, p)
    return best


def run(site, cache):
    from producers import footprint
    fp = footprint.shape_at(site.lat, site.lng, cache, site.acres_stated, site.outline)
    if fp['stage'] == 'failed':
        return [failed(f, SOURCE, LYR, METHOD, fp['error'] + '; rerun') for f in FIELDS]
    on_site = fp['basis'] in (footprint.BASIS_OUTLINE, footprint.BASIS_PARCEL)
    target = fp['m'] if on_site else Point(0, 0)
    lines, subs, fetched, err = near_site(site, cache, fp)
    if err:
        return [failed(f, SOURCE, LYR, METHOD, err) for f in FIELDS]
    line_kv, sub_kv, head_kv = kvs()
    frm = fp['basis'] if on_site else 'pin (no site outline)'
    note = f'{NOTE}; from the {frm}; line >= {line_kv} kV, substation >= {sub_kv} kV in service (and a {head_kv} kV+ substation)'
    mk = lambda fld, val: Value(fld, val, SOURCE, LYR, METHOD, fetched_at=fetched or now_iso(), note=note)
    out = [mk('pw_from', frm), mk('line_crosses_site', bool(on_site and any(g.intersects(fp['m']) for g, _ in lines)))]
    ln_ = nearest(lines, target, lambda p: line_ok(p, line_kv))
    out += ([mk('line_kv_site_m', round(ln_[0], 1)), mk('line_kv_site_kv', transmission._kv(ln_[2]) or ln_[2].get('VOLT_CLASS'))] if ln_ else
            [absent(f, SOURCE, LYR, METHOD, note=f'no line >= {line_kv} kV in the data searched') for f in ('line_kv_site_m', 'line_kv_site_kv')])
    for tag, kv in (('sub_kv_site', sub_kv), ('sub_115kv_site', head_kv)):
        sb = nearest(subs, target, lambda p, kv=kv: sub_ok(p, kv))
        out += ([mk(f'{tag}_m', round(sb[0], 1)), mk(f'{tag}_name', substations._shown(sb[2].get('NAME'))),
                 mk(f'{tag}_kv', substations._kv(sb[2].get('MAX_VOLT')))] if sb else
                [absent(f, SOURCE, LYR, METHOD, note=f'no in-service substation >= {kv} kV in the data searched')
                 for f in (f'{tag}_m', f'{tag}_name', f'{tag}_kv')])
    return out
