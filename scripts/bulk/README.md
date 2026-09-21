# scripts/bulk — bulk site research pipeline

CSV of sites in → per-site fields with provenance out (Excel + KMZ to follow).
Free/public sources only, by decision (2026-09-21): no Mireye, no paid APIs.

```
.venv_fema/Scripts/python.exe scripts/bulk/run.py --sites <in.csv> --out Outputs/<batch>/
```

## Input contract

One CSV, one row per site.

| Column | Required | Notes |
|---|---|---|
| `site_id` | yes | unique key; Windstream uses the CLLI |
| `lat`, `lng` | yes | WGS84 decimal degrees; rows outside the US are rejected (lat/lng swapped?) |
| `name`, `address`, `apn`, `acres_stated`, `state`, `county`, `group`, `notes` | no | understood and carried through; `group` drives KMZ folder splits |
| anything else | no | passed through untouched to `sites.csv`, never interpreted |

Rejected rows are listed with a reason in the console and in `run.json`, never dropped silently.

## Outputs (`--out`)

| File | Contents |
|---|---|
| `sites.csv` | one row per site: input columns, then every producer field |
| `provenance.csv` | one row per site × field: `value, status, source, source_url, vintage, fetched_at, method, note` |
| `run.json` | input path + sha256, rejected rows, per-producer source/vintage/status tallies, cache hits/misses |
| `cache/<producer>/<site_id>.json` | the raw service response; a rerun is offline and reproduces the first run exactly. Delete to refresh from source. |

`status` is one of `ok`, `absent` (source confirmed nothing there — an answer, not an error),
`failed` (source unreachable; value null), `manual` (supplied by a person).

## Producers

| Producer | Fields | Source | Status |
|---|---|---|---|
| `transmission` | `tx_nearest_m/ft, tx_voltage_kv, tx_volt_class, tx_voltage_basis, tx_line_name, tx_line_id, tx_owner, tx_type, tx_status, tx_attrs_inferred, tx_100kv_*` | HIFLD US Electric Power Transmission Lines — ArcGIS mirror of the dataset DHS retired Aug 2025; data last edited 2025-08-26. 15 km query, exact point-to-segment distance. | **regression-proven** (below) |

Planned, same frame: `substations` (HIFLD mirror), `flood` (FEMA NFHL point + mapped-coverage check),
`wetlands` (USFWS NWI), `metro` (Census TIGERweb urban areas, straight-line), `datacenter`
(PeeringDB KMZ, straight-line), `parcel` (county/state GIS, per-county registry). Then `flags`
(go/no-go rules as data), `excel`, `kmz`.

A producer never raises on a bad source answer: it returns `absent`/`failed` values with a note.

## Regression fixture

`fixtures/windstream_200.csv` — the 200 Windstream COs in the input format
(built by `fixtures/make_windstream_fixture.py` from the broker workbook + KMZ;
`group` = Interesting / Other).

`fixtures/check_windstream_transmission.py Outputs/windstream-200/sites.csv` compares the
transmission producer against `Outputs/Excel outputs/WS_Top200_Transmission_Distance.csv`
(the Aug 2026 `tx_distance.py` output). **2026-09-21: 200/200 match** on line ID, distance,
owner, and the ≥100 kV line. One deliberate difference: the old CSV carried HIFLD's
`-999999` "not published" sentinel as a voltage; the producer normalizes it to null.

Every new producer gets the same treatment: a fixture run and a check against a known answer
before it is trusted.

## Requirements

`.venv_fema` plus `requirements-bulk.txt` (openpyxl). Standard library otherwise.
