# -*- coding: utf-8 -*-
"""Regression: the bulk pipeline's transmission fields for the Windstream 200
must match WS_Top200_Transmission_Distance.csv (Aug 2026, tx_distance.py).

    python check_windstream_transmission.py Outputs/windstream-200/sites.csv
Exit 0 only when every site matches on line ID and distance (0.1 m) for both the
any-voltage and the >= 100 kV nearest line.
"""
import csv, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
# A frozen copy of Outputs/Excel outputs/WS_Top200_Transmission_Distance.csv, kept beside the check so
# tidying Outputs/ cannot break the regression.
REF = os.path.join(HERE, 'ws200_transmission_aug2026.csv')


def num(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    # The Aug 2026 reference stored HIFLD's "not published" sentinel (-999999) as a
    # voltage; the bulk producer normalizes it to null. Treat them as equal.
    return None if v <= -999999 else v


def sid(x):
    n = num(x)
    return str(int(n)) if n is not None else (x or '')


def main(new_csv):
    ref = {r['CLLI']: r for r in csv.DictReader(open(REF, encoding='utf-8-sig'))}
    new = {r['site_id']: r for r in csv.DictReader(open(new_csv, encoding='utf-8-sig'))}
    pairs = [('line_id', 'tx_line_id', sid), ('nearest_tx_line_m', 'tx_nearest_m', num),
             ('voltage_kv', 'tx_voltage_kv', num), ('owner', 'tx_owner', str),
             ('line_id_100plus', 'tx_100kv_line_id', sid), ('nearest_100kv_plus_m', 'tx_100kv_nearest_m', num)]
    bad, checked = [], 0
    for clli, r in ref.items():
        n = new.get(clli)
        if n is None:
            bad.append((clli, 'missing from new output')); continue
        checked += 1
        for rc, nc, f in pairs:
            a, b = f(r.get(rc) or ''), f(n.get(nc) or '')
            if f is num:
                ok = (a is None and b is None) or (a is not None and b is not None and abs(a - b) <= 0.1)
            else:
                ok = (a or '') == (b or '')
            if not ok:
                bad.append((clli, f'{rc}={a!r} vs {nc}={b!r}'))
    print(f'reference sites: {len(ref)} | checked: {checked} | mismatches: {len(bad)}')
    for b in bad[:40]:
        print('  ', b)
    return 0 if not bad else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1]))
