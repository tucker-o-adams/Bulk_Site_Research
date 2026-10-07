# -*- coding: utf-8 -*-
"""Sensitive neighbors that are not homes - schools, places of worship, nursing homes, hospitals - measured from the
site footprint's edge, not the pin (2026-10-07). With homes (producers/homes.py) they are the receptors the
receptor distances apply to: producers/usable.py counts pads at least receptor_review_ft / receptor_pass_ft from
every one of them.

    sensitive_nearest_m, _name, _kind   nearest school / place of worship / nursing home / hospital from the site edge
    sensitive_within_review / _pass     how many lie within the profile's receptor distances of the site edge

Sources: NCES public and private school points, HIFLD places of worship (IRS-geocoded, may be a mailing address),
CMS nursing homes and hospitals (data/reference CSVs, as producers/healthcare.py). The point layers are queried over
the footprint's bounding box grown by the pass distance + 100 m. The pin-based school, worship and healthcare
producers stay as they were.
"""
import urllib.parse
from shapely.geometry import Point
from cache import coord_key
from geom import arcgis_envelope_query
from provenance import Value, absent, failed, now_iso
from producers import healthcare, schools, worship
import product_profile as prof

NAME = 'sensitive'
LYR = schools.PUB
SOURCE = 'Sensitive neighbors: NCES schools, HIFLD places of worship, CMS nursing homes and hospitals'
VINTAGE = None
PROFILE = None
MARGIN_M = 100
METHOD = ("NCES school and HIFLD place-of-worship points over the footprint's bounding box grown by the pass distance + "
          '100 m, plus CMS nursing homes and hospitals; distance from the footprint edge')
FIELDS = ['sensitive_nearest_m', 'sensitive_nearest_name', 'sensitive_nearest_kind', 'sensitive_within_review', 'sensitive_within_pass']
LAYERS = (('public school', schools.PUB), ('private school', schools.PRV), ('place of worship', worship.LYR))


def receptor_m(p=None):
    p = p or PROFILE or prof.DEFAULTS
    return prof.m(p, 'receptor_review_ft'), prof.m(p, 'receptor_pass_ft')


def points(site, cache, fp):
    """([(Point in footprint metres, name, kind)], fetched, error) near the footprint."""
    from producers import footprint
    _, pass_m = receptor_m()
    grow = pass_m + MARGIN_M
    x0, y0, x1, y1 = fp['m'].bounds
    fwd, inv = fp['fwd'], footprint.projection(site.lat, site.lng)[1]
    (a, b), (c, d) = inv(x0 - grow, y0 - grow), inv(x1 + grow, y1 + grow)
    tag = '_'.join(str(round(v)) for v in (x0 - grow, y0 - grow, x1 + grow, y1 + grow))
    out, fetched = [], []
    for kind, lyr in LAYERS:
        url = arcgis_envelope_query(lyr, (a, b, c, d), 'NAME,CITY,STATE')
        resp, f, err = cache.get_json(NAME, coord_key(site.lat, site.lng, f"{kind.replace(' ', '')}_{tag}"), url)
        if err:
            return None, f, f'{kind}: {err}'
        fetched.append(f)
        for ft in (resp or {}).get('features') or []:
            g = ft.get('geometry') or {}
            if g.get('type') != 'Point':
                continue
            x, y = fwd(*g['coordinates'][:2])
            out.append((Point(x, y), ((ft.get('properties') or {}).get('NAME') or '').title(), kind))
    healthcare._load()
    for rows, kind, key in ((healthcare._NH, 'nursing home', 'provider_name'), (healthcare._H, 'hospital', 'facility_name')):
        for r in rows:
            try:
                lng, lat = float(r['longitude']), float(r['latitude'])
            except (TypeError, ValueError, KeyError):
                continue
            if a <= lng <= c and b <= lat <= d:
                x, y = fwd(lng, lat)
                out.append((Point(x, y), (r.get(key) or '').title(), kind))
    return out, max([x for x in fetched if x] or [None]), None


def run(site, cache):
    from producers import footprint
    fp = footprint.shape_at(site.lat, site.lng, cache, site.acres_stated, site.outline)
    if fp['stage'] == 'failed':
        return [failed(f, SOURCE, LYR, METHOD, fp['error'] + '; rerun') for f in FIELDS]
    pts, fetched, err = points(site, cache, fp)
    if err:
        return [failed(f, SOURCE, LYR, METHOD, err) for f in FIELDS]
    rev_m, pass_m = receptor_m()
    note = f"from the {fp['basis']} edge; review {rev_m / prof.FT:,.0f} ft, pass {pass_m / prof.FT:,.0f} ft; worship points are IRS geocodes"
    mk = lambda fld, val: Value(fld, val, SOURCE, LYR, METHOD, fetched_at=fetched or now_iso(), note=note)
    dist = sorted(((p.distance(fp['m']), name, kind) for p, name, kind in pts), key=lambda t: t[0])
    if not dist:
        why = f'no school, place of worship, nursing home or hospital within {pass_m + MARGIN_M:,.0f} m of the footprint'
        return [absent(f, SOURCE, LYR, METHOD, note=why) for f in FIELDS[:3]] + [mk('sensitive_within_review', 0), mk('sensitive_within_pass', 0)]
    d0, n0, k0 = dist[0]
    return [mk('sensitive_nearest_m', round(d0, 1)), mk('sensitive_nearest_name', n0), mk('sensitive_nearest_kind', k0),
            mk('sensitive_within_review', sum(1 for d, _, _ in dist if d <= rev_m)),
            mk('sensitive_within_pass', sum(1 for d, _, _ in dist if d <= pass_m))]
