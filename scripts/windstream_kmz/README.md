# Windstream Top 200 KMZ pipeline — recovered scripts

These scripts built `TBDI_WS_Combined_2.kmz` (Aug 24 2026) and its supporting
CSVs. They were written in Claude Code session "Mireye tools access"
(Aug 11–24 2026) to a session scratchpad that was later deleted; the code
here was recovered verbatim from that session's transcript on Sep 21 2026,
with every subsequent edit replayed, so each file is its final version.

**Status: as-recovered.** Paths are hardcoded to the old
`C:\Users\tucke\OneDrive\...\Mireye` location and to the scratchpad. They
need path updates before they run again. `fetch_hifld_segments.py` is new
(Sep 21) and already uses project-relative paths.

## Build chain (in order)

| Step | Script | Reads | Writes |
|---|---|---|---|
| 0 | `read_ws200.py` | Top 200 workbook | site list (CLLI, state, lat, lng) |
| 1 | `tx_distance.py` | site list; HIFLD national layer (live) | `WS_Top200_Transmission_Distance.csv` — nearest line per site, any voltage and ≥100 kV, validated vs Mireye within 0.5 % |
| 1a | `find_tx.py`, `tx_voltcheck.py`, `verify_kv.py` | — | one-off probes used while choosing the HIFLD endpoint |
| 1b | `fetch_hifld_segments.py` **(new)** | Transmission_Distance CSV; HIFLD (live) | `Windstream site data/hifld_tx_segments_5km.geojson` + `.meta.json` — all segments within 5 km of any site, deduped by HIFLD ID (1,128) |
| 2 | `build_kmz.py` | Transmission_Distance CSV; HIFLD (live, 5 km) | `WS_Sites_and_Transmission.kmz` — folder A: 200 sites + segments in six voltage folders |
| 3 | `merge_kmz.py` | step 2 KMZ; broker `WS Targeted Sites Overview 26.8.20.kmz`; `WS_Sites_Parcel_Sizes_FINAL.csv` | `TBDI_WS_Combined.kmz` — adds B (broker overview) and C (parcel results) |
| 4 | `add_folders.py` | Combined KMZ | adds D (nearest segment + connector per site) and E (Interesting Sites) |
| 5 | `add_verify.py`, `add_interesting_verify.py` | Combined KMZ | adds F (per-site verification folders by state, then the Interesting-only subset) |
| 6 | `parcel_lookup.py`, `kmz_poly.py`, `kmz_geom.py`, `add_parcels.py` | county GIS (live); Parcel_Sizes_FINAL | adds G (33 parcel polygons) and inserts them into F |
| — | `tree.py`, `parse_kmz.py` | any KMZ | inspection helpers |

## Parcel / power side-scripts (same session)

`parcel_lookup.py`, `compare_acres.py`, `refresh_acres.py`, `merge_final.py`,
`finalize.py`, `parcel_status.py` → the 45-site parcel CSVs.
`build_power_csv.py`, `power_analysis.py`, `power_analysis2.py`, `mw_tiers.py`
→ `WS_Top200_Existing_Power.csv`.
`build_screen_xlsx.py` → `TBDI_Mireye_Site_Screen*.xlsx` (Mireye field pulls, Aug 11).

## Data sources

- **Transmission:** HIFLD / EIA "US Electric Power Transmission Lines", full
  national layer (94,619 segments incl. sub-100 kV):
  `https://services2.arcgis.com/FiaPA4ga0iQKduv3/arcgis/rest/services/US_Electric_Power_Transmission_Lines/FeatureServer/0`
  An earlier FEMA Region-9 mirror was rejected because it is filtered to
  ≥100 kV and silently drops 69 kV lines. Geometry is national-scale and
  commonly sits 20–50 m off the towers visible in imagery.
- **Parcels:** county GIS REST services (Regrid via Mireye for some). 11 of 45
  Interesting Sites have no polygon (7 GA qPublic counties, 3 KY PVA, 1 TX).
- **Broker overlay:** `Reference/WS Targeted Sites Overview 26.8.20.kmz`.
