# Site attractiveness rating — design note (v1.0, 2026-09-28)

Internal (Tucker + Claude). Not for Mike until we agree the whole method. Status: **framework agreed (v0.1); full draft
method v0.2 (§4) for review, then testing (§5).**

Version log: v0.1 framework (2026-09-26) · v0.2 draft rubric, confidence rule, overall rule; Timeline anchors set to the
market's 18–24-month premium and 4–10-year norm after a first check on test batch 1; fiber build cost moved wholly to Investment to ready (2026-09-26). · v0.3: Power rebuilt as reliable MW + certainty + time (5 = ≥ 5 MW committed within 12 months), the separate Timeline dimension retired (its non-power gates move to Site control and Community and entitlements) (2026-09-27). Power ladder written with explicit ≥ 5 MW and 2–5 MW columns (2026-09-27). Investment to ready bands anchored to 2025–26 typical costs, per MW counted in Power (2 MW min), unpaid-for upgrades developer-funded (2026-09-27). Land and buildability simplified: land need max(1.0 ac, 0.5 ac/MW); acreage ratio × slope / soils (site-prep cost proxy), explicit criteria (2026-09-27). Site control explicit (closing ≤ 12 months for 5; signed LOI 4; negotiating 3; least-controlled tract rule) (2026-09-27). Connectivity: FCC fiber-provider proxy replaces hub distance (hub stays in Market position); quote level sets confidence; not quoted → proxy (2026-09-27). Market position explicit on metro and hub distance (2026-09-27). Community and entitlements rebuilt on ordinance research (1,000 ft setback line, permit path, receptors incl. worship / healthcare); Texas grid-audit named adjustment for ≥ 25 MW (2026-09-27). · v0.4: Power as an amount × certainty grid (one point off per step in either); overall rule revised (screeners passed for High; moratorium caps at Low; low-confidence supporting 1s flagged only; adjustments limited to factors outside the dimensions) (2026-09-28). · v0.5 after edge-case testing (21 profiles, scripts/bulk/rating_edge_cases.py): caps applied after step-downs; Power floor of 3 for the 2 MW minimum committed or credible within 24 months; High needs one important dimension at 4+ and none below 3 (2026-09-28). · v0.6 after calibration on 17 public cases (scripts/bulk/rating_calibration.py): Community and entitlements moved to important; named adjustment for a publicly stated utility capacity constraint (sites without committed power only); primary use set to edge inference (2026-09-28). · v0.7 after the test batch 1 trial (scripts/bulk/rate.py; independent consistency pass agreed on all 25 priorities; sensitivity stable): Power's Low threshold moved from 24 to 36 months (C1 12–36, C2 ~36, C3 > 36); phased power scored on its best phase (2026-09-28). · **v1.0**: 14 application rules (§4.6) approved as a set; Texas audit adjustment kept for now (2026-09-28). Test batch 1 at v1.0: 13 Medium, 12 Low (one site indicated High, Medium after the audit adjustment).

## 1. Goal

Rate each broker site **High / Medium / Low priority**: a general view of attractiveness for TBDI's attention, not a
go/no-go decision (GO / REVIEW / NO-GO waits for thresholds Mike approves). Focus: small to medium campuses,
**primarily for edge inference** (Tucker, 2026-09-28) - so nearness to demand counts (Market position), and remote
sites suited to training or cable landings rate lower there by design.

- A **1–5 rating per dimension**, then an **overall priority** reached by written rules plus judgment, not an average.
- Ratings measure the site against **market standards and its own need**, never against the other sites in the batch.
  A site sized for 5 MW with 5 MW secured rates high on power; it is not penalised for not being 100 MW.
- Where no approved threshold exists we use **labeled hypothesis thresholds**, derived from the product segment and
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
agrees on flood / wetlands, neighbors, land, market and site control. It differed on: distance to power instead of
deliverable power (now: distance is only a fallback proxy), no time-to-power or investment dimension (now: time-to-power inside Power; Investment added), carrier
diversity (ask Mike), thin zoning / community data (partly addressed by a local headlines search).

## 3. Structure

### Screeners (not rated; screen a site out)
- **Site risk, fatal flaws only:** the site mostly in a floodway, wetland or a known contaminated site. Partial
  exposure is not a screener: it reduces buildable acres under Land and buildability.
- **Site control completely blocked** (found, not assumed: a site offered as an acquisition target is presumed not blocked).

### Rated dimensions (1–5, each only where information allows; otherwise "unknown")

| Dimension | What it measures | Notes |
|---|---|---|
| **Power** | Reliable MW the site can count on, how certain, and when it arrives | Deliverable MW and its evidence first; distance / voltage to infrastructure only as a fallback proxy. Time-to-power is part of this dimension (a credible date, and how certain) |
| **Investment to ready** | Cost to make the site ready for development or sale | Substation / transformer / feeder upgrades, connection charges (CIAC), fiber build, remediation. External benchmark: > ~30 % of project cost is a deal-breaker at edge scale |
| **Connectivity** | Fiber and network position | Carrier quotes, carriers nearby, data-center / interconnection ecosystem for network. Carrier diversity: question for Mike |
| **Land and buildability** | Enough buildable land for the need, and how buildable | Minimum: the footprint of 2 MW of modular data-center infrastructure (figure to set). Partial flood / wetland exposure reduces buildable acres; slope, soils, room to expand |
| **Community and entitlements** | Zoning, permits, neighbors, local stance | Often unknown. Broker zoning; neighbors (homes, schools, worship, healthcare); a search for notable local headlines, positive or negative |
| **Site control** | How far along control of the land is | Contract > LOI > owner / tract identified > none. Blocked control is a screener |
| **Market position** | Nearness to demand and the data-center ecosystem | Metro distance, data centers and hubs nearby, planned developments (Baxtel, manual); later: regional grid congestion (Mike's item) |

### Confidence (over every dimension, not a dimension itself)
- Each rating carries a confidence level set by an **evidence standard** where one exists (power: utility study or
  will-serve letter = high; utility pre-screen = medium; broker estimate = low). Utility power studies define what a
  complete power answer contains (confirmed capacity, source substation, upgrades, timeline); most sites won't have one.
- **"No information" is always a valid state**, and will be common. It is shown, never guessed or scored as average.
- **Top ratings need high confidence** (a 5 needs strong evidence, not only a good-looking number). How much a gap
  costs depends on the dimension: unknown power bites far harder than unknown water. (Mechanism to design.)

## 4. Draft method (v0.2 — for review, then testing)

All thresholds below are **hypotheses** (labeled H), set from the market sources in §2 and the product segment, scaled
to the site's own need, never to a batch's values. Testing (§6) may move them; every move is logged in the version log.

### 4.1 Common terms

- **MW counted:** the reliable MW scored under Power (absolute ladder, full credit at ≥ 5 MW). It is the divisor for
  Investment to ready (2 MW minimum) and, with the broker's target MW, sets the land need.
- **Land need (acres, H):** max(1.0 ac, 0.5 ac × MW) (see Land and buildability). **1.0 ac is a deliberately conservative minimum** for 2 MW
  of modular infrastructure (Tucker, 2026-09-27; revisit with Mike). Evidence: a real 2 MW modular proposal needs
  ~0.25–0.5 ac inside a larger leased parcel (NODIAC, Dunn County WI, July 2026); modular sites run "1 to 20 MW on 1 to
  5 acres" (MomentumWest); edge sites "1–3 acres for 5MW; 3–8 acres for 20MW" (Build.inc), i.e. ~0.15–0.6 ac/MW. The
  gap to 1.0 ac covers setbacks, access, transformer / generator pads and noise buffers on a standalone parcel.
- **Reference build cost (H):** $11.3M per MW (Cushman & Wakefield 2026). ~30 % of it (~$3.4M/MW) is the market's
  deal-breaker line for readiness spend at edge scale.
- **Scale (all dimensions):** 5 strong and market-competitive · 4 good, minor gaps · 3 workable / typical · 2 weak, a
  material issue · 1 poor, likely unworkable · **U unknown** (no usable information).

### 4.2 Confidence and unknowns

| Confidence | Typical evidence | Highest score allowed |
|---|---|---|
| High | written utility commitment or study; signed contract; our own measure on a confirmed site | 5 |
| Medium | utility pre-screen or verbal estimate; specific broker statement with a source (study stage, date, $); our measure on a site with an approximate location | 4 |
| Low | broker estimate or untagged claim; a **proxy** (e.g. distance to a substation instead of deliverable MW) | 3 |
| None | nothing usable | U |

Shown score = min(evidence score, confidence cap). For Power the grid already scores certainty with the same tiers,
so the cap never costs a Power score an extra step. **A proxy counts as known information** (capped at 3), so a site
with only a proxy is never "Insufficient information". Silence is never read as good news ("no upgrade mentioned" is U,
not 5). **Ambiguity cost** decides how much a U matters in the overall rule: **critical** Power;
**important** Investment to ready, Land and buildability, Site control, Community and entitlements (moved from
supporting in v0.6 after calibration); **supporting** Connectivity, Market position.

### 4.3 Screeners (checked first; a screened site gets no priority)
- **Site risk:** buildable acres after removing **all flood zone (SFHA, including floodway)** and mapped wetland fall
  below the 1.0 ac minimum, or a contaminated-site listing on the parcel. Partial exposure is handled in Land and
  buildability. *Assumption: no building anywhere in the flood zone for now; confirm with Mike (elevated / permitted
  building in zone AE may be acceptable).*
  - Sites not confirmed on the map: **not assessed** (never "passed").
  - Carve-outs whose position in the parent parcel is unknown: screened only if the whole parent parcel fails;
    otherwise not assessed.
  - Contaminated sites: not yet in the free pipeline (to-do: EPA Superfund / brownfields / leaking-tank lists).
- **Site control blocked:** evidence that the land cannot be acquired or leased: the owner has refused or the land has
  sold to another party (broker or local news); a conservation easement or deed restriction that bars the use; public
  or protected land not for sale. A site offered as a target is presumed not blocked. USGS PAD-US (protected areas,
  free) flags parcels under easement or public ownership **for a person to check** - never an automatic screen-out
  (to-do: add the PAD-US check).

### 4.4 Rubric cards

**Power** — how much reliable power the site can count on, how certain it is, and when it arrives. (critical)

Score = 5, minus one point for each step down in **amount** and each step down in **certainty** (minimum 1). Only
confirmed power that is also enough power earns a 5.

- **Amount (MW counted):** A0 ≥ 5 MW (enough) · A1 3 to < 5 MW (slightly restricted) · A2 2 to < 3 MW (more restricted).
- **Certainty (evidence and timing together):** C0 energised or committed (signed service agreement, or confirmed in
  writing by the utility), within 12 months (6 months best) · C1 a credible date within 12–36 months (e.g. a utility
  pre-screen or estimate with a date) · C2 within about 36 months but less certain (requested, under study, or
  broker-stated only) · C3 more than 36 months, or requested with no study or date. **(v0.7: the Low threshold moved
  from 24 to 36 months - Tucker, 2026-09-28.)**
- **Phased power:** each phase is scored on the MW available by its date; the best phase counts (e.g. 22 MW in spring
  2029, 35 MW in summer 2030 → the 22 MW phase at ~31 months → C1).

| | C0 | C1 | C2 | C3 |
|---|---|---|---|---|
| **A0: ≥ 5 MW** | **5** | 4 | 3 | 2 |
| **A1: 3 to < 5 MW** | 4 | 3 | 2 | 1 |
| **A2: 2 to < 3 MW** | 3 | **3** | 1 | 1 |

**Floor (v0.5):** a site that meets the 2 MW minimum with committed power or a credible date within 36 months (C0 /
C1) scores at least 3 - a workable site (changes only A2 × C1, from 2 to 3; edge case P16).
**1** also for: under 2 MW with no path to more (below the 2 MW modular minimum), or the utility states no capacity in view.

- **Amount:** the top score needs ≥ 5 MW (small and medium campuses); no extra credit above 5 MW for now. Committed
  on-site / bridge generation counts in the MW (it replaced a named adjustment, 2026-09-28). Rate the MW
  the site can *count on* (firm, committed), not the headline figure, as lenders size on P90 rather than P50: non-firm
  or interruptible MW counts as requested; phased power scores on the MW available by each date.
- **Certainty** follows the stage: requested → studied → signed or committed → energised (the market's language and
  the large-load process: application, feasibility, system impact, facilities study, service agreement). Evidence
  tags map onto it: confirmed in writing → committed; utility pre-screen / estimate → studied; broker estimate →
  requested.
- **Time** is months from the as-of date to energisation of the MW counted.
- A complete answer names capacity, source substation, upgrades and date; each missing piece lowers confidence.
- **Proxy** when no MW is stated: distance and voltage of the nearest substation / line (to research), always low
  confidence, capped at 3.
- Why one dimension: GridMatch treats capacity, timeline and certainty as one criterion ("a credible 24-month path to
  100 MW"); Enverus's power pillar pairs capacity with "defensible time-to-power" and "power certainty"; the stage a
  site has reached sets both its certainty and its remaining time, so they can't be scored apart.

**Investment to ready** — known spend needed to make the site ready beyond a standard connection: substation /
transformer / feeder upgrades, connection charges (CIAC), line extension, fiber build, remediation. **Per MW counted in
Power (2 MW minimum, so small sites are not flattered).** (important)
| 5 | 4 | 3 | 2 | 1 |
|---|---|---|---|---|
| ≤ $0.1M/MW (a standard connection charge and a short fiber lateral) | $0.1–0.25M/MW (e.g. ~1 mile of overhead line extension, or a long fiber build) | $0.25–1M/MW (e.g. underground extension, a substation transformer upgrade, large-load interconnection costs) | $1–3.4M/MW (e.g. a new distribution substation for a small site) | > $3.4M/MW (> ~30 % of the $11.3M/MW build cost) |

- **Silence = U.** An upgrade with **no payer stated is treated as developer-funded** (Tucker, 2026-09-27).
- **A named upgrade with no cost stated** takes the typical cost below ÷ MW counted in Power, at low confidence
  (e.g. "new substation needed" on a 5 MW site: $3–8M → $0.6–1.6M/MW → 2–3).
- **Typical costs (2025–26):** new distribution substation (138 → 34.5 kV, ~25 MVA) ~$3–8M; substation transformer
  (10–100 MVA) $0.3–2M, lead time 18–36 months; overhead distribution line ~$0.63–0.76M/mile; underground distribution
  line ~$1.85–6M/mile; fiber $18/ft underground, $8/ft aerial (FBA 2025); large-load interconnection $5–25M+ at 25 MW.
  Sources: Buildermuse, DecorDash, Illinois ICC substation estimator, Taishan Transformer, Electrical Trader, Renewable
  Energy World, Fiber Broadband Association, Terrapin CG, Cushman & Wakefield. **To confirm with Mike.**
- Timing effects of an upgrade (e.g. a transformer's lead time) are scored under Power; its cost here.

**Land and buildability** — enough buildable land for the power, and how costly it is to prepare. (important)

- **Land need (H):** max(1.0 ac, 0.5 ac × MW), using the larger of the MW counted in Power and the broker's target MW.
  1.0 ac is the conservative 2 MW modular minimum (Tucker, 2026-09-27).
- **Buildable acres:** site acres minus flood zone (SFHA, incl. floodway) and mapped wetland (our check on confirmed
  sites). Exposure is counted only here, never twice.
- **Slope / soils** stand in for site-prep (grading) cost.

| 5 | 4 | 3 | 2 | 1 |
|---|---|---|---|---|
| buildable ≥ 2× land need, **and** slope mostly < 5 % with no severe soil limits | buildable ≥ 1× land need with slope < 5 % and no severe soils; **or** buildable ≥ 2× land need with slope 5–15 % | buildable ≥ 1× land need with slope 5–15 %; **or** buildable < 1× land need (above the 1.0 ac screener) with slope < 5 % and no severe soils | slope ≥ 15 % or severe soils (shrink-swell clay, shallow rock, fill), any acreage; **or** buildable < 1× land need with slope 5–15 % | buildable < 1× land need **and** slope ≥ 15 % or severe soils |

- **Slope / soils unknown** (not yet measured): score on acreage alone (≥ 2× → 4 at most, ≥ 1× → 4, < 1× → 3), at
  medium confidence.
- **A stated grading or site-prep cost** goes under Investment to ready; Land then does not lower the score for slope
  again.
- Carve-outs: stated acres, medium confidence (the site's own exposure is unknown).
- Sources: acreage from MomentumWest, Build.inc and the Dunn County 2 MW project; the 15 % line from data-center siting
  guidance to avoid slopes of 15 % or more (Georgia Tech EPIcenter) and civil guidance that flat to gently sloping
  land minimizes grading and foundation cost (JPC Engineering, Cadence); **5 % is our hypothesis** for "gently
  sloping". Data: USGS 3DEP (slope) and USDA SSURGO (soils), free - to-do, not in the pipeline yet.

**Site control** — how far along control of the land is. (important)
| 5 | 4 | 3 | 2 | 1 |
|---|---|---|---|---|
| owned, or under contract for all tracts with closing within 12 months | under contract with closing > 12 months or subject to major contingencies; **or** a signed LOI; **or** part of the site (some tracts) under contract | negotiating with the owner, no signed LOI; **or** owner identified and engaged, no terms; **or** a tract listed for sale | tract identified, owner not engaged | no site yet (a search area); or "no site control" stated with no acreage |

- **Multi-tract sites** score on the least-controlled tract the site needs, with the better tract noted (e.g. one
  tract under contract and one in draft → 4).
- **Time to close** (from the retired Timeline dimension) is in the 5 / 4 split above.
- Confidence: broker statement → medium; documents (contract, LOI) → high.
- Blocked control is a screener. Stages come from the extraction vocabulary; **to-do: split "LOI or negotiating" into
  "signed LOI" and "negotiating"** in extraction_vocab.json.

**Connectivity** — fiber at the site: carriers, routes, and fiber providers nearby. (supporting)
| 5 | 4 | 3 | 2 | 1 |
|---|---|---|---|---|
| ≥ 2 carriers quoted, or on-net with diverse routes | one carrier quoted with two diverse routes | one carrier quoted with one route; **or** (proxy) ≥ 2 fiber providers within 2 km | (proxy) 1 fiber provider within 2 km | (proxy) no fiber provider within 2 km |

- **Quotes first; the proxy only when there is no quote.** "Not quoted" means the broker didn't ask, not that there
  is no fiber: it sends the site to the proxy, never lowers the score by itself.
- **Quote level sets confidence:** a firm / engineered quote → high; a desktop (Level 1) quote → medium; fiber
  mentioned with no quote → low.
- **Proxy (low confidence, so ≤ 3):** the most fiber providers reported in any FCC Broadband Data Collection H3
  hexagon (res. 8, ~0.7 km²) within 2 km of the site, or of the placed point for sites not confirmed. Source: Esri
  Living Atlas "FCC Broadband Data Collection" (field UniqueProvidersFiber; Dec 2025 data; public feature service
  under the Esri Master License Agreement - the raw FCC data, public domain, is the fallback). Limitation: the FCC
  data covers mass-market broadband and misses some enterprise / long-haul carriers (e.g. Lumen, Zayo), so it
  under-counts carriers; hence a proxy, capped at 3. Tested on test batch 1: the site with the longest quoted
  fiber build had 0 providers within 2 km; the confirmed sites inside a metro had up to 4-5.
- Build cost counts under Investment to ready only; interconnection-hub distance counts under Market position only.
- **For Mike:** is one carrier with two diverse routes worth a 4, or does a 4 need two carriers?

**Market position** — nearness to demand and the data-center ecosystem. (supporting)
| 5 | 4 | 3 | 2 | 1 |
|---|---|---|---|---|
| ≤ 10 km of a 1M+ urban area **and** an interconnection hub (PeeringDB facility with 20+ networks) ≤ 25 km | ≤ 25 km of a 1M+ urban area **and** a hub ≤ 50 km | ≤ 50 km of a 1M+ urban area; **or** ≤ 25 km of a 250k+ urban area | 50–100 km from a 1M+ urban area | > 100 km from any 1M+ urban area **and** > 25 km from any 250k+ urban area |

- Distances: Census 2020 urban areas (distance to the edge; inside = 0) and PeeringDB facilities, both already in the
  pipeline. Sites not confirmed are measured from the placed point (market context), medium confidence at most.
- A nearby data-center ecosystem counts as a plus (network, customers, workforce). Competition for power / grid
  congestion (Mike's item) and planned developments (Baxtel) come in later, as named adjustments or their own measure.
- Bands (10 / 25 / 50 / 100 km; hub 25 / 50 km) are **our hypotheses**, loosely anchored on edge sites being within
  20–50 km of major employment centers (Build.inc).

**Community and entitlements** — zoning and permit path, neighbors, local stance. (important, since v0.6)

"Sensitive receptors" = schools, places of worship, hospitals and nursing homes (all measured by the pipeline).

| 5 | 4 | 3 | 2 | 1 |
|---|---|---|---|---|
| data centers permitted by right, or no zoning authority; nearest sensitive receptor > 0.5 mi; ≤ 25 homes within 0.5 mi; no negative local news in 24 months | permitted by right, no zoning authority, or industrial zoning; nearest receptor > 1,000 ft; ≤ 100 homes within 0.5 mi; no negative local news | conditional / special use permit needed, or zoning unclear; **or** 100–500 homes within 0.5 mi; **or** mixed local news | rezoning needed; **or** a sensitive receptor within 1,000 ft; **or** > 500 homes within 0.5 mi; **or** negative local news (opposition, a county resolution against) | a moratorium or ban covering the site's jurisdiction; **or** organized opposition to this project on record |

- **Permit path = time to entitlement** (from the retired Timeline dimension): by right is fastest; a conditional /
  special use permit adds public hearings (e.g. Lewisville TX: two); rezoning is slower and riskier.
- **No zoning authority** (not "unincorporated"): e.g. Texas counties generally cannot zone; other states differ.
- **Sourced:** the 1,000 ft line is the strictest common residential setback in 2024–26 ordinances (200–1,000 ft:
  Fairfax 200 / 300 ft, El Paso 300 ft, Stafford 500 ft proposed, Floyd 600 ft, a Virginia county 750 ft, Georgia
  jurisdictions, an Indiana county and Forney TX 1,000 ft); common noise limit 55 dBA at night at the property line
  (Albemarle; Prince William 24 h since Feb 2026). **Our hypotheses:** the home counts (25 / 100 / 500 within 0.5 mi),
  because Census blocks cannot place the nearest house. To-do: nearest-residence distance from FEMA USA Structures
  (residential occupancy), then score on the 1,000 ft line directly.
- **Local headlines search** (to formalise): "[county / city] data center" with moratorium, opposition, rezoning,
  approved; last 24 months; each result recorded positive / negative with its link.
- Zoning is the broker's; receptors are our check on confirmed sites; unknown zoning → U (common).

### 4.5 Overall priority (indicated), then named adjustments (assigned)

1. **Screeners** → *Screened out*.
2. **No power information at all** (not even a proxy) → *Insufficient information*. Not Low: Low would wrongly say
   "unattractive".
3. **Ceiling from Power** (weakest link, like S&P's weaker-phase rule): Power ≥ 4 → High possible; 3 → Medium at
   most; ≤ 2 → Low.
4. **Step-downs first** (from the Power ceiling):
   - **Important dimensions** (Investment to ready, Land and buildability, Site control, Community and entitlements):
     any one ≤ 2 → one step down; two or more ≤ 2 → Low.
   - **Supporting dimensions** (Connectivity, Market position): a 1 at medium confidence or better → one step down; a
     low-confidence 1 (e.g. the FCC fiber proxy) is flagged in the report, not applied.
5. **Then caps, as ceilings** (v0.5: applied last, so one underlying fact is never counted twice - edge case P6, a
   power position with no site, is Medium, not Low):
   - High needs **both screeners passed**, not "not assessed" (a site not confirmed on the map caps at Medium).
   - High needs **at least two of Investment to ready, Land and buildability, Site control known**.
   - High needs **at least one of those three at 4 or better and none below 3** (edge case P18: great power with
     everything else middling is Medium).
   - **Community 1** (a moratorium or ban over the site's jurisdiction) caps the site at **Low**.
6. **Named adjustments** move the assigned priority one step, with a written reason, **only for factors the
   dimensions do not already score** (as Moody's notching covers what is "not fully reflected in the scorecard").
   Open list:
   - up: anchor demand adjacent (e.g. a hyperscale campus next door).
   - down: **serving utility has publicly stated a capacity constraint in the area** (its own statement or a
     regulatory filing, e.g. a multi-year system upgrade or a pause on new large loads) - **only for sites without
     committed power** (C0 exempts); added v0.6 after calibration (Santa Clara / Silicon Valley Power, Hillsboro / PGE).
   - down: first power phase below half the MW counted; **Texas grid audit: site ≥ 25 MW while the PUCT / ERCOT audit
     (directed 3 Aug 2026; RFIs to 25–75 MW loads, pause for ≥ 75 MW "Batch Zero"; completion targeted Dec 2026) is
     open** - remove when it closes; does not apply to sites under 25 MW (e.g. the ~5 MW sites this framework centers on).
   - Retired as double counting (2026-09-28): upstream grid work beyond ~5 years (scored in Power), utility-funded
     upgrades (Investment), community opposition near the site (Community); on-site / bridge generation now counts in
     Power's MW when committed.
7. The report shows **indicated and assigned** priority side by side; any difference gets a second review (Tucker).

### 4.6 Application rules (v1.0 - from the trial and the independent consistency pass; approved 2026-09-28)

1. Community and entitlements is an **important** dimension (the card header now says so).
2. **Power: MW confirmed in writing with a broker-estimated date** → C1 if within 36 months, C3 beyond.
3. **Land need** uses the MW counted in Power, not a broker "target" (e.g. an expansion request).
4. **Per-mile upgrades with no length given** (e.g. "new feeders") → left unknown, never an assumed length.
5. **"No payer stated = developer-funded"** covers upgrades serving the site (its substation, transformer, feeder).
   System-wide transmission work (e.g. a G&T's improvements) affects Power timing, not Investment.
6. **Mixed quoted and estimated costs** → the lower confidence applies.
7. **Community confidence:** our receptor checks on a confirmed site are high; broker zoning follows its evidence tag
   ("no zoning authority" is a legal fact, high); the lower applies. Sourced local news counts as medium or better.
8. **Community on sites not confirmed:** zoning and news only, capped at 4; negative news counts even when zoning is
   unknown.
9. **Carve-outs on Land:** stated acres, no subtraction of the parent parcel's flood / wetland share (the site's
   position is unknown), medium confidence, the parent's exposure noted.
10. **Site-risk screener for multi-parcel sites:** passed when the checked parcel alone clears the 1.0 ac minimum.
11. **Texas grid audit:** MW per interconnection request, else the headline MW; a step down at Low has no effect.
12. **A request with a utility-stated date within 36 months but no study** → C2.
13. **Conflicting site-control evidence:** the most specific fact wins (a named tract beats "no site yet").
14. **"Anchor demand adjacent"** = a named large campus within ~2 km; Market position scores distances, not a
    particular neighbor, so the two do not overlap.

Code: scripts/bulk/rating_rules.py (combination), scripts/bulk/rate.py (per-site scoring; in-session readings in
input/rating_readings.json). Tests: rating_edge_cases.py (21 / 21), rating_calibration.py (17 public cases),
rating_sensitivity.py.

## 5. Testing plan (agreed)
- **Edge-case profiles:** made-up sites that probe the rules (all strong; strong but power unknown; strong power, no
  site control; small site fully powered; heavy flood exposure) — do the rules give the intended answer?
- **Calibration on public proxies:** publicly reported outcomes (sites that were built or sold as powered land; projects
  cancelled for lack of power, local opposition or flood) rated from what was known before the outcome.
  - **Done 2026-09-28** (scripts/bulk/rating_edge_cases.py): 21 profiles; 18 matched at first; three fixes (v0.5);
    21 / 21 since.
  - **Done 2026-09-28** (scripts/bulk/rating_calibration.py): 17 public US cases 2021–2026 (6 built, 5 community /
    zoning failures, 1 flood, 5 power stalls or cancellations). v0.5 missed community failures (Community was
    supporting, so a 2 never moved a site) and site-invisible utility constraints. v0.6 fixes both: community
    failures 4 / 5 Low, power failures 3 / 4 Low (the fourth had committed power and got partial power), flood
    screened out, no built project Low. No built project reaches High from public facts (committed power and flood
    are rarely public, so the screener cap holds them at Medium). Limits: small sample, few clean small-site
    failures in public sources, rated with the outcome known (hindsight risk).
- **Sensitivity:** move each threshold and the ceiling rules a step; which ratings flip?
  - **Done 2026-09-28** (rating_sensitivity.py on test batch 1): one notch on the time windows, MW steps or land factor
    moves at most one site; the Texas grid-audit adjustment is the one large lever (6 sites at v1.0) - kept for now.
- **Consistency:** an independent in-session pass rates the same sites from the rubric cards alone; compare.
  - **Done 2026-09-28**: a separate rater, blind to our ratings and code, agreed on the priority of all 25 sites;
    dimension differences traced to wording gaps, closed by the 14 application rules (§4.6).
- **Trial:** test batch 1 (25 rows); review; version 1.0; then build into the pipeline (spec, ratings.csv, a fixed
  Ratings section in the summary memo, a check that refuses ratings missing evidence, reason or confidence, or
  breaking a cap).
  - **Done 2026-09-28**: `rate.py` writes `<batch>/Supporting outputs/ratings.csv`; `rating_check.py` refuses a rating missing its
    confidence or reason, above its confidence cap, with a priority the rules do not give, with an adjustment
    without a reason, from another method version or against a changed location status (it caught four
    deliberate faults); the summary memo opens with "Priority ratings" (by market, with a total) and carries
    Appendix D, ratings by site (MEMOS.md §3).

## 6. Open items
0. To confirm with Mike: Investment to ready cost bands and typical costs; no building in any flood zone (screener and Land); the 1.0 ac minimum for 2 MW modular (evidence
   supports ~0.5 ac inside a larger parcel).
1. Carrier diversity (Mike): one carrier with two diverse routes vs two carriers for a 4.
2. To-do: add contaminated-site data (EPA Superfund, brownfields, leaking underground tanks) for the site-risk screener;
   add slope (USGS 3DEP) and soils (USDA SSURGO) for Land and buildability; split "LOI or negotiating" in the
   extraction vocabulary; add the FCC fiber-provider count (Esri Living Atlas BDC, H3 res. 8) as a producer; add
   nearest-residence distance (FEMA USA Structures); formalise the local headlines search.
3. Local headlines search: a repeatable in-session procedure (source, date window, what counts).
4. Baxtel planned developments: manual for now.

## Appendix: limitations (to complete with the method)
- Evidence is mostly broker-supplied; our checks use free public data (HIFLD substations are from 2021).
- The tool does not estimate deliverable MW; power ratings rest on what the broker and utility state.
- Zoning, community stance and incentives are rarely available from free sources.
- Ratings are as of their date; broker positions and utility capacity change.
