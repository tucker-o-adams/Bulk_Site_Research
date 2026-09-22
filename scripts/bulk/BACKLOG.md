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

**Result: 57 of the 102 unresolved Windstream sites return a parcel polygon at the point from free
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
| GA | 35 | 16 | 13 | County / regional-commission ArcGIS (Baldwin, Ben Hill, Berrien, Cook, Houston, Macon, Meriwether, Screven, Whitfield) and **Schneider's open WFS host** (Franklin, Grady, Habersham ×3). | 19 sites: Colquitt 2, Early, Murray, Pickens, Seminole, Telfair, Terrell, Towns, Union, Upson 2, Walton 2, White, Wilcox, Wilkinson, Walker (no polygon at point), Charlton (see caveats) |
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

So Georgia is **not** structurally closed, but it is county-by-county: the 19 GA sites still open
are in counties whose only public face is the qPublic portal.

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
| E | **Operator-owner check as a review aid**: for portfolio batches the owner field self-validates the parcel (49/57 hits). Flag hits whose owner is not the operator for a person to look at. | every portfolio batch | trivial | Dalark AR and Moore TX would be flagged |
| F | **Kentucky: ask DOR** for the statewide layer (108/120 counties already aggregated) — one email from Tucker. A formal records request needs a KY resident/business requester (HB 312). | up to 23 KY sites | an email | GIS council minutes |
| G | **GA qPublic-only tail**: survivor-only. Ask the county board of assessors for the parcel shapefile under O.C.G.A. 50-18-71 (native format, 3 business days) for the counties a flags cut leaves, or accept `point only`. | ≤19 GA sites | per-county email + possible fee | statute; economics above |

Recommended order: **A, B, E** first (they turn most of the remaining 102 into reviewable
proposals for a few hours' work); **C** after the Schneider terms call; **F** as a parallel
email; **G** only for survivors.

## Cross-cutting

- **Census batch geocoder** (`geocoding.geo.census.gov`, free, no key, 10k rows/request): the standard route for any address-only dataset (CMS hospitals, county assessor lists, client CSVs with addresses but no coordinates). **Built** as `scripts/bulk/geocode.py` (2026-09-21).
- **OSM Overpass** as universal fallback: free, crowd-sourced, rate-limited; a complement for coverage checks, never the sole source for a knockout field.
- **Frozen local copies** for any known batch area (FEMA county GDBs, NWI downloads): speed and vintage control. Do this when Ozinga's counties are known.
- Re-verify every primary endpoint at the start of each batch; `run.json` records failures, `LOCAL_ONLY.md` records what is cached.
