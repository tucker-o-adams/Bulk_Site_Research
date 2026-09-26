# Site attractiveness rating — design note (v0.1, 2026-09-26)

Internal (Tucker + Claude). Not for Mike until we agree the whole method. Status: **framework agreed; metrics per
dimension and the overall rule not yet designed.**

## 1. Goal

Rate each broker site **High / Medium / Low priority**: a general view of attractiveness for TBDI's attention, not a
go/no-go decision (GO / REVIEW / NO-GO waits for thresholds Mike approves). Focus: small to medium campuses.

- A **1–5 rating per dimension**, then an **overall priority** reached by written rules plus judgement, not an average.
- Ratings measure the site against **market standards and its own need**, never against the other sites in the batch.
  A site sized for 5 MW with 5 MW secured rates high on power; it is not penalised for not being 100 MW.
- Where no approved threshold exists we use **labelled hypothesis thresholds**, derived from the product segment and
  external benchmarks, never tuned to a batch's own values.

## 2. What the market says (summary)

Deliverable power and time-to-power lead (18–24 months carries a premium; interconnection elsewhere takes 4–10
years; a utility commitment in writing is the strongest evidence). Small sites hit the same feeder / substation /
transmission bottlenecks as large ones, and upgrade cost is its own screen (above ~30 % of project cost is typically a
deal-breaker at edge scale). Then: connectivity (2+ diverse carriers; within 20–50 km of demand for edge), land for
the MW plus room to grow, zoning and community (now a constraint on par with power), and secondary factors (power
price, incentives, water, workforce). Sources: JLL, CBRE, Build, GridMatch, Bloom Energy, LVI Associates, Area
Development, Bipartisan Policy Center (links in the session of 2026-09-26).

TBDI's implied framework (CLAUDE.md filters, Mike's Teams message, the incomplete-inputs design note, the pipeline)
agrees on flood / wetlands, neighbours, land, market and site control. It differed on: distance to power instead of
deliverable power (now: distance is only a fallback proxy), no timeline or investment dimension (now added), carrier
diversity (ask Mike), thin zoning / community data (partly addressed by a local headlines search).

## 3. Structure

### Screeners (not rated; screen a site out)
- **Site risk, fatal flaws only:** the site mostly in a floodway, wetland or a known contaminated site. Partial
  exposure is not a screener: it reduces buildable acres under Land and buildability.
- **Site control completely blocked** (found, not assumed: a site offered as an acquisition target is presumed not blocked).

### Rated dimensions (1–5, each only where information allows; otherwise "unknown")

| Dimension | What it measures | Notes |
|---|---|---|
| **Power** | MW deliverable against the site's need, and how secure it is | Deliverable MW and its evidence first; distance / voltage to infrastructure only as a fallback proxy. The delivery *date* belongs to Timeline, not here |
| **Timeline** | When the site can start construction with power | The latest of its gates: power energised, site control closed, entitlements, required upgrades. Assessed separately, as project-finance ratings separate construction risk from operations (S&P: the weaker phase sets the profile) |
| **Investment to ready** | Cost to make the site ready for development or sale | Substation / transformer / feeder upgrades, connection charges (CIAC), fiber build, remediation. External benchmark: > ~30 % of project cost is a deal-breaker at edge scale |
| **Connectivity** | Fiber and network position | Carrier quotes, carriers nearby, data-centre / interconnection ecosystem for network. Carrier diversity: question for Mike |
| **Land and buildability** | Enough buildable land for the need, and how buildable | Minimum: the footprint of 2 MW of modular data-centre infrastructure (figure to set). Partial flood / wetland exposure reduces buildable acres; slope, soils, room to expand |
| **Community and entitlements** | Zoning, permits, neighbours, local stance | Often unknown. Broker zoning; neighbours (homes, schools, worship, healthcare); a search for notable local headlines, positive or negative |
| **Site control** | How far along control of the land is | Contract > LOI > owner / tract identified > none. Blocked control is a screener |
| **Market position** | Nearness to demand and the data-centre ecosystem | Metro distance, data centres and hubs nearby, planned developments (Baxtel, manual); later: regional grid congestion (Mike's item) |

### Confidence (over every dimension, not a dimension itself)
- Each rating carries a confidence level set by an **evidence standard** where one exists (power: utility study or
  will-serve letter = high; utility pre-screen = medium; broker estimate = low). Utility power studies define what a
  complete power answer contains (confirmed capacity, source substation, upgrades, timeline); most sites won't have one.
- **"No information" is always a valid state**, and will be common. It is shown, never guessed or scored as average.
- **Top ratings need high confidence** (a 5 needs strong evidence, not only a good-looking number). How much a gap
  costs depends on the dimension: unknown power bites far harder than unknown water. (Mechanism to design.)

## 4. From dimensions to priority (to design)
- Written rules give an **indicated priority**; some dimensions weigh more, some can cap the result (like the S&P weaker-phase rule and Moody's caps).
- **Named adjustments** move the priority one step with a stated reason (e.g. upstream grid gate, adjacent hyperscale
  demand, community opposition on record). **The list is open**: it grows or changes as we rate more portfolios, each
  change recorded in the method version log.
- The report shows **indicated and assigned priority** side by side, with the reason when they differ; a **second
  review** (Tucker) whenever they differ.

## 5. Controls (best practice)
- **Calibration** on sites whose outcome we know (developed, sold as powered land, abandoned) before trusting the rules.
- **Sensitivity check:** do ratings flip under small changes to weights or thresholds?
- **Consistency check:** two raters or two runs on the same sites.
- **A written reason** for every judgement call.
- **Versioning:** the method has a version and change log; every rating records the method version and its as-of
  date, and names what would trigger a re-rate (new utility letter, change in site control).

## 6. Next steps
1. Metrics per dimension: what earns a 1–5, the evidence standard, and how "unknown" is recorded.
2. The land minimum figure (2 MW modular footprint).
3. The overall rule: weights, caps, how confidence limits the top, the first list of named adjustments.
4. Calibrate on known outcomes; then a trial on test batch 1.
5. Questions for Mike (when we go to him): carrier diversity; later the whole method.

## Appendix: limitations (to complete with the method)
- Evidence is mostly broker-supplied; our checks use free public data (HIFLD substations are from 2021).
- The tool does not estimate deliverable MW; power ratings rest on what the broker and utility state.
- Zoning, community stance and incentives are rarely available from free sources.
- Ratings are as of their date; broker positions and utility capacity change.
