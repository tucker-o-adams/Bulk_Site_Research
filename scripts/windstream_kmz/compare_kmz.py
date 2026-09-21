# -*- coding: utf-8 -*-
"""Structural diff of two KMZs: folder tree with placemark counts, then every
placemark matched by (folder path, name) and compared on geometry + styleUrl.

Usage:
    python compare_kmz.py A.kmz B.kmz
"""
import hashlib, sys, zipfile
import xml.etree.ElementTree as ET
from collections import Counter

NS = '{http://www.opengis.net/kml/2.2}'


def load(path):
    z = zipfile.ZipFile(path)
    name = next(n for n in z.namelist() if n.lower().endswith('.kml'))
    return ET.fromstring(z.read(name))


def nm(el):
    n = el.find(NS + 'name')
    return (n.text or '').strip() if n is not None else ''


def geom_sig(pm):
    """Hash of every coordinates string under the placemark, in document order,
    with numbers rounded so serialisation differences don't count."""
    h = hashlib.md5()
    for c in pm.iter(NS + 'coordinates'):
        for tok in (c.text or '').split():
            vals = tok.split(',')
            h.update(','.join(f'{float(v):.6f}' for v in vals[:2]).encode())
            h.update(b' ')
        h.update(b'|')
    st = pm.find(NS + 'styleUrl')
    h.update(((st.text or '') if st is not None else '').encode())
    return h.hexdigest()


def walk(el, path, tree, pms):
    for ch in el:
        if ch.tag == NS + 'Folder':
            p = path + (nm(ch),)
            tree[p] = tree.get(p, 0)
            walk(ch, p, tree, pms)
        elif ch.tag == NS + 'Placemark':
            tree[path] = tree.get(path, 0) + 1
            pms.setdefault((path, nm(ch)), []).append(geom_sig(ch))
        elif ch.tag == NS + 'Document':
            walk(ch, path, tree, pms)


def main(a, b):
    ta, pa, tb, pb = {}, {}, {}, {}
    walk(load(a), (), ta, pa)
    walk(load(b), (), tb, pb)

    print(f'A = {a}\nB = {b}\n')
    print('--- folder tree: placemark counts (A vs B); only rows that differ or are top-level ---')
    for p in sorted(set(ta) | set(tb), key=lambda x: (len(x), x)):
        ca, cb = ta.get(p), tb.get(p)
        if ca != cb or len(p) <= 1:
            flag = '' if ca == cb else '   <-- DIFF'
            print(f'  {"/".join(p) or "(root)"}: {ca} vs {cb}{flag}')

    only_a = sorted(set(pa) - set(pb)); only_b = sorted(set(pb) - set(pa))
    both = set(pa) & set(pb)
    same = sum(1 for k in both if sorted(pa[k]) == sorted(pb[k]))
    diff = [k for k in both if sorted(pa[k]) != sorted(pb[k])]
    print(f'\n--- placemarks matched by (folder path, name) ---')
    print(f'  in both: {len(both)}  | identical geometry+style: {same}  | differ: {len(diff)}')
    print(f'  only in A: {len(only_a)}  | only in B: {len(only_b)}')
    for label, lst in (('only in A', only_a), ('only in B', only_b), ('geometry differs', diff)):
        for k in lst[:25]:
            print(f'    [{label}] {"/".join(k[0])} :: {k[1]}')
        if len(lst) > 25:
            print(f'    ... {len(lst) - 25} more')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1], sys.argv[2]))
