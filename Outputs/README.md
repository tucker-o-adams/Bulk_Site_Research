# Outputs

| Folder | Status | What it is |
|---|---|---|
| `windstream-200/` | **current** | Bulk pipeline run on the 200 Windstream COs (`scripts/bulk/fixtures/windstream_200.csv`): `Windstream_Top200_Site_Research.xlsx` + `.kmz`, `sites.csv`, `provenance.csv`, `run.json`, and exhibits in `figures/` |
| `mireye-screen-10/` | current (validation) | Bulk pipeline on the 10 sites of the Aug 2026 Mireye screen (`fixtures/mireye_screen_10.csv`), for comparing free-source values with Mireye's |
| `parcel-test/` | test | Parcel producer test output (2026-09-22); not a deliverable |
| `Excel outputs/`, `KMZ outputs/` | **superseded** (Aug 2026) | Before the pipeline: the Mireye site screen workbook, Windstream parcel sizes, power and transmission CSVs, and the Combined KMZs from `scripts/windstream_kmz/`. `WS_Top200_Transmission_Distance.csv` is the transmission regression's origin (a frozen copy lives in `scripts/bulk/fixtures/`) |

Batch outputs are regenerated from `data/cache` by `scripts/bulk/run.py`, `excel.py` and `kmz.py`;
site exhibit PNGs (`figures/*.png`, 10–14 MB each) are not committed.
