import json,time,requests,geopandas as gpd,os
t0=time.time()
S=requests.Session(); S.headers.update({'User-Agent':'Mozilla/5.0'})
BASE='https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPImagery/ImageServer'
info=S.get(BASE,params={'f':'json'},timeout=60).json()
print('service:',info.get('name'),'| maxImageHeight',info.get('maxImageHeight'),'maxImageWidth',info.get('maxImageWidth'))
print('pixelSizeX',info.get('pixelSizeX'),'| bands',info.get('bandCount'),'| SR',info.get('spatialReference',{}).get('latestWkid'))
print('formats:',info.get('supportedImageFormatTypes'))

parcel=gpd.read_file('out/site1_fema.gpkg',layer='parcel')
# buffer 0.5 mi in a projected CRS (UTM 13N) then take bbox
utm=parcel.to_crs(32613)
buf=utm.buffer(0.5*1609.344)
minx,miny,maxx,maxy=buf.total_bounds
# pad to 16:9
w=maxx-minx; h=maxy-miny
target=16/9
if w/h<target:
    nw=h*target; cx=(minx+maxx)/2; minx,maxx=cx-nw/2,cx+nw/2
else:
    nh=w/target; cy=(miny+maxy)/2; miny,maxy=cy-nh/2,cy+nh/2
w=maxx-minx; h=maxy-miny
LONG=2400
px=LONG; py=int(round(LONG*h/w))
print('\nextent UTM13N: %.1f %.1f %.1f %.1f  (%.0f x %.0f m)'%(minx,miny,maxx,maxy,w,h))
print('requested size: %d x %d px -> %.3f m/px'%(px,py,w/px))
params={'bbox':'%f,%f,%f,%f'%(minx,miny,maxx,maxy),'bboxSR':32613,'imageSR':32613,
        'size':'%d,%d'%(px,py),'format':'tiff','f':'image','adjustAspectRatio':'false'}
url=BASE+'/exportImage'
r=S.get(url,params=params,timeout=300)
print('\nexportImage HTTP',r.status_code,'content-type',r.headers.get('Content-Type'),'bytes',len(r.content))
print('REQUEST URL:',r.url)
if r.status_code==200 and 'image' in (r.headers.get('Content-Type') or ''):
    open('out/naip_site1.tif','wb').write(r.content)
    import rasterio
    with rasterio.open('out/naip_site1.tif') as ds:
        print('raster: %dx%d bands=%d dtype=%s crs=%s'%(ds.width,ds.height,ds.count,ds.dtypes[0],ds.crs))
        print('transform res: %.4f m/px'%ds.transform.a); print('bounds:',ds.bounds)
else:
    print('BODY:',r.text[:500])
# metadata JSON version for extent confirmation
rj=S.get(url,params={**params,'f':'json'},timeout=120).json()
print('\nf=json response keys:',list(rj.keys()))
print(json.dumps({k:v for k,v in rj.items() if k!='href'},indent=1)[:600])
json.dump({'request_url':r.url,'extent_utm13n':[minx,miny,maxx,maxy],'size_px':[px,py],
           'res_m':w/px,'export_json':rj},open('out/step3.json','w'),indent=2,default=str)

# imagery date: query the mosaic footprint at the centroid
cen=parcel.to_crs(4326).geometry.iloc[0].centroid
qr=S.get(BASE+'/query',params={'f':'json','geometry':'%f,%f'%(cen.x,cen.y),'geometryType':'esriGeometryPoint',
    'inSR':4326,'spatialRel':'esriSpatialRelIntersects','outFields':'*','returnGeometry':'false','resultRecordCount':5},timeout=120)
print('\nmosaic query HTTP',qr.status_code)
try:
    j=qr.json()
    for f in j.get('features',[])[:5]: print(' ',json.dumps(f['attributes'])[:600])
except Exception as e: print('  ',e,qr.text[:300])
print('elapsed %.1fs'%(time.time()-t0))
