# Product profile: the per-portfolio limits file (template, 2026-10-07)

Every portfolio gets one profile before any site is scored (WORKFLOW steps 2–3). It says what the client
needs on a site, and turns that into the limits the screen applies. First used 2026-10-07 for an owner's parcel
portfolio (modular data center pods); that profile stays in its batch folder, outside git.

**Where it lives:** `Outputs/<batch>/input/thresholds.md`, versioned with a change log. Mike approves it
before step 6. Later, `flags.py` (BACKLOG 9b) reads its values.

**Every limit carries its basis**, one of:

| Label | Meaning |
|---|---|
| decided | Tucker or Mike chose it (name and date) |
| client terms | from the client's or tenant's term sheet, spec or lease draft |
| sourced | a published ordinance, study or tariff, linked in Sources |
| derived | computed from the above (show the arithmetic) |
| hypothesis | our estimate, to confirm |

## Step 2 checklist: questions to answer before drafting limits

Ask these of the client's documents first. Ask a person only for what the documents don't settle.

1. **Product.** What is built (modular pods, a building, a substation yard)? Who is the tenant?
2. **Target MW per site** and the smallest site worth keeping.
3. **Density:** MW per acre, so pad acres = MW ÷ density.
4. **Land available:** all of the owner's land, or only some (site control agreement)?
5. **"Empty" land:** what rules land out (buildings, active pits, stockpiles, water, steep ground)?
6. **One block or patches:** must the pad be contiguous? Minimum width?
7. **Setbacks:** from homes and other sensitive receptors (schools, worship, healthcare), and from the site's outer edge - by what is next door (road frontage, industrial neighbor, anything else). How loud is the product? Lean conservative when the client says loud.
7a. **What counts as a home:** which building tags (Residential; untagged ones only if house-sized?), the smallest size that is a home and not a shed, and what to do with homes on the site itself (counted, or flagged for review).
8. **Power:** service voltage, who pays the hookup charge (CIAC) and up to what cap. Is there a large-load threshold? Which line and substation voltages count, and is distance measured from where a pad could go (usable land)? How wide a right-of-way under lines is excluded?
9. **Flood and wetlands:** a knockout, or just subtracted from usable land?
10. **Fiber:** screened now or later?
11. **Groups:** does the client sort sites (e.g. fits / can expand / outside)? Define each group in measurable terms.
12. **Site grouping:** for owner parcel lists, the gap for merging nearby parcels into one site (`group_parcels.py --gap`).

## Template

The run reads the profile's first ```json block (`product_profile.py` lists the keys and defaults):
`run.py --profile Outputs/<batch>/input/thresholds.md` adds the usable-land producer and sets the home distances.

```
# <Portfolio>: screening limits (DRAFT v0.1, <date>)
Status: draft for Mike's approval. Nothing is screened against these until he approves.

## 0. Values the run reads   a ```json block; every key, its meaning and default: product_profile.py
                             (the Amrize profile is a complete worked example)

## 1. Product basis        target MW, density, pad acres, service voltage, hookup cap, land available, skipped topics
## 2. Usable land          exclusions (buildings, flood, wetlands, pits, slope, line right-of-way, edge setback by neighbor) + pad rules (one block, min width)
## 3. Noise / receptors    PASS / REVIEW / NO-GO distances, receptor list, what counts as a home (tags, sizes, on-site), why
## 4. Power                PASS / REVIEW / NO-GO rules, voltages, measured from (usable land / site edge), the cost arithmetic
## 5. Site grouping        gap, resulting site count
## 6. Groups               rule per group (if the client uses groups)
## Open items
## Sources                 one line per source: what it says, link
## Change log
```

Reusable evidence for limits (noise, setbacks, line costs, feeder limits) is collected in `LIMIT_SOURCES.md`.
