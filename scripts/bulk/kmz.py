# -*- coding: utf-8 -*-
"""Write a batch's Google Earth KMZ from its run outputs and the shared cache.

    .venv_fema/Scripts/python.exe scripts/bulk/kmz.py Outputs/<batch>/ [--name <title>]

No network: every geometry is read from data/cache (the exact responses the
producers scored) or from the CMS reference files, so the map shows what the
workbook was computed from. Folders, in the Windstream layout:

    A. Sites                       one pin per site, styled by `group`; popup = key values + sources
    B. Transmission within 5 km    HIFLD segments by voltage band
    C. Nearest line per site       the identified segment, and a site -> line connector
    D. Substations within 5 km     points by voltage band                      (off)
    E. Flood: SFHA within 1 km     FEMA A/AE/AH/AO/V polygons                  (off)
    F. Wetlands within 500 m       NWI polygons                                 (off)
    G. Neighbors within 1 mi       schools, places of worship, nursing homes, hospitals (off)
    H. Site-by-site verification   group -> state -> site: pin, nearest line, connector,
                                   nearest substation, fly-to                  (off)
"""
import argparse, csv, html, json, math, os, sys, zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from cache import coord_key, _safe                       # noqa: E402
from geom import point_dist_m, geojson_polygon_dist_m    # noqa: E402
from shapely.geometry import shape, box, mapping           # noqa: E402

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


def site_desc(s, srcs):
    """Popup: key values by producer, with the source name."""
    def m(v):
        return '—' if v in (None, '') else f'{float(v):,.0f} m ({float(v) / MI:.2f} mi)'
    rows = [
        ('Site', f"<b>{esc(s['site_id'])}</b> {esc(s.get('name'))}<br/>{esc(s.get('address'))} {esc(s.get('city') or '')} {esc(s.get('state'))}<br/>group: {esc(s.get('group'))}"),
        (srcs.get('transmission', 'Transmission'), f"nearest line {m(s.get('tx_nearest_m'))} — {fmt(s.get('tx_voltage_kv'), ' kV')} [{esc(s.get('tx_voltage_basis'))}] {esc(s.get('tx_owner'))}<br/>"
                                                    f"nearest ≥100 kV {m(s.get('tx_100kv_nearest_m'))} — {fmt(s.get('tx_100kv_voltage_kv'), ' kV')}"),
        (srcs.get('substations', 'Substations'), f"nearest {m(s.get('sub_nearest_m'))} — {esc(s.get('sub_nearest_name'))} {fmt(s.get('sub_nearest_max_kv'), ' kV')} ({esc(s.get('sub_nearest_type'))}, kV inferred={esc(s.get('sub_nearest_kv_inferred'))})<br/>"
                                                  f"nearest ≥100 kV {m(s.get('sub_100kv_nearest_m'))}; ≥230 kV {m(s.get('sub_230kv_nearest_m'))}; {fmt(s.get('sub_count_within_10km'))} within 10 km"),
        (srcs.get('flood', 'Flood'), f"{esc(s.get('fema_determination'))}: zone <b>{esc(s.get('fema_flood_zone')) or '—'}</b> {esc(s.get('fema_zone_subtype'))}; SFHA={esc(s.get('fema_sfha'))}<br/>"
                                     f"nearest SFHA {m(s.get('fema_nearest_sfha_m'))} (zone {esc(s.get('fema_nearest_sfha_zone')) or '—'}); panel {esc(s.get('fema_firm_panel'))} eff. {esc(s.get('fema_panel_effective'))}"),
        (srcs.get('wetlands', 'Wetlands'), f"NWI at point={esc(s.get('nwi_at_point'))}; nearest {m(s.get('nwi_nearest_m'))} {esc(s.get('nwi_nearest_type'))}; "
                                           f"{fmt(s.get('nwi_count_within_500m'))} polygons / {fmt(s.get('nwi_polygon_acres_within_500m'))} ac within 500 m; imagery {esc(s.get('nwi_image_year'))}"),
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
    return '<table cellpadding="2" style="font-size:11px">' + ''.join(f'<tr><td valign="top" style="color:#666;white-space:nowrap"><i>{esc(k)}</i></td><td>{v}</td></tr>' for k, v in rows) + '</table>'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('batch'); ap.add_argument('--name', default=None)
    a = ap.parse_args()
    b = a.batch.rstrip('/\\'); name = a.name or os.path.basename(b)
    sites = list(csv.DictReader(open(os.path.join(b, 'sites.csv'), encoding='utf-8-sig')))
    run = json.load(open(os.path.join(b, 'run.json'), encoding='utf-8'))
    srcs = {n: p['source'].split(' (')[0] for n, p in run['producers'].items()}
    groups = sorted({s.get('group') or 'Sites' for s in sites})
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

    # ---- A. Sites
    A = folder(doc, f'A. Sites ({len(sites)})', open_=True)
    by_group = defaultdict(list)
    for s in sites:
        by_group[s.get('group') or 'Sites'].append(s)
    for i, g in enumerate(groups):
        gf = folder(A, f'{g} ({len(by_group[g])})')
        for s in by_group[g]:
            add_point_pm(gf, s['site_id'], f'site_{i}', site_desc(s, srcs), float(s['lng']), float(s['lat']))

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
    B = folder(doc, f'B. Transmission within 5 km of any site ({len(seen)} segments, HIFLD mirror)')
    for sid, _, _, _, label in KV_STYLES:
        items = tiers.get(sid) or []
        if not items:
            continue
        tf = folder(B, f'{label} ({len(items)})')
        for p, parts in items:
            nm = ' - '.join(x for x in ((p.get('SUB_1') or '').strip(), (p.get('SUB_2') or '').strip()) if x and not x.upper().startswith(('UNKNOWN', 'NOT AVAIL'))) or f"line {p.get('ID')}"
            add_line_pm(tf, nm, sid, f"ID {esc(p.get('ID'))}<br/>Voltage {esc(p.get('VOLTAGE'))} kV ({esc(p.get('VOLT_CLASS'))})<br/>Owner {esc(p.get('OWNER'))}<br/>"
                                     f"Type {esc(p.get('TYPE'))}; Status {esc(p.get('STATUS'))}; attrs inferred {esc(p.get('INFERRED'))}", parts)
    C = folder(doc, f'C. Nearest transmission line per site ({len(nearest)})')
    Cs, Cc = folder(C, f'Identified nearest segments ({len(nearest)})'), folder(C, f'Site → line connectors ({len(nearest)})')
    site_by = {s['site_id']: s for s in sites}
    for sid_, (d, fp, p, parts) in sorted(nearest.items()):
        s = site_by[sid_]; v = kv(p); kvtxt = f'{v:g} kV' if v else 'kV n/p'
        desc = f"<b>{esc(sid_)}</b> nearest line {d:,.0f} m ({d / MI:.2f} mi)<br/>{kvtxt} ({esc(p.get('VOLT_CLASS'))}); ID {esc(p.get('ID'))}; owner {esc(p.get('OWNER'))}"
        add_line_pm(Cs, f'{sid_} — {kvtxt} @ {d:,.0f} m', 'nearLine', desc, parts)
        pm = sub(Cc, 'Placemark'); sub(pm, 'name', f'{sid_} — {d:,.0f} m'); sub(pm, 'styleUrl', '#connector'); sub(pm, 'description', desc)
        ls = sub(pm, 'LineString'); sub(ls, 'tessellate', '1'); sub(ls, 'coordinates', f"{s['lng']},{s['lat']},0 {fp[0]},{fp[1]},0")

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

    # ---- E. Flood SFHA within 1 km
    E = folder(doc, 'E. Flood: FEMA SFHA polygons within 1 km of any site', visible=False,
               description=f'Special Flood Hazard Area zones (A, AE, AH, AO, AR, A99, V, VE) from the NFHL responses scored for each site. Geometry simplified ~2 m and clipped to {CLIP_M} m around each site.')
    seen_z = set(); nz = 0
    for s in sites:
        resp = cached('flood', float(s['lat']), float(s['lng']), 'zones1000')
        if not resp:
            continue
        for f in resp.get('features') or []:
            p = f.get('properties') or {}
            if (p.get('SFHA_TF') or '').upper() != 'T':
                continue
            key = json.dumps(f.get('geometry', {}).get('coordinates', [])[:1])[:200] + str(p.get('FLD_ZONE'))
            if key in seen_z:
                continue
            seen_z.add(key)
            geom = clip_to_site(f.get('geometry') or {}, float(s['lat']), float(s['lng']))
            if not geom:
                continue
            nz += 1
            add_poly_pm(E, f"Zone {p.get('FLD_ZONE')} {p.get('ZONE_SUBTY') or ''}".strip(), 'sfha',
                        f"FLD_ZONE {esc(p.get('FLD_ZONE'))}; {esc(p.get('ZONE_SUBTY'))}; static BFE {esc(p.get('STATIC_BFE'))}; DFIRM {esc(p.get('DFIRM_ID'))}; clipped to {CLIP_M} m of {esc(s['site_id'])}", geom)
    E.find(NS + 'name').text += f' ({nz})'

    # ---- F. Wetlands within 500 m
    F = folder(doc, 'F. Wetlands: NWI polygons within 500 m of any site', visible=False,
               description=f'USFWS National Wetlands Inventory polygons from the responses scored for each site, clipped to {CLIP_M} m around each site. Photointerpreted; not a jurisdictional determination.')
    seen_w = set(); nw = 0
    for s in sites:
        resp = cached('wetlands', float(s['lat']), float(s['lng']), 'near500')
        if not resp:
            continue
        for f in resp.get('features') or []:
            p = f.get('properties') or {}
            attr = next((v for k, v in p.items() if k.upper().endswith('ATTRIBUTE')), '')
            wt = next((v for k, v in p.items() if k.upper().endswith('WETLAND_TYPE')), '')
            ac = next((v for k, v in p.items() if k.upper().endswith('ACRES')), None)
            key = json.dumps(f.get('geometry', {}).get('coordinates', [])[:1])[:200] + str(attr)
            if key in seen_w:
                continue
            seen_w.add(key)
            geom = clip_to_site(f.get('geometry') or {}, float(s['lat']), float(s['lng']))
            if not geom:
                continue
            nw += 1
            add_poly_pm(F, f'{wt} ({attr})', 'nwi', f"{esc(wt)}; Cowardin {esc(attr)}; {fmt(ac)} ac (whole polygon); drawn clipped to {CLIP_M} m of {esc(s['site_id'])}", geom)
    F.find(NS + 'name').text += f' ({nw})'

    # ---- G. Neighbors within 1 mi
    G = folder(doc, 'G. Neighbors within 1 mi of any site', visible=False)
    def points_from_cache(producer, suffix, style, label_fn, desc_fn, fold):
        seen_p = set(); n = 0
        for s in sites:
            la, ln = float(s['lat']), float(s['lng'])
            resp = cached(producer, la, ln, suffix)
            if not resp:
                continue
            for f in resp.get('features') or []:
                g = f.get('geometry') or {}
                if g.get('type') != 'Point':
                    continue
                x, y = g['coordinates'][:2]
                if point_dist_m(ln, la, x, y) > MI:
                    continue
                key = (round(x, 5), round(y, 5))
                if key in seen_p:
                    continue
                seen_p.add(key); n += 1
                p = f.get('properties') or {}
                add_point_pm(fold, label_fn(p), style, desc_fn(p), x, y)
        return n
    gs = folder(G, 'Schools (NCES)')
    n1 = points_from_cache('schools', 'pub5000', 'school', lambda p: p.get('NAME', ''), lambda p: f"public school; {esc(p.get('CITY'))}, {esc(p.get('STATE'))}", gs)
    n2 = points_from_cache('schools', 'prv5000', 'school', lambda p: p.get('NAME', ''), lambda p: f"private school; {esc(p.get('CITY'))}, {esc(p.get('STATE'))}", gs)
    gs.find(NS + 'name').text += f' ({n1 + n2})'
    gw = folder(G, 'Places of worship (HIFLD, IRS-geocoded)')
    n3 = points_from_cache('worship', 'r5000', 'worship', lambda p: (p.get('NAME') or '').title(), lambda p: f"{esc((p.get('CITY') or '').title())}, {esc(p.get('STATE'))}; geocoded from IRS filing", gw)
    gw.find(NS + 'name').text += f' ({n3})'
    def points_from_ref(rows, style, label_fn, desc_fn, fold):
        seen_p = set(); n = 0
        for s in sites:
            la, ln = float(s['lat']), float(s['lng'])
            for r in rows:
                try:
                    x, y = float(r['longitude']), float(r['latitude'])
                except (TypeError, ValueError, KeyError):
                    continue
                if point_dist_m(ln, la, x, y) > MI or (x, y) in seen_p:
                    continue
                seen_p.add((x, y)); n += 1
                add_point_pm(fold, label_fn(r), style, desc_fn(r), x, y)
        return n
    gn = folder(G, 'Nursing homes (CMS)')
    n4 = points_from_ref(ref_nh, 'nursing', lambda r: r.get('provider_name', '').title(), lambda r: f"{esc(r.get('number_of_certified_beds'))} certified beds; rating {esc(r.get('overall_rating'))}; {esc(r.get('ownership_type'))}", gn)
    gn.find(NS + 'name').text += f' ({n4})'
    gh = folder(G, 'Hospitals (CMS, Census-geocoded)')
    n5 = points_from_ref(ref_h, 'hospital', lambda r: r.get('facility_name', '').title(), lambda r: f"{esc(r.get('hospital_type'))}; emergency {esc(r.get('emergency_services'))}; geocode {esc(r.get('geocode_match_type'))}", gh)
    gh.find(NS + 'name').text += f' ({n5})'

    # ---- H. Site-by-site verification
    H = folder(doc, 'H. Site-by-site verification', visible=False,
               description='One folder per site: pin, identified nearest transmission line, connector, nearest substation. Tick one at a time; double-click to fly to it. '
                           'HIFLD geometry is national-scale and may sit 20-50 m off the visible towers.')
    for i, g in enumerate(groups):
        gf = folder(H, f'{g} ({len(by_group[g])})')
        by_state = defaultdict(list)
        for s in by_group[g]:
            by_state[s.get('state') or '??'].append(s)
        for stt in sorted(by_state):
            sf = folder(gf, f'{stt} ({len(by_state[stt])})')
            for s in sorted(by_state[stt], key=lambda s: s['site_id']):
                la, ln = float(s['lat']), float(s['lng']); nb = nearest.get(s['site_id'])
                dist = nb[0] if nb else 2000.0
                v = kv(nb[2]) if nb else None
                site_f = folder(sf, f"{s['site_id']} — {f'{v:g} kV' if v else 'kV n/p'} @ {dist:,.0f} m", visible=False)
                look = sub(site_f, 'LookAt'); sub(look, 'longitude', ln); sub(look, 'latitude', la); sub(look, 'altitude', '0')
                sub(look, 'heading', '0'); sub(look, 'tilt', '0'); sub(look, 'range', str(max(400.0, dist * 4.0))); sub(look, 'altitudeMode', 'relativeToGround')
                add_point_pm(site_f, f"{s['site_id']} (site)", 'verifySite', site_desc(s, srcs), ln, la)
                if nb:
                    d, fp, p, parts = nb
                    add_line_pm(site_f, f"nearest line — {f'{v:g} kV' if v else 'kV n/p'} @ {d:,.0f} m", 'nearLine', f"ID {esc(p.get('ID'))}; owner {esc(p.get('OWNER'))}", parts)
                    pm = sub(site_f, 'Placemark'); sub(pm, 'name', f'connector {d:,.0f} m'); sub(pm, 'styleUrl', '#connector')
                    ls = sub(pm, 'LineString'); sub(ls, 'tessellate', '1'); sub(ls, 'coordinates', f'{ln},{la},0 {fp[0]},{fp[1]},0')
                ns_ = nearest_sub.get(s['site_id'])
                if ns_:
                    d, p, x, y = ns_
                    add_point_pm(site_f, f"nearest substation — {(p.get('NAME') or '').strip() or p.get('ID')} @ {d:,.0f} m", 'substation',
                                 f"MAX_VOLT {esc(p.get('MAX_VOLT'))} (inferred {esc(p.get('MAX_INFER'))}); {esc(p.get('TYPE'))}; source {esc(p.get('SOURCE'))}", x, y)

    out = os.path.join(b, f'{name}.kmz')
    data = ET.tostring(kml, encoding='utf-8', xml_declaration=True)
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('doc.kml', data)
    t = data.decode('utf-8')
    print(f'wrote {out} ({os.path.getsize(out) / 1024:,.0f} KB): folders {t.count("<Folder")}, placemarks {t.count("<Placemark")}')
    print(f'  B transmission segments {len(seen)} | C nearest lines {len(nearest)} | D substations {len(seen_s)} | E SFHA polygons {nz} | '
          f'F NWI polygons {nw} | G schools {n1 + n2}, worship {n3}, nursing {n4}, hospitals {n5}')


if __name__ == '__main__':
    main()
