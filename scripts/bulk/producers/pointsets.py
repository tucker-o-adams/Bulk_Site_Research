# -*- coding: utf-8 -*-
"""Shared machinery for "nearest X and count within radius" producers over
point features: schools, places of worship, healthcare. Each producer names
its sources; this does the distance work and the counts."""
from geom import point_dist_m
from tbdi_geo import registry as shared
from tbdi_geo import rules

# The report rings are tbdi-geo's (rules.NEIGHBOUR_RINGS_MI); the field names (*_within_0_5mi, *_within_1mi) are
# this repo's, so a ring tbdi-geo changes fails here at import, not as a mislabelled count.
assert rules.NEIGHBOUR_RINGS_MI == (0.5, 1.0), rules.NEIGHBOUR_RINGS_MI
HALF_MI, ONE_MI = (r * 1609.344 for r in rules.NEIGHBOUR_RINGS_MI)


def layer(kind):
    """The layer URL tbdi-geo names for a neighbour kind (rules.NEIGHBOURS: home, school_public, worship ...)."""
    sid, lyr = next((s, ly) for k, _, s, ly, _, _ in rules.NEIGHBOURS if k == kind)
    return shared.layer_url(sid, lyr)


def score_points(features, lat, lng, name_fn):
    """features: GeoJSON point features. Returns sorted [(dist_m, props, label)]."""
    scored = []
    for f in features:
        g = f.get('geometry') or {}
        if g.get('type') != 'Point':
            continue
        x, y = g['coordinates'][0], g['coordinates'][1]
        p = f.get('properties') or {}
        scored.append((point_dist_m(lng, lat, x, y), p, name_fn(p)))
    scored.sort(key=lambda s: s[0])
    return scored


def score_rows(rows, lat, lng, lat_key, lng_key):
    """rows: dicts with numeric lat/lng strings. Returns sorted [(dist_m, row)]."""
    scored = []
    for r in rows:
        try:
            scored.append((point_dist_m(lng, lat, float(r[lng_key]), float(r[lat_key])), r))
        except (TypeError, ValueError, KeyError):
            continue
    scored.sort(key=lambda s: s[0])
    return scored


def counts(scored):
    return (sum(1 for s in scored if s[0] <= HALF_MI), sum(1 for s in scored if s[0] <= ONE_MI))
