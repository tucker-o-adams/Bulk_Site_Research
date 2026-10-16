# -*- coding: utf-8 -*-
"""Serving electric utility and its average industrial price, from EIA data (2026-10-08).

The retail service territory at the pin (EIA Form 861 / HIFLD territories, with EIA revenue and sales by customer class,
as published by Esri's PolicyMap team): the utility that serves retail load there, its type (investor-owned, co-op,
municipal ...), its balancing authority / grid operator, and its average industrial and commercial price.

The price is AVERAGE REVENUE PER kWh across all the utility's industrial customers for the year - what they paid on
average, not the tariff a new 25 MW load would get. The serving utility is not necessarily the transmission owner or
the interconnection counterparty.

Where territories overlap at the pin: federal power marketers (WAPA, TVA, BPA ... - wholesale, territory = a whole region)
and utilities with no industrial sales are set aside; a utility that also serves homes (a true retail distributor) is
preferred over wholesale or irrigation agencies; then the most local territory (smallest area) is taken;
every other utility at the pin is listed in utility_others_at_pin. Territory polygons are approximate, so check that list.

In retail-choice states customers can buy their energy from competitive suppliers, so the local utility's revenue - and
this average - can be DELIVERY ONLY (0.6-2.7 cents/kWh in the 2026-10 sample), not the all-in price. industrial_price_basis
says so for those states.
"""
from cache import coord_key
from geom import arcgis_query
from provenance import Value, absent, failed, now_iso
from tbdi_geo import registry as shared
from tbdi_geo import rules

NAME = 'utility'
RETAIL_CHOICE = rules.RETAIL_CHOICE   # tbdi-geo rules
LYR = shared.layer_url('eia-861-utility-rates')  # tbdi-geo source registry
SOURCE = 'EIA Form 861 retail service territories and rates (Esri PolicyMap layer)'
VINTAGE = 'EIA 861, 2024'
METHOD = ('retail service territory polygons containing the site pin; average revenue per kWh = revenue / sales by '
          'customer class (EIA Form 861)')
NOTE = 'average paid by all industrial customers in the year, not a large-load tariff; serving utility, not the transmission owner'
OUT = ','.join(rules.UTILITY_FIELDS)
FIELDS = ['utility_name', 'utility_type', 'utility_grid_operator', 'utility_eia_id', 'utility_others_at_pin',
          'industrial_cents_kwh_2024', 'industrial_cents_kwh_2023', 'industrial_cents_kwh_2020', 'commercial_cents_kwh_2024',
          'industrial_price_basis']


def _r(v):
    try:
        return round(float(v), 2) if v not in (None, '') and float(v) > 0 else None
    except (TypeError, ValueError):
        return None


def run(site, cache):
    la, ln = site.lat, site.lng
    resp, fetched, err = cache.get_json(NAME, coord_key(la, ln, 'territory2'), arcgis_query(LYR, la, ln, OUT))
    if err:
        return [failed(f, SOURCE, LYR, METHOD, err) for f in FIELDS]
    feats = [f['attributes'] for f in (resp or {}).get('features') or []]
    if not feats:
        return [absent(f, SOURCE, LYR, METHOD, note='no retail service territory at the pin') for f in FIELDS]
    a, others = rules.serving_utility(feats)                            # tbdi-geo rules: the selection above
    feats = [a] + others
    mk = lambda fld, val: Value(fld, val, SOURCE, LYR, METHOD, vintage=VINTAGE, fetched_at=fetched or now_iso(), note=NOTE)
    out = [mk('utility_name', a.get('NAME')), mk('utility_type', a.get('TYPE')), mk('utility_grid_operator', a.get('CNTRL_AREA')),
           mk('utility_eia_id', a.get('Utility_ID')), mk('utility_others_at_pin', '; '.join(x.get('NAME') or '' for x in feats[1:]))]
    for fld, col in (('industrial_cents_kwh_2024', 'Indust_Electricity_Rate_Nom_2024'), ('industrial_cents_kwh_2023', 'Indust_Electricity_Rate_Nom_2023'),
                     ('industrial_cents_kwh_2020', 'Indust_Electricity_Rate_Nom_2020'), ('commercial_cents_kwh_2024', 'Cmrcl_Electricity_Rate_Nom_2024')):
        v = _r(a.get(col))
        out.append(mk(fld, v) if v is not None else absent(fld, SOURCE, LYR, METHOD, note='no sales in that class and year'))
    out.append(mk('industrial_price_basis', rules.price_basis(site.state or a.get('STATE'))))
    return out
