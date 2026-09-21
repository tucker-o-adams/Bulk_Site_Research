# scripts/bulk — bulk site research pipeline

CSV of sites in → per-site fields with provenance out (Excel + KMZ to follow).
Free/public sources only, by decision (2026-09-21): no Mireye, no paid APIs.

```
.venv_fema/Scripts/python.exe scripts/bulk/run.py --sites <in.csv> --out Outputs/<batch>/
```

## Input contract

One CSV, one row per site.

| Column | Required | Notes |
|---|---|---|
| `site_id` | yes | unique key; Windstream uses the CLLI |
| `lat`, `lng` | yes | WGS84 decimal degrees; rows outside the US are rejected (lat/lng swapped?) |
| `name`, `address`, `apn`, `acres_stated`, `state`, `county`, `group`, `notes` | no | understood and carried through; `group` drives KMZ folder splits |
| anything else | no | passed through untouched to `sites.csv`, never interpreted |

Rejected rows are listed with a reason in the console and in `run.json`, never dropped silently.

## Outputs (`--out`)

| File | Contents |
|---|---|
| `sites.csv` | one row per site: input columns, then every producer field |
| `provenance.csv` | one row per site × field: `value, status, source, source_url, vintage, fetched_at, method, note` |
| `run.json` | input path + sha256, rejected rows, per-producer source/vintage/status tallies, cache hits/misses |
| *(none in the batch folder)* | raw service responses go to **`data/cache/<producer>/<lat_lng[_subquery]>.json`**, shared across batches and keyed by coordinate, so any location fetched once is never fetched again. A failed query is never cached. Delete a file or folder to refresh from source. |

`status` is one of `ok`, `absent` (source confirmed nothing there — an answer, not an error),
`failed` (source unreachable; value null), `manual` (supplied by a person).

## Producers

| Producer | Fields | Source | Status |
|---|---|---|---|
| `transmission` | `tx_nearest_m/ft, tx_voltage_kv, tx_volt_class, tx_voltage_basis, tx_line_name, tx_line_id, tx_owner, tx_type, tx_status, tx_attrs_inferred, tx_100kv_*` | HIFLD US Electric Power Transmission Lines — ArcGIS mirror of the dataset DHS retired Aug 2025; data last edited 2025-08-26. 15 km query, exact point-to-segment distance. | **regression-proven** (below) |
| `substations` | `sub_nearest_m/name/type/max_kv/min_kv/kv_inferred/lines/status/source/id, sub_100kv_nearest_m/name/max_kv/lines, sub_230kv_nearest_m/name/max_kv, sub_count_within_10km, sub_max_kv_within_10km` | HIFLD Electric Substations — ArcGIS mirror, layer edited 2021-02-25 (older than the lines layer). 15 km query, straight-line distance. Per-row SOURCE (imagery / OpenStreetMap / state GIS) and MAX_INFER carried through; TAP = line tap. `-999999` normalised to null. | **validated** 10/10 vs Mireye Aug 11 (nearest distance within 0.3 %, nearest max kV, count within 10 km) |
| `flood` | `fema_determination, fema_flood_zone, fema_zone_subtype, fema_sfha, fema_static_bfe_ft, fema_dfirm_id, fema_firm_panel, fema_panel_effective, fema_nearest_sfha_m, fema_nearest_sfha_zone` | FEMA National Flood Hazard Layer: one L28 query for all zones within 1 km (geometry simplified to ~2 m) gives the zone under the pin and the nearest SFHA; L3 panel; L22 political (Area Not Included) and L0 availability only when no zone contains the pin. 2 FEMA calls per typical site. `fema_determination` = mapped / area_not_included / no_nfhl_data — an unmapped point is never reported as Zone X. | **validated** 10/10 vs Mireye Aug 11 zones |
| `wetlands` | `nwi_mapping_status, nwi_image_year, nwi_project, nwi_at_point, nwi_type_at_point, nwi_code_at_point, nwi_nearest_m, nwi_nearest_type, nwi_nearest_code, nwi_nearest_acres, nwi_count_within_500m, nwi_polygon_acres_within_500m` | USFWS National Wetlands Inventory: Wetlands, Wetlands_Status, Data_Source. Photointerpreted, not jurisdictional; acres are whole NWI polygons, not clipped. Unmapped areas carry a note on every zero. | in use; no independent known answer yet |
| `metro` | `metro_urban_area_at_point, metro_urban_area_at_point_pop, metro_250k_nearest_name/m/pop, metro_1m_nearest_name/m/pop` | Census TIGERweb 2020 Urban Areas with POP100. Straight-line to the urban-area boundary (0 inside), not driving time; urban areas are built-up footprints, not MSAs. 300 km search. | geographic sanity checks (Sugar Land inside Houston 0 km, Baldwin GA 41 km to Atlanta, Riverside TX rural) |
| `datacenter` | `dc_nearest_m/name/city/state/networks/peeringdb_url, dc_hub_nearest_m/name/city/networks, dc_count_within_25km/50km, dc_max_networks_within_50km` | PeeringDB facility list (`Reference/peeringdb.kmz`, 1,353 US facilities), local, no network. Registered colo/IX facilities only — hyperscale and enterprise data centers are not listed. Hub = >= 20 networks (114 facilities). | geographic sanity checks |
| `housing` | `hu_block_at_point, pop_block_at_point, block_at_point_acres, hu_within_0_5mi, pop_within_0_5mi, hu_within_1mi, pop_within_1mi, blocks_within_1mi` | Census TIGERweb 2020 Blocks (HU100, POP100). Blocks counted whole when their Census internal point is within the radius; rural blocks are large, so rural sums are coarse. Raw counts only — no density class until thresholds are agreed. | sanity checks |
| `schools` | `school_nearest_m/name/type/city, schools_within_0_5mi/1mi, public_schools_within_1mi, private_schools_within_1mi` | NCES EDGE public 2024-25 + private 2023-24 school points (K-12 only). 5 km search. | sanity checks (Nordonia Middle 122 m from NRFDOHXA) |
| `worship` | `worship_nearest_m/name/city, worship_within_0_5mi/1mi` | HIFLD All Places of Worship, third-party ArcGIS mirror (fragile), geocoded from IRS filings — may be a mailing address. 5 km search. | sanity checks |
| `healthcare` | `nursing_home_nearest_m/name/beds/rating, nursing_homes_within_0_5mi/1mi, hospital_nearest_m/name/type/emergency/geocode_match, hospitals_within_1mi` | Local CMS reference files (`data/reference/`, built by `reference/fetch_cms_reference.py`): 14,690 certified nursing homes with CMS coordinates; 4,621 of 5,419 Medicare hospitals geocoded with the Census batch geocoder (`geocode.py`). No network at run time. | sanity checks |

Planned producers, their verified sources, and the fallback for every source (built or not): **BACKLOG.md**.

**Operating note.** FEMA's NFHL server answers in 30-70 s per site and drops connections
intermittently; NWI occasionally too. `run.py` processes sites in parallel (`--workers`, default 6)
and never caches a failed query, so the procedure is: run, then rerun until `run.json` shows no
`failed` status. Windstream 200 on 2026-09-21 (two-call flood, fresh FEMA fetch): first pass 147 s with 170 failed
fields, two reruns (53 s, 43 s) to zero. The earlier five-call design took 26 min for its first pass.

A producer never raises on a bad source answer: it returns `absent`/`failed` values with a note.

## Regression fixture

`fixtures/windstream_200.csv` — the 200 Windstream COs in the input format
(built by `fixtures/make_windstream_fixture.py` from the broker workbook + KMZ;
`group` = Interesting / Other).

`fixtures/check_windstream_transmission.py Outputs/windstream-200/sites.csv` compares the
transmission producer against `Outputs/Excel outputs/WS_Top200_Transmission_Distance.csv`
(the Aug 2026 `tx_distance.py` output). **2026-09-21: 200/200 match** on line ID, distance,
owner, and the ≥100 kV line. One deliberate difference: the old CSV carried HIFLD's
`-999999` "not published" sentinel as a voltage; the producer normalizes it to null.

Every new producer gets the same treatment: a fixture run and a check against a known answer
before it is trusted.

## Requirements

`.venv_fema` plus `requirements-bulk.txt` (openpyxl). Standard library otherwise.
