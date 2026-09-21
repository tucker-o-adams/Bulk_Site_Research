import json, time, os, requests, geopandas as gpd, numpy as np, rasterio, datetime
from rasterio.transform import from_bounds
from shapely.geometry import box

OUT = 'out/site2'; G = OUT + '/site2_fema.gpkg'
S = requests.Session(); S.headers.update({'User-Agent': 'Mozilla/5.0'})
log = []; T0 = time.time()
CRS = 32618  # UTM 18N covers Williamsburg VA


def L(m):
    log.append('[%6.1fs] %s' % (time.time() - T0, m)); print(log[-1], flush=True)


parcel = gpd.read_file(G, layer='parcel')
utm = parcel.to_crs(CRS)
minx, miny, maxx, maxy = utm.buffer(0.5 * 1609.344).total_bounds
w, h = maxx - minx, maxy - miny
if w / h < 16 / 9:
    nw = h * 16 / 9; cx = (minx + maxx) / 2; minx, maxx = cx - nw / 2, cx + nw / 2
else:
    nh = w * 9 / 16; cy = (miny + maxy) / 2; miny, maxy = cy - nh / 2, cy + nh / 2
w, h = maxx - minx, maxy - miny
L('extent EPSG:%d  %.1f %.1f %.1f %.1f  (%.0f x %.0f m)' % (CRS, minx, miny, maxx, maxy, w, h))

BASE = 'https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPImagery/ImageServer'
NX = NY = 2; TILE = 3200
px_w = NX * TILE; px_h = int(round(NY * TILE * h / w)); tile_h = px_h // NY
L('mosaic %d x %d px -> %.3f m/px (2x2 tiles of %d px, server cap 4000)' % (px_w, px_h, w / px_w, TILE))
mos = np.zeros((3, px_h, px_w), 'uint8'); urls = []
for iy in range(NY):
    for ix in range(NX):
        x0 = minx + w * ix / NX; x1 = minx + w * (ix + 1) / NX
        y1 = maxy - h * iy / NY; y0 = maxy - h * (iy + 1) / NY
        p = {'bbox': '%f,%f,%f,%f' % (x0, y0, x1, y1), 'bboxSR': CRS, 'imageSR': CRS,
             'size': '%d,%d' % (TILE, tile_h), 'format': 'tiff', 'f': 'image', 'adjustAspectRatio': 'false'}
        ok = False
        for att in range(3):
            try:
                r = S.get(BASE + '/exportImage', params=p, timeout=300)
                if r.status_code == 200 and 'image' in (r.headers.get('Content-Type') or ''):
                    t = OUT + '/_t.tif'; open(t, 'wb').write(r.content)
                    with rasterio.open(t) as ds:
                        a = ds.read([1, 2, 3])
                    mos[:, iy * tile_h:(iy + 1) * tile_h, ix * TILE:(ix + 1) * TILE] = a[:, :tile_h, :TILE]
                    os.remove(t); urls.append(r.url); ok = True
                    L('  tile %d,%d OK (%d bytes)' % (iy, ix, len(r.content))); break
                L('  tile %d,%d attempt %d HTTP %s %s' % (iy, ix, att + 1, r.status_code, r.text[:100]))
            except Exception as e:
                L('  tile %d,%d attempt %d %s: %s' % (iy, ix, att + 1, type(e).__name__, str(e)[:120]))
            time.sleep(3)
        if not ok:
            L('  TILE %d,%d FAILED' % (iy, ix))
tr = from_bounds(minx, miny, maxx, maxy, px_w, px_h)
with rasterio.open(OUT + '/naip_site2.tif', 'w', driver='GTiff', height=px_h, width=px_w, count=3,
                   dtype='uint8', crs='EPSG:%d' % CRS, transform=tr, compress='deflate', photometric='rgb') as ds:
    ds.write(mos)
L('wrote naip_site2.tif  %.1f MB' % (os.path.getsize(OUT + '/naip_site2.tif') / 1e6))
for iy in range(2):
    for ix in range(2):
        q = mos[:, iy * px_h // 2:(iy + 1) * px_h // 2, ix * px_w // 2:(ix + 1) * px_w // 2]
        L('  quad %d%d mean %.2f std %.2f' % (iy, ix, q.mean(), q.std()))

cen = parcel.geometry.iloc[0].centroid
qr = S.get(BASE + '/query', params={'f': 'json', 'geometry': '%f,%f' % (cen.x, cen.y),
           'geometryType': 'esriGeometryPoint', 'inSR': 4326, 'spatialRel': 'esriSpatialRelIntersects',
           'where': 'Category=1', 'outFields': 'Name,Year,acquisition_date,resolution_value,resolution_units,vendor',
           'returnGeometry': 'false'}, timeout=180)
scenes = []
for f in qr.json().get('features', []):
    a = f['attributes']
    ad = a.get('acquisition_date')
    ad = datetime.datetime.fromtimestamp(ad / 1000, datetime.UTC).strftime('%Y-%m-%d') if ad else None
    scenes.append([a.get('Name'), a.get('Year'), ad, a.get('resolution_value'), a.get('resolution_units'), a.get('vendor')])
    L('  NAIP scene: %s' % scenes[-1])

# ---------------- context lines ----------------
bb = gpd.GeoSeries([box(minx, miny, maxx, maxy)], crs=CRS).to_crs(4326).total_bounds
env = {"xmin": bb[0], "ymin": bb[1], "xmax": bb[2], "ymax": bb[3], "spatialReference": {"wkid": 4326}}


def q(svc, layer, fields, name):
    url = 'https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/%s/MapServer/%d/query' % (svc, layer)
    p = {'f': 'geojson', 'geometry': json.dumps(env), 'geometryType': 'esriGeometryEnvelope', 'inSR': 4326,
         'outSR': 4326, 'spatialRel': 'esriSpatialRelIntersects', 'outFields': fields, 'returnGeometry': 'true'}
    for i in range(4):
        try:
            r = S.post(url, data=p, timeout=180); j = r.json()
            if 'error' in j:
                L('  %s ERROR %s' % (name, json.dumps(j['error'])[:150])); time.sleep(3); continue
            n = len(j.get('features', []))
            L('  %-18s L%-2d -> %d features' % (name, layer, n))
            return gpd.GeoDataFrame.from_features(j['features'], crs='EPSG:4326') if n else None
        except Exception as e:
            L('  %s attempt %d %s: %s' % (name, i + 1, type(e).__name__, str(e)[:120])); time.sleep(4)
    return None


L('TIGERweb context:')
for key, svc, lyr, fields in [('roads_primary', 'Transportation', 2, 'NAME,MTFCC'),
                              ('roads_secondary', 'Transportation', 6, 'NAME,MTFCC'),
                              ('roads_local', 'Transportation', 8, 'NAME,MTFCC'),
                              ('railroads', 'Transportation', 9, 'NAME,MTFCC'),
                              ('hydro_linear', 'Hydro', 0, 'NAME,MTFCC'),
                              ('hydro_areal', 'Hydro', 1, 'NAME,MTFCC')]:
    g = q(svc, lyr, fields, key)
    if g is not None and len(g):
        g.to_file(G, layer=key, driver='GPKG')
        nm = sorted(set(x for x in g.get('NAME', []).dropna() if x)) if 'NAME' in g else []
        L('     named (%d): %s' % (len(nm), ', '.join(nm[:14])))

json.dump({'extent': [minx, miny, maxx, maxy], 'crs': CRS, 'size_px': [px_w, px_h], 'res_m': w / px_w,
           'urls': urls, 'scenes': scenes}, open(OUT + '/site2_imagery.json', 'w'), indent=2, default=str)
open(OUT + '/site2_imagery_log.txt', 'w', encoding='utf-8').write('\n'.join(log))
L('DONE %.1fs' % (time.time() - T0))
