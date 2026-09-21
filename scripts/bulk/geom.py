# -*- coding: utf-8 -*-
"""Small planar-geometry helpers on WGS84 coordinates, in a local ENU frame
around the query point (metres). Accurate well under 1 % at the distances the
pipeline cares about (tens of km). No dependencies."""
import json, math, urllib.parse


def seg_dist_m(px, py, ax, ay, bx, by):
    """Point (px,py) to segment (ax,ay)-(bx,by), metres. Lng/lat order."""
    k = math.cos(math.radians(py))
    AX, AY = (ax - px) * 111320 * k, (ay - py) * 110540
    BX, BY = (bx - px) * 111320 * k, (by - py) * 110540
    dx, dy = BX - AX, BY - AY
    if dx == 0 and dy == 0:
        return math.hypot(AX, AY)
    t = max(0.0, min(1.0, ((0 - AX) * dx + (0 - AY) * dy) / (dx * dx + dy * dy)))
    return math.hypot(AX + t * dx, AY + t * dy)


def point_dist_m(lng1, lat1, lng2, lat2):
    k = math.cos(math.radians(lat1))
    return math.hypot((lng2 - lng1) * 111320 * k, (lat2 - lat1) * 110540)


def ring_contains(ring, px, py):
    """Even-odd point-in-ring test. ring = [(lng,lat), ...]."""
    inside = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i][0], ring[i][1]
        x2, y2 = ring[(i + 1) % n][0], ring[(i + 1) % n][1]
        if (y1 > py) != (y2 > py):
            x = x1 + (py - y1) * (x2 - x1) / (y2 - y1)
            if x > px:
                inside = not inside
    return inside


def ring_dist_m(ring, px, py):
    return min(seg_dist_m(px, py, ring[i][0], ring[i][1], ring[i + 1][0], ring[i + 1][1])
               for i in range(len(ring) - 1)) if len(ring) > 1 else float('inf')


def polygon_dist_m(rings, px, py):
    """Distance from point to a polygon given as a list of rings (first = outer,
    rest = holes, GeoJSON convention). 0 when the point is inside."""
    if not rings:
        return float('inf')
    if ring_contains(rings[0], px, py) and not any(ring_contains(h, px, py) for h in rings[1:]):
        return 0.0
    return min(ring_dist_m(r, px, py) for r in rings)


def geojson_polygon_dist_m(geometry, px, py):
    """Distance to a GeoJSON Polygon or MultiPolygon."""
    if not geometry:
        return float('inf')
    t = geometry.get('type')
    if t == 'Polygon':
        return polygon_dist_m(geometry['coordinates'], px, py)
    if t == 'MultiPolygon':
        return min(polygon_dist_m(poly, px, py) for poly in geometry['coordinates'])
    return float('inf')


def esri_point(lat, lng):
    return urllib.parse.quote(json.dumps({'x': lng, 'y': lat, 'spatialReference': {'wkid': 4326}}))


def arcgis_query(layer_url, lat, lng, out_fields='*', distance_m=None, geometry=False, where=None, fmt='json',
                 precision=None, max_offset_m=None):
    """Build an ArcGIS REST query URL: features intersecting the point (or a
    distance_m buffer around it)."""
    u = (f'{layer_url}/query?f={fmt}&outFields={urllib.parse.quote(out_fields)}'
         f'&returnGeometry={"true" if geometry else "false"}'
         f'&geometryType=esriGeometryPoint&inSR=4326&outSR=4326&spatialRel=esriSpatialRelIntersects'
         f'&geometry={esri_point(lat, lng)}')
    if distance_m:
        u += f'&distance={distance_m}&units=esriSRUnit_Meter'
    if where:
        u += '&where=' + urllib.parse.quote(where)
    if precision is not None:
        u += f'&geometryPrecision={precision}'
    if max_offset_m is not None:
        u += f'&maxAllowableOffset={max_offset_m / 111320:.8f}'   # degrees, approx
    return u
