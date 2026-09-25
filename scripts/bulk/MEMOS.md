# Batch memos — spec

Every broker portfolio that goes through the bulk pipeline gets the same two Word memos, beside `sites.csv`, the
workbook and the KMZ. Same sections, same order, same colours, every batch, so a reader learns them once.
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

| Status | Colour | Rule | Asks a person? |
|---|---|---|---|
| **Confirmed** | green `2E7D32` / `E2EFDA` | The broker's pin (or APN) sits in a parcel within 15 % of the stated acreage, and nothing the broker says contradicts it. Also: a precise pin with no acreage stated. | No |
| **Confirmed: carve-out / several parcels** | blue `1F5FA8` / `DDEBF7` | Precise pin; the size gap is explained. Stated site much smaller than the parcel → carve-out (*stated* when the broker says so, else *probable*). Larger → *spans several parcels*. The note says which; parcel figures describe the parcel, not exactly the site. | No |
| **Needs confirmation** | amber `B26A00` / `FFF2CC` | Borderline and settleable: an approximate pin whose parcel does not match (candidates listed); a substation claim that contradicts a precise pin; a site near a named anchor with 1–5 candidate parcels; tracts named by owner with 1–5 parcels under those names. | Yes: one question with options |
| **Not locatable** | grey `6E6E6E` / `EDEDED` | Only a ZIP or county with no tract names; an anchor with no acreage to search by; zero or more than 5 candidates. | No |
| **No site yet** | light grey `9A9A9A` / `F7F7F7` | The broker says no site is identified (`no_site_yet`, or `no_site_control` with no acreage and no point). Nothing to locate. | No |

Rules that keep the questions few:
- **Trust a precise pin.** When its parcel matches the size, no neighbour is offered instead, even a closer size match.
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
3. **Location status**: the five definitions as colour banners, then one table row per site, grouped by status (heavy rule between groups), status cell shaded: Site · Status · Located by · Why.
4. **Needs your input**: per site, an amber banner, the assessment, what the broker says about the location (verbatim, `broker_text.py`), the question in bold with the exhibit reference, tick-box options (candidates lettered A, B, C as on the exhibit, then "the parcel under the coordinate" if not listed, then "None of these"), and a notes line.
5. **How the status is set**: the rules above, in five bullets, and the sources.
6. **Appendix A**: one landscape page per site with a question; a banner in the status colour, then the exhibit.

Not in this memo: flood, wetlands, power, site control, data-handling notes. They are in the summary.

## 3. Summary memo — sections, in order

1. **Title block** and the **status line** (no screening verdicts until thresholds are approved).
2. **Summary**: `input/memo_narrative.md`, written in the Claude Code session (§5).
3. **Portfolio at a glance**: sites by market; site control; location status counts (pointing to the confirmation memo); broker-stated power by confidence tag and market; fiber quotes; how many sites carry broker grid caveats.
4. **Site by site** (landscape): one block per site, a heavy rule between sites; rows Location · Site control · Acreage · Power · Connection · Transmission · Flood · Wetlands · Fiber · Grid caveats · Homes within 1 mi, columns *Broker says* | *We found*; a row appears only if either side has something. The Location row's *We found* cell is shaded in the status colour. Parcel-level checks (flood, wetlands, parcel acres) only for sites located to a point; `~` marks values measured from a placed point, for context only.
5. **Data handling notes**: licensed-county parcels, parcel records without owners, pin/ZIP or pin/address differences that were *not* treated as contradictions.
6. **Method, sources and gaps**: how the list was read; the producers table; what the tool does not do.

## 4. Exhibits

- A parcel check (`figure.py --layers parcels --views site --audience internal`) is drawn for every site located to a point; a location map for an L3 or L4 site only when its candidate or tract-name search leaves a question. Only the exhibits of **Needs confirmation** sites go into the memo.
- Banner in the status colour, with the status, stated vs found acreage and the assessment; the broker's words verbatim under it.
- Identified parcel: dark red, thick outline. Candidates: orange, lettered. Named substation: purple square. Red dot for the pin only when the broker gave a precise coordinate.

## 5. The narrative (Claude, in session)

Written after the run, read into the summary memo. Portfolio facts only, no verdicts, about half a page:
what the offering is; the power picture and how well it is evidenced; how much of the land side can be checked
(pointing to the confirmation memo, not repeating it); the facts on confirmed sites a reader should see first
(e.g. a site in Zone AE); broker-stated caveats that change what a MW figure means.

## 6. Order of work

```
figure.py <batch> --only <all L1-L4 sites> --layers parcels --views site --audience internal
(write input/memo_narrative.md)
memo.py <batch> --name <Title>
```
Then render both .docx to PDF and look at every page before sending (Word COM → PDF → PNG, as in the test notes).
