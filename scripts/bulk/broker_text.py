# -*- coding: utf-8 -*-
"""What the broker says about where a site is, verbatim - shared by the exhibits (figure.py) and the memo (memo.py),
so both quote exactly the same words from the broker list (input/cells.csv, EXTRACTION.md)."""
import csv, os, re


def broker_words(batch, sid):
    """The site name, the location cells, the acreage cells, any other cell a location clue was read from, and the one
    grid-power sentence that names a substation (why a site name like 'Treaschwig Rd' is read as a substation).
    Returns [(label, text)] with duplicates removed."""
    inp = os.path.join(batch, 'input')
    cf, lf = os.path.join(inp, 'cells.csv'), os.path.join(inp, 'clues_checked.csv')
    if not os.path.exists(cf):
        return []
    cells = [c for c in csv.DictReader(open(cf, encoding='utf-8-sig')) if c['site_id'] == sid and c['text']]
    cited = {r['source_cell'] for r in csv.DictReader(open(lf, encoding='utf-8-sig')) if r['site_id'] == sid} if os.path.exists(lf) else set()

    def order(c):
        is_name = c['dimensions'] == 'location' and c['text'] == c['name']
        return (0 if is_name else 1 if 'location' in c['dimensions'] else 2 if 'acreage' in c['dimensions'] else 3, c['sheet'] != 'Site Matrix')
    grid = [c for c in cells if 'grid' in c['column'].lower() and re.search(r'\bsub(station)?s?\b', c['text'], re.I)]
    grid = sorted(grid, key=lambda c: c['sheet'] != 'Site Matrix')[:1]
    pick = [c for c in cells if 'location' in c['dimensions'] or 'acreage' in c['dimensions'] or c['source_cell'] in cited] + \
           [c for c in grid if c['source_cell'] not in cited]
    out, seen = [], set()
    for c in sorted(pick, key=order):
        key = re.sub(r'\W+', ' ', c['text']).strip().lower()
        if key in seen or any(key in s_ for s_ in seen):
            continue
        seen.add(key)
        label = c['column'].title().replace('Lat / Long · City · Zip', 'Location').replace('Mw', 'MW').replace('Poi', 'POI')
        out.append((f"{label} ({c['sheet']})", ' / '.join(x.strip() for x in c['text'].splitlines() if x.strip())))
    return out
