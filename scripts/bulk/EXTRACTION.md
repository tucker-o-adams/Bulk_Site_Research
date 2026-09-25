# Broker-text extraction: the procedure

How a broker list with free-text cells becomes structured evidence and location clues. Decided 2026-09-24
(Tucker): the reading is done **by Claude in a Claude Code session** (covered by the subscription), not by an
automated API call. Scripts do everything deterministic around it and refuse to continue on a bad reading.
Design background: `design_incomplete_inputs.md` (local, not in git).

## The steps

| # | Step | Who | Command / file | Gate |
|---|---|---|---|---|
| 1 | **Column map**: which broker column (and detail-sheet key) feeds which dimension, how confidence tags normalise | Claude drafts, **Tucker checks** | `<Portfolio> site data/column_map.json` | Every header is mapped or listed in `ignore_columns`; the script refuses otherwise |
| 2 | **Dump the cells** | script | `extract_cells.py <column_map> --out Outputs/<batch>/input/` → `site_list.csv`, `cells.csv` | — |
| 3 | **Read the cells** into evidence rows and location clues | **Claude, in session** | writes `input/broker_evidence.csv`, `input/location_clues.csv` | — |
| 4 | **Check the reading** | script | `extract_check.py Outputs/<batch>/input/` → `evidence_checked.csv`, `clues_checked.csv`, `extract_check.json` | **0 errors**. Every quote verbatim in its cell; vocabulary; numbers parse; every site × dimension with text has a row |
| 5 | **Locate** | script | `locate.py Outputs/<batch>/input/ --state TX` → `sites_in.csv`, `locate.json` | Refuses unless step 4 passed |
| 6 | Run, workbook, KMZ | scripts | `run.py --sites Outputs/<batch>/input/sites_in.csv --out Outputs/<batch>/`, `excel.py`, `kmz.py` | Zero `failed` |
| 7 | **Memo narrative** (summary memo): about half a page, portfolio facts only, no verdicts (MEMOS.md §5) | Claude, in session | `input/memo_narrative.md` | Every number in it must match the memos' computed facts |
| 8 | **Memos** | script | `memo.py Outputs/<batch>/ --name <Title>` → `<Title>_confirmation_memo.docx`, `<Title>_summary_memo.docx`, `broker_summary.csv` | Refuses unless step 4 passed and the parcel checks carry statuses |

## Column map (`column_map.json`)

```json
{
 "source": "<Portfolio> site data/<broker file>.xlsx",
 "default_state": "TX",
 "table": {"sheet": "...", "header_first_cell": "SITE ID", "id_column": "SITE ID", "name_column": "SITE", "skip_id_regex": "^Total"},
 "tag_pattern": "\\[([^\\]]+)\\]\\s*$",
 "tag_levels": [["^Confirmed,\\s*(pre-)?screen", "confirmed_prescreen"], ["^Confirmed", "confirmed_written"], ...],
 "columns": {"MW AVAILABLE": ["power_capacity"], "LAT / LONG · CITY · ZIP": ["location"], ...},
 "ignore_columns": [],
 "detail": [{"sheet": "...", "title_regex": "^(\\S+) · ", "keys": {"Grid power": ["power_connection", "grid_constraints"], ...}}]
}
```

- Rows whose name cell is empty are **section banners** (a market); each site gets the banner above it.
- The **site name** is always dumped as a `location` cell: names carry clues (e.g. "Oak Sub (Town / Main St & 2nd St)").
- `tag_levels` map the broker's own confidence tags onto one scale, strongest first:
  `confirmed_written` > `confirmed_prescreen` > `utility_estimate` > `broker_estimate` > `pending` (> `untagged`). An unmapped tag stops the dump.
- A column can feed several dimensions (grid constraints hide in "Grid power", "New generation" and "Schedule").

## Reading the cells (step 3)

Vocabulary: `extraction_vocab.json` (dimensions, fields, units, kinds, clue types). Add to it deliberately, never per batch.

**`broker_evidence.csv`**: `site_id, dimension, field, value, unit, kind, quote, source_cell, note`
- `quote` is the shortest verbatim fragment of the cell that supports the value. Nothing typed from memory: the check refuses it.
- `kind`: `actual` / `target` ("~20 ac target", "2029 target", a request) / `range_low` / `range_high` / `text`. A search target is never an actual.
- Numbers in the vocabulary's unit (`MW`, `kV`, `ac`, `ft`, `USD`, `c/kWh`, ...). Keep the broker's words in `note` when the number loses meaning.
- `none_stated` (no quote needed) records "read every cell, nothing on this dimension". Use it for `grid_constraints` and `flood_wetlands`, which are usually silent: silence is **not provided**, never "none".
- A fact found outside its expected column is fine (a warning, not an error): cite the cell it is in.
- Site control is a deal fact (`site_control.stage`: `under_contract`, `loi_or_negotiating`, `owner_identified`, `tract_identified`, `no_site_yet`, `no_site_control`); it is reported beside the evidence, never scored with it.
- Fiber quotes are broker-stated evidence (carrier, level, date, route lengths, NRC/MRC), never a fiber-proximity number.

**`location_clues.csv`**: `site_id, clue_type, value, quote, source_cell, note`. Clue types (vocab): `coordinate`,
`coordinate_approx`, `apn`, `street_address`, `intersection` ("A & B, City, ST"), `substation_name` (existing),
`substation_planned`, `landmark` (a named business or park: geocodable), `area_name` (a district or base: context
only, never geocoded), `owner_name`, `corridor`, `city`, `zip`, `county`, `state`, `utility`, `acreage`.
Give `value` in a form a resolver can use (a full address, "Main St & 2nd St, Town, ST") even when the quote is shorter.

**Working pattern that saves most of the effort:** many cells are copied across sites (`dup_n` in `cells.csv`; 330 of
650 in the first batch). Read each distinct text once, keyed by its first cell, and write the same rows for every copy with that
copy's own `source_cell`. Keep the reading script with the batch's data folder (not in git).

## What `locate.py` does with the clues

Best tier among candidates that land in the stated county (an anchor within its radius of the county line also passes);
each candidate also reports whether it is in the stated ZIP.

| Tier | From | Radius |
|---|---|---|
| L1 | APN found in a registered county parcel service that accepts attribute queries | 50 m |
| L2 | broker coordinate; `coordinate_approx`; Census-geocoded street address | 100 / 500 / 100 m |
| L3 | existing substation by name in HIFLD (must be unique in the county); intersection computed from Census TIGER roads inside the ZIP; landmark via OpenStreetMap Nominatim (1 req/s) | 2 km |
| L4 | ZIP (ZCTA) centroid | from ZIP area |
| L5 | county centroid | from county area |

Planned substations, owner/tract names, corridors and area names are listed as unresolved clues for the memo's
verification section. `run.py` then runs only what the tier supports (`tiers.py`): L1-L2 everything; L3 power, metro,
data centres, housing (area context); L4 metro, data centres, housing; L5 metro, data centres. The rest are
`not_assessable`. No area-level flood or wetland statistics at any tier.

## Effort, first batch (25 sites, 650 cells)

Column map ~5 min; reading ~25 min (the de-duplicated worklist is ~320 distinct texts); check passed first time
(then verified by planting three errors, all caught); locate ~2 min of machine time plus one round of fixes.
