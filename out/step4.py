import json,time,requests,geopandas as gpd,pandas as pd
from shapely.geometry import box
t0=time.time()
S=requests.Session(); S.headers.update({'User-Agent':'Mozilla/5.0'})
ext=json.load(open('out/step3.json'))['extent_utm13n']
bb=gpd.GeoSeries([box(*ext)],crs=32613).to_crs(4326).total_bounds
print('bbox 4326:',[round(v,6) for v in bb])
env={"xmin":bb[0],"ymin":bb[1],"xmax":bb[2],"ymax":bb[3],"spatialReference":{"wkid":4326}}
log=[]
def q(svc,layer,fields,name):
    url='https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/%s/MapServer/%d/query'%(svc,layer)
    p={'f':'geojson','geometry':json.dumps(env),'geometryType':'esriGeometryEnvelope','inSR':4326,'outSR':4326,
       'spatialRel':'esriSpatialRelIntersects','outFields':fields,'returnGeometry':'true'}
    for i in range(4):
        try:
            r=S.post(url,data=p,timeout=180); j=r.json()
            if 'error' in j: log.append('%s L%d ERROR %s'%(name,layer,json.dumps(j['error'])[:160])); time.sleep(3); continue
            n=len(j.get('features',[])); log.append('%s L%d HTTP %d -> %d features'%(name,layer,r.status_code,n))
            print(log[-1])
            return gpd.GeoDataFrame.from_features(j['features'],crs='EPSG:4326') if n else None
        except Exception as e:
            log.append('%s L%d attempt %d %s: %s'%(name,layer,i+1,type(e).__name__,str(e)[:120])); time.sleep(4)
    print(log[-1]); return None

# check field names
for svc,lyr in [('Transportation',2),('Transportation',8),('Transportation',9),('Hydro',0),('Hydro',1)]:
    d=S.get('https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/%s/MapServer/%d'%(svc,lyr),params={'f':'json'},timeout=60).json()
    print(svc,lyr,d.get('name'),'|',[f['name'] for f in d['fields']][:12])

parts={}
parts['roads_primary']=q('Transportation',2,'NAME,MTFCC,BASENAME','PrimaryRoads')
parts['roads_secondary']=q('Transportation',6,'NAME,MTFCC,BASENAME','SecondaryRoads')
parts['roads_local']=q('Transportation',8,'NAME,MTFCC,BASENAME','LocalRoads')
parts['railroads']=q('Transportation',9,'NAME,MTFCC','Railroads')
parts['hydro_linear']=q('Hydro',0,'NAME,MTFCC','LinearHydro')
parts['hydro_areal']=q('Hydro',1,'NAME,MTFCC','ArealHydro')
for k,v in parts.items():
    if v is not None and len(v):
        v.to_file('out/site1_fema.gpkg',layer=k,driver='GPKG')
        nm=sorted(set(x for x in v.get('NAME',pd.Series(dtype=str)).dropna() if x))
        print('%-16s %4d features | %d named: %s'%(k,len(v),len(nm),', '.join(nm[:12])))
    else: print('%-16s none'%k)
open('out/step4_log.txt','w').write('\n'.join(log))
print('layers now:',gpd.list_layers('out/site1_fema.gpkg')['name'].tolist())
print('elapsed %.1fs'%(time.time()-t0))
