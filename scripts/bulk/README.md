# scripts/bulk — bulk site research pipeline

CSV of sites in → per-site fields with provenance out, then a workbook, a Google Earth KMZ and,
for chosen sites, PNG exhibits. Free/public sources only, by decision (2026-09-21): no Mireye, no
paid APIs.

## Running a batch, end to end

The commands below are the mechanics; the full sequence around them (product definition, thresholds
approved before any site is scored, screening, survivor review) is in **WORKFLOW.md** (draft).

```
# 0. only if the list has addresses but no coordinates
.venv_fema/Scripts/python.exe scripts/bulk/geocode.py <raw.csv> <in.csv>
# 1. are the sources still there and unchanged? (exit 1 = something drifted; read it before trusting a run)
.venv_fema/Scripts/python.exe scripts/bulk/check_sources.py
# 2. the run; repeat until run.json shows no `failed` (FEMA drops connections; failures are never cached)
.venv_fema/Scripts/python.exe scripts/bulk/run.py --sites <in.csv> --out Outputs/<batch>/
# 3. deliverables, from the run's outputs and the cache (no network)
.venv_fema/Scripts/python.exe scripts/bulk/excel.py Outputs/<batch>/ --name <Title>
.venv_fema/Scripts/python.exe scripts/bulk/kmz.py Outputs/<batch>/ --name <Title>
# 4. exhibits for the sites someone will look at
.venv_fema/Scripts/python.exe scripts/bulk/figure.py Outputs/<batch>/ --only SITE_ID,SITE_ID
```

`run.py` options: `--producers transmission,flood,...` (default all, in the order of the Producers
table), `--only SITE_ID,...` (a subset; an unknown id is reported), `--workers N` (default 6),
`--expected-owner REGEX` (below). A run overwrites the batch folder's `sites.csv`, `provenance.csv`
and `run.json`; everything it fetched stays in `data/cache`, so a rerun is fast and offline.

## Input contract

One CSV, one row per site.

| Column | Required | Notes |
|---|---|---|
| `site_id` | yes | unique key; Windstream uses the CLLI. Also read from `id` / `site` |
| `lat`, `lng` | yes | WGS84 decimal degrees; rows outside the US are rejected (lat/lng swapped?). Also read from `Latitude` / `Longitude` / `lon` / `long` / `x`,`y`. A row with no coordinates is rejected with "run geocode.py first" |
| `acres_stated` | no | the broker's acreage; also read from `acres` / `acreage`. Read leniently: `25`, `25 ac`, `±25 acres`, `1,200` parse; a range or text (`20-30`, `TBD`) leaves it empty and keeps the words in `acres_stated_text` — never a rejection. Sizes the stand-in square when no parcel resolves (footprint) |
| `name`, `address`, `apn`, `state`, `county`, `group`, `notes` | no | understood and carried through; `group` drives KMZ folder splits; `state` drives the KMZ verification folders (omit it and they are flat) |
| anything else | no | passed through untouched to `sites.csv`, never interpreted |

Rejected rows are listed with a reason in the console and in `run.json`, never dropped silently.

**Address-only lists.** `geocode.py <raw.csv> <in.csv>` fills `lat`/`lng` from `street, city, state, zip`
columns or one `address` column ("123 Main St, Town, ST 12345"), using the free Census batch geocoder
(tens of metres typical). It adds `geocode_match` / `geocode_match_type` / `geocode_matched_address`:
check every `Non_Exact` row (it matched Chestnut **St** to Chestnut **Ct** in testing). Unmatched rows
keep blank coordinates, and run.py lists them as rejected.

## Outputs (`--out`)

| File | Contents |
|---|---|
| `sites.csv` | one row per site: input columns, then every producer field |
| `provenance.csv` | one row per site × field: `value, status, source, source_url, vintage, fetched_at, method, note` |
| `run.json` | input path + sha256, rejected rows, per-producer source/vintage/status tallies, cache hits/misses |
| *(none in the batch folder)* | raw service responses go to **`data/cache/<producer>/<lat_lng[_subquery]>.json`**, shared across batches and keyed by coordinate, so any location fetched once is never fetched again. A failed query is never cached; an answer capped at the service's record limit is paged to completion (or fails if the service cannot page); a cached answer from a different service endpoint is refetched. Delete a file or folder to refresh from source. |

`status` is one of `ok`, `absent` (source confirmed nothing there — an answer, not an error),
`failed` (source unreachable; value null), `manual` (supplied by a person).

## Portfolio owner check

For a batch that is one operator's portfolio, pass the owner of record the parcels should carry:

```
.venv_fema/Scripts/python.exe scripts/bulk/run.py --sites <in.csv> --out Outputs/<batch>/ --expected-owner "windstream|kinetic|csl|valor tele|telephone|telecom|alltel|allied tele|arcco|public utility|-PU$"
```

(That is the Windstream pattern: its CSL, Kinetic, Valor, Alltel and Iowa Telecom entities, and the
public-utility parcel numbering some counties use.) `parcel_owner_check` is then `expected owner`,
`different owner - review` (the pin may be on a neighbouring parcel), `no owner in source - review`, or
`not checkable: source has no owner field` (Ohio's statewide layer omits owners). An `expected_owner`
column in the input CSV overrides the flag per site. The pattern is recorded in `run.json`. Filter the
workbook on `review` before anyone relies on an acreage.

## Workbook

```
.venv_fema/Scripts/python.exe scripts/bulk/excel.py Outputs/<batch>/ --name <Title>
```

Writes `<Title>.xlsx` in the batch folder: **Sites** (one row per site, producer bands over
field names, absent cells grey / failed cells red, frozen site columns, autofilter), **Gaps**
(every absent/failed value with the source's note), **Sources** (one row per producer: source,
URL, vintage, method, fields, tallies), **Provenance** (full site × field table), **Run** (input
file + sha256, run time, counts, rejected rows, status meanings). Distances stay in metres.

## KMZ

```
.venv_fema/Scripts/python.exe scripts/bulk/kmz.py Outputs/<batch>/ --name <Title>
```

Writes `<Title>.kmz` in the batch folder, entirely from `data/cache` and the CMS reference files (no
network), so the map shows exactly what the workbook was computed from. Folders: **A** sites by
`group` with a full popup; **A2** site footprints — parcel boundary (green) or the square around the pin (blue),
the shape the `fp_*` columns were measured over; **B** HIFLD transmission within 5 km by voltage; **C** nearest line per
site + connector; **D** substations within 5 km; **E** FEMA SFHA polygons within 1 km; **F** NWI
polygons within 500 m; **G** schools / places of worship / nursing homes / hospitals within 1 mi;
**H** site-by-site verification ([group →] state → site, fly-to). E, F and G (flood, wetlands, neighbours) open switched on; A, A2, B, C, D and H open switched off — tick a folder to show it. E/F polygons
are clipped to 1.5 km around each site (a whole-river polygon otherwise dominates the file).
Windstream 200: 4.7 MB, 6,707 placemarks; folder C matches `Combined_3` on all 198 sites.

## Figures (chosen sites only)

```
.venv_fema/Scripts/python.exe scripts/bulk/figure.py Outputs/<batch>/ --only SITE_ID,SITE_ID [--layers flood,wetlands] [--views site,regional] [--buffer-m 400]
```

Four PNGs per named site, generalised from `out/site2_*.py`: **flood** (FEMA NFHL zones, unmapped
ground hatched) and **wetlands** (NWI polygons in greens/earth tones — never blue, which flood owns; Census water bodies
are outline-only on both) — always separate, because
riverine wetlands sit inside the floodplain and one layer hides the other — each at two zooms:
**site** (footprint fills ~65 % of the frame, never under 60 m tall) and **regional** (footprint + 400 m).
NAIP imagery and TIGERweb roads/hydro underneath. Footprint: solid dark red = parcel; dashed grey = the
square around the pin (grey = lower confidence). Each acreage panel prints the workbook's `fp_*` values. Writes
`<batch>/figures/<site_id>_{fema_flood,nwi_wetlands}_{site,regional}.png` (4800 × 2700, 300 dpi) and
`<site_id>_figures.json` (every query URL). NAIP is ~0.6 m, so the site view of a sub-acre parcel is
visibly pixelated — that is the imagery's limit, not a rendering fault.

**Basemap and audience.** The imagery is a pluggable provider (`basemap.py`); the overlays are identical
on any of them. `--basemap naip` (default; public domain, cleared for external use). `--audience external`
(default) refuses any provider not cleared for external use — so an internal-only source cannot reach a
sold report; `--audience internal` stamps "INTERNAL - NOT FOR DISTRIBUTION" on the map and footer and
writes `*_internal.png`. Every figure prints its provider's attribution. To add a source (e.g. KyFromAbove,
or a licensed internal one), write a fetch function and add a `Provider` to `basemap.PROVIDERS`.
Google Maps/Earth cannot be a provider: automated retrieval isn't permitted outside the paid Maps
Platform. The internal Google route is manual: open the batch KMZ in Google Earth Pro.
~20–120 s a site on first run (FEMA + NAIP), seconds from cache. Not for whole batches — the numbers are
already in the workbook; the picture is for the sites someone will look at. The map is drawn in UTM, so
the true-north square can sit a degree or two off the grid (grid convergence).

## Producers

| Producer | Fields | Source | Status |
|---|---|---|---|
| `transmission` | `tx_nearest_m/ft, tx_voltage_kv, tx_volt_class, tx_voltage_basis, tx_line_name, tx_line_id, tx_owner, tx_type, tx_status, tx_attrs_inferred, tx_100kv_*` | HIFLD US Electric Power Transmission Lines — ArcGIS mirror of the dataset DHS retired Aug 2025; data last edited 2025-08-26. 15 km query, exact point-to-segment distance. | **regression-proven** (below) |
| `substations` | `sub_nearest_m/name/type/max_kv/min_kv/kv_inferred/lines/status/source/id, sub_100kv_nearest_m/name/max_kv/lines, sub_230kv_nearest_m/name/max_kv, sub_count_within_10km, sub_max_kv_within_10km` | HIFLD Electric Substations — ArcGIS mirror, layer edited 2021-02-25 (older than the lines layer). 15 km query, straight-line distance. Per-row SOURCE (imagery / OpenStreetMap / state GIS) and MAX_INFER carried through; TAP = line tap. `-999999` normalised to null. | **validated** 10/10 vs Mireye Aug 11 (nearest distance within 0.3 %, nearest max kV, count within 10 km) |
| `flood` | `fema_determination, fema_flood_zone, fema_zone_subtype, fema_sfha, fema_static_bfe_ft, fema_dfirm_id, fema_firm_panel, fema_panel_effective, fema_nearest_sfha_m, fema_nearest_sfha_zone` | FEMA National Flood Hazard Layer: one L28 query for all zones within 1 km (geometry simplified to ~2 m) gives the zone under the pin and the nearest SFHA; L3 panel; L22 political (Area Not Included) and L0 availability only when no zone contains the pin. 2 FEMA calls per typical site. `fema_determination` = mapped / area_not_included / no_nfhl_data — an unmapped point is never reported as Zone X. | **validated** 10/10 vs Mireye Aug 11 zones |
| `wetlands` | `nwi_mapping_status, nwi_image_year, nwi_mapping_age_years, nwi_project, nwi_at_point, nwi_type_at_point, nwi_code_at_point, nwi_nearest_m, nwi_nearest_type, nwi_nearest_code, nwi_nearest_acres, nwi_count_within_500m, nwi_polygon_acres_within_500m` | USFWS National Wetlands Inventory: Wetlands, Wetlands_Status, Data_Source. Photointerpreted, not jurisdictional; acres are whole NWI polygons, not clipped. Unmapped areas carry a note on every zero. **Stale mapping:** `nwi_mapping_age_years` = run year − imagery year; when the imagery predates `STALE_BEFORE` (2000), every NWI value — and the footprint's `fp_nwi_*` — carries a `STALE MAPPING` note and the KMZ popup says so. A wetland hit from stale mapping is REVIEW against current imagery, never a knockout (BEREKYXA's 1984 "pond" is now tennis courts). Windstream 200: 110 of 197 dated sites are stale. | in use; no independent known answer yet |
| `metro` | `metro_urban_area_at_point, metro_urban_area_at_point_pop, metro_250k_nearest_name/m/pop, metro_1m_nearest_name/m/pop` | Census TIGERweb 2020 Urban Areas with POP100. Straight-line to the urban-area boundary (0 inside), not driving time; urban areas are built-up footprints, not MSAs. 300 km search. | geographic sanity checks (Sugar Land inside Houston 0 km, Baldwin GA 41 km to Atlanta, Riverside TX rural) |
| `datacenter` | `dc_nearest_m/name/city/state/networks/peeringdb_url, dc_hub_nearest_m/name/city/networks, dc_count_within_25km/50km, dc_max_networks_within_50km` | PeeringDB facility list (`Reference/peeringdb.kmz`, 1,353 US facilities), local, no network. Registered colo/IX facilities only — hyperscale and enterprise data centers are not listed. Hub = >= 20 networks (114 facilities). | geographic sanity checks |
| `parcel` | `parcel_county, parcel_county_geoid, parcel_source_scope, parcel_service_name, parcel_apn, parcel_owner, parcel_address, parcel_acres_gis, parcel_acres_stated_by_county, parcel_acres_input, parcel_apn_matches_input, parcel_owner_check, parcel_vertices, parcel_status` | Census TIGERweb county at the point, then the county (or statewide) parcel service from `data/reference/parcel-services.json`: statewide OH, FL, VA, IA (2017), TX (TxGIO StratMap, via `identify`; Dallas via DCAD), AR, OK (OKMaps WMS), NJ (NJOGIS composite, no owner names), plus county entries (each carries `reviewed` and `review_notes`). A returned polygon that does not contain the pin is used only within 2 m (a WMS pixel), with the distance in the note; a geocoded pin on the street centreline usually resolves nothing, because parcels stop at the right-of-way (BACKLOG approach D, address match, is the fix). There is no national parcel layer: an unregistered county returns `unresolved` naming the county, and `reference/discover_parcel_service.py` writes a reviewable proposal (OpenAddresses and NSGIC first, then searches). `parcel_owner_check` compares the owner of record with `--expected-owner`. Logic ported from tbdi-pasa `pasa_geo.core.parcel_at_point` / `pasa_geo.county`. | **29/29 acreages match** the Aug 2026 county-GIS results; Windstream 200: 130 resolved, 78 with the expected owner |
| `footprint` | `fp_basis, fp_acres, fp_flood_zones, fp_sfha_acres, fp_sfha_pct, fp_floodway_acres, fp_flood_unmapped_acres, fp_nwi_acres, fp_nwi_pct, fp_nwi_types` | The site shape — the parcel polygon from `parcel.resolve()` where one resolves, otherwise a north-aligned square centred on the pin: **200 m × 200 m** (9.88 ac), or a square of the input's `acres_stated` when that is larger (100 ac → 636 m), so a large site is not judged on a 10 ac patch; `fp_basis` names the size (`636 m square`) — intersected with FEMA NFHL zones and USFWS NWI polygons. Reuses the flood/wetlands producers' cached answers (no new calls unless a parcel reaches past 1 km / 500 m). Areas in a pin-centred Lambert equal-area projection. A failed parcel lookup is `failed`, never silently a square. Unmapped flood ground is reported as unmapped, never as Zone X. | Windstream 200: 130 parcel / 70 square; parcel `fp_acres` within 0.37 % of `parcel_acres_gis` (spherical vs ellipsoidal area); squares 200.00 m a side (geodesic check); finds SFHA in 13 footprints whose pin is outside it, NWI in 12 |
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
(built by `fixtures/make_windstream_fixture.py` from the broker workbook; no `group` column since
2026-09-23 — the broker's Interesting / Other split is no longer used, so the KMZ is one flat site list).

`fixtures/check_windstream_transmission.py Outputs/windstream-200/sites.csv` compares the
transmission producer against `fixtures/ws200_transmission_aug2026.csv` (a frozen copy of
`Outputs/Excel outputs/WS_Top200_Transmission_Distance.csv`, the Aug 2026 `tx_distance.py` output). **2026-09-21: 200/200 match** on line ID, distance,
owner, and the ≥100 kV line. One deliberate difference: the old CSV carried HIFLD's
`-999999` "not published" sentinel as a voltage; the producer normalizes it to null.

Every new producer gets the same treatment: a fixture run and a check against a known answer
before it is trusted.

## Requirements

Python 3.12. `python -m venv .venv_fema` then `.venv_fema/Scripts/pip install -r requirements-bulk.txt`
(openpyxl, pyproj, shapely for the run, workbook and KMZ; rasterio, geopandas, matplotlib, numpy for
`figure.py`; requests for the `reference/` tools). `requirements-fema.txt` is the older, larger
environment the Aug 2026 FEMA figure work used.

## Checks

- `check_sources.py` — every external source still answers, same layer, record count and fields as
  last recorded (43 today: producer layers, parcel registry, NFHL 28/3, figure's TIGERweb and NAIP, the
  PeeringDB export, the CMS files and whether CMS has a newer release) (`data/reference/source-baseline.json`; `--record` accepts reviewed drift). Run it
  before each batch.
- `fixtures/check_windstream_transmission.py Outputs/windstream-200/sites.csv` — transmission regression
  against the frozen Aug 2026 answer (`fixtures/ws200_transmission_aug2026.csv`); 200/200 on 2026-09-23.
- The other "validated" claims in the Producers table (substations, flood 10/10 vs Mireye; parcel 29/29)
  were one-off comparisons, not scripted checks.
