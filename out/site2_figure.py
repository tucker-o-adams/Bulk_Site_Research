import json, time, os, math
import geopandas as gpd, pandas as pd, rasterio, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

t0 = time.time()
CRS = 32618
QDATE = '2026-08-26'
OUT = 'out/site2'
G = OUT + '/site2_fema.gpkg'
V = json.load(open(OUT + '/site2_values.json'))
IM = json.load(open(OUT + '/site2_imagery.json'))
ACRES = V['acres']
NAIP_DATE = IM['scenes'][0][2] if IM['scenes'] else 'unknown'
NAIP_NAME = IM['scenes'][0][0] if IM['scenes'] else 'unknown'
PANEL = V['panels'][0] if V['panels'] else None
LAYERS = set(gpd.list_layers(G)['name'])


def L(n):
    return gpd.read_file(G, layer=n).to_crs(CRS) if n in LAYERS else None


parcel = L('parcel'); zones = L('flood_zones_clipped'); ani = L('area_not_included')
pan = L('firm_panels'); rp = L('roads_primary'); rs = L('roads_secondary'); rl = L('roads_local')
rr = L('railroads'); hl = L('hydro_linear'); ha = L('hydro_areal')

ds = rasterio.open(OUT + '/naip_site2.tif')
img = ds.read([1, 2, 3]).transpose(1, 2, 0)
b = ds.bounds

fig = plt.figure(figsize=(16, 9), dpi=300)
ax = fig.add_axes([0.005, 0.075, 0.775, 0.915])
ax.imshow(img, extent=(b.left, b.right, b.bottom, b.top), origin='upper', interpolation='bilinear')
ax.set_xlim(b.left, b.right); ax.set_ylim(b.bottom, b.top)
ax.set_xticks([]); ax.set_yticks([])
for s in ax.spines.values():
    s.set_linewidth(1.2); s.set_color('#222')

if ha is not None: ha.plot(ax=ax, facecolor='#4a90d9', edgecolor='#2c5f8f', alpha=.55, linewidth=.6, zorder=3)
if hl is not None: hl.plot(ax=ax, color='#2c6fb5', linewidth=1.4, alpha=.85, zorder=3)
if rl is not None: rl.plot(ax=ax, color='#f6e6b4', linewidth=.7, alpha=.75, zorder=4)
if rs is not None: rs.plot(ax=ax, color='#ffd24d', linewidth=2.4, alpha=.95, zorder=5)
if rp is not None: rp.plot(ax=ax, color='#ff9d2e', linewidth=3.4, alpha=.95, zorder=5)
if rr is not None: rr.plot(ax=ax, color='#3a3a3a', linewidth=1.1, linestyle=(0, (6, 4)), alpha=.9, zorder=4)

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
                                              alpha=.45, linewidth=1.2, zorder=6)
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
                    xytext=(0, -95), textcoords='offset points',
                    ha='center', va='center', fontsize=7.5, color='#003a3a', zorder=12,
                    bbox=dict(boxstyle='round,pad=0.3', fc='#c9fbfb', ec='#00a0a0', alpha=.88, lw=.8))

parcel.boundary.plot(ax=ax, color='#ffffff', linewidth=5.2, zorder=9, alpha=.85)
parcel.boundary.plot(ax=ax, color='#8b0000', linewidth=3.2, zorder=10)
pc = parcel.geometry.iloc[0].centroid
pminx, pminy, pmaxx, pmaxy = parcel.total_bounds
ax.annotate('SITE PARCEL\n%.2f ac' % ACRES, (pc.x, pmaxy + 210), ha='center', va='bottom', fontsize=10.5,
            fontweight='bold', color='#ffffff', zorder=13,
            bbox=dict(boxstyle='round,pad=0.35', fc='#8b0000', ec='white', alpha=.92, lw=1.2))

# call out the SFHA sliver with a leader
sf = zones[zones['FLD_ZONE'].isin(SFHA)]
if len(sf):
    g = sf.geometry.union_all()
    p = g.representative_point()
    ac = sum(sf.geometry.area) / 4046.8564224
    ax.annotate('Zone A (SFHA)\n%.3f ac' % ac, xy=(p.x, p.y), xytext=(p.x + 430, p.y - 330),
                ha='center', va='center', fontsize=7.5, color='white', zorder=14,
                arrowprops=dict(arrowstyle='-|>', lw=1.4, color='#1f6fd0',
                                shrinkA=2, shrinkB=2, connectionstyle='arc3,rad=-0.2'),
                bbox=dict(boxstyle='round,pad=0.3', fc='#1f6fd0', ec='white', alpha=.95, lw=1.0))


def label_lines(gdf, size, color, n=None, minlen=380, zo=11):
    if gdf is None or 'NAME' not in gdf:
        return
    from shapely.geometry import box as _box
    frame = _box(b.left, b.bottom, b.right, b.top)
    seen = set(); g = gdf.dropna(subset=['NAME']).copy()
    g['geometry'] = g.geometry.intersection(frame)   # label the visible run, not the whole 20 km line
    g = g[~g.geometry.is_empty]
    g['len'] = g.length
    for _, r in g.sort_values('len', ascending=False).iterrows():
        nm = r['NAME']
        if nm in seen or r['len'] < minlen:
            continue
        ln = r.geometry if r.geometry.geom_type == 'LineString' else max(r.geometry.geoms, key=lambda x: x.length)
        # walk along the line for the first position that sits inside the label frame
        p = None; f = None
        for frac in (.5, .35, .65, .25, .75, .15, .85):
            c = ln.interpolate(frac, normalized=True)
            if b.left + 200 < c.x < b.right - 200 and b.bottom + 200 < c.y < b.top - 200:
                p, f = c, frac; break
        if p is None:
            continue
        seen.add(nm)
        p0 = ln.interpolate(max(f - .08, 0), normalized=True); p1 = ln.interpolate(min(f + .08, 1), normalized=True)
        a = math.degrees(math.atan2(p1.y - p0.y, p1.x - p0.x))
        a = a - 180 if a > 90 else (a + 180 if a < -90 else a)
        ax.annotate(nm, (p.x, p.y), rotation=a, rotation_mode='anchor', ha='center', va='center',
                    fontsize=size, color=color, zorder=zo,
                    bbox=dict(boxstyle='round,pad=0.15', fc='black', ec='none', alpha=.42))
        if n and len(seen) >= n:
            break


label_lines(rp, 8.5, '#ffe0b0', minlen=300)
label_lines(rs, 7.6, '#fff3c4', minlen=300)
label_lines(rl, 5.6, '#f0f0f0', n=24, minlen=330)
label_lines(hl, 7.0, '#bfe0ff', minlen=200)
if ha is not None and 'NAME' in ha:
    for _, r in ha.dropna(subset=['NAME']).iterrows():
        p = r.geometry.representative_point()
        if b.left + 200 < p.x < b.right - 200 and b.bottom + 200 < p.y < b.top - 200:
            ax.annotate(r['NAME'], (p.x, p.y), ha='center', va='center', fontsize=6.8, color='#bfe0ff',
                        zorder=11, bbox=dict(boxstyle='round,pad=0.15', fc='black', ec='none', alpha=.42))

# scale bar
FT = 0.3048; span = b.right - b.left; hspan = b.top - b.bottom
sb = min([500, 1000, 1500, 2000, 2500, 3000, 4000], key=lambda v: abs(v - span * 0.20 / FT))
sbm = sb * FT
x0 = b.left + span * 0.030; y0 = b.bottom + hspan * 0.040; pad = span * 0.022
ax.add_patch(Rectangle((x0 - pad, y0 - 118), sbm + 2 * pad, 240, fc='white', ec='#333', alpha=.90, lw=.8, zorder=14))
for i in range(4):
    ax.add_patch(Rectangle((x0 + i * sbm / 4, y0), sbm / 4, 42,
                           fc=('black' if i % 2 == 0 else 'white'), ec='black', lw=.6, zorder=15))
ax.text(x0, y0 + 54, '0', ha='center', va='bottom', fontsize=6.0, zorder=15)
ax.text(x0 + sbm, y0 + 54, '%d ft' % sb, ha='center', va='bottom', fontsize=6.0, zorder=15)
ax.text(x0 + sbm / 2, y0 - 28, '1 in = %d ft at 16x9 full slide' % int(round((span / FT) / (16 * 0.775) / 25) * 25),
        ha='center', va='top', fontsize=5.0, zorder=15, color='#333')

nx = b.right - span * 0.028; ny = b.bottom + hspan * 0.040
ax.add_patch(Rectangle((nx - 118, ny - 27), 236, 378, fc='white', ec='#333', alpha=.90, lw=.8, zorder=14))
ax.annotate('', xy=(nx, ny + 236), xytext=(nx, ny + 30),
            arrowprops=dict(arrowstyle='-|>', lw=1.8, color='black'), zorder=15)
ax.text(nx, ny + 250, 'N', ha='center', va='bottom', fontsize=8.5, fontweight='bold', zorder=15)

# ---------------- side panel ----------------
px = fig.add_axes([0.788, 0.075, 0.207, 0.915]); px.axis('off')
px.add_patch(Rectangle((0, 0), 1, 1, transform=px.transAxes, fc='#f7f7f5', ec='#bbb', lw=1))
T = px.transAxes; y = 0.975
px.text(.5, y, 'FEMA FLOOD HAZARD', ha='center', va='top', fontsize=12.5, fontweight='bold', transform=T); y -= .030
px.text(.5, y, '1637 Green Mount Pkwy', ha='center', va='top', fontsize=9.5, transform=T); y -= .022
px.text(.5, y, 'Williamsburg, VA 23185', ha='center', va='top', fontsize=8.5, color='#444', transform=T); y -= .020
px.text(.5, y, 'James City County - Parcel %s' % V['parcel_id'], ha='center', va='top', fontsize=7, color='#444', transform=T); y -= .028
px.plot([.05, .95], [y, y], color='#999', lw=.9, transform=T); y -= .026

px.text(.05, y, 'FLOOD ZONES PRESENT', ha='left', va='top', fontsize=8.5, fontweight='bold', transform=T); y -= .026
for lab, fc, hatch, ec in present:
    px.add_patch(Rectangle((.06, y - .024), .075, .024, transform=T, fc=fc, ec=ec, hatch=hatch, alpha=.75, lw=.8))
    px.text(.15, y - .006, lab, ha='left', va='top', fontsize=6.3, transform=T)
    y -= .041
y -= .004
px.add_patch(Rectangle((.06, y - .020), .075, .020, transform=T, fc='none', ec='#8b0000', lw=2.2))
px.text(.15, y - .004, 'Site parcel boundary', ha='left', va='top', fontsize=6.3, transform=T); y -= .030
for col, lw, ls, lab in [('#00d0d0', 1.6, (0, (6, 3)), 'FIRM panel boundary'),
                         ('#ff9d2e', 2.6, '-', 'Interstate / primary road'),
                         ('#ffd24d', 2.2, '-', 'Secondary / arterial road'),
                         ('#f6e6b4', 1.0, '-', 'Local road'),
                         ('#3a3a3a', 1.1, (0, (5, 3)), 'Railroad'),
                         ('#2c6fb5', 1.4, '-', 'Stream / creek')]:
    px.plot([.06, .135], [y - .010, y - .010], transform=T, color=col, lw=lw, ls=ls)
    px.text(.15, y - .002, lab, ha='left', va='top', fontsize=6.3, transform=T); y -= .0225
px.add_patch(Rectangle((.06, y - .020), .075, .020, transform=T, fc='#4a90d9', ec='#2c5f8f', alpha=.6, lw=.8))
px.text(.15, y - .004, 'Water body', ha='left', va='top', fontsize=6.3, transform=T); y -= .034

px.plot([.05, .95], [y, y], color='#999', lw=.9, transform=T); y -= .026
px.text(.05, y, 'ACREAGE WITHIN PARCEL', ha='left', va='top', fontsize=8.5, fontweight='bold', transform=T); y -= .028
px.text(.05, y, 'Total parcel', ha='left', va='top', fontsize=6.8, transform=T)
px.text(.95, y, '%.2f ac' % ACRES, ha='right', va='top', fontsize=6.8, fontweight='bold', transform=T); y -= .021
summ = pd.read_csv(OUT + '/site2_zone_summary.csv')
for _, r in summ.sort_values('acres', ascending=False).iterrows():
    nm = 'Zone %s (minimal)' % r['FLD_ZONE'] if r['SFHA_TF'] == 'F' else 'Zone %s (SFHA)' % r['FLD_ZONE']
    px.text(.05, y, nm, ha='left', va='top', fontsize=6.8, transform=T)
    px.text(.95, y, '%.3f ac (%.2f%%)' % (r['acres'], r['pct']), ha='right', va='top', fontsize=6.8, transform=T)
    y -= .021
sf_ac = summ[summ['SFHA_TF'] == 'T']['acres'].sum()
px.text(.05, y, 'SFHA (1% chance)', ha='left', va='top', fontsize=6.8, fontweight='bold', color='#8b0000', transform=T)
px.text(.95, y, '%.3f ac (%.2f%%)' % (sf_ac, 100 * sf_ac / ACRES), ha='right', va='top', fontsize=6.8,
        fontweight='bold', color='#8b0000', transform=T); y -= .030

px.plot([.05, .95], [y, y], color='#999', lw=.9, transform=T); y -= .024
px.text(.05, y, 'FIRM PANEL', ha='left', va='top', fontsize=8.5, fontweight='bold', transform=T); y -= .024
px.text(.05, y, '%s - eff. %s\nDFIRM %s (James City Co., VA)\nCommunity: James City County\nUnincorporated Areas, CID 510201\nNo Base Flood Elevation on Zone A'
        % (PANEL['FIRM_PAN'], pd.to_datetime(PANEL['EFF_ISO']).strftime('%m/%d/%Y'), PANEL['DFIRM_ID']),
        ha='left', va='top', fontsize=6.3, transform=T, linespacing=1.35); y -= .079

px.plot([.05, .95], [y, y], color='#999', lw=.9, transform=T); y -= .022
px.text(.05, y, 'SOURCES', ha='left', va='top', fontsize=8, fontweight='bold', transform=T); y -= .022
src = ('Flood zones / FIRM panels / political areas:\n'
       'FEMA NFHL MapServer layers 28 / 3 / 22,\n'
       'hazards.fema.gov/arcgis/rest/services/\n'
       'public/NFHL/MapServer - queried ' + QDATE + '\n\n'
       'Imagery: USGS NAIP ImageServer,\n'
       'imagery.nationalmap.gov - quad\n' + NAIP_NAME + ',\n'
       'acquired ' + NAIP_DATE + ', 0.6 m, USDA-FSA-APFO\n\n'
       'Roads / hydrography / county: US Census\n'
       'TIGERweb 2025 (Transportation L2/L6/L8/L9,\n'
       'Hydro L0/L1, State_County L1)\n\n'
       'Parcel: VGIN Virginia Parcels (VDEM),\n'
       'QPID ' + V['vgin_qpid'] + ', updated 2026-04-06.\n'
       'Address geocoded with Esri World\n'
       'Geocoding Service (score 100).\n\n'
       'Projection: EPSG:32618 (UTM 18N, WGS84).\n'
       'Areas computed in EPSG:5070 Albers.')
px.text(.05, y, src, ha='left', va='top', fontsize=4.9, color='#333', transform=T, linespacing=1.27)

fig.text(.005, .045, 'FEMA National Flood Hazard Layer - Site Flood Hazard Exhibit  |  1637 Green Mount Pkwy, '
         'Williamsburg, VA 23185  |  James City County  |  Prepared ' + QDATE, fontsize=7.5, color='#222', ha='left', va='center')
fig.text(.005, .018, 'Derived from the FEMA NFHL web service for planning screening only. Not a FIRM, not a LOMA/LOMR '
         'determination, and no substitute for the effective printed FIRM panel or an elevation certificate. Parcel geometry '
         'is the VGIN statewide cadastral layer, not a boundary survey.', fontsize=5.6, color='#666', ha='left', va='center')
fig.savefig(OUT + '/site2_fema_flood.png', dpi=300, facecolor='white')
print('wrote %s  %.2f MB' % (OUT + '/site2_fema_flood.png', os.path.getsize(OUT + '/site2_fema_flood.png') / 1e6))
from PIL import Image
print('size:', Image.open(OUT + '/site2_fema_flood.png').size)
print('elapsed %.1fs' % (time.time() - t0))
