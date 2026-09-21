# Bulk pipeline backlog

Staged work and, per data source, the fallback to switch to if the primary
dies (HIFLD Open's retirement and two county parcel services vanishing in one
month are the reason this list exists). Free/public sources only.

Last reviewed 2026-09-21.

## Producers still to build

| # | Producer | Primary source (verified live 2026-09-21) | Fallback(s), in order |
|---|---|---|---|
| 1 | `neighbors` — housing density | Census TIGERweb Census 2020 Blocks: `HU100`, `POP100`, `AREALAND` within 500 m / 1 km | TIGERweb ACS block groups; Microsoft Building Footprints (structure count, free, static) |
| 2 | `neighbors` — public schools | NCES EDGE Public School Locations 2024-25 (102,178) | previous NCES vintage; OSM `amenity=school` |
| 3 | `neighbors` — private schools | NCES EDGE Private School Locations 2023-24 (22,510) | OSM `amenity=school` |
| 4 | `neighbors` — places of worship | HIFLD "All Places of Worship" mirror on a third-party ArcGIS org (XG15cJAlne2vxtgt), 254,742, edited 2025-03. **Fragile**: not a government host. Geocoded from IRS 501(c)(3) filings, so a mailing address may not be the building. | OSM `amenity=place_of_worship` (Overpass); IRS Exempt Organizations BMF (addresses) + Census batch geocoder |
| 5 | `neighbors` — nursing homes / retirement | CMS Provider Data Catalog "Provider Information" (id `4pq5-n9py`, ~14k, monthly, has `latitude`/`longitude` + `geocoding_footnote`). Download CSV once per run, query locally. | OSM `amenity=nursing_home` / `social_facility`; state licensing lists + Census geocoder |
| 6 | `neighbors` — hospitals | **No live free point layer** (HIFLD hub 404, `Hospitals_WFL1` needs a token, NASA NCCS mirror unresolvable). Plan: CMS "Hospital General Information" (id `xubh-q36u`, ~5k, addresses only) + **Census batch geocoder** (free, 10k addresses/request). | OSM `amenity=hospital`; HHS/ASPR emPOWER or state hospital lists + geocoder |
| 7 | `baxtel` — operational / under-construction / planned data centers within 5 & 10 mi | **Manual export only.** Baxtel terms prohibit scraping and commercial use of the Map Tool without written consent; data may be shared when Baxtel is cited. Mike exports the region's CSV (statuses: Operational, Construction, Planned, Prospective, Expansion, Land Bank, In Doubt, Withdrawn, Decommissioned; MW), file goes in `Reference/`, producer runs locally with `status: manual` and the citation. Open: confirm Mike's plan covers export; ask Baxtel in writing about data-room use. | none — this is proprietary data |
| 8 | `parcel` — boundary, area, owner, APN | County/state ArcGIS parcel services via a registry (tbdi-pasa `county-services.json` pattern). Ozinga expected to supply APN + acreage. | statewide services where they exist (VA, others); OSM has no parcels; mark `manual` with the county assessor URL |
| 9 | `excel` → `kmz` (interim deliverables, **next**) | openpyxl workbook; Windstream KMZ chain generalised | — |
| 9b | `flags` (**deferred** until Michael weighs in on thresholds, 2026-09-21) | rules as JSON | — |
| 10 | Demand / generation / congestion (Mike's method) | EIA-860 generators + EIA Energy Atlas substations; ISO queue data (PJM, MISO, SPP, ERCOT publish CSVs) | needs Mike's method first |

## Fallbacks for producers already built

| Producer | Primary | If it dies |
|---|---|---|
| `transmission` | HIFLD lines mirror `services2.arcgis.com/FiaPA4ga0iQKduv3` (retired dataset, frozen 2025-08) | **EIA U.S. Energy Atlas** transmission lines service (EIA is the origin of the HIFLD electric layers); OSM `power=line` with `voltage` tag |
| `substations` | HIFLD substations mirror `services5.arcgis.com/HDRa0B57OVrv2E1q` (edited 2021-02) | EIA Energy Atlas substations; OSM `power=substation` |
| `flood` | FEMA NFHL MapServer (slow, drops connections) | FEMA county NFHL GDB download → local query (also the speed fix for a known batch area); FEMA MSC product downloads |
| `wetlands` | USFWS NWI ArcGIS services | NWI state/watershed downloads (GDB/shapefile) → local query |
| `metro` | Census TIGERweb 2020 Urban Areas | Census TIGER/Line urban-area shapefile + gazetteer (local) |
| `datacenter` | PeeringDB KMZ in `Reference/` (registered colo/IX only) | PeeringDB API (free, rate-limited) for a fresh export; Baxtel export (manual) for hyperscale/enterprise |

## Cross-cutting

- **Census batch geocoder** (`geocoding.geo.census.gov`, free, no key, 10k rows/request): the standard route for any address-only dataset (CMS hospitals, county assessor lists, client CSVs with addresses but no coordinates). Build once as `geocode.py`, reuse.
- **OSM Overpass** as universal fallback: free, crowd-sourced, rate-limited; a complement for coverage checks, never the sole source for a knockout field.
- **Frozen local copies** for any known batch area (FEMA county GDBs, NWI downloads): speed and vintage control. Do this when Ozinga's counties are known.
- Re-verify every primary endpoint at the start of each batch; `run.json` records failures, `LOCAL_ONLY.md` records what is cached.
