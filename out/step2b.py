import json, time, requests, geopandas as gpd, pandas as pd
from shapely.geometry import mapping
t0=time.time(); AC=4046.8564224
parcel=gpd.read_file('out/site1_fema.gpkg',layer='parcel'); poly=parcel.geometry.iloc[0]
p5=parcel.to_crs(5070); PA=p5.area.iloc[0]
esri_poly={"rings":[[[round(x,8),round(y,8)] for x,y in list(poly.exterior.coords)]],"spatialReference":{"wkid":4326}}
S=requests.Session(); S.headers.update({'User-Agent':'Mozilla/5.0'})
BASE='https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/%d/query'
log=[]
def q(layer,outFields,tries=5):
    p={'f':'geojson','geometry':json.dumps(esri_poly),'geometryType':'esriGeometryPolygon',
       'inSR':4326,'outSR':4326,'spatialRel':'esriSpatialRelIntersects',
       'outFields':outFields,'returnGeometry':'true'}
    for i in range(tries):
        try:
            r=S.post(BASE%layer,data=p,timeout=180)
            j=r.json()
            if 'error' in j: log.append('layer %d attempt %d ERROR %s'%(layer,i+1,json.dumps(j['error'])[:200])); time.sleep(3); continue
            log.append('layer %d HTTP %d OK on attempt %d (%d features)'%(layer,r.status_code,i+1,len(j.get('features',[]))))
            return j
        except Exception as e:
            log.append('layer %d attempt %d %s: %s'%(layer,i+1,type(e).__name__,str(e)[:140])); time.sleep(4)
    return None

# --- Political jurisdictions (layer 22 = S_POL_AR; layer 31 is Subbasins, NOT political) ---
print('--- Layer 22 S_POL_AR ---')
j=q(22,'DFIRM_ID,POL_NAME1,POL_NAME2,POL_NAME3,CID,COMM_NO,CO_FIPS,ST_FIPS,ANI_TF')
pol=None
if j and j.get('features'):
    pol=gpd.GeoDataFrame.from_features(j['features'],crs='EPSG:4326')
    p5g=p5.geometry.iloc[0]
    pol5=pol.to_crs(5070)
    pol['pct_of_parcel']=[100*g.intersection(p5g).area/PA for g in pol5.geometry]
    print(pol.drop(columns='geometry').to_string())
    pol.to_file('out/site1_fema.gpkg',layer='political_areas',driver='GPKG')
else: print('  FAILED/none')

# --- NFHL availability (layer 0) coverage of parcel ---
print('\n--- Layer 0 NFHL Availability ---')
j0=q(0,'STUDY_ID')
if j0 and j0.get('features'):
    av=gpd.GeoDataFrame.from_features(j0['features'],crs='EPSG:4326').to_crs(5070)
    for i,row in av.iterrows():
        print('  STUDY_ID %s covers %.2f%% of parcel'%(row['STUDY_ID'],100*row.geometry.intersection(p5.geometry.iloc[0]).area/PA))
    cov=av.geometry.union_all().intersection(p5.geometry.iloc[0]).area
    print('  union NFHL availability coverage of parcel: %.2f%%'%(100*cov/PA))

# --- Layer 27 Flood Hazard Boundaries (context) ---
print('\n--- Layer 27 Flood Hazard Boundaries (count) ---')
j27=q(27,'DFIRM_ID,LINE_TYP')
print('  features:',len(j27.get('features',[])) if j27 else 'FAILED')

open('out/step2b_log.txt','w').write('\n'.join(log))
print('\n'.join(log))
print('elapsed %.1fs'%(time.time()-t0))
