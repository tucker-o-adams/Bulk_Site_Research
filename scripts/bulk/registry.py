# -*- coding: utf-8 -*-
"""Per-county (and statewide) parcel services, and how to choose one.

There is no national public parcel layer, so a parcel boundary needs a service
that is specific to the county — or to the state, where one exists.

Since 2026-10-15 the services live in **tbdi-geo** (`data/counties.json`), the
library this pipeline shares with tbdi-pasa, so a county either tool registers
reaches the other on the next release. This repo's own file,
`data/reference/county-services.json`, is an **overlay** in the same schema:
reviewed entries not yet released to tbdi-geo. An overlay entry replaces
tbdi-geo's entry for that county or state, whole. Until 2026-10-15 the services
were in `data/reference/parcel-services.json`; every entry moved into tbdi-geo
0.1.0, and that file was renamed to the overlay and emptied.

The shared schema is tbdi-pasa's `roles` shape (`registry.py` in tbdi-geo has
it in full). This module hands the rest of the pipeline the shape it was
written for — a parcel `service` whose `fields` maps our roles to the county's
column names:

    service = {"base": "<MapServer or FeatureServer url>", "layer": 0,
               "name": "...", "owner": "...",
               "fields": {"apn": "PARCELID", "owner": "OWNERNAME",
                          "acres": "GIS_ACRES", "address": "SITUS"},   # county field names
               "notes": "..."}

    Optional service keys: "protocol" ("query" default, "identify", "wms" - see
    producers/parcel.py), "data_vintage", a "vintage" role in "fields" naming a
    per-parcel date column, "exclude" {geoid: {"county", "reason"}} for counties a
    statewide layer carries but we may not use, and "check_point" [lat, lng] for
    check_sources.py where the service cannot count its records (WMS).

In tbdi-geo those `fields` are the parcel role's `field_roles`. A county
tbdi-pasa registered and Mireye never reviewed may have none: its polygon is
used and its APN and owner come back empty, never guessed.

A county entry wins over the statewide one: the county is the authority and
everyone else is a copy of unknown age.

Three tiers, in order (tbdi-pasa's rule, and the reason the registry is reviewed
by a person): **registry** → **discovery proposal** (written by
`discover_parcel_service.py`, never used by a run until someone moves it in) →
**unresolved**, which records what was tried. An unresolved parcel is a valid
result. A wrong parcel silently poisons buildable acres, the flood and wetland
clips, and the KMZ outline, so nothing is auto-registered.
"""
import os

from tbdi_geo import registry as shared

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
PATH = os.path.join(ROOT, 'data', 'reference', 'county-services.json')     # overlay on tbdi-geo
PROPOSALS = os.path.join(ROOT, 'data', 'reference', 'parcel-proposals')


def _service(role):
    """A tbdi-geo parcel role in the shape this pipeline reads: `fields` is the role map."""
    svc = dict(role)
    svc['fields'] = dict(role.get('field_roles') or {})
    return svc


def _entry(entry):
    """An entry's metadata (county, state, reviewed...) without its roles."""
    return {k: v for k, v in entry.items() if k != 'roles'}


def load():
    """The parcel services in this pipeline's shape:
    {"statewide": {fips: {..., "service": svc}}, "counties": {geoid: {..., "service": svc}}}.
    Entries that register no parcel role (tbdi-pasa's other county roles) are left out."""
    reg = shared.counties(PATH)
    out = {'registry_version': reg.get('registry_version'), 'updated': reg.get('updated'),
           'statewide': {}, 'counties': {}, '_overlay': reg.get('_overlay')}
    for section in ('statewide', 'counties'):
        for key, e in (reg.get(section) or {}).items():
            role = (e.get('roles') or {}).get('parcel')
            if role:
                out[section][key] = {**_entry(e), 'service': _service(role)}
    return out


def for_county(county_geoid, state_fips=None):
    """Return (service, scope, entry) for a county GEOID ('39153'), or (None, None, None).

    scope is 'county' or 'statewide'; entry carries the review metadata for the
    citation. A county entry wins over the statewide one.
    """
    found = shared.parcel_services(str(county_geoid), PATH, state_fips=state_fips)
    if not found:
        return None, None, None
    f = found[0]
    return _service(f['service']), f['scope'], _entry(f['entry'])


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
