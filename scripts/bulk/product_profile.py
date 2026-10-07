# -*- coding: utf-8 -*-
"""A portfolio's product profile (PRODUCT_PROFILE.md): the values the screen measures against.

The profile is one file, `Outputs/<batch>/input/thresholds.md`, read by people and by the code. The code reads
the first ```json block in it, so the numbers a person edits are the numbers the run uses - no second copy.

    run.py --profile Outputs/<batch>/input/thresholds.md

Keys (all distances in feet, as the profile states them; missing keys take DEFAULTS, and run.json records the
values actually used):

    version              the profile's version, recorded in run.json
    approved             true only once Mike has approved it (WORKFLOW step 3). Measuring is allowed before then;
                         scoring (flags.py, BACKLOG 9b) is not
    pad_mw, mw_per_acre  pad acres = pad_mw / mw_per_acre
    pad_min_width_ft     a block narrower than this anywhere cannot hold a pad
    edge_setback_ft      pad kept this far inside the site's outer edge, everywhere (used when the three below are unset)
    edge_setback_road_ft / edge_setback_other_ft / edge_setback_industrial_ft
                         the setback by what is next door (producers/usable.py): road frontage, an industrial neighbor,
                         anything else. Homes are covered by the receptor distances, not here
    building_buffer_ft   around every existing building
    max_slope_pct        ground steeper than this is not usable
    exclude_sfha         FEMA 1% annual-chance zones are not usable
    exclude_nwi          NWI wetlands and water are not usable
    exclude_nlcd         NLCD 2021 classes that are not usable (31 barren: quarries, pits; 11 open water)
    receptor_review_ft   pads closer than this to a home are NO-GO territory
    receptor_pass_ft     pads at least this far from every home pass
    buildings_required   false: a failed building lookup degrades (noted) instead of failing the usable-land fields
    home_min_residential_sqft   a Residential-tagged building smaller than this is a shed or garage, not a home
    home_unclassified_sqft      [min, max]: an Unclassified building counts as a possible home only at this size
    line_row_width_ft    [[min_kv, total width ft], ...]: ground under a transmission line excluded from usable land, by
                         voltage (the widest band whose min_kv the line reaches)
    line_row_unknown_ft  width for a line with no published voltage and no voltage class
    power_line_min_kv / power_sub_min_kv / power_115kv_sub_kv
                         the line and substation voltages the site-based power distances look for (producers/power_site.py)
"""
import hashlib, json, re

FT = 0.3048
DEFAULTS = {'version': None, 'approved': False, 'pad_mw': None, 'mw_per_acre': None, 'pad_min_width_ft': 0,
            'edge_setback_ft': 0, 'edge_setback_road_ft': None, 'edge_setback_other_ft': None,
            'edge_setback_industrial_ft': None, 'building_buffer_ft': 0, 'max_slope_pct': None, 'exclude_sfha': True,
            'exclude_nwi': True, 'exclude_nlcd': [], 'receptor_review_ft': 1000, 'receptor_pass_ft': 2000,
            'buildings_required': True, 'home_min_residential_sqft': 0, 'home_unclassified_sqft': None,
            'line_row_width_ft': None, 'line_row_unknown_ft': 150, 'power_line_min_kv': 69, 'power_sub_min_kv': 69, 'power_115kv_sub_kv': 115}
REQUIRED = ('pad_mw', 'mw_per_acre')


def load(path):
    """(profile dict with defaults filled, sha256 of the file). Exits with a reason when the block is missing or wrong."""
    raw = open(path, 'rb').read()
    m = re.search(r'```json\s*\n(.*?)\n```', raw.decode('utf-8'), re.S)
    if not m:
        raise SystemExit(f'{path}: no ```json block - the profile must carry its values in one (PRODUCT_PROFILE.md)')
    try:
        vals = json.loads(m.group(1))
    except json.JSONDecodeError as e:
        raise SystemExit(f'{path}: the ```json block is not valid JSON: {e}')
    unknown = set(vals) - set(DEFAULTS)
    if unknown:
        raise SystemExit(f'{path}: unknown profile keys {sorted(unknown)} (known: {sorted(DEFAULTS)})')
    missing = [k for k in REQUIRED if vals.get(k) in (None, '')]
    if missing:
        raise SystemExit(f'{path}: profile is missing {missing}')
    return {**DEFAULTS, **vals}, hashlib.sha256(raw).hexdigest()


def pad_acres(p):
    return p['pad_mw'] / p['mw_per_acre']


def m(p, key):
    """A *_ft profile value in metres."""
    return (p.get(key) or 0) * FT
