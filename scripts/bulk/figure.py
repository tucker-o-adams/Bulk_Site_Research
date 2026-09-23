# -*- coding: utf-8 -*-
"""Site exhibits (PNG) for the sites you pick - not for a whole batch. Flood and wetlands are
always separate exhibits (never one combined map), each drawn at two zooms:

    site       the footprint fills ~65% of the frame (never under 60 m tall - NAIP resolution)
    regional   the footprint plus --buffer-m (400 m) of surroundings

    .venv_fema/Scripts/python.exe scripts/bulk/figure.py Outputs/<batch>/ --only SITE_ID,SITE_ID
        [--layers flood,wetlands] [--views site,regional] [--buffer-m 400]
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
from geom import arcgis_envelope_query                                   # noqa: E402
from producers import flood, footprint, wetlands                         # noqa: E402
import basemap                                                           # noqa: E402

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


def frame_bounds(fp_utm, buffer_m=None, fill=None, min_h=0):
    """The map frame, at the map box's aspect: the footprint plus buffer_m, or sized so the footprint
    fills `fill` of the frame's height or width (whichever binds), never under min_h metres tall."""
    minx, miny, maxx, maxy = fp_utm.bounds
    cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
    if fill:
        h = max((maxy - miny) / fill, (maxx - minx) / fill / ASPECT, min_h)
    else:
        h = max(maxy - miny + 2 * buffer_m, (maxx - minx + 2 * buffer_m) / ASPECT)
    w = h * ASPECT
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
LAYERS = ('flood', 'wetlands')


def prepare(s, fp, buffer_m, cache):
    """Everything both exhibits draw, fetched once per site through the cache. Returns (data, error)."""
    sid = s['site_id']; la, ln = float(s['lat']), float(s['lng'])
    epsg = utm_epsg(la, ln)
    to_utm = Transformer.from_crs('EPSG:4326', f'EPSG:{epsg}', always_xy=True).transform
    to_ll = Transformer.from_crs(f'EPSG:{epsg}', 'EPSG:4326', always_xy=True).transform
    fp_utm = transform(to_utm, fp['ll'])
    views = {'regional': frame_bounds(fp_utm, buffer_m=buffer_m),
             'site': frame_bounds(fp_utm, fill=SITE_FILL, min_h=SITE_MIN_H)}
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
    return {'s': s, 'fp': fp, 'epsg': epsg, 'to_utm': to_utm, 'fp_utm': fp_utm, 'views': views,
            'raw_ctx': ctx, 'log': log,
            'raw_zones': zf, 'zones_error': ze, 'raw_nwi': wf, 'nwi_error': we}, None


def view(d, name, provider, audience, cache):
    """The prepared data clipped to one zoom, over that zoom's basemap. Returns (view, error)."""
    bounds = d['views'][name]
    frame = box(*bounds)
    epsg, s = d['epsg'], d['s']
    tag = hashlib.md5(repr([round(v, 2) for v in bounds]).encode()).hexdigest()[:10]
    key = f"{s['site_id']}_{name}_{tag}" if provider == 'naip' else f"{provider}_{s['site_id']}_{name}_{tag}"
    bm, err = basemap.get(provider, audience, bounds, epsg, key, RES_M[name], float(s['lat']), float(s['lng']), cache)
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


def render(d, layer, run, out_dir):
    s, fp, epsg, ctx = d['s'], d['fp'], d['epsg'], d['ctx']
    sid = s['site_id']; la, ln = float(s['lat']), float(s['lng'])
    minx, miny, maxx, maxy = d['bounds']
    span, hspan = maxx - minx, maxy - miny
    k = hspan / 1980.0                  # Site 2 layout was tuned for a ~1,980 m frame height
    is_parcel = fp['basis'] == footprint.BASIS_PARCEL
    fig = plt.figure(figsize=(16, 9), dpi=300)
    ax = fig.add_axes(list(MAP_BOX))
    with rasterio.open(d['img']) as ds:
        ax.imshow(ds.read([1, 2, 3]).transpose(1, 2, 0), extent=(minx, maxx, miny, maxy), origin='upper', interpolation='bilinear')
    ax.set_xlim(minx, maxx); ax.set_ylim(miny, maxy); ax.set_xticks([]); ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_linewidth(1.2); sp.set_color('#222')

    c = ctx
    if c['hydro_areal'] is not None: c['hydro_areal'].plot(ax=ax, facecolor='none', edgecolor='#c9d6e3', alpha=.9, linewidth=.6, zorder=7)   # outline only: fills are reserved for flood / wetland
    if c['hydro_linear'] is not None: c['hydro_linear'].plot(ax=ax, color='#2c6fb5', linewidth=1.4, alpha=.85, zorder=3)
    if c['roads_local'] is not None: c['roads_local'].plot(ax=ax, color='#f6e6b4', linewidth=.7, alpha=.75, zorder=4)
    if c['roads_secondary'] is not None: c['roads_secondary'].plot(ax=ax, color='#ffd24d', linewidth=2.4, alpha=.95, zorder=5)
    if c['roads_primary'] is not None: c['roads_primary'].plot(ax=ax, color='#ff9d2e', linewidth=3.4, alpha=.95, zorder=5)
    if c['railroads'] is not None: c['railroads'].plot(ax=ax, color='#3a3a3a', linewidth=1.1, linestyle=(0, (6, 4)), alpha=.9, zorder=4)

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

    def label_lines(g, size, color, n=None, minlen=380):
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
    label_lines(c['roads_primary'], 8.5, '#ffe0b0', minlen=300)
    label_lines(c['roads_secondary'], 7.6, '#fff3c4', minlen=300)
    label_lines(c['roads_local'], 5.6, '#f0f0f0', n=24, minlen=330)
    label_lines(c['hydro_linear'], 7.0, '#bfe0ff', minlen=200)

    # scale bar and north arrow
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
    sites = {s['site_id']: s for s in csv.DictReader(open(os.path.join(b, 'sites.csv'), encoding='utf-8-sig'))}
    run = json.load(open(os.path.join(b, 'run.json'), encoding='utf-8'))
    want = [x.strip() for x in a.only.split(',') if x.strip()]
    unknown = [x for x in want if x not in sites]
    if unknown:
        raise SystemExit(f'not in {b}/sites.csv: {", ".join(unknown)}')
    cache = Cache(CACHE)
    out_dir = os.path.join(b, 'figures')
    for sid in want:
        s = sites[sid]
        if not s.get('fp_basis'):
            print(f'  {sid}: SKIPPED - no footprint in sites.csv (run run.py with the footprint producer first)')
            continue
        t0 = time.time()
        fp = footprint.shape_at(float(s['lat']), float(s['lng']), Cache(CACHE, offline=True), footprint.row_acres(s))
        if fp['stage'] != 'ok' or fp['basis'] != s['fp_basis']:
            print(f'  {sid}: SKIPPED - footprint no longer matches the workbook ({fp.get("basis") or fp.get("error")}); rerun run.py')
            continue
        d, err = prepare(s, fp, a.buffer_m, cache)
        if err:
            print(f'  {sid}: FAILED - {err} (nothing cached for the failed call; rerun)')
            continue
        for vname in views:
            v, err = view(d, vname, a.basemap, a.audience, cache)
            if err:
                print(f'  {sid} {vname}: FAILED - {err} (rerun)')
                continue
            for layer in layers:
                if (layer == 'flood' and d['zones_error']) or (layer == 'wetlands' and d['nwi_error']):
                    print(f"  {sid} {layer}: FAILED - {d['zones_error' if layer == 'flood' else 'nwi_error']} (rerun)")
                    continue
                print(f'  {sid} {layer} {vname}: wrote {render(v, layer, run, out_dir)}')
        os.makedirs(out_dir, exist_ok=True)       # every render may have failed, so nothing created it yet
        with open(os.path.join(out_dir, f"{sid}_figures{'_internal' if a.audience == 'internal' else ''}.json"), 'w', encoding='utf-8') as f:
            json.dump(d['log'], f, indent=1, default=str)
        print(f'  {sid}: {time.time() - t0:.0f}s')


if __name__ == '__main__':
    main()
