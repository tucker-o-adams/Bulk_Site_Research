# -*- coding: utf-8 -*-
"""Shared machinery for "nearest X and count within radius" producers over
point features: schools, places of worship, healthcare. Each producer names
its sources; this does the distance work and the counts."""
from geom import point_dist_m

HALF_MI, ONE_MI = 804.672, 1609.344


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
