"""Site 2 - 1637 Green Mount Pkwy, Williamsburg VA 23185.
Parcel from VGIN statewide parcels; county from TIGERweb; flood from FEMA NFHL;
context from TIGERweb. All public REST, no manual downloads."""
import json, time, os, requests, geopandas as gpd, pandas as pd, simplekml, zipfile
from shapely.geometry import box

AC = 4046.8564224
QDATE = '2026-08-26'
OUT = 'out/site2'
os.makedirs(OUT, exist_ok=True)
G = OUT + '/site2_fema.gpkg'
S = requests.Session(); S.headers.update({'User-Agent': 'Mozilla/5.0'})
log = []; T0 = time.time()


def L(m):
    log.append('[%6.1fs] %s' % (time.time() - T0, m)); print(log[-1], flush=True)


def post(url, params, tries=5, tag=''):
    for i in range(tries):
        try:
            r = S.post(url, data=params, timeout=180)
            j = r.json()
            if isinstance(j, dict) and 'error' in j:
                L('  %s attempt %d ERROR %s' % (tag, i + 1, json.dumps(j['error'])[:180])); time.sleep(3); continue
            L('  %s HTTP %d -> %d features (attempt %d)' % (tag, r.status_code, len(j.get('features', [])), i + 1))
            return j
        except Exception as e:
            L('  %s attempt %d %s: %s' % (tag, i + 1, type(e).__name__, str(e)[:140])); time.sleep(4)
    L('  %s FAILED after %d attempts' % (tag, tries)); return None


# ---------------- 1. parcel ----------------
LON, LAT = -76.589451588965, 37.201089140587
L('geocode (Esri World Geocoding, score 100): %.6f, %.6f' % (LON, LAT))
VG = 'https://vginmaps.vdem.virginia.gov/arcgis/rest/services/VA_Base_Layers/VA_Parcels/MapServer/0/query'
j = post(VG, {'f': 'geojson', 'geometry': '%f,%f' % (LON, LAT), 'geometryType': 'esriGeometryPoint',
              'inSR': 4326, 'outSR': 4326, 'spatialRel': 'esriSpatialRelIntersects',
              'outFields': '*', 'returnGeometry': 'true'}, tag='VGIN parcel')
parcel = gpd.GeoDataFrame.from_features(j['features'], crs='EPSG:4326')
poly = parcel.geometry.iloc[0]
p5 = parcel.to_crs(5070); PA = p5.area.iloc[0]; pg5 = p5.geometry.iloc[0]
nvert = len(poly.exterior.coords) - 1
cen = poly.centroid
L('PARCEL: id=%s locality=%s FIPS=%s' % (parcel['PARCELID'].iloc[0], parcel['LOCALITY'].iloc[0], parcel['FIPS'].iloc[0]))
L('  vertices=%d  interior rings=%d' % (nvert, len(poly.interiors)))
L('  centroid %.7f, %.7f' % (cen.x, cen.y))
L('  area EPSG:5070 = %.2f m2 = %.4f acres' % (PA, PA / AC))
L('  bbox %s' % [round(v, 7) for v in poly.bounds])
L('  last updated %s' % pd.to_datetime(parcel['LASTUPDATE'].iloc[0], unit='ms').strftime('%Y-%m-%d'))
parcel.to_file(G, layer='parcel', driver='GPKG')

# ---------------- 2. county ----------------
rings = [list(poly.exterior.coords)] + [list(i.coords) for i in poly.interiors]
esri_poly = {"rings": [[[round(x, 8), round(y, 8)] for x, y in r] for r in rings],
             "spatialReference": {"wkid": 4326}}
GEOM = {'geometry': json.dumps(esri_poly), 'geometryType': 'esriGeometryPolygon', 'inSR': 4326,
        'outSR': 4326, 'spatialRel': 'esriSpatialRelIntersects', 'returnGeometry': 'true', 'f': 'geojson'}
j = post('https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/State_County/MapServer/1/query',
         dict(GEOM, outFields='GEOID,NAME,STATE,COUNTY'), tag='TIGERweb county')
co = gpd.GeoDataFrame.from_features(j['features'], crs='EPSG:4326')
co5 = co.to_crs(5070)
L('COUNTY:')
counties = []
for i, r in co5.iterrows():
    a = r.geometry.intersection(pg5).area
    counties.append({'GEOID': r['GEOID'], 'NAME': r['NAME'], 'pct': 100 * a / PA, 'm2': a})
    L('  GEOID %s  %-24s %10.1f m2  %6.2f%%' % (r['GEOID'], r['NAME'], a, 100 * a / PA))
co.to_file(G, layer='county', driver='GPKG')

# ---------------- 3. FEMA NFHL ----------------
NF = 'https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/%d/query'
L('FEMA NFHL:')
j = post(NF % 28, dict(GEOM, outFields='DFIRM_ID,FLD_ZONE,ZONE_SUBTY,SFHA_TF,STATIC_BFE'), tag='L28 S_FLD_HAZ_AR')
rows = []
if j and j.get('features'):
    z = gpd.GeoDataFrame.from_features(j['features'], crs='EPSG:4326')
    z.to_file(G, layer='flood_zones_raw', driver='GPKG')
    z5 = z.to_crs(5070)
    z5['geometry'] = z5.geometry.intersection(pg5)
    z5 = z5[~z5.geometry.is_empty].copy()
    z5['acres'] = z5.area / AC; z5['pct'] = 100 * z5.area / PA
    L('  clipped features: %d' % len(z5))
    for _, r in z5.iterrows():
        L('   %-6s %-34s SFHA=%s BFE=%s  %8.4f ac  %6.2f%%'
          % (r['FLD_ZONE'], str(r['ZONE_SUBTY'])[:34], r['SFHA_TF'], r['STATIC_BFE'], r['acres'], r['pct']))
    agg = z5.groupby(['FLD_ZONE', 'ZONE_SUBTY', 'SFHA_TF'], dropna=False).agg(
        acres=('acres', 'sum'), pct=('pct', 'sum')).reset_index()
    L('  --- per zone ---')
    for _, r in agg.iterrows():
        L('   %-6s %-34s SFHA=%s  %8.4f ac  %6.2f%%' % (r['FLD_ZONE'], str(r['ZONE_SUBTY'])[:34], r['SFHA_TF'], r['acres'], r['pct']))
    sfha = z5[z5['SFHA_TF'] == 'T']['acres'].sum()
    L('  TOTAL SFHA: %.4f ac (%.2f%% of parcel)' % (sfha, 100 * sfha / (PA / AC)))
    L('  mapped total: %.4f ac (%.2f%%)' % (z5['acres'].sum(), 100 * z5.area.sum() / PA))
    z5.to_crs(4326).to_file(G, layer='flood_zones_clipped', driver='GPKG')
    agg.to_csv(OUT + '/site2_zone_summary.csv', index=False)
    rows = agg.to_dict('records')

j = post(NF % 3, dict(GEOM, outFields='DFIRM_ID,FIRM_PAN,EFF_DATE,PANEL,SUFFIX,ST_FIPS'), tag='L3 S_FIRM_PAN')
panels = []
if j and j.get('features'):
    pan = gpd.GeoDataFrame.from_features(j['features'], crs='EPSG:4326')
    pan['EFF_ISO'] = pd.to_datetime(pan['EFF_DATE'], unit='ms', errors='coerce').dt.strftime('%Y-%m-%d')
    cofips = counties[0]['GEOID']
    L('  panels intersecting: %d' % len(pan))
    for _, r in pan.iterrows():
        L('   DFIRM %-7s %-13s eff %s' % (r['DFIRM_ID'], r['FIRM_PAN'], r['EFF_ISO']))
    keep = pan[pan['DFIRM_ID'].astype(str).str.startswith(cofips)]
    L('  kept (DFIRM matches county %s): %d' % (cofips, len(keep)))
    use = keep if len(keep) else pan
    use.to_file(G, layer='firm_panels', driver='GPKG')
    panels = use.drop(columns='geometry').astype(str).to_dict('records')

j = post(NF % 22, dict(GEOM, outFields='DFIRM_ID,POL_NAME1,POL_NAME2,CID,COMM_NO,ANI_TF'), tag='L22 S_POL_AR')
ani_gdf = None
if j and j.get('features'):
    pol = gpd.GeoDataFrame.from_features(j['features'], crs='EPSG:4326')
    pol5 = pol.to_crs(5070)
    pol['pct_of_parcel'] = [100 * g.intersection(pg5).area / PA for g in pol5.geometry]
    L('  political areas:')
    for _, r in pol.iterrows():
        L('   %-38s CID %-7s ANI=%s  %6.2f%%' % (str(r['POL_NAME1'])[:38], r['CID'], r['ANI_TF'], r['pct_of_parcel']))
    pol.to_file(G, layer='political_areas', driver='GPKG')
    a = pol5[pol['ANI_TF'].values == 'T']
    if len(a):
        gm = a.geometry.union_all().intersection(pg5)
        if not gm.is_empty:
            ani_gdf = gpd.GeoDataFrame({'FLD_ZONE': ['AREA NOT INCLUDED'], 'ZONE_SUBTY': ['AREA NOT INCLUDED'],
                                        'SFHA_TF': ['F'], 'SOURCE': ['S_POL_AR ANI_TF=T']},
                                       geometry=[gm], crs='EPSG:5070')
            ani_gdf.to_crs(4326).to_file(G, layer='area_not_included', driver='GPKG')
            L('  ANI derived: %.4f ac (%.2f%%)' % (gm.area / AC, 100 * gm.area / PA))
    else:
        L('  no ANI area on this parcel')

j = post(NF % 0, dict(GEOM, outFields='STUDY_ID'), tag='L0 NFHL Availability')
if j and j.get('features'):
    av = gpd.GeoDataFrame.from_features(j['features'], crs='EPSG:4326').to_crs(5070)
    cov = av.geometry.union_all().intersection(pg5).area
    L('  NFHL study coverage of parcel: %.2f%% (studies %s)' % (100 * cov / PA, list(av['STUDY_ID'])))

json.dump({'query_date': QDATE, 'geocode': [LON, LAT], 'parcel_id': str(parcel['PARCELID'].iloc[0]),
           'vgin_qpid': str(parcel['VGIN_QPID'].iloc[0]), 'locality': parcel['LOCALITY'].iloc[0],
           'vertices': nvert, 'centroid': [cen.x, cen.y], 'acres': PA / AC, 'area_m2': PA,
           'bounds': list(poly.bounds), 'counties': counties, 'zones': rows, 'panels': panels},
          open(OUT + '/site2_values.json', 'w'), indent=2, default=str)
open(OUT + '/site2_data_log.txt', 'w', encoding='utf-8').write('\n'.join(log))
L('DATA STEPS DONE %.1fs' % (time.time() - T0))
