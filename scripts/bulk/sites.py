# -*- coding: utf-8 -*-
"""Input contract: one CSV, one row per site.

Required columns:   site_id, lat, lng
Optional, understood: name, address, apn, acres_stated, state, county, group, notes
Anything else:      carried through untouched to the output, never interpreted

Rows that fail validation are not dropped silently: they come back in
`rejected` with the reason, and the run report lists them.
"""
import csv
from dataclasses import dataclass, field
from typing import Optional

REQUIRED = ('site_id', 'lat', 'lng')
OPTIONAL = ('name', 'address', 'apn', 'acres_stated', 'state', 'county', 'group', 'notes')


@dataclass
class Site:
    site_id: str
    lat: float
    lng: float
    name: str = ''
    address: str = ''
    apn: str = ''
    acres_stated: Optional[float] = None
    state: str = ''
    county: str = ''
    group: str = ''
    notes: str = ''
    extra: dict = field(default_factory=dict)   # pass-through columns


def _norm_header(h: str) -> str:
    return (h or '').strip().lstrip('﻿').lower().replace(' ', '_')


def load_sites(path: str):
    """Return (sites, rejected). rejected = [(row_number, site_id_or_blank, reason)]."""
    sites, rejected, seen = [], [], set()
    with open(path, encoding='utf-8-sig', newline='') as f:
        rdr = csv.DictReader(f)
        headers = [_norm_header(h) for h in (rdr.fieldnames or [])]
        missing = [c for c in REQUIRED if c not in headers]
        if missing:
            raise SystemExit(f'{path}: missing required column(s) {missing}; have {headers}')
        for n, raw in enumerate(rdr, start=2):
            r = {_norm_header(k): (v or '').strip() for k, v in raw.items() if k is not None}
            sid = r.get('site_id', '')
            if not sid:
                rejected.append((n, '', 'blank site_id')); continue
            if sid in seen:
                rejected.append((n, sid, 'duplicate site_id')); continue
            try:
                lat, lng = float(r['lat']), float(r['lng'])
            except ValueError:
                rejected.append((n, sid, f"non-numeric lat/lng {r.get('lat')!r},{r.get('lng')!r}")); continue
            if not (-90 <= lat <= 90 and -180 <= lng <= 180):
                rejected.append((n, sid, f'lat/lng out of range {lat},{lng}')); continue
            if not (17 <= lat <= 72 and -180 <= lng <= -64):
                rejected.append((n, sid, f'coordinate outside the US {lat},{lng} (lat/lng swapped?)')); continue
            acres = None
            if r.get('acres_stated'):
                try:
                    acres = float(r['acres_stated'].replace(',', ''))
                except ValueError:
                    rejected.append((n, sid, f"non-numeric acres_stated {r['acres_stated']!r}")); continue
            seen.add(sid)
            extra = {k: v for k, v in r.items() if k not in REQUIRED and k not in OPTIONAL}
            sites.append(Site(site_id=sid, lat=lat, lng=lng,
                              name=r.get('name', ''), address=r.get('address', ''), apn=r.get('apn', ''),
                              acres_stated=acres, state=r.get('state', '').upper(), county=r.get('county', ''),
                              group=r.get('group', ''), notes=r.get('notes', ''), extra=extra))
    return sites, rejected
