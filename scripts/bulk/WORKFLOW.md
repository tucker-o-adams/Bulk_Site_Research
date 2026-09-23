# Operating workflow — DRAFT v0.1 (2026-09-23)

Our working hypothesis of how a portfolio moves through the tool, end to end. **Internal draft: not yet
shared with Mike.** The thresholds template goes to him as part of this, not on its own (BACKLOG 9d).

The one rule the order exists to protect: **thresholds are set from the product requirement and approved
before any site in the batch is looked at** — never tuned to the batch's own numbers (BACKLOG 9b).

| # | Step | Who | In → out | Gate before the next step |
|---|---|---|---|---|
| 1 | **Intake** | Tucker | Broker list as received → saved unchanged in `<Portfolio> site data/`, with who sent it and when | We know what each column means |
| 2 | **Define the product** | Mike + Tucker | Target MW, product type (edge / hyperscale / ...), minimum and typical acreage → a short portfolio brief | Brief agreed |
| 3 | **Set thresholds** | Tucker drafts, Mike approves | Brief → knockout and review rules per field (flood zone, SFHA %, wetland %, distance to substation/line and voltage, schools / housing nearby, ...) as a dated thresholds file | **Mike's approval, before step 6.** Until `flags.py` exists, the rules are applied by hand in step 7 |
| 4 | **Prepare the input** | Tucker | Broker list → pipeline CSV (`site_id`, `lat`, `lng`, plus `acres_stated`, `state`, `address`, `apn` if given). `geocode.py` for an address-only list; check every `Non_Exact` match | No unexpected rejected rows |
| 5 | **Check sources and coverage** | Tucker | `check_sources.py` (drift since last batch); for any new state, `reference/sweep_statewide_parcels.py` | Drift reviewed; parcel coverage known per state (sites in unregistered counties get the square around the pin) |
| 6 | **Run** | Tucker | `run.py` → rerun until `run.json` shows no `failed` → `excel.py`, `kmz.py` | Zero `failed`; `absent` is an answer, not a gap |
| 7 | **Screen** | Tucker | Workbook + approved thresholds → GO / REVIEW / NO-GO per site, with the reason and source. Standing rules: a wetland hit from stale NWI mapping (`STALE MAPPING` note) is REVIEW, never NO-GO; `parcel_owner_check` = `review` means confirm the parcel before trusting its acreage | Every NO-GO names the rule that fired |
| 8 | **Review the survivors** | Tucker (+ Mike on the close calls) | GO + REVIEW sites → KMZ fly-through (flood, wetlands, neighbours on by default; power folders on demand); current imagery for stale-NWI and flood-edge cases; **Baxtel map opened on Baxtel's site for context — looked at, not copied into any deliverable** (no export rights) | Shortlist (~20 of 200) |
| 9 | **Deepen the shortlist** | Tucker | Register parcel services for the shortlist's counties only (survivor-only economics); rerun; `figure.py --only` for flood and wetland exhibits | Every shortlist site has a parcel or a stated reason why not |
| 10 | **Deliver and archive** | Tucker → Mike | Workbook, KMZ, exhibits, a one-page note (method, thresholds version, what is unknown and why); zip `data/cache` for the batch | — |

## What is deliberately not in the tool (say so, don't improvise)

- **Deliverable MW / power availability.** Proximity facts only (substation and line distance, voltage,
  status). Capacity is a utility study; demand/generation/congestion is Phase 2.
- **Baxtel data.** Context during review only (step 8).
- **County politics, incentives, moratoriums.** Outside the free sources.
- **Jurisdictional wetland or flood determinations.** NWI and NFHL are screening layers.

## Open questions for the draft

1. Does step 2 happen per portfolio or per broker batch (Ozinga may send several)?
2. Who owns step 3 when Mike is unavailable — do we screen with provisional thresholds marked as such, or wait?
3. Is the step 10 note one page per batch, or per shortlisted site?
4. ~~For the new-sites test: skip step 3 approval (thresholds provisional, flagged), or hold for Mike?~~
   **Decided 2026-09-23 (Tucker): wait for Mike.** The test runs steps 1 and 4–6 only (intake, input,
   sources, run, workbook/KMZ). No screening — no GO / REVIEW / NO-GO, no provisional thresholds — until
   Mike approves thresholds.
