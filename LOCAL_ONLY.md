# Local-only files (on disk, not in git)

Generated 2026-09-22T13:22+00:00 by `scripts/local_only_inventory.py` from `git ls-files --others --ignored`. Re-run it after any batch or fetch. These files exist only in this working copy; back up the ones marked worth archiving by some other means.

**Total: 13979 files, 1.18 GB**

| Path | Files | Size | Largest file | What it is / how to regenerate |
|---|---|---|---|---|
| `.venv_fema` | 10487 | 529.2 MB | 92.5 MB `node.exe` | Python environment. Rebuild: python -m venv .venv_fema; pip install -r requirements-fema.txt -r requirements-bulk.txt |
| `data/cache` | 3450 | 315.4 MB | 12.3 MB `38.57342_-82.83963_near500.json` | Raw service responses (FEMA NFHL, USFWS NWI, HIFLD) keyed by coordinate; what makes pipeline reruns offline. Re-fetchable from source with scripts/bulk/run.py, but a source that has since changed or vanished cannot be re-fetched — this is the evidence trail worth archiving. Some NWI files exceed 100 MB. |
| `Reference/FEMA-Toolkit` | 2 | 187.4 MB | 141.2 MB `fema-flood-figure-toolkit.zip` | Toolkit zips: superseded by out/ and tbdi-pasa; the README is committed. Low value. |
| `out` | 9 | 143.9 MB | 48.8 MB `naip_site2.tif` | FEMA flood-figure pipeline rasters/PNGs/GPKGs; rebuilt by the out/*.py scripts from NAIP/NFHL. Medium value (slow to rebuild). |
| `Outputs/KMZ outputs/WS_Sites_and_Transmission_3.kmz` | 1 | 637 KB | 637 KB `WS_Sites_and_Transmission_3.kmz` | Pipeline intermediate; rebuilt by scripts/windstream_kmz/run_pipeline.py in seconds. |
| `scripts` | 29 | 195 KB | 13 KB `parcel.cpython-312.pyc` | Python __pycache__ only. Nothing to save. |
| `.claude` | 1 | 0 KB | 0 KB `settings.local.json` | Claude Code per-machine permission settings. Nothing to save. |

## Worth archiving outside git

- **`data/cache/`** — the raw responses behind every value in `Outputs/*/provenance.csv`. Re-fetchable today; not re-fetchable if a source changes (county parcel services have already vanished once). Suggested: zip per batch to OneDrive/Drive after each clean run.
- **`out/`** — slow-to-rebuild FEMA figure rasters. Optional.

Everything else in the table is either rebuildable in seconds or not project data.
