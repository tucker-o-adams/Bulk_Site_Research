import json, time, requests, geopandas as gpd, pandas as pd, simplekml, zipfile, os
t0=time.time(); AC=4046.8564224
parcel=gpd.read_file('out/site1_fema.gpkg',layer='parcel'); p5=parcel.to_crs(5070)
PA=p5.area.iloc[0]; pg5=p5.geometry.iloc[0]
zones=gpd.read_file('out/site1_fema.gpkg',layer='flood_zones_clipped')
pol=gpd.read_file('out/site1_fema.gpkg',layer='political_areas')
pan=gpd.read_file('out/site1_fema.gpkg',layer='firm_panels')

# Derive Area Not Included polygon: parcel portion inside FEMA S_POL_AR where ANI_TF='T'
ani=pol[pol['ANI_TF']=='T'].to_crs(5070)
ani_geom=ani.geometry.union_all().intersection(pg5)
ani_gdf=gpd.GeoDataFrame({'FLD_ZONE':['AREA NOT INCLUDED'],'ZONE_SUBTY':['AREA NOT INCLUDED'],
                          'SFHA_TF':['F'],'DFIRM_ID':[ani['DFIRM_ID'].iloc[0]],
                          'SOURCE':['S_POL_AR ANI_TF=T ('+ani['POL_NAME1'].iloc[0]+')']},
                         geometry=[ani_geom],crs='EPSG:5070')
ani_gdf.to_crs(4326).to_file('out/site1_fema.gpkg',layer='area_not_included',driver='GPKG')

rows=[]
z5=zones.to_crs(5070)
for _,r in z5.iterrows():
    rows.append(dict(category=r['FLD_ZONE'],subtype=r['ZONE_SUBTY'],sfha=r['SFHA_TF'],
                     static_bfe=r['STATIC_BFE'],dfirm=r['DFIRM_ID'],
                     acres=r.geometry.area/AC,pct=100*r.geometry.area/PA))
rows.append(dict(category='AREA NOT INCLUDED',subtype='AREA NOT INCLUDED (Rocky Mountain Arsenal)',
                 sfha='F',static_bfe=None,dfirm=ani['DFIRM_ID'].iloc[0],
                 acres=ani_geom.area/AC,pct=100*ani_geom.area/PA))
df=pd.DataFrame(rows)
print('PARCEL: %.3f acres (EPSG:5070)'%(PA/AC))
print(df.to_string(index=False))
sfha_ac=df[df['sfha']=='T']['acres'].sum()
print('\nTOTAL SFHA acres: %.4f  (%.2f%% of parcel)'%(sfha_ac,100*sfha_ac/(PA/AC)))
print('accounted: %.3f ac (%.2f%%)'%(df['acres'].sum(),df['pct'].sum()))
df.to_csv('out/step2_zone_summary.csv',index=False)

# ---- KMZ export ----
kml=simplekml.Kml(name='TBDI Example Site 1 - FEMA Flood')
def add(gdf,folder,fill,line,namecol=None):
    f=kml.newfolder(name=folder)
    for _,r in gdf.to_crs(4326).iterrows():
        geoms=[r.geometry] if r.geometry.geom_type=='Polygon' else list(r.geometry.geoms)
        for g in geoms:
            if g.is_empty: continue
            pg=f.newpolygon(name=str(r[namecol]) if namecol else folder)
            pg.outerboundaryis=[(x,y) for x,y in g.exterior.coords]
            pg.innerboundaryis=[[(x,y) for x,y in i.coords] for i in g.interiors]
            pg.style.polystyle.color=fill; pg.style.linestyle.color=line; pg.style.linestyle.width=2
add(z5,'Flood Zones (clipped to parcel)','7fFF9900','ffFF9900','FLD_ZONE')
add(ani_gdf,'Area Not Included','7f808080','ff808080','FLD_ZONE')
add(pan,'FIRM Panels','00ffffff','ff00ffff','FIRM_PAN')
pf=kml.newfolder(name='Parcel')
pp=pf.newpolygon(name='TBDI Example Site 1 (596.33 ac)')
pp.outerboundaryis=[(x,y) for x,y in parcel.geometry.iloc[0].exterior.coords]
pp.style.polystyle.fill=0; pp.style.linestyle.color='ff0000aa'; pp.style.linestyle.width=4
kml.save('out/_site1.kml')
with zipfile.ZipFile('out/site1_fema.kmz','w',zipfile.ZIP_DEFLATED) as z:
    z.write('out/_site1.kml','doc.kml')
os.remove('out/_site1.kml')
print('\ngpkg layers:',gpd.list_layers('out/site1_fema.gpkg')['name'].tolist())
print('kmz bytes:',os.path.getsize('out/site1_fema.kmz'))
print('elapsed %.1fs'%(time.time()-t0))
