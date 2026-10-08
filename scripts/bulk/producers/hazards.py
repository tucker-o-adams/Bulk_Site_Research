# -*- coding: utf-8 -*-
"""Natural hazard ratings from FEMA's National Risk Index (NRI), census tract at the pin (2026-10-08).

One query per site returns FEMA's risk rating for each hazard: Very Low / Relatively Low / Relatively Moderate /
Relatively High / Very High (or No Rating, Not Applicable, Insufficient Data). Ratings are RELATIVE - a tract's risk
compared with every other US tract, combining expected annual loss, social vulnerability and community resilience - not
engineering design values. Tract level: coarse in large rural tracts, and a big site can cross tracts (the pin's tract
is reported).
"""
from cache import coord_key
from geom import arcgis_query
from provenance import Value, absent, failed, now_iso

NAME = 'hazards'
LYR = 'https://services.arcgis.com/XG15cJAlne2vxtgt/arcgis/rest/services/National_Risk_Index_Census_Tracts/FeatureServer/0'
SOURCE = 'FEMA National Risk Index (census tracts)'
VINTAGE = None                   # per row: NRI_VER
METHOD = 'NRI census tract containing the site pin; FEMA risk rating per hazard (relative to all US tracts)'
NOTE = 'relative ratings (risk vs. other US tracts), not design values; tract at the pin'
HAZARDS = [('nri_overall', 'RISK_RATNG'), ('nri_tornado', 'TRND_RISKR'), ('nri_strong_wind', 'SWND_RISKR'), ('nri_hail', 'HAIL_RISKR'),
           ('nri_hurricane', 'HRCN_RISKR'), ('nri_earthquake', 'ERQK_RISKR'), ('nri_wildfire', 'WFIR_RISKR'),
           ('nri_inland_flooding', 'IFLD_RISKR'), ('nri_coastal_flooding', 'CFLD_RISKR'), ('nri_landslide', 'LNDS_RISKR'),
           ('nri_ice_storm', 'ISTM_RISKR'), ('nri_winter_weather', 'WNTW_RISKR'), ('nri_lightning', 'LTNG_RISKR'),
           ('nri_heat_wave', 'HWAV_RISKR'), ('nri_drought', 'DRGT_RISKR')]
FIELDS = ['nri_tract'] + [f for f, _ in HAZARDS]


def run(site, cache):
    la, ln = site.lat, site.lng
    out_fields = 'TRACTFIPS,NRI_VER,' + ','.join(c for _, c in HAZARDS)
    resp, fetched, err = cache.get_json(NAME, coord_key(la, ln, 'tract'), arcgis_query(LYR, la, ln, out_fields))
    if err:
        return [failed(f, SOURCE, LYR, METHOD, err) for f in FIELDS]
    feats = (resp or {}).get('features') or []
    if not feats:
        return [absent(f, SOURCE, LYR, METHOD, note='no NRI census tract at the pin') for f in FIELDS]
    a = feats[0]['attributes']
    mk = lambda fld, val: Value(fld, val, SOURCE, LYR, METHOD, vintage=a.get('NRI_VER'), fetched_at=fetched or now_iso(), note=NOTE)
    return [mk('nri_tract', a.get('TRACTFIPS'))] + [mk(f, a.get(c)) for f, c in HAZARDS]
