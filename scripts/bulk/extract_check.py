# -*- coding: utf-8 -*-
"""Step 3 of broker-text extraction: check Claude's reading of the cells before anything uses it.

    .venv_fema/Scripts/python.exe scripts/bulk/extract_check.py Outputs/<batch>/input/

Reads cells.csv + site_list.csv (extract_cells.py) and the two files Claude writes by reading the cells
(EXTRACTION.md): broker_evidence.csv and location_clues.csv. Refuses (exit 1) on any error:

  * every row names a known site, a vocabulary dimension/field/unit/kind (extraction_vocab.json), and a
    source_cell that exists for that site
  * every quote appears verbatim in its source cell (whitespace and case aside) - nothing typed from memory
  * numeric fields parse; enum fields use an allowed value
  * coverage: every site x dimension that has any text in the cells has at least one row (a
    `none_stated` row records "read it, nothing on this dimension" - grid constraints are usually absent)

Writes evidence_checked.csv and clues_checked.csv: the rows plus what the script, not Claude, derives from
the source cell (tag_raw, tag_norm, dup_n, dup_sites, column, section), and extract_check.json.
"""
import argparse, csv, json, os, re, sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
VOCAB = json.load(open(os.path.join(HERE, 'extraction_vocab.json'), encoding='utf-8'))
EVIDENCE_COLUMNS = ['site_id', 'dimension', 'field', 'value', 'unit', 'kind', 'quote', 'source_cell', 'note']
CLUE_COLUMNS = ['site_id', 'clue_type', 'value', 'quote', 'source_cell', 'note']
DERIVED = ['section', 'column', 'tag_raw', 'tag_norm', 'dup_n', 'dup_sites']
_QMAP = str.maketrans({'‘': "'", '’': "'", '“': '"', '”': '"', '–': '-', '—': '-', '×': 'x'})


def norm(s):
    return re.sub(r'\s+', ' ', (s or '').translate(_QMAP)).strip().casefold()


def read(path):
    with open(path, encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def check_value(dim, fld, r, err):
    spec = VOCAB['dimensions'][dim]['fields'].get(fld)
    if fld == 'none_stated':
        return
    if spec is None:
        err(f"field {fld!r} not in dimension {dim!r} (allowed: {sorted(VOCAB['dimensions'][dim]['fields'])})"); return
    if r['kind'] not in VOCAB['kinds']:
        err(f"kind {r['kind']!r} not in {sorted(VOCAB['kinds'])}")
    if isinstance(spec, list):
        if r['value'] not in spec:
            err(f"{dim}.{fld} value {r['value']!r} not in {spec}")
    elif spec == 'text':
        if not r['value']:
            err(f'{dim}.{fld} has no value')
    else:
        try:
            float(str(r['value']).replace(',', ''))
        except ValueError:
            err(f"{dim}.{fld} needs a number in {spec}, got {r['value']!r}")
        if r['unit'] != spec:
            err(f"{dim}.{fld} unit must be {spec!r}, got {r['unit']!r}")
        if r['kind'] == 'text':
            err(f'{dim}.{fld} is numeric: kind must be actual/target/range_low/range_high')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('input_dir')
    a = ap.parse_args()
    d = a.input_dir
    sites = {s['site_id']: s for s in read(os.path.join(d, 'site_list.csv'))}
    cells = read(os.path.join(d, 'cells.csv'))
    by_cell = {(c['site_id'], c['source_cell']): c for c in cells}
    errors, warnings = [], []
    out = {}
    for fname, cols, kind in (('broker_evidence.csv', EVIDENCE_COLUMNS, 'evidence'), ('location_clues.csv', CLUE_COLUMNS, 'clue')):
        path = os.path.join(d, fname)
        if not os.path.exists(path):
            errors.append(f'{fname}: missing (Claude writes it from cells.csv - EXTRACTION.md step 2)'); out[kind] = []; continue
        rows = read(path)
        if rows and list(rows[0].keys())[:len(cols)] != cols:
            errors.append(f'{fname}: columns must be {cols}, got {list(rows[0].keys())}')
        checked = []
        for n, r in enumerate(rows, 2):
            def err(m, n=n):
                errors.append(f'{fname} row {n} ({r.get("site_id")}): {m}')
            if r['site_id'] not in sites:
                err('unknown site_id'); continue
            c = by_cell.get((r['site_id'], r['source_cell']))
            if kind == 'evidence':
                dim, fld = r['dimension'], r['field']
                if dim not in VOCAB['dimensions']:
                    err(f'dimension {dim!r} not in vocabulary'); continue
                check_value(dim, fld, r, err)
                if fld == 'none_stated':
                    checked.append({**r, **{k: (c or {}).get(k, '') for k in DERIVED}}); continue
                if c and dim not in c['dimensions'].split(';'):
                    warnings.append(f"{fname} row {n} ({r['site_id']}): {dim} cited from column {c['column']!r}, which the map files under {c['dimensions']}")
            else:
                if r['clue_type'] not in VOCAB['clue_types']:
                    err(f"clue_type {r['clue_type']!r} not in {sorted(VOCAB['clue_types'])}"); continue
                if r['clue_type'].startswith('coordinate'):
                    try:
                        la, ln = (float(x) for x in r['value'].split(','))
                        assert -90 <= la <= 90 and -180 <= ln <= 180
                    except Exception:
                        err(f"coordinate must be 'lat,lng', got {r['value']!r}")
                if r['clue_type'] == 'zip' and not re.fullmatch(r'\d{5}', r['value']):
                    err(f"zip must be 5 digits, got {r['value']!r}")
                if r['clue_type'] == 'acreage':
                    try:
                        float(r['value'])
                    except ValueError:
                        err(f"acreage must be a number, got {r['value']!r}")
            if not c:
                err(f"source_cell {r['source_cell']!r} is not one of this site's cells"); continue
            if not r['quote']:
                err('empty quote')
            elif norm(r['quote']) not in norm(c['text']):
                err(f"quote not found verbatim in {r['source_cell']}: {r['quote'][:80]!r}")
            checked.append({**r, **{k: c.get(k, '') for k in DERIVED}})
        out[kind] = checked
    # coverage: every site x dimension with text somewhere must be read
    have = defaultdict(set)
    for c in cells:
        if c['text']:
            for dim in c['dimensions'].split(';'):
                have[c['site_id']].add(dim)
    got = defaultdict(set)
    for r in out.get('evidence', []):
        got[r['site_id']].add(r['dimension'])
    for r in out.get('clue', []):
        got[r['site_id']].add('location')
    for sid in sites:
        for dim in sorted(have[sid] - got[sid]):
            errors.append(f'coverage: {sid} has text for {dim} but no row (add rows, or a none_stated row)')
    for kind, fname, cols in (('evidence', 'evidence_checked.csv', EVIDENCE_COLUMNS), ('clue', 'clues_checked.csv', CLUE_COLUMNS)):
        with open(os.path.join(d, fname), 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.DictWriter(f, fieldnames=cols + DERIVED, extrasaction='ignore'); w.writeheader(); w.writerows(out.get(kind, []))
    rep = {'errors': errors, 'warnings': warnings, 'evidence_rows': len(out.get('evidence', [])), 'clue_rows': len(out.get('clue', [])),
           'sites': len(sites), 'ok': not errors}
    json.dump(rep, open(os.path.join(d, 'extract_check.json'), 'w', encoding='utf-8'), indent=1)
    for m in warnings[:20]:
        print('  warn ', m)
    for m in errors[:60]:
        print('  ERROR', m)
    print(f"{rep['evidence_rows']} evidence rows, {rep['clue_rows']} clue rows | {len(errors)} errors, {len(warnings)} warnings"
          + ('' if errors else ' | OK'))
    sys.exit(1 if errors else 0)


if __name__ == '__main__':
    main()
