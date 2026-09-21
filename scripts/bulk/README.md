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
| `flood` | `fema_determination, fema_flood_zone, fema_zone_subtype, fema_sfha, fema_static_bfe_ft, fema_dfirm_id, fema_firm_panel, fema_panel_effective, fema_nearest_sfha_m, fema_nearest_sfha_zone` | FEMA National Flood Hazard Layer: one L28 query for all zones within 1 km (geometry simplified to ~2 m) gives the zone under the pin and the nearest SFHA; L3 panel; L22 political (Area Not Included) and L0 availability only when no zone contains the pin. 2 FEMA calls per typical site. `fema_determination` = mapped / area_not_included / no_nfhl_data — an unmapped point is never reported as Zone X. | **validated** 10/10 vs Mireye Aug 11 zones |
| `wetlands` | `nwi_mapping_status, nwi_image_year, nwi_project, nwi_at_point, nwi_type_at_point, nwi_code_at_point, nwi_nearest_m, nwi_nearest_type, nwi_nearest_code, nwi_nearest_acres, nwi_count_within_500m, nwi_polygon_acres_within_500m` | USFWS National Wetlands Inventory: Wetlands, Wetlands_Status, Data_Source. Photointerpreted, not jurisdictional; acres are whole NWI polygons, not clipped. Unmapped areas carry a note on every zero. | in use; no independent known answer yet |

Planned, same frame: `substations` (HIFLD mirror), `metro` (Census TIGERweb urban areas, straight-line),
`datacenter` (PeeringDB KMZ, straight-line), `parcel` (county/state GIS, per-county registry). Then `flags`
(go/no-go rules as data), `excel`, `kmz`.

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
