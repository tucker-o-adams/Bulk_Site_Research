# -*- coding: utf-8 -*-
"""Write a batch's Google Earth KMZ from its run outputs and the shared cache.

    .venv_fema/Scripts/python.exe scripts/bulk/kmz.py Outputs/<batch>/ [--name <title>]

No network: every geometry is read from data/cache (the exact responses the
producers scored) or from the CMS reference files, so the map shows what the
workbook was computed from. Folders:

    A. Sites                       one pin per site, in state subfolders (group subfolders instead
                                   only with --group-folders); popup = key values + sources   (off)
    A2. Site footprints            the shape the fp_* columns were measured over: parcel boundary or intake
                                   outline (green) or, with no parcel, the square around the pin (blue)  (off)
    A3. Approximate locations      sites located only to a landmark, ZIP or county (location tier L3-L5):
                                   a circle of the location's uncertainty radius; these sites' pins are
                                   grey and get no flood, wetland or neighbor layers              (ON)
    B. Transmission within 5 km    HIFLD segments by voltage band: regional, shared by nearby sites  (off)
    D. Substations within 5 km     points by voltage band                      (off)
    H. Site by site                state -> site ([group ->] with --group-folders), fly-to; every theme of one
                                   site in its own folder with its own checkbox (2026-10-07: everything that is
                                   about one site lives with that site):                         (off)
         Power                     sites with an outline or parcel: every line within 1 mi (by voltage); nearest qualifying line,
                                   substation and 115 kV+
                                   substation (profile voltages), each with a line from the usable land (or the site
                                   edge when nothing is usable); a stand-in square: from the pin, as before
         Flood                     FEMA SFHA polygons over the site outline + 500 m (and 1.5 km around the pin)
         Wetlands                  NWI polygons, same extent
         Excluded land by reason   edge setback, buildings, flood, wetlands, land cover, steep ground, line right-of-way
         Homes and sensitive       everything within the pass distance of the usable land: homes (clusters of 5+ as one
           neighbors               neighborhood shape, else pins), schools, worship, nursing homes, hospitals; the review
                                   and pass zones around them clipped to the site; the nearest home's line; on-site
                                   Residential buildings as numbered pins to review (not counted)
         Usable land (last)        usable blocks by distance from every receptor (purple >= pass, yellow review-pass, red < review)

A folder that ships off has every folder and placemark inside it off too, so Google Earth's
checkboxes agree with what is drawn; ticking the folder turns its contents on.
"""
import argparse, csv, html, json, math, os, sys, zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from cache import Cache, coord_key, _safe                # noqa: E402
from batch_paths import support, publish                 # noqa: E402
from geom import point_dist_m, geojson_polygon_dist_m    # noqa: E402
from shapely.geometry import shape, box, mapping           # noqa: E402
from shapely.ops import nearest_points, transform, unary_union   # noqa: E402
from producers import flood, footprint, homes, power_site, usable, wetlands   # noqa: E402
from sites import Site                                     # noqa: E402
import product_profile as prof                             # noqa: E402

CLIP_M = 1500     # polygons in E/F are clipped to this box around the site they were fetched for


def clip_to_site(geometry, lat, lng, radius_m=CLIP_M):
    """Return the part of a GeoJSON polygon within a square of half-width radius_m around
    the site, as GeoJSON (or None if empty). A river polygon that runs for 500 km is
    otherwise drawn whole and dominates the file."""
    try:
        g = shape(geometry)
        k = math.cos(math.radians(lat))
        dx, dy = radius_m / (111320 * k), radius_m / 110540
        c = g.intersection(box(lng - dx, lat - dy, lng + dx, lat + dy))
        if c.is_empty:
            return None
        c = c.buffer(0) if not c.is_valid else c
        return mapping(c) if c.geom_type in ('Polygon', 'MultiPolygon') else None
    except Exception:
        return geometry

ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
CACHE = os.path.join(ROOT, 'data', 'cache')
REF = os.path.join(ROOT, 'data', 'reference')
K = 'http://www.opengis.net/kml/2.2'
ET.register_namespace('', K)
NS = '{%s}' % K
MI = 1609.344

# KML colours are aabbggrr
KV_STYLES = [('kv500', 'ffff00ff', 4.4, lambda kv: kv is not None and kv >= 400, '500 kV +'),
             ('kv345', 'ff0000ff', 4.0, lambda kv: kv is not None and 300 <= kv < 400, '345 kV'),
             ('kv230', 'ff0080ff', 3.4, lambda kv: kv is not None and 200 <= kv < 300, '230-287 kV'),
             ('kv100', 'ff00d7ff', 3.0, lambda kv: kv is not None and 100 <= kv < 200, '100-161 kV'),
             ('kvSub100', 'ffb4b4b4', 2.4, lambda kv: kv is not None and kv < 100, 'Under 100 kV'),
             ('kvUnknown', '96b4b4b4', 2.0, lambda kv: kv is None, 'Voltage not published')]
ICON = 'http://maps.google.com/mapfiles/kml/'


def esc(v):
    return html.escape('' if v is None else str(v))


def sub(parent, tag, text=None, **attrs):
    el = ET.SubElement(parent, NS + tag, attrs)
    if text is not None:
        el.text = str(text)
    return el


def folder(parent, name, visible=True, description=None, open_=False):
    f = sub(parent, 'Folder'); sub(f, 'name', name)
    if not visible:
        sub(f, 'visibility', '0')
    if not open_:
        sub(f, 'open', '0')
    if description:
        sub(f, 'description', description)
    return f


def cached(producer, lat, lng, suffix=''):
    p = os.path.join(CACHE, producer, _safe(coord_key(lat, lng, suffix)) + '.json')
    if not os.path.exists(p):
        return None
    return json.load(open(p, encoding='utf-8'))['response']


def kv(p):
    try:
        v = float(p.get('VOLTAGE') if 'VOLTAGE' in p else p.get('MAX_VOLT'))
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


def style_id(v):
    return next(s[0] for s in KV_STYLES if s[3](v))


def line_parts(g):
    if not g:
        return []
    return [g['coordinates']] if g.get('type') == 'LineString' else g.get('coordinates', []) if g.get('type') == 'MultiLineString' else []


def foot(px, py, ax, ay, bx, by):
    """Nearest point on segment AB to P (lng/lat), and distance in metres."""
    k = math.cos(math.radians(py))
    AX, AY = (ax - px) * 111320 * k, (ay - py) * 110540
    BX, BY = (bx - px) * 111320 * k, (by - py) * 110540
    dx, dy = BX - AX, BY - AY
    t = 0.0 if dx == 0 and dy == 0 else max(0.0, min(1.0, ((0 - AX) * dx + (0 - AY) * dy) / (dx * dx + dy * dy)))
    fx, fy = AX + t * dx, AY + t * dy
    return (px + fx / (111320 * k), py + fy / 110540), math.hypot(fx, fy)


def coords(parts):
    return [' '.join(f'{c[0]},{c[1]},0' for c in part) for part in parts]


def add_line_pm(parent, name, style, desc, parts):
    pm = sub(parent, 'Placemark'); sub(pm, 'name', name[:80]); sub(pm, 'styleUrl', f'#{style}'); sub(pm, 'description', desc)
    mg = sub(pm, 'MultiGeometry')
    for cs in coords(parts):
        ls = sub(mg, 'LineString'); sub(ls, 'tessellate', '1'); sub(ls, 'coordinates', cs)
    return pm


def add_point_pm(parent, name, style, desc, lng, lat, visible=True):
    pm = sub(parent, 'Placemark'); sub(pm, 'name', name[:80])
    if not visible:
        sub(pm, 'visibility', '0')
    sub(pm, 'styleUrl', f'#{style}'); sub(pm, 'description', desc)
    pt = sub(pm, 'Point'); sub(pt, 'coordinates', f'{lng},{lat},0')
    return pm


def add_poly_pm(parent, name, style, desc, geometry):
    pm = sub(parent, 'Placemark'); sub(pm, 'name', name[:80]); sub(pm, 'styleUrl', f'#{style}'); sub(pm, 'description', desc)
    mg = sub(pm, 'MultiGeometry')
    polys = [geometry['coordinates']] if geometry.get('type') == 'Polygon' else geometry.get('coordinates', []) if geometry.get('type') == 'MultiPolygon' else []
    for rings in polys:
        pg = sub(mg, 'Polygon'); sub(pg, 'tessellate', '1')
        ob = sub(sub(pg, 'outerBoundaryIs'), 'LinearRing'); sub(ob, 'coordinates', coords([rings[0]])[0])
        for hole in rings[1:]:
            ib = sub(sub(pg, 'innerBoundaryIs'), 'LinearRing'); sub(ib, 'coordinates', coords([hole])[0])
    return pm


def fmt(v, unit=''):
    if v in (None, ''):
        return '—'
    try:
        f = float(v)
        s = f'{f:,.0f}' if abs(f) >= 100 or f.is_integer() else f'{f:,.1f}'
    except ValueError:
        s = str(v)
    return s + unit


def approx(s):
    """Located only to an anchor, a ZIP or a county (locate.py tier L3-L5): the pin is not the site."""
    return (s.get('location_tier') or '').upper() in ('L3', 'L4', 'L5')


def circle(lat, lng, r_m, n=64):
    k = math.cos(math.radians(lat))
    ring = [(lng + r_m * math.cos(2 * math.pi * i / n) / (111320 * k), lat + r_m * math.sin(2 * math.pi * i / n) / 110540) for i in range(n + 1)]
    return {'type': 'Polygon', 'coordinates': [ring]}


def basis_text(s):
    """What the site's area figures rest on. fp_basis when the footprint producer ran; the parcel status otherwise."""
    if s.get('fp_basis') == footprint.BASIS_PARCEL or (not s.get('fp_basis') and s.get('parcel_status') == 'ok'):
        return 'parcel boundary' + (' - <b>INTERNAL USE ONLY</b> (licensed county parcel data)' if (s.get('parcel_use') or '').startswith('INTERNAL') else '')
    if s.get('fp_basis'):
        return (f"{esc(s['fp_basis'])} around the pin - no parcel for {esc(s.get('parcel_county') or 'this county')}; "
                'footprint figures describe the square, not a parcel')
    return 'point only - no parcel service registered for ' + esc(s.get('parcel_county') or 'this county') + '; values are measured at the pin'


def site_desc(s, srcs):
    """Popup: key values by producer, with the source name."""
    def m(v):
        return '—' if v in (None, '') else f'{float(v):,.0f} m ({float(v) / MI:.2f} mi)'
    rows = [
        ('Site', f"<b>{esc(s['site_id'])}</b> {esc(s.get('name'))}<br/>{esc(s.get('address'))} {esc(s.get('city') or '')} {esc(s.get('state'))}" + (f"<br/>group: {esc(s.get('group'))}" if s.get('group') else '')
                 + (f"<br/><i>basis: {basis_text(s)}</i>" if s.get('fp_basis') or s.get('parcel_status') else '')),
    ]
    if s.get('location_tier'):
        rows.append(('Location', f"<b>{esc(s['location_tier'])}</b>: {esc(s.get('location_basis'))} (radius {fmt(s.get('location_radius_m'))} m); {esc(s.get('location_check'))}"
                                 + ('<br/><b>The pin is not the site.</b> Values below describe the located point; flood, wetland, parcel and neighbour fields are not assessable.' if approx(s) else '')
                                 + (f"<br/>other clues: {esc(s.get('location_other'))}" if s.get('location_other') else '')
                                 + (f"<br/>unresolved: {esc(s.get('location_unresolved'))}" if s.get('location_unresolved') else '')))
    if s.get('fp_basis'):
        rows.append(('Footprint', f"{esc(s.get('fp_basis'))}, {fmt(s.get('fp_acres'))} ac<br/>"
                                  f"flood: {esc(s.get('fp_flood_zones')) or 'no FEMA determination'}; SFHA <b>{fmt(s.get('fp_sfha_acres'))} ac</b> "
                                  f"({fmt(s.get('fp_sfha_pct'))}%), floodway {fmt(s.get('fp_floodway_acres'))} ac, unmapped {fmt(s.get('fp_flood_unmapped_acres'))} ac<br/>"
                                  f"NWI wetlands: <b>{fmt(s.get('fp_nwi_acres'))} ac</b> ({fmt(s.get('fp_nwi_pct'))}%) {esc(s.get('fp_nwi_types'))}"))
    rows += [
        (srcs.get('transmission', 'Transmission'), f"nearest line {m(s.get('tx_nearest_m'))} — {fmt(s.get('tx_voltage_kv'), ' kV')} [{esc(s.get('tx_voltage_basis'))}] {esc(s.get('tx_owner'))}<br/>"
                                                    f"nearest ≥100 kV {m(s.get('tx_100kv_nearest_m'))} — {fmt(s.get('tx_100kv_voltage_kv'), ' kV')}"),
        (srcs.get('substations', 'Substations'), f"nearest {m(s.get('sub_nearest_m'))} — {esc(s.get('sub_nearest_name'))} {fmt(s.get('sub_nearest_max_kv'), ' kV')} ({esc(s.get('sub_nearest_type'))}, kV inferred={esc(s.get('sub_nearest_kv_inferred'))})<br/>"
                                                  f"nearest ≥100 kV {m(s.get('sub_100kv_nearest_m'))}; ≥230 kV {m(s.get('sub_230kv_nearest_m'))}; {fmt(s.get('sub_count_within_10km'))} within 10 km"),
        (srcs.get('flood', 'Flood'), f"{esc(s.get('fema_determination'))}: zone <b>{esc(s.get('fema_flood_zone')) or '—'}</b> {esc(s.get('fema_zone_subtype'))}; SFHA={esc(s.get('fema_sfha'))}<br/>"
                                     f"nearest SFHA {m(s.get('fema_nearest_sfha_m'))} (zone {esc(s.get('fema_nearest_sfha_zone')) or '—'}); panel {esc(s.get('fema_firm_panel'))} eff. {esc(s.get('fema_panel_effective'))}"),
        (srcs.get('wetlands', 'Wetlands'), f"NWI at point={esc(s.get('nwi_at_point'))}; nearest {m(s.get('nwi_nearest_m'))} {esc(s.get('nwi_nearest_type'))}; "
                                           f"{fmt(s.get('nwi_count_within_500m'))} polygons / {fmt(s.get('nwi_polygon_acres_within_500m'))} ac within 500 m; imagery {esc(s.get('nwi_image_year'))}"
                                           + (f" — <b>stale mapping ({esc(s.get('nwi_mapping_age_years'))} yr): confirm against current imagery</b>"
                                              if wetlands.stale_note(int(s['nwi_image_year']) if (s.get('nwi_image_year') or '').isdigit() else None) else '')),
        (srcs.get('metro', 'Metro'), f"in urban area: {esc(s.get('metro_urban_area_at_point')) or 'none (rural)'}; nearest 250k+ {esc(s.get('metro_250k_nearest_name'))} {m(s.get('metro_250k_nearest_m'))}; "
                                     f"nearest 1M+ {esc(s.get('metro_1m_nearest_name'))} {m(s.get('metro_1m_nearest_m'))}"),
        (srcs.get('datacenter', 'Data centers'), f"nearest PeeringDB facility {esc(s.get('dc_nearest_name'))}, {esc(s.get('dc_nearest_city'))} {m(s.get('dc_nearest_m'))} ({fmt(s.get('dc_nearest_networks'))} networks); "
                                                 f"nearest hub {esc(s.get('dc_hub_nearest_city'))} {m(s.get('dc_hub_nearest_m'))}"),
        (srcs.get('housing', 'Housing'), f"{fmt(s.get('hu_within_0_5mi'))} housing units / {fmt(s.get('pop_within_0_5mi'))} people within 0.5 mi; {fmt(s.get('hu_within_1mi'))} / {fmt(s.get('pop_within_1mi'))} within 1 mi"),
        (srcs.get('schools', 'Schools'), f"nearest {esc(s.get('school_nearest_name'))} ({esc(s.get('school_nearest_type'))}) {m(s.get('school_nearest_m'))}; {fmt(s.get('schools_within_1mi'))} within 1 mi"),
        (srcs.get('worship', 'Places of worship'), f"nearest {esc(s.get('worship_nearest_name'))} {m(s.get('worship_nearest_m'))}; {fmt(s.get('worship_within_1mi'))} within 1 mi"),
        (srcs.get('healthcare', 'Nursing homes & hospitals'), f"nursing home {esc(s.get('nursing_home_nearest_name'))} {m(s.get('nursing_home_nearest_m'))} ({fmt(s.get('nursing_home_nearest_beds'))} beds); "
                                                             f"hospital {esc(s.get('hospital_nearest_name'))} {m(s.get('hospital_nearest_m'))} ({esc(s.get('hospital_nearest_type'))})"),
    ]
    if s.get('utility_name'):
        rows.append((srcs.get('utility', 'Utility'), f"serving utility <b>{esc(s.get('utility_name'))}</b> ({esc(s.get('utility_type'))}; {esc(s.get('utility_grid_operator'))}); "
                                                   f"average industrial price {fmt(s.get('industrial_cents_kwh_2024'))}¢/kWh (2024), {fmt(s.get('industrial_cents_kwh_2020'))}¢ (2020)" + (f" - <b>{esc(s.get('industrial_price_basis'))}</b>" if str(s.get('industrial_price_basis') or '').startswith('retail-choice') else '')
                                                   + (f"<br/>also at the pin: {esc(s.get('utility_others_at_pin'))}" if s.get('utility_others_at_pin') else '')))
    if s.get('nri_overall'):
        rows.append((srcs.get('hazards', 'Hazards'), f"FEMA risk (relative to US tracts): overall <b>{esc(s.get('nri_overall'))}</b>; tornado {esc(s.get('nri_tornado'))}; "
                                                   f"strong wind {esc(s.get('nri_strong_wind'))}; hail {esc(s.get('nri_hail'))}; hurricane {esc(s.get('nri_hurricane'))}; "
                                                   f"earthquake {esc(s.get('nri_earthquake'))}; wildfire {esc(s.get('nri_wildfire'))}; inland flooding {esc(s.get('nri_inland_flooding'))}"))
    if s.get('npl_on_site') not in (None, ''):
        flags = []
        if str(s.get('npl_on_site')) == 'True':
            flags.append('<b>an NPL site point is on the site</b>')
        if str(s.get('npl_active_within_1mi') or '0') not in ('0', '0.0'):
            flags.append(f"<b>{esc(s.get('npl_active_within_1mi'))} active NPL site(s) within 1 mi</b>")
        if str(s.get('npl_deleted_within_half_mi') or '0') not in ('0', '0.0'):
            flags.append(f"<b>{esc(s.get('npl_deleted_within_half_mi'))} deleted NPL site(s) within 0.5 mi</b>")
        rows.append((srcs.get('superfund', 'Superfund'), ('; '.join(flags) + '<br/>' if flags else 'none within the Phase I search distances (1 mi active, 0.5 mi deleted)<br/>')
                     + ('nearest: ' + (f"{esc(s.get('npl_nearest_name'))} ({esc(s.get('npl_nearest_status'))}) {m(s.get('npl_nearest_m'))}"
                                        if s.get('npl_nearest_m') not in (None, '') else 'none within 5 km'))))
    ft = lambda k, d: f"{float((s.get('_profile') or {}).get(k) or d):,.0f} ft"
    if s.get('home_nearest_m') not in (None, '') or s.get('homes_within_pass') not in (None, ''):
        rows.append((srcs.get('homes', 'Homes'), f"nearest home {m(s.get('home_nearest_m'))} ({esc(s.get('home_nearest_class'))}); on site <b>{fmt(s.get('homes_on_site'))}</b>; "
                                               f"within {ft('receptor_review_ft', 1000)} <b>{fmt(s.get('homes_within_review'))}</b>, within {ft('receptor_pass_ft', 2000)} {fmt(s.get('homes_within_pass'))}"
                                               f"<br/>Census estimate: {fmt(s.get('hu_near_review'))} / {fmt(s.get('hu_near_pass'))} housing units"))
    if s.get('ul_layers'):
        rows.append((srcs.get('usable', 'Usable land'), f"usable <b>{fmt(s.get('ul_usable_acres'))} ac</b> of {fmt(s.get('ul_site_acres'))} ac; largest block {fmt(s.get('ul_largest_block_acres'))} ac<br/>"
                                                      f"pads that fit: <b>{fmt(s.get('ul_pads_fit'))}</b>; at least {ft('receptor_review_ft', 1000)} from every home <b>{fmt(s.get('ul_pads_fit_review'))}</b>; "
                                                      f"at least {ft('receptor_pass_ft', 2000)} <b>{fmt(s.get('ul_pads_fit_pass'))}</b><br/>excluded: {esc(s.get('ul_excluded'))}<br/><i>{esc(s.get('ul_layers'))}</i>"))
    return '<table cellpadding="2" style="font-size:11px">' + ''.join(f'<tr><td valign="top" style="color:#666;white-space:nowrap"><i>{esc(k)}</i></td><td>{v}</td></tr>' for k, v in rows) + '</table>'


def _extent(fp, la, ln):
    """Where a site's flood and wetland polygons are drawn (lng/lat): the footprint's box + 500 m, and CLIP_M around the pin."""
    k = math.cos(math.radians(la))
    parts = [box(ln - CLIP_M / (111320 * k), la - CLIP_M / 110540, ln + CLIP_M / (111320 * k), la + CLIP_M / 110540)]
    if fp:
        x0, y0, x1, y1 = fp['ll'].bounds
        dx, dy = 500 / (111320 * k), 500 / 110540
        parts.append(box(x0 - dx, y0 - dy, x1 + dx, y1 + dy))
    return unary_union(parts)


def _overlay(fp, la, ln, cache, producer, pin_suffix, request, reach, layer, fields):
    """The polygons the site was scored from: the producer's answer around the pin, plus the footprint's own answer
    (the bounding-box query when the footprint reaches past the pin radius). Duplicates dropped."""
    feats = list((cached(producer, la, ln, pin_suffix) or {}).get('features') or [])
    if fp:
        more, _, err = footprint.overlay_features(fp, la, ln, cache, producer, request, reach, layer, fields)
        if not err:
            feats += more
    out, seen = [], set()
    for f in feats:
        key = json.dumps((f.get('geometry') or {}).get('coordinates', [])[:1])[:300] + json.dumps(f.get('properties') or {}, sort_keys=True)[:200]
        if key not in seen:
            seen.add(key); out.append(f)
    return out


LINES_SHOWN_M = 1609.344          # every transmission line within 1 mile of the site is drawn in its Power folder
CLUSTER_M = 60                    # homes within 2 x this of each other form one cluster
NEIGHBORHOOD_MIN = 5              # a cluster of this many homes is drawn as one neighborhood shape, not pins


def draw_power(site_f, site, fp, cache, r, profile, inv):
    """Power from the site: every transmission line within LINES_SHOWN_M of the site, colored by voltage; the nearest
    qualifying line, substation and 115 kV+ substation (profile voltages), each with a line from the usable land -
    where a pad could go - or from the site edge when nothing is usable."""
    lines, subs, _, err = power_site.near_site(site, cache, fp)
    pf = folder(site_f, 'Power: from the usable land' if r and r['blocks'] else 'Power: from the site edge', visible=False)
    if err:
        return
    line_kv, sub_kv, head_kv = power_site.kvs(profile)
    target = unary_union(r['blocks']) if r and r['blocks'] else fp['m']
    ll = lambda g: transform(inv, g)
    near = sorted(((g.distance(fp['m']), g, p) for g, p in lines if g.distance(fp['m']) <= LINES_SHOWN_M), key=lambda t: t[0])
    af = folder(pf, f'All lines within 1 mi of the site ({len(near)})', visible=False)
    for d_site, g, p in near:
        kvv = power_site.line_kv_for_row(p)
        d_use = g.distance(target)
        add_line_pm(af, f"{transmission_kv(p)} kV, {(p.get('OWNER') or '?').title()}: {d_use:,.0f} m from {'usable land' if r and r['blocks'] else 'the site'}",
                    style_id(kvv), f"{esc(transmission_kv(p))} kV ({esc(p.get('VOLT_CLASS'))}); owner {esc(p.get('OWNER'))}; status {esc(p.get('STATUS'))}; "
                    f"HIFLD ID {esc(p.get('ID'))}; {d_site:,.0f} m from the site edge" + (' (crosses the site)' if d_site == 0 else ''),
                    line_parts(mapping(ll(g))))
    shown = set()
    for label, items, ok, kind in ((f'line >= {line_kv:g} kV', lines, lambda q: power_site.line_ok(q, line_kv), 'line'),
                                   (f'substation >= {sub_kv:g} kV', subs, lambda q: power_site.sub_ok(q, sub_kv), 'sub'),
                                   (f'{head_kv:g} kV+ substation', subs, lambda q: power_site.sub_ok(q, head_kv), 'sub')):
        nb = power_site.nearest(items, target, ok)
        if not nb:
            continue
        d, g, p = nb
        if kind == 'line':
            add_line_pm(pf, f'nearest {label}: {transmission_kv(p)} kV @ {d:,.0f} m', 'nearLine',
                        f"{esc(transmission_kv(p))} kV; owner {esc(p.get('OWNER'))}; HIFLD ID {esc(p.get('ID'))}", line_parts(mapping(ll(g))))
        elif p.get('ID') not in shown:
            c = ll(g.centroid)
            add_point_pm(pf, f"nearest {label}: {(p.get('NAME') or '').strip() or p.get('ID')} @ {d:,.0f} m", 'substation',
                         f"{esc(p.get('NAME'))}; MAX_VOLT {esc(p.get('MAX_VOLT'))} (inferred {esc(p.get('MAX_INFER'))}); {esc(p.get('TYPE'))}; "
                         f"status {esc(p.get('STATUS'))}; source {esc(p.get('SOURCE'))}", c.x, c.y)
            shown.add(p.get('ID'))
        if d > 0:
            a, b_ = nearest_points(target, g)
            add_line_pm(pf, f'{label}: {d:,.0f} m ({d / MI:.2f} mi)', 'connector', '', [[inv(a.x, a.y), inv(b_.x, b_.y)]])


def transmission_kv(p):
    try:
        v = float(p.get('VOLTAGE'))
        return f'{v:g}' if v > 0 else (p.get('VOLT_CLASS') or 'n/p')
    except (TypeError, ValueError):
        return p.get('VOLT_CLASS') or 'n/p'


def draw_receptors(site_f, s, r, profile, inv, to_ll, counts):
    """Homes and sensitive neighbors that limit the usable land: everything within the pass distance of it (of the site
    edge when nothing is usable). Homes close together are drawn as one neighborhood shape with a count; isolated homes
    as pins. The review and pass zones around all of them, clipped to the site, show why land is red or yellow.
    Residential buildings on the site itself are pins to review - not counted."""
    rev_ft, pass_ft = profile['receptor_review_ft'], profile['receptor_pass_ft']
    rev_m, pass_m = homes.receptor_m(profile)
    base = unary_union(r['blocks']) if r['blocks'] else r['fp']['m']
    near_h = [h for h in r['homes'] if h[0].distance(base) <= pass_m]
    near_s = [x for x in r['sensitive'] if x[0].distance(base) <= pass_m]
    of = folder(site_f, f"Homes and sensitive neighbors within {pass_ft:,} ft ({len(near_h)} homes, {len(near_s)} other)", visible=False)
    # clusters: homes within 2 x CLUSTER_M of each other
    blobs = unary_union([h[0].buffer(CLUSTER_M) for h in near_h]) if near_h else None
    for blob in (list(getattr(blobs, 'geoms', [blobs])) if blobs is not None else []):
        members = [h for h in near_h if blob.contains(h[0])]
        if len(members) >= NEIGHBORHOOD_MIN:
            d = min(h[0].distance(base) for h in members)
            add_poly_pm(of, f"neighborhood: {len(members)} homes, {d / 0.3048:,.0f} ft away", 'neighborhood',
                        f"{len(members)} homes (FEMA USA Structures) within {2 * CLUSTER_M} m of each other; nearest {d:,.0f} m "
                        f"({d / 0.3048:,.0f} ft) from {'the usable land' if r['blocks'] else 'the site'}", to_ll(blob.buffer(-CLUSTER_M / 2)))
            counts['neighborhoods'] += 1
        else:
            for hp, lab, yr, info in members:
                d = hp.distance(base)
                x, y = inv(hp.x, hp.y)
                add_point_pm(of, f"home: {esc(lab.split(' / ')[-1])}, {d / 0.3048:,.0f} ft away", 'home',
                             f"<b>{esc(lab)}</b><br/>{info['sqft']:,} sq ft; imagery {yr or '?'}" + (f"<br/>{esc(info['address'])}" if info['address'] else '')
                             + '<br/><i>FEMA USA Structures</i>', x, y)
                counts['home pins'] += 1
    style = {'public school': 'school', 'private school': 'school', 'place of worship': 'worship', 'nursing home': 'nursing', 'hospital': 'hospital'}
    for pt, name, kind in near_s:
        d = pt.distance(base)
        x, y = inv(pt.x, pt.y)
        add_point_pm(of, f"{kind}: {name}, {d / 0.3048:,.0f} ft away", style.get(kind, 'school'),
                     f"{esc(kind)}" + ('; IRS-geocoded, may be a mailing address' if kind == 'place of worship' else ''), x, y)
        counts['sensitive pins'] += 1
    # the nearest home, the one home_nearest_m measures to (from the site edge)
    if r['homes']:
        hp, lab, yr, info = min(r['homes'], key=lambda h: h[0].distance(r['fp']['m']))
        d = hp.distance(r['fp']['m'])
        if d > 0:
            a, b_ = nearest_points(hp, r['fp']['m'])
            add_line_pm(of, f'nearest home: {d / 0.3048:,.0f} ft from the site edge ({esc(lab.split(" / ")[-1])})', 'connector',
                        f"the home home_nearest_m measures to; {info['sqft']:,} sq ft", [[inv(a.x, a.y), inv(b_.x, b_.y)]])
    # zones around every receptor within reach, clipped to the site
    pts = [h[0] for h in near_h] + [x[0] for x in near_s]
    if pts:
        seed = unary_union([q.buffer(CLUSTER_M) for q in pts])
        for dist_m, ft, style_z in ((rev_m, rev_ft, 'zoneReview'), (pass_m, pass_ft, 'zonePass')):
            z = seed.buffer(dist_m - CLUSTER_M).intersection(r['fp']['m'])
            if not z.is_empty:
                add_poly_pm(of, f'within {ft:,} ft of a home or sensitive neighbor: {z.area / footprint.AC:,.1f} ac of the site', style_z,
                            'the ground this distance rule holds pads off', to_ll(z))
    if r.get('homes_on_site'):
        rf = folder(of, f"On-site homes: review ({len(r['homes_on_site'])})", visible=False)
        for n, (hp, lab, yr, info) in enumerate(sorted(r['homes_on_site'], key=lambda h: (-h[0].y, h[0].x)), 1):   # numbered north to south
            desc = (f"<b>{esc(lab)}</b> on the site itself - not counted as a home; check it against imagery, the assessor or the owner"
                    f"<br/>{info['sqft']:,} sq ft; imagery {yr or '?'}" + (f"<br/>{esc(info['address'])}" if info['address'] else '')
                    + '<br/><i>FEMA USA Structures</i>')
            x, y = inv(hp.x, hp.y)
            add_point_pm(rf, f"{s['site_id']} on-site home {n}: {esc(lab.split(' / ')[-1])}, {info['sqft']:,} sq ft", 'homeReview', desc, x, y)
        counts['on-site homes'] += len(r['homes_on_site'])


def site_layers(site_f, s, fp, cache, outlines, profile, ref_nh, ref_h, counts):
    """A site's layers from the cache, in this order (usable land last - everything before it is a reason land is not
    usable): power, flood, wetlands, excluded land by reason, homes and sensitive neighbors, usable land."""
    la, ln = float(s['lat']), float(s['lng'])
    ext = _extent(fp, la, ln)
    site = Site(site_id=s['site_id'], lat=la, lng=ln, acres_stated=footprint.row_acres(s), outline=outlines.get(s['site_id']))
    inv = footprint.projection(la, ln)[1]
    to_ll = lambda geom: mapping(transform(inv, geom.simplify(1.0)))
    has_ul = bool(profile and s.get('ul_layers') and s.get('ul_pads_fit') not in (None, ''))
    r = usable.measure(site, cache, profile) if has_ul else None
    if r is not None and 'error' in r:
        r = None

    if fp and fp['basis'] in (footprint.BASIS_OUTLINE, footprint.BASIS_PARCEL) and s.get('pw_from'):
        draw_power(site_f, site, fp, cache, r, profile, inv)
        counts['power folders'] += 1

    def clipped(geometry):
        try:
            g = shape(geometry)
            c = g.intersection(ext) if g.intersects(ext) else None
        except Exception:
            try:
                c = shape(geometry).buffer(0).intersection(ext)
            except Exception:
                return None
        return mapping(c) if c is not None and not c.is_empty and c.geom_type in ('Polygon', 'MultiPolygon', 'GeometryCollection') else None

    ff = folder(site_f, 'Flood: FEMA SFHA zones', visible=False)
    for f in _overlay(fp, la, ln, cache, 'flood', 'zones1000', flood.zones_request(la, ln), flood.SFHA_SEARCH_M, f'{flood.NFHL}/28', flood.ZONE_FIELDS):
        p = f.get('properties') or {}
        if (p.get('SFHA_TF') or '').upper() != 'T':
            continue
        geom = clipped(f.get('geometry') or {})
        if geom:
            counts['flood polygons'] += 1
            add_poly_pm(ff, f"Zone {p.get('FLD_ZONE')} {p.get('ZONE_SUBTY') or ''}".strip(), 'sfha',
                        f"FLD_ZONE {esc(p.get('FLD_ZONE'))}; {esc(p.get('ZONE_SUBTY'))}; static BFE {esc(p.get('STATIC_BFE'))}; DFIRM {esc(p.get('DFIRM_ID'))}", geom)
    wf = folder(site_f, 'Wetlands: NWI', visible=False)
    for f in _overlay(fp, la, ln, cache, 'wetlands', 'near500', wetlands.near_request(la, ln), wetlands.SEARCH_M, wetlands.WET, '*'):
        p = f.get('properties') or {}
        attr = next((v for k, v in p.items() if k.upper().endswith('ATTRIBUTE')), '')
        wt = next((v for k, v in p.items() if k.upper().endswith('WETLAND_TYPE')), '')
        geom = clipped(f.get('geometry') or {})
        if geom:
            counts['wetland polygons'] += 1
            add_poly_pm(wf, f'{wt} ({attr})', 'nwi', f'{esc(wt)}; Cowardin {esc(attr)}; photointerpreted, not a jurisdictional determination', geom)

    if r is None:
        return
    xf = folder(site_f, 'Excluded land by reason', visible=False)
    reasons = [('edge setback', 'exSetback', r['setback'])]
    for k, g in r['excluded'].items():
        style = ('exRow' if k.startswith('power line') else 'exBuildings' if k.startswith('buildings') else 'exFlood' if k.startswith('flood')
                 else 'exWetlands' if k.startswith('wetlands') else 'exCover' if k.startswith('land cover') else 'exSlope' if k.startswith('slope') else 'exSetback')
        reasons.append((f"steep ground ({k})" if k.startswith('slope') else k, style, g))
    for label, style, g in reasons:
        if g is not None and not g.is_empty:
            counts['excluded polygons'] += 1
            add_poly_pm(xf, f'{label}: {g.area / footprint.AC:,.1f} ac', style, 'removed from usable land (reasons overlap)', to_ll(g))

    draw_receptors(site_f, s, r, profile, inv, to_ll, counts)

    rev_ft, pass_ft = profile['receptor_review_ft'], profile['receptor_pass_ft']
    uf = folder(site_f, f"Usable land: {fmt(s.get('ul_pads_fit'))} pads, {fmt(s.get('ul_pads_fit_pass'))} at {pass_ft:,} ft", visible=False)
    # colored by each piece's actual distance from the nearest receptor (not by whether a whole pad fits in the band:
    # a strip 2,000+ ft away that is too narrow for a pad is still purple). The pad counts need a full pad in the band.
    allb = unary_union(r['blocks']) if r['blocks'] else None
    pts = [h[0] for h in r['homes']] + [x[0] for x in r['sensitive']]
    rev_m, pass_m = homes.receptor_m(profile)
    if allb is not None and pts:
        far1, far2 = usable.far_from(allb, pts, rev_m), usable.far_from(allb, pts, pass_m)
        empty = allb.difference(allb)
        far1 = far1 if far1 is not None else empty
        far2 = far2 if far2 is not None else empty
        bands = ((allb.difference(far1), 'ulNear'), (far1.difference(far2), 'ulMid'), (far2, 'ulFar'))
    else:
        bands = ((None, 'ulNear'), (None, 'ulMid'), (allb, 'ulFar'))
    labels = {'ulNear': f'under {rev_ft:,} ft from a home or sensitive neighbor (red)', 'ulMid': f'{rev_ft:,}-{pass_ft:,} ft (yellow)',
              'ulFar': f'{pass_ft:,} ft or more (purple)'}
    for geom, style in bands:
        if geom is not None and not geom.is_empty and geom.area > 1:
            counts['usable polygons'] += 1
            add_poly_pm(uf, f'usable, {labels[style]}: {geom.area / footprint.AC:,.1f} ac', style,
                        'usable blocks, colored by distance from the nearest home or sensitive neighbor; pad counts need a whole '
                        'pad inside a band, so a narrow strip may hold none', to_ll(geom))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('batch'); ap.add_argument('--name', default=None)
    ap.add_argument('--group-folders', action='store_true',
                    help="split folders A and H by the input's group column (default: by state only)")
    a = ap.parse_args()
    b = a.batch.rstrip('/\\'); name = a.name or os.path.basename(b)
    sites = list(csv.DictReader(open(support(b, 'sites.csv'), encoding='utf-8-sig')))
    run = json.load(open(support(b, 'run.json'), encoding='utf-8'))
    srcs = {n: p['source'].split(' (')[0] for n, p in run['producers'].items()}
    profile = {**prof.DEFAULTS, **((run.get('profile') or {}).get('values') or {})} if run.get('profile') else None
    for s in sites:
        s['_profile'] = profile
    # States are the only subfolders unless the user asks for group folders (rule, 2026-09-23)
    use_group = a.group_folders and any(s.get('group') for s in sites)
    fkey = (lambda s: s.get('group') or 'Sites') if use_group else (lambda s: s.get('state') or 'State not given')
    groups = sorted({fkey(s) for s in sites})
    ref_nh = list(csv.DictReader(open(os.path.join(REF, 'cms_nursing_homes.csv'), encoding='utf-8'))) if os.path.exists(os.path.join(REF, 'cms_nursing_homes.csv')) else []
    ref_h = list(csv.DictReader(open(os.path.join(REF, 'cms_hospitals.csv'), encoding='utf-8'))) if os.path.exists(os.path.join(REF, 'cms_hospitals.csv')) else []

    kml = ET.Element(NS + 'kml'); doc = sub(kml, 'Document'); sub(doc, 'name', name)
    sub(doc, 'description', f'{len(sites)} sites, run {run["run_at"][:16].replace("T", " ")} UTC. Every layer is drawn from the exact service '
                            'responses the workbook was computed from. Distances in the popups are straight-line. Sources: ' +
                            '; '.join(f'{n}: {p["source"]}' for n, p in run['producers'].items()))
    # ---- styles
    for sid, colour, width, _, _ in KV_STYLES:
        st = sub(doc, 'Style', id=sid); ls = sub(st, 'LineStyle'); sub(ls, 'color', colour); sub(ls, 'width', str(width))
    for sid, colour, width in (('nearLine', 'ff00ffff', 4.0), ('connector', 'ffffffff', 2.0)):
        st = sub(doc, 'Style', id=sid); ls = sub(st, 'LineStyle'); sub(ls, 'color', colour); sub(ls, 'width', str(width))
    group_colours = ['ff00ffff', 'ff00a5ff', 'ffff00ff', 'ff00ff00', 'ffffff00']
    for i, g in enumerate(groups):
        st = sub(doc, 'Style', id=f'site_{i}'); ic = sub(st, 'IconStyle'); sub(ic, 'scale', '1.1'); sub(ic, 'color', group_colours[i % len(group_colours)])
        sub(sub(ic, 'Icon'), 'href', ICON + 'shapes/placemark_circle.png')
    for sid, href, colour, scale in (('verifySite', 'paddle/grn-circle.png', 'ff00ff00', '1.2'), ('substation', 'shapes/square.png', 'ff00ffff', '0.8'),
                                     ('school', 'shapes/schools.png', 'ffffffff', '0.9'), ('worship', 'shapes/church.png', 'ffffffff', '0.9'),
                                     ('nursing', 'shapes/hospitals.png', 'ffb469ff', '0.9'), ('hospital', 'shapes/hospitals.png', 'ff0000ff', '1.0')):
        st = sub(doc, 'Style', id=sid); ic = sub(st, 'IconStyle'); sub(ic, 'scale', scale); sub(ic, 'color', colour); sub(sub(ic, 'Icon'), 'href', ICON + href)
    for sid, line, fill in (('sfha', 'ffd06f1f', '66d06f1f'), ('nwi', 'ff1cc37f', '551cc37f')):
        st = sub(doc, 'Style', id=sid); ls = sub(st, 'LineStyle'); sub(ls, 'color', line); sub(ls, 'width', '2')
        ps = sub(st, 'PolyStyle'); sub(ps, 'color', fill); sub(ps, 'fill', '1'); sub(ps, 'outline', '1')
    st = sub(doc, 'Style', id='siteApprox'); ic = sub(st, 'IconStyle'); sub(ic, 'scale', '1.0'); sub(ic, 'color', 'ffb4b4b4')
    sub(sub(ic, 'Icon'), 'href', ICON + 'shapes/placemark_circle.png')
    st = sub(doc, 'Style', id='approxCircle'); ls = sub(st, 'LineStyle'); sub(ls, 'color', 'ffb4b4b4'); sub(ls, 'width', '2')
    ps = sub(st, 'PolyStyle'); sub(ps, 'color', '22b4b4b4'); sub(ps, 'fill', '1'); sub(ps, 'outline', '1')
    # usable land: purple / yellow / red, so it never reads as wetland green or flood blue (KML colours are aabbggrr)
    for sid, colour in (('ulNear', 'ff0000ff'), ('ulMid', 'ff00d7ff'), ('ulFar', 'ffd30094'),
                        ('exSetback', 'ff909090'), ('exBuildings', 'ff202020'), ('exFlood', 'ffd06f1f'), ('exWetlands', 'ff1cc37f'),
                        ('exCover', 'ff2a5a8b'), ('exSlope', 'ff008cff'), ('exRow', 'ffff00ff')):
        st = sub(doc, 'Style', id=sid); ls = sub(st, 'LineStyle'); sub(ls, 'color', colour); sub(ls, 'width', '1.5')
        ps = sub(st, 'PolyStyle'); sub(ps, 'color', '66' + colour[2:]); sub(ps, 'fill', '1'); sub(ps, 'outline', '1')
    st = sub(doc, 'Style', id='home'); ic = sub(st, 'IconStyle'); sub(ic, 'scale', '0.8'); sub(ic, 'color', 'ff0000ff')
    sub(sub(ic, 'Icon'), 'href', ICON + 'shapes/homegardenbusiness.png')
    st = sub(doc, 'Style', id='neighborhood'); ls = sub(st, 'LineStyle'); sub(ls, 'color', 'ff0000ff'); sub(ls, 'width', '2')
    ps = sub(st, 'PolyStyle'); sub(ps, 'color', '660000ff'); sub(ps, 'fill', '1'); sub(ps, 'outline', '1')
    for sid_z, colour in (('zoneReview', 'ff0000ff'), ('zonePass', 'ff00d7ff')):     # outlines only: what is inside stays visible
        st = sub(doc, 'Style', id=sid_z); ls = sub(st, 'LineStyle'); sub(ls, 'color', colour); sub(ls, 'width', '2.5')
        ps = sub(st, 'PolyStyle'); sub(ps, 'fill', '0'); sub(ps, 'outline', '1')
    st = sub(doc, 'Style', id='homeReview'); ic = sub(st, 'IconStyle'); sub(ic, 'scale', '0.8'); sub(ic, 'color', 'ff00ffff')
    sub(sub(ic, 'Icon'), 'href', ICON + 'shapes/caution.png')
    st = sub(doc, 'Style', id='homeReviewBldg'); ls = sub(st, 'LineStyle'); sub(ls, 'color', 'ff00ffff'); sub(ls, 'width', '3')
    ps = sub(st, 'PolyStyle'); sub(ps, 'color', '5500ffff'); sub(ps, 'fill', '1'); sub(ps, 'outline', '1')
    st = sub(doc, 'Style', id='homeBldg'); ls = sub(st, 'LineStyle'); sub(ls, 'color', 'ff0000ff'); sub(ls, 'width', '3')
    ps = sub(st, 'PolyStyle'); sub(ps, 'color', '880000ff'); sub(ps, 'fill', '1'); sub(ps, 'outline', '1')
    for sid, line in (('fpParcel', 'ff00ff00'), ('fpSquare', 'ffffc864')):      # outline only: imagery shows through
        st = sub(doc, 'Style', id=sid); ls = sub(st, 'LineStyle'); sub(ls, 'color', line); sub(ls, 'width', '2.5')
        ps = sub(st, 'PolyStyle'); sub(ps, 'fill', '0'); sub(ps, 'outline', '1')

    # labels of the many small pins (homes, neighbors, on-site homes) stay hidden until the pin is hovered: each style
    # becomes a StyleMap - normal = label scale 0, highlight = the original style
    for sid_h in ('home', 'homeReview', 'school', 'worship', 'nursing', 'hospital'):
        st = doc.find(f"{NS}Style[@id='{sid_h}']")
        if st is None:
            continue
        st.set('id', f'{sid_h}_h')
        quiet = ET.fromstring(ET.tostring(st)); quiet.set('id', f'{sid_h}_n')
        ls = quiet.find(NS + 'LabelStyle')
        if ls is None:
            ls = ET.SubElement(quiet, NS + 'LabelStyle')
        sc = ls.find(NS + 'scale') if ls.find(NS + 'scale') is not None else ET.SubElement(ls, NS + 'scale')
        sc.text = '0'
        doc.insert(list(doc).index(st) + 1, quiet)
        sm = ET.Element(NS + 'StyleMap', id=sid_h)
        for key, ref in (('normal', f'{sid_h}_n'), ('highlight', f'{sid_h}_h')):
            pair = ET.SubElement(sm, NS + 'Pair'); ET.SubElement(pair, NS + 'key').text = key; ET.SubElement(pair, NS + 'styleUrl').text = f'#{ref}'
        doc.insert(list(doc).index(quiet) + 1, sm)

    # ---- A. Sites
    A = folder(doc, f'A. Sites ({len(sites)})', visible=False, open_=True)
    by_group = defaultdict(list)
    for s in sites:
        by_group[fkey(s)].append(s)
    grouped = use_group or any(s.get('state') for s in sites)     # no group or state: pins straight under A
    for i, g in enumerate(groups):
        gf = folder(A, f'{g} ({len(by_group[g])})') if grouped else A
        for s in by_group[g]:
            if approx(s):
                add_point_pm(gf, f"{s['site_id']} (approx. {s['location_tier']}, {fmt(s.get('location_radius_m'))} m)", 'siteApprox', site_desc(s, srcs), float(s['lng']), float(s['lat']))
            else:
                add_point_pm(gf, s['site_id'], f'site_{i}', site_desc(s, srcs), float(s['lng']), float(s['lat']))
    ap_sites = [s for s in sites if approx(s)]
    if ap_sites:
        A3 = folder(doc, f'A3. Approximate locations: uncertainty circles ({len(ap_sites)})', description=(
            'Sites the broker list places only near a named substation, intersection or landmark (L3), within a ZIP (L4) or a county (L5). '
            'The circle is the uncertainty radius around the located point; the site could be anywhere in it. No flood, wetland or '
            'neighbour layers are drawn for these sites.'))
        for s in ap_sites:
            add_poly_pm(A3, f"{s['site_id']} {s['location_tier']} radius {fmt(s.get('location_radius_m'))} m", 'approxCircle', site_desc(s, srcs),
                        circle(float(s['lat']), float(s['lng']), float(s.get('location_radius_m') or 1000)))

    # ---- A2. Site footprints: the very shape the fp_* columns were measured over (offline: cache only)
    fps = {}
    if any(s.get('fp_basis') for s in sites):
        offline = Cache(CACHE, offline=True)
        outlines = footprint.batch_outlines(b)
        for s in sites:
            if not s.get('fp_basis'):
                continue                    # footprint not assessable at this location tier
            fp = footprint.shape_at(float(s['lat']), float(s['lng']), offline, footprint.row_acres(s), outlines.get(s['site_id']))
            if fp['stage'] == 'ok':
                fps[s['site_id']] = fp
        A2 = folder(doc, 'A2. Site footprints', visible=False, description=(
            f'The shape each site\'s footprint figures (fp_*) were measured over. Green = parcel boundary from the registered '
            f'county/state parcel service. Blue = no parcel resolved, so a north-aligned square centred on the pin '
            f'({footprint.SQUARE_M} m, or the stated acreage if larger) stands in for the site - it is not a parcel.'))
        for is_parcel, style, label in ((True, 'fpParcel', 'Parcel boundaries and intake outlines'), (False, 'fpSquare', 'Squares around the pin (no parcel)')):
            ids = [sid_ for sid_, fp in fps.items() if (fp['basis'] in (footprint.BASIS_PARCEL, footprint.BASIS_OUTLINE)) == is_parcel]
            ff = folder(A2, f'{label} ({len(ids)})')
            for s in (x for x in sites if x['site_id'] in ids):
                internal = ' (INTERNAL USE ONLY - licensed county parcel)' if fps[s['site_id']]['parcel'].get('exclusion') and is_parcel else ''
                add_poly_pm(ff, f"{s['site_id']} — {fmt(s.get('fp_acres'))} ac{internal}", style, site_desc(s, srcs), mapping(fps[s['site_id']]['ll']))
        missing = [s['site_id'] for s in sites if s['site_id'] not in fps and s.get('fp_basis')]
        if missing:
            print(f'  A2: no footprint for {len(missing)} sites (parcel lookup failed or not cached): {", ".join(missing[:10])}')

    # ---- B, C: transmission from the cache
    seen, tiers, nearest = set(), defaultdict(list), {}
    for s in sites:
        la, ln = float(s['lat']), float(s['lng'])
        resp = cached('transmission', la, ln)
        if not resp:
            continue
        best = None
        for f in resp.get('features') or []:
            p = f.get('properties') or {}; parts = line_parts(f.get('geometry'))
            dmin, fp = None, None
            for part in parts:
                for j in range(len(part) - 1):
                    pt, d = foot(ln, la, part[j][0], part[j][1], part[j + 1][0], part[j + 1][1])
                    if dmin is None or d < dmin:
                        dmin, fp = d, pt
            if dmin is None:
                continue
            if dmin <= 5000 and p.get('ID') not in seen:
                seen.add(p.get('ID')); tiers[style_id(kv(p))].append((p, parts))
            if best is None or dmin < best[0]:
                best = (dmin, fp, p, parts)
        if best:
            nearest[s['site_id']] = best
    B = folder(doc, f'B. Transmission within 5 km of any site ({len(seen)} segments, HIFLD mirror)', visible=False)
    for sid, _, _, _, label in KV_STYLES:
        items = tiers.get(sid) or []
        if not items:
            continue
        tf = folder(B, f'{label} ({len(items)})')
        for p, parts in items:
            nm = ' - '.join(x for x in ((p.get('SUB_1') or '').strip(), (p.get('SUB_2') or '').strip()) if x and not x.upper().startswith(('UNKNOWN', 'NOT AVAIL'))) or f"line {p.get('ID')}"
            add_line_pm(tf, nm, sid, f"ID {esc(p.get('ID'))}<br/>Voltage {esc(p.get('VOLTAGE'))} kV ({esc(p.get('VOLT_CLASS'))})<br/>Owner {esc(p.get('OWNER'))}<br/>"
                                     f"Type {esc(p.get('TYPE'))}; Status {esc(p.get('STATUS'))}; attrs inferred {esc(p.get('INFERRED'))}", parts)
    # ---- D. Substations within 5 km
    D = folder(doc, 'D. Substations within 5 km of any site (HIFLD mirror, 2021)', visible=False)
    seen_s, nearest_sub = set(), {}
    dtiers = defaultdict(list)
    for s in sites:
        la, ln = float(s['lat']), float(s['lng'])
        resp = cached('substations', la, ln, 'r15000')
        if not resp:
            continue
        best = None
        for f in resp.get('features') or []:
            g = f.get('geometry') or {}
            if g.get('type') != 'Point':
                continue
            x, y = g['coordinates'][:2]; p = f.get('properties') or {}; d = point_dist_m(ln, la, x, y)
            if d <= 5000 and p.get('ID') not in seen_s:
                seen_s.add(p.get('ID')); dtiers[style_id(kv(p))].append((p, x, y))
            if best is None or d < best[0]:
                best = (d, p, x, y)
        if best:
            nearest_sub[s['site_id']] = best
    for sid, _, _, _, label in KV_STYLES:
        items = dtiers.get(sid) or []
        if not items:
            continue
        tf = folder(D, f'{label} ({len(items)})')
        for p, x, y in items:
            nm = (p.get('NAME') or '').strip(); nm = nm if nm and not nm.upper().startswith('UNKNOWN') else f"[unnamed {p.get('ID')}]"
            add_point_pm(tf, f"{nm} — {fmt(kv(p), ' kV') if kv(p) else 'kV n/p'}", 'substation',
                         f"{esc(p.get('TYPE'))}; MAX_VOLT {esc(p.get('MAX_VOLT'))} (inferred {esc(p.get('MAX_INFER'))}); lines {esc(p.get('LINES'))}; "
                         f"status {esc(p.get('STATUS'))}; source {esc(p.get('SOURCE'))}; HIFLD ID {esc(p.get('ID'))}", x, y)
    D.find(NS + 'name').text = f'D. Substations within 5 km of any site ({len(seen_s)}, HIFLD mirror 2021)'

    # ---- H. Site by site: everything about one site in its folder, each theme with its own checkbox
    offline = Cache(CACHE, offline=True)
    outlines = footprint.batch_outlines(b)
    if profile:
        homes.PROFILE = profile
    counts = defaultdict(int)
    H = folder(doc, 'H. Site by site', visible=False,
               description='One folder per site, by state. Tick a site to see all of its layers; untick a theme inside it to hide that theme. '
                           'Double-click a site to fly to it. HIFLD geometry is national-scale and may sit 20-50 m off the visible towers.')
    for i, g in enumerate(groups):
        gf = folder(H, f'{g} ({len(by_group[g])})') if use_group else H
        by_state = defaultdict(list)
        for s in by_group[g]:
            by_state[s.get('state') or 'State not given'].append(s)
        for stt in sorted(by_state):
            # an input with no state column gets no state level, rather than one folder of everything
            sf = folder(gf, f'{stt} ({len(by_state[stt])})') if len(by_state) > 1 or stt != 'State not given' else gf
            for s in sorted(by_state[stt], key=lambda s: s['site_id']):
                la, ln = float(s['lat']), float(s['lng']); nb = nearest.get(s['site_id'])
                dist = nb[0] if nb else 2000.0
                v = kv(nb[2]) if nb else None
                fp = fps.get(s['site_id'])
                site_based = bool(fp and fp['basis'] in (footprint.BASIS_OUTLINE, footprint.BASIS_PARCEL) and s.get('pw_from'))
                if site_based:
                    lm = s.get('line_kv_site_m')
                    title = (f"{s['site_id']} — {fmt(s.get('line_kv_site_kv'))} kV line @ {float(lm):,.0f} m from the site" if lm not in (None, '')
                             else f"{s['site_id']} — no qualifying line found")
                else:
                    title = f"{s['site_id']} — {f'{v:g} kV' if v else 'kV n/p'} @ {dist:,.0f} m"
                site_f = folder(sf, title, visible=False)
                look = sub(site_f, 'LookAt'); sub(look, 'longitude', ln); sub(look, 'latitude', la); sub(look, 'altitude', '0')
                span = max(fp['m'].bounds[2] - fp['m'].bounds[0], fp['m'].bounds[3] - fp['m'].bounds[1]) if fp else 0
                sub(look, 'heading', '0'); sub(look, 'tilt', '0'); sub(look, 'range', str(max(400.0, dist * 4.0, span * 1.6))); sub(look, 'altitudeMode', 'relativeToGround')
                add_point_pm(site_f, f"{s['site_id']} (site)", 'verifySite', site_desc(s, srcs), ln, la)
                if fp:
                    add_poly_pm(site_f, f"footprint — {fp['basis']}, {fmt(s.get('fp_acres'))} ac",
                                'fpParcel' if fp['basis'] in (footprint.BASIS_PARCEL, footprint.BASIS_OUTLINE) else 'fpSquare', '', mapping(fp['ll']))
                pw = folder(site_f, 'Power: nearest line and substation (from the pin)', visible=False) if not site_based else None
                if nb and pw is not None:
                    d, fpt, p, parts = nb
                    add_line_pm(pw, f"nearest line — {f'{v:g} kV' if v else 'kV n/p'} @ {d:,.0f} m", 'nearLine', f"ID {esc(p.get('ID'))}; owner {esc(p.get('OWNER'))}", parts)
                    pm = sub(pw, 'Placemark'); sub(pm, 'name', f'connector {d:,.0f} m'); sub(pm, 'styleUrl', '#connector')
                    ls = sub(pm, 'LineString'); sub(ls, 'tessellate', '1'); sub(ls, 'coordinates', f'{ln},{la},0 {fpt[0]},{fpt[1]},0')
                ns_ = nearest_sub.get(s['site_id'])
                if ns_ and pw is not None:
                    d, p, x, y = ns_
                    add_point_pm(pw, f"nearest substation — {(p.get('NAME') or '').strip() or p.get('ID')} @ {d:,.0f} m", 'substation',
                                 f"MAX_VOLT {esc(p.get('MAX_VOLT'))} (inferred {esc(p.get('MAX_INFER'))}); {esc(p.get('TYPE'))}; source {esc(p.get('SOURCE'))}", x, y)
                if not approx(s):           # around an approximate point these would be read as the site's
                    site_layers(site_f, s, fp, offline, outlines, profile, ref_nh, ref_h, counts)

    # A folder that ships off: switch off everything inside it too, so its checkboxes match
    for top in doc.findall(NS + 'Folder'):
        v = top.find(NS + 'visibility')
        if v is not None and v.text == '0':
            for el in top.iter():
                if el is not top and el.tag in (NS + 'Folder', NS + 'Placemark'):
                    vis = el.find(NS + 'visibility')
                    if vis is None:
                        vis = ET.Element(NS + 'visibility'); el.insert(1, vis)   # after <name>, per the KML schema order
                    vis.text = '0'

    data = ET.tostring(kml, encoding='utf-8', xml_declaration=True)

    def write(path):
        with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
            z.writestr('doc.kml', data)
    out = publish(b, f'{name}.kmz', write)
    t = data.decode('utf-8')
    print(f'wrote {out} ({os.path.getsize(out) / 1024:,.0f} KB): folders {t.count("<Folder")}, placemarks {t.count("<Placemark")}')
    print(f'  B transmission segments {len(seen)} | D substations {len(seen_s)} | per site: ' +
          ', '.join(f'{k} {v}' for k, v in sorted(counts.items())))


if __name__ == '__main__':
    main()
