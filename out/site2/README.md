# Site 2 — 1637 Green Mount Pkwy, Williamsburg, VA 23185

Same Step 5 pipeline as TBDI Example Site 1, run 2026-08-26. All public REST
services, no manual downloads.

**Deliverable:** `site2_fema_flood.png` — 4800 × 2700 px, 300 dpi, 16:9.

## The one difference in method

Site 1 supplied its own parcel polygon in a KMZ. This one was an address, so
the boundary had to be found:

1. **Geocode** — the US Census geocoder returned **0 matches** for every
   spelling tried (Green Mount / Greenmount, Pkwy / Parkway). Esri's World
   Geocoding Service matched at **score 100** → −76.589452, 37.201089.
2. **Parcel** — that point was used in a point-in-polygon query against the
   **VGIN statewide Virginia Parcels** layer (Virginia Dept. of Emergency
   Management), which returned exactly one parcel.

> **Caveat worth checking before this goes in a report.** The address→parcel
> link rests on a single geocode. The Census geocoder not knowing the street
> suggests it is recently platted, and the VGIN layer carries no address
> field — only parcel IDs. The geometry is authoritative; that it is *this*
> address is one inference. Confirm PARCELID 6010200001 against the James City
> County assessor before relying on it. VGIN is also a statewide cadastral
> compilation, not a boundary survey.

## Values

| Item | Value | Source (all queried 2026-08-26) |
|---|---|---|
| Geocode | −76.589452, 37.201089 (score 100) | `geocode.arcgis.com/.../World/GeocodeServer/findAddressCandidates` |
| Parcel ID / VGIN QPID | **6010200001** / 5109506999583 | `vginmaps.vdem.virginia.gov/arcgis/rest/services/VA_Base_Layers/VA_Parcels/MapServer/0/query` |
| Locality (parcel layer) | James City County, FIPS 51095; layer updated 2026-04-06 | same |
| Vertices / interior rings | 78 / 0 | same |
| Centroid | −76.5891982, 37.2011340 | computed |
| **Area** | **135,072.34 m² = 33.377 acres** | computed in EPSG:5070 |
| County (spatial query) | **James City County, GEOID 51095 — 100.00 %** | `tigerweb.geo.census.gov/.../TIGERweb/State_County/MapServer/1/query` |
| **Zone X** (minimal hazard) | **33.309 ac — 99.80 %** | FEMA NFHL layer 28 `S_FLD_HAZ_AR` |
| **Zone A** (SFHA, no BFE) | **0.068 ac — 0.20 %**, `STATIC_BFE = -9999` | same |
| **Total SFHA** | **0.068 ac (0.20 %)** | same |
| NFHL mapped coverage | **100.00 %** of parcel (study 51095C) | NFHL layer 0 |
| FIRM panel (county-matched) | **51095C0229D**, eff. **2015-12-16**, DFIRM 51095C | NFHL layer 3 `S_FIRM_PAN` |
| Panels dropped (other DFIRMs) | 51199C0105D eff. 2015-01-16; 5101030029D eff. 2014-12-09 | same |
| Political area | James City County Unincorporated Areas, CID 510201, `ANI_TF = F` — **100 %** | NFHL layer 22 `S_POL_AR` |
| Imagery | **2023-10-10**, 0.6 m, `m_3707652_nw_18_060_20231010`, USDA-FSA-APFO | `imagery.nationalmap.gov/.../USGSNAIPImagery/ImageServer` |
| Imagery mosaic | 6400 × 3600 px @ **0.601 m/px** (2 × 2 tiles, native resolution) | `exportImage` |
| Context | I-64, Pocahontas Trl, Yorktown Rd, Jefferson Ave, Warwick Blvd; CSX; Skiffes Creek + Skiffs Creek Reservoir | TIGERweb Transportation L2/L6/L8/L9, Hydro L0/L1 |
| Projections | figure EPSG:32618 (UTM 18N); areas EPSG:5070 | — |

**No service failed.** No retries were needed, no `partial_failures`, no HTTP
400s. Total data-fetch time 9.8 s; imagery + context 53.7 s; figure render 30 s.

## Reading of the result

Practically a clean site: 100 % of the parcel carries an effective FEMA
determination (unlike Site 1, where 72 % was Area Not Included), and 99.8 % is
Zone X minimal hazard. The only SFHA is a **0.068-acre Zone A sliver** on the
northeast edge where the parcel meets Skiffs Creek Reservoir — called out on
the figure with a leader because at this scale it is about 28 px across. Zone A
is an *approximate* study with **no Base Flood Elevation determined**, so if
anything is ever proposed near that edge, the BFE would have to be developed
rather than read off the FIRM.

## Files

| File | What |
|---|---|
| `site2_fema_flood.png` | the figure, 4800 × 2700, 300 dpi |
| `site2_fema.gpkg` | 12 layers — parcel, county, flood zones (raw + clipped), FIRM panel, political areas, roads ×3, railroads, hydro ×2 |
| `site2_fema.kmz` | parcel, Zone A, Zone X, FIRM panel for Google Earth |
| `naip_site2.tif` | georeferenced NAIP mosaic, EPSG:32618, 48.8 MB |
| `site2_values.json`, `site2_zone_summary.csv` | the numbers above, machine-readable |
| `site2_data_log.txt`, `site2_imagery_log.txt` | timestamped request logs |

Scripts: `../site2_data.py`, `../site2_imagery.py`, `../site2_figure.py`.
