import json,time,requests,geopandas as gpd,numpy as np,rasterio,os
from rasterio.transform import from_bounds
t0=time.time()
S=requests.Session(); S.headers.update({'User-Agent':'Mozilla/5.0'})
BASE='https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPImagery/ImageServer'
ext=json.load(open('out/step3.json'))['extent_utm13n']
minx,miny,maxx,maxy=ext
W=maxx-minx; H=maxy-miny
NX,NY=2,2; TILE=3200
px_w,px_h=NX*TILE,int(round(NY*TILE*H/W))
tile_h=px_h//NY
print('mosaic target %d x %d px -> %.3f m/px'%(px_w,px_h,W/px_w))
mos=np.zeros((3,px_h,px_w),dtype='uint8'); urls=[]
for iy in range(NY):
    for ix in range(NX):
        x0=minx+W*ix/NX; x1=minx+W*(ix+1)/NX
        y1=maxy-H*iy/NY; y0=maxy-H*(iy+1)/NY
        p={'bbox':'%f,%f,%f,%f'%(x0,y0,x1,y1),'bboxSR':32613,'imageSR':32613,
           'size':'%d,%d'%(TILE,tile_h),'format':'tiff','f':'image','adjustAspectRatio':'false'}
        ok=False
        for att in range(3):
            try:
                r=S.get(BASE+'/exportImage',params=p,timeout=300)
                if r.status_code==200 and 'image' in (r.headers.get('Content-Type') or ''):
                    tmp='out/_t%d%d.tif'%(iy,ix); open(tmp,'wb').write(r.content)
                    with rasterio.open(tmp) as ds:
                        a=ds.read([1,2,3])
                    mos[:, iy*tile_h:(iy+1)*tile_h, ix*TILE:(ix+1)*TILE]=a[:,:tile_h,:TILE]
                    os.remove(tmp); urls.append(r.url); ok=True
                    print('  tile %d,%d OK %d bytes'%(iy,ix,len(r.content))); break
                else:
                    print('  tile %d,%d attempt %d HTTP %s %s'%(iy,ix,att+1,r.status_code,r.text[:120]))
            except Exception as e:
                print('  tile %d,%d attempt %d %s: %s'%(iy,ix,att+1,type(e).__name__,str(e)[:120]))
            time.sleep(3)
        if not ok: print('  TILE %d,%d FAILED'%(iy,ix))
tr=from_bounds(minx,miny,maxx,maxy,px_w,px_h)
with rasterio.open('out/naip_site1.tif','w',driver='GTiff',height=px_h,width=px_w,count=3,
                   dtype='uint8',crs='EPSG:32613',transform=tr,compress='deflate',photometric='rgb') as ds:
    ds.write(mos)
print('wrote out/naip_site1.tif  %.1f MB'%(os.path.getsize('out/naip_site1.tif')/1e6))

# imagery date: query actual NAIP scene footprints (Category=1 = primary rasters)
print('\n--- mosaic dataset scene query (Category=1) ---')
cen=gpd.read_file('out/site1_fema.gpkg',layer='parcel').geometry.iloc[0].centroid
qr=S.get(BASE+'/query',params={'f':'json','geometry':'%f,%f'%(cen.x,cen.y),'geometryType':'esriGeometryPoint',
  'inSR':4326,'spatialRel':'esriSpatialRelIntersects','where':'Category=1','outFields':'Name,State,Year,acquisition_date,resolution_value,resolution_units,vendor,agency,projection_zone',
  'returnGeometry':'false'},timeout=180)
print('HTTP',qr.status_code)
j=qr.json(); feats=j.get('features',[])
print('scenes:',len(feats))
dates=[]
for f in feats:
    a=f['attributes']
    ad=a.get('acquisition_date')
    if ad:
        import datetime
        ad=datetime.datetime.utcfromtimestamp(ad/1000).strftime('%Y-%m-%d')
    dates.append((a.get('Name'),a.get('Year'),ad,a.get('resolution_value'),a.get('resolution_units'),a.get('vendor')))
    print('  ',dates[-1])
json.dump({'mosaic_urls':urls,'size_px':[px_w,px_h],'res_m':W/px_w,'extent_utm13n':ext,
           'scenes':dates},open('out/step3b.json','w'),indent=2,default=str)
print('elapsed %.1fs'%(time.time()-t0))
