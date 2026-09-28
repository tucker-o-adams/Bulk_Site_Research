# -*- coding: utf-8 -*-
"""Edge-case profiles for the rating rules (design_site_rating.md §5). Each profile states the INTENDED priority,
written before the rules were run; the script reports every profile where the rules disagree.

    .venv_fema/Scripts/python.exe scripts/bulk/rating_edge_cases.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rating_rules import power_score, indicated_priority, assigned_priority   # noqa: E402

OK = {'site_risk': 'passed', 'control_blocked': 'passed'}
UNCONF = {'site_risk': 'not_assessed', 'control_blocked': 'passed'}
GOOD = {'investment': (5, 'high'), 'land': (5, 'high'), 'site_control': (5, 'high'),
        'connectivity': (4, 'medium'), 'market': (5, 'high'), 'community': (4, 'medium')}


def dims(power, **over):
    d = dict(GOOD, power=power)
    d.update(over)
    return d


P = lambda mw, c, conf='high': (power_score(mw, c), conf)
U = (None, 'none')

# (id, description, dims, screeners, adjustments, intended priority)
CASES = [
    ('P1', 'ideal: 5 MW committed now, everything strong', dims(P(5, 'C0')), OK, [], 'High'),
    ('P2', 'small, fully powered: 3 MW committed now', dims(P(3, 'C0')), OK, [], 'High'),
    ('P3', 'minimum site: 2 MW committed now', dims(P(2, 'C0')), OK, [], 'Medium'),
    ('P4', 'everything strong, no power information at all', dims(U), OK, [], 'Insufficient information'),
    ('P5', 'power known only by proxy (substation nearby)', dims((3, 'low')), OK, [], 'Medium'),
    ('P6', 'power position with no site yet (HOU-type): 20 MW credible 12-24 mo, no site',
     dims(P(20, 'C1', 'medium'), site_control=(1, 'medium'), land=U, investment=U), UNCONF, [], 'Medium'),
    ('P7', '5 MW committed, site named but not confirmed on the map',
     dims(P(5, 'C0'), land=(4, 'medium'), investment=U, site_control=(4, 'medium')), UNCONF, [], 'Medium'),
    ('P8', 'buildable land below 1 ac after flood / wetland', dims(P(5, 'C0')),
     {'site_risk': 'failed', 'control_blocked': 'passed'}, [], 'Screened out'),
    ('P9', 'strong power, moratorium over the jurisdiction', dims(P(5, 'C0'), community=(1, 'medium')), OK, [], 'Low'),
    ('P10', 'strong power, two weak important dimensions', dims(P(5, 'C0'), investment=(2, 'medium'), site_control=(2, 'medium')), OK, [], 'Low'),
    ('P11', 'strong power, FCC proxy shows no fiber nearby (low confidence)', dims(P(5, 'C0'), connectivity=(1, 'low')), OK, [], 'High'),
    ('P12', '5 MW but more than 24 months away', dims(P(5, 'C3', 'medium')), OK, [], 'Low'),
    ('P13', '3 MW committed now, readiness spend > $3.4M/MW', dims(P(3, 'C0'), investment=(1, 'high')), OK, [], 'Medium'),
    ('P14', '5 MW committed now, only site control known of the important three',
     dims(P(5, 'C0'), land=U, investment=U), OK, [], 'Medium'),
    ('P15', '3 MW committed now, quote says no fiber (medium confidence)', dims(P(3, 'C0'), connectivity=(1, 'medium')), OK, [], 'Medium'),
    ('P16', '2.5 MW with a credible date 12-24 months', dims(P(2.5, 'C1', 'medium')), OK, [], 'Medium'),
    ('P17', '5 MW committed, every other dimension unknown', dims(P(5, 'C0'), investment=U, land=U, site_control=U,
                                                                 connectivity=U, market=U, community=U), OK, [], 'Medium'),
    ('P18', '5 MW committed, everything else middling (all 3s)', dims(P(5, 'C0'), investment=(3, 'medium'), land=(3, 'medium'),
                                                                     site_control=(3, 'medium'), connectivity=(3, 'medium'),
                                                                     market=(3, 'medium'), community=(3, 'medium')), OK, [], 'Medium'),
    ('P19', '3 MW committed now, tract identified but owner not engaged', dims(P(3, 'C0'), site_control=(2, 'medium')), OK, [], 'Medium'),
    ('P20', 'broker estimate only: 5 MW "immediate" (C2), no site control stated', dims(P(5, 'C2', 'low'), site_control=(1, 'medium'),
                                                                                       land=U, investment=U), UNCONF, [], 'Low'),
    ('P21', '35 MW committed now, strong, Texas grid audit open (named adjustment)', dims(P(35, 'C0')), OK,
     [(-1, 'Texas grid audit: site >= 25 MW while open')], 'Medium'),
]

if __name__ == '__main__':
    miss = 0
    for cid, desc, d, scr, adj, want in CASES:
        ind, reasons, flags = indicated_priority(d, scr)
        got = assigned_priority(ind, adj) if adj else ind
        ok = got == want
        miss += not ok
        print(f"{'  ' if ok else '✗ '}{cid:4} {got:24} (intended {want:24}) {desc}")
        if not ok or flags:
            for r in reasons:
                print(f"         - {r}")
            for f in flags:
                print(f"         ! {f}")
    print(f"\n{len(CASES) - miss} of {len(CASES)} profiles match the intended priority")
