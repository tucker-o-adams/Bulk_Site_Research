# -*- coding: utf-8 -*-
"""Which producers a site's location precision supports (design_incomplete_inputs.md, Part 1).

locate.py sets `location_tier` per site; run.py asks `allowed()` before running a producer and writes
`not_assessable` values for the rest. A site without a tier (an input CSV with its own coordinates, as
before) is treated as L2.

    L1/L2  everything
    L3     anchor within ~2 km: power context, metro, data centres, housing as area context
    L4     ZIP centroid: metro, data centres, housing as area context
    L5     county centroid: metro, data centres
No area-level flood or wetland statistics at any tier (decided 2026-09-24: a pond or stream decides the
parcel, so regional coverage would be false precision).
"""
ALL = None
SUPPORTED = {
    'L1': ALL,
    'L2': ALL,
    'L3': {'transmission', 'substations', 'metro', 'datacenter', 'housing'},
    'L4': {'metro', 'datacenter', 'housing'},
    'L5': {'metro', 'datacenter'},
}
AREA_CONTEXT = {'housing'}          # meaningful at L3-L4 only as context around the area, not the site


def tier_of(site):
    return (site.extra.get('location_tier') or 'L2').upper()


def allowed(site, producer_name):
    s = SUPPORTED.get(tier_of(site), ALL)
    return s is ALL or producer_name in s


def approx_note(site, producer_name):
    """The caveat every value measured from an L3+ point carries: it describes the anchor, not the site."""
    t = tier_of(site)
    if t in ('L1', 'L2'):
        return ''
    basis = site.extra.get('location_basis') or 'the located point'
    r = site.extra.get('location_radius_m') or '?'
    what = 'area context around' if producer_name in AREA_CONTEXT else 'measured from'
    return f"location {t}: {what} {basis}, not the site (site within ~{r} m)"


def reason(site):
    t = tier_of(site)
    return (f"not assessable at location {t} ({site.extra.get('location_basis') or 'no located point'}): "
            'this needs the parcel or a point on the site')
