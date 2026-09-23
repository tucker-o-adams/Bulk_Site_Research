# TBDI data center site screening

Screening broker batches of candidate data center sites before physical diligence: power
proximity, flood, wetlands, neighbours, parcels — every value with its source, vintage and status.

**The current tool is the bulk pipeline in [`scripts/bulk/`](scripts/bulk/README.md)** — free/public
sources only; CSV of sites in, workbook + Google Earth KMZ + site exhibits out. Start with its
README ("Running a batch, end to end"); planned work and source fallbacks are in
[`scripts/bulk/BACKLOG.md`](scripts/bulk/BACKLOG.md).

| Path | What it is |
|---|---|
| `scripts/bulk/` | **the pipeline** (run.py, producers, excel.py, kmz.py, figure.py, geocode.py, check_sources.py) |
| `data/reference/` | parcel service registry, CMS reference files, source baseline — committed |
| `data/cache/` | raw service responses behind every value — on disk only, see `LOCAL_ONLY.md` |
| `Outputs/` | batch outputs; `Outputs/README.md` says which are current |
| `Windstream site data/` | the Windstream broker workbook and files derived from it |
| `Reference/` | PeeringDB export, meeting transcripts, trackers, toolkits |
| `scripts/windstream_kmz/`, `out/`, `results.md`, `network-test.txt` | Aug 2026 work that preceded the pipeline (Windstream KMZ/power analysis, FEMA figure environment test) — kept as history |
| `CLAUDE.md`, `tbdi-setup-guide.md` | the Mireye (paid MCP) screening guide and setup — a separate route from the free pipeline, which uses no Mireye |

Requirements: `requirements-bulk.txt` (see the pipeline README).
