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

| State | Sites | Counties | Statewide sweep result (2026-09-22) |
|---|---|---|---|
| ~~IA~~ | ~~40~~ **0 left — registered 2026-09-22** | 29 | **Only `Iowa_Parcels_2017`** answers all four probe points (2.45M records, university-hosted 2017 snapshot). Confirmed by three independent methods now. The choice is: register it with its 2017 vintage stated, or go county-by-county. |
| GA | 35 | 28 | none — 21 candidate URLs checked, 5 probed |
| KY | 27 | 21 | none — 17 checked, 8 probed |
| TX | 20 | 19 | none — 27 checked, 6 probed |
| OK | 14 | 8 | none — 6 checked, 4 probed (Tulsa registered individually) |
| AR | 8 | 6 | none — 9 checked, 4 probed |
| AL | 2 | 2 | none — 9 checked, 6 probed |

**Sweep verdict: 1 statewide layer in 7 states, and it is a 2017 snapshot — registered 2026-09-22 after review (see below).** 97 candidate URLs
checked, 40 probed at four real sites each. The statewide shortcut that won Ohio (35 sites) and
Florida (8) does not exist for the six states holding 106 of the 154 unresolved sites. Those are
county-by-county or nothing. Re-run `sweep_statewide_parcels.py` for any new batch's states before
touching counties — it is cheap and the payoff when it hits is large.

**Discovery techniques, all built and measured 2026-09-22:**

| Technique | What it reaches |
|---|---|
| AGOL title search | services a publisher registered on ArcGIS Online under a parcel-ish title |
| **Web maps and apps** | a county that published a *viewer* but never registered a *service*: search its web maps/apps, read each item's `data`, harvest the `url` of every operational layer. This is what reached Tulsa County, whose parcels are served by INCOG, a regional council. |
| **Host enumeration** (`--server`, or the root of any URL found) | everything on a host, folders included — including the live service when a web map points at a stale one (Tulsa's map named `map8`, the live host is `map11`) |

The three **compose**: a web map reveals the host, enumeration finds the live layer on it.

**Scoring guards learned the hard way.** A probe hit only counts when the layer also carries
parcel attributes — `World_Imagery` and `StateBoundaries` answer a point query anywhere and were
out-ranking real parcel layers. Short field names (`pid`, `pin`, `apn`) match **exactly only**:
as a substring, `pid` matched `ZIP_ID` and would have registered a Boyd County KY **ZIP-code
layer** as parcels. Esri basemap hosts are excluded outright.

**Measured hit rate: roughly 3 of 10 counties**, and one of those three was the ZIP-code false
positive now rejected. Tulsa County is a genuine win (4 sites, unreachable by any other route).
**Discovery does not eliminate manual research on the tail** — it makes the search cheaper and
much safer, and a person still reviews every proposal.

**Graceful degradation (G, built 2026-09-22).** A site with no parcel boundary is not a blank row.
Every workbook now carries a frozen **`basis`** column — `parcel boundary` or `point only` — with a
legend saying what each means, and every KMZ site popup says the same. Windstream 200: 58 parcel
boundary, 142 point only. A "point only" site still has its flood zone, wetland distance, power,
metro and neighbour values; it simply has no acreage and no parcel-clipped figure, and says so.

Not deliverable as originally scoped: **there is no free national building-footprint service** to
estimate buildable area from — every Hub hit is a single county or city layer, and Microsoft's
footprints ship as per-state files, not a queryable endpoint. That half of G needs a download-and-host
step (see E). **BLM PLSS is verified working** as a free national service (township/section at any
point) but a section is 640 acres — useful as context for large rural parcels, useless for a
0.17-acre telecom exchange.

**Iowa 2017, registered deliberately (2026-09-22).** Tucker's call, with the trade stated: parcel
*boundaries* are the stable attribute, and a split since 2017 shows up as an over-large acreage
rather than a wrong location, so 2017 is fine for screening. Probed acreages are plausible for
telecom exchanges (0.02–0.97 ac, matching the Ohio and Florida profile). The service carries
`data_vintage` 2017-11-02 and **every value carries that vintage, not the review date** —
`parcel.py` now prefers `data_vintage` over `reviewed` for exactly this case.

`DEEDHOLDER` is 2017 ownership: it returns the CSL entities (e.g. `CSL IOWA SYSTEM LLC`), which are
Windstream-affiliated and consistent with the portfolio, but predate the late-2025 CSL→Kinetic
transfers the Aug 2026 county-record work found in Ohio. Treat owner from this layer as a 2017 fact,
never as current ownership.

**Economics.** At 1–2 sites per county, discovery + human review is poor value for a broker batch.
Treat `parcel` as a **survivor-only** step: run it after the flags cut a batch to ~20 sites, and
register only the counties those survivors are in. A statewide service, where one exists, is worth
finding first — Ohio and Florida each took minutes and covered 43 sites between them.

## Cross-cutting

- **Census batch geocoder** (`geocoding.geo.census.gov`, free, no key, 10k rows/request): the standard route for any address-only dataset (CMS hospitals, county assessor lists, client CSVs with addresses but no coordinates). **Built** as `scripts/bulk/geocode.py` (2026-09-21).
- **OSM Overpass** as universal fallback: free, crowd-sourced, rate-limited; a complement for coverage checks, never the sole source for a knockout field.
- **Frozen local copies** for any known batch area (FEMA county GDBs, NWI downloads): speed and vintage control. Do this when Ozinga's counties are known.
- Re-verify every primary endpoint at the start of each batch; `run.json` records failures, `LOCAL_ONLY.md` records what is cached.
