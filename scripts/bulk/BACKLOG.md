# Bulk pipeline backlog

Staged work and, per data source, the fallback to switch to if the primary
dies (HIFLD Open's retirement and two county parcel services vanishing in one
month are the reason this list exists). Free/public sources only.

Last reviewed 2026-09-21.

## Phase 1 wrap-up (agreed 2026-09-23)

Scope to close Phase 1 before testing on a new site list: (1) stale-wetland-mapping handling, below;
(2) a very basic operating workflow draft (9d); (3) the loose ends from the Phase 1 project scan.
Explicitly **not** Phase 1: flags/thresholds (9b, held), demand / generation / congestion (10, Phase 2),
the parcel tail (handled separately).

**Stale-wetland-mapping handling.** Found at BEREKYXA: an NWI `PUBHh` "Freshwater Pond" (0.50 ac,
diked/impounded) drawn over what is now Berea College's tennis courts — NWI there is photointerpreted
from **1984** imagery (`nwi_image_year`) and never re-mapped. NWI vintage is often decades old.
1. **Workbook flag:** add `nwi_mapping_age_years` (run year − `nwi_image_year`) to the wetlands producer,
   and a stale-mapping note on every NWI value when older than a set cut-off (e.g. pre-2000 imagery), so
   it filters easily.
2. **Screening rule** (goes into the per-portfolio thresholds, 9b): a wetland hit from stale mapping is
   **REVIEW — confirm against current imagery**, never a knockout.

## Producers still to build

| # | Producer | Primary source (verified live 2026-09-21) | Fallback(s), in order |
|---|---|---|---|
| ~~1~~ | `housing` **built 2026-09-21** | Census TIGERweb Census 2020 Blocks: `HU100`, `POP100`, `AREALAND` within 500 m / 1 km | TIGERweb ACS block groups; Microsoft Building Footprints (structure count, free, static) |
| ~~2~~ | `schools` (public) **built 2026-09-21** | NCES EDGE Public School Locations 2024-25 (102,178) | previous NCES vintage; OSM `amenity=school` |
| ~~3~~ | `schools` (private) **built 2026-09-21** | NCES EDGE Private School Locations 2023-24 (22,510) | OSM `amenity=school` |
| ~~4~~ | `worship` **built 2026-09-21** | HIFLD "All Places of Worship" mirror on a third-party ArcGIS org (XG15cJAlne2vxtgt), 254,742, edited 2025-03. **Fragile**: not a government host. Geocoded from IRS 501(c)(3) filings, so a mailing address may not be the building. | OSM `amenity=place_of_worship` (Overpass); IRS Exempt Organizations BMF (addresses) + Census batch geocoder |
| ~~5~~ | `healthcare` (nursing homes) **built 2026-09-21** | CMS Provider Data Catalog "Provider Information" (id `4pq5-n9py`, ~14k, monthly, has `latitude`/`longitude` + `geocoding_footnote`). Download CSV once per run, query locally. | OSM `amenity=nursing_home` / `social_facility`; state licensing lists + Census geocoder |
| ~~6~~ | `healthcare` (hospitals) **built 2026-09-21**; 85 % geocoded, the rest need a second geocoder pass | **No live free point layer** (HIFLD hub 404, `Hospitals_WFL1` needs a token, NASA NCCS mirror unresolvable). Plan: CMS "Hospital General Information" (id `xubh-q36u`, ~5k, addresses only) + **Census batch geocoder** (free, 10k addresses/request). | OSM `amenity=hospital`; HHS/ASPR emPOWER or state hospital lists + geocoder |
| ~~7~~ | `baxtel` — **dropped as a producer 2026-09-23.** Mike's plan does not allow export, so Baxtel data will not be used directly in the pipeline or its outputs. Where it helps, a person opens the Baxtel map on the Baxtel site during review — that is a workflow step (9d), not a producer. Earlier notes kept for the record: | **Manual entry only — Michael's free account has no export (confirmed 2026-09-21).** A person reads the map per survivor site and types the nearby facilities into `baxtel_*` columns of the input CSV; the pipeline carries them with `status: manual` and the Baxtel citation. A regional snapshot for a batch's area is the practical unit, not per-site counts at 200 sites. Prior note: Baxtel terms prohibit scraping and commercial use of the Map Tool without written consent; data may be shared when Baxtel is cited. Mike exports the region's CSV (statuses: Operational, Construction, Planned, Prospective, Expansion, Land Bank, In Doubt, Withdrawn, Decommissioned; MW), file goes in `Reference/`, producer runs locally with `status: manual` and the citation. Open: confirm Mike's plan covers export; ask Baxtel in writing about data-room use. | none — this is proprietary data |
| ~~8~~ | `parcel` **built 2026-09-22**; registry covers OH+VA statewide and 12 counties (46/200 Windstream sites). Remaining: 117 counties need discovery + review | County/state ArcGIS parcel services via a registry (tbdi-pasa `county-services.json` pattern). Ozinga expected to supply APN + acreage. | statewide services where they exist (VA, others); OSM has no parcels; mark `manual` with the county assessor URL |
| ~~9~~ | `excel` **built 2026-09-21** (`excel.py`) | — | — |
| ~~9a~~ | `kmz` **built 2026-09-21** (`kmz.py`) | — | — |
| 9b | `flags` (**deferred** until Michael weighs in on thresholds, 2026-09-21). **Process rule (2026-09-23): thresholds are set per portfolio from the product requirement (target MW, product type, minimum size) and approved before any site is assessed — never tuned to the batch's own distribution.** `flags.py` refuses to run without an approved thresholds file for the batch and records its version in `run.json`. Portfolios differ: Windstream COs (median 0.35 ac, few-MW edge — distribution-voltage service, so nearest substation of any voltage + feeder headroom matter more than ≥100 kV) vs Ozinga (≥2 ac, mostly 2–20 ac, some 100–200+ ac, per Mike's Teams message) | rules as JSON, one per portfolio, approved before use | — |
| 9c | **Sharper imagery for site exhibits** (agreed 2026-09-23). NAIP is 60 cm in most states, so `figure.py`'s site view of a sub-acre parcel is pixelated — the source's limit, not ours (the site view already requests its own frame). Plug in free state ortho where it beats NAIP, per state, NAIP as the fallback | **KY:** KyFromAbove 3–6 in, free, Cloud-Optimized GeoTIFFs on AWS Open Data (`registry.opendata.aws/kyfromabove`); the state ImageServer `Ky_KYAPED_Imagery` is only 2012–14 and errored on one test export. **TX:** no — free statewide is 0.5–1 m; the 6-in Texas Imagery Service is limited to TX governments and their contractors. Check each new batch state. Record each source's licence before a sold report (NAIP is public domain). Google Earth / Maps is **not** an option for the pipeline: paid API, and commercial use is prohibited under Google's Geo Guidelines | NAIP (current) |
| 9d | **Operating workflow for the tool** (noted 2026-09-23; **a very basic draft is Phase 1 scope**, before the new-sites test). A defined sequence for running a portfolio end to end, with thresholds set *before* any site is assessed as an explicit step (see 9b) — e.g. intake → product/target-MW definition → thresholds approved → run → flags → survivors → parcels/exhibits. **Draft our own hypothesis of this workflow before sharing anything with Mike**; the thresholds template goes to him as part of it, not on its own | — | — |
| 9e | **Per-site layers in the KMZ verification folder** (considered 2026-09-23, on hold). Copy each site's flood (SFHA), wetland (NWI) and neighbour points into its folder H entry, off by default. ~1–2 h, all from cache. Measured cost: KMZ 4.8 → ~8.4 MB (doc.kml ~18 → ~32 MB) because sites barely share polygons (1,341 per-site vs 1,319 unique SFHA; 663 vs 632 NWI; 1,610 vs 1,065 neighbour points). Options: clip per-site copies to 500 m (~+1.5–2 MB, preferred); move polygons into H and drop E/F (no size change, loses the all-sites toggle); neighbours only (tiny) | — | — |
| 10 | Demand / generation / congestion (Mike's method) — **Phase 2** (2026-09-23) | EIA-860 generators + EIA Energy Atlas substations; ISO queue data (PJM, MISO, SPP, ERCOT publish CSVs) | needs Mike's method first |

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
carries OWN_NAME), **VA** (VGIN), **IA** (2017 snapshot), and since 2026-09-22 **TX** (TxGIO StratMap, 21
licensed counties excluded), **AR** (state GIS office), **OK** (OKMaps WMS). Counties: 13.
**Windstream 200: 130 resolve** (was 98) — see "Built 2026-09-22" under the prior-art research below.
The table that follows is the 2026-09-22 morning state, kept as the record of the sweep.

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

> **Corrected later on 2026-09-22 — see "Parcel prior-art research" below.** The verdict for TX, AR and
> OK was wrong: all three have free statewide layers the sweep could not see, because it searches
> ArcGIS Online and these states host on their own servers (TX identify-only MapServer, AR enterprise
> server, OK GeoServer WMS). The GA, KY and AL verdicts stand.

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

**Footprint (built 2026-09-23, Tucker's direction: don't block on parcels).** Every site now gets an
area to measure over: the parcel where one resolves, otherwise a 200 m square centred on the pin
(`producers/footprint.py`, `fp_*` columns). The `basis` column reads `parcel boundary` / `200 m square`.
KMZ folder A2 draws the shapes; `figure.py --only` makes PNG exhibits for chosen sites. When more
counties are registered, a rerun turns their squares into parcels with no other change.

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

## Parcel prior-art research (2026-09-22)

Researched how the problem is already solved before building more (kickoff:
`PARCEL_RESEARCH_KICKOFF.md`). Six research passes: commercial aggregators, open-source/civic prior
art, public-records law, hidden aggregation points, assessor-vendor structure, and the Georgia
qPublic measurement. Then every lead was probed at the actual unresolved sites.

**Result: 60 of the 102 unresolved Windstream sites return a parcel polygon at the point from free
sources; 49 of those carry an operator-looking owner** (CSL / Kinetic / Windstream / Valor / a
telephone co. / a `-PU` public-utility parcel number). Per-site evidence:
`data/reference/parcel-proposals/remaining-probe.csv`, produced by
`reference/probe_remaining_parcels.py`. **Nothing is registered** — every source below still needs
review before it goes into `parcel-services.json`.

| State | Left | Hit | Operator owner | Route that works | Still open |
|---|---|---|---|---|---|
| TX | 20 | 19 | 17 | **TxGIO StratMap Land Parcels**, statewide, 253/254 counties, tax year 2025, CC0. `feature.geographic.texas.gov/.../stratmap_land_parcels_48_most_recent/MapServer` — `/query` is disabled, **`/identify` works** (so `parcel.py` needs an identify mode). Returns rings, PROP_ID, OWNER_NAME. | Moore Co. polygons have no attributes (PROP_ID 0); Waterwood (Huntsville) no polygon |
| AR | 8 | 6 | 5 | **Arkansas GIS Office** `gis.arkansas.gov/.../Planning_Cadastre/FeatureServer/6`, 75/75 counties, 2.1M parcels, published 2026-04, plain query. | Crossett: point is in the street; the parcel 60 m away is CSL Arkansas at the site address (see D). Fordyce, Dalark: no operator parcel nearby |
| OK | 10 | 10 | 10 | **OKMaps `ogi_wms:Statewide_Parcels`** (GeoServer WMS `GetFeatureInfo`, JSON), 77/77 counties, compiled by Property Records Preservation LLC, county updates Feb–Aug 2026. Terms: "view only or through OGC WMS… not available for download" — per-site lookups fit; bulk harvest does not. INCOG (`map11.incog.org`) also serves Tulsa, Creek, Osage, Rogers, Wagoner as open FeatureServers (Creek/Osage/Rogers are 2022). | none |
| AL | 2 | 2 | 2 | County servers (Jefferson, St. Clair), both in OpenAddresses. KCS hosts open ArcGIS for ~18–22 AL counties (`web3..6.kcsgis.com/kcsgis/rest/services/<County>/`, and `al<NN>portal.kcsgis.com`). | none |
| GA | 35 | 19 | 13 | County / regional-commission ArcGIS (Baldwin, Ben Hill, Berrien, Cook, Houston, Macon, Meriwether, Screven, Whitfield; Telfair and Wilcox geometry-only via Heart of Georgia Altamaha RC; White via the City of Cleveland water map, `TAX_CLASS` U) and **Schneider's open WFS host** (Franklin, Grady, Habersham ×3). | 16 sites: Colquitt 2, Early, Murray, Pickens, Seminole, Terrell, Towns, Union, Upson 2, Walton 2, Wilkinson, Walker (no polygon at point), Charlton (see caveats) |
| KY | 27 | 4 | 2 | Schneider WFS (Bullitt ×2, Hardin), Madison Co. server | 23 sites in 18 counties. No public multi-county source covers them (below) |

### The Georgia measurement

**All 28 unresolved GA counties are Schneider customers** — 27 on qPublic, Whitfield on Beacon
(membership from the `qpublic.net/ga/gaassessors/` directory and county sites; qPublic itself was
never requested). Statewide, qPublic hosts ~153 of 159 GA counties; the CAMA behind it is WinGAP
(GA DOR / GAP Group, 147 counties).

| | Counties |
|---|---|
| qPublic only (nothing else public; Upson and Walton have county services but they are token-gated) | 15 |
| qPublic **and** an open county/RC ArcGIS layer (Grady 2017 and Macon 2018 are stale) | 8 |
| qPublic plus an unofficial or non-ArcGIS copy (Charlton, Habersham, Meriwether, Walker, Union/MapGuide) | 5 |
| open ArcGIS only | 0 |

**But "qPublic" does not mean "closed".** Schneider runs **`wfs.schneidercorp.com/arcgis/rest/services`**,
an open ArcGIS Server (no Cloudflare) with 126 `<County><ST>_WFS` services — GA 6, KY 7, IA 36, IN 27,
OK 1, others. Presumably the counties that buy Schneider's WFS add-on. It resolved Habersham (all 3
sites, current owners — the county the kickoff called qPublic-only), Franklin, Grady, the City of Perry
(which also covers Houston County sites), Bullitt and Hardin KY. **Decision for Tucker:** Schneider's
portal terms prohibit "automated data mining" and point bulk requests to support@schneidergis.com; the
WFS host is a machine-facing service a county paid to publish, and a per-site point query is not bulk
extraction — but that reading is ours, not Schneider's. Asking Schneider is cheap.

So Georgia is **not** structurally closed, but it is county-by-county: the 16 GA sites still open
are in counties whose only public face is the qPublic portal.

**Georgia regional commissions, fully scanned.** All 12 RCs publish into one shared AGOL org,
`services1.arcgis.com/Ug5xGQbHsD8zuZzM` (1,617 services; every layer scanned). Systematic parcel
hosting: **Heart of Georgia Altamaha** 17/17 counties on its own org
`services5.arcgis.com/HHvUPZ2XuLOAJxjR` (`<County>_County_Wide_View`, mostly 2025–26, mostly geometry +
acres with no owner); **Southern Georgia** 11/18 (`sgrcmaps.com/alma`, `valorgis.com`);
**Middle Georgia** 6/11; **River Valley** 9/16. Coastal 3; Northeast and Georgia Mountains a few
unmaintained project/city-utility layers (Georgia Mountains sells parcels at $85/hr). Three Rivers,
Northwest, CSRA, Southwest and Atlanta RC publish none. The Georgia GIS Clearinghouse
(`data.georgiaspatial.org`) is login-only. No license terms stated on any RC item.

### What the evidence says, by question

1. **Commercial aggregators** (Regrid, LightBox, ICE/Black Knight, ReportAll, ATTOM, CoreLogic) all say
   they collect **county by county**: download what counties publish, automated pulls where possible,
   phone/email and **pay** for the rest ("a nominal fee, or the total opposite of nominal" — Regrid).
   CoreLogic also buys from other aggregators. None claims FOIA as a method or admits scraping. Regrid
   refreshes 200–400 counties/month. **None publishes a per-county source list** — Regrid's verse
   table and `sourceurl` field are paid; its public Coverage Report (Google Sheet) has per-county
   `last_refresh` and fill rates but no source column. Regrid's free Living Atlas layer is image tiles
   only (no identify). Implication: the free ceiling is what counties and states publish themselves;
   the vendors' extra reach is money.
2. **Open-source prior art — the one we should have started from.** **OpenAddresses** v2 sources carry
   a `parcels` layer: 1,140 of 1,971 US source files have one (GA 94, AL 38, TX 24, KY 9, OK 7, AR 3),
   almost all ArcGIS REST URLs, in `github.com/openaddresses/openaddresses` under
   `sources/us/<st>/<county>.json`. It is a maintained, human-curated registry of exactly what our
   discovery hunts for. URLs rot: of 17 GA counties it lists for our sites, 7 were dead (AGOL
   "Invalid URL") and Habersham's roktech URL is gone. Processed outputs need a free OA account.
   Also: the **NSGIC 2025 Parcel Portal**
   (`services5.arcgis.com/fmKivMCp6fwbWbeE/.../2025_NSGIC_Parcel_Portal/FeatureServer/0`) — one polygon
   per county with `PRCLACCS` (Y/I/N), `VIEWURL`, `DLDURL`, `APIURL`, `STEWARD`; a point query gives
   the county's parcel status and endpoints. TX 253 "Y", AR 75 "Y", GA all "I" (internal), KY mostly
   "I", AL viewer URLs only. No free national compilation exists (Overture has no parcels theme; OSM
   excludes cadastre; ZTRAX ended 2023; the HUD national-parcel feasibility set is 2010–11 data).
3. **Public-records law.** All six states' statutes cover GIS data. **GA** (O.C.G.A. 50-18-71):
   native/export format on request, 3 business days, fees may include GIS cost recovery and counties
   may license against resale. **KY** (KRS 61.874): **requester must be a Kentucky resident or
   KY-operating business since HB 312 (2021)**; commercial-purpose requests can be charged
   creation cost. **AR**: citizens only. **TX, OK**: any person. **AL**: residents (2024 timelines
   added). Automation exists (MuckRock API files to agency lists at a per-request credit; OpenAddresses
   runs a 91-request MuckRock project) but no success-rate data was found. For the TBDI economics
   (1–2 sites per county) a records request is a survivor-only tool.
4. **Hidden aggregation points.** The wins were **state GIS offices that host outside AGOL** (TX, AR,
   OK — all three missed by the sweep) and **regional hosts**: Southern Georgia RC
   (`sgrcmaps.com/alma/...`), a GA regional AGOL org (`services1.arcgis.com/Ug5xGQbHsD8zuZzM`: Houston,
   Macon, Crawford, Monroe, Twiggs, Peach, …), Coastal RC (`maps.crc.ga.gov/crcarcgis`), INCOG (OK).
   **Kentucky:** the Department of Revenue has aggregated parcels from **108 of 120 counties** into a
   2.2M-parcel standardized layer (state GIS council minutes, Apr 2026) — **not public**;
   `kygisportalservices.ky.gov/.../Revenue` is token-gated, owner fields are stripped unless a county
   opts in. KY Area Development Districts publish almost nothing (Pennyrile: Todd; Gateway:
   Montgomery; KIPDA: Henry, Trimble; LINK-GIS: Campbell, Kenton, Pendleton — none of ours). KYTC's
   `KYTC_County_PVA_Availability_Web_Part` layer lists which counties have shared data (status only).
   TVA's parcel clip (UT-Chattanooga org) is a partial third-party copy whose query fails.
5. **Vendor structure.** Schneider qPublic/Beacon: ~153 GA, ~45–61 KY counties; portal behind
   Cloudflare; open WFS host for a paying subset (above). **KCS** (Alabama): ~22 counties, open ArcGIS,
   predictable hosts; its viewer has reCAPTCHA and a non-commercial/no-bulk disclaimer. **Flagship
   GIS** (~38 AL counties + Union GA): MapGuide, no REST, WFS lists nothing. **BIS Consultants**
   (TX): 155 CAD folders with open AGOL-proxied FeatureServers — redundant with StratMap.
   **DataScout/actDataScout** (AR/OK/LA), **ARCountyData** (AR), many KY PVA sites: bot-blocked.
   **Visual Lease Services** OK usassessor subdomains no longer resolve.

### Negative findings

- No aggregator discloses a per-county source list or county costs; no scraping lawsuits found.
- No free national or multi-state parcel compilation; no "awesome-parcels" list; the two GitHub
  endpoint harvesters found are small (mcp-atlas, 227 counties) or poor quality (parcel-index-sites:
  100-feature samples, wrong-state layers).
- No statewide parcel layer for GA or AL, public or state-held. KY's exists but is gated.
- Flagship GIS (AL) exposes no queryable service.
- `kygeonet.ky.gov/pva/<county>/` exists only for Webster; the older PVA viewers are gone.

### Caveats a reviewer must apply

- **Charlton GA**: the only open layer is a UGA-hosted copy of **CoreLogic** data — licensed
  commercial data; excluded from the probe. Do not register.
- **Meriwether GA**: published by an individual AGOL account; publisher unverified, though it
  returned `WINDSTREAM GEORGIA COMMUNICATIONS CORP` at the site.
- **Grady GA** (2017, no owner) and **Macon GA** (2018) are stale; state the vintage.
- Terms to respect: OKMaps per-site WMS only, no harvesting; KCS and Schneider disclaimers (above).
  One query per site, cached, is the posture for all three.

### Proposed approaches, grounded in the above (for Tucker to pick)

| # | Approach | Covers | Cost | Evidence |
|---|---|---|---|---|
| A | **Register TX, AR, OK statewide** after review. `parcel.py` needs two small modes: MapServer `identify` (TX) and WMS `GetFeatureInfo` (OK). AR is a plain query. | 35 sites now; every future batch in those states | small | probe: 35/38 hit, 32 operator owner |
| B | **Seed discovery from OpenAddresses + NSGIC** instead of AGOL search alone: for a county, read OA's `sources/us/<st>/<county>.json` parcels URL and the NSGIC portal row first, probe them, then fall back to the existing discovery. OA is a person-curated list, so it also beats our scoring guards on false positives. | GA/AL/KY/TX counties OA lists; status for all 3,000+ | small | OA URLs alone returned a parcel for 7 of our GA counties (one is the Charlton CoreLogic copy), Wagoner OK, Bullitt and Madison KY, and both AL counties |
| C | **Add known multi-county hosts** to host enumeration: `wfs.schneidercorp.com`, `sgrcmaps.com/alma`, the GA regional AGOL org, `maps.crc.ga.gov`, `map11.incog.org`, KCS `webN`/`al<NN>portal`. Schneider depends on the terms decision. | the GA/KY/AL counties on them | small | 5 GA + 3 KY sites came from the Schneider host alone (Habersham 3, Franklin, Grady; Bullitt 2, Hardin) |
| D | **Near-miss fallback**: when the point hits no parcel (or a road), take parcels within ~60 m and accept one only if its owner or situs address matches the site. Otherwise stay `point only`. | ROW-coordinate sites (Crossett AR) | small | 1 confirmed case |
| E | **Operator-owner check as a review aid**: for portfolio batches the owner field self-validates the parcel (49/60 hits). Flag hits whose owner is not the operator for a person to look at. | every portfolio batch | trivial | Dalark AR and Moore TX would be flagged |
| F | **Kentucky: ask DOR** for the statewide layer (108/120 counties already aggregated) — one email from Tucker. A formal records request needs a KY resident/business requester (HB 312). | up to 23 KY sites | an email | GIS council minutes |
| G | **GA qPublic-only tail**: survivor-only. Ask the county board of assessors for the parcel shapefile under O.C.G.A. 50-18-71 (native format, 3 business days) for the counties a flags cut leaves, or accept `point only`. | ≤16 GA sites | per-county email + possible fee | statute; economics above |

Recommended order: **A, B, E** first (they turn most of the remaining 102 into reviewable
proposals for a few hours' work); **C** after the Schneider terms call; **F** as a parallel
email; **G** only for survivors.

### Built 2026-09-22: A, B and E (Tucker approved all three)

**A — TX, AR, OK statewide registered.** `parcel.py` gained a `protocol` per service: `query` (default),
`identify` (TxGIO disables `/query`; Esri rings are converted to GeoJSON, and computed acreage matches
StratMap's own `GIS_AREA` to 0.001 ac), and `wms` (OKMaps `GetFeatureInfo`, one request per site). A
`vintage` field role gives each parcel its county's own date (TX `DATE_ACQ`, AR `camadate`, OK
`dataupdate`) instead of one statewide date. `check_sources.py` checks a WMS service at a stored
`check_point`, and now matches field names case-insensitively (TxGIO names them `prop_id`, identify
returns `PROP_ID` — it had reported "fields gone").

**TxGIO licence exclusion.** TxGIO's own item lists 21 counties as "licensed land parcel datasets available
to Texas governmental entities by special request" (Castro, Chambers, Cottle, Crockett, Crosby, Dawson,
Donley, Frio, Gonzales, Houston, Jack, Kerr, Knox, Mason, Menard, Oldham, Roberts, Shelby, Ward, Wichita,
Wilbarger). `identify` still returns them. The registry entry carries them under `exclude`, and a site
there comes back `unresolved: county excluded from the statewide layer` with the reason. Three Windstream
sites (Castro, Dawson, Kerr). Their appraisal districts' own BIS-hosted services (`<County>CADWebService`,
~138 CADs; Castro's is open) are the route if they matter.

**B — discovery starts from prior art.** `discover_parcel_service.py` now reads the county's OpenAddresses
source file (matched by the Census GEOID in its `coverage`, name first, full scan only as fallback) and
the state's `statewide.json`, probes their parcel URLs, uses OA's curated `pid` field as the APN guess, and
enumerates the host of every OA URL even when it is dead. It writes the county's **NSGIC 2025** row
(`PRCLACCS`, steward, view/download/API URLs) into the proposal and probes an API URL if there is one.
Berrien GA: the OA candidate ranks first (105) with `PARCEL_NO`. **Fixed a discovery bug found on the way:**
AGOL lists every hosted layer twice, as FeatureServer and MapServer, and the hosted MapServer answers
`/query` with "Invalid URL" — host enumeration was probing that copy and scoring real parcel layers as
broken (the "TVA clip query fails" and Charlton results above were this). Enumeration now keeps the
FeatureServer.

**E — `parcel_owner_check`.** `run.py --expected-owner REGEX` (or an `expected_owner` column) — see the
README. Windstream 200 with the Windstream pattern: **78 expected owner, 43 not checkable** (Ohio has no
owner field), **9 for review**:

| Site | County | Owner of record | What it probably means |
|---|---|---|---|
| BRFRFLXA | Suwannee FL | CITY OF BRANFORD JAIL | pin on the neighbouring parcel |
| DLRKARXA | Dallas AR | BULLOCK GREGGORY R & DIANNE | pin on the neighbouring parcel |
| HLCRIAXP | Dubuque IA | HEIDERSCHEIT ED | 2017 owner, or neighbouring parcel |
| KNVLIAXD | Marion IA | Feagins Dixie | 2017 owner, or neighbouring parcel |
| MORVIAIC | Appanoose IA | Spencer Elaine Ann & | 2017 owner, or neighbouring parcel |
| DUMSTXXA | Moore TX | (blank; PROP_ID 0) | StratMap has no attributes for Moore |
| DNSNIAXO, MRNGIAXO, WLBGIAXO | Lee, Iowa IA | (blank) | Iowa 2017 layer has no owner there |

It also caught a **registry error**: Stanly County NC (37167) mapped `owner` to `TaxPayerAddr1`, the
mailing address (Windstream's Little Rock HQ); corrected to `Name1` (`KINETIC ABS NC LLC`).

**Found after the first write-up** (not registered; none holds a Windstream site):
Alabama GeoHub `services7.arcgis.com/jF2q3LPxL7PETdYk/.../PARCELS_072026_1231_WFL1` (Montgomery, Elmore,
Autauga; one analyst's working copy, churns); H-GAC `gis.h-gac.com/.../RLUIS_24_v2_Current_Land_Use`
(8 Houston-area counties, 2024, no owner); an unofficial 2024 StratMap copy on a university AGOL account
(`Texas_Land_Parcels`, supports `/query`, 235/254 counties) — a fallback if TxGIO's identify goes away.

**Still open from the 102:** GA 16 sites (qPublic-only counties), KY 23, TX 4 (3 licensed + Waterwood),
AR 2 (Crossett — pin in the street, needs D; Fordyce), AL 2 (Jefferson and St. Clair county services
proven but not yet registered), plus the GA counties proven in `remaining-probe.csv` but not yet
registered (they need the per-county review). **Next:** register the proven GA/KY/AL county services
from `remaining-probe.csv` after review (Schneider-hosted ones wait on the terms call — C); D for
Crossett; F (Kentucky DOR email).

## Cross-cutting

- **Census batch geocoder** (`geocoding.geo.census.gov`, free, no key, 10k rows/request): the standard route for any address-only dataset (CMS hospitals, county assessor lists, client CSVs with addresses but no coordinates). **Built** as `scripts/bulk/geocode.py` (2026-09-21).
- **OSM Overpass** as universal fallback: free, crowd-sourced, rate-limited; a complement for coverage checks, never the sole source for a knockout field.
- **Frozen local copies** for any known batch area (FEMA county GDBs, NWI downloads): speed and vintage control. Do this when Ozinga's counties are known.
- Re-verify every primary endpoint at the start of each batch; `run.json` records failures, `LOCAL_ONLY.md` records what is cached.
