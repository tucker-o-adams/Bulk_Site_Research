# -*- coding: utf-8 -*-
"""Nearest data center, from the PeeringDB facility list (local KMZ, no network).

Reference/peeringdb.kmz holds PeeringDB's public facility list (5,260 sites
worldwide, ~1,500 in the US) with name, address, city/state, the count of
networks present, and a PeeringDB URL per facility. Distances are straight-line
from the site to the facility point.

What this is and is not: PeeringDB lists colocation / interconnection
facilities that networks choose to register in — it is the best free map of
where connectivity concentrates. It does not list hyperscale campuses,
enterprise or single-tenant data centers, or facilities that never registered.
"Nearest data center" here means "nearest registered colo/IX facility".
`Networks` is the number of networks present, a fair proxy for how much of a
hub it is; a facility with >= HUB_NETWORKS networks is called a hub below.
"""
import os, threading, zipfile
import xml.etree.ElementTree as ET
from geom import point_dist_m
from provenance import Value, absent, now_iso

NAME = 'datacenter'
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
KMZ = os.path.join(ROOT, 'Reference', 'peeringdb.kmz')
LYR = 'https://www.peeringdb.com/'
SOURCE = 'PeeringDB facility list (Reference/peeringdb.kmz)'
HUB_NETWORKS = 20   # 114 of 1,353 US facilities; the top facility in Houston (36), Columbus (30), Cleveland (20) qualify, Cincinnati (8) does not
COUNT_M = (25000, 50000)
METHOD = ('straight-line distance from the site to each US PeeringDB facility point; nearest facility, '
          f'nearest facility with >= {HUB_NETWORKS} networks, counts within 25 / 50 km, most networks within 50 km')
NOTE = 'PeeringDB = registered colo/IX facilities only; hyperscale campuses and enterprise data centers are not listed'

FIELDS = ['dc_nearest_m', 'dc_nearest_name', 'dc_nearest_city', 'dc_nearest_state', 'dc_nearest_networks',
          'dc_nearest_peeringdb_url', 'dc_hub_nearest_m', 'dc_hub_nearest_name', 'dc_hub_nearest_city',
          'dc_hub_nearest_networks', 'dc_count_within_25km', 'dc_count_within_50km', 'dc_max_networks_within_50km']

_FACILITIES = None
_VINTAGE = None


_LOCK = threading.Lock()      # run.py calls run() from several threads


def _load():
    with _LOCK:
        if _FACILITIES is None:
            _read()


def _read():
    global _FACILITIES, _VINTAGE
    NS = '{http://www.opengis.net/kml/2.2}'
    z = zipfile.ZipFile(KMZ)
    root = ET.fromstring(z.read('doc.kml'))
    facs = []
    for pm in root.iter(NS + 'Placemark'):
        d = {x.get('name'): (x.find(NS + 'value').text or '').strip() if x.find(NS + 'value') is not None else ''
             for x in pm.iter(NS + 'Data')}
        if (d.get('country') or '').upper() != 'US':
            continue
        c = pm.find('.//' + NS + 'coordinates')
        if c is None:
            continue
        lng, lat = (float(v) for v in c.text.strip().split(',')[:2])
        try:
            nets = int(d.get('Networks') or 0)
        except ValueError:
            nets = 0
        facs.append((lng, lat, d.get('name', ''), d.get('city', ''), d.get('state', ''), nets, d.get('peeringDB', '')))
    # the export date is doc.kml's timestamp inside the KMZ - it travels with the file, unlike the file's
    # mtime, which becomes the clone/copy date on any other machine
    y, mo, dd = z.getinfo('doc.kml').date_time[:3]
    _VINTAGE = f'{y:04d}-{mo:02d}-{dd:02d}'
    _FACILITIES = facs


def run(site, cache):
    _load()
    la, ln = site.lat, site.lng
    fetched = now_iso()

    def mk(fld, val, note=NOTE):
        return Value(fld, val, SOURCE, LYR, METHOD, vintage=_VINTAGE, fetched_at=fetched, note=note)

    scored = sorted(((point_dist_m(ln, la, x, y), name, city, st, nets, url) for x, y, name, city, st, nets, url in _FACILITIES),
                    key=lambda s: s[0])
    if not scored:
        return [absent(f, SOURCE, LYR, METHOD, note='no US facilities in the reference file', vintage=_VINTAGE) for f in FIELDS]
    d, name, city, st, nets, url = scored[0]
    out = [mk('dc_nearest_m', round(d)), mk('dc_nearest_name', name), mk('dc_nearest_city', city),
           mk('dc_nearest_state', st), mk('dc_nearest_networks', nets), mk('dc_nearest_peeringdb_url', url)]
    hub = next((s for s in scored if s[4] >= HUB_NETWORKS), None)
    if hub:
        out += [mk('dc_hub_nearest_m', round(hub[0])), mk('dc_hub_nearest_name', hub[1]),
                mk('dc_hub_nearest_city', hub[2]), mk('dc_hub_nearest_networks', hub[4])]
    else:
        out += [absent(f, SOURCE, LYR, METHOD, note=f'no facility with >= {HUB_NETWORKS} networks', vintage=_VINTAGE)
                for f in ('dc_hub_nearest_m', 'dc_hub_nearest_name', 'dc_hub_nearest_city', 'dc_hub_nearest_networks')]
    w25 = [s for s in scored if s[0] <= COUNT_M[0]]
    w50 = [s for s in scored if s[0] <= COUNT_M[1]]
    out += [mk('dc_count_within_25km', len(w25)), mk('dc_count_within_50km', len(w50)),
            mk('dc_max_networks_within_50km', max((s[4] for s in w50), default=0))]
    return out
