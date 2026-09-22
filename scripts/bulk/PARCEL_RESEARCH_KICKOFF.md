# Kickoff: automating nationwide parcel lookup — research prior art first

## The task

Find a way to resolve **the legal parcel under an arbitrary US coordinate** (boundary, area, APN,
owner) programmatically, at scale, using **free/public sources only**. This is the last unsolved
producer in the bulk site-research pipeline.

## Where things stand (read these first)

- `scripts/bulk/README.md` — the pipeline: CSV of sites in → per-site fields with provenance →
  Excel + KMZ out. Eleven producers, ten of them solved.
- `scripts/bulk/BACKLOG.md` — **the full record of what has been tried on parcels and why it
  failed.** Read this before trying anything; most obvious approaches are already tested.
- `scripts/bulk/producers/parcel.py`, `registry.py`, `data/reference/parcel-services.json` —
  the working producer and its per-county/statewide service registry.
- `scripts/bulk/reference/discover_parcel_service.py` — discovery: AGOL item search + ArcGIS Hub
  dataset index + web-map config harvesting + host enumeration, with scoring guards.
- `scripts/bulk/reference/sweep_statewide_parcels.py` — the statewide sweep.

**Current coverage:** 98 of 200 Windstream sites resolve. Solved by statewide services: OH, IA
(2017 snapshot), FL. Plus 13 individually registered counties. **102 sites remain across 83
counties in GA, KY, TX, OK, AR, AL** — six states the sweep proved have no free statewide layer.

**Key constraints and findings:**
- Free/public sources only, indefinitely. No Regrid, no paid APIs.
- There is no national public parcel layer; data lives with ~3,000 county assessors.
- **qPublic / Schneider** — the dominant assessor portal in GA and KY — is behind **Cloudflare bot
  protection**. Closed by policy and technical control. Do not attempt to bypass it.
- County services move and vanish: Habersham GA migrated roktech → qPublic (data still current);
  Union GA's endpoint now 400s.
- Discovery's measured hit rate on unregistered counties is roughly **3 in 10**.
- `check_sources.py` monitors every registered source for drift.

## The next step — and the reason for a fresh session

Everything above was derived **from first principles**: I hypothesised avenues and tested them.
That is probably the wrong order. **Start by researching how this problem is already solved.**

Concretely, go looking for:

1. **How commercial aggregators actually assemble nationwide parcel data** — Regrid/Loveland,
   ATTOM, Estated, CoreLogic, Lightbox, Dynamo Spatial, Mapping Solutions. Engineering blogs,
   investor/company disclosures, conference talks, job postings, API docs, methodology pages.
   *Do they license per county? Buy from a few state aggregators? Scrape? Use FOIA?*
2. **Open-source and civic-tech prior art** — anything in the spirit of OpenAddresses but for
   parcels; GitHub projects, Awesome-GIS lists, state-level harvesters, academic papers on
   national cadastral assembly.
3. **Public-records routes** — whether counties are obliged to supply GIS data on request, what
   state open-records law says, and whether anyone has automated the request itself.
4. **Aggregation points we may not know about** — NSGIC parcel initiatives, FEMA/USDA/Census
   programs that assembled parcels for another purpose, state DOT right-of-way datasets,
   university consortia, regional councils (this is how Tulsa was solved — INCOG hosts it).
5. **Per-vendor structure** — how many counties use each assessor-portal vendor, and which of
   those vendors expose an open ArcGIS REST endpoint rather than a gated portal.

Use web search and fetch freely. Report what the evidence actually says, including negative
findings. Then propose approaches grounded in that evidence, and we will pick what to build.

## The immediate measurable question

Before or alongside the research: **what share of the 28 unresolved Georgia counties sit on
qPublic versus their own ArcGIS?** If most are qPublic, Georgia is structurally closed and further
county-by-county effort there is wasted. That single measurement changes the strategy.

## Ground rules

- Honesty over optimism: a verified negative is a good result. Record it in `BACKLOG.md`.
- Never register a parcel service without a person reviewing it — a wrong parcel silently poisons
  buildable acres, the flood and wetland clips, and the map outline. See the ZIP-code near-miss in
  `BACKLOG.md`.
- Every value carries source, URL, vintage, method. Data vintage, not review date.
- Commit as you go; Tucker pushes.
