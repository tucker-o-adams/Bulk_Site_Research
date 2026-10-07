# -*- coding: utf-8 -*-
"""Site exhibits (PNG) for the sites you pick - not for a whole batch. Flood, wetlands and the parcel
check are always separate exhibits (never one combined map), each drawn at two zooms:

    site       the footprint fills ~65% of the frame (never under 60 m tall - NAIP resolution)
    regional   the footprint plus --buffer-m (400 m) of surroundings

    .venv_fema/Scripts/python.exe scripts/bulk/figure.py Outputs/<batch>/ --only SITE_ID,SITE_ID
        [--layers flood,wetlands,parcels] [--views site,regional] [--buffer-m 400]
        [--basemap naip] [--audience external|internal]

The imagery underneath is a pluggable provider (basemap.py); the overlays are the same on any of
them. --audience external (the default) refuses any provider not cleared for external use; internal
figures are marked "INTERNAL - not for distribution" and written as *_internal.png.

Footprint outline: solid dark red = parcel boundary; dashed grey = the square around the pin, drawn grey
because it is the lower-confidence shape.

The measurements behind them are already in the workbook (the footprint producer's fp_* columns);
this draws them. Generalised from the Site 2 exhibit (out/site2_*.py) to any site in a batch:

    footprint  the shape the fp_* columns were measured over - parcel boundary, or the square
               around the pin when no parcel resolved (200 m, or the stated acreage if larger) (labelled as such on the figure)
    imagery    the --basemap provider (basemap.py); default USGS NAIP, ~0.6 m, in the site's UTM zone
    flood      FEMA NFHL L28 zones for the whole frame (one bounding-box query; the producer's
               1 km answer does not reach the frame corners); ground no zone covers is hatched
    wetlands   USFWS NWI polygons for the frame, filled by wetland type in greens/earth tones (never blue)
    context    Census TIGERweb roads, railroads, streams, water bodies
    parcels    the parcel check (parcel_check.py): a headline banner in the location status colour
               (location_status.py: status, stated vs found acreage, assessment), the broker's pin as a solid
               red dot (precise pins only), the identified parcel, neighbouring parcels labelled with acres and
               owner, and - for an approximate pin that does not match - the candidate parcels of the stated
               size (candidates.py), lettered as in the memo. Its 'site' view frames the parcel, its touching
               neighbours and any candidates; writes <site_id>_parcels_{site,regional}.png and
               <site_id>_parcel_check.json (read by memo.py). A site placed only near a named anchor (L3) gets
               a candidate search when the broker says its tract is identified and states its acreage
               (<site_id>_candidates.json), and a location exhibit only when that leaves a question to ask

The two layers get separate PNGs because they overlap where it matters (riverine wetlands sit
inside the floodplain) and one hides the other. The acreage panel prints the workbook's own fp_*
values, so figure and workbook cannot disagree. Every service answer is cached (data/cache/figure,
data/cache/naip) - a rerun is offline. Run run.py (with the footprint producer) first. Writes
<batch>/figures/<site_id>_{fema_flood,nwi_wetlands}_{site,regional}.png (4800 x 2700 px, 300 dpi,
16:9; *_internal.png for --audience internal) and <site_id>_figures.json (every query URL, basemap).
"""
import argparse, csv, hashlib, json, math, os, re, sys, textwrap, time
from datetime import datetime

import rasterio
import geopandas as gpd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from pyproj import Transformer
from shapely.geometry import box, Point
from shapely.ops import transform, unary_union

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from cache import Cache, coord_key                                      # noqa: E402
from batch_paths import support                                         # noqa: E402
from geom import arcgis_envelope_query                                   # noqa: E402
from producers import flood, footprint, wetlands                         # noqa: E402
from producers import parcel as parcel_mod                               # noqa: E402
import basemap                                                           # noqa: E402
import parcel_check                                                      # noqa: E402
from broker_text import broker_words                                      # noqa: E402
import candidates                                                         # noqa: E402
import location_status                                                    # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
CACHE = os.path.join(ROOT, 'data', 'cache')
TIGER = 'https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb'
CONTEXT = [('roads_primary', 'Transportation', 2), ('roads_secondary', 'Transportation', 6),
           ('roads_local', 'Transportation', 8), ('railroads', 'Transportation', 9),
           ('hydro_linear', 'Hydro', 0), ('hydro_areal', 'Hydro', 1)]
FT = 0.3048
MAP_BOX = (0.005, 0.075, 0.775, 0.915)                       # map axes on the 16 x 9 in figure
ASPECT = (16 * MAP_BOX[2]) / (9 * MAP_BOX[3])                # frame w/h that fills the map box exactly
# Two zooms per exhibit. regional: the footprint plus --buffer-m of surroundings. site: the footprint
# fills SITE_FILL of the frame, but never less than SITE_MIN_H m tall - NAIP is ~0.6 m (0.3 m in some
# newer states), so a tighter frame than that is only enlarged pixels.
VIEWS = ('site', 'regional')
SITE_FILL = 0.65
SITE_MIN_H = 60
RES_M = {'regional': 0.6, 'site': 0.3}                       # requested; the server returns its native best
FP_COLOUR = {True: '#8b0000', False: '#bdbdbd'}              # footprint line: parcel / square around pin (grey = lower confidence)
FP_LABEL = {True: '#8b0000', False: '#6e6e6e'}
INTERNAL_MARK = 'INTERNAL - NOT FOR DISTRIBUTION'


def utm_epsg(la, ln):
    return (32600 if la >= 0 else 32700) + int((ln + 180) // 6) + 1


def frame_bounds(fp_utm, buffer_m=None, fill=None, min_h=0, aspect=None):
    """The map frame, at the map box's aspect: the footprint plus buffer_m, or sized so the footprint
    fills `fill` of the frame's height or width (whichever binds), never under min_h metres tall."""
    aspect = aspect or ASPECT
    minx, miny, maxx, maxy = fp_utm.bounds
    cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
    if fill:
        h = max((maxy - miny) / fill, (maxx - minx) / fill / aspect, min_h)
    else:
        h = max(maxy - miny + 2 * buffer_m, (maxx - minx + 2 * buffer_m) / aspect)
    w = h * aspect
    return cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2


def gdf(features, epsg, frame):
    """GeoJSON features -> GeoDataFrame in UTM, clipped to the frame."""
    feats = [f for f in features or [] if f.get('geometry')]
    if not feats:
        return None
    g = gpd.GeoDataFrame.from_features(feats, crs='EPSG:4326').to_crs(epsg)
    g['geometry'] = g.geometry.make_valid().intersection(frame)
    g = g[~g.geometry.is_empty]
    return g if len(g) else None


def props(r):
    """A GeoDataFrame row as the plain dict footprint.zone_label / is_sfha expect (NaN -> None)."""
    return {k: (None if isinstance(v, float) and math.isnan(v) else v) for k, v in r.items() if k != 'geometry'}


def parse_zones(s):
    """'X 9.708 ac (98.2%); AE 0.176 ac (1.8%)' -> [(label, acres, pct)]"""
    out = []
    for part in (s or '').split('; '):
        m = re.match(r'^(.*) ([\d,.]+) ac \(([\d.]+)%\)$', part.strip())
        if m:
            out.append((m.group(1), float(m.group(2).replace(',', '')), float(m.group(3))))
    return out


def zone_style(label):
    z = label.split()[0]
    if z in flood.SFHA_ZONES:
        return ('#1f6fd0', '\\\\\\' if 'floodway' in label else None, '#0d3f7a',
                f'Zone {label} - 1% annual chance (SFHA)')
    if label == 'X 0.2%':
        return '#8fa9c4', '////', '#5a7692', 'Zone X (shaded) - 0.2% annual chance'
    if z == 'X':
        return '#d9d9d9', None, '#9a9a9a', 'Zone X - minimal flood hazard' + (' (levee)' if 'levee' in label else '')
    if z == 'AREA':
        return '#9e9e9e', 'xxx', '#5e5e5e', 'Area Not Included - not mapped on the FIRM'
    return '#f2e394', None, '#a8963a', f'Zone {label}'


def num(v, d=3):
    try:
        return f'{float(v):,.{d}f}'
    except (TypeError, ValueError):
        return '—'


# NWI wetland types in greens and earth tones - deliberately no blue, so a wetland is never read as a
# flood zone (flood exhibits own the blues: FEMA-style SFHA #1f6fd0, shaded X #8fa9c4). This departs
# from the USFWS Wetlands Mapper legend, which draws Riverine / Pond / Lake in blues.
NWI_COLOURS = {'Riverine': '#1b9e5a', 'Freshwater Pond': '#8fd16a', 'Freshwater Emergent Wetland': '#d4e157',
               'Freshwater Forested/Shrub Wetland': '#1e5631', 'Lake': '#6b8e23',
               'Estuarine and Marine Wetland': '#a1887f', 'Estuarine and Marine Deepwater': '#6d4c41'}
NWI_OTHER = '#c9a227'
LAYERS = ('flood', 'wetlands', 'parcels')
PC_SITE_FILL = 0.85                                          # parcel check: parcel + touching neighbours fill the frame
PC_MAP_BOX = (0.005, 0.075, 0.775, 0.725)                    # parcel check: map below the headline and the broker's-words band
PC_ASPECT = (16 * PC_MAP_BOX[2]) / (9 * PC_MAP_BOX[3])


def prepare(s, fp, buffer_m, cache, broker=None):
    """Everything the exhibits draw, fetched once per site through the cache. Returns (data, error).
    broker: {'acres', 'parent_acres', 'address'} for the parcel check, or None to skip it."""
    sid = s['site_id']; la, ln = float(s['lat']), float(s['lng'])
    epsg = utm_epsg(la, ln)
    to_utm = Transformer.from_crs('EPSG:4326', f'EPSG:{epsg}', always_xy=True).transform
    to_ll = Transformer.from_crs(f'EPSG:{epsg}', 'EPSG:4326', always_xy=True).transform
    fp_utm = transform(to_utm, fp['ll'])
    views = {'regional': frame_bounds(fp_utm, buffer_m=buffer_m),
             'site': frame_bounds(fp_utm, fill=SITE_FILL, min_h=SITE_MIN_H)}
    pc, pc_err = None, None
    if broker is not None:
        pc, pc_err = parcel_check.analyse(s, fp, cache, broker.get('acres'), broker.get('parent_acres'), broker.get('address'),
                                          broker.get('carve_out', False), broker.get('pin_approx', False), broker.get('substation'))
        if pc:
            for n in pc['neighbours']:
                n['utm'] = transform(to_utm, n['geom'])
            cl = (pc.get('candidates') or {}).get('candidates') or []
            for c in cl:
                c['utm'] = transform(to_utm, c['geom'])
            shapes = [fp_utm] + [n['utm'] for n in pc['neighbours'] if n['touches']] + [c['utm'] for c in cl]
            sc = pc.get('substation') or {}
            if cl and sc.get('lat') is not None:
                shapes.append(Point(*to_utm(sc['lng'], sc['lat'])).buffer(60))
            views['parcels_site'] = frame_bounds(unary_union(shapes), fill=PC_SITE_FILL, min_h=SITE_MIN_H, aspect=PC_ASPECT)
            views['parcels_regional'] = frame_bounds(fp_utm, buffer_m=buffer_m, aspect=PC_ASPECT)
    # one set of queries covering both zooms; each view clips from it
    frame = unary_union([box(*b) for b in views.values()]).envelope
    bb_ll = transform(to_ll, frame).bounds
    tag = hashlib.md5(repr([round(v, 6) for v in bb_ll]).encode()).hexdigest()[:10]
    log = {'site_id': sid, 'epsg': epsg, 'views_utm': views, 'query_frame_ll': bb_ll, 'buffer_m': buffer_m,
           'basis': fp['basis'], 'queries': {}}

    def q(producer, name, url):
        resp, fetched, err = cache.get_json(producer, coord_key(la, ln, f'fig_{name}_{tag}'), url)
        log['queries'][name] = {'url': url, 'fetched_at': fetched, 'error': err}
        return (resp or {}).get('features'), err
    zf, ze = q('flood', 'zones', arcgis_envelope_query(f'{flood.NFHL}/28', bb_ll, flood.ZONE_FIELDS))
    wf, we = q('wetlands', 'nwi', arcgis_envelope_query(wetlands.WET, bb_ll, '*'))
    ctx = {}
    for name, svc, lyr in CONTEXT:
        feats, err = q('figure', name, arcgis_envelope_query(f'{TIGER}/{svc}/MapServer/{lyr}', bb_ll, 'NAME,MTFCC'))
        ctx[name] = None if err else feats
    if broker is not None:
        log['parcel_check'] = {'error': pc_err, 'query_bbox': pc and pc['query_bbox']}
    return {'s': s, 'fp': fp, 'epsg': epsg, 'to_utm': to_utm, 'fp_utm': fp_utm, 'views': views,
            'raw_ctx': ctx, 'log': log, 'pc': pc, 'pc_error': pc_err,
            'raw_zones': zf, 'zones_error': ze, 'raw_nwi': wf, 'nwi_error': we}, None


def view(d, name, provider, audience, cache):
    """The prepared data clipped to one zoom, over that zoom's basemap. Returns (view, error)."""
    bounds = d['views'][name]
    frame = box(*bounds)
    epsg, s = d['epsg'], d['s']
    tag = hashlib.md5(repr([round(v, 2) for v in bounds]).encode()).hexdigest()[:10]
    key = f"{s['site_id']}_{name}_{tag}" if provider == 'naip' else f"{provider}_{s['site_id']}_{name}_{tag}"
    bm, err = basemap.get(provider, audience, bounds, epsg, key, RES_M.get(name, RES_M['site']), float(s['lat']), float(s['lng']), cache)
    if err:
        return None, err
    d['log'].setdefault('basemaps', {})[name] = {'provider': provider, 'audience': audience, **bm.meta}
    return {**d, 'view': name, 'bounds': bounds, 'frame': frame, 'img': bm.path, 'basemap': bm, 'audience': audience,
            'ctx': {k: gdf(v, epsg, frame) for k, v in d['raw_ctx'].items()},
            'zones': None if d['zones_error'] else gdf(d['raw_zones'], epsg, frame),
            'nwi': None if d['nwi_error'] else gdf(d['raw_nwi'], epsg, frame)}, None


def draw_flood(ax, d):
    """FEMA zones and unmapped ground; returns the legend entries [(fc, hatch, ec, text)]."""
    zones, frame, epsg = d['zones'], d['frame'], d['epsg']
    present = []
    mapped = None
    if zones is not None:
        for _, r in zones.iterrows():
            unm = str(r['FLD_ZONE']).upper() in footprint.UNMAPPED_ZONES
            fc, hatch, ec, text = zone_style('AREA NOT INCLUDED' if unm else footprint.zone_label(props(r)))
            gpd.GeoSeries([r.geometry], crs=epsg).plot(ax=ax, facecolor=fc, edgecolor=ec, hatch=hatch, alpha=.45, linewidth=.5, zorder=6)
            if text not in [p[3] for p in present]:
                present.append((fc, hatch, ec, text))
        keep = [g for g, z in zip(zones.geometry, zones['FLD_ZONE']) if str(z).upper() not in footprint.UNMAPPED_ZONES]
        mapped = unary_union(keep) if keep else None
    unmapped = frame.difference(mapped) if mapped is not None else frame
    if not unmapped.is_empty and unmapped.area > 1:
        gpd.GeoSeries([unmapped], crs=epsg).plot(ax=ax, facecolor='#9e9e9e', edgecolor='#5e5e5e', hatch='xxx', alpha=.35, linewidth=.4, zorder=6)
        present.append(('#9e9e9e', 'xxx', '#5e5e5e', 'No FEMA flood zone (not studied / not included)'))
    return present


def draw_wetlands(ax, d):
    """NWI polygons filled by Cowardin wetland type (USFWS colours); returns the legend entries."""
    nwi, epsg = d['nwi'], d['epsg']
    present = []
    if nwi is None:
        return present
    col = next((c for c in nwi.columns if c.upper().endswith('WETLAND_TYPE')), None)
    for _, r in nwi.iterrows():
        wt = (r[col] if col else None) or 'Other'
        fc = NWI_COLOURS.get(wt, NWI_OTHER)
        gpd.GeoSeries([r.geometry], crs=epsg).plot(ax=ax, facecolor=fc, edgecolor='#ffffff', alpha=.6, linewidth=.4, zorder=6)
        if wt not in [p[3] for p in present]:
            present.append((fc, None, '#ffffff', wt))
    return present


def sfha_callout(ax, d, hspan):
    zones = d['zones']
    if zones is None:
        return
    sf = [r.geometry for _, r in zones.iterrows() if footprint.is_sfha(props(r))]
    inside = unary_union(sf).intersection(d['fp_utm']) if sf else Point()
    if not inside.is_empty and inside.area > 0:
        s = d['s']
        callout(ax, inside, hspan, f"SFHA in footprint\n{num(s.get('fp_sfha_acres'))} ac ({num(s.get('fp_sfha_pct'), 1)}%)", '#1f6fd0')


def nwi_callout(ax, d, hspan):
    nwi = d['nwi']
    if nwi is None:
        return
    inside = unary_union(list(nwi.geometry)).intersection(d['fp_utm'])
    if not inside.is_empty and inside.area > 0:
        s = d['s']
        callout(ax, inside, hspan, f"NWI wetland in footprint\n{num(s.get('fp_nwi_acres'))} ac ({num(s.get('fp_nwi_pct'), 1)}%)", '#0b7a3e')


def callout(ax, geom, hspan, text, colour):
    p = geom.representative_point()
    ax.annotate(text, xy=(p.x, p.y), xytext=(p.x + 0.22 * hspan, p.y - 0.17 * hspan), ha='center', va='center', fontsize=7.5,
                color='white', zorder=14,
                arrowprops=dict(arrowstyle='-|>', lw=1.4, color=colour, shrinkA=2, shrinkB=2, connectionstyle='arc3,rad=-0.2'),
                bbox=dict(boxstyle='round,pad=0.3', fc=colour, ec='white', alpha=.95, lw=1.0))


def draw_context(ax, c):
    """Census roads, railroads and hydrography under an exhibit."""
    if c['hydro_areal'] is not None: c['hydro_areal'].plot(ax=ax, facecolor='none', edgecolor='#c9d6e3', alpha=.9, linewidth=.6, zorder=7)   # outline only: fills are reserved for flood / wetland
    if c['hydro_linear'] is not None: c['hydro_linear'].plot(ax=ax, color='#2c6fb5', linewidth=1.4, alpha=.85, zorder=3)
    if c['roads_local'] is not None: c['roads_local'].plot(ax=ax, color='#f6e6b4', linewidth=.7, alpha=.75, zorder=4)
    if c['roads_secondary'] is not None: c['roads_secondary'].plot(ax=ax, color='#ffd24d', linewidth=2.4, alpha=.95, zorder=5)
    if c['roads_primary'] is not None: c['roads_primary'].plot(ax=ax, color='#ff9d2e', linewidth=3.4, alpha=.95, zorder=5)
    if c['railroads'] is not None: c['railroads'].plot(ax=ax, color='#3a3a3a', linewidth=1.1, linestyle=(0, (6, 4)), alpha=.9, zorder=4)


def label_lines(ax, g, size, color, bounds, k, n=None, minlen=380):
    """Name the longest road / stream lines inside the frame, rotated along the line."""
    minx, miny, maxx, maxy = bounds
    hspan = maxy - miny
    if g is None or 'NAME' not in g:
        return
    seen = set(); g = g.dropna(subset=['NAME']).copy(); g['len'] = g.length
    m = 0.1 * hspan
    for _, r in g.sort_values('len', ascending=False).iterrows():
        nm = r['NAME']
        if nm in seen or r['len'] < minlen * k or r.geometry.geom_type not in ('LineString', 'MultiLineString'):
            continue
        line = r.geometry if r.geometry.geom_type == 'LineString' else max(r.geometry.geoms, key=lambda x: x.length)
        p = f = None
        for frac in (.5, .35, .65, .25, .75, .15, .85):
            cpt = line.interpolate(frac, normalized=True)
            if minx + m < cpt.x < maxx - m and miny + m < cpt.y < maxy - m:
                p, f = cpt, frac; break
        if p is None:
            continue
        seen.add(nm)
        p0 = line.interpolate(max(f - .08, 0), normalized=True); p1 = line.interpolate(min(f + .08, 1), normalized=True)
        a = math.degrees(math.atan2(p1.y - p0.y, p1.x - p0.x))
        a = a - 180 if a > 90 else (a + 180 if a < -90 else a)
        ax.annotate(nm, (p.x, p.y), rotation=a, rotation_mode='anchor', ha='center', va='center', fontsize=size, color=color,
                    zorder=11, bbox=dict(boxstyle='round,pad=0.15', fc='black', ec='none', alpha=.42))
        if n and len(seen) >= n:
            break


def label_all_lines(ax, c, bounds, k):
    label_lines(ax, c['roads_primary'], 8.5, '#ffe0b0', bounds, k, minlen=300)
    label_lines(ax, c['roads_secondary'], 7.6, '#fff3c4', bounds, k, minlen=300)
    label_lines(ax, c['roads_local'], 5.6, '#f0f0f0', bounds, k, n=24, minlen=330)
    label_lines(ax, c['hydro_linear'], 7.0, '#bfe0ff', bounds, k, minlen=200)


def scale_north(ax, bounds, k):
    """Scale bar (feet) bottom-left and north arrow bottom-right."""
    minx, miny, maxx, maxy = bounds
    span, hspan = maxx - minx, maxy - miny
    sb = min([25, 50, 100, 200, 250, 500, 1000, 1500, 2000, 2500, 3000, 4000], key=lambda v: abs(v - span * 0.20 / FT))
    sbm = sb * FT
    x0 = minx + span * 0.030; y0 = miny + hspan * 0.040; pad = span * 0.022
    ax.add_patch(Rectangle((x0 - pad, y0 - 118 * k), sbm + 2 * pad, 240 * k, fc='white', ec='#333', alpha=.90, lw=.8, zorder=14))
    for i in range(4):
        ax.add_patch(Rectangle((x0 + i * sbm / 4, y0), sbm / 4, 42 * k, fc=('black' if i % 2 == 0 else 'white'), ec='black', lw=.6, zorder=15))
    ax.text(x0, y0 + 54 * k, '0', ha='center', va='bottom', fontsize=6.0, zorder=15)
    ax.text(x0 + sbm, y0 + 54 * k, '%d ft' % sb, ha='center', va='bottom', fontsize=6.0, zorder=15)
    ax.text(x0 + sbm / 2, y0 - 28 * k, '1 in = %d ft at 16x9 full slide' % int(round((span / FT) / (16 * 0.775) / 25) * 25),
            ha='center', va='top', fontsize=5.0, zorder=15, color='#333')
    nx_, ny_ = maxx - span * 0.028, miny + hspan * 0.040
    ax.add_patch(Rectangle((nx_ - 118 * k, ny_ - 27 * k), 236 * k, 378 * k, fc='white', ec='#333', alpha=.90, lw=.8, zorder=14))
    ax.annotate('', xy=(nx_, ny_ + 236 * k), xytext=(nx_, ny_ + 30 * k), arrowprops=dict(arrowstyle='-|>', lw=1.8, color='black'), zorder=15)
    ax.text(nx_, ny_ + 250 * k, 'N', ha='center', va='bottom', fontsize=8.5, fontweight='bold', zorder=15)


def render(d, layer, run, out_dir):
    s, fp, epsg, ctx = d['s'], d['fp'], d['epsg'], d['ctx']
    sid = s['site_id']; la, ln = float(s['lat']), float(s['lng'])
    minx, miny, maxx, maxy = d['bounds']
    span, hspan = maxx - minx, maxy - miny
    k = hspan / 1980.0                  # Site 2 layout was tuned for a ~1,980 m frame height
    is_parcel = fp['basis'] in (footprint.BASIS_PARCEL, footprint.BASIS_OUTLINE)
    fig = plt.figure(figsize=(16, 9), dpi=300)
    ax = fig.add_axes(list(MAP_BOX))
    with rasterio.open(d['img']) as ds:
        ax.imshow(ds.read([1, 2, 3]).transpose(1, 2, 0), extent=(minx, maxx, miny, maxy), origin='upper', interpolation='bilinear')
    ax.set_xlim(minx, maxx); ax.set_ylim(miny, maxy); ax.set_xticks([]); ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_linewidth(1.2); sp.set_color('#222')

    c = ctx
    draw_context(ax, c)

    present = draw_flood(ax, d) if layer == 'flood' else draw_wetlands(ax, d)

    # Footprint: thin line on a thin halo. Parcel = solid dark red; square = dashed grey, the
    # lower-confidence shape (ground around the pin, not a surveyed or assessed boundary).
    fs = gpd.GeoSeries([d['fp_utm']], crs=epsg)
    fs.boundary.plot(ax=ax, color='#ffffff' if is_parcel else '#1a1a1a', linewidth=2.0, zorder=9, alpha=.7 if is_parcel else .5)
    fs.boundary.plot(ax=ax, color=FP_COLOUR[is_parcel], linewidth=1.0, zorder=10,
                     linestyle='-' if is_parcel else (0, (4, 2)))
    px_, py_ = d['to_utm'](ln, la)
    ax.plot([px_], [py_], marker='o', markersize=3.5, markeredgewidth=.8, color='#ffffff', markeredgecolor='#8b0000', zorder=12)
    pminx, pminy, pmaxx, pmaxy = d['fp_utm'].bounds
    title = (f"SITE PARCEL\n{num(s.get('fp_acres'), 2)} ac" if is_parcel
             else f"{s['fp_basis'].upper()} AROUND PIN\n(no parcel) {num(s.get('fp_acres'), 2)} ac")
    # site view: the footprint fills the frame, so the label sits in the top margin, not above the shape
    at, va = (((pminx + pmaxx) / 2, maxy - 0.025 * hspan), 'top') if d['view'] == 'site' else \
             (((pminx + pmaxx) / 2, pmaxy + 0.06 * hspan), 'bottom')
    ax.annotate(title, at, ha='center', va=va, fontsize=10.5, fontweight='bold', color='#ffffff', zorder=13,
                bbox=dict(boxstyle='round,pad=0.35', fc=FP_LABEL[is_parcel], ec='white', alpha=.92, lw=.8))
    (sfha_callout if layer == 'flood' else nwi_callout)(ax, d, hspan)

    label_all_lines(ax, c, d['bounds'], k)
    scale_north(ax, d['bounds'], k)

    # ---- side panel
    pn = fig.add_axes([0.788, 0.075, 0.207, 0.915]); pn.axis('off')
    pn.add_patch(Rectangle((0, 0), 1, 1, transform=pn.transAxes, fc='#f7f7f5', ec='#bbb', lw=1))
    T = pn.transAxes; y = 0.975
    place = ', '.join(x for x in (s.get('city'), s.get('state')) if x)
    county = s.get('parcel_county')
    county = f"{county}{'' if re.search(r'(County|Parish|Borough|city)$', county or '') else ' County'}" if county else None
    heading = 'FEMA FLOOD HAZARD' if layer == 'flood' else 'NWI WETLANDS'
    pn.text(.5, y, heading, ha='center', va='top', fontsize=12.5, fontweight='bold', transform=T); y -= .030
    pn.text(.5, y, f"{sid}  {s.get('name') or ''}".strip(), ha='center', va='top', fontsize=9.5, transform=T); y -= .022
    addr = textwrap.wrap(f"{s.get('address') or ''}{', ' if s.get('address') and place else ''}{place}", 42) or ['']
    pn.text(.5, y, '\n'.join(addr[:2]), ha='center', va='top', fontsize=8, color='#444', transform=T, linespacing=1.2)
    y -= .020 + .016 * (min(len(addr), 2) - 1)
    sub = (f"{county} - Parcel {s.get('parcel_apn') or '(no APN)'}" if is_parcel else
           f"{county + ' - ' if county else ''}no parcel resolved")
    pn.text(.5, y, sub, ha='center', va='top', fontsize=7, color='#444', transform=T); y -= .028
    pn.plot([.05, .95], [y, y], color='#999', lw=.9, transform=T); y -= .026

    pn.text(.05, y, 'FLOOD ZONES PRESENT' if layer == 'flood' else 'NWI WETLAND TYPES PRESENT', ha='left', va='top',
            fontsize=8.5, fontweight='bold', transform=T); y -= .026
    if not present:
        pn.text(.06, y, 'none in the frame' + ('' if layer == 'flood' or not d['nwi_error'] else f" (NWI query failed: {d['nwi_error'][:40]})"),
                ha='left', va='top', fontsize=6.3, transform=T); y -= .030
    for fc, hatch, ec, text in present:
        pn.add_patch(Rectangle((.06, y - .024), .075, .024, transform=T, fc=fc, ec='#666' if layer == 'wetlands' else ec,
                               hatch=hatch, alpha=.75, lw=.8))
        pn.text(.15, y - .006, text, ha='left', va='top', fontsize=6.3, transform=T); y -= .036
    y -= .004
    pn.add_patch(Rectangle((.06, y - .020), .075, .020, transform=T, fc='none', ec=FP_COLOUR[is_parcel] if is_parcel else '#8a8a8a', lw=1.2,
                           ls='-' if is_parcel else '--'))
    pn.text(.15, y - .004, 'Site parcel boundary' if is_parcel else f"{s['fp_basis']} around the pin (not a parcel)",
            ha='left', va='top', fontsize=6.3, transform=T); y -= .028
    for col, lw, ls, lab in [('#ff9d2e', 2.6, '-', 'Interstate / primary road'), ('#ffd24d', 2.2, '-', 'Secondary / arterial road'),
                             ('#f6e6b4', 1.0, '-', 'Local road'), ('#3a3a3a', 1.1, (0, (5, 3)), 'Railroad'),
                             ('#2c6fb5', 1.4, '-', 'Stream / creek (Census)')]:
        pn.plot([.06, .135], [y - .010, y - .010], transform=T, color=col, lw=lw, ls=ls)
        pn.text(.15, y - .002, lab, ha='left', va='top', fontsize=6.3, transform=T); y -= .0215
    pn.add_patch(Rectangle((.06, y - .020), .075, .020, transform=T, fc='none', ec='#8aa0b5', lw=.9))
    pn.text(.15, y - .004, 'Water body outline (Census)', ha='left', va='top', fontsize=6.3, transform=T); y -= .032

    pn.plot([.05, .95], [y, y], color='#999', lw=.9, transform=T); y -= .024
    pn.text(.05, y, 'ACREAGE WITHIN ' + ('PARCEL' if is_parcel else 'SQUARE'), ha='left', va='top', fontsize=8.5, fontweight='bold', transform=T); y -= .026

    def row(label, value, bold=False, color='black'):
        nonlocal y
        pn.text(.05, y, label, ha='left', va='top', fontsize=6.8, transform=T, fontweight='bold' if bold else 'normal', color=color)
        pn.text(.95, y, value, ha='right', va='top', fontsize=6.8, transform=T, fontweight='bold' if bold else 'normal', color=color)
        y -= .020
    row('Total ' + ('parcel' if is_parcel else 'square'), f"{num(s.get('fp_acres'), 2)} ac", bold=True)
    if layer == 'flood':
        for lab, ac, pct in parse_zones(s.get('fp_flood_zones')):
            row(f'Zone {lab}', f'{ac:,.3f} ac ({pct:.1f}%)')
        if float(s.get('fp_flood_unmapped_acres') or 0) >= 0.0005:
            row('No FEMA flood zone', f"{num(s.get('fp_flood_unmapped_acres'))} ac")
        row('SFHA (1% chance)', f"{num(s.get('fp_sfha_acres'))} ac ({num(s.get('fp_sfha_pct'), 1)}%)" if s.get('fp_sfha_acres') else 'n/a - unmapped',
            bold=True, color='#8b0000')
        row('Floodway', f"{num(s.get('fp_floodway_acres'))} ac" if s.get('fp_floodway_acres') else 'n/a')
        row('NWI wetlands (see wetland exhibit)', f"{num(s.get('fp_nwi_acres'))} ac")
    else:
        for lab, ac, pct in parse_zones(s.get('fp_nwi_types')):
            row(lab, f'{ac:,.3f} ac ({pct:.1f}%)')
        row('NWI wetland, total', f"{num(s.get('fp_nwi_acres'))} ac ({num(s.get('fp_nwi_pct'), 1)}%)", bold=True, color='#0b5e30')
        row('SFHA (see flood exhibit)', f"{num(s.get('fp_sfha_acres'))} ac" if s.get('fp_sfha_acres') else 'n/a - unmapped')
    y -= .008

    pn.plot([.05, .95], [y, y], color='#999', lw=.9, transform=T); y -= .022
    if layer == 'flood':
        pn.text(.05, y, 'AT THE PIN / FIRM PANEL', ha='left', va='top', fontsize=8.5, fontweight='bold', transform=T); y -= .022
        pin = (f"Zone {s.get('fema_flood_zone')} {s.get('fema_zone_subtype') or ''}".strip() if s.get('fema_flood_zone')
               else (s.get('fema_determination') or 'unknown').replace('_', ' '))
        second = (f"{s.get('fema_firm_panel')} - eff. {s.get('fema_panel_effective')}" if s.get('fema_firm_panel') else 'no FIRM panel at the pin')
    else:
        pn.text(.05, y, 'AT THE PIN / NWI MAPPING', ha='left', va='top', fontsize=8.5, fontweight='bold', transform=T); y -= .022
        pin = (f"On NWI polygon: {s.get('nwi_type_at_point')} ({s.get('nwi_code_at_point')})" if s.get('nwi_at_point') == 'True'
               else f"Not on an NWI polygon; nearest {num(s.get('nwi_nearest_m'), 0)} m ({s.get('nwi_nearest_type') or '—'})")
        second = (f"Mapping: {s.get('nwi_mapping_status') or 'no status (unmapped?)'}; imagery year {s.get('nwi_image_year') or '—'}")
    pn.text(.05, y, f"{pin}\n{second}", ha='left', va='top', fontsize=6.3, transform=T, linespacing=1.35); y -= .048

    pn.plot([.05, .95], [y, y], color='#999', lw=.9, transform=T); y -= .020
    pn.text(.05, y, 'SOURCES', ha='left', va='top', fontsize=8, fontweight='bold', transform=T); y -= .020
    qz = d['log']['queries']
    parcel_src = (f"Parcel: {s.get('parcel_service_name')}; owner check: {s.get('parcel_owner_check') or 'n/a'}\n"
                  if is_parcel else f"Footprint: no parcel resolved; {s['fp_basis']} centred on the pin\n")
    data_src = (f"Flood zones: FEMA NFHL MapServer L28 (hazards.fema.gov),\nqueried {(qz['zones']['fetched_at'] or '')[:10]}\n"
                if layer == 'flood' else
                f"Wetlands: USFWS National Wetlands Inventory Wetlands\nMapServer, queried {(qz['nwi']['fetched_at'] or '')[:10]}\n")
    src = (data_src + d['basemap'].attribution + '\n'
           f"Roads / hydrography: US Census TIGERweb\n" + parcel_src +
           f"Projection EPSG:{epsg} (UTM, WGS84). Acreage = workbook\nfp_* columns (pin-centred Lambert equal-area).")
    pn.text(.05, y, src, ha='left', va='top', fontsize=4.9, color='#333', transform=T, linespacing=1.3)

    kind = 'FEMA National Flood Hazard Layer - Site Flood Hazard Exhibit' if layer == 'flood' else 'USFWS National Wetlands Inventory - Site Wetlands Exhibit'
    fig.text(.005, .045, f"{kind}  |  {sid}  {s.get('address') or ''} {place}  |  {run['run_at'][:10]} batch  |  "
             f"Prepared {datetime.now().date().isoformat()}", fontsize=7.5, color='#222', ha='left', va='center')
    caveat = ('Parcel geometry is a county/state cadastral layer, not a boundary survey.' if is_parcel else
              f"No parcel boundary: the {s['fp_basis']} describes the ground around the pin, not the site parcel.")
    disclaim = ('Derived from the FEMA NFHL web service for planning screening only. Not a FIRM, not a LOMA/LOMR determination, '
                'and no substitute for the effective printed FIRM panel or an elevation certificate. ' if layer == 'flood' else
                'NWI wetlands are photointerpreted from aerial imagery for planning screening only. Not a jurisdictional determination '
                '(CWA Section 404); a field delineation decides what is regulated. ')
    fig.text(.005, .018, disclaim + caveat, fontsize=5.6, color='#666', ha='left', va='center')
    internal = d['audience'] == 'internal'
    if internal:
        # A standalone PNG has no slide around it, so the marking goes on the image itself - top-left
        # of the map and in the footer. (A generated deck would carry it as slide text instead.)
        ax.text(minx + 0.012 * span, maxy - 0.02 * hspan, INTERNAL_MARK, ha='left', va='top', fontsize=10, fontweight='bold',
                color='white', zorder=20, bbox=dict(boxstyle='square,pad=0.4', fc='#b00020', ec='white', lw=.8, alpha=.95))
        fig.text(.995, .045, INTERNAL_MARK, fontsize=7.5, fontweight='bold', color='#b00020', ha='right', va='center')
    os.makedirs(out_dir, exist_ok=True)
    png = os.path.join(out_dir, f"{sid}_{'fema_flood' if layer == 'flood' else 'nwi_wetlands'}_{d['view']}"
                                f"{'_internal' if internal else ''}.png")
    fig.savefig(png, dpi=300, facecolor='white'); plt.close(fig)
    return png


def draw_broker_words(fig, words, top=0.893, bottom=0.806):
    """The broker's own words about location, in a full-width band under the headline, two columns."""
    fig.patches.append(Rectangle((0.005, bottom), 0.990, top - bottom, transform=fig.transFigure, fc='#fffdf5', ec='#d8cfa8', lw=.8, zorder=0))
    fig.text(0.012, top - 0.010, 'WHAT THE BROKER SAYS ABOUT LOCATION (verbatim, from the broker list)', fontsize=7.2, fontweight='bold', color='#6b5a1e',
             ha='left', va='top')
    if not words:
        fig.text(0.012, top - 0.030, 'No location text in the broker list.', fontsize=6.6, color='#444', ha='left', va='top')
        return
    items = [(lab, textwrap.wrap(f'\u201c{txt}\u201d', 100)) for lab, txt in words]
    total = sum(len(w) + 1 for _, w in items)
    cols, cur, acc = [[], []], 0, 0
    for it in items:
        if cur == 0 and acc + len(it[1]) + 1 > (total + 1) / 2 and cols[0]:
            cur = 1
        cols[cur].append(it); acc += len(it[1]) + 1
    lh, max_lines = 0.0118, int((top - bottom - 0.024) / 0.0118)
    for ci, col_items in enumerate(cols):
        x, y, used = 0.012 + ci * 0.494, top - 0.026, 0
        for lab, lines in col_items:
            room = int(max_lines - used + 0.4)
            if room <= 0:
                fig.text(x, y, '(more in the memo)', fontsize=6.2, color='#888', ha='left', va='top', style='italic'); break
            shown = lines[:room]
            if len(shown) < len(lines):
                shown[-1] = shown[-1][:110] + ' ...'
            fig.text(x, y, lab, fontsize=6.0, color='#6b5a1e', ha='left', va='top', fontweight='bold')
            fig.text(x + 0.105, y, '\n'.join(shown), fontsize=6.4, color='#222', ha='left', va='top', linespacing=1.25)
            y -= lh * (len(shown) + 0.35); used += len(shown) + 0.35


NB_LINE, NB_TOUCH, NB_CAND = '#f2f2f2', '#ffe066', '#ff8c00'      # parcel outlines: other / touching / candidate of the stated size
PIN_RED = '#e00000'


def render_parcels(d, vname, run, out_dir):
    """The parcel check. Headline banner in the location status colour (location_status.py): the status, stated vs found
    acreage, the assessment. Map: the broker's pin (solid red, precise pins only), the identified parcel (dark red),
    neighbours labelled with acres and owner, and - for an approximate pin that does not match - the candidate parcels
    of the stated size, lettered A, B, C to match the memo's question."""
    s, fp, epsg, ctx, pc = d['s'], d['fp'], d['epsg'], d['ctx'], d['pc']
    v = pc['verdict']
    sid = s['site_id']; la, ln = float(s['lat']), float(s['lng'])
    minx, miny, maxx, maxy = d['bounds']
    span, hspan = maxx - minx, maxy - miny
    k = hspan / 1980.0
    frame = d['frame']
    fig = plt.figure(figsize=(16, 9), dpi=300)

    # ---- headline banner, in the location status colour
    fill, ink = location_status.colours(v['status'])
    col = '#' + ink
    fig.patches.append(Rectangle((0.005, 0.900), 0.990, 0.090, transform=fig.transFigure, fc='#' + fill, ec='#bbb', lw=1, zorder=0))
    fig.patches.append(Rectangle((0.005, 0.900), 0.010, 0.090, transform=fig.transFigure, fc=col, ec='none', zorder=1))
    fig.text(0.022, 0.968, f"{sid}  {s.get('name') or ''}", fontsize=12, fontweight='bold', color='#222', ha='left', va='center')
    fig.text(0.995 - 0.008, 0.968, f"Location: {location_status.label(v['status'], v.get('note')).upper()}", fontsize=12, fontweight='bold', color=col,
             ha='right', va='center')
    under = 'under the approximate coordinate' if pc['pin_approx'] else 'under the broker\'s pin'
    fig.text(0.022, 0.941, f"Broker states: {v['stated']}     |     We found {under}: {v['found']}", fontsize=9.2, color='#222', ha='left', va='center')
    head = v.get('headline') or v['assessment']
    fig.text(0.022, 0.914, textwrap.shorten(head, 230, placeholder='...'), fontsize=8.3 if len(head) > 185 else 9.2,
             color=col, ha='left', va='center', fontweight='bold')
    draw_broker_words(fig, d.get('words') or [])

    ax = fig.add_axes(list(PC_MAP_BOX))
    with rasterio.open(d['img']) as ds:
        ax.imshow(ds.read([1, 2, 3]).transpose(1, 2, 0), extent=(minx, maxx, miny, maxy), origin='upper', interpolation='bilinear')
    ax.set_xlim(minx, maxx); ax.set_ylim(miny, maxy); ax.set_xticks([]); ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_linewidth(1.2); sp.set_color('#222')
    draw_context(ax, ctx)

    cl = [c for c in ((pc.get('candidates') or {}).get('candidates') or []) if str(c['apn']) != str(pc['identified']['apn'])]
    cand_apns = {str(c['apn']) for c in cl}
    shown = [n for n in pc['neighbours'] if n['utm'].intersects(frame) and str(n['apn']) not in cand_apns]
    for n in shown:
        c, lw = (NB_TOUCH, .7) if n['touches'] else (NB_LINE, .4)
        gpd.GeoSeries([n['utm']], crs=epsg).boundary.plot(ax=ax, color=c, linewidth=lw, alpha=.95, zorder=7)
    letters = {str(c['apn']): chr(65 + k_) for k_, c in enumerate((pc.get('candidates') or {}).get('candidates') or [])}
    for c in cl:
        gs = gpd.GeoSeries([c['utm']], crs=epsg)
        gs.plot(ax=ax, facecolor=NB_CAND, alpha=.18, edgecolor='none', zorder=6)
        gs.boundary.plot(ax=ax, color=NB_CAND, linewidth=1.8, alpha=.95, zorder=8)
        cp = c['utm'].intersection(frame).representative_point() if not c['utm'].intersection(frame).is_empty else None
        if cp is not None:
            ax.annotate(f"{letters[str(c['apn'])]}  {c['acres']:,.1f} ac\n{textwrap.shorten(c['owner'] or '(no owner)', 26, placeholder='...')}", (cp.x, cp.y),
                        ha='center', va='center', fontsize=6.4, color='white', zorder=12, fontweight='bold',
                        bbox=dict(boxstyle='round,pad=0.25', fc=NB_CAND, ec='white', alpha=.9, lw=.7))
    lab = [n for n in shown if n['same_owner'] or (vname == 'site' and (n['touches'] or n['utm'].area > 0.02 * span * hspan))]
    lab = sorted(lab, key=lambda n: (not n['same_owner'], -n['acres']))[:30]
    m = 0.03
    for n in lab:
        vis = n['utm'].intersection(frame)
        if vis.is_empty:
            continue
        p = vis.representative_point()
        if not (minx + m * span < p.x < maxx - m * span and miny + m * hspan < p.y < maxy - m * hspan):
            continue
        owner = textwrap.shorten(n['owner'] or '(no owner)', 26, placeholder='...')
        tag = ' - same owner' if n['same_owner'] else ''
        ax.annotate(f"{n['acres']:,.1f} ac{tag}\n{owner}", (p.x, p.y), ha='center', va='center', fontsize=5.6 if vname == 'site' else 4.8,
                    color='white', zorder=11, bbox=dict(boxstyle='round,pad=0.2', fc='#1a1a1a', ec='none', alpha=.62))
    fs = gpd.GeoSeries([d['fp_utm']], crs=epsg)
    fs.boundary.plot(ax=ax, color='#ffffff', linewidth=3.6, zorder=9, alpha=.8)          # thick, so the site reads at a glance
    fs.boundary.plot(ax=ax, color=FP_COLOUR[True], linewidth=2.2, zorder=10)
    ip = d['fp_utm'].intersection(frame).representative_point()
    ax.annotate(f"IDENTIFIED PARCEL {pc['identified']['acres']:,.2f} ac", (ip.x, ip.y), xytext=(0, -14), textcoords='offset points', ha='center', va='center',
                fontsize=7.5, fontweight='bold', color='#ffffff', zorder=13, bbox=dict(boxstyle='round,pad=0.25', fc=FP_LABEL[True], ec='white', alpha=.9, lw=.7))
    sc = pc.get('substation') or {}
    if sc.get('lat') is not None:            # the substation the broker names (HIFLD point)
        sx, sy = d['to_utm'](sc['lng'], sc['lat'])
        if minx < sx < maxx and miny < sy < maxy:
            ax.plot([sx], [sy], marker='s', markersize=8, color='#7b1fa2', markeredgecolor='white', markeredgewidth=1.0, zorder=14)
            ax.annotate(f"{sc.get('hifld') or sc['name']} substation (HIFLD)", (sx, sy), xytext=(8, 6), textcoords='offset points', fontsize=6.4,
                        fontweight='bold', color='white', zorder=14, bbox=dict(boxstyle='round,pad=0.2', fc='#7b1fa2', ec='none', alpha=.85))
    if not pc['pin_approx']:                # a point is marked only when the broker gave a precise one
        px_, py_ = d['to_utm'](ln, la)
        ax.plot([px_], [py_], marker='o', markersize=7, markeredgewidth=1.0, color=PIN_RED, markeredgecolor='white', zorder=14)
    label_all_lines(ax, ctx, d['bounds'], k)
    scale_north(ax, d['bounds'], k)

    # ---- side panel: the evidence behind the headline
    pn = fig.add_axes([0.788, 0.075, 0.207, 0.725]); pn.axis('off')
    pn.add_patch(Rectangle((0, 0), 1, 1, transform=pn.transAxes, fc='#f7f7f5', ec='#bbb', lw=1))
    T = pn.transAxes; y = 0.972
    idf = pc['identified']

    def row(label, value, bold=False, color='black', wrap=34):
        nonlocal y
        lines = textwrap.wrap(str(value), wrap) or ['']
        pn.text(.05, y, label, ha='left', va='top', fontsize=6.6, transform=T, fontweight='bold' if bold else 'normal', color=color)
        pn.text(.95, y, '\n'.join(lines[:3]), ha='right', va='top', fontsize=6.6, transform=T, fontweight='bold' if bold else 'normal', color=color, linespacing=1.25)
        y -= .021 * min(len(lines), 3) + .003

    def heading(text):
        nonlocal y
        pn.text(.05, y, text, ha='left', va='top', fontsize=8.3, fontweight='bold', transform=T); y -= .027

    def rule():
        nonlocal y
        pn.plot([.05, .95], [y, y], color='#999', lw=.9, transform=T); y -= .024

    county = s.get('parcel_county') or ''
    heading('IDENTIFIED PARCEL')
    row('APN', f"{idf['apn'] or '(none)'} ({county}{'' if county.endswith('County') else ' County'})", wrap=30)
    row('Acreage (from geometry)', f"{idf['acres']:,.2f} ac", bold=True, color='#8b0000')
    row('Owner of record', idf['owner'] or '(none in the record)', wrap=30)
    row('Situs address', idf['address'] if re.sub(r'[\s,]', '', idf['address'] or '') else '(none in the record)', wrap=30)
    row('Parcels at the pin', f"{idf['hits_at_pin']}" + (' (overlapping)' if idf['hits_at_pin'] > 1 else ''))
    if idf['internal_only']:
        row('Parcel data', 'INTERNAL USE ONLY (licensed county)', color='#b00020', wrap=30)
    rule()
    heading('BROKER STATES')
    row('Site acreage', f"{pc['broker_acres']:,.2f} ac" if pc['broker_acres'] else 'not stated', bold=True)
    if pc['parent_acres']:
        row('Parent tract', f"{pc['parent_acres']:,.1f} ac")
    if pc['carve_out']:
        row('Described as', 'a carve-out of a larger tract', wrap=30)
    if pc['pin_approx']:
        row('Pin', 'marked approximate by the broker', wrap=30)
    if pc['listing_address']:
        am = pc['address_match'] or {}
        row('Listing address', pc['listing_address'], wrap=30)
        row('...carried by', am.get('where', '-'), wrap=30)
    rule()
    allc = (pc.get('candidates') or {}).get('candidates') or []
    if allc:
        heading('CANDIDATES (STATED SIZE, +/-15 %)')
        for c in allc:
            row(f"{letters[str(c['apn'])]}  APN {c['apn']}", f"{c['acres']:,.1f} ac" + (' (under the coordinate)' if str(c['apn']) == str(idf['apn']) else '')
                + (f"; {c['sub_m']:,} m to substation" if c.get('sub_m') is not None else ''), wrap=30, color='#b35f00')
    else:
        heading('ADJACENT PARCELS')
        touch = [n for n in pc['neighbours'] if n['touches']]
        same = [n for n in touch if n['same_owner']]
        row('Touching the parcel', f"{len(touch)}")
        row('Same owner, touching', ', '.join(f"{n['acres']:,.1f} ac" for n in same[:6]) or 'none', wrap=30)
    sc = pc.get('substation')
    if sc:
        rule()
        heading('SUBSTATION CHECK')
        claim = ('adjacent' if sc.get('claim') == 'adjacent' else f"~{sc['stated_mi']:g} mi" if sc.get('stated_mi') else 'named')
        row('Broker says', f"{claim}: {sc['name']}", wrap=30)
        if sc.get('identified'):
            row('HIFLD substation', sc.get('hifld') or '-', wrap=30)
            row('To identified parcel', f"{sc['identified']['dist_m']:,} m" + (' (adjacent)' if sc['identified']['adjacent'] else ''), wrap=30)
            if sc.get('likely'):
                row('To likely parcel', f"{sc['likely']['dist_m']:,} m" + (' (adjacent)' if sc['likely']['adjacent'] else ''), wrap=30)
        pn.text(.05, y, '\n'.join(textwrap.wrap(sc['text'], 52)[:3]), ha='left', va='top', fontsize=6.0, transform=T, linespacing=1.25,
                color={'identified': '#2e7d32', 'likely': '#2e7d32', 'near': '#b26a00'}.get(sc.get('supports'), '#b00020')); y -= .019 * min(3, len(textwrap.wrap(sc['text'], 52))) + .006
    rule()
    for fc, ec, ls, lw, text in [('none', FP_COLOUR[True], '-', 2.0, 'Identified parcel (the workbook uses this one)')] + \
                                ([(NB_CAND, NB_CAND, '-', 1.6, 'Candidate: parcel of the stated size (+/-15 %)')] if allc else []) + \
                                [('none', NB_TOUCH, '-', .9, 'Parcel touching the identified parcel'),
                                 ('none', '#9a9a9a', '-', .6, 'Other parcel')]:
        pn.add_patch(Rectangle((.06, y - .018), .075, .018, transform=T, fc=fc, ec=ec, ls=ls, lw=lw, alpha=.5 if fc != 'none' else 1))
        pn.text(.15, y - .003, text, ha='left', va='top', fontsize=6.1, transform=T); y -= .026
    if (pc.get('substation') or {}).get('lat') is not None:
        pn.plot([.0975], [y - .008], transform=T, marker='s', markersize=5, color='#7b1fa2', markeredgecolor='white', markeredgewidth=.8)
        pn.text(.15, y - .003, 'Substation the broker names (HIFLD, 2021)', ha='left', va='top', fontsize=6.1, transform=T); y -= .026
    if pc['pin_approx']:
        pn.text(.06, y - .003, "No point marked: the broker's coordinate is approximate.\nThe identified parcel is the one under it.", ha='left', va='top',
                fontsize=6.1, transform=T, color='#b26a00', linespacing=1.3); y -= .036
    else:
        pn.plot([.0975], [y - .008], transform=T, marker='o', markersize=5, color=PIN_RED, markeredgecolor='white', markeredgewidth=.8)
        pn.text(.15, y - .003, "Broker's pin (the precise coordinate given)", ha='left', va='top', fontsize=6.1, transform=T); y -= .026
    pn.text(.06, y - .002, 'Labels: acres / owner of record', ha='left', va='top', fontsize=5.8, color='#555', transform=T); y -= .026
    rule()
    src = (f"Parcels: {pc['service']}, queried {(pc['fetched_at'] or '')[:10]}\n" + d['basemap'].attribution + '\n'
           f"Roads / hydrography: US Census TIGERweb\nAcres from the parcel geometry (ellipsoidal); the broker's\n"
           f"figures and pin are from the broker list. Match = within 15 %.")
    pn.text(.05, y, src, ha='left', va='top', fontsize=4.9, color='#333', transform=T, linespacing=1.3)

    place = ', '.join(x for x in (s.get('county'), s.get('state')) if x)
    fig.text(.005, .045, f"Parcel check exhibit  |  {sid}  {place}  |  {run['run_at'][:10]} batch  |  Prepared {datetime.now().date().isoformat()}",
             fontsize=7.5, color='#222', ha='left', va='center')
    fig.text(.005, .018, 'Parcel geometry is a county/state cadastral layer, not a boundary survey. Candidates rest on acreage and location only; none is '
             'chosen by the tool. Confirm the site with the broker, the deed or the appraisal district.', fontsize=5.6, color='#666', ha='left', va='center')
    internal = d['audience'] == 'internal'
    if internal:
        ax.text(minx + 0.012 * span, maxy - 0.02 * hspan, INTERNAL_MARK, ha='left', va='top', fontsize=10, fontweight='bold',
                color='white', zorder=20, bbox=dict(boxstyle='square,pad=0.4', fc='#b00020', ec='white', lw=.8, alpha=.95))
        fig.text(.995, .045, INTERNAL_MARK, fontsize=7.5, fontweight='bold', color='#b00020', ha='right', va='center')
    os.makedirs(out_dir, exist_ok=True)
    png = os.path.join(out_dir, f"{sid}_parcels_{vname}{'_internal' if internal else ''}.png")
    fig.savefig(png, dpi=300, facecolor='white'); plt.close(fig)
    return png


CLUE_WORDS = {'coordinate': 'coordinate', 'coordinate_approx': 'approximate coordinate', 'apn': 'parcel number', 'street_address': 'street address',
              'intersection': 'intersection', 'substation_name': 'substation', 'substation_planned': 'planned substation', 'landmark': 'landmark',
              'owner_name': 'owner / tract name', 'corridor': 'corridor', 'area_name': 'area name', 'city': 'city', 'zip': 'ZIP', 'county': 'county',
              'utility': 'serving utility', 'acreage': 'acreage'}
TIER_WORDS = {'L3': 'near a named substation, intersection or landmark', 'L4': 'within a ZIP code', 'L5': 'within a county'}


def render_area(batch, s, provider, audience, run, cache, out_dir, cands=None, status=None):
    """Where a site could be, for a site the broker places only loosely (location tier L3-L5): no point and no parcel
    are marked. Shows the anchor the tool placed it by (a named substation or an intersection), the uncertainty circle,
    the broker's ZIP boundary, nearby substations, and every location clue the broker gave. Returns (png, error)."""
    import locate
    sid, tier = s['site_id'], s['location_tier'].upper()
    la, ln = float(s['lat']), float(s['lng'])
    r_m = float(s.get('location_radius_m') or 2000)
    clues = []
    cl = os.path.join(batch, 'input', 'clues_checked.csv')
    if os.path.exists(cl):
        clues = [r for r in csv.DictReader(open(cl, encoding='utf-8-sig')) if r['site_id'] == sid]
    epsg = utm_epsg(la, ln)
    to_utm = Transformer.from_crs('EPSG:4326', f'EPSG:{epsg}', always_xy=True).transform
    to_ll = Transformer.from_crs(f'EPSG:{epsg}', 'EPSG:4326', always_xy=True).transform
    cx, cy = to_utm(ln, la)
    cl = (cands or {}).get('candidates') or []
    ctx_parcels = (cands or {}).get('context') or []
    for c in cl + ctx_parcels:
        c['utm'] = transform(to_utm, c['geom'])
    owner_kind = (cands or {}).get('kind') == 'owner'
    if cands and not owner_kind:    # the searched area, not the anchor's full uncertainty circle
        r_m = cands['areas'][0][2]
    shapes = [Point(cx, cy).buffer(r_m)] + [c['utm'] for c in cl]
    zipc = next((c['value'] for c in clues if c['clue_type'] == 'zip'), None)
    zpoly = None
    if zipc:
        z = locate.Resolver(cache, (s.get('state') or 'TX').upper()).zcta(zipc)
        if z and z.get('rings'):
            from shapely.geometry import Polygon
            zpoly = unary_union([Polygon([to_utm(x, y) for x, y in ring]) for ring in z['rings']]).buffer(0)
            if tier != 'L3':
                shapes.append(zpoly)
    if owner_kind and cl:           # frame the candidates (with room around them), not the whole ZIP
        shapes = [c['utm'].buffer(350) for c in cl]
    bounds = frame_bounds(unary_union(shapes), fill=0.86, min_h=SITE_MIN_H, aspect=PC_ASPECT)
    minx, miny, maxx, maxy = bounds
    span, hspan = maxx - minx, maxy - miny
    k = hspan / 1980.0
    frame = box(*bounds)
    bb_ll = transform(to_ll, frame).bounds
    tag = hashlib.md5(repr([round(v, 5) for v in bb_ll]).encode()).hexdigest()[:10]
    raw = {}
    for name, svc, lyr in CONTEXT:
        resp, _, err = cache.get_json('figure', coord_key(la, ln, f'fig_{name}_{tag}'), arcgis_envelope_query(f'{TIGER}/{svc}/MapServer/{lyr}', bb_ll, 'NAME,MTFCC'))
        raw[name] = None if err else (resp or {}).get('features')
    ctx = {k_: gdf(v, epsg, frame) for k_, v in raw.items()}
    sp = cache.path('substations', coord_key(la, ln, 'r15000'))          # the substations producer's 15 km answer
    bm, err = basemap.get(provider, audience, bounds, epsg, f"{sid}_area_{tag}", max(0.6, span / 5000), la, ln, cache)
    if err:
        return None, err
    fig = plt.figure(figsize=(16, 9), dpi=300)
    st = status or {'status': 'not_locatable', 'note': ''}
    fill, ink = location_status.colours(st['status'])
    col = '#' + ink
    fig.patches.append(Rectangle((0.005, 0.900), 0.990, 0.090, transform=fig.transFigure, fc='#' + fill, ec='#bbb', lw=1, zorder=0))
    fig.patches.append(Rectangle((0.005, 0.900), 0.010, 0.090, transform=fig.transFigure, fc=col, ec='none', zorder=1))
    fig.text(0.018, 0.968, f"{sid}  {s.get('name') or ''}", fontsize=12, fontweight='bold', color='#222', ha='left', va='center')
    basis = s.get('location_basis') or ''
    known = ('near a named substation' if basis.startswith('HIFLD substation') else 'near an intersection' if basis.startswith('TIGER roads')
             else 'near a landmark' if tier == 'L3' else TIER_WORDS.get(tier, ''))
    fig.text(0.987, 0.968, f"Location: {location_status.label(st['status'], st.get('note')).upper()} ({known})", fontsize=12, fontweight='bold', color=col,
             ha='right', va='center')
    gave = '; '.join(f"{CLUE_WORDS.get(c['clue_type'], c['clue_type'])} \"{c['quote']}\"" for c in clues
                     if c['clue_type'] in ('substation_name', 'substation_planned', 'intersection', 'landmark', 'owner_name', 'corridor', 'area_name', 'zip', 'city'))
    fig.text(0.018, 0.941, textwrap.shorten(f"Broker gives no coordinate or parcel, only: {gave or 'county'}", 250, placeholder='...'),
             fontsize=9.0, color='#222', ha='left', va='center')
    where = (f"placed it by {basis.replace('HIFLD substation ', 'substation ').split(' (')[0]}; the site could be anywhere within about {r_m / 1000:,.1f} km" if tier == 'L3'
             else f"know only the ZIP ({zipc}); the site could be anywhere in it")
    fig.text(0.018, 0.914, textwrap.shorten(st.get('headline') or st.get('assessment') if cl else f"We {where}. No point or parcel is marked, so parcel, flood, wetland and neighbour "
                                            "checks are not possible.", 205, placeholder='...'), fontsize=9.0, color=col, ha='left', va='center', fontweight='bold')
    draw_broker_words(fig, broker_words(batch, sid))
    ax = fig.add_axes(list(PC_MAP_BOX))
    with rasterio.open(bm.path) as ds:
        ax.imshow(ds.read([1, 2, 3]).transpose(1, 2, 0), extent=(minx, maxx, miny, maxy), origin='upper', interpolation='bilinear')
    ax.set_xlim(minx, maxx); ax.set_ylim(miny, maxy); ax.set_xticks([]); ax.set_yticks([])
    for spn in ax.spines.values():
        spn.set_linewidth(1.2); spn.set_color('#222')
    draw_context(ax, ctx)
    if zpoly is not None:
        gpd.GeoSeries([zpoly.boundary], crs=epsg).plot(ax=ax, color='#1a1a1a', linewidth=2.2, alpha=.5, zorder=8)
        gpd.GeoSeries([zpoly.boundary], crs=epsg).plot(ax=ax, color='#ffffff', linewidth=1.1, linestyle=(0, (6, 3)), zorder=9)
        zp = zpoly.intersection(frame)
        if not zp.is_empty:
            if tier == 'L3':           # on the boundary, as far from the anchor as the frame allows, so it never covers it
                bd = zpoly.boundary
                pts = [bd.interpolate(f, normalized=True) for f in [i / 200 for i in range(200)]]
                pts = [q for q in pts if minx + .08 * span < q.x < maxx - .08 * span and miny + .08 * hspan < q.y < maxy - .08 * hspan]
                pz = max(pts, key=lambda q: math.hypot(q.x - cx, q.y - cy)) if pts else Point(maxx - 0.12 * span, maxy - 0.06 * hspan)
            else:
                pz = Point(maxx - 0.12 * span, maxy - 0.06 * hspan)
            ax.annotate(f"ZIP {zipc} (broker's)", (pz.x, pz.y), ha='center', va='center', fontsize=7, color='white', zorder=12,
                        bbox=dict(boxstyle='round,pad=0.2', fc='#1a1a1a', ec='none', alpha=.6))
    for c in ctx_parcels:           # the same owner's other parcels: a larger one may hold the tract as a carve-out
        vis = c['utm'].intersection(frame)
        if vis.is_empty:
            continue
        gpd.GeoSeries([c['utm']], crs=epsg).boundary.plot(ax=ax, color=NB_CAND, linewidth=1.0, linestyle=(0, (4, 3)), zorder=9)
        cp = vis.representative_point()
        ax.annotate(f"{c['tract']}: {c['acres']:,.1f} ac", (cp.x, cp.y), ha='center', va='center', fontsize=5.8, color='white', zorder=12,
                    bbox=dict(boxstyle='round,pad=0.2', fc='#1a1a1a', ec='none', alpha=.6))
    if owner_kind:
        for k_, c in enumerate(cl):
            gs = gpd.GeoSeries([c['utm']], crs=epsg)
            gs.plot(ax=ax, facecolor=NB_CAND, alpha=.3, edgecolor='none', zorder=7)
            gs.boundary.plot(ax=ax, color=NB_CAND, linewidth=1.8, zorder=10)
            cp = c['utm'].representative_point()
            top = c['utm'].bounds[3]
            ax.annotate(f"{chr(65 + k_)}  {c['tract']}? {c['acres']:,.1f} ac\n{textwrap.shorten(c['owner'], 30, placeholder='...')}", (cp.x, cp.y),
                        xytext=(cp.x, top + 0.06 * hspan), ha='center', va='bottom', fontsize=6.6, fontweight='bold', color='white', zorder=13,
                        bbox=dict(boxstyle='round,pad=0.25', fc=NB_CAND, ec='white', alpha=.9, lw=.7),
                        arrowprops=dict(arrowstyle='-', color=NB_CAND, lw=1.2))
    if tier == 'L3':
        circ = gpd.GeoSeries([Point(cx, cy).buffer(r_m)], crs=epsg)
        circ.plot(ax=ax, facecolor='#ff8c00', alpha=.10, edgecolor='none', zorder=6)
        circ.boundary.plot(ax=ax, color='#ff8c00', linewidth=1.4, linestyle=(0, (5, 3)), zorder=9)
        ax.annotate(f"site probably within ~{r_m / 1000:,.1f} km of the anchor", (cx, cy + r_m), xytext=(0, 6), textcoords='offset points',
                    ha='center', va='bottom', fontsize=7.5, color='white', zorder=12, bbox=dict(boxstyle='round,pad=0.2', fc='#b26a00', ec='none', alpha=.85))
        for k_, c in enumerate(cl):
            gs = gpd.GeoSeries([c['utm']], crs=epsg)
            gs.plot(ax=ax, facecolor=NB_CAND, alpha=.25, edgecolor='none', zorder=7)
            gs.boundary.plot(ax=ax, color=NB_CAND, linewidth=1.8, zorder=10)
            cp = c['utm'].representative_point()
            ax.annotate(f"{chr(65 + k_)}  {c['acres']:,.1f} ac", (cp.x, cp.y), ha='center', va='center', fontsize=7, fontweight='bold', color='white', zorder=13,
                        bbox=dict(boxstyle='round,pad=0.25', fc=NB_CAND, ec='white', alpha=.9, lw=.7))
        is_sub = (s.get('location_basis') or '').startswith('HIFLD substation')
        ax.plot([cx], [cy], marker='s' if is_sub else 'X', markersize=9, color='#7b1fa2', markeredgecolor='white', markeredgewidth=1.0, zorder=14)
        ax.annotate(('ANCHOR: ' + s['location_basis'].replace('HIFLD substation ', 'substation ')) if is_sub else f"ANCHOR: {s.get('location_basis')}",
                    (cx, cy), xytext=(10, -10), textcoords='offset points', ha='left', va='top', fontsize=7.5, fontweight='bold', color='white', zorder=14,
                    bbox=dict(boxstyle='round,pad=0.25', fc='#7b1fa2', ec='white', alpha=.9, lw=.7))
    if os.path.exists(sp):
        feats = (json.load(open(sp, encoding='utf-8')).get('response') or {}).get('features') or []
        for f in feats:
            g = f.get('geometry') or {}
            if g.get('type') != 'Point':
                continue
            x, y = to_utm(*g['coordinates'][:2])
            if not (minx < x < maxx and miny < y < maxy) or math.hypot(x - cx, y - cy) < 30:
                continue
            p = f.get('properties') or {}
            kv = p.get('MAX_VOLT')
            ax.plot([x], [y], marker='s', markersize=4.5, color='#ffd400', markeredgecolor='#333', markeredgewidth=.6, zorder=12)
            ax.annotate(f"{(p.get('NAME') or '')[:22]}{f' {kv:g} kV' if isinstance(kv, (int, float)) and kv > 0 else ''}", (x, y), xytext=(5, 3),
                        textcoords='offset points', fontsize=5.2, color='white', zorder=12, bbox=dict(boxstyle='round,pad=0.15', fc='black', ec='none', alpha=.5))
    label_all_lines(ax, ctx, bounds, k)
    scale_north(ax, bounds, k)

    pn = fig.add_axes([0.788, 0.075, 0.207, 0.725]); pn.axis('off')
    pn.add_patch(Rectangle((0, 0), 1, 1, transform=pn.transAxes, fc='#f7f7f5', ec='#bbb', lw=1))
    T = pn.transAxes; y = 0.972
    pn.text(.05, y, 'WHAT THE BROKER GAVE', ha='left', va='top', fontsize=8.3, fontweight='bold', transform=T); y -= .028
    for c in clues:
        if c['clue_type'] in ('state',):
            continue
        txt = f"{CLUE_WORDS.get(c['clue_type'], c['clue_type'])}: \"{c['quote']}\""
        lines = textwrap.wrap(txt, 48)
        pn.text(.06, y, '\n'.join(lines[:2]), ha='left', va='top', fontsize=6.2, transform=T, linespacing=1.25); y -= .019 * min(len(lines), 2) + .005
    pn.plot([.05, .95], [y, y], color='#999', lw=.9, transform=T); y -= .024
    pn.text(.05, y, 'HOW WE PLACED IT', ha='left', va='top', fontsize=8.3, fontweight='bold', transform=T); y -= .028
    for txt in ((f"{tier}: {basis}", s.get('location_check') or '', f"uncertainty radius ~{r_m:,.0f} m") if tier == 'L3'
                else (f"{tier}: ZIP {zipc} only", 'the whole ZIP is the uncertainty; no point is used for parcel checks')):
        lines = textwrap.wrap(txt, 48)
        pn.text(.06, y, '\n'.join(lines[:3]), ha='left', va='top', fontsize=6.2, transform=T, linespacing=1.25); y -= .019 * min(len(lines), 3) + .005
    unres = [u for u in (s.get('location_unresolved') or '').split(' | ') if u and not u.endswith('context only')
             and not (owner_kind and u.startswith('owner/tract name'))]            # searched: the candidates are the answer
    if unres:
        pn.plot([.05, .95], [y, y], color='#999', lw=.9, transform=T); y -= .024
        pn.text(.05, y, 'CLUES WE COULD NOT PLACE', ha='left', va='top', fontsize=8.3, fontweight='bold', transform=T); y -= .028
        for u in unres[:4]:
            lines = textwrap.wrap(u, 50)
            pn.text(.06, y, '\n'.join(lines[:3]), ha='left', va='top', fontsize=6.0, transform=T, linespacing=1.25); y -= .018 * min(len(lines), 3) + .006
    pn.plot([.05, .95], [y, y], color='#999', lw=.9, transform=T); y -= .022
    legend = []
    if tier == 'L3':
        legend += [('marker', 's', '#7b1fa2', 'Anchor the site was placed by'), ('patch', '#ff8c00', '--', f'Area searched (~{r_m / 1000:,.1f} km)' if cands else
                                                                                   f'Where the site could be (~{r_m / 1000:,.1f} km)')]
        if cl:
            legend += [('patch', NB_CAND, '-', 'Candidate: parcel of the stated size (+/-15 %)')]
    if owner_kind:
        legend += [('patch', NB_CAND, '-', 'Candidate: parcel under the tract name, stated size (+/-15 %)'),
                   ('line', NB_CAND, '--', 'Other parcel under the same name (context)')]
    legend += [('line', '#ffffff', '--', "Broker's ZIP boundary"), ('marker', 's', '#ffd400', 'Other substations (HIFLD, 2021)')]
    for kind, a1, a2, text in legend:
        if kind == 'marker':
            pn.plot([.0975], [y - .008], transform=T, marker=a1, markersize=5, color=a2, markeredgecolor='#333', markeredgewidth=.6)
        elif kind == 'patch':
            pn.add_patch(Rectangle((.06, y - .018), .075, .018, transform=T, fc=a1, ec=a1, ls=a2, lw=1.2, alpha=.4))
        else:
            pn.plot([.06, .135], [y - .009, y - .009], transform=T, color='#555', lw=1.2, ls=a2)
        pn.text(.15, y - .003, text, ha='left', va='top', fontsize=6.1, transform=T); y -= .026
    pn.text(.06, y - .002, 'No point is marked: the broker gave none.' + ('\nCandidates are lettered as in the memo; none is chosen.' if cl else ''),
            ha='left', va='top', fontsize=6.1, color='#b00020', transform=T, linespacing=1.3); y -= .030 + (.016 if cl else 0)
    pn.text(.05, y, bm.attribution + '\nRoads / hydrography: US Census TIGERweb; ZIP: Census ZCTA 2020\nSubstations: HIFLD (2021 layer)',
            ha='left', va='top', fontsize=4.9, color='#333', transform=T, linespacing=1.3)
    fig.text(.005, .045, f"Location exhibit (no parcel)  |  {sid}  {s.get('county') or ''} {s.get('state') or ''}  |  {run['run_at'][:10]} batch  |  "
             f"Prepared {datetime.now().date().isoformat()}", fontsize=7.5, color='#222', ha='left', va='center')
    fig.text(.005, .018, 'The broker list gives no coordinate or parcel for this site. ' +
             ('The anchor and circle show how the tool placed it for power and market context only; they are not the site.' if tier == 'L3' else
              'The ZIP boundary is the only location given; values for this site are measured from the ZIP centre for market context only.'),
             fontsize=5.6, color='#666', ha='left', va='center')
    internal = audience == 'internal'
    if internal:
        ax.text(minx + 0.012 * span, maxy - 0.02 * hspan, INTERNAL_MARK, ha='left', va='top', fontsize=10, fontweight='bold',
                color='white', zorder=20, bbox=dict(boxstyle='square,pad=0.4', fc='#b00020', ec='white', lw=.8, alpha=.95))
        fig.text(.995, .045, INTERNAL_MARK, fontsize=7.5, fontweight='bold', color='#b00020', ha='right', va='center')
    os.makedirs(out_dir, exist_ok=True)
    png = os.path.join(out_dir, f"{sid}_location{'_internal' if internal else ''}.png")
    fig.savefig(png, dpi=300, facecolor='white'); plt.close(fig)
    return png, None


def hifld_substation(s, name):
    """The HIFLD substation matching a broker-named substation near the pin (the substations producer's cached 15 km answer)."""
    toks = [w for w in re.findall(r'[a-z]+', name.lower()) if len(w) > 2 and w not in ('road', 'sub', 'substation', 'new')]
    la, ln = float(s['lat']), float(s['lng'])
    f = Cache(CACHE, offline=True).path('substations', coord_key(la, ln, 'r15000'))
    if not toks or not os.path.exists(f):
        return {'lat': None, 'lng': None, 'hifld': None}
    best = None
    for feat in (json.load(open(f, encoding='utf-8')).get('response') or {}).get('features') or []:
        g, pr = feat.get('geometry') or {}, feat.get('properties') or {}
        if g.get('type') != 'Point' or not any(w in (pr.get('NAME') or '').lower() for w in toks):
            continue
        x, y = g['coordinates'][:2]
        d = math.hypot((x - ln) * 111320 * math.cos(math.radians(la)), (y - la) * 110540)
        if best is None or d < best[0]:
            best = (d, x, y, pr.get('NAME'))
    return {'lat': best[2], 'lng': best[1], 'hifld': best[3]} if best else {'lat': None, 'lng': None, 'hifld': None}


def owner_tracts(batch, sid, site_acres=None):
    """The tracts a broker names by owner ('25 ac Smith + 23 ac Jones'): owner_name clues, each with the acreage
    quoted beside it, else the site's acreage when there is only one tract. [{'name', 'acres'}]"""
    cl = os.path.join(batch, 'input', 'clues_checked.csv')
    if not os.path.exists(cl):
        return []
    rows = [r for r in csv.DictReader(open(cl, encoding='utf-8-sig')) if r['site_id'] == sid and r['clue_type'] == 'owner_name']
    out = []
    for r in rows:
        m = re.search(r'(\d+(?:\.\d+)?)\s*(?:ac|acres?)\b', r['quote'] + ' ' + r.get('note', ''), re.I)
        out.append({'name': r['value'], 'acres': float(m.group(1)) if m else (site_acres if len(rows) == 1 else None)})
    return out


def search_area(s, batch, cache):
    """(lng/lat geometry, label) of the area a loosely placed site is known to be in: the broker's ZIP (L4) or the anchor's
    uncertainty circle (L3)."""
    import locate
    tier = (s.get('location_tier') or '').upper()
    la, ln = float(s['lat']), float(s['lng'])
    if tier == 'L3':
        r = float(s.get('location_radius_m') or 2000)
        fwd = Transformer.from_crs('EPSG:4326', f'+proj=laea +lat_0={la} +lon_0={ln} +datum=WGS84 +units=m', always_xy=True).transform
        inv = Transformer.from_crs(f'+proj=laea +lat_0={la} +lon_0={ln} +datum=WGS84 +units=m', 'EPSG:4326', always_xy=True).transform
        return transform(inv, Point(*fwd(ln, la)).buffer(r)), f"{r / 1000:g} km of {s.get('location_basis')}"
    cl = os.path.join(batch, 'input', 'clues_checked.csv')
    zipc = next((r['value'] for r in csv.DictReader(open(cl, encoding='utf-8-sig')) if r['site_id'] == s['site_id'] and r['clue_type'] == 'zip'), None) \
        if os.path.exists(cl) else None
    z = locate.Resolver(cache, (s.get('state') or 'TX').upper()).zcta(zipc) if zipc else None
    if not (z and z.get('rings')):
        return None, None
    from shapely.geometry import Polygon
    return unary_union([Polygon(ring) for ring in z['rings']]).buffer(0), f'ZIP {zipc}'


def broker_facts(batch, sid, s):
    """Broker acreage, parent tract and listing address for the parcel check: from the checked extraction
    (input/, EXTRACTION.md) when present, else the sites.csv acres_stated."""
    inp = os.path.join(batch, 'input')
    out = {'acres': footprint.row_acres(s), 'parent_acres': None, 'address': None, 'carve_out': False, 'pin_approx': False, 'substation': None, 'stage': ''}
    ev = os.path.join(inp, 'evidence_checked.csv')
    if os.path.exists(ev):
        rows = [r for r in csv.DictReader(open(ev, encoding='utf-8-sig')) if r['site_id'] == sid and r['dimension'] == 'acreage']
        act = next((r for r in rows if r['field'] == 'acres' and r['kind'] == 'actual'), None)
        par = next((r for r in rows if r['field'] == 'parent_acres'), None)
        out['acres'] = float(act['value']) if act else out['acres']
        out['parent_acres'] = float(par['value']) if par else None
        out['carve_out'] = any('carve' in (r['quote'] + ' ' + r['note']).lower() for r in rows)
        stg = next((r for r in csv.DictReader(open(ev, encoding='utf-8-sig')) if r['site_id'] == sid and r['dimension'] == 'site_control' and r['field'] == 'stage'), None)
        out['stage'] = stg['value'] if stg else ''
        # the broker's substation claim: an existing substation named as serving the site, 'adjacent' or at a distance
        pcx = [r for r in csv.DictReader(open(ev, encoding='utf-8-sig')) if r['site_id'] == sid and r['dimension'] == 'power_connection']
        name = next((r for r in pcx if r['field'] == 'substation'), None)
        status = next((r['value'] for r in pcx if r['field'] == 'substation_status'), '')
        if name and status == 'existing':
            words = ' '.join(r['quote'] + ' ' + r['note'] for r in pcx if r['field'] in ('substation', 'substation_status'))
            mi = re.search(r'~?\s*(\d+(?:\.\d+)?)\s*mi\b', words)
            out['substation'] = {'name': name['value'], 'claim': 'adjacent' if 'adjacent' in words.lower() else ('distance' if mi else None),
                                 'stated_mi': float(mi.group(1)) if mi else None, **hifld_substation(s, name['value'])}
    cl = os.path.join(inp, 'clues_checked.csv')
    if os.path.exists(cl):
        rows = [r for r in csv.DictReader(open(cl, encoding='utf-8-sig')) if r['site_id'] == sid]
        a = next((r for r in rows if r['clue_type'] == 'street_address'), None)
        out['address'] = a['value'] if a else None
        out['pin_approx'] = any(r['clue_type'] == 'coordinate_approx' for r in rows)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('batch')
    ap.add_argument('--only', required=True, help='comma-separated site_ids - figures are made for chosen sites only')
    ap.add_argument('--layers', default=','.join(LAYERS), help=f'exhibits to draw, from {LAYERS}; always one PNG per layer')
    ap.add_argument('--views', default=','.join(VIEWS), help=f'zooms to draw, from {VIEWS}; one PNG per layer per view')
    ap.add_argument('--buffer-m', type=float, default=400, help='regional view: ground shown around the footprint (default 400 m)')
    ap.add_argument('--basemap', default='naip', help=f'imagery under the overlays, from: {", ".join(basemap.PROVIDERS)}')
    ap.add_argument('--audience', default='external', choices=basemap.AUDIENCES,
                    help='external (default) = may be sold or sent to a client: only providers cleared for external use. '
                         'internal = marked "INTERNAL - not for distribution" and written as *_internal.png')
    a = ap.parse_args()
    b = a.batch.rstrip('/\\')
    layers = [x.strip() for x in a.layers.split(',') if x.strip()]
    views = [x.strip() for x in a.views.split(',') if x.strip()]
    if set(layers) - set(LAYERS) or set(views) - set(VIEWS):
        raise SystemExit(f'--layers must be from {LAYERS}, --views from {VIEWS}')
    basemap.check(a.basemap, a.audience)          # refuse before any fetching, not halfway through a batch
    sites = {s['site_id']: s for s in csv.DictReader(open(support(b, 'sites.csv'), encoding='utf-8-sig'))}
    run = json.load(open(support(b, 'run.json'), encoding='utf-8'))
    want = [x.strip() for x in a.only.split(',') if x.strip()]
    unknown = [x for x in want if x not in sites]
    if unknown:
        raise SystemExit(f'not in {b}/sites.csv: {", ".join(unknown)}')
    cache = Cache(CACHE)
    out_dir = os.path.join(b, 'figures')
    for sid in want:
        s = sites[sid]
        if not s.get('fp_basis'):
            tier_ = (s.get('location_tier') or '').upper()
            if 'parcels' in layers and tier_ in ('L3', 'L4'):      # exhibit only when a search leaves a question to ask
                t0 = time.time()
                bf = broker_facts(b, sid, s)
                adj = bool(bf['substation'] and bf['substation'].get('claim') == 'adjacent')
                plan = location_status.search_plan(tier_, bf['stage'], bf['acres'], s.get('location_basis'), s['lat'], s['lng'], s.get('location_radius_m'), adj)
                cres = None
                tracts = owner_tracts(b, sid, bf['acres'])
                if tracts and not location_status.no_site(bf['stage'], bool(bf['acres']), tier_):
                    # the broker names the tracts' owners: search the county's owner-searchable parcel service
                    geoid = ((parcel_mod.resolve(float(s['lat']), float(s['lng']), cache) or {}).get('county') or {}).get('GEOID')
                    svc = candidates.owner_service(geoid)
                    area, label = search_area(s, b, cache)
                    if not svc:
                        print(f"  {sid}: tract names given ({', '.join(x['name'] for x in tracts)}) but county {geoid} has no owner-searchable "
                              f"parcel service in data/reference/owner-search-services.json")
                    elif area is not None:
                        cres, cerr = candidates.search_owner(area, tracts, cache, svc, label)
                        if cerr:
                            print(f'  {sid} owner search: FAILED - {cerr} (rerun)')
                            continue
                        plan = None
                        os.makedirs(out_dir, exist_ok=True)
                        with open(os.path.join(out_dir, f'{sid}_candidates.json'), 'w', encoding='utf-8') as f:
                            json.dump(candidates.to_json(cres), f, indent=1, default=str)
                if plan:
                    sub = bf['substation'] if bf['substation'] and bf['substation'].get('lat') is not None else None
                    cres, cerr = candidates.search(plan, bf['acres'], cache, substation=sub)
                    if cerr:
                        print(f'  {sid} candidates: FAILED - {cerr} (rerun)')
                        continue
                    os.makedirs(out_dir, exist_ok=True)
                    with open(os.path.join(out_dir, f'{sid}_candidates.json'), 'w', encoding='utf-8') as f:
                        json.dump(candidates.to_json(cres), f, indent=1, default=str)
                st = location_status.classify(tier_, bf['stage'], bool(bf['acres']), s.get('location_basis', ''), s.get('location_radius_m'),
                                              cands=cres, acres=bf['acres'])
                if st['status'] != 'needs_input':
                    print(f"  {sid}: no exhibit - {location_status.label(st['status'])}: {st['assessment']}")
                    continue
                png, err = render_area(b, s, a.basemap, a.audience, run, cache, out_dir, cands=cres, status=st)
                print(f'  {sid} area: ' + (f'wrote {png}' if png else f'FAILED - {err} (rerun)') + f'  ({time.time() - t0:.0f}s)')
                continue
            print(f'  {sid}: SKIPPED - no footprint in sites.csv (run run.py with the footprint producer first)')
            continue
        t0 = time.time()
        fp = footprint.shape_at(float(s['lat']), float(s['lng']), Cache(CACHE, offline=True), footprint.row_acres(s),
                                footprint.batch_outlines(b).get(sid))
        if fp['stage'] != 'ok' or fp['basis'] != s['fp_basis']:
            print(f'  {sid}: SKIPPED - footprint no longer matches the workbook ({fp.get("basis") or fp.get("error")}); rerun run.py')
            continue
        if a.audience == 'external' and fp['basis'] == footprint.BASIS_PARCEL and fp['parcel'].get('exclusion'):
            print(f'  {sid}: SKIPPED - parcel from a licensed county (internal use only); use --audience internal')
            continue
        want_pc = 'parcels' in layers and fp['basis'] == footprint.BASIS_PARCEL
        if 'parcels' in layers and not want_pc:
            print(f'  {sid} parcels: SKIPPED - no identified parcel to check')
        d, err = prepare(s, fp, a.buffer_m, cache, broker_facts(b, sid, s) if want_pc else None)
        if err:
            print(f'  {sid}: FAILED - {err} (nothing cached for the failed call; rerun)')
            continue
        if want_pc and d['pc_error']:
            print(f"  {sid} parcels: FAILED - {d['pc_error']} (rerun)")
        elif want_pc:
            os.makedirs(out_dir, exist_ok=True)
            with open(os.path.join(out_dir, f'{sid}_parcel_check.json'), 'w', encoding='utf-8') as f:
                json.dump(parcel_check.to_json(d['pc']), f, indent=1, default=str)
        for vname in views:
            got = {}
            for layer in layers:
                if layer == 'parcels' and (not want_pc or d['pc_error']):
                    continue
                vkey = f'parcels_{vname}' if layer == 'parcels' else vname
                if vkey not in got:
                    got[vkey] = view(d, vkey, a.basemap, a.audience, cache)
                v, err = got[vkey]
                if err:
                    print(f'  {sid} {vname}: FAILED - {err} (rerun)')
                    continue
                if (layer == 'flood' and d['zones_error']) or (layer == 'wetlands' and d['nwi_error']):
                    print(f"  {sid} {layer}: FAILED - {d['zones_error' if layer == 'flood' else 'nwi_error']} (rerun)")
                    continue
                png = render_parcels({**v, 'words': broker_words(b, sid)}, vname, run, out_dir) if layer == 'parcels' else render(v, layer, run, out_dir)
                print(f'  {sid} {layer} {vname}: wrote {png}')
        os.makedirs(out_dir, exist_ok=True)       # every render may have failed, so nothing created it yet
        with open(os.path.join(out_dir, f"{sid}_figures{'_internal' if a.audience == 'internal' else ''}.json"), 'w', encoding='utf-8') as f:
            json.dump(d['log'], f, indent=1, default=str)
        print(f'  {sid}: {time.time() - t0:.0f}s')


if __name__ == '__main__':
    main()
