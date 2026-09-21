# -*- coding: utf-8 -*-
"""Nursing homes and hospitals near the site, from the local CMS reference
files built by reference/fetch_cms_reference.py (no network at run time).

  nursing homes  CMS Provider Data Catalog "Provider Information" - every Medicare/
                 Medicaid-certified nursing home (~14.7k), with CMS's own coordinates.
  hospitals      CMS "Hospital General Information" - Medicare-certified hospitals
                 (~5.4k), addresses geocoded here with the Census batch geocoder;
                 ~85 % geocode (PO Box and rural-route addresses do not). A hospital
                 that did not geocode is invisible to this producer - stated per row.

Neither file lists non-certified facilities (e.g. some assisted-living, VA
hospitals are separate). "Retirement homes" in the ordinary sense are covered
only insofar as they are certified nursing facilities.
"""
import csv, json, os
from provenance import Value, absent, now_iso
from producers.pointsets import score_rows, counts

NAME = 'healthcare'
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
REF = os.path.join(ROOT, 'data', 'reference')
LYR = 'https://data.cms.gov/provider-data/'
SOURCE = 'CMS Provider Data Catalog (nursing homes: CMS coordinates; hospitals: Census-geocoded)'
VINTAGE = None      # from cms_reference.meta.json
SEARCH_M = 5000
METHOD = ('straight-line distance from the site to each CMS nursing home (CMS latitude/longitude) and each '
          'geocoded CMS hospital (Census batch geocoder, Public_AR_Current); nearest; counts within 0.5 mi and 1 mi')
NOTE_NH = 'CMS-certified nursing facilities only; coordinates are CMS-supplied'
NOTE_H = 'Medicare-certified hospitals only; ~85 % geocoded (PO Box / rural-route addresses missing); geocode match type given'

FIELDS = ['nursing_home_nearest_m', 'nursing_home_nearest_name', 'nursing_home_nearest_beds', 'nursing_home_nearest_rating',
          'nursing_homes_within_0_5mi', 'nursing_homes_within_1mi',
          'hospital_nearest_m', 'hospital_nearest_name', 'hospital_nearest_type', 'hospital_nearest_emergency',
          'hospital_nearest_geocode_match', 'hospitals_within_1mi']

_NH = _H = _META = None


def _load():
    global _NH, _H, _META
    if _NH is not None:
        return
    _NH = list(csv.DictReader(open(os.path.join(REF, 'cms_nursing_homes.csv'), encoding='utf-8')))
    _H = list(csv.DictReader(open(os.path.join(REF, 'cms_hospitals.csv'), encoding='utf-8')))
    _META = json.load(open(os.path.join(REF, 'cms_reference.meta.json'), encoding='utf-8'))


def run(site, cache):
    _load()
    la, ln = site.lat, site.lng
    fetched = now_iso()
    vint = f"nursing homes {_META['nursing_homes']['modified']}; hospitals {_META['hospitals']['modified']}"

    def mk(fld, val, note):
        return Value(fld, val, SOURCE, LYR, METHOD, vintage=vint, fetched_at=fetched, note=note)

    out = []
    nh = [s for s in score_rows(_NH, la, ln, 'latitude', 'longitude') if s[0] <= SEARCH_M]
    if nh:
        d, r = nh[0]
        c5, c1 = counts(nh)
        out += [mk('nursing_home_nearest_m', round(d), NOTE_NH), mk('nursing_home_nearest_name', r.get('provider_name'), NOTE_NH),
                mk('nursing_home_nearest_beds', int(r['number_of_certified_beds']) if r.get('number_of_certified_beds', '').isdigit() else None, NOTE_NH),
                mk('nursing_home_nearest_rating', r.get('overall_rating') or None, NOTE_NH),
                mk('nursing_homes_within_0_5mi', c5, NOTE_NH), mk('nursing_homes_within_1mi', c1, NOTE_NH)]
    else:
        out += [absent(f, SOURCE, LYR, METHOD, note=f'no CMS-certified nursing home within {SEARCH_M} m', vintage=vint) for f in FIELDS[:4]]
        out += [mk('nursing_homes_within_0_5mi', 0, NOTE_NH), mk('nursing_homes_within_1mi', 0, NOTE_NH)]

    h = [s for s in score_rows(_H, la, ln, 'latitude', 'longitude') if s[0] <= SEARCH_M]
    if h:
        d, r = h[0]
        out += [mk('hospital_nearest_m', round(d), NOTE_H), mk('hospital_nearest_name', r.get('facility_name'), NOTE_H),
                mk('hospital_nearest_type', r.get('hospital_type'), NOTE_H), mk('hospital_nearest_emergency', r.get('emergency_services'), NOTE_H),
                mk('hospital_nearest_geocode_match', r.get('geocode_match_type'), NOTE_H),
                mk('hospitals_within_1mi', counts(h)[1], NOTE_H)]
    else:
        out += [absent(f, SOURCE, LYR, METHOD, note=f'no geocoded Medicare-certified hospital within {SEARCH_M} m', vintage=vint) for f in FIELDS[6:11]]
        out += [mk('hospitals_within_1mi', 0, NOTE_H)]
    return out
