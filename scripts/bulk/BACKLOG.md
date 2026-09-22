# Bulk pipeline backlog

Staged work and, per data source, the fallback to switch to if the primary
dies (HIFLD Open's retirement and two county parcel services vanishing in one
month are the reason this list exists). Free/public sources only.

Last reviewed 2026-09-21.

## Producers still to build

| # | Producer | Primary source (verified live 2026-09-21) | Fallback(s), in order |
|---|---|---|---|
| ~~1~~ | `housing` **built 2026-09-21** | Census TIGERweb Census 2020 Blocks: `HU100`, `POP100`, `AREALAND` within 500 m / 1 km | TIGERweb ACS block groups; Microsoft Building Footprints (structure count, free, static) |
| ~~2~~ | `schools` (public) **built 2026-09-21** | NCES EDGE Public School Locations 2024-25 (102,178) | previous NCES vintage; OSM `amenity=school` |
| ~~3~~ | `schools` (private) **built 2026-09-21** | NCES EDGE Private School Locations 2023-24 (22,510) | OSM `amenity=school` |
| ~~4~~ | `worship` **built 2026-09-21** | HIFLD "All Places of Worship" mirror on a third-party ArcGIS org (XG15cJAlne2vxtgt), 254,742, edited 2025-03. **Fragile**: not a government host. Geocoded from IRS 501(c)(3) filings, so a mailing address may not be the building. | OSM `amenity=place_of_worship` (Overpass); IRS Exempt Organizations BMF (addresses) + Census batch geocoder |
| ~~5~~ | `healthcare` (nursing homes) **built 2026-09-21** | CMS Provider Data Catalog "Provider Information" (id `4pq5-n9py`, ~14k, monthly, has `latitude`/`longitude` + `geocoding_footnote`). Download CSV once per run, query locally. | OSM `amenity=nursing_home` / `social_facility`; state licensing lists + Census geocoder |
| ~~6~~ | `healthcare` (hospitals) **built 2026-09-21**; 85 % geocoded, the rest need a second geocoder pass | **No live free point layer** (HIFLD hub 404, `Hospitals_WFL1` needs a token, NASA NCCS mirror unresolvable). Plan: CMS "Hospital General Information" (id `xubh-q36u`, ~5k, addresses only) + **Census batch geocoder** (free, 10k addresses/request). | OSM `amenity=hospital`; HHS/ASPR emPOWER or state hospital lists + geocoder |
| 7 | `baxtel` — operational / under-construction / planned data centers within 5 & 10 mi | **Manual entry only — Michael's free account has no export (confirmed 2026-09-21).** A person reads the map per survivor site and types the nearby facilities into `baxtel_*` columns of the input CSV; the pipeline carries them with `status: manual` and the Baxtel citation. A regional snapshot for a batch's area is the practical unit, not per-site counts at 200 sites. Prior note: Baxtel terms prohibit scraping and commercial use of the Map Tool without written consent; data may be shared when Baxtel is cited. Mike exports the region's CSV (statuses: Operational, Construction, Planned, Prospective, Expansion, Land Bank, In Doubt, Withdrawn, Decommissioned; MW), file goes in `Reference/`, producer runs locally with `status: manual` and the citation. Open: confirm Mike's plan covers export; ask Baxtel in writing about data-room use. | none — this is proprietary data |
| ~~8~~ | `parcel` **built 2026-09-22**; registry covers OH+VA statewide and 12 counties (46/200 Windstream sites). Remaining: 117 counties need discovery + review | County/state ArcGIS parcel services via a registry (tbdi-pasa `county-services.json` pattern). Ozinga expected to supply APN + acreage. | statewide services where they exist (VA, others); OSM has no parcels; mark `manual` with the county assessor URL |
| ~~9~~ | `excel` **built 2026-09-21** (`excel.py`) | — | — |
| ~~9a~~ | `kmz` **built 2026-09-21** (`kmz.py`) | — | — |
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

## Parcel registry coverage (reviewed 2026-09-22)

Statewide: **OH** (Ohio Statewide Parcels, 6.3M), **FL** (FDOR Cadastral 2025, 10.8M, edited 2026-09-16,
carries OWN_NAME), **VA** (VGIN). Counties: 12. Together these resolve 54 of the Windstream 200.

Unresolved, by state — what each needs:

| State | Sites | Counties | Status |
|---|---|---|---|
| IA | 40 | 29 | **No current statewide source found.** Checked 2026-09-22: AGOL has only `Iowa_Parcels_2017` (a 2017 snapshot on a university account — rejected as a copy of unknown age); Iowa DOT's REST `Cadastre` and `Boundaries` folders enumerate zero services; the Iowa AGOL org (8lRhdTsQyJpO52F1, 264 services) has no parcel service. Next: ask a person to check geodata.iowa.gov (an ArcGIS Hub, not a REST root) or the Iowa Land Records / county auditors. 29 counties otherwise. |
| GA | 35 | 28 | county-by-county; 5 already registered from the Aug 2026 work |
| KY | 27 | 21 | county-by-county |
| TX | 20 | 19 | county-by-county (Dallas Co registered) |
| OK | 14 | 8 | county-by-county |
| AR | 8 | 6 | county-by-county |
| AL | 2 | 2 | county-by-county |

**Discovery techniques, and how far each got (tested 2026-09-22 on Tulsa County OK, 4 sites):**

| Technique | Status | Result on Tulsa |
|---|---|---|
| AGOL title search | built | one weak hit (`INCOG 911 Address Map`, owner `Josh060123`), probe 0 features |
| **Host enumeration** (`org_root` + `enumerate_services`, ported from tbdi-pasa) | built, `--server` flag | enumerated the one host AGOL gave (7 services); no parcel layer answered |
| **Web-app config** — read an AGOL web map/app's `data` and harvest the `url` of every operational layer | **lead, not built** | found `https://map9.incog.org/arcgis9wa/rest/services/Parcels_TulsaCo/FeatureServer`, a real regional-council host AGOL title search never surfaces — but it returns 404 from here (stale reference in the app, or internal-only). Worth building: a county that publishes a viewer but never registered a service is the common case. |

Tulsa remains unresolved after all three. **The ports improved the tooling; they did not crack the tail.**

**Economics.** At 1–2 sites per county, discovery + human review is poor value for a broker batch.
Treat `parcel` as a **survivor-only** step: run it after the flags cut a batch to ~20 sites, and
register only the counties those survivors are in. A statewide service, where one exists, is worth
finding first — Ohio and Florida each took minutes and covered 43 sites between them.

## Cross-cutting

- **Census batch geocoder** (`geocoding.geo.census.gov`, free, no key, 10k rows/request): the standard route for any address-only dataset (CMS hospitals, county assessor lists, client CSVs with addresses but no coordinates). **Built** as `scripts/bulk/geocode.py` (2026-09-21).
- **OSM Overpass** as universal fallback: free, crowd-sourced, rate-limited; a complement for coverage checks, never the sole source for a knockout field.
- **Frozen local copies** for any known batch area (FEMA county GDBs, NWI downloads): speed and vintage control. Do this when Ozinga's counties are known.
- Re-verify every primary endpoint at the start of each batch; `run.json` records failures, `LOCAL_ONLY.md` records what is cached.
