# -*- coding: utf-8 -*-
"""Actual homes near the site, from FEMA USA Structures (building footprints tagged by occupancy class).
Decided 2026-10-07 (Tucker): home distance is measured to real homes, not to Census block edges.

A home = a building whose OCC_CLS is Residential, or Unclassified (counted as a possible home: conservative), with
two size rules from the profile (Tucker, 2026-10-07, after spot checks found sheds and 100,000 sq ft warehouses
among the "homes"): a Residential building smaller than home_min_residential_sqft is a shed or garage, and an
Unclassified building counts only inside home_unclassified_sqft [min, max] - house-sized. Size = the dataset's
SQFEET, else the footprint area. The dataset does not say how each use tag was assigned (VAL_METHOD describes the
check of the building OUTLINE, not of the tag), so some tags are wrong;
kmz.py draws each site's nearest home with its tags for checking.
Every home counts - one farmhouse weighs the same as a subdivision - including a Residential building on the site
itself (homes_on_site says how many), since a house on the owner's land may be occupied. An Unclassified building
ON the site (intake outline or parcel) is not a home: on a quarry or plant it is almost always a plant building
(Tucker, 2026-10-07). Off the site it still counts. The square around a pin is not the site, so nothing is dropped there.

Measured from the site footprint (producers/footprint.py: intake outline, parcel or square), not the pin:

    home_nearest_m        distance from the footprint edge to the nearest home (0 = a home on the site)
    home_nearest_class    its OCC_CLS / PRIM_OCC
    homes_on_site         homes inside the footprint
    homes_within_review   homes within the profile's receptor_review_ft of the footprint (default 1,000 ft)
    homes_within_pass     homes within receptor_pass_ft (default 2,000 ft)

producers/usable.py uses the same homes to count pads that fit at least each distance from every home.
Homes built after the dataset's imagery date are missing; the value's vintage gives the imagery years.
"""
import urllib.parse
from datetime import datetime, timezone
from shapely.geometry import MultiPoint, shape
from shapely.ops import transform
from cache import coord_key
from geom import arcgis_envelope_query
from provenance import Value, absent, failed, now_iso
import product_profile as prof

NAME = 'homes'
LYR = 'https://services2.arcgis.com/FiaPA4ga0iQKduv3/arcgis/rest/services/USA_Structures_View/FeatureServer/0'
SOURCE = 'FEMA USA Structures (OCC_CLS Residential, or Unclassified as a possible home)'
VINTAGE = None                   # per site: the imagery years of the homes found
CLASSES = ('Residential', 'Unclassified')
PROFILE = None                   # run.py sets the batch's product profile; None = product_profile.DEFAULTS distances
MARGIN_M = 100
OUT_FIELDS = 'OCC_CLS,PRIM_OCC,IMAGE_DATE,SQFEET,PROP_ADDR,PROP_CITY,VAL_METHOD'
METHOD = ("USA Structures buildings with OCC_CLS Residential or Unclassified intersecting the footprint's bounding box grown "
          'by the pass distance + 100 m; each building as its centroid; distances from the footprint edge')
FIELDS = ['home_nearest_m', 'home_nearest_class', 'homes_on_site', 'homes_within_review', 'homes_within_pass']


def receptor_m(p=None):
    p = p or PROFILE or prof.DEFAULTS
    return prof.m(p, 'receptor_review_ft'), prof.m(p, 'receptor_pass_ft')


def points(site, cache, fp):
    """Homes near a footprint: ([(centroid Point in footprint metres, class label, imagery year, info)], fetched, error).
    info: poly (outline in footprint metres), sqft, address, verified (VAL_METHOD), occ (OCC_CLS)."""
    from producers import footprint
    _, pass_m = receptor_m()
    xmin, ymin, xmax, ymax = fp['m'].bounds
    grow = pass_m + MARGIN_M
    _, inv = footprint.projection(site.lat, site.lng)
    (x0, y0), (x1, y1) = inv(xmin - grow, ymin - grow), inv(xmax + grow, ymax + grow)
    where = 'OCC_CLS IN (' + ','.join(f"'{c}'" for c in CLASSES) + ')'
    url = arcgis_envelope_query(LYR, (x0, y0, x1, y1), OUT_FIELDS, max_offset_m=1) + '&where=' + urllib.parse.quote(where)
    key = coord_key(site.lat, site.lng, 'homes2_' + '_'.join(str(round(v)) for v in (xmin - grow, ymin - grow, xmax + grow, ymax + grow)))
    resp, fetched, err = cache.get_json(NAME, key, url, timeout=120)
    if err:
        return None, fetched, err
    own = fp['m'] if fp['basis'] in (footprint.BASIS_OUTLINE, footprint.BASIS_PARCEL) else None
    p = PROFILE or prof.DEFAULTS
    min_res = p.get('home_min_residential_sqft') or 0
    unc = p.get('home_unclassified_sqft')
    out = []
    for f in (resp or {}).get('features') or []:
        pr = f.get('properties') or {}
        try:
            poly = transform(fp['fwd'], shape(f['geometry']))
            c = poly.centroid
        except Exception:
            continue
        sqft = pr.get('SQFEET') or poly.area / prof.FT ** 2
        occ = pr.get('OCC_CLS')
        if occ == 'Unclassified' and own is not None and own.contains(c):
            continue                                  # an untagged building on the site: a plant building, not a home
        if occ == 'Residential' and sqft < min_res:
            continue                                  # shed or garage
        if occ == 'Unclassified' and unc and not (unc[0] <= sqft <= unc[1]):
            continue                                  # not house-sized
        yr = None
        try:
            yr = datetime.fromtimestamp(pr['IMAGE_DATE'] / 1000, tz=timezone.utc).year if pr.get('IMAGE_DATE') else None
        except (TypeError, ValueError, OSError):
            pass
        label = pr.get('OCC_CLS') or '?'
        if pr.get('PRIM_OCC') and pr.get('PRIM_OCC') != label:
            label += f" / {pr['PRIM_OCC']}"
        addr = ', '.join(x for x in (pr.get('PROP_ADDR'), pr.get('PROP_CITY')) if x)
        out.append((c, label, yr, {'poly': poly, 'sqft': round(sqft), 'address': addr, 'verified': pr.get('VAL_METHOD'), 'occ': occ}))
    return out, fetched, None


def zone(homes, d, snap_m=25.0):
    """Union of d-metre circles around the homes, as one geometry (None when no homes). Homes are snapped to a
    snap_m grid first and the radius grown by half the cell diagonal, so the zone never shrinks (thousands of
    town homes otherwise make the union slow)."""
    if not homes:
        return None
    cells = {(round(h[0].x / snap_m), round(h[0].y / snap_m)) for h in homes}
    return MultiPoint([(x * snap_m, y * snap_m) for x, y in cells]).buffer(d + snap_m * 0.71, quad_segs=6)


def run(site, cache):
    from producers import footprint
    fp = footprint.shape_at(site.lat, site.lng, cache, site.acres_stated, site.outline)
    if fp['stage'] == 'failed':
        return [failed(f, SOURCE, LYR, METHOD, fp['error'] + '; rerun') for f in FIELDS]
    homes, fetched, err = points(site, cache, fp)
    if err:
        return [failed(f, SOURCE, LYR, METHOD, err) for f in FIELDS]
    rev_m, pass_m = receptor_m()
    yrs = sorted({h[2] for h in homes if h[2]})
    vintage = (f'imagery {yrs[0]}' if len(yrs) == 1 else f'imagery {yrs[0]}-{yrs[-1]}') if yrs else None
    p = PROFILE or prof.DEFAULTS
    note = (f"from the {fp['basis']} edge; review {rev_m / prof.FT:,.0f} ft, pass {pass_m / prof.FT:,.0f} ft; Residential under "
            f"{p.get('home_min_residential_sqft') or 0:,} sq ft = shed/garage; Unclassified counts only off the site and at "
            f"{(p.get('home_unclassified_sqft') or ['any', 'any'])[0]:,}-{(p.get('home_unclassified_sqft') or ['any', 'any'])[1]:,} sq ft")
    mk = lambda fld, val, n=note: Value(fld, val, SOURCE, LYR, METHOD, vintage=vintage, fetched_at=fetched or now_iso(), note=n)
    if not homes:
        why = f'no Residential or Unclassified building within {pass_m + MARGIN_M:,.0f} m of the footprint'
        return [absent('home_nearest_m', SOURCE, LYR, METHOD, note=why), absent('home_nearest_class', SOURCE, LYR, METHOD, note=why),
                mk('homes_on_site', 0, why), mk('homes_within_review', 0, why), mk('homes_within_pass', 0, why)]
    dist = [(h[0].distance(fp['m']), h[1]) for h in homes]
    d0, lab0 = min(dist, key=lambda t: t[0])
    return [mk('home_nearest_m', round(d0, 1)), mk('home_nearest_class', lab0),
            mk('homes_on_site', sum(1 for d, _ in dist if d == 0)),
            mk('homes_within_review', sum(1 for d, _ in dist if d <= rev_m)),
            mk('homes_within_pass', sum(1 for d, _ in dist if d <= pass_m))]
