# -*- coding: utf-8 -*-
"""The site attractiveness rating rules (design_site_rating.md §4, v0.4) as code: the Power grid, the confidence
cap, and the overall indicated priority. Dimension scores for everything except Power are set in session from the
rubric cards; this module only combines them, so the combination is the same every time.

    power_score(mw, certainty)                       -> 1..5
    capped(score, confidence)                        -> score limited by its confidence (None = unknown)
    indicated_priority(dims, screeners)              -> (priority, reasons, flags)

dims: {'power', 'investment', 'land', 'site_control', 'community', 'connectivity', 'market'} ->
      (score 1-5 or None, confidence 'high' | 'medium' | 'low' | 'none')
screeners: {'site_risk', 'control_blocked'} -> 'passed' | 'failed' | 'not_assessed'
"""

METHOD_VERSION = 'v1.0'
PRIORITIES = ('Low', 'Medium', 'High')
CORE = ('investment', 'land', 'site_control')          # the High caps look at these three
IMPORTANT = CORE + ('community',)                      # v0.6: Community moved from supporting (calibration)
SUPPORTING = ('connectivity', 'market')
CAP = {'high': 5, 'medium': 4, 'low': 3, 'none': None}
CERTAINTY = ('C0', 'C1', 'C2', 'C3')   # committed <= 12 mo; credible date 12-36 mo; ~36 mo less certain; > 36 mo / no study (v1.0)


def power_score(mw, certainty, no_capacity=False, path_to_more=False, full_mw=5, mid_mw=3):
    """Amount x certainty grid: 5 minus one point per step down in either (minimum 1). full_mw / mid_mw: the amount
    steps (>= 5 MW enough, 3-5 slightly restricted, 2-3 more restricted); parameters only for the sensitivity check."""
    if no_capacity or mw is None or certainty is None:
        return 1 if no_capacity else None
    if mw < 2:
        return 1 if not path_to_more else None      # a credible path is rated on the MW it leads to
    amount_step = 0 if mw >= full_mw else 1 if mw >= mid_mw else 2
    score = max(1, 5 - amount_step - CERTAINTY.index(certainty))
    if certainty in ('C0', 'C1'):          # floor: the 2 MW minimum, committed or credible within 36 months, is workable
        score = max(score, 3)   # (C1 now runs to 36 months)
    return score


def capped(score, confidence):
    """Shown score = min(evidence score, confidence cap); no usable information = unknown (None)."""
    cap = CAP[confidence]
    if score is None or cap is None:
        return None
    return min(score, cap)


def _step(priority, n=1):
    return PRIORITIES[max(0, PRIORITIES.index(priority) - n)]


def _cap(priority, ceiling):
    return PRIORITIES[min(PRIORITIES.index(priority), PRIORITIES.index(ceiling))]


def indicated_priority(dims, screeners, important=None, supporting=None):
    """§4.5 steps 1-6. Returns (priority, reasons, flags); named adjustments (step 7) are applied separately.
    important / supporting: override the dimension groups (used to test alternatives in calibration)."""
    important = IMPORTANT if important is None else tuple(important)
    supporting = SUPPORTING if supporting is None else tuple(supporting)
    reasons, flags = [], []
    if 'failed' in screeners.values():
        return 'Screened out', [f"screener failed: {k}" for k, v in screeners.items() if v == 'failed'], flags
    s = {k: capped(*dims.get(k, (None, 'none'))) for k in ('power',) + important + supporting}
    conf = {k: dims.get(k, (None, 'none'))[1] for k in s}
    if s['power'] is None:
        return 'Insufficient information', ['no power information at all (not even a proxy)'], flags
    p = 'High' if s['power'] >= 4 else 'Medium' if s['power'] == 3 else 'Low'
    reasons.append(f"Power {s['power']} sets the ceiling at {p}")
    # a moratorium over the jurisdiction caps at Low whichever group Community is in (applied with the caps)
    moratorium = s.get('community') == 1 and conf.get('community') in ('high', 'medium')
    # 1) step-downs from the ceiling
    weak = [k for k in important if s[k] is not None and s[k] <= 2 and not (k == 'community' and moratorium)]
    if len(weak) >= 2:
        p = 'Low'
        reasons.append(f"two or more important dimensions ≤ 2 ({', '.join(weak)})")
    elif weak:
        p = _step(p)
        reasons.append(f"important dimension ≤ 2 ({weak[0]}): one step down")
    for k in supporting:
        if s[k] == 1 and not (k == 'community' and moratorium):
            if conf[k] in ('high', 'medium'):
                p = _step(p)
                reasons.append(f"{k} 1 at {conf[k]} confidence: one step down")
            else:
                flags.append(f"{k} 1 at low confidence: flagged, not applied")
    # 2) caps are ceilings, applied last, so one underlying fact is never counted twice (v0.5)
    if p == 'High' and any(v != 'passed' for v in screeners.values()):
        p = 'Medium'
        reasons.append('capped at Medium: High needs both screeners passed (' +
                       ', '.join(f'{k} {v}' for k, v in screeners.items() if v != 'passed') + ')')
    known = [k for k in CORE if s.get(k) is not None]
    if p == 'High' and len(known) < 2:
        p = 'Medium'
        reasons.append(f"capped at Medium: High needs at least two of the three important dimensions known ({len(known)} known)")
    if p == 'High' and not (any(s[k] >= 4 for k in known) and all(s[k] >= 3 for k in known)):
        p = 'Medium'
        reasons.append('capped at Medium: High needs one important dimension at 4+ and none below 3')
    if moratorium:
        p = _cap(p, 'Low')
        reasons.append('capped at Low: Community 1 (moratorium or ban over the jurisdiction)')
    return p, reasons, flags


def assigned_priority(indicated, adjustments):
    """Named adjustments (open list, §4.5 step 7): each moves one step, with a written reason. [(+1 | -1, reason)]"""
    if indicated in ('Screened out', 'Insufficient information'):
        return indicated
    i = PRIORITIES.index(indicated) + sum(d for d, _ in adjustments)
    return PRIORITIES[max(0, min(2, i))]
