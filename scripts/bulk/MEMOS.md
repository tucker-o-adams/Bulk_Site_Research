# Batch memos — spec

Every broker portfolio that goes through the bulk pipeline gets the same two Word memos, at the top of the batch
folder beside the workbook and the KMZ (machine files in `Supporting outputs/`, earlier versions in `Archive/`: README). Same sections, same order, same colors, every batch, so a reader learns them once.
`memo.py` builds both from files already on disk; the only hand-written part is the summary narrative.
Both are **internal to TBDI** (Mike included): owner names, broker detail and licensed-county parcels are allowed,
marked where they apply.

| Memo | File | Purpose |
|---|---|---|
| Location confirmation | `<Title>_confirmation_memo.docx` | **A.** How sure we are that the tool has each site's location. **B.** A question for each site a person can settle. Nothing else. |
| Portfolio summary | `<Title>_summary_memo.docx` | What the portfolio is: narrative, the portfolio at a glance, one block per site (broker says / we found), data-handling notes, method and sources. |

## 1. Location status (both memos, the exhibits, `broker_summary.csv`)

One of five per site, set by `location_status.py` from fixed rules. The parcel check (`parcel_check.py`) and the
candidate search (`candidates.py`) produce the evidence; the exhibits and the memos read the status from the
same function, so they cannot disagree.

| Status | Color | Rule | Asks a person? |
|---|---|---|---|
| **Confirmed** | green `2E7D32` / `E2EFDA` | The broker's pin (or APN) sits in a parcel within 15 % of the stated acreage, and nothing the broker says contradicts it. Also: a precise pin with no acreage stated. | No |
| **Confirmed: carve-out / several parcels** | blue `1F5FA8` / `DDEBF7` | Precise pin; the size gap is explained. Stated site much smaller than the parcel → carve-out (*stated* when the broker says so, else *probable*). Larger → *spans several parcels*. The note says which; parcel figures describe the parcel, not exactly the site. | No |
| **Needs confirmation** | amber `B26A00` / `FFF2CC` | Borderline and settleable: an approximate pin whose parcel does not match (candidates listed); a substation claim that contradicts a precise pin; a site near a named anchor with 1–5 candidate parcels; tracts named by owner with 1–5 parcels under those names. | Yes: one question with options |
| **Not locatable** | gray `6E6E6E` / `EDEDED` | Only a ZIP or county with no tract names; an anchor with no acreage to search by; zero or more than 5 candidates. | No |
| **No site yet** | light gray `9A9A9A` / `F7F7F7` | The broker says no site is identified (`no_site_yet`, or `no_site_control` with no acreage and no point). Nothing to locate. | No |

Rules that keep the questions few:
- **Trust a precise pin.** When its parcel matches the size, no neighbor is offered instead, even a closer size match.
- **Carve-outs and multi-parcel sites are confirmed**, with a note: nothing contradicts the broker.
- **A substation 150–400 m from the parcel** ("near": HIFLD points can sit tens of metres off) does not lower a status. Beyond 400 m, against a broker "adjacent", it does.
- **Never guess combinations** of parcels, and never let the tool pick a candidate.
- **Never recommend a parcel whose owner contradicts known information** (candidates only rank same-owner parcels first; the person chooses).
- **ZIP-, county-level and no-site rows get no exhibit and no question.**

Candidate search (`candidates.py`): every parcel within ±15 % of the stated acreage in the area the site can be in.
- Approximate pin that does not match: the pin's 500 m radius, plus 400 m around a substation the broker says the site adjoins.
- Near a named anchor (L3): only when the broker says the tract is identified (not "no site yet") and states an actual acreage (not a search target). The anchor's radius (2 km), or 400 m when the broker says the site adjoins the anchor substation.
- Tract names (`search_owner`): the broker names a tract by its owner ("25 ac Smith + 23 ac Jones") for a site placed within a ZIP or near an anchor, and says a site exists. Parcels under each name within ±15 % of the tract's acreage, inside the area plus 2 km (a Census ZIP area is not the mailing ZIP), from the county's own service in `data/reference/owner-search-services.json` (reviewed, like the parcel registry; Bexar added 2026-09-25). The name's other parcels there are drawn as context. First run (test batch 1): one tract 2 candidates, the other none.
- Services that cap answers are tiled (TxGIO identify: 2,000 records per request). Cached.
- Tested on a confirmed site of test batch 1 as if only its substation were known: 18 parcels of the size within 2 km, one of them adjoining the substation — the right one.

## 2. Confirmation memo — sections, in order

1. **Title block**: `<Title>: location confirmation`, INTERNAL stamp, run date, source file and hash.
2. **Purpose** (fixed text) and **Bottom line**: counts by status; how many questions.
3. **Location status**: the five definitions as color banners, then one table row per site, grouped by status (heavy rule between groups), status cell shaded: Site · Status · Located by · Why.
4. **Needs your input**: per site, an amber banner, the assessment, what the broker says about the location (verbatim, `broker_text.py`), the question in bold with the exhibit reference, tick-box options (candidates lettered A, B, C as on the exhibit, then "the parcel under the coordinate" if not listed, then "None of these"), and a notes line.
5. **How the status is set**: the rules above, in five bullets, and the sources.
6. **Appendix A**: one landscape page per site with a question; a banner in the status color, then the exhibit.

Not in this memo: flood, wetlands, power, site control, data-handling notes. They are in the summary.

## 3. Summary memo — LOCKED structure

**Purpose:** give TBDI an overview of the portfolio, before thresholds exist. Consistency across reports comes first:
the section headers, their order, and every table's rows and columns below are fixed and appear in every batch
(Tucker, 2026-09-25). A reader learns the memo once. Change this only when Tucker asks, and change `memo.py`
(`SUMMARY_SECTIONS` and the section code) in the same commit.

Rules for every section:
- `Summary` (heading 1) contains only these sections (heading 2), in this order. Nothing above them.
- Each opens with its **summary line**, bold, computed by `memo.py` from the fixed template below: the same words in
  every report, no site names (Tucker, 2026-09-28). Then bullets. No blocks of prose.
- **A bullet never repeats the section's table.** Bullets add what the table cannot show (sites, causes, context).
- American spelling everywhere a reader sees it; `memo.py` warns about British spellings in either memo.
- **Every summary table has one row per market (MSA), in list order, then a bold Total row.** Zero counts show "—". Ranges show min–max.
- A section with nothing to show keeps its heading and table and says so.

| # | Section | Summary line (computed) | Table (rows: each market, then Total) |
|---|---|---|---|
| 1 | **Priority ratings** (our rating, `ratings.csv`; added 2026-09-28) | High: n · Medium: n · Low: n · Insufficient information: n · Screened out: n | Market · Rows · High · Medium · Low · Insufficient information · Screened out (assigned priority; columns shaded in the priority colors) |
| 2 | **Location confidence** (brief; the confirmation memo has the detail) | n of N rows confirmed on the map. | Market · Rows · Confirmed · Confirmed: carve-out / several parcels · Needs confirmation · Not locatable · No site yet (status columns shaded in the status colors) |
| 3 | **Power** | n MW stated available (n confirmed in writing); n MW requested. | Market · Rows · MW confirmed in writing · MW pre-screen / estimate · MW requested / up to · MW per row · First power · ¢/kWh |
| 4 | **Fiber** | Quoted on n of N rows. | Market · Quoted (n of rows) · Carrier · Build (NRC) · Monthly (MRC) · Longer route |
| 5 | **Proximity** (our check, every row) | Confirmed sites: a–b km from a 1M+ metro and a–b km from the nearest data center. | Market · Rows · From site / placed point · To 1M+ metro · Nearest data center · Nearest hub (20+ networks) · Data centers within 50 km |
| 6 | **Neighbors** (our check, confirmed sites) | n of N confirmed sites have more than 100 homes within 1 mile. | no table: bullets only (homes within 1 mile, schools, places of worship, hospitals / nursing homes); per-site figures in Appendix A |
| 7 | **Flood** (our check, confirmed sites) | n of N confirmed sites have part of the parcel in the FEMA flood zone. | no table: bullets only (FEMA zone at the pin, % of parcel in SFHA, % in NWI wetland); per-site figures in Appendix A |
| 8 | **Ownership** | n of N rows are under contract or at LOI / negotiating. | Market · Rows · Under contract · LOI / negotiating · Owner identified · Tract identified · No site yet · No site control |
| 9 | **Caveats and other** | n caveats affect the headline figures. | no table: bullets, each naming the sites and the effect on the headline figures |

**Priority ratings** is all computed (no session text): the summary line, then one bullet per priority in the order
above ("n High" … "n Screened out", every one shown, even at 0), and under each a sub-bullet per cause: "n <cause>:
sites", largest first. The causes are every step that moved the site, in order, joined by "→", in the fixed wording of
`rating_rules.CAUSE` (a named adjustment by its name, "(up)" if it raises the priority; the Power ceiling counts unless High; a step that changes nothing does not).

**Ownership** bullets are exactly two: "**Partial control:**" (session: sites where only some tracts are under
contract or LOI, or "None.") and "**Complete packages**" (computed: confirmed site, contract or LOI, MW confirmed in
writing, fiber quote).

Proximity for a row without a confirmed site is measured from where it was placed (named substation, intersection,
ZIP center): market context, counted in "From site / placed point" and marked "(placed)" in Appendix A.

Appendices:
- **A. Site by site** (landscape): one row per site, grouped by market (heavy rule between markets). Columns: Site · Location (our status, shaded) · Site control · Power, timing, utility · Fiber · Proximity (ours) · Flood (ours) · Neighbors (ours) · Caveats and other notes.
- **B. Ownership and data handling**: owner of record beside what the broker says, on confirmed sites; licensed-county parcels, records without owners, pin/ZIP or pin/address differences not treated as contradictions.
- **C. Method, sources and gaps**.
- **D. Ratings by site** (landscape): one row per site, grouped by market. Columns: Site · Location (shaded) · the seven dimension scores (Power, Investment, Land, Site control, Community, Connectivity, Market; shaded 1–5, U = unknown) · Screeners · Indicated · Named adjustments · Assigned · Why (the rules). Evidence and confidence for every score stay in `ratings.csv`.

The broker wording in Appendix A (Site control; Power, timing, utility; Fiber; Caveats and other notes) and in Appendix B's
broker column comes from `broker_facts.py`, which the workbook's **Broker says** sheet also uses (README, Workbook): change
the wording there and the memo and the workbook follow together.

The ratings come from `rate.py` (method: `design_site_rating.md`). `memo.py` runs `rating_check.py` on `ratings.csv` and
will not write the summary memo from ratings that fail it (missing confidence or reason, a score above its confidence cap,
a priority the rules do not give, an adjustment without a reason, another method version, or a changed location status).
Without `ratings.csv` the section keeps its heading and table and says the batch is not rated.

## 4. Exhibits

- A parcel check (`figure.py --layers parcels --views site --audience internal`) is drawn for every site located to a point; a location map for an L3 or L4 site only when its candidate or tract-name search leaves a question. Only the exhibits of **Needs confirmation** sites go into the memo.
- Banner in the status color, with the status, stated vs found acreage and the assessment; the broker's words verbatim under it.
- Identified parcel: dark red, thick outline. Candidates: orange, lettered. Named substation: purple square. Red dot for the pin only when the broker gave a precise coordinate.

## 5. The bullets (Claude, in session)

`input/memo_narrative.md`, written after the run: one `## <Section>` block per section in §3 except Priority ratings,
named exactly. Facts only, no verdicts; memo.py flags any section without one.
- Each block: **bullets only** (`- `), 1–6 of them: sites and numbers, outliers, contrasts between markets, what the broker says against our check. No lead sentence (memo.py writes the summary line) and no paragraphs; memo.py leaves out and reports any other text.
- Never restate the section's table or its summary line.
- A finding goes in the section it is mainly about (MW without land: Power; the rows with every element in place: Ownership). Never add a free-form section.
- Check every number against the computed tables and Appendix A before rerunning.

## 6. Order of work

```
figure.py <batch> --only <all L1-L4 sites> --layers parcels --views site --audience internal
memo.py <batch> --name <Title>          (writes broker_summary.csv, which rate.py reads)
(write input/rating_readings.json)
rate.py <batch>                         (ratings.csv; rating_check.py <batch> to check it on its own)
(write input/memo_narrative.md)
memo.py <batch> --name <Title>
```
Then render both .docx to PDF and look at every page before sending (Word COM → PDF → PNG, as in the test notes).
