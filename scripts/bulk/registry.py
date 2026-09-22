# -*- coding: utf-8 -*-
"""Per-county (and statewide) parcel services, and how to choose one.

There is no national public parcel layer, so a parcel boundary needs a service
that is specific to the county — or to the state, where one exists. This module
holds the lookup; `data/reference/parcel-services.json` holds the services.

Schema (ported from tbdi-pasa `data/reference/county-services.json`, whose
design this follows deliberately):

    {"registry_version": 1, "updated": "...",
     "statewide": {"<state_fips>": {"state": "VA", "service": {...}}},
     "counties":  {"<county_geoid>": {"county": "...", "state": "VA",
                                      "publisher": "...", "reviewed": "2026-09-09",
                                      "review_notes": "...", "service": {...}}}}

    service = {"base": "<MapServer or FeatureServer url>", "layer": 0,
               "name": "...", "owner": "...",
               "fields": {"apn": "PARCELID", "owner": "OWNERNAME",
                          "acres": "GIS_ACRES", "address": "SITUS"},   # county field names
               "notes": "..."}

A county entry wins over the statewide one: the county is the authority and
everyone else is a copy of unknown age.

Three tiers, in order (tbdi-pasa's rule, and the reason this file is reviewed
by a person): **registry** → **discovery proposal** (written by
`discover_parcel_service.py`, never used by a run until someone moves it in) →
**unresolved**, which records what was tried. An unresolved parcel is a valid
result. A wrong parcel silently poisons buildable acres, the flood and wetland
clips, and the KMZ outline, so nothing is auto-registered.
"""
import json, os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
PATH = os.path.join(ROOT, 'data', 'reference', 'parcel-services.json')
PROPOSALS = os.path.join(ROOT, 'data', 'reference', 'parcel-proposals')

_REG = None


def load():
    global _REG
    if _REG is None:
        _REG = json.load(open(PATH, encoding='utf-8')) if os.path.exists(PATH) else \
            {'registry_version': 1, 'statewide': {}, 'counties': {}}
    return _REG


def for_county(county_geoid, state_fips=None):
    """Return (service, scope, entry) for a county GEOID ('39153'), or (None, None, None).

    scope is 'county' or 'statewide'; entry carries the review metadata for the
    citation. A county entry wins over the statewide one.
    """
    reg = load()
    e = (reg.get('counties') or {}).get(str(county_geoid))
    if e and e.get('service'):
        return e['service'], 'county', e
    st = str(state_fips or str(county_geoid)[:2])
    s = (reg.get('statewide') or {}).get(st)
    if s and s.get('service'):
        return s['service'], 'statewide', s
    return None, None, None


def field(service, role, default=None):
    """County field name for one of our roles ('apn', 'owner', 'acres', 'address')."""
    return (service.get('fields') or {}).get(role, default)


def pick(props, service, role):
    """Value for a role from a returned feature's properties, tolerant of case."""
    name = field(service, role)
    if not name:
        return None
    for k, v in (props or {}).items():
        if k.lower() == name.lower():
            return v
    return None


def coverage():
    reg = load()
    return {'counties': sorted((reg.get('counties') or {})), 'statewide': sorted((reg.get('statewide') or {}))}
