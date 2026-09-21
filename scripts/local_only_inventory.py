# -*- coding: utf-8 -*-
"""Write LOCAL_ONLY.md: everything in this working copy that git ignores, so it
can be backed up some other way. Re-run after any batch or fetch:

    .venv_fema/Scripts/python.exe scripts/local_only_inventory.py

The list comes from git itself (`git ls-files --others --ignored --exclude-standard`),
so it cannot drift from .gitignore. Files are grouped by their top-level ignored
path; a HOW_TO_REGENERATE note is kept here per group.
"""
import os, subprocess, sys
from collections import defaultdict
from datetime import datetime, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
OUT = os.path.join(ROOT, 'LOCAL_ONLY.md')

# how each ignored group can be rebuilt, or why it cannot
REGEN = {
    'data/cache': ('Raw service responses (FEMA NFHL, USFWS NWI, HIFLD) keyed by coordinate; what makes '
                   'pipeline reruns offline. Re-fetchable from source with scripts/bulk/run.py, but a '
                   'source that has since changed or vanished cannot be re-fetched — this is the evidence '
                   'trail worth archiving. Some NWI files exceed 100 MB.'),
    '.venv_fema': 'Python environment. Rebuild: python -m venv .venv_fema; pip install -r requirements-fema.txt -r requirements-bulk.txt',
    'Reference/FEMA-Toolkit': 'Toolkit zips: superseded by out/ and tbdi-pasa; the README is committed. Low value.',
    'out': 'FEMA flood-figure pipeline rasters/PNGs/GPKGs; rebuilt by the out/*.py scripts from NAIP/NFHL. Medium value (slow to rebuild).',
    'Outputs/KMZ outputs/WS_Sites_and_Transmission_3.kmz': 'Pipeline intermediate; rebuilt by scripts/windstream_kmz/run_pipeline.py in seconds.',
    'Windstream site data': 'Excel lock file only (~$...). Nothing to save.',
    'scripts': 'Python __pycache__ only. Nothing to save.',
    '.claude': 'Claude Code per-machine permission settings. Nothing to save.',
}


def main():
    res = subprocess.run(['git', 'ls-files', '--others', '--ignored', '--exclude-standard', '-z'],
                         cwd=ROOT, capture_output=True, check=True)
    paths = [p for p in res.stdout.decode('utf-8', 'replace').split('\0') if p]
    groups = defaultdict(lambda: {'n': 0, 'bytes': 0, 'largest': (0, '')})
    total = 0
    for p in paths:
        full = os.path.join(ROOT, p)
        try:
            sz = os.path.getsize(full)
        except OSError:
            continue
        parts = p.split('/')
        key = parts[0] if len(parts) == 1 or parts[0] not in ('Reference', 'Outputs', 'data') else '/'.join(parts[:2])
        if key.startswith('Outputs/') and len(parts) > 2 and parts[1] == 'KMZ outputs':
            key = p
        g = groups[key]
        g['n'] += 1; g['bytes'] += sz; total += sz
        if sz > g['largest'][0]:
            g['largest'] = (sz, p)

    def fmt(b):
        return f'{b/1e9:.2f} GB' if b >= 1e9 else f'{b/1e6:.1f} MB' if b >= 1e6 else f'{b/1e3:.0f} KB'

    lines = ['# Local-only files (on disk, not in git)', '',
             f'Generated {datetime.now(timezone.utc).isoformat(timespec="minutes")} by '
             '`scripts/local_only_inventory.py` from `git ls-files --others --ignored`. '
             'Re-run it after any batch or fetch. These files exist only in this working copy; '
             'back up the ones marked worth archiving by some other means.', '',
             f'**Total: {len(paths)} files, {fmt(total)}**', '',
             '| Path | Files | Size | Largest file | What it is / how to regenerate |', '|---|---|---|---|---|']
    for key in sorted(groups, key=lambda k: -groups[k]['bytes']):
        g = groups[key]
        note = next((v for k, v in REGEN.items() if key == k or key.startswith(k + '/') or key.startswith(k)), 'not documented — add to REGEN in the script')
        lines.append(f"| `{key}` | {g['n']} | {fmt(g['bytes'])} | {fmt(g['largest'][0])} `{os.path.basename(g['largest'][1])}` | {note} |")
    lines += ['', '## Worth archiving outside git', '',
              '- **`data/cache/`** — the raw responses behind every value in `Outputs/*/provenance.csv`. '
              'Re-fetchable today; not re-fetchable if a source changes (county parcel services have already '
              'vanished once). Suggested: zip per batch to OneDrive/Drive after each clean run.',
              '- **`out/`** — slow-to-rebuild FEMA figure rasters. Optional.',
              '', 'Everything else in the table is either rebuildable in seconds or not project data.']
    with open(OUT, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(lines) + '\n')
    print(f'wrote {OUT}: {len(paths)} files, {fmt(total)} across {len(groups)} groups')
    return 0


if __name__ == '__main__':
    sys.exit(main())
