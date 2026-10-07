# -*- coding: utf-8 -*-
"""Usable land: how many of the profile's pads fit on the site, and how many fit far enough from homes
(BACKLOG 9i, 2026-10-07). Runs only with a product profile (run.py --profile); every distance and limit comes
from it (product_profile.py).

Usable land = the site footprint (producers/footprint.py: intake outline, parcel or square) inside the edge
setback, minus each of the layers below. The setback depends on what is next door when the profile sets
edge_setback_road/other/industrial_ft (Tucker, 2026-10-07): an outer edge within ROAD_NEAR_M of a Census TIGER road
(primary, secondary, local) is road frontage; else an edge with a USA Structures Industrial building within
IND_NEAR_M beyond it faces an industrial neighbor; else it takes the "other" setback (farmland, vacant, commercial,
homes - homes are held off far further by the receptor distances). Otherwise one edge_setback_ft applies everywhere. The setback is measured from the site's OUTER edge only (Tucker,
2026-10-07): gaps up to GAP_FILL_M between the site's own parcels (roads, rail, digitizing slivers) are filled
before measuring, so they cut no strip through the site; holes wider than that (likely other owners' land) keep
the setback. Pads still sit only on the site's own land, never on a filled gap.

    buildings   FEMA USA Structures footprints, grown by building_buffer_ft
    flood       FEMA NFHL 1% annual-chance zones (SFHA), when exclude_sfha - the footprint producer's answer
    wetlands    USFWS NWI polygons (wetlands and water), when exclude_nwi - the footprint producer's answer
    land cover  NLCD 2021 cells in exclude_nlcd (31 barren: quarries, pits, bare rock; 11 open water); cells
                with no NLCD value (0, outside the coverage) are excluded too - unknown ground is not usable
    slope       USGS 3DEP elevation, lightly smoothed (3 x 3 mean), slope over max_slope_pct; steep patches
                under 0.25 ac are dropped as DEM noise
    power lines HIFLD transmission lines, each widened to its right-of-way (profile line_row_width_ft by voltage;
                a line with no voltage takes the top of its class band, else line_row_unknown_ft)

A pad needs one contiguous block: the usable land is "opened" by the pad's minimum width (shrunk by half the
width, then grown back), which removes every part too narrow to hold a pad. Pads fitting = the sum over the
remaining blocks of floor(block area / pad area) - an area count, not a layout; a test-fit decides the real number.

The same count is repeated inside two receptor zones: usable land at least receptor_review_ft and at least
receptor_pass_ft from every receptor: actual homes (producers/homes.py: FEMA USA Structures) and schools, places of
worship, nursing homes and hospitals (producers/sensitive.py), all measured to the site, not the pin.
So "pads at the pass distance >= 1" means a pad can sit that far from every home.

measure() returns the geometries too (usable blocks, and the parts beyond each distance), so kmz.py draws
exactly what was counted.

A failed layer fails the measured fields (rerun): a missing layer would overstate usable land. The one exception
is buildings when the profile sets buildings_required false - then the values carry a note instead.
"""
import math, urllib.parse
import numpy as np
import rasterio
import rasterio.transform
import shapely
from rasterio import features
from shapely.geometry import shape
from shapely.ops import transform, unary_union
from cache import coord_key
from geom import arcgis_envelope_query
from provenance import Value, absent, failed, now_iso
from producers import flood, footprint, homes, power_site, sensitive, wetlands
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
FAR_CELL_M = 3                  # grid for "at least d from every home" (far_from); 3 m: 0.2 s a site, never lets ground closer than d
ROADS = 'https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Transportation/MapServer'
ROAD_LAYERS = (2, 6, 8)         # primary roads, secondary roads (full detail), local roads
ROAD_NEAR_M = 30                # an edge this close to a road centreline fronts the road (right-of-way width) - hypothesis
IND_NEAR_M = 150                # an industrial building this close beyond an edge makes it an industrial neighbor - hypothesis
GAP_FILL_M = 50                 # = the grouping gap: gaps this wide between the site's own parcels are inside the site
METHOD = ('footprint shrunk by the edge setback, minus buildings (+buffer), SFHA, NWI, NLCD excluded classes and slope over '
          'the limit; opened by the pad minimum width; pads = sum of floor(block / pad area); repeated beyond the review and '
          'pass distances from actual homes (USA Structures)')

FIELDS = ['ul_basis', 'ul_site_acres', 'ul_usable_acres', 'ul_excluded', 'ul_largest_block_acres', 'ul_pads_fit',
          'ul_pads_fit_review', 'ul_pads_fit_pass', 'ul_line_kv_m', 'ul_sub_kv_m', 'ul_sub_115kv_m', 'ul_layers']


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


def far_from(area, points, d, cell_m=FAR_CELL_M):
    """The part of area at least d from every point. A cell_m grid over the area; a cell is kept when its centre is at
    least d + half its diagonal from the nearest point (so no kept ground is closer than d); kept cells are turned back
    into polygons and clipped to the area. Far faster than unioning thousands of d-metre circles."""
    x0, y0, x1, y1 = area.bounds
    nx, ny = max(1, math.ceil((x1 - x0) / cell_m)), max(1, math.ceil((y1 - y0) / cell_m))
    xs = x0 + (np.arange(nx) + 0.5) * cell_m
    ys = y1 - (np.arange(ny) + 0.5) * cell_m
    gx, gy = np.meshgrid(xs, ys)
    inside = shapely.contains_xy(area.buffer(cell_m * 0.7072), gx, gy)     # cells that reach into the area; clipped below
    keep = np.zeros(gx.shape, dtype='uint8')
    if inside.any():
        tree = shapely.STRtree(points)
        cells = shapely.points(gx[inside], gy[inside])
        _, dist = tree.query_nearest(cells, return_distance=True, all_matches=False)
        keep[inside] = dist >= d + cell_m * 0.7072
    if not keep.any():
        return None
    tf = rasterio.transform.from_origin(x0, y1, cell_m, cell_m)
    parts = [shape(g) for g, v in features.shapes(keep, mask=keep.astype(bool), transform=tf) if v]
    return unary_union(parts).intersection(area)


def inside_setback(fp, edge_m):
    """The part of the site's own land at least edge_m inside its outer edge: gaps up to GAP_FILL_M are closed first."""
    if not edge_m:
        return fp['m']
    h = GAP_FILL_M / 2
    closed = fp['m'].buffer(h).buffer(-h)
    return closed.buffer(-edge_m).intersection(fp['m'])


def neighbors(fp, cache):
    """(roads, industrial buildings outside the site) near the footprint, in footprint metres, plus fetched, error."""
    gs, fetched = [], []
    for lid in ROAD_LAYERS:
        url = arcgis_envelope_query(f'{ROADS}/{lid}', _bbox_ll(fp, ROAD_NEAR_M + 20), 'MTFCC')
        resp, f, err = cache.get_json(NAME, _key(fp, f'road{lid}'), url)
        if err:
            return None, None, f, f'roads (TIGER layer {lid}): {err}'
        fetched.append(f)
        for ft in (resp or {}).get('features') or []:
            try:
                gs.append(transform(fp['fwd'], shape(ft['geometry'])))
            except Exception:
                continue
    url = arcgis_envelope_query(STRUCTURES, _bbox_ll(fp, IND_NEAR_M + 20), 'OCC_CLS') + '&where=' + \
        urllib.parse.quote("OCC_CLS='Industrial'")
    resp, f, err = cache.get_json(NAME, _key(fp, 'ind'), url)
    if err:
        return None, None, f, f'industrial buildings: {err}'
    fetched.append(f)
    ind = []
    for ft in (resp or {}).get('features') or []:
        try:
            g = transform(fp['fwd'], shape(ft['geometry']))
        except Exception:
            continue
        if not fp['m'].contains(g.centroid):
            ind.append(g)
    return (unary_union(gs) if gs else None), (unary_union(ind) if ind else None), max([x for x in fetched if x] or [None]), None


def inside_setback_by_neighbor(fp, p, roads, industrial):
    """(interior, note): the site's own land inside a setback that depends on what lies beyond each stretch of the
    outer edge - road frontage, an industrial neighbor, or anything else. Gaps up to GAP_FILL_M are closed first."""
    h = GAP_FILL_M / 2
    closed = fp['m'].buffer(h).buffer(-h)
    edge = closed.boundary
    road_zone = roads.buffer(ROAD_NEAR_M) if roads is not None else None
    ind_zone = industrial.buffer(IND_NEAR_M) if industrial is not None else None
    on_road = edge.intersection(road_zone) if road_zone is not None else None
    rest = edge.difference(road_zone) if road_zone is not None else edge
    on_ind = rest.intersection(ind_zone) if ind_zone is not None else None
    other = rest.difference(ind_zone) if ind_zone is not None else rest
    parts = []
    for seg, key in ((on_road, 'edge_setback_road_ft'), (on_ind, 'edge_setback_industrial_ft'), (other, 'edge_setback_other_ft')):
        d = prof.m(p, key) if p.get(key) is not None else prof.m(p, 'edge_setback_other_ft')
        if seg is not None and not seg.is_empty and d > 0:
            parts.append(seg.buffer(d))
    interior = (closed.difference(unary_union(parts)) if parts else closed).intersection(fp['m'])
    km = lambda g: 0 if g is None or g.is_empty else g.length / 1000
    note = (f"outer edge: road frontage {km(on_road):,.2f} km at {p.get('edge_setback_road_ft')} ft, industrial neighbor "
            f"{km(on_ind):,.2f} km at {p.get('edge_setback_industrial_ft')} ft, other {km(other):,.2f} km at {p.get('edge_setback_other_ft')} ft")
    return interior, note


def measure(site, cache, p):
    """{'fp', 'values' (field -> (value, note)) or 'error', 'layers', 'blocks', 'review', 'pass', 'homes'}; geometry in
    footprint metres. A failed layer comes back as 'error'."""
    la, ln = site.lat, site.lng
    fp = footprint.shape_at(la, ln, cache, site.acres_stated, site.outline)
    if fp['stage'] == 'failed':
        return {'fp': fp, 'error': fp['error'] + '; rerun', 'layers': [], 'notes': [], 'fetched': None}
    fp['center'] = (la, ln)
    site_m2 = fp['m'].area
    pad_m2 = prof.pad_acres(p) * AC
    width_m = prof.m(p, 'pad_min_width_ft')
    excl, layers, notes, fetched_all, errors = {}, [], [], [], []
    edge_note = None
    if p.get('edge_setback_other_ft') is not None:
        roads, industrial, fn, en = neighbors(fp, cache)
        if en:
            return {'fp': fp, 'error': en + '; rerun - the edge setback depends on it', 'layers': [f'neighbors FAILED'],
                    'notes': [], 'fetched': fn}
        fetched_all.append(fn)
        interior, edge_note = inside_setback_by_neighbor(fp, p, roads, industrial)
    else:
        interior = inside_setback(fp, prof.m(p, 'edge_setback_ft'))

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
    hs_all, f3, e3 = homes.points(site, cache, fp)
    take('homes (USA Structures)', None, f3, e3)
    hs, hs_on = homes.split(hs_all or [])
    sens, f5, e5 = sensitive.points(site, cache, fp)
    take('schools, worship, healthcare', None, f5, e5)
    receptors = [h[0] for h in hs] + [x[0] for x in (sens or [])]
    lines, subs, f4, e4 = power_site.near_site(site, cache, fp)
    row = None
    if not e4 and p.get('line_row_width_ft'):
        strips = [g.buffer(power_site.row_width_m(q, p) / 2) for g, q in lines if g.intersects(fp['m'].buffer(150))]
        row = unary_union([x for x in strips if not x.is_empty]) if strips else None
    take('power line right-of-way' if p.get('line_row_width_ft') else 'power (HIFLD)', row, f4, e4)
    fetched = max([f for f in fetched_all if f] or [now_iso()])
    if errors:
        return {'fp': fp, 'error': '; '.join(errors) + '; rerun - a missing layer would overstate usable land',
                'layers': layers, 'notes': notes, 'fetched': fetched}

    removed = unary_union(list(excl.values())) if excl else None
    usable = interior.difference(removed) if removed is not None else interior
    blocks_all = opened(usable, width_m)
    rev_m, pass_m = homes.receptor_m(p)
    union_all = unary_union(blocks_all) if blocks_all else None

    def beyond(d):
        if union_all is None:
            return []
        return blocks_all if not receptors else opened(far_from(union_all, receptors, d), width_m)

    rev, pas = beyond(rev_m), beyond(pass_m)
    line_kv, sub_kv, head_kv = power_site.kvs(p)
    pw = {}
    for key, items, ok in (('line', lines, lambda q: power_site.line_ok(q, line_kv)), ('sub', subs, lambda q: power_site.sub_ok(q, sub_kv)),
                           ('head', subs, lambda q: power_site.sub_ok(q, head_kv))):
        pw[key] = power_site.nearest(items, union_all, ok) if union_all is not None else None
    pw_note = lambda kv, what: (f'from the nearest usable block (wide enough for a pad) to the nearest {what} >= {kv} kV'
                                + ('' if union_all is not None else '; no usable block'))
    parts = [f"edge setback {(site_m2 - interior.area) / AC:,.1f} ac"] + \
            [f'{k} {v.intersection(interior).area / AC:,.1f} ac' for k, v in excl.items()]
    pad_note = (f"pad {prof.pad_acres(p):,.2f} ac ({p['pad_mw']} MW at {p['mw_per_acre']} MW/ac), min width {p['pad_min_width_ft']} ft; "
                'an area count, not a layout')
    values = {'ul_usable_acres': (round(usable.area / AC, 2), None),
              'ul_excluded': ('; '.join(parts), '; '.join(x for x in [edge_note, 'edge setback from the outer edge only; layers overlap, '
                                                                        'so these do not add up to the excluded total'] if x)),
              'ul_largest_block_acres': (round(max((b.area for b in blocks_all), default=0) / AC, 2), pad_note),
              'ul_pads_fit': (pads(blocks_all, pad_m2), pad_note),
              'ul_pads_fit_review': (pads(rev, pad_m2), f'{pad_note}; at least {p["receptor_review_ft"]:,} ft from every home, school, place of worship, nursing home and hospital'),
              'ul_pads_fit_pass': (pads(pas, pad_m2), f'{pad_note}; at least {p["receptor_pass_ft"]:,} ft from every home, school, place of worship, nursing home and hospital'),
              'ul_line_kv_m': (round(pw['line'][0], 1) if pw['line'] else None, pw_note(line_kv, 'line')),
              'ul_sub_kv_m': (round(pw['sub'][0], 1) if pw['sub'] else None, pw_note(sub_kv, 'in-service substation')),
              'ul_sub_115kv_m': (round(pw['head'][0], 1) if pw['head'] else None, pw_note(head_kv, 'in-service substation')),
              'ul_layers': ('; '.join(layers), None)}
    return {'fp': fp, 'values': values, 'layers': layers, 'notes': notes, 'fetched': fetched,
            'blocks': blocks_all, 'review': rev, 'pass': pas, 'homes': hs, 'homes_on_site': hs_on, 'sensitive': sens or [], 'power': pw,
            'setback': fp['m'].difference(interior), 'excluded': {k: v.intersection(fp['m']) for k, v in excl.items()}}


def run(site, cache):
    if PROFILE is None:
        raise SystemExit('usable needs a product profile: run.py --profile Outputs/<batch>/input/thresholds.md')
    r = measure(site, cache, PROFILE)
    fp = r['fp']
    if fp['stage'] == 'failed':
        return [failed(f, SOURCE, LYR, METHOD, r['error']) for f in FIELDS]
    basis_note = f"over the {fp['basis']}" + (' - a stand-in square, not the site' if 'square' in fp['basis'] else '')
    mk = lambda fld, val, n=None: Value(fld, val, SOURCE, LYR, METHOD, fetched_at=r['fetched'],
                                        note='; '.join(x for x in [basis_note, n] + r.get('notes', []) if x))
    out = [mk('ul_basis', fp['basis']), mk('ul_site_acres', round(fp['m'].area / AC, 2))]
    if 'error' in r:
        return out + [failed(f, SOURCE, LYR, METHOD, r['error']) for f in FIELDS[2:-1]] + [mk('ul_layers', '; '.join(r['layers']))]
    vals = []
    for f in FIELDS[2:]:
        v, n = r['values'][f]
        vals.append(mk(f, v, n) if v is not None else absent(f, SOURCE, LYR, METHOD, note=n))
    return out + vals
