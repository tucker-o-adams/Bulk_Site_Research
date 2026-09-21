import json, time, requests, geopandas as gpd
parcel=gpd.read_file('out/site1_fema.gpkg',layer='parcel')
poly=parcel.geometry.iloc[0]
esri_poly={"rings":[[[round(x,8),round(y,8)] for x,y in list(poly.exterior.coords)]],"spatialReference":{"wkid":4326}}
S=requests.Session(); S.headers.update({'User-Agent':'Mozilla/5.0'})
BASE='https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/%d/query'
def post(layer,extra,tries=4):
    p={'f':'json','geometry':json.dumps(esri_poly),'geometryType':'esriGeometryPolygon',
       'inSR':4326,'outSR':4326,'spatialRel':'esriSpatialRelIntersects'}
    p.update(extra)
    for i in range(tries):
        try:
            r=S.post(BASE%layer,data=p,timeout=180)
            return r
        except Exception as e:
            print('   attempt %d failed: %s: %s'%(i+1,type(e).__name__,str(e)[:120])); time.sleep(3)
    return None
# 1. count of flood hazard features
r=post(28,{'returnCountOnly':'true'}); print('L28 count:',r.text[:200] if r else 'FAILED')
r=post(28,{'outFields':'DFIRM_ID,FLD_ZONE,ZONE_SUBTY,SFHA_TF,STATIC_BFE','returnGeometry':'false'})
print('L28 attrs:',r.text[:600] if r else 'FAILED')
# maxRecordCount
d=S.get('https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28',params={'f':'json'},timeout=60).json()
print('L28 maxRecordCount:',d.get('maxRecordCount'),'name',d.get('name'))
d22=S.get('https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/22',params={'f':'json'},timeout=60).json()
print('L22 name:',d22.get('name'),'fields:',[f['name'] for f in d22['fields']])
d3=S.get('https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/3',params={'f':'json'},timeout=60).json()
print('L3 name:',d3.get('name'))
d31=S.get('https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/31',params={'f':'json'},timeout=60).json()
print('L31 name:',d31.get('name'))
# layer 27 flood hazard boundaries / layer 0 availability
r=post(0,{'outFields':'*','returnGeometry':'false'}); print('L0 NFHL Availability:',r.text[:800] if r else 'FAILED')
