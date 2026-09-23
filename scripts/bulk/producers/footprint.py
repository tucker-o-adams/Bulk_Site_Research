# -*- coding: utf-8 -*-
"""The site footprint - the parcel boundary where one resolves, otherwise a 200 m square
centred on the pin - and what lies inside it.

Every other producer measures at the pin ("the pin is in Zone X"). This one measures over an
area, so a flood sliver or a wetland 60 m from the pin is counted rather than missed:

  shape     parcel.resolve(): the registered parcel polygon at the pin, the same one the parcel
            columns describe. No polygon (county unregistered or excluded, nothing at the pin)
            -> a north-aligned 200 m x 200 m square, 40,000 m2 = 9.88 ac, built in a Lambert
            azimuthal equal-area projection centred on the pin. A *failed* parcel query is a
            failure, not a square: rerun rather than guess.
  flood     FEMA NFHL L28 zone polygons intersected with the shape: acres by zone, SFHA acres
            and %, floodway acres, and the acres no zone covers (Area Not Included / no study).
            Unmapped is never counted as Zone X.
  wetlands  USFWS NWI polygons intersected with the shape: acres, %, acres by wetland type.

No new service calls in the usual case: both overlays reuse the flood and wetlands producers'
cached answers (zones within 1 km, NWI within 500 m), which cover the square and any parcel that
fits inside those radii. A parcel reaching past them gets its own bounding-box query. Areas are
computed in the pin-centred equal-area projection; NFHL and NWI geometry is simplified to ~2 m,
so a sliver under ~0.01 ac is at the limit of what this can resolve.

The square is not a parcel. Its acres describe the ground around the pin and `fp_basis` says so
on every row; parcel acreage stays in the parcel columns.
"""
import hashlib, math
from pyproj import Transformer
from shapely.geometry import box, shape
from shapely.ops import transform, unary_union
from cache import coord_key
from geom import arcgis_envelope_query, arcgis_query
from provenance import Value, absent, failed, now_iso
from producers import flood, parcel, wetlands

NAME = 'footprint'
SQUARE_M = 200
SOURCE = 'Site footprint (parcel boundary, else 200 m square) x FEMA NFHL + USFWS NWI'
VINTAGE = None
AC = 4046.8564224
BASIS_PARCEL, BASIS_SQUARE = 'parcel boundary', f'{SQUARE_M} m square'
UNMAPPED_ZONES = {'AREA NOT INCLUDED'}
METHOD_SHAPE = (f'parcel polygon from the registered parcel service at the pin; if none, a {SQUARE_M} m north-aligned '
                'square centred on the pin (Lambert azimuthal equal-area, pin-centred); area in that projection')
METHOD_FLOOD = ('NFHL L28 zone polygons (the flood producer\'s 1 km answer, or a bounding-box query when the footprint '
                'reaches past it) intersected with the footprint; unioned by zone; unmapped = footprint minus all zones')
METHOD_NWI = ('NWI Wetlands polygons (the wetlands producer\'s 500 m answer, or a bounding-box query when the footprint '
              'reaches past it) intersected with the footprint; unioned by Cowardin wetland type')
NOTE_SQUARE = (f'{SQUARE_M} m square around the pin stands in for the site - it is not a parcel; its acres describe '
               'the ground around the pin')
NOTE_NWI = 'NWI is photointerpreted, not a jurisdictional determination'

FIELDS = ['fp_basis', 'fp_acres', 'fp_flood_zones', 'fp_sfha_acres', 'fp_sfha_pct', 'fp_floodway_acres',
          'fp_flood_unmapped_acres', 'fp_nwi_acres', 'fp_nwi_pct', 'fp_nwi_types']
FLOOD_FIELDS, NWI_FIELDS = FIELDS[2:7], FIELDS[7:]

WHY_NO_PARCEL = {'no_county': 'no US county contains the pin', 'unregistered': 'no parcel service registered for the county',
                 'excluded': 'county excluded from the statewide parcel layer', 'no_polygon': 'parcel service returned no polygon at the pin',
                 'empty': 'parcel polygon returned without geometry'}


def projection(la, ln):
    """(to metres, to lng/lat) for a Lambert azimuthal equal-area frame centred on the pin."""
    crs = f'+proj=laea +lat_0={la} +lon_0={ln} +datum=WGS84 +units=m +no_defs'
    return (Transformer.from_crs('EPSG:4326', crs, always_xy=True).transform,
            Transformer.from_crs(crs, 'EPSG:4326', always_xy=True).transform)


def shape_at(la, ln, cache):
    """The footprint at a pin. Returns a dict:
        stage   'ok' or 'failed' (parcel lookup failed - no footprint, rerun)
        basis   'parcel boundary' / '200 m square'
        why     for a square: why there is no parcel
        ll, m   the shape as a shapely geometry in lng/lat, and in pin-centred metres
        fwd     lng/lat -> metres transform
        parcel  the parcel.resolve() result"""
    r = parcel.resolve(la, ln, cache)
    if r['stage'] in ('county_failed', 'parcel_failed'):
        return {'stage': 'failed', 'error': f"parcel lookup ({r['stage']}): {r['error']}", 'parcel': r}
    fwd, inv = projection(la, ln)
    stage = r['stage']
    if stage == 'ok':
        g = shape(r['feature'].get('geometry') or {'type': 'Polygon', 'coordinates': []})
        g = g if g.is_valid else g.buffer(0)
        if not g.is_empty and g.area > 0:
            return {'stage': 'ok', 'basis': BASIS_PARCEL, 'why': None, 'll': g, 'm': transform(fwd, g), 'fwd': fwd, 'parcel': r}
        stage = 'empty'
    h = SQUARE_M / 2
    m = box(-h, -h, h, h)
    return {'stage': 'ok', 'basis': BASIS_SQUARE, 'why': WHY_NO_PARCEL.get(stage, stage), 'll': transform(inv, m), 'm': m,
            'fwd': fwd, 'parcel': r}


def overlay_features(fp, la, ln, cache, producer, key_url, reach_m, layer_url, out_fields):
    """Polygons to intersect with the footprint: the producer's cached radius answer when the whole footprint
    lies inside that radius (every polygon touching the footprint is then in it), else a bounding-box query."""
    xmin, ymin, xmax, ymax = fp['m'].bounds
    far = max(math.hypot(x, y) for x in (xmin, xmax) for y in (ymin, ymax))
    if far <= reach_m:
        key, url = key_url
    else:
        bb = fp['ll'].bounds
        url = arcgis_envelope_query(layer_url, bb, out_fields)
        key = 'fpbox_' + hashlib.md5(repr([round(v, 6) for v in bb]).encode()).hexdigest()[:10]
    resp, fetched, err = cache.get_json(producer, coord_key(la, ln, key), url)
    return (resp or {}).get('features') or [], fetched, err


def clip(feats, fp):
    """[(properties, part of the feature inside the footprint, in metres)]"""
    out, env = [], fp['ll'].envelope
    for f in feats:
        try:
            g = shape(f.get('geometry'))
            if not g.intersects(env):
                continue
            g = transform(fp['fwd'], g)
            g = g if g.is_valid else g.buffer(0)
            c = g.intersection(fp['m'])
        except Exception:                 # a malformed ring from the source: skip it, never guess its area
            continue
        if not c.is_empty and c.area > 0:
            out.append((f.get('properties') or {}, c))
    return out


def zone_label(p):
    z = (p.get('FLD_ZONE') or '?').strip()
    sub = (p.get('ZONE_SUBTY') or '').upper()
    if 'FLOODWAY' in sub:
        return f'{z} floodway'
    if z == 'X' and '0.2' in sub:
        return 'X 0.2%'
    if z == 'X' and 'LEVEE' in sub:
        return 'X levee'
    return z


def is_sfha(p):
    return (p.get('SFHA_TF') or '').upper() == 'T' or p.get('FLD_ZONE') in flood.SFHA_ZONES


def area_ac(parts):
    return unary_union([g for _, g in parts]).area / AC if parts else 0.0


def breakdown(groups, total_m2):
    """'X 9.71 ac (98.2%); AE 0.18 ac (1.8%)', largest first."""
    rows = sorted(((k, unary_union(v).area) for k, v in groups.items()), key=lambda kv: -kv[1])
    return '; '.join(f'{k} {a / AC:,.3f} ac ({100 * a / total_m2:.1f}%)' for k, a in rows if a / AC >= 0.0005)


def run(site, cache):
    la, ln = site.lat, site.lng
    fp = shape_at(la, ln, cache)
    if fp['stage'] == 'failed':
        return [failed(f, SOURCE, parcel.LYR, METHOD_SHAPE, fp['error'] + '; rerun - a failed lookup is never replaced by the square')
                for f in FIELDS]
    total = fp['m'].area
    r = fp['parcel']
    if fp['basis'] == BASIS_PARCEL:
        svc = r['svc']
        src_shape, url_shape = f"{svc.get('name')} ({svc.get('owner')})", svc['base']
        note_shape = 'the parcel the parcel_* columns describe; check parcel_owner_check before relying on it'
    else:
        src_shape, url_shape = f'Constructed: {SQUARE_M} m square centred on the site pin', ''
        note_shape = f"{NOTE_SQUARE}; no parcel because: {fp['why']}"
    out = [Value('fp_basis', fp['basis'], src_shape, url_shape, METHOD_SHAPE, fetched_at=r['fetched_parcel'] or now_iso(), note=note_shape),
           Value('fp_acres', round(total / AC, 4), src_shape, url_shape, METHOD_SHAPE, fetched_at=r['fetched_parcel'] or now_iso(), note=note_shape)]
    basis_note = '' if fp['basis'] == BASIS_PARCEL else f' - over the {SQUARE_M} m square, not a parcel'

    # ---- flood
    feats, fetched, err = overlay_features(fp, la, ln, cache, 'flood', flood.zones_request(la, ln), flood.SFHA_SEARCH_M,
                                           f'{flood.NFHL}/28', flood.ZONE_FIELDS)
    if err:
        out += [failed(f, flood.SOURCE, flood.NFHL, METHOD_FLOOD, err) for f in FLOOD_FIELDS]
    else:
        parts = clip(feats, fp)
        mapped = [(p, g) for p, g in parts if (p.get('FLD_ZONE') or '').upper() not in UNMAPPED_ZONES]
        groups = {}
        for p, g in mapped:
            groups.setdefault(zone_label(p), []).append(g)
        unmapped_ac = max(0.0, (total - (unary_union([g for _, g in mapped]).area if mapped else 0.0)) / AC)
        note = ('FEMA NFHL geometry simplified to ~2 m; see fema_panel_effective for the FIRM date' + basis_note)
        mk = lambda fld, val, n=note: Value(fld, val, flood.SOURCE, flood.NFHL, METHOD_FLOOD, fetched_at=fetched or now_iso(), note=n)
        if not mapped:
            why = 'no FEMA flood zone covers any of the footprint (Area Not Included or no NFHL study); see fema_determination'
            out += [absent(f, flood.SOURCE, flood.NFHL, METHOD_FLOOD, note=why) for f in FLOOD_FIELDS[:4]]
            out.append(mk('fp_flood_unmapped_acres', round(unmapped_ac, 4), why))
        else:
            part_note = note + (f'; {unmapped_ac:,.3f} ac of the footprint has no FEMA determination - SFHA figures cover '
                                'the mapped part only' if unmapped_ac >= 0.0005 else '')
            sfha = area_ac([(p, g) for p, g in mapped if is_sfha(p)])
            out += [mk('fp_flood_zones', breakdown(groups, total), part_note),
                    mk('fp_sfha_acres', round(sfha, 4), part_note),
                    mk('fp_sfha_pct', round(100 * sfha * AC / total, 2), part_note),
                    mk('fp_floodway_acres', round(area_ac([(p, g) for p, g in mapped if 'FLOODWAY' in (p.get('ZONE_SUBTY') or '').upper()]), 4), part_note),
                    mk('fp_flood_unmapped_acres', round(unmapped_ac, 4), part_note)]

    # ---- wetlands
    feats, fetched, err = overlay_features(fp, la, ln, cache, 'wetlands', wetlands.near_request(la, ln), wetlands.SEARCH_M,
                                           wetlands.WET, '*')
    if err:
        out += [failed(f, wetlands.SOURCE, wetlands.WET, METHOD_NWI, err) for f in NWI_FIELDS]
    else:
        st, _, e_st = cache.get_json('wetlands', coord_key(la, ln, 'status'), arcgis_query(wetlands.STATUS, la, ln, 'STATUS'))
        mapped_nwi = bool(not e_st and (st or {}).get('features'))
        note = NOTE_NWI + basis_note + ('' if mapped_nwi else
                                        '; the pin is not in an NWI-mapped area (or the status layer did not answer): zero is not evidence of no wetlands')
        parts = clip(feats, fp)
        groups = {}
        for p, g in parts:
            groups.setdefault(wetlands._attr(p, 'WETLAND_TYPE') or 'unclassified', []).append(g)
        wet = area_ac(parts)
        mk = lambda fld, val: Value(fld, val, wetlands.SOURCE, wetlands.WET, METHOD_NWI, fetched_at=fetched or now_iso(), note=note)
        out += [mk('fp_nwi_acres', round(wet, 4)), mk('fp_nwi_pct', round(100 * wet * AC / total, 2))]
        out.append(mk('fp_nwi_types', breakdown(groups, total)) if parts else
                   absent('fp_nwi_types', wetlands.SOURCE, wetlands.WET, METHOD_NWI, note='no NWI polygon intersects the footprint; ' + note))
    return out
