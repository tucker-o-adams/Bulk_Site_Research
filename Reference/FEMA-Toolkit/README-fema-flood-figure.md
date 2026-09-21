# FEMA Flood Hazard Figure Toolkit

Build a report-grade FEMA floodplain exhibit for a US site from public REST
services only — no manual downloads, no ArcGIS licence, no API keys.

Two sites are worked end to end as examples:

| Site | Input | Result |
|---|---|---|
| **Site 1** — TBDI Example Site, Adams County, CO | client KMZ polygon | 596.33 ac; **0.00 ac SFHA**; 71.9 % is *Area Not Included* (Rocky Mountain Arsenal) |
| **Site 2** — 1637 Green Mount Pkwy, Williamsburg, VA | street address | 33.38 ac; **0.068 ac Zone A SFHA**; 100 % NFHL-mapped |

Deliverables are `out/site1_fema_flood.png` and `out/site2/site2_fema_flood.png`
— 4800 × 2700 px, 300 dpi, 16:9, drops straight onto a slide or a letter page.

---

## Setup

Python 3.12 recommended (3.11–3.13 fine). From this directory:

```bash
py -3.12 -m venv .venv && .venv/Scripts/python.exe -m pip install -r requirements.txt
```

Playwright's browser is only needed for the NFHL Viewer screenshot (site 1,
step 6). Skip it if you only want figures:

```bash
.venv/Scripts/python.exe -m playwright install chromium
```

**Run every script from this directory** (the project root) — all paths inside
are relative to it:

```bash
.venv/Scripts/python.exe scripts/site2/site2_figure.py
```

### Network requirement

The four services below must be reachable. They are open and unauthenticated,
but corporate proxies and sandboxed containers often block them — see
`reference/network-test-prior-session.txt` for a case where all of them were
refused at the egress proxy. Test first:

```bash
.venv/Scripts/python.exe -c "import requests; [print(u.split('/')[2], requests.get(u, timeout=60).status_code) for u in ['https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer?f=json','https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPImagery/ImageServer?f=json','https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/State_County/MapServer?f=json','https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates?SingleLine=1600+Pennsylvania+Ave+NW+Washington+DC&f=json']]"
```

---

## Layout

```
input/          the client KMZ for site 1
scripts/site1/  step-by-step scripts, KMZ-polygon workflow
scripts/site2/  three consolidated scripts, address workflow
out/            site 1 data, figure, logs
out/site2/      site 2 data, figure, logs  (see out/site2/README.md)
results.md      full site-1 test report: what worked, what failed, timings
reference/      prior network test from a blocked environment
```

---

## Running a new site

**Site 2's three scripts are the better starting point** — they are consolidated,
parameterised, and were written after the lessons from site 1.

1. **`scripts/site2/site2_data.py`** — geocode → parcel → county → FEMA NFHL.
   Edit the top: `LON, LAT` and the parcel source. ~10 s.
2. **`scripts/site2/site2_imagery.py`** — NAIP mosaic + TIGERweb roads/hydro.
   Edit `CRS` to the right UTM zone. ~55 s.
3. **`scripts/site2/site2_figure.py`** — composes the PNG. Edit `CRS` and the
   title strings. ~30 s.

### Three things you must change per site

| What | Where | Why |
|---|---|---|
| **UTM zone** | `CRS` in scripts 2 and 3 | 32613 = UTM 13N (Colorado), 32618 = UTM 18N (Virginia). Wrong zone ⇒ distorted figure. Areas are always computed in EPSG:5070, which is national and needs no change. |
| **Parcel source** | `site2_data.py` | VGIN is **Virginia only**. Other states need their own parcel service, or a client KMZ (use `scripts/site1/step1.py` to parse it). |
| **Title / address strings** | side panel in `site2_figure.py` | not derived from the data |

### Getting a parcel boundary

- **Client KMZ** — best. `scripts/site1/step1.py` parses it.
- **Address** — geocode, then point-in-polygon against a parcel service.
  The **Census geocoder is free but misses new streets** (it failed on site 2);
  **Esri World Geocoding** `findAddressCandidates` worked at score 100 and needs
  no key for non-stored use. There is **no national public parcel service** —
  you need the state or county layer. Virginia: VGIN. Elsewhere, search
  `<county> ArcGIS REST parcels`.
- Always sanity-check the address→parcel link. Parcel layers rarely carry
  addresses, so the match rests on one geocode landing inside one polygon.

---

## What the FEMA data actually gives you

| Layer | ID | Field of interest |
|---|---|---|
| `S_FLD_HAZ_AR` | **28** | `FLD_ZONE`, `ZONE_SUBTY`, `SFHA_TF`, `STATIC_BFE` |
| `S_FIRM_PAN` | **3** | `FIRM_PAN`, `EFF_DATE`, `DFIRM_ID` |
| `S_POL_AR` | **22** | `POL_NAME1`, `CID`, **`ANI_TF`** |
| NFHL Availability | **0** | `STUDY_ID` — how much of the parcel is studied at all |

Base: `https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer`

**Layer 31 is `Subbasins`, not political areas** — a natural guess that is wrong.
Read the MapServer layer list rather than trusting a remembered ID.

### Gotchas these two sites surfaced

- **Missing flood-zone coverage is a finding, not a bug.** Site 1 returned one
  polygon covering 28 % of the parcel. The other 72 % was `ANI_TF='T'` on layer 22
  — Rocky Mountain Arsenal, an *Area Not Included* on the FIRM. Always
  cross-check layer 22 and layer 0 when the zones don't cover the parcel, and
  say so plainly: unmapped ≠ safe.
- **`STATIC_BFE = -9999`** means no Base Flood Elevation determined. On a Zone A
  (approximate study) that is normal and material — the BFE must be developed,
  not read off the FIRM.
- **FIRM panels are rectangles**, so neighbouring counties' DFIRMs overlap your
  parcel. Filter on `DFIRM_ID` matching the county GEOID from TIGERweb.
- **`hazards.fema.gov` resets TLS connections** intermittently
  (`WinError 10054`). Use a `requests.Session` with a browser UA and retries.
- **Layer 27** returned HTTP 400 on every attempt for a polygon the other
  layers accepted. Not needed; don't chase it.

### NAIP imagery

`exportImage` caps at **4000 × 4000 px**, so the scripts tile 2 × 2 at 3200 px
and mosaic. Target native resolution — 0.6 m for recent NAIP; requesting finer
just makes the server upsample. Get the acquisition date from a mosaic-dataset
query with `where=Category=1`; the overview records return nulls.

### Figure conventions

FEMA-standard: blue for SFHA (A/AE/AH/AO/V/VE), grey-blue hatch for 0.2 % shaded
X, light grey for minimal X, grey cross-hatch for ANI. Legend lists **only zones
present**. A small SFHA gets a leader callout — site 2's 0.068 ac sliver is about
28 px wide and would otherwise be missed.

---

## The NFHL Viewer screenshot (site 1, step 6)

Included for completeness, and because the comparison is instructive
(see `results.md` §7.3). Two things to know:

- The commonly cited URL `hazards.fema.gov/femaportal/wps/portal/NFHLWMS` is a
  **documentation page, not the viewer**. The viewer is `https://msc.fema.gov/nfhl`,
  which redirects to an ArcGIS WebAppBuilder app.
- Two modal dialogs load over the app and swallow every click. Dismiss all
  visible `OK` buttons in a loop before interacting.
- **The FIRMette print/export could not be made to work.** The widget reports
  `No preconfigured geoprocessing task available` and never issues a `GPServer`
  `submitJob`. Full diagnosis in `results.md` §6.

---

## Not included

- **`.venv/`** — rebuild it with the command above.
- **The rest of the Mireye project** (site-screening spreadsheets, Windstream
  KMZs, `CLAUDE.md`, `.claude/settings.local.json`). If you want the Mireye MCP
  site-screening instructions in this new directory, copy `CLAUDE.md` across
  yourself — it is about a different workflow and is deliberately left out.
- The two `naip_*.tif` files are **95 MB of this archive** and are fully
  regenerable in under a minute by re-running the imagery scripts, if you ever
  need a lighter copy.
