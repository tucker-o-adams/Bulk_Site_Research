import json, time, requests, geopandas as gpd
from shapely.geometry import shape, mapping
from shapely.ops import unary_union
t0=time.time()
parcel=gpd.read_file('out/site1_fema.gpkg',layer='parcel')
poly=parcel.geometry.iloc[0]
rings=[list(poly.exterior.coords)]+[list(i.coords) for i in poly.interiors]
esri_poly={"rings":[[[round(x,8),round(y,8)] for x,y in r] for r in rings],
           "spatialReference":{"wkid":4326}}
URL='https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/State_County/MapServer/1/query'
params={'f':'geojson','geometry':json.dumps(esri_poly),'geometryType':'esriGeometryPolygon',
        'inSR':4326,'outSR':4326,'spatialRel':'esriSpatialRelIntersects',
        'outFields':'GEOID,NAME,BASENAME,STATE,COUNTY','returnGeometry':'true'}
r=requests.post(URL,data=params,timeout=120)
print('HTTP',r.status_code,'len',len(r.content))
j=r.json()
if 'error' in j: print('ERROR',j); raise SystemExit(1)
feats=j['features']; print('features:',len(feats))
g=gpd.GeoDataFrame.from_features(feats,crs='EPSG:4326')
p5=parcel.to_crs(5070); total=p5.area.iloc[0]
g5=g.to_crs(5070)
rows=[]
for i,row in g5.iterrows():
    inter=row.geometry.intersection(p5.geometry.iloc[0]).area
    rows.append((row['GEOID'],row['NAME'],row['STATE'],row['COUNTY'],inter,100*inter/total))
print('\n=== COUNTY INTERSECTION (TIGERweb Counties, layer 1, 2025 vintage) ===')
print('parcel area 5070 m2: %.2f'%total)
for gid,nm,st,co,a,pc in sorted(rows,key=lambda r:-r[4]):
    print('GEOID %s  %-20s STATE=%s COUNTY=%s  %10.1f m2  %6.2f%%'%(gid,nm,st,co,a,pc))
json.dump([{'GEOID':r[0],'NAME':r[1],'STATE':r[2],'COUNTY':r[3],'inter_m2':r[4],'pct':r[5]} for r in rows],
          open('out/step1_county.json','w'),indent=2)
g.to_file('out/site1_fema.gpkg',layer='county',driver='GPKG')
print('elapsed %.1fs'%(time.time()-t0))
