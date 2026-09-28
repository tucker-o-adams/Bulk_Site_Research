# -*- coding: utf-8 -*-
"""Check a batch's ratings.csv before it is reported (design_site_rating.md §4.5-4.6). Refuses a rating that:
- is missing its confidence or its reason (the reason carries the evidence), or has a confidence outside the scale;
- shows a score above its confidence cap (high 5, medium 4, low 3, none = unknown) or outside 1-5;
- has a screener value outside passed / failed / not_assessed;
- has an indicated priority the rules (rating_rules.py) do not give from its own scores and screeners;
- has a named adjustment without a direction or a reason, or an assigned priority that does not follow from them;
- was made with another method version, or against a location status that has since changed (stale).
Indicated and assigned priorities that differ are listed for the second review (Tucker); they are not errors.

    .venv_fema/Scripts/python.exe scripts/bulk/rating_check.py Outputs/<batch>/

memo.py runs the same check and will not write the summary memo from a ratings.csv that fails it.
"""
import os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rating_rules import CAP, METHOD_VERSION, indicated_priority, assigned_priority   # noqa: E402

DIMS = ('power', 'investment', 'land', 'site_control', 'community', 'connectivity', 'market')
SCREENERS = {'screener_site_risk': 'site_risk', 'screener_control': 'control_blocked'}
SCREENER_VALUES = ('passed', 'failed', 'not_assessed')


def parse_adjustments(text):
    """'+1 reason | -1 reason' -> ([(+1 | -1, reason)], errors)."""
    out, errs = [], []
    for part in [p.strip() for p in (text or '').split(' | ') if p.strip()]:
        m = re.match(r'([+-])1\s+(.+)', part)
        if not m or not m.group(2).strip():
            errs.append(f"adjustment without a direction and a reason: {part!r}")
            continue
        out.append((1 if m.group(1) == '+' else -1, m.group(2).strip()))
    return out, errs


def row_inputs(r):
    """A checked ratings.csv row -> (dims, screeners, adjustments) as rating_rules takes them."""
    dims = {d: (int(r[f'{d}_score']) if r[f'{d}_score'] else None, r[f'{d}_conf']) for d in DIMS}
    return dims, {key: r[col] for col, key in SCREENERS.items()}, parse_adjustments(r.get('adjustments'))[0]


def check_rows(rows, status=None):
    """rows: ratings.csv rows; status: {site_id: current location status} (broker_summary.csv) to catch stale ratings.
    Returns (errors, review): errors ['<site>: <problem>'], review ['<site>: indicated X, assigned Y']."""
    errors, review = [], []
    for r in rows:
        sid = r.get('site_id') or '?'
        err = lambda msg: errors.append(f"{sid}: {msg}")
        if r.get('method_version') != METHOD_VERSION:
            err(f"method {r.get('method_version')!r}, not {METHOD_VERSION}: re-run rate.py")
        if not r.get('as_of'):
            err('no as-of date')
        if status is not None and status.get(sid) != r.get('location_status'):
            err(f"rated as {r.get('location_status')!r}, location status is now {status.get(sid)!r}: re-run rate.py")
        dims = {}
        for d in DIMS:
            sc, cf, why = (r.get(f'{d}_score') or '').strip(), (r.get(f'{d}_conf') or '').strip(), (r.get(f'{d}_reason') or '').strip()
            if cf not in CAP:
                err(f"{d}: confidence {cf!r} is not high / medium / low / none")
                continue
            if not why:
                err(f"{d}: no reason / evidence")
            if sc == '':
                dims[d] = (None, cf)
                continue
            if not re.fullmatch(r'[1-5]', sc):
                err(f"{d}: score {sc!r} is not 1-5 or blank (unknown)")
                continue
            if CAP[cf] is None:
                err(f"{d}: score {sc} with confidence none (no usable information must show as unknown)")
            elif int(sc) > CAP[cf]:
                err(f"{d}: score {sc} above the {cf}-confidence cap of {CAP[cf]}")
            dims[d] = (int(sc), cf)
        scr = {}
        for col, key in SCREENERS.items():
            v = (r.get(col) or '').strip()
            if v not in SCREENER_VALUES:
                err(f"{col}: {v!r} is not passed / failed / not_assessed")
            scr[key] = v
        if len(dims) == len(DIMS) and all(v in SCREENER_VALUES for v in scr.values()):
            ind, _, _ = indicated_priority(dims, scr)
            if r.get('indicated') != ind:
                err(f"indicated {r.get('indicated')!r}, the rules give {ind!r}")
            if not (r.get('indicated_reasons') or '').strip():
                err('no reason for the indicated priority')
            adj, aerr = parse_adjustments(r.get('adjustments'))
            for e in aerr:
                err(e)
            asg = assigned_priority(ind, adj)
            if r.get('assigned') != asg:
                err(f"assigned {r.get('assigned')!r}, the indicated priority and adjustments give {asg!r}")
            elif r.get('assigned') != r.get('indicated'):
                review.append(f"{sid}: indicated {r.get('indicated')}, assigned {r.get('assigned')}")
    return errors, review


if __name__ == '__main__':
    from memo import rd                                                       # noqa: E402
    from batch_paths import support                                           # noqa: E402
    b = sys.argv[1].rstrip('/\\')
    summ = support(b, 'broker_summary.csv')
    status = {r['site_id']: r['location_status'] for r in rd(summ)} if os.path.exists(summ) else None
    errors, review = check_rows(rd(support(b, 'ratings.csv')), status)
    for e in errors:
        print(f"ERROR {e}")
    for x in review:
        print(f"second review: {x}")
    print(f"{'FAILED' if errors else 'ok'}: {len(errors)} error(s), {len(review)} for second review")
    sys.exit(1 if errors else 0)
