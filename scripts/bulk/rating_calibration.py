# -*- coding: utf-8 -*-
"""Calibration on public proxies (design_site_rating.md §5): 17 publicly reported US data-centre projects with known
outcomes (2021-2026), rated from the facts reported BEFORE the outcome (announcement / application stage), then
compared with what happened. Research: three in-session research passes, 2026-09-28 (sources in the session and in
the design note). Scores are Claude's in-session rubric reading; unknowns are None (U) - public announcements rarely
give the utility stage, costs, flood or neighbours, so screeners are 'not_assessed' unless a fact settles them.

    .venv_fema/Scripts/python.exe scripts/bulk/rating_calibration.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rating_rules import power_score, indicated_priority, assigned_priority, IMPORTANT, SUPPORTING   # noqa: E402

UTIL = [(-1, 'serving utility has publicly stated a capacity constraint in the area; no committed power')]

U = (None, 'none')
NA = {'site_risk': 'not_assessed', 'control_blocked': 'passed'}
P = lambda mw, c, conf: (power_score(mw, c), conf)

# outcome class: good = built / energised; power = stalled or cancelled for power; community = stopped by
# community / zoning; flood = stopped by flood / wetland
CASES = [
    # --- built / energised
    ('B1', 'Connect / Oppidan, Des Moines IA, 5 MW', 'good',
     dict(power=U, land=U, site_control=U, investment=U, connectivity=U, market=(3, 'medium'), community=U), NA, []),
    ('B2', 'Edged, New Albany OH, 24 MW (AEP partner, business park)', 'good',
     dict(power=P(24, 'C2', 'low'), land=(4, 'medium'), site_control=U, investment=U, connectivity=U,
          market=(5, 'medium'), community=(4, 'medium')), NA, []),
    ('B3', 'Edged, Kansas City MO, 18 MW (Evergy partner, greenfield)', 'good',
     dict(power=P(18, 'C2', 'low'), land=(4, 'medium'), site_control=U, investment=U, connectivity=U,
          market=(5, 'medium'), community=U), NA, []),
    ('B4', 'DC BLOX, Greenville SC, 15 MW (3 MW phase 1), business park', 'good',
     dict(power=P(15, 'C2', 'low'), land=(3, 'medium'), site_control=(5, 'medium'), investment=U,
          connectivity=(5, 'medium'), market=(3, 'medium'), community=(4, 'medium')), NA, []),
    ('B5', 'DC BLOX cable landing, Myrtle Beach SC, 15 MW', 'good',
     dict(power=U, land=(4, 'medium'), site_control=(4, 'medium'), investment=U, connectivity=(5, 'medium'),
          market=(1, 'medium'), community=U), NA, []),
    ('B6', 'WhiteFiber NC-1, Madison NC, 24 MW of 99 MW signed with Duke', 'good',
     dict(power=P(24, 'C0', 'high'), land=(4, 'medium'), site_control=(5, 'high'), investment=U, connectivity=U,
          market=(1, 'medium'), community=U), NA, []),
    # --- stopped by community / zoning
    ('C1', 'Deep Green, Lansing MI, 24 MW on 2.5 ac city lots (rezoning + land sale)', 'community',
     dict(power=P(24, 'C2', 'low'), land=(3, 'medium'), site_control=(4, 'medium'), investment=U, connectivity=U,
          market=(3, 'medium'), community=(2, 'medium')), NA, []),
    ('C2', 'Monterey Park CA, 33-56 MW, homes and park adjacent (use permit)', 'community',
     dict(power=P(33, 'C2', 'low'), land=(3, 'medium'), site_control=(5, 'high'), investment=U, connectivity=U,
          market=(5, 'medium'), community=(2, 'medium')), NA, []),
    ('C3', 'Amazon Blackwell Rd, Warrenton VA (special use permit; organised opposition)', 'community',
     dict(power=P(20, 'C1', 'medium'), land=(4, 'medium'), site_control=(5, 'high'), investment=U, connectivity=U,
          market=(4, 'medium'), community=(2, 'medium')), NA, []),
    ('C4', 'Price Road, Chandler AZ, 150 MW approved but full delivery years out (PAD rezoning)', 'community',
     dict(power=P(150, 'C3', 'medium'), land=(3, 'medium'), site_control=U, investment=U, connectivity=U,
          market=(5, 'medium'), community=(2, 'medium')), NA, []),
    ('C5', 'PRSM speculative site, Preble Co. OH (ag -> industrial rezoning, no power requested)', 'community',
     dict(power=P(20, 'C3', 'low'), land=(4, 'medium'), site_control=(5, 'medium'), investment=U, connectivity=U,
          market=(2, 'medium'), community=(2, 'medium')), NA, []),
    ('C6', 'Project Cumulus, St. Charles MO, 440 ac in the 100-year floodplain (15 ft of fill)', 'flood',
     dict(power=U, land=U, site_control=U, investment=U, connectivity=U, market=(5, 'medium'), community=(2, 'medium')),
     {'site_risk': 'failed', 'control_blocked': 'passed'}, []),
    # --- stalled / cancelled for power
    ('P1', 'Digital Realty SJC37, Santa Clara CA, 48 MW (SVP; on-site substation by applicant)', 'power',
     dict(power=P(48, 'C2', 'low'), land=U, site_control=(5, 'high'), investment=(4, 'low'), connectivity=(5, 'medium'),
          market=(5, 'medium'), community=(4, 'medium')), NA, UTIL),
    ('P2', 'STACK SVY02A, Santa Clara CA, 48 MW on 9 ac (SVP)', 'power',
     dict(power=P(48, 'C2', 'low'), land=(3, 'medium'), site_control=(5, 'high'), investment=U, connectivity=U,
          market=(5, 'medium'), community=(4, 'medium')), NA, UTIL),
    ('P3', 'EdgeConneX POR03, Hillsboro OR, 20 MW "available 2025" (PGE)', 'power',
     dict(power=P(20, 'C2', 'low'), land=U, site_control=(5, 'medium'), investment=U, connectivity=(5, 'medium'),
          market=(5, 'medium'), community=U), NA, UTIL),
    ('P4', 'PowerHouse ABX-1, Ashburn VA, 30 MW committed + 50 MW substation (Dominion)', 'power',
     dict(power=P(30, 'C0', 'high'), land=(3, 'medium'), site_control=(5, 'high'), investment=U, connectivity=(5, 'medium'),
          market=(5, 'medium'), community=(4, 'medium')), NA, []),
    ('P5', 'Stream Project Liberty, Marion SC, ~400 ac (utility not named)', 'power',
     dict(power=U, land=(4, 'medium'), site_control=U, investment=U, connectivity=U, market=(1, 'medium'), community=(2, 'medium')),
     NA, []),
]

# the variants tested (the current rules first)
VARIANTS = [
    ('v0.5 (Community supporting, no utility adjustment)', ('investment', 'land', 'site_control'), ('connectivity', 'market', 'community')),
    ('current', IMPORTANT, SUPPORTING),
]


def run(important, supporting):
    out = []
    for cid, name, outcome, dims, scr, adj in CASES:
        ind, reasons, flags = indicated_priority(dims, scr, important, supporting)
        if 'v0.5' in str(important) or tuple(important) == ('investment', 'land', 'site_control'):
            adj = []                      # the utility-constraint adjustment is new in v0.6
        out.append((cid, name, outcome, assigned_priority(ind, adj) if adj else ind, reasons))
    return out


if __name__ == '__main__':
    results = {v: run(i, s) for v, i, s in VARIANTS}
    names = [v for v, _, _ in VARIANTS]
    print(f"{'':4} {'outcome':10} " + ' '.join(f'{n[:26]:27}' for n in names) + ' case')
    for row in zip(*[results[n] for n in names]):
        cid, name, outcome = row[0][:3]
        print(f"{cid:4} {outcome:10} " + ' '.join(f'{r[3]:27}' for r in row) + ' ' + name)
    for n in names:
        from collections import Counter
        c = Counter((r[2], r[3]) for r in results[n])
        print(f"\n{n}: " + '; '.join(f"{o} -> {p}: {k}" for (o, p), k in sorted(c.items())))
