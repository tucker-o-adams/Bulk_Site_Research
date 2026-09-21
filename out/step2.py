import json, time, requests, geopandas as gpd, pandas as pd
t0=time.time()
QDATE='2026-08-26'
parcel=gpd.read_file('out/site1_fema.gpkg',layer='parcel')
poly=parcel.geometry.iloc[0]
rings=[list(poly.exterior.coords)]+[list(i.coords) for i in poly.interiors]
esri_poly={"rings":[[[round(x,8),round(y,8)] for x,y in r] for r in rings],"spatialReference":{"wkid":4326}}
p5=parcel.to_crs(5070); PA=p5.area.iloc[0]; AC=4046.8564224
print('parcel: %.2f m2 = %.3f ac'%(PA,PA/AC))

BASE='https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/%d/query'
def q(layer,outFields):
    params={'f':'geojson','geometry':json.dumps(esri_poly),'geometryType':'esriGeometryPolygon',
            'inSR':4326,'outSR':4326,'spatialRel':'esriSpatialRelIntersects',
            'outFields':outFields,'returnGeometry':'true'}
    r=requests.post(BASE%layer,data=params,timeout=180)
    print('  layer %d HTTP %s bytes %d'%(layer,r.status_code,len(r.content)))
    try: j=r.json()
    except Exception as e: print('  PARSE FAIL',e,r.text[:300]); return None
    if isinstance(j,dict) and 'error' in j: print('  ERROR:',json.dumps(j['error'])[:500]); return None
    return j

out={}
print('\n--- Layer 28 S_FLD_HAZ_AR ---')
j=q(28,'DFIRM_ID,FLD_ZONE,ZONE_SUBTY,SFHA_TF,STATIC_BFE')
if j and j.get('features'):
    z=gpd.GeoDataFrame.from_features(j['features'],crs='EPSG:4326')
    print('  features:',len(z))
    z5=z.to_crs(5070)
    z5['geometry']=z5.geometry.intersection(p5.geometry.iloc[0])
    z5=z5[~z5.geometry.is_empty]
    z5['acres']=z5.area/AC
    z5['pct']=100*z5.area/PA
    print(z5[['DFIRM_ID','FLD_ZONE','ZONE_SUBTY','SFHA_TF','STATIC_BFE','acres','pct']].to_string())
    agg=z5.groupby(['FLD_ZONE','ZONE_SUBTY','SFHA_TF'],dropna=False).agg(acres=('acres','sum'),pct=('pct','sum')).reset_index()
    print('\n  === PER-ZONE WITHIN PARCEL ===')
    print(agg.to_string())
    sfha=z5[z5['SFHA_TF']=='T']['acres'].sum()
    print('\n  TOTAL SFHA acres within parcel: %.4f (%.2f%%)'%(sfha,100*sfha/(PA/AC)))
    print('  TOTAL mapped acres within parcel: %.4f'%z5['acres'].sum())
    z5.to_crs(4326).to_file('out/site1_fema.gpkg',layer='flood_zones_clipped',driver='GPKG')
    z.to_file('out/site1_fema.gpkg',layer='flood_zones_raw',driver='GPKG')
    agg.to_csv('out/step2_zones.csv',index=False)
    out['zones']=agg.to_dict('records'); out['sfha_acres']=float(sfha)
else:
    print('  NO FEATURES / FAILED')

print('\n--- Layer 3 S_FIRM_PAN ---')
j=q(3,'DFIRM_ID,FIRM_PAN,EFF_DATE,PANEL,SUFFIX,ST_FIPS')
if j and j.get('features'):
    pn=gpd.GeoDataFrame.from_features(j['features'],crs='EPSG:4326')
    if 'EFF_DATE' in pn:
        pn['EFF_DATE_ISO']=pd.to_datetime(pn['EFF_DATE'],unit='ms',errors='coerce').dt.strftime('%Y-%m-%d')
    print(pn.drop(columns='geometry').to_string())
    keep=pn[pn['DFIRM_ID'].astype(str).str.startswith('08001')]
    print('\n  panels matching county 08001:',len(keep))
    print(keep.drop(columns="geometry").to_string() if len(keep) else '  (none)')
    (keep if len(keep) else pn).to_file('out/site1_fema.gpkg',layer='firm_panels',driver='GPKG')
    out['panels']=(keep if len(keep) else pn).drop(columns='geometry').astype(str).to_dict('records')
else: print('  NO FEATURES / FAILED')

print('\n--- Layer 22 S_POL_AR (Political Jurisdictions) ---')
j=q(22,'DFIRM_ID,POL_NAME1,POL_NAME2,POL_NAME3,CID,COMM_NO')
if j and j.get('features'):
    po=gpd.GeoDataFrame.from_features(j['features'],crs='EPSG:4326')
    print(po.drop(columns='geometry').to_string())
    po.to_file('out/site1_fema.gpkg',layer='political_areas',driver='GPKG')
    out['pol']=po.drop(columns='geometry').astype(str).to_dict('records')
else: print('  NO FEATURES / FAILED')

out['query_date']=QDATE
json.dump(out,open('out/step2.json','w'),indent=2,default=str)
print('\nelapsed %.1fs'%(time.time()-t0))
