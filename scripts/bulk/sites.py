# -*- coding: utf-8 -*-
"""Input contract: one CSV, one row per site.

Required columns:   site_id, lat, lng
Optional, understood: name, address, apn, acres_stated, state, county, group, notes
Anything else:      carried through untouched to the output, never interpreted

Common header spellings are accepted (ALIASES: Latitude/Longitude/lon, acres/acreage, ...).
acres_stated is read leniently: "25", "25 ac", "±25 acres" and "1,200" parse; a range or
other text ("20-30", "TBD") leaves acres_stated empty and keeps the text in acres_stated_text,
so a messy acreage never costs the site.

Rows that fail validation are not dropped silently: they come back in
`rejected` with the reason, and the run report lists them.
"""
import csv, re
from dataclasses import dataclass, field
from typing import Optional

REQUIRED = ('site_id', 'lat', 'lng')
OPTIONAL = ('name', 'address', 'apn', 'acres_stated', 'state', 'county', 'group', 'notes')
ALIASES = {'id': 'site_id', 'site': 'site_id',
           'latitude': 'lat', 'lat_dd': 'lat', 'y': 'lat',
           'longitude': 'lng', 'long': 'lng', 'lon': 'lng', 'lng_dd': 'lng', 'x': 'lng',
           'acres': 'acres_stated', 'acreage': 'acres_stated', 'size_acres': 'acres_stated', 'site_acres': 'acres_stated'}
_ACRES = re.compile(r'[~±≈+]?\s*(\d[\d,]*(?:\.\d+)?|\.\d+)\s*(?:ac|acs|acre|acres)?\.?', re.I)


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


def parse_acres(text):
    """Acres from a broker's acreage text, or None when it is a range or not a single number."""
    m = _ACRES.fullmatch((text or '').strip())
    return float(m.group(1).replace(',', '')) if m else None


def load_sites(path: str):
    """Return (sites, rejected). rejected = [(row_number, site_id_or_blank, reason)]."""
    sites, rejected, seen = [], [], set()
    with open(path, encoding='utf-8-sig', newline='') as f:
        rdr = csv.DictReader(f)
        norm = [_norm_header(h) for h in (rdr.fieldnames or [])]
        # an alias maps only when the canonical name is not already a column
        alias = {h: ALIASES[h] for h in norm if h in ALIASES and ALIASES[h] not in norm}
        headers = [alias.get(h, h) for h in norm]
        missing = [c for c in REQUIRED if c not in headers]
        if missing:
            raise SystemExit(f'{path}: missing required column(s) {missing}; have {headers}')
        for n, raw in enumerate(rdr, start=2):
            r = {headers[norm.index(_norm_header(k))]: (v or '').strip() for k, v in raw.items() if k is not None}
            sid = r.get('site_id', '')
            if not sid:
                rejected.append((n, '', 'blank site_id')); continue
            if sid in seen:
                rejected.append((n, sid, 'duplicate site_id')); continue
            if not r.get('lat') or not r.get('lng'):
                rejected.append((n, sid, 'no coordinates (address-only row? run geocode.py first)')); continue
            try:
                lat, lng = float(r['lat']), float(r['lng'])
            except ValueError:
                rejected.append((n, sid, f"non-numeric lat/lng {r.get('lat')!r},{r.get('lng')!r}")); continue
            if not (-90 <= lat <= 90 and -180 <= lng <= 180):
                rejected.append((n, sid, f'lat/lng out of range {lat},{lng}')); continue
            if not (17 <= lat <= 72 and -180 <= lng <= -64):
                rejected.append((n, sid, f'coordinate outside the US {lat},{lng} (lat/lng swapped?)')); continue
            acres = parse_acres(r.get('acres_stated'))
            seen.add(sid)
            extra = {k: v for k, v in r.items() if k not in REQUIRED and k not in OPTIONAL}
            if r.get('acres_stated') and (acres is None or not re.fullmatch(r'[\d,.]+', r['acres_stated'])):
                extra['acres_stated_text'] = r['acres_stated']      # the broker's words, when they were not a plain number
            sites.append(Site(site_id=sid, lat=lat, lng=lng,
                              name=r.get('name', ''), address=r.get('address', ''), apn=r.get('apn', ''),
                              acres_stated=acres, state=r.get('state', '').upper(), county=r.get('county', ''),
                              group=r.get('group', ''), notes=r.get('notes', ''), extra=extra))
    return sites, rejected
