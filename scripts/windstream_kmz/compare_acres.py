import csv
p = r'C:\Users\tucke\OneDrive\Documents\Claude\Projects\TBDI Modeling\Mireye\WS_Sites_Parcel_Sizes.csv'
rows = [r for r in csv.DictReader(open(p, encoding='utf-8-sig')) if r['status'] == 'ok']
have = [r for r in rows if (r['acres_stated'] or '').strip()]
print(f'resolved rows: {len(rows)} | acres_stated populated: {len(have)} | blank: {len(rows)-len(have)}\n')
print(f"{'CLLI':10} {'County':11} {'acres_gis':>10} {'acres_stated':>13} {'diff %':>8}")
for r in rows:
    gis = float(r['acres_gis'] or 0)
    st = (r['acres_stated'] or '').strip()
    if st:
        try:
            sv = float(st)
            d = (gis - sv) / sv * 100 if sv else float('nan')
            print(f"{r['clli']:10} {r['county'][:11]:11} {gis:10.4f} {sv:13.4f} {d:+7.1f}%")
        except ValueError:
            print(f"{r['clli']:10} {r['county'][:11]:11} {gis:10.4f} {st:>13} (non-numeric)")
    else:
        print(f"{r['clli']:10} {r['county'][:11]:11} {gis:10.4f} {'-':>13}")
