# -*- coding: utf-8 -*-
"""Usable land: how many of the profile's pads fit on the site, and how many fit far enough from homes
(BACKLOG 9i, 2026-10-07). Runs only with a product profile (run.py --profile); every distance and limit comes
from it (product_profile.py).

Usable land = the site footprint (producers/footprint.py: intake outline, parcel or square) shrunk by the edge
setback, minus each of:

    buildings   FEMA USA Structures footprints, grown by building_buffer_ft
    flood       FEMA NFHL 1% annual-chance zones (SFHA), when exclude_sfha - the footprint producer's answer
    wetlands    USFWS NWI polygons (wetlands and water), when exclude_nwi - the footprint producer's answer
    land cover  NLCD 2021 cells in exclude_nlcd (31 barren: quarries, pits, bare rock; 11 open water); cells
                with no NLCD value (0, outside the coverage) are excluded too - unknown ground is not usable
    slope       USGS 3DEP elevation, lightly smoothed (3 x 3 mean), slope over max_slope_pct; steep patches
                under 0.25 ac are dropped as DEM noise

A pad needs one contiguous block: the usable land is "opened" by the pad's minimum width (shrunk by half the
width, then grown back), which removes every part too narrow to hold a pad. Pads fitting = the sum over the
remaining blocks of floor(block area / pad area) - an area count, not a layout; a test-fit decides the real number.

The same count is repeated inside two receptor zones: usable land at least receptor_review_ft and at least
receptor_pass_ft from every 2020 Census block with a home (producers/housing.py home_blocks, the same blocks
as home_block_dist_m). So "pads at the pass distance >= 1" means a pad can sit far enough from every home.

A failed layer fails the measured fields (rerun): a missing layer would overstate usable land. The one exception
is buildings when the profile sets buildings_required false - then the values carry a note instead.
"""
import math
import numpy as np
import rasterio
from rasterio import features
from shapely.geometry import shape
from shapely.ops import transform, unary_union
from cache import coord_key
from geom import arcgis_envelope_query
from provenance import Value, failed, now_iso
from producers import flood, footprint, housing, wetlands
import product_profile as prof

NAME = 'usable'
SOURCE = 'Usable land: site footprint minus FEMA USA Structures, NFHL, NWI, NLCD 2021, USGS 3DEP slope'
LYR = ''
VINTAGE = None
AC = footprint.AC
PROFILE = None                  # run.py sets the batch's product profile
STRUCTURES = 'https://services2.arcgis.com/FiaPA4ga0iQKduv3/arcgis/rest/services/USA_Structures_View/FeatureServer/0'
NLCD_WCS = 'https://www.mrlc.gov/geoserver/mrlc_download/wcs'
NLCD_COVERAGE = 'mrlc_download__NLCD_2021_Land_Cover_L48'
DEM = 'https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer'
DEM_MAX_PX, DEM_TARGET_M = 1500, 10
SLOPE_MIN_PATCH_M2 = 0.25 * AC
METHOD = ('footprint shrunk by the edge setback, minus buildings (+buffer), SFHA, NWI, NLCD excluded classes and slope over '
          'the limit; opened by the pad minimum width; pads = sum of floor(block / pad area); repeated beyond the review and '
          'pass distances from 2020 blocks with homes')

FIELDS = ['ul_basis', 'ul_site_acres', 'ul_usable_acres', 'ul_excluded', 'ul_largest_block_acres', 'ul_pads_fit',
          'ul_pads_fit_review', 'ul_pads_fit_pass', 'ul_layers']


def _bbox_ll(fp, grow_m=0):
    xmin, ymin, xmax, ymax = fp['m'].bounds
    inv = footprint.projection(*fp['center'])[1]
    (x0, y0), (x1, y1) = inv(xmin - grow_m, ymin - grow_m), inv(xmax + grow_m, ymax + grow_m)
    return x0, y0, x1, y1


def _key(fp, tag):
    return coord_key(*fp['center'], tag + '_' + '_'.join(str(round(v)) for v in fp['m'].bounds))


def buildings(fp, cache, buf_m):
    url = arcgis_envelope_query(STRUCTURES, _bbox_ll(fp, buf_m + 10), 'OCC_CLS')
    resp, fetched, err = cache.get_json(NAME, _key(fp, 'bldg'), url)
    if err:
        return None, fetched, err
    gs = []
    for f in (resp or {}).get('features') or []:
        try:
            g = transform(fp['fwd'], shape(f['geometry']))
            gs.append((g if g.is_valid else g.buffer(0)).buffer(buf_m))
        except Exception:
            continue
    return unary_union(gs) if gs else None, fetched, None


def _raster_polys(path, mask_fn, fp, min_m2=0.0):
    """Cells where mask_fn(array) is true, as one geometry in footprint metres."""
    with rasterio.open(path) as ds:
        a = ds.read(1)
        mask = mask_fn(a, ds).astype('uint8')
        parts = [transform(fp['fwd'], shape(g)) for g, v in features.shapes(mask, mask=mask.astype(bool), transform=ds.transform) if v]
    parts = [p.buffer(0) for p in parts if p.area >= min_m2]
    return unary_union(parts) if parts else None


def land_cover(fp, cache, classes):
    x0, y0, x1, y1 = _bbox_ll(fp, 60)
    q = (f'{NLCD_WCS}?service=WCS&version=2.0.1&request=GetCoverage&coverageid={NLCD_COVERAGE}'
         f'&subset=Long({x0:.6f},{x1:.6f})&subset=Lat({y0:.6f},{y1:.6f})'
         '&subsettingcrs=http://www.opengis.net/def/crs/EPSG/0/4326&format=image/geotiff')
    path, fetched, err = cache.get_bytes(NAME, _key(fp, 'nlcd'), q, '.tif')
    if err:
        return None, fetched, err
    bad = set(classes) | {0}
    return _raster_polys(path, lambda a, ds: np.isin(a, list(bad)), fp), fetched, None


def steep(fp, cache, max_pct):
    x0, y0, x1, y1 = _bbox_ll(fp, 60)
    lat = (y0 + y1) / 2
    w_m, h_m = (x1 - x0) * 111320 * math.cos(math.radians(lat)), (y1 - y0) * 110540
    nx = max(16, min(DEM_MAX_PX, round(w_m / DEM_TARGET_M)))
    ny = max(16, min(DEM_MAX_PX, round(h_m / DEM_TARGET_M)))
    q = (f'{DEM}/exportImage?bbox={x0:.6f},{y0:.6f},{x1:.6f},{y1:.6f}&bboxSR=4326&imageSR=4326&size={nx},{ny}'
         '&format=tiff&pixelType=F32&interpolation=RSP_BilinearInterpolation&f=image')
    path, fetched, err = cache.get_bytes(NAME, _key(fp, 'dem'), q, '.tif')
    if err:
        return None, fetched, err

    def mask(a, ds):
        a = a.astype('float64')
        if ds.nodata is not None:
            a[a == ds.nodata] = np.nan
        p = np.pad(a, 1, mode='edge')
        sm = sum(p[i:i + a.shape[0], j:j + a.shape[1]] for i in range(3) for j in range(3)) / 9.0
        dx = abs(ds.transform.a) * 111320 * math.cos(math.radians(lat))
        dy = abs(ds.transform.e) * 110540
        gy, gx = np.gradient(sm, dy, dx)
        pct = 100 * np.hypot(gx, gy)
        return np.nan_to_num(pct, nan=1e9) > max_pct          # no elevation = not usable
    return _raster_polys(path, mask, fp, SLOPE_MIN_PATCH_M2), fetched, None


def opened(g, width_m):
    if g is None or g.is_empty:
        return []
    o = g.buffer(-width_m / 2).buffer(width_m / 2) if width_m > 0 else g
    return [p for p in getattr(o, 'geoms', [o]) if p.area > 0]


def pads(blocks, pad_m2):
    return sum(int(b.area // pad_m2) for b in blocks)


def run(site, cache):
    if PROFILE is None:
        raise SystemExit('usable needs a product profile: run.py --profile Outputs/<batch>/input/thresholds.md')
    p = PROFILE
    la, ln = site.lat, site.lng
    fp = footprint.shape_at(la, ln, cache, site.acres_stated, site.outline)
    if fp['stage'] == 'failed':
        return [failed(f, SOURCE, LYR, METHOD, fp['error'] + '; rerun') for f in FIELDS]
    fp['center'] = (la, ln)
    site_m2 = fp['m'].area
    pad_m2 = prof.pad_acres(p) * AC
    edge_m, width_m = prof.m(p, 'edge_setback_ft'), prof.m(p, 'pad_min_width_ft')
    interior = fp['m'].buffer(-edge_m) if edge_m else fp['m']

    excl, layers, notes, fetched_all, errors = {}, [], [], [], []

    def take(label, geom, fetched, err, required=True):
        if err:
            (errors if required else notes).append(f'{label}: {err}')
            layers.append(f'{label} FAILED' if required else f'{label} not applied (lookup failed)')
            return
        fetched_all.append(fetched)
        layers.append(f'{label} ok')
        if geom is not None and not geom.is_empty:
            excl[label] = geom

    take('buildings', *buildings(fp, cache, prof.m(p, 'building_buffer_ft')), required=p['buildings_required'])
    if p['exclude_sfha']:
        feats, f1, e1 = footprint.overlay_features(fp, la, ln, cache, 'flood', flood.zones_request(la, ln), flood.SFHA_SEARCH_M,
                                                   f'{flood.NFHL}/28', flood.ZONE_FIELDS)
        take('flood (SFHA)', None if e1 else unary_union([g for pr, g in footprint.clip(feats, fp) if footprint.is_sfha(pr)]), f1, e1)
    if p['exclude_nwi']:
        feats, f2, e2 = footprint.overlay_features(fp, la, ln, cache, 'wetlands', wetlands.near_request(la, ln), wetlands.SEARCH_M,
                                                   wetlands.WET, '*')
        take('wetlands (NWI)', None if e2 else unary_union([g for _, g in footprint.clip(feats, fp)]), f2, e2)
    if p['exclude_nlcd']:
        take(f"land cover (NLCD {','.join(map(str, p['exclude_nlcd']))})", *land_cover(fp, cache, p['exclude_nlcd']))
    if p['max_slope_pct'] is not None:
        take(f"slope > {p['max_slope_pct']}%", *steep(fp, cache, p['max_slope_pct']))
    blocks, f3, e3 = housing.home_blocks(site, cache, fp)
    take('homes (Census blocks)', None, f3, e3)

    fetched = max([f for f in fetched_all if f] or [now_iso()])
    basis_note = f"over the {fp['basis']}" + (' - a stand-in square, not the site' if 'square' in fp['basis'] else '')
    mk = lambda fld, val, n=None: Value(fld, val, SOURCE, LYR, METHOD, fetched_at=fetched,
                                        note='; '.join(x for x in [basis_note, n] + notes if x))
    out = [mk('ul_basis', fp['basis']), mk('ul_site_acres', round(site_m2 / AC, 2))]
    if errors:
        why = '; '.join(errors) + '; rerun - a missing layer would overstate usable land'
        return out + [failed(f, SOURCE, LYR, METHOD, why) for f in FIELDS[2:-1]] + [mk('ul_layers', '; '.join(layers))]

    removed = unary_union(list(excl.values())) if excl else None
    usable = interior.difference(removed) if removed is not None else interior
    parts = [f"edge setback {(site_m2 - interior.area) / AC:,.1f} ac"] + \
            [f'{k} {v.intersection(interior).area / AC:,.1f} ac' for k, v in excl.items()]
    blocks_all = opened(usable, width_m)
    rev_m, pass_m = housing.receptor_m(p)
    homes = unary_union([g for _, g in blocks]) if blocks else None

    def beyond(d):
        return blocks_all if homes is None else opened(unary_union(blocks_all).difference(homes.buffer(d)) if blocks_all else None, width_m)

    pad_note = (f"pad {prof.pad_acres(p):,.2f} ac ({p['pad_mw']} MW at {p['mw_per_acre']} MW/ac), min width {p['pad_min_width_ft']} ft; "
                'an area count, not a layout')
    return out + [mk('ul_usable_acres', round(usable.area / AC, 2)),
                  mk('ul_excluded', '; '.join(parts), 'layers overlap, so these do not add up to the excluded total'),
                  mk('ul_largest_block_acres', round(max((b.area for b in blocks_all), default=0) / AC, 2), pad_note),
                  mk('ul_pads_fit', pads(blocks_all, pad_m2), pad_note),
                  mk('ul_pads_fit_review', pads(beyond(rev_m), pad_m2), f'{pad_note}; at least {p["receptor_review_ft"]:,} ft from every block with a home'),
                  mk('ul_pads_fit_pass', pads(beyond(pass_m), pad_m2), f'{pad_note}; at least {p["receptor_pass_ft"]:,} ft from every block with a home'),
                  mk('ul_layers', '; '.join(layers))]
