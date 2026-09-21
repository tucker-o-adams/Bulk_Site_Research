# -*- coding: utf-8 -*-
"""Places of worship near the site, from the HIFLD "All Places of Worship"
layer (254,742 points, edited 2025-03), served by a third-party ArcGIS mirror.

Two caveats that travel with every row: the records were geocoded from IRS
501(c)(3) filings, so a point may be the congregation's mailing address rather
than the building; and the host is not a government server, so this source is
on the fragile list (BACKLOG.md) with OpenStreetMap as the fallback.
"""
from cache import coord_key
from geom import arcgis_query
from provenance import Value, absent, failed, now_iso
from producers.pointsets import score_points, counts

NAME = 'worship'
LYR = ('https://services.arcgis.com/XG15cJAlne2vxtgt/ArcGIS/rest/services/'
       'All_Places_Of_Worship__HiFLD_Open_/FeatureServer/42')
SOURCE = 'HIFLD All Places of Worship (ArcGIS mirror; IRS 501(c)(3) geocodes)'
VINTAGE = '2025-03-24'
SEARCH_M = 5000
METHOD = f'HIFLD places-of-worship points within {SEARCH_M} m; straight-line distance; nearest; counts within 0.5 mi and 1 mi'
NOTE = 'geocoded from IRS filings - may be a mailing address, not the building; third-party mirror of a retired dataset'

FIELDS = ['worship_nearest_m', 'worship_nearest_name', 'worship_nearest_city', 'worship_within_0_5mi', 'worship_within_1mi']


def run(site, cache):
    la, ln = site.lat, site.lng
    resp, fetched, err = cache.get_json(NAME, coord_key(la, ln, f'r{SEARCH_M}'),
                                        arcgis_query(LYR, la, ln, 'NAME,CITY,STATE', distance_m=SEARCH_M, geometry=True, fmt='geojson'))
    if err:
        return [failed(f, SOURCE, LYR, METHOD, err) for f in FIELDS]
    fetched = fetched or now_iso()

    def mk(fld, val):
        return Value(fld, val, SOURCE, LYR, METHOD, vintage=VINTAGE, fetched_at=fetched, note=NOTE)

    scored = score_points(resp.get('features') or [], la, ln, lambda p: (p.get('NAME') or '').title())
    if not scored:
        return ([absent(f, SOURCE, LYR, METHOD, note=f'no place of worship within {SEARCH_M} m', vintage=VINTAGE) for f in FIELDS[:3]]
                + [mk(f, 0) for f in FIELDS[3:]])
    d, p, n = scored[0]
    c5, c1 = counts(scored)
    return [mk('worship_nearest_m', round(d)), mk('worship_nearest_name', n), mk('worship_nearest_city', (p.get('CITY') or '').title()),
            mk('worship_within_0_5mi', c5), mk('worship_within_1mi', c1)]
