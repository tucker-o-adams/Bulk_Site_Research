import zipfile, io, json, time, sys
from xml.etree import ElementTree as ET
from shapely.geometry import Polygon, Point, mapping
import geopandas as gpd

t0=time.time()
KMZ=r"E:\Claude\Projects\TBDI Modeling\Example kmz\TBDI Example Site 1.kmz"
z=zipfile.ZipFile(KMZ)
print("KMZ members:", z.namelist())
kmlname=[n for n in z.namelist() if n.lower().endswith('.kml')][0]
kml=z.read(kmlname).decode('utf-8')
print("--- KML (first 1500) ---"); print(kml[:1500])
open('out/site1.kml','w',encoding='utf-8').write(kml)

ns={'k':'http://www.opengis.net/kml/2.2'}
root=ET.fromstring(kml)
polys=[]; pts=[]
for pm in root.iter():
    tag=pm.tag.split('}')[-1]
    if tag=='Placemark':
        name=None
        for c in pm:
            if c.tag.split('}')[-1]=='name': name=(c.text or '').strip()
        for el in pm.iter():
            t=el.tag.split('}')[-1]
            if t=='Polygon':
                # outer boundary
                outer=None; inners=[]
                for sub in el.iter():
                    st=sub.tag.split('}')[-1]
                    if st=='coordinates':
                        coords=[tuple(float(v) for v in c.split(',')[:2]) for c in sub.text.split()]
                        if outer is None: outer=coords
                        else: inners.append(coords)
                polys.append((name,Polygon(outer,inners)))
            if t=='Point':
                for sub in el.iter():
                    if sub.tag.split('}')[-1]=='coordinates':
                        c=[float(v) for v in sub.text.strip().split(',')[:2]]
                        pts.append((name,Point(c[0],c[1])))
print("\npolygons:",[(n,len(p.exterior.coords)) for n,p in polys])
print("points:",[(n,(p.x,p.y)) for n,p in pts])

name,poly=polys[0]
gdf=gpd.GeoDataFrame({'name':[name]},geometry=[poly],crs='EPSG:4326')
a5070=gdf.to_crs(5070)
acres=a5070.area.iloc[0]/4046.8564224
cen=poly.centroid
print("\n=== STEP 1 VALUES ===")
print("placemark name :",name)
print("vertex count (exterior ring incl. closing dup):",len(poly.exterior.coords))
print("unique vertices:",len(poly.exterior.coords)-1)
print("interior rings :",len(poly.interiors))
print("centroid lon/lat: %.7f, %.7f"%(cen.x,cen.y))
print("area EPSG:5070 m2: %.2f"%a5070.area.iloc[0])
print("area acres      : %.4f"%acres)
print("bbox lon/lat    :",[round(v,7) for v in poly.bounds])
json.dump({'name':name,'vertices':len(poly.exterior.coords)-1,'centroid':[cen.x,cen.y],
           'acres_5070':acres,'area_m2_5070':float(a5070.area.iloc[0]),'bounds':list(poly.bounds),
           'point_placemarks':[[n,p.x,p.y] for n,p in pts]},open('out/step1.json','w'),indent=2)
gdf.to_file('out/site1_fema.gpkg',layer='parcel',driver='GPKG')
print("elapsed %.1fs"%(time.time()-t0))
