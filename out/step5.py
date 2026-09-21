import json, time, os, math
import geopandas as gpd, pandas as pd, numpy as np, rasterio, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

t0 = time.time()
CRS = 32613
QDATE = '2026-08-26'
G = 'out/site1_fema.gpkg'


def L(n):
    try:
        return gpd.read_file(G, layer=n).to_crs(CRS)
    except Exception:
        return None


parcel = L('parcel'); zones = L('flood_zones_clipped'); ani = L('area_not_included')
pan = L('firm_panels'); rs = L('roads_secondary'); rl = L('roads_local'); rr = L('railroads')
hl = L('hydro_linear'); ha = L('hydro_areal')

ds = rasterio.open('out/naip_site1.tif')
img = ds.read([1, 2, 3]).transpose(1, 2, 0)
b = ds.bounds
extent = (b.left, b.right, b.bottom, b.top)

fig = plt.figure(figsize=(16, 9), dpi=300)
ax = fig.add_axes([0.005, 0.075, 0.775, 0.915])
ax.imshow(img, extent=extent, origin='upper', interpolation='bilinear')
ax.set_xlim(b.left, b.right); ax.set_ylim(b.bottom, b.top)
ax.set_xticks([]); ax.set_yticks([])
for s in ax.spines.values():
    s.set_linewidth(1.2); s.set_color('#222')

if ha is not None and len(ha):
    ha.plot(ax=ax, facecolor='#4a90d9', edgecolor='#2c5f8f', alpha=.55, linewidth=.6, zorder=3)
if hl is not None and len(hl):
    hl.plot(ax=ax, color='#2c6fb5', linewidth=1.4, alpha=.85, zorder=3)
if rl is not None and len(rl):
    rl.plot(ax=ax, color='#f6e6b4', linewidth=.7, alpha=.75, zorder=4)
if rs is not None and len(rs):
    rs.plot(ax=ax, color='#ffd24d', linewidth=2.4, alpha=.95, zorder=5)
if rr is not None and len(rr):
    rr.plot(ax=ax, color='#3a3a3a', linewidth=1.1, linestyle=(0, (6, 4)), alpha=.9, zorder=4)

SFHA = {'A', 'AE', 'AH', 'AO', 'AR', 'A99', 'V', 'VE'}
present = []
for _, r in zones.iterrows():
    z = str(r['FLD_ZONE']); sub = str(r.get('ZONE_SUBTY') or '')
    if z in SFHA:
        fc, hatch, ec = '#1f6fd0', None, '#0d3f7a'
        lab = 'Zone %s - 1%% annual chance (SFHA)' % z
    elif '0.2 PCT' in sub.upper():
        fc, hatch, ec = '#8fa9c4', '////', '#5a7692'
        lab = 'Zone X (shaded) - 0.2% annual chance'
    else:
        fc, hatch, ec = '#d9d9d9', None, '#9a9a9a'
        lab = 'Zone X - area of minimal flood hazard'
    gpd.GeoSeries([r.geometry], crs=CRS).plot(ax=ax, facecolor=fc, edgecolor=ec, hatch=hatch,
                                              alpha=.45, linewidth=1.0, zorder=6)
    if lab not in [p[0] for p in present]:
        present.append((lab, fc, hatch, ec))

if ani is not None and len(ani) and not ani.geometry.iloc[0].is_empty:
    ani.plot(ax=ax, facecolor='#9e9e9e', edgecolor='#5e5e5e', hatch='xxx', alpha=.42, linewidth=1.0, zorder=6)
    present.append(('Area Not Included (ANI) - not mapped on FIRM', '#9e9e9e', 'xxx', '#5e5e5e'))

if pan is not None and len(pan):
    pan.boundary.plot(ax=ax, color='#00d0d0', linewidth=1.6, linestyle=(0, (9, 5)), zorder=7)
    for _, r in pan.iterrows():
        eff = pd.to_datetime(r['EFF_DATE'], unit='ms', errors='coerce')
        eff = eff.strftime('%m/%d/%Y') if pd.notna(eff) else 'n/a'
        c = r.geometry.intersection(parcel.geometry.iloc[0])
        pt = (c if not c.is_empty else r.geometry).representative_point()
        ax.annotate('FIRM PANEL %s\nEFF. %s' % (r['FIRM_PAN'], eff), (pt.x, pt.y),
                    ha='center', va='center', fontsize=7.5, color='#003a3a', zorder=12,
                    bbox=dict(boxstyle='round,pad=0.3', fc='#c9fbfb', ec='#00a0a0', alpha=.88, lw=.8))

parcel.boundary.plot(ax=ax, color='#ffffff', linewidth=5.2, zorder=9, alpha=.85)
parcel.boundary.plot(ax=ax, color='#8b0000', linewidth=3.2, zorder=10)
pc = parcel.geometry.iloc[0].centroid
ax.annotate('SITE PARCEL\n596.33 ac', (pc.x, pc.y + 430), ha='center', va='center', fontsize=11,
            fontweight='bold', color='#ffffff', zorder=13,
            bbox=dict(boxstyle='round,pad=0.35', fc='#8b0000', ec='white', alpha=.9, lw=1.2))


def label_lines(gdf, size, color, n=None, minlen=380, zo=11):
    if gdf is None or 'NAME' not in gdf:
        return
    seen = set()
    g = gdf.dropna(subset=['NAME']).copy()
    g['len'] = g.length
    g = g.sort_values('len', ascending=False)
    for _, r in g.iterrows():
        nm = r['NAME']
        if nm in seen or r['len'] < minlen:
            continue
        ln = r.geometry if r.geometry.geom_type == 'LineString' else max(r.geometry.geoms, key=lambda x: x.length)
        p = ln.interpolate(.5, normalized=True)
        if not (b.left + 250 < p.x < b.right - 250 and b.bottom + 250 < p.y < b.top - 250):
            continue
        seen.add(nm)
        p0 = ln.interpolate(.42, normalized=True); p1 = ln.interpolate(.58, normalized=True)
        ang = math.degrees(math.atan2(p1.y - p0.y, p1.x - p0.x))
        if ang > 90:
            ang -= 180
        if ang < -90:
            ang += 180
        ax.annotate(nm, (p.x, p.y), rotation=ang, rotation_mode='anchor', ha='center', va='center',
                    fontsize=size, color=color, zorder=zo,
                    bbox=dict(boxstyle='round,pad=0.15', fc='black', ec='none', alpha=.42))
        if n and len(seen) >= n:
            break


label_lines(rs, 8.0, '#fff3c4')
label_lines(rl, 5.6, '#f0f0f0', n=26, minlen=520)
label_lines(hl, 7.0, '#bfe0ff', minlen=300)

# scale bar in feet
FT = 0.3048
span = b.right - b.left
hspan = b.top - b.bottom
targ = span * 0.20 / FT
sb = min([500, 1000, 1500, 2000, 2500, 3000, 4000, 5000], key=lambda v: abs(v - targ))
sbm = sb * FT
x0 = b.left + span * 0.030
y0 = b.bottom + hspan * 0.040
pad = span * 0.022
ax.add_patch(Rectangle((x0 - pad, y0 - 175), sbm + 2 * pad, 355,
                       fc='white', ec='#333', alpha=.90, lw=.8, zorder=14))
for i in range(4):
    ax.add_patch(Rectangle((x0 + i * sbm / 4, y0), sbm / 4, 62,
                           fc=('black' if i % 2 == 0 else 'white'), ec='black', lw=.6, zorder=15))
ax.text(x0, y0 + 78, '0', ha='center', va='bottom', fontsize=6.0, zorder=15)
ax.text(x0 + sbm, y0 + 78, '%d ft' % sb, ha='center', va='bottom', fontsize=6.0, zorder=15)
axes_in = 16 * 0.775
ax.text(x0 + sbm / 2, y0 - 42, '1 in = %d ft at 16x9 full slide' % int(round((span / FT) / axes_in / 50) * 50),
        ha='center', va='top', fontsize=5.0, zorder=15, color='#333')

# north arrow
nx = b.right - span * 0.028
ny = b.bottom + hspan * 0.040
ax.add_patch(Rectangle((nx - 175, ny - 40), 350, 560, fc='white', ec='#333', alpha=.90, lw=.8, zorder=14))
ax.annotate('', xy=(nx, ny + 350), xytext=(nx, ny + 45),
            arrowprops=dict(arrowstyle='-|>', lw=1.8, color='black'), zorder=15)
ax.text(nx, ny + 370, 'N', ha='center', va='bottom', fontsize=8.5, fontweight='bold', zorder=15)

# ---------------- side panel ----------------
px = fig.add_axes([0.788, 0.075, 0.207, 0.915])
px.axis('off')
px.add_patch(Rectangle((0, 0), 1, 1, transform=px.transAxes, fc='#f7f7f5', ec='#bbb', lw=1))
T = px.transAxes
y = 0.975
px.text(.5, y, 'FEMA FLOOD HAZARD', ha='center', va='top', fontsize=12.5, fontweight='bold', transform=T); y -= .032
px.text(.5, y, 'TBDI Example Site 1', ha='center', va='top', fontsize=10, transform=T); y -= .024
px.text(.5, y, 'Adams County, Colorado', ha='center', va='top', fontsize=8.5, color='#444', transform=T); y -= .030
px.plot([.05, .95], [y, y], color='#999', lw=.9, transform=T); y -= .028

px.text(.05, y, 'FLOOD ZONES PRESENT', ha='left', va='top', fontsize=8.5, fontweight='bold', transform=T); y -= .026
for lab, fc, hatch, ec in present:
    px.add_patch(Rectangle((.06, y - .024), .075, .024, transform=T, fc=fc, ec=ec, hatch=hatch, alpha=.75, lw=.8))
    px.text(.15, y - .006, lab, ha='left', va='top', fontsize=6.3, transform=T, wrap=True)
    y -= .046
y -= .004
px.add_patch(Rectangle((.06, y - .020), .075, .020, transform=T, fc='none', ec='#8b0000', lw=2.2))
px.text(.15, y - .004, 'Site parcel boundary', ha='left', va='top', fontsize=6.3, transform=T); y -= .032
for col, lw, ls, lab in [('#00d0d0', 1.6, (0, (6, 3)), 'FIRM panel boundary'),
                         ('#ffd24d', 2.2, '-', 'Secondary / arterial road'),
                         ('#f6e6b4', 1.0, '-', 'Local road'),
                         ('#3a3a3a', 1.1, (0, (5, 3)), 'Railroad'),
                         ('#2c6fb5', 1.4, '-', 'Stream / ditch')]:
    px.plot([.06, .135], [y - .010, y - .010], transform=T, color=col, lw=lw, ls=ls)
    px.text(.15, y - .002, lab, ha='left', va='top', fontsize=6.3, transform=T)
    y -= .026
px.add_patch(Rectangle((.06, y - .020), .075, .020, transform=T, fc='#4a90d9', ec='#2c5f8f', alpha=.6, lw=.8))
px.text(.15, y - .004, 'Water body', ha='left', va='top', fontsize=6.3, transform=T); y -= .036

px.plot([.05, .95], [y, y], color='#999', lw=.9, transform=T); y -= .026
px.text(.05, y, 'ACREAGE WITHIN PARCEL', ha='left', va='top', fontsize=8.5, fontweight='bold', transform=T); y -= .028
summ = pd.read_csv('out/step2_zone_summary.csv')
px.text(.05, y, 'Total parcel', ha='left', va='top', fontsize=6.8, transform=T)
px.text(.95, y, '596.33 ac', ha='right', va='top', fontsize=6.8, fontweight='bold', transform=T); y -= .022
for _, r in summ.iterrows():
    nm = 'Zone X (minimal)' if r['category'] == 'X' else 'Area Not Included'
    px.text(.05, y, nm, ha='left', va='top', fontsize=6.8, transform=T)
    px.text(.95, y, '%.1f ac (%.1f%%)' % (r['acres'], r['pct']), ha='right', va='top', fontsize=6.8, transform=T)
    y -= .022
px.text(.05, y, 'SFHA (1% chance)', ha='left', va='top', fontsize=6.8, fontweight='bold', color='#8b0000', transform=T)
px.text(.95, y, '0.00 ac (0.0%)', ha='right', va='top', fontsize=6.8, fontweight='bold', color='#8b0000', transform=T)
y -= .032

px.plot([.05, .95], [y, y], color='#999', lw=.9, transform=T); y -= .024
px.text(.05, y, 'FIRM PANEL', ha='left', va='top', fontsize=8.5, fontweight='bold', transform=T); y -= .024
px.text(.05, y, '08001C0609H - eff. 03/05/2007\nDFIRM 08001C (Adams Co., CO)\nCommunity: Commerce City 080006\nRocky Mountain Arsenal - ANI',
        ha='left', va='top', fontsize=6.4, transform=T, linespacing=1.5); y -= .078

px.plot([.05, .95], [y, y], color='#999', lw=.9, transform=T); y -= .022
px.text(.05, y, 'SOURCES', ha='left', va='top', fontsize=8, fontweight='bold', transform=T); y -= .022
src = ('Flood zones / FIRM panels / political areas:\n'
       'FEMA NFHL MapServer layers 28 / 3 / 22,\n'
       'hazards.fema.gov/arcgis/rest/services/\n'
       'public/NFHL/MapServer - queried ' + QDATE + '\n\n'
       'Imagery: USGS NAIP ImageServer,\n'
       'imagery.nationalmap.gov - quad\n'
       'm_3910409_ne_13_060_20190803,\n'
       'acquired 2019-08-03, 0.6 m, USDA-FSA-APFO\n\n'
       'Roads / hydrography / county: US Census\n'
       'TIGERweb 2025 (Transportation L6/L8/L9,\n'
       'Hydro L0/L1, State_County L1)\n\n'
       'Parcel: client KMZ, TBDI Example Site 1\n\n'
       'Projection: EPSG:32613 (UTM 13N, NAD83).\n'
       'Areas computed in EPSG:5070 Albers.')
px.text(.05, y, src, ha='left', va='top', fontsize=5.3, color='#333', transform=T, linespacing=1.42)

fig.text(.005, .045,
         'FEMA National Flood Hazard Layer - Site Flood Hazard Exhibit  |  TBDI Example Site 1, Adams County, Colorado  |  Prepared ' + QDATE,
         fontsize=7.5, color='#222', ha='left', va='center')
fig.text(.005, .018,
         'Derived from the FEMA NFHL web service for planning screening only. Not a FIRM, not a LOMA/LOMR determination, and no substitute for the effective printed FIRM panel or an elevation certificate.',
         fontsize=5.6, color='#666', ha='left', va='center')
fig.savefig('out/site1_fema_flood.png', dpi=300, facecolor='white')
print('wrote out/site1_fema_flood.png  %.2f MB' % (os.path.getsize('out/site1_fema_flood.png') / 1e6))
from PIL import Image
print('size:', Image.open('out/site1_fema_flood.png').size)
print('elapsed %.1fs' % (time.time() - t0))
