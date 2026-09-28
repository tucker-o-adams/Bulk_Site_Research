# -*- coding: utf-8 -*-
"""Sensitivity check (design_site_rating.md §5): move each key threshold one notch and count which sites change
assigned priority. Uses rate.py on a batch folder; the method's values are the baseline.

    .venv_fema/Scripts/python.exe scripts/bulk/rating_sensitivity.py Outputs/<batch>/
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rate                                    # noqa: E402

VARIANTS = [
    ('C0 window 12 -> 6 months', {'c0_months': 6}),
    ('C0 window 12 -> 18 months', {'c0_months': 18}),
    ('C1 window 36 -> 30 months', {'c1_months': 30}),
    ('C1 window 36 -> 42 months', {'c1_months': 42}),
    ('full-credit MW 5 -> 4', {'full_mw': 4}),
    ('full-credit MW 5 -> 7.5', {'full_mw': 7.5}),
    ('amount step 3 -> 2.5 MW', {'mid_mw': 2.5}),
    ('land 0.5 -> 0.3 ac/MW', {'land_ac_per_mw': 0.3}),
    ('land 0.5 -> 0.7 ac/MW', {'land_ac_per_mw': 0.7}),
    ('Texas audit adjustment off', {'texas_audit': False}),
]

if __name__ == '__main__':
    b = sys.argv[1].rstrip('/\\')
    base_params = dict(rate.PARAMS)
    base = {r['site_id']: r['assigned'] for r in rate.rate_batch(b)}
    print(f"baseline: " + ', '.join(f"{p} {sum(1 for v in base.values() if v == p)}" for p in ('High', 'Medium', 'Low')))
    for name, over in VARIANTS:
        rate.PARAMS.clear(); rate.PARAMS.update(base_params); rate.PARAMS.update(over)
        got = {r['site_id']: r['assigned'] for r in rate.rate_batch(b)}
        flips = [f"{k} {base[k]}->{got[k]}" for k in base if got[k] != base[k]]
        print(f"{name:30} {len(flips):2} flip(s)  " + ', '.join(flips))
    rate.PARAMS.clear(); rate.PARAMS.update(base_params)
