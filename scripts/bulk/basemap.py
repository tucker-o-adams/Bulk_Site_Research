# -*- coding: utf-8 -*-
"""Basemap providers: the imagery under figure.py's overlays, chosen per audience.

The overlays (flood zones, wetlands, footprint, roads, acreage panel) are drawn the same way on any
basemap. What changes is where the picture underneath comes from, and whether that source may leave
the building. Each provider declares:

    name         what --basemap selects
    label        short name printed with the attribution
    licence      the terms the imagery is used under, as a person would state them
    cleared_for  the audiences it may be used for: 'external' (anything sold or sent to a client)
                 and/or 'internal' (screening decks, team discussion)
    fetch(...)   -> (Basemap, error): a georeferenced RGB GeoTIFF for the frame, cached, plus its
                 attribution text

`get` refuses a provider that is not cleared for the requested audience, so an internal-only
source cannot end up in a sold report by accident. figure.py marks every internal figure
"INTERNAL - not for distribution".

Registered today: `naip` (USGS/USDA NAIP, public domain, cleared for both). To add one, write a
fetch function with the same signature and add a Provider to PROVIDERS - figure.py needs no change.
Google Maps / Google Earth imagery cannot be a provider, for either audience: automated retrieval
is not permitted outside the paid Google Maps Platform. The internal route to Google imagery is
manual - open the batch KMZ (kmz.py) in Google Earth Pro, which draws the same overlays over
Google's imagery with Google's own attribution.
"""
import math, os, re, time, urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np
import rasterio
from rasterio.transform import from_bounds

from cache import UA, coord_key

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.abspath(os.path.join(HERE, '..', '..', 'data', 'cache'))
AUDIENCES = ('external', 'internal')


@dataclass
class Basemap:
    provider: str
    path: str                        # georeferenced RGB GeoTIFF covering the frame
    attribution: str                 # printed on the figure, verbatim
    meta: dict = field(default_factory=dict)


@dataclass
class Provider:
    name: str
    label: str
    licence: str
    cleared_for: frozenset
    fetch: object                    # fetch(bounds, epsg, key, res_m, lat, lng, cache) -> (Basemap, error)


def fetch_bytes(url, tries=3, timeout=300):
    err = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                ctype = r.headers.get('Content-Type') or ''
                body = r.read()
            if 'image' in ctype:
                return body, None
            err = f'not an image ({ctype}): {body[:120]!r}'
        except Exception as e:
            err = f'{type(e).__name__}: {str(e)[:160]}'
        time.sleep(3 * (i + 1))
    return None, err


# ---------------------------------------------------------------- NAIP
NAIP = 'https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPImagery/ImageServer'
TILE_MAX = 3200          # NAIP exportImage caps at 4000 px a side


def naip_scene(lat, lng, cache):
    """The most recent NAIP quad at the pin: its name and acquisition date."""
    sc, _, _ = cache.get_json('naip', coord_key(lat, lng, 'scene'),
                              f'{NAIP}/query?f=json&geometry={lng},{lat}&geometryType=esriGeometryPoint&inSR=4326'
                              '&spatialRel=esriSpatialRelIntersects&where=Category%3D1'
                              '&outFields=Name,Year,acquisition_date,resolution_value&returnGeometry=false')
    scenes = [f['attributes'] for f in (sc or {}).get('features') or []]
    scene = max(scenes, key=lambda a: a.get('acquisition_date') or 0) if scenes else {}
    m = re.search(r'_(\d{4})(\d{2})(\d{2})$', scene.get('Name') or '')     # NAIP quad names end in the acquisition date
    date = (datetime.fromtimestamp(scene['acquisition_date'] / 1000, tz=timezone.utc).date().isoformat()
            if scene.get('acquisition_date') else f'{m.group(1)}-{m.group(2)}-{m.group(3)}' if m else 'date unknown')
    return scene, date


def naip_fetch(bounds, epsg, key, res_m, lat, lng, cache):
    """NAIP RGB mosaic for the frame (exportImage, tiled under the 4000 px cap), cached as a GeoTIFF."""
    scene, date = naip_scene(lat, lng, cache)
    attribution = (f"Imagery: USGS NAIP (USDA FSA, public domain),\n{scene.get('Name') or 'scene unknown'}, "
                   f"acquired {date}")
    meta = {'scene': scene, 'acquired': date, 'service': NAIP}
    d = os.path.join(CACHE, 'naip'); os.makedirs(d, exist_ok=True)
    path = os.path.join(d, key + '.tif')
    if os.path.exists(path):
        return Basemap('naip', path, attribution, meta), None
    minx, miny, maxx, maxy = bounds
    w, h = maxx - minx, maxy - miny
    px_w = int(min(2 * TILE_MAX, max(1600, round(w / res_m))))
    px_h = int(round(px_w * h / w))
    nx, ny = math.ceil(px_w / TILE_MAX), math.ceil(px_h / TILE_MAX)
    xs = [round(px_w * i / nx) for i in range(nx + 1)]
    ys = [round(px_h * j / ny) for j in range(ny + 1)]
    mos = np.zeros((3, px_h, px_w), 'uint8')
    for j in range(ny):
        for i in range(nx):
            x0, x1 = minx + w * xs[i] / px_w, minx + w * xs[i + 1] / px_w
            y1, y0 = maxy - h * ys[j] / px_h, maxy - h * ys[j + 1] / px_h
            tw, th = xs[i + 1] - xs[i], ys[j + 1] - ys[j]
            url = (f'{NAIP}/exportImage?bbox={x0},{y0},{x1},{y1}&bboxSR={epsg}&imageSR={epsg}&size={tw},{th}'
                   f'&format=tiff&f=image&adjustAspectRatio=false')
            body, err = fetch_bytes(url)
            if err:
                return None, f'NAIP tile {j},{i}: {err}'
            with rasterio.MemoryFile(body) as mf, mf.open() as ds:
                a = ds.read([1, 2, 3])
            mos[:, ys[j]:ys[j] + th, xs[i]:xs[i] + tw] = a[:, :th, :tw]
    with rasterio.open(path, 'w', driver='GTiff', height=px_h, width=px_w, count=3, dtype='uint8',
                       crs=f'EPSG:{epsg}', transform=from_bounds(minx, miny, maxx, maxy, px_w, px_h),
                       compress='deflate', photometric='rgb') as ds:
        ds.write(mos)
    return Basemap('naip', path, attribution, meta), None


# ---------------------------------------------------------------- registry
PROVIDERS = {
    'naip': Provider('naip', 'USGS NAIP', 'Public domain (USDA Farm Service Agency)',
                     frozenset({'external', 'internal'}), naip_fetch),
}


def check(name, audience):
    """The provider for `name`, or SystemExit when it is unknown or not cleared for `audience`."""
    if audience not in AUDIENCES:
        raise SystemExit(f'audience must be one of {AUDIENCES}, not {audience!r}')
    p = PROVIDERS.get(name)
    if p is None:
        raise SystemExit(f'unknown basemap {name!r}; registered: {", ".join(PROVIDERS)}')
    if audience not in p.cleared_for:
        raise SystemExit(f'basemap {name!r} ({p.licence}) is not cleared for {audience} use; '
                         f'cleared for: {", ".join(sorted(p.cleared_for))}')
    return p


def get(name, audience, bounds, epsg, key, res_m, lat, lng, cache):
    """Fetch (or read from cache) the basemap for one frame. Returns (Basemap, error)."""
    return check(name, audience).fetch(bounds, epsg, key, res_m, lat, lng, cache)
