# FEMA Floodplain Figure — End-to-End Environment Test

**Site:** TBDI Example Site 1 — polygon from `Example kmz/TBDI Example Site 1.kmz`
**Run date:** 2026-08-26 (all service queries this date)
**Machine:** local Windows 11 session, Python 3.12 venv at `.venv_fema/`
**All outputs:** `./out/`

**Bottom line:** every step produced real, sourced output except the NFHL Viewer's
print/export, which failed. The figure in `out/site1_fema_flood.png` is built
entirely from public REST services with no manual downloads.

---

## Step 0 — Network and tools

### Outbound GET tests

| Endpoint | HTTP status | Latency |
|---|---|---|
| `https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer?f=json` | **200** | 0.9 s |
| `https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPImagery/ImageServer?f=json` | **200** | 0.2 s |
| `https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/State_County/MapServer?f=json` | **200** | 0.3 s |
| `https://epqs.nationalmap.gov/v1/json?x=-104.895&y=39.820&units=Feet` | **200** | 0.5 s |

All four reachable, no proxy interference.

> A pre-existing `network-test.txt` in this folder records these same hosts as
> **blocked** (proxy `403 Forbidden`, "no rule or allowlist entry allows host")
> from a Claude Cowork cloud container and from a desktop VM behind an `srt`
> proxy. That restriction does **not** apply to this local session. The
> conclusion of this test is therefore environment-specific: the work is
> possible locally, not from those two sandboxes.

### Packages

| Package | Version | Result |
|---|---|---|
| geopandas | 1.1.4 | OK |
| shapely | 2.1.2 | OK |
| pyproj | 3.7.2 | OK |
| requests | 2.34.2 | OK |
| rasterio | 1.5.1 | OK |
| matplotlib | 3.11.1 | OK |
| simplekml | 1.3.2 | OK |
| playwright | 1.62.0 | OK |
| Chromium (playwright `chromium-1234`) | — | OK — headless launch + navigation verified |

Nothing failed. Python was not on `PATH` (the Windows Store `python.exe` shim
errors out); resolved with `py -0p` and using the 3.12 interpreter directly.

---

## Step 1 — Parcel and county

### 1.1 Parcel from KMZ

The KMZ contains one `doc.kml` with one polygon placemark
(*"TBDI Example Site 596 Acres"*) and one point placemark
(*"TBDI Example Site 1"*, −104.8951065, 39.8201258). The **polygon** was used.

| Value | Result |
|---|---|
| Vertices (exterior ring, closing duplicate excluded) | **16** |
| Interior rings | 0 |
| Centroid (lon, lat, WGS84) | **−104.8936070, 39.8199842** |
| Bounding box (lon/lat) | −104.9029468, 39.8129820 → −104.8845421, 39.8272026 |
| Area, EPSG:5070 (Albers CONUS) | **2,413,252.39 m² = 596.328 acres** |

The computed 596.33 ac matches the "596 Acres" in the placemark name to 0.06%.

### 1.2 County by spatial query

Queried TIGERweb `State_County/MapServer/**1**` (*Counties*, Jan-1-2025
vintage) with the parcel polygon, `esriSpatialRelIntersects`, `inSR=4326`.
**Exactly one** county returned:

| GEOID | County | STATE / COUNTY FIPS | Parcel area in county |
|---|---|---|---|
| **08001** | **Adams County, Colorado** | 08 / 001 | **100.00 %** |

No county was inferred from coordinates or any other source.

---

## Step 2 — Flood hazard by REST query

### 2.1 Flood hazard zones — layer 28 `S_FLD_HAZ_AR`

`returnCountOnly` confirmed **exactly 1** feature intersects the parcel
(`maxRecordCount` is 2000, so this is not a paging truncation).

| Zone | `ZONE_SUBTY` | `SFHA_TF` | `STATIC_BFE` | `DFIRM_ID` | Acres in parcel | % of parcel |
|---|---|---|---|---|---|---|
| **X** | AREA OF MINIMAL FLOOD HAZARD | F | −9999 (no BFE) | 08001C | **167.794** | **28.14 %** |
| *(derived, see 2.3)* **AREA NOT INCLUDED** | Rocky Mountain Arsenal | F | — | 08001C | **428.534** | **71.86 %** |

**Total SFHA acres within the parcel: 0.000 ac (0.00 %).** No Zone A, AE, AH,
AO, V or VE polygon touches the parcel, and no 0.2 %-annual-chance (shaded X)
area either.

**The important finding is the 71.86 % that has no flood-zone polygon at all.**
That is not a query error — it is Rocky Mountain Arsenal, which FEMA carries as
an **Area Not Included (ANI)** on the effective FIRM. Confirmed three ways:

1. `S_POL_AR` (§2.3) returns `ROCKY MOUNTAIN ARSENAL / ADAMS COUNTY` with
   `ANI_TF = **T**` covering 71.862 % of the parcel — matching the Zone X
   complement to five decimal places.
2. NFHL Availability (layer 0) reports study `08001C` covering only **37.13 %**
   of the parcel.
3. The NFHL Viewer (Step 6) labels that ground
   *"ROCKY MOUNTAIN ARSENAL / ADAMS COUNTY / (AREA NOT INCLUDED)"* and labels
   panel 08001C0609H **"Not Printed."**

Practical consequence for a site assessment: **0 acres of SFHA, but only 28 %
of the site carries an effective FEMA flood determination at all.** The
remaining 428.5 acres are unmapped and would need a site-specific hydrology
study, not a FIRM citation.

### 2.2 FIRM panels — layer 3 `S_FIRM_PAN`

Three panels intersect the parcel geometry (panels are rectangular quads, so
neighbouring counties' DFIRMs overlap):

| `DFIRM_ID` | `FIRM_PAN` | `EFF_DATE` | Kept? |
|---|---|---|---|
| **08001C** | **08001C0609H** | **2007-03-05** | **KEPT — matches county 08001** |
| 08005C | 08005C0025K | 2010-12-17 | dropped (Arapahoe Co. DFIRM) |
| 080046 | 0800460084G | 2005-11-17 | dropped (community DFIRM) |

### 2.3 Political areas — layer **22** `S_POL_AR`

> **Layer 31 is `Subbasins`, not political areas.** The MapServer layer list
> gives `S_POL_AR` as **layer 22** (*"Political Jurisdictions"*). Layer 22 was
> used.

| `POL_NAME1` | `POL_NAME2` | `CID` | `ANI_TF` | % of parcel |
|---|---|---|---|---|
| **ROCKY MOUNTAIN ARSENAL** | ADAMS COUNTY | 08FED | **T** | 71.862 % |
| **CITY OF COMMERCE CITY** | — | 080006 | F | 28.138 % |

### 2.4 Files

`out/site1_fema.gpkg` (EPSG:4326) — layers:

| Layer | Features | Geometry |
|---|---|---|
| `parcel` | 1 | Polygon |
| `county` | 1 | Polygon |
| `flood_zones_clipped` | 1 | Polygon |
| `flood_zones_raw` | 1 | Polygon |
| `firm_panels` | 1 | Polygon |
| `political_areas` | 2 | Polygon |
| `area_not_included` | 1 | Polygon |
| `roads_secondary` / `roads_local` / `railroads` | 11 / 278 / 4 | LineString |
| `hydro_linear` / `hydro_areal` | 4 / 5 | LineString / Polygon |

`out/site1_fema.kmz` — zones, ANI, panel, parcel (Google-Earth-ready).

### Failures in Step 2

* **Layer 22, first attempt:** `requests.exceptions.ConnectionError:
  ('Connection aborted.', ConnectionResetError(10054, 'An existing connection
  was forcibly closed by the remote host'))` — a TLS handshake reset at
  `hazards.fema.gov`. Succeeded on retry with a `requests.Session` and a
  browser `User-Agent`. Transient, not systematic.
* **Layer 27 (`Flood Hazard Boundaries`, optional context):** returned
  `{"code": 400, "message": "Failed to execute query.", "details": []}` on
  **all 5 attempts** with the same polygon that layers 3, 22, 28 and 0 accepted.
  Not required for the deliverable; recorded and skipped.

---

## Step 3 — NAIP aerial imagery by REST

`exportImage` on the USGS NAIP ImageServer worked first try.

* First request: 2400 × 1350 px, **2.361 m/px** — usable but soft for a
  full-slide figure.
* Server caps at **4000 × 4000 px**, so the extent was tiled **2 × 2** at
  3200 px per tile and mosaicked to **6400 × 3600 px = 0.885 m/px** (the four
  tiles were verified to hold different pixel data, not a repeated response).

| Item | Value |
|---|---|
| Request URL (single-tile form) | `https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPImagery/ImageServer/exportImage?bbox=506260.914359,4406202.077642,511926.391018,4409388.908263&bboxSR=32613&imageSR=32613&size=2400,1350&format=tiff&f=image&adjustAspectRatio=false` |
| Extent (EPSG:32613, UTM 13N) | 506260.914, 4406202.078 → 511926.391, 4409388.908 (5665 × 3187 m) |
| Margin | parcel bbox + 0.5 mi (804.7 m), padded to 16:9 |
| Final raster | `out/naip_site1.tif`, 6400 × 3600, 3-band uint8, EPSG:32613, deflate, 46.1 MB |
| Resolution | **0.885 m/px** |
| **Imagery date** | **2019-08-03** |
| Source scene | `m_3910409_ne_13_060_20190803`, 0.6 m, USDA-FSA-APFO (mosaic dataset query, `Category=1`) |

Format `tiff` was accepted — no PNG fallback needed. The service returns
georeferenced TIFF that `rasterio` opened directly with correct CRS and
transform.

---

## Step 4 — Context lines by REST

TIGERweb, same extent, envelope query. Layer ids taken from each MapServer's
layer list.

| Service / layer | Features | Named examples |
|---|---|---|
| `Transportation/2` Primary Roads | **0** | *(none in extent — a real result, not a failure)* |
| `Transportation/6` Secondary Roads | 11 | E 74th Ave, State Hwy 2, State Hwy 224, US Hwy 6, US Hwy 85, Vasquez Blvd |
| `Transportation/8` Local Roads | 278 | Brighton Blvd, Quebec St, E 72nd Ave, Olive St, … (112 distinct names) |
| `Transportation/9` Railroads | 4 | BNSF, Union Pacific RR |
| `Hydro/0` Linear Hydrography | 4 | Sand Crk Lateral Ditch |
| `Hydro/1` Areal Hydrography | 5 | *(all unnamed)* |

All written to `out/site1_fema.gpkg`. No failures.

---

## Step 5 — Composed figure

`out/site1_fema_flood.png` — **4800 × 2700 px, 300 dpi, 16:9, 16.1 MB.**

Contains: NAIP base; Zone X in light grey and the ANI area in grey cross-hatch
at 42–45 % alpha (FEMA convention — no SFHA blue is drawn because none is
present); parcel in a heavy dark-red line with a white casing; named roads,
railroads and hydrography; FIRM panel boundary dashed cyan with a
panel-number + effective-date label; legend listing **only the zones present**;
a feet scale bar with the slide-scale note; a north arrow; and a full source
block naming each service, the NAIP acquisition date, the query date and both
projections.

### Inspection of the rendered PNG

I opened the PNG and reviewed it at full size and at 3 crops.

* **Parcel centred** — yes. It occupies roughly the middle third of the map
  panel, horizontally and vertically, with the 0.5-mile context margin intact
  on all sides.
* **Imagery legible** — yes. At 0.885 m/px, individual houses, the Adams City
  High School track and stadium, farm tracks inside the Arsenal and the
  Union Pacific alignment all resolve cleanly.
* **Labels readable at slide size** — yes for the parcel callout, the FIRM
  panel label, the arterials and the legend. The local-road labels (5.6 pt at
  300 dpi ≈ 1.9 mm on a projected slide) are readable on a printed page and on
  a laptop, but marginal from the back of a conference room; they are context,
  not the message, so this is acceptable.
* **Two defects were found and fixed**: the scale bar and north arrow had
  oversized white backing boxes that read as blank patches, and the
  slide-scale note fell outside the map frame. Both corrected and re-rendered.
* **Comparable to a FEMA NFHL Viewer screenshot** — it is better on every axis
  that matters for a report (see §7.3), but it does **not** reproduce the
  FIRM's cartographic furniture: no BFE lines, cross-sections, or
  profile baselines (none exist here), and no FIRMette title block.

---

## Step 6 — NFHL Viewer by browser

**The URL given in the brief is a documentation page, not the viewer.**
`https://hazards.fema.gov/femaportal/wps/portal/NFHLWMS` returns HTTP 200 with
title `NOPAGETAB_NFHLWMS` — a Risk MAP portal page about the NFHL web services.
It does not redirect. It *contains* a link labelled "NFHL Viewer" →
`https://msc.fema.gov/nfhl`, which **does** redirect to
`https://hazards-fema.maps.arcgis.com/apps/webappviewer/index.html?id=8b0adb51996444d4879338b5529aa9cd`.
That link was followed, as instructed.

| Action | Result | Time |
|---|---|---|
| Load entry URL, find and follow the viewer link | **worked** | 9 s |
| Load viewer, wait for map render | **worked** | 41 s |
| Dismiss blocking modals | **worked** (see below) | ~18 s |
| Search parcel centroid coordinates | **worked** — typed `39.819984, -104.893607`, Enter, 1 result popup returned | 18 s |
| Zoom/centre so the parcel area fills ~the centre third | **worked** — `&center=lon,lat&level=16` gives a 4.6 km wide frame around a 1.57 km parcel (≈34 % of frame width) | — |
| Full-page screenshot → `out/nfhl_viewer_screenshot.png` (2020 × 1087, 2.8 MB) | **worked** | 0.6 s |
| **NFHL Print Tool export** | **FAILED** | 302 s spent |

**Step 6 total across all attempts: ~14 minutes.**

### The blocker that cost the first two runs

Two stacked modal dialogs sit over the app on load and intercept every click:
a *"The layer, Coastal Barrier Resources System (US FWS), cannot be added"*
alert, and the *"Welcome to the National Flood Hazard Layer (NFHL) Viewer!"*
splash. Playwright resolved the target locators but every `click()` timed out:

```
TimeoutError: Locator.click: Timeout 90000ms exceeded.
  - waiting for locator("#esri_dijit_Search_0_input")
    - locator resolved to <input value="" type="text" tabindex="0" ...>
```

Workaround: click every visible `OK` button in a loop before doing anything
else (3 dismissals per load).

### The print/export failure — exact errors

The widget's submit button is labelled **"Run"**, not "Execute" as its own
instructions claim. It was located by measuring its bounding box
(x = 348, y = 560) and clicked directly.

1. The widget itself reported: **`No preconfigured geoprocessing task
   available.`**
2. Clicking Run produced no download:
   `TimeoutError: Timeout 180000ms exceeded while waiting for event "download"`
3. After a further 60 s wait, no PDF/PNG link appeared anywhere in the DOM
   (`pdf/img links: []`).
4. Network capture shows the app only ever called the **FIRMette MapServer**
   (`hazards.fema.gov/arcgis/rest/services/FIRMette/NFHLREST_FIRMette/MapServer/*/query`,
   all HTTP 200) — it **never** issued a `GPServer` `submitJob`, which is what
   actually renders a FIRMette.
5. Setting the widget's lat/lon inputs directly also failed —
   `Page.fill: Timeout 10000ms exceeded` on `#dijit_form_NumberTextBox_0`
   (which held the app default `29.877 / -81.2837`); the Dojo NumberTextBox is
   not writable through a plain fill.

There is also a **substantive** reason a FIRMette may be unobtainable here,
independent of the automation: the viewer labels panel **08001C0609H "Not
Printed"**, and its identify popup states *"Download a graphic of the map
(available if map panel is printed)."* FEMA has no printed FIRM panel over the
Arsenal, so there may be no FIRMette to generate at this location at all. I
could not separate the two causes from outside the service.

Evidence retained: `out/nfhl_print_tool_panel.png` (panel open, FIRMETTE/PDF
selected), `out/nfhl_print_tool_after_run.png` (state after Run), and the full
logs in `out/step6_print2_log.txt`.

---

## 7. Results

### 7.1 Step summary

| Step | Worked | Time | Files produced |
|---|---|---|---|
| 0 — Network & tools | **yes** | ~3 min | `.venv_fema/` (outside `out/`) |
| 1 — Parcel & county | **yes** | ~2 s of service time | `site1.kml`, `step1.json`, `step1_county.json`, `site1_fema.gpkg` (`parcel`, `county`) |
| 2 — Flood hazard REST | **partial** | ~35 s | `step2_zone_summary.csv`, `step2_zones.csv`, `step2b_log.txt`, `site1_fema.gpkg` (+5 layers), `site1_fema.kmz` |
| 3 — NAIP imagery | **yes** | ~2 min 15 s | `naip_site1.tif` (46.1 MB), `step3.json`, `step3b.json` |
| 4 — Context lines | **yes** | 2.9 s | `site1_fema.gpkg` (+5 layers), `step4_log.txt` |
| 5 — Compose figure | **yes** | ~75 s (3 renders) | `site1_fema_flood.png` (4800×2700, 300 dpi) |
| 6 — Viewer screenshot | **partial** | ~14 min | `nfhl_viewer_screenshot.png`, `nfhl_print_tool_panel.png`, `nfhl_print_tool_after_run.png`, `step6*.json`, `step6*_log.txt` |

Step 2 is *partial* only because layer 27 (optional context) returned HTTP 400
on every attempt. Every required value was obtained.
Step 6 is *partial* because the print/export failed; search, render, zoom and
screenshot all worked.

### 7.2 Values with sources

Query date for every row: **2026-08-26**.

| Value | Result | Source |
|---|---|---|
| Polygon vertices | 16 | `Example kmz/TBDI Example Site 1.kmz` → `doc.kml`, polygon placemark "TBDI Example Site 596 Acres" |
| Centroid (lon, lat) | −104.8936070, 39.8199842 | same KMZ, computed with shapely |
| Parcel area | 2,413,252.39 m² = **596.328 ac** | same KMZ, area computed in EPSG:5070 |
| County | **Adams County, CO — GEOID 08001**, 100.00 % of parcel | `https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/State_County/MapServer/1/query` (Counties, 2025 vintage), `esriSpatialRelIntersects`, parcel polygon |
| Flood zone X (minimal) | 167.794 ac = 28.14 % | `https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28/query` (`S_FLD_HAZ_AR`) |
| `ZONE_SUBTY` | AREA OF MINIMAL FLOOD HAZARD | same |
| `SFHA_TF` / `STATIC_BFE` | F / −9999 (no BFE) | same |
| `DFIRM_ID` | 08001C | same |
| **Total SFHA** | **0.000 ac (0.00 %)** | same (no A/AE/AH/AO/V/VE feature intersects) |
| Area Not Included | 428.534 ac = 71.86 % | derived: parcel ∩ (`S_POL_AR` where `ANI_TF='T'`) from `https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/22/query` |
| FIRM panel (county-matched) | **08001C0609H**, eff. **2007-03-05**, DFIRM 08001C | `https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/3/query` (`S_FIRM_PAN`) |
| Other panels intersecting (dropped) | 08005C0025K eff. 2010-12-17; 0800460084G eff. 2005-11-17 | same |
| `POL_NAME1` values | ROCKY MOUNTAIN ARSENAL (`ANI_TF=T`, CID 08FED, 71.862 %); CITY OF COMMERCE CITY (CID 080006, 28.138 %) | `.../MapServer/22/query` (`S_POL_AR`) |
| NFHL study coverage of parcel | study 08001C, 37.13 % | `.../MapServer/0/query` (NFHL Availability) |
| Imagery date | **2019-08-03**, 0.6 m, `m_3910409_ne_13_060_20190803`, USDA-FSA-APFO | `https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPImagery/ImageServer/query?where=Category=1` |
| Imagery extent / resolution | EPSG:32613 506260.914,4406202.078→511926.391,4409388.908; 6400×3600 px; 0.885 m/px | `.../ImageServer/exportImage` |
| Roads / railroads / hydro | 11 / 278 / 4 / 4 / 5 features | `https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Transportation/MapServer/{6,8,9}/query` and `.../Hydro/MapServer/{0,1}/query` |
| Projections | figure EPSG:32613 (UTM 13N); areas EPSG:5070 (Albers CONUS) | — |

### 7.3 Honest comparison: Step 5 figure vs Step 6 screenshot

The Step 5 figure is the one that belongs in a report, and it is not close. It
shows the actual parcel — the viewer has no idea the parcel exists, so its
screenshot is a picture of a neighbourhood with the site invisible, and a
reader cannot tell what is being assessed. The figure also carries the numbers
that a reader needs (596.33 ac total, 0.00 ac SFHA, 428.5 ac not mapped), a
legend restricted to the zones actually present, a scale bar in feet, a north
arrow, a full source-and-projection block, and a disclaimer — and it is
4800 × 2700 at 300 dpi, which drops onto a 16:9 slide or a letter page without
resampling. The screenshot is 2020 × 1087 of browser chrome, has the NFHL Print
Tool panel covering the upper-left quarter of the map (it opens by default and
cannot be suppressed via URL), a scale bar in a corner too small to read when
scaled down, and Esri/Vantor attribution baked in. What the screenshot does
better is provenance and trust: it is unmistakably FEMA's own rendering, it
carries FEMA's authoritative symbology and label placement, and it displays
things my figure derives rather than renders — the panel effective dates in
FEMA's own type, the "Not Printed" annotation, and the community/ANI labels
positioned by FEMA. For a diligence pack I would lead with the Step 5 figure
and keep the screenshot as a one-page appendix corroborating it. What the Step 5
figure lacks is any FEMA imprimatur: it is my rendering of FEMA data, so a
reviewer who wants the official article still needs the FIRMette — which is
exactly the artefact this environment could not produce.

### 7.4 Workarounds required

1. **Python not on PATH.** The Windows Store `python.exe` shim errors instead of
   running. Located real interpreters with `py -0p` and used Python 3.12
   directly to build the venv.
2. **`S_POL_AR` is layer 22, not 31.** Layer 31 on this MapServer is
   `Subbasins`. Read the MapServer layer list and used 22.
3. **FEMA TLS connection reset** (`WinError 10054`) on the first layer-22
   request. Switched to a persistent `requests.Session` with a browser
   `User-Agent` and up to 5 retries with backoff; it then succeeded first try.
4. **Missing flood-zone coverage over 72 % of the parcel.** Rather than report a
   gap, cross-checked `S_POL_AR` and found `ANI_TF='T'` for Rocky Mountain
   Arsenal. The ANI polygon in the figure and the geopackage is **derived**
   (parcel ∩ ANI political area) and labelled as such in
   `out/site1_fema.gpkg:area_not_included` (`SOURCE` column). It is not a
   `S_FLD_HAZ_AR` feature, and the report says so.
5. **NAIP resolution.** A single `exportImage` at 2400 px gave only 2.36 m/px.
   Tiled 2 × 2 at 3200 px each (under the server's 4000 px cap) and mosaicked
   to 0.885 m/px, then verified the four tiles were not identical responses.
6. **Blocking modals in the NFHL Viewer.** Loop-click every visible `OK` before
   any other interaction, on every page load.
7. **Deterministic viewer framing.** The search box centres but does not set a
   predictable zoom, so the final screenshot was taken after re-loading with
   `&center=lon,lat&level=16` URL parameters.
8. **No workaround found for the print/export.** Tried: the pin tool + map
   click, direct entry into the widget's lat/lon boxes, `Execute` (does not
   exist) and `Run` (exists, clicked, no effect), waiting 180 s for a download
   event, waiting a further 60 s for a result link, and scraping the DOM for
   any PDF/PNG href. All failed. Recorded and moved on.
