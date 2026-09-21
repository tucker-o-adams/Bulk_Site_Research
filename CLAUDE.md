# Mireye instructions — TBDI data center site screening

> **How to install:** save this file as `CLAUDE.md` in the folder where you run Claude Code for site screening. Claude reads it automatically every session. (If a `CLAUDE.md` already exists there, append this to it.)

You (Claude) have the **mireye-earth** MCP server connected. Mireye returns authoritative geospatial data for any US coordinate or address — grid and power, flood, wetlands, hazards, soils, water/sewer, fiber, gas, parcels, zoning. **Every value carries `source`, `source_url`, `dataset_vintage`, `fetched_at`, and a `confidence` rating.** The citation chain is the product: never present a Mireye value without at least its source name.

TBDI's job: take a broker batch of candidate data center sites (currently Ohio and Iowa) and cut 200 sites down to ~20 before physical diligence. Sites in the batch are already fiber-connected and zoned appropriately, so those are context, not knockouts.

## Tools — when to use which


| Tool                                                   | Use for                                                                                                                                                                                                                                                          | Credits         |
| ------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------- |
| `mireye_lookup`                                        | **First call per site.** Address/coordinate/APN → resolved coordinate + parcel (id, boundary, owner) + flood zone + county market context. Check `disposition`: `resolved` / `clarify` (ambiguous — show the user the candidates, never auto-pick) / `no_match`. | ~301            |
| `mireye_fetch`                                         | Named fields and/or a preset at one location. The workhorse.                                                                                                                                                                                                     | 1/field         |
| `mireye_ask`                                           | One-off natural-language question with a cited prose answer. Good for verification and odd questions; don't use it for batch screening (nondeterministic field choice).                                                                                          | 10              |
| `mireye_geocode`                                       | Address → coordinate only. Usually superseded by `mireye_lookup`.                                                                                                                                                                                                | 1               |
| `mireye_proximity`                                     | Driving-time matrices, nearest-from-curated-set (`@airports`, `@substations`, `@power_plants`, `@rail`, `@ports`, `@urban_areas`), proximity screening, labor shed. Coordinates or full street addresses only — never place names.                               | 12/driving calc |
| `mireye_request_field` / `mireye_field_request_status` | Order a field that doesn't exist yet.                                                                                                                                                                                                                            | plan allowance  |


Authoritative preset expansions and field definitions: read the MCP resources `mireye://catalog/presets` and `mireye://catalog/fields` (or public `GET https://api.mireye.com/v1/meta/fields`). Don't trust remembered field lists — check the catalog when unsure, and use exact field names (`fema_flood_zone`, not `flood_zone`; `slope_degrees`, not `slope`; `nearest_substation_distance_m`, not `substation`).

Presets that matter here: `data_center_siting` (~106 fields), `natural_hazard` (17), `utilities` (27), `site_selection` (72, includes parcel + wetland-on-parcel + schools), `points_of_interest` (23), `grid_interconnect` (29). A preset plus explicitly named `fields` in the same call union together — do that.

## The per-site screening recipe

**Full screen** (~750–800 credits) — for the priority cut:

1. **`mireye_lookup(input=address)`** — pins the coordinate, returns parcel id/boundary/owner, FEMA flood zone, county market bundle. If `disposition` is `clarify`, stop and ask which candidate is right.
2. **`mireye_fetch(lat, lng, preset="data_center_siting", fields=[...])`** — one call, with these added explicitly: `developable_acres_proxy`, `wetland_acres_on_parcel`, `wetland_fraction_of_parcel`, `intersects_wetland`, `wetland_type`, `nearest_wetland_distance_m`, `parcel_zoning`, `parcel_area_m2`, `nearest_school_distance_m`, `nearest_school_name`.
3. **`mireye_fetch(lat, lng, preset="natural_hazard")`** — seismic, design wind, tornado/hail/lightning frequency, landslide, dams, karst. Not covered by the DC preset.
4. **`mireye_fetch(lat, lng, preset="utilities")`** — transmission line distance/voltage/owner, water & sewer service areas, wastewater plant.

**Billing rule, not an optimization:** the 17 parcel-record fields (`parcel_*`, `developable_acres_proxy`, `wetland_acres_on_parcel`, `wetland_fraction_of_parcel`, `onsite_solar_potential_*`) bill **300 credits once per request** that touches any of them. Put them all in ONE fetch call (step 2). Never split them across calls — each extra call re-bills the 300. (Step 1's lookup carries its own separate 300-credit parcel charge — that's deliberate: its ambiguity detection on messy broker addresses is worth it. Skip the lookup only when you already have a trusted coordinate.)

**Triage screen** (~110 credits) — for raw-batch sweeps (the 2,800-site ambition): skip the lookup and the parcel fields; run `data_center_siting` alone on a coordinate. Parcel geometry and buildable acres come later, only for survivors.

## Mapping TBDI's disqualifiers to fields


| TBDI filter                | Field(s)                                                                                                                                                                                                    |
| -------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Flood                      | `fema_flood_zone`, `within_floodplain_polygon` (zone X = minimal hazard; A/AE = knockout territory)                                                                                                         |
| Wetlands / buildable acres | `intersects_wetland`, `wetland_acres_on_parcel`, `wetland_fraction_of_parcel`, `developable_acres_proxy`, `parcel_area_m2`                                                                                  |
| Near schools               | `nearest_school_distance_m`, `nearest_school_name`                                                                                                                                                          |
| Neighborhood fit / "vibe"  | `residential_context_class_1km` (isolated/sparse/moderate/dense), `housing_units_within_1km`, `housing_units_density_per_km2`, plus the `points_of_interest` preset (23 credits) for what's actually nearby |
| Power proximity            | `nearest_substation_distance_m` / `_max_voltage_kv` / `_status`, `nearest_transmission_line_distance_m` / `_voltage_kv`, `interconnection_queue_active_capacity_county_mw`                                  |
| Utility                    | `electric_utility_service_territory`, `avg_retail_electricity_price_industrial_usd_per_kwh`                                                                                                                 |
| Site prep                  | `slope_degrees`, `grading_difficulty_class`, `soil_shrink_swell_class`, `soil_hydrologic_group`                                                                                                             |
| Water/sewer                | `within_water_service_area`, `within_sewer_service_area`, `nearest_wastewater_plant_`*                                                                                                                      |
| Environmental red flags    | `nearest_superfund_distance_m`, `nearest_hazardous_facility_*`, `open_lust_sites_within_1km_count`, air-quality nonattainment fields                                                                        |


**Churches are not a Mireye field.** Say so when asked; cover "bad neighbor" risk with residential context, housing density, schools, and the POI preset instead of guessing.

## Batch output format

For multi-site screens, produce a ranked table: **GO / REVIEW / NO-GO**, one row per site, with the specific reason ("Zone AE floodplain", "345 kV substation 4.1 km, in service", "dense residential 1 km") and source names. Under the table, list per-site anything that came back `absent`, `failed`, or low-confidence. Rank GOs by power proximity first (substation distance × voltage), then buildable acres, then residential context — unless the user says otherwise.

## Honesty rules

- `**status: "absent"` is an answer, not an error** — the source confirmed no data exists there (e.g. no transmission line within the radius). Report it as such; don't retry.
- **Check `partial_failures` on every fetch** — a 200 can still contain failed fields (they're auto-refunded). Retry once if `retryable: true`; otherwise report the gap. Never present a failed field as a value.
- **Never fabricate a value Mireye didn't return.** An honest "unknown" beats a guess, always.
- **Respect confidence:** `high`/`medium` are fine for screening; flag `low` explicitly when it's load-bearing for a verdict.
- `**electric_utility_service_territory` is the retail serving utility, NOT the transmission owner or interconnection counterparty.** In rural Ohio/Iowa it's often a co-op. Say "serving utility"; the interconnection conversation is with the transmission owner, and the real capacity number is a utility study.
- **Rural expectations (verified in Ohio):** fiber fields can be null in hexes with no broadband-serviceable locations (fine — these sites already have fiber); transmission-line fields come back `absent` when no line is within the search radius (a real finding, not a bug); the occasional federal upstream times out — retry it. Failed fields are auto-refunded.
- **Wetland-on-parcel fallback:** `wetland_acres_on_parcel` / `wetland_fraction_of_parcel` / `developable_acres_proxy` are heavy computations (USFWS wetlands × parcel geometry) and can time out on some parcels even on retry. When that happens, don't stall the screen: report `parcel_area_m2`, `intersects_wetland`, `wetland_type`, and `nearest_wetland_distance_m` (these return reliably), mark buildable acres "needs recheck," and move on. Retry the site later.

## What is NOT in the standard API (do not improvise these)

Three capabilities are contract-gated with Mireye and are **not** derivable from the fields above:

1. **Power availability estimate** — the deliverable-MW band. Do NOT construct a MW estimate from substation distance/voltage/queue fields; that's a proprietary multi-source model. Report the raw proximity facts and say the estimate is available under the Mireye contract.
2. **Owner contact finder** — owner names pierced through LLCs to real phones/emails. `mireye_lookup` returns the owner of record only; stop there.
3. **County friendliness** — moratoriums, town-hall sentiment, tax incentives, data-center-specific political read. `tax_incentive_stack` and `in_opportunity_zone` are the only incentive signals in the standard fields.

When the user asks for any of these, give what the standard fields honestly support, then note the gap: "the full [power estimate / owner contact / county read] is a Mireye contract capability — Ansh can turn it on."

## Credits

1 credit per field, 10 per `mireye_ask`. Balance: the Usage tab at mireye.com/account. Live prices: `GET https://api.mireye.com/v1/meta/plans`.

Full API reference (endpoints, batch, errors): **[https://docs.mireye.ai](https://docs.mireye.ai)** · agent-readable summary: **[https://mireye.com/skills.md](https://mireye.com/skills.md)**