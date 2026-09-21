# -*- coding: utf-8 -*-
"""Nearest transmission line per site, from the HIFLD / EIA layer.

Port of scripts/windstream_kmz/tx_distance.py (Aug 2026), same method so the
Windstream 200 regression must match it exactly:

  * buffer-query the polyline service around the point (RADIUS_M), geometry in WGS84
  * exact point-to-segment distance computed locally in a local ENU frame
    (accurate well under 1 % at these scales)
  * nearest line of ANY voltage, and separately the nearest >= 100 kV line

Source caveats that travel with every row (tbdi-pasa D-015): HIFLD Open was
retired by DHS in Aug 2025; this ArcGIS layer is a mirror whose data last
changed 2025-08-26. Geometry is national-scale and commonly sits 20-50 m off
the towers visible in imagery. It is the full national layer (94,619 segments
incl. sub-100 kV); the FEMA Region-9 copy is filtered to >= 100 kV and was
rejected for silently missing 69 kV lines.
"""
import json, math, urllib.parse
from provenance import Value, absent, failed, now_iso

NAME = 'transmission'
LYR = ('https://services2.arcgis.com/FiaPA4ga0iQKduv3/arcgis/rest/services/'
       'US_Electric_Power_Transmission_Lines/FeatureServer/0')
SOURCE = 'HIFLD US Electric Power Transmission Lines (ArcGIS mirror of retired HIFLD Open)'
VINTAGE = '2025-08-26'          # layer editingInfo.dataLastEditDate, checked 2026-09-21
RADIUS_M = 15000
OUT_FIELDS = 'VOLTAGE,VOLT_CLASS,OWNER,STATUS,TYPE,SOURCEDATE,ID,SUB_1,SUB_2,INFERRED'
METHOD = (f'HIFLD segments within {RADIUS_M} m of the site point; exact point-to-segment '
          'distance in a local ENU frame; nearest of any voltage, and nearest >= 100 kV')
NOTE = 'HIFLD mirror (dataset retired Aug 2025); line geometry may sit 20-50 m off visible towers'

FIELDS = ['tx_nearest_m', 'tx_nearest_ft', 'tx_voltage_kv', 'tx_volt_class', 'tx_voltage_basis',
          'tx_line_name', 'tx_line_id', 'tx_owner', 'tx_type', 'tx_status', 'tx_attrs_inferred',
          'tx_100kv_nearest_m', 'tx_100kv_voltage_kv', 'tx_100kv_line_name', 'tx_100kv_line_id',
          'tx_100kv_owner']


def seg_dist_m(px, py, ax, ay, bx, by):
    """Point-to-segment distance in metres, local ENU around (px,py)."""
    k = math.cos(math.radians(py))
    AX, AY = (ax - px) * 111320 * k, (ay - py) * 110540
    BX, BY = (bx - px) * 111320 * k, (by - py) * 110540
    dx, dy = BX - AX, BY - AY
    if dx == 0 and dy == 0:
        return math.hypot(AX, AY)
    t = max(0.0, min(1.0, ((0 - AX) * dx + (0 - AY) * dy) / (dx * dx + dy * dy)))
    return math.hypot(AX + t * dx, AY + t * dy)


def _parts(g):
    if not g:
        return []
    if g.get('type') == 'LineString':
        return [g['coordinates']]
    if g.get('type') == 'MultiLineString':
        return g['coordinates']
    return []


def _ident(p):
    """Human-usable circuit name from endpoint substations."""
    clean = lambda s: '' if (not s or s.upper().startswith(('UNKNOWN', 'NOT AVAIL'))) else s
    a, b = clean((p.get('SUB_1') or '').strip()), clean((p.get('SUB_2') or '').strip())
    return f'{a} - {b}' if a and b else (a or b or '')


def _kv(p):
    try:
        v = float(p.get('VOLTAGE'))
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


def _basis(p):
    if _kv(p) is not None:
        return 'numeric'
    vc = (p.get('VOLT_CLASS') or '').upper()
    return 'class_band' if vc and not vc.startswith('NOT AVAIL') else 'not_published'


def query_url(lat, lng, radius_m=RADIUS_M):
    geom = json.dumps({'x': lng, 'y': lat, 'spatialReference': {'wkid': 4326}})
    return (LYR + f'/query?f=geojson&outFields={OUT_FIELDS}&returnGeometry=true'
            '&geometryType=esriGeometryPoint&inSR=4326&outSR=4326'
            f'&distance={radius_m}&units=esriSRUnit_Meter&spatialRel=esriSpatialRelIntersects'
            '&geometry=' + urllib.parse.quote(geom))


def nearest(features, lat, lng):
    """Return (best, best_hv): each (dist_m, props, parts) or None."""
    best = best_hv = None
    for f in features:
        parts = _parts(f.get('geometry'))
        p = f.get('properties') or {}
        dmin = None
        for part in parts:
            for i in range(len(part) - 1):
                d = seg_dist_m(lng, lat, part[i][0], part[i][1], part[i + 1][0], part[i + 1][1])
                if dmin is None or d < dmin:
                    dmin = d
        if dmin is None:
            continue
        if best is None or dmin < best[0]:
            best = (dmin, p, parts)
        kv = _kv(p)
        if kv is not None and kv >= 100 and (best_hv is None or dmin < best_hv[0]):
            best_hv = (dmin, p, parts)
    return best, best_hv


def run(site, cache):
    url = query_url(site.lat, site.lng)
    resp, fetched, err = cache.get_json(NAME, site.site_id, url)
    mk = lambda fld, val, **kw: Value(fld, val, SOURCE, LYR, METHOD, vintage=VINTAGE,
                                      fetched_at=fetched or now_iso(), note=NOTE, **kw)
    if err:
        return [failed(f, SOURCE, LYR, METHOD, err) for f in FIELDS]
    best, hv = nearest(resp.get('features') or [], site.lat, site.lng)
    if best is None:
        return [absent(f, SOURCE, LYR, METHOD, note=f'no transmission line within {RADIUS_M} m',
                       vintage=VINTAGE) for f in FIELDS]
    d, p, _ = best
    out = [mk('tx_nearest_m', round(d, 1)), mk('tx_nearest_ft', round(d * 3.28084)),
           mk('tx_voltage_kv', _kv(p)), mk('tx_volt_class', p.get('VOLT_CLASS')),
           mk('tx_voltage_basis', _basis(p)), mk('tx_line_name', _ident(p)),
           mk('tx_line_id', p.get('ID')), mk('tx_owner', p.get('OWNER')), mk('tx_type', p.get('TYPE')),
           mk('tx_status', p.get('STATUS')), mk('tx_attrs_inferred', p.get('INFERRED'))]
    if hv:
        dh, ph, _ = hv
        out += [mk('tx_100kv_nearest_m', round(dh, 1)), mk('tx_100kv_voltage_kv', _kv(ph)),
                mk('tx_100kv_line_name', _ident(ph)), mk('tx_100kv_line_id', ph.get('ID')),
                mk('tx_100kv_owner', ph.get('OWNER'))]
    else:
        out += [absent(f, SOURCE, LYR, METHOD, note=f'no line >= 100 kV within {RADIUS_M} m',
                       vintage=VINTAGE)
                for f in ('tx_100kv_nearest_m', 'tx_100kv_voltage_kv', 'tx_100kv_line_name',
                          'tx_100kv_line_id', 'tx_100kv_owner')]
    return out
