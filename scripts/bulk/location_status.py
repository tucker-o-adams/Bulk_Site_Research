# -*- coding: utf-8 -*-
"""Location status: how sure we are that the tool has the broker's site, one of five, set by fixed rules
(MEMOS.md). The exhibits (figure.py) and both memos (memo.py) read it from here, so they cannot disagree.

  confirmed           the broker's pin (or APN) sits in a parcel that matches the stated size, and nothing the
                      broker says contradicts it. No neighbour is offered instead; no person needed
  confirmed_partial   the pin is trusted and the size gap is explained: a carve-out (stated or probable - the site
                      is part of the parcel) or a site that spans several parcels. No person needed; the note says which
  needs_input         borderline, and a person can settle it from a short list: an approximate pin whose parcel
                      does not match, a substation claim that contradicts the pin, or a site known only near a named
                      anchor with 1-5 parcels of the stated size around it, or tracts the broker names by owner with 1-5
                      parcels under those names of about the stated size (candidates.py)
  not_locatable       too little to find the parcel: only a ZIP or county with no tract names, or an anchor with no acreage to search
                      by, or too many (or no) parcels of the stated size around it
  no_site             the broker says no site is identified yet (a power position with a search area). Nothing to locate

Precision tiers (L1-L5, locate.py) say how the point was placed; the status says whether that is the site.
"""
from collections import OrderedDict

STATUS = OrderedDict([
    ('confirmed',         {'label': 'Confirmed',          'fill': 'E2EFDA', 'ink': '2E7D32'}),
    ('confirmed_partial', {'label': 'Confirmed',          'fill': 'DDEBF7', 'ink': '1F5FA8'}),
    ('needs_input',       {'label': 'Needs confirmation', 'fill': 'FFF2CC', 'ink': 'B26A00'}),
    ('not_locatable',     {'label': 'Not locatable',      'fill': 'EDEDED', 'ink': '6E6E6E'}),
    ('no_site',           {'label': 'No site yet',        'fill': 'F7F7F7', 'ink': '9A9A9A'}),
])
SITE_LEVEL = ('L1', 'L2')
NO_SITE_STAGES = ('no_site_yet',)
ANCHOR_ADJ_M = 400           # the broker says the site adjoins the anchor substation: search this close to it


def label(status, note=''):
    """'Confirmed', 'Confirmed: carve-out (stated)', 'Needs confirmation', ..."""
    base = STATUS[status]['label']
    return f'{base}: {note}' if status == 'confirmed_partial' and note else base


def colours(status):
    """(fill, ink) as 'RRGGBB' strings; figure.py prefixes '#'."""
    s = STATUS[status]
    return s['fill'], s['ink']


def no_site(stage, has_acres, tier):
    """The broker says there is no site: 'no site yet', or 'no site control' with no acreage and no point on a site."""
    return stage in NO_SITE_STAGES or (stage == 'no_site_control' and not has_acres and tier not in SITE_LEVEL)


def search_plan(tier, stage, acres, basis, lat, lng, radius_m, anchor_adjacent=False):
    """Where to look for candidate parcels for a site placed near a named anchor (L3), or None when there is nothing
    to search by: a tract the broker says is identified, with a stated acreage. Returns [(lat, lng, radius_m)]."""
    if tier != 'L3' or not acres or no_site(stage, True, tier):
        return None
    r = ANCHOR_ADJ_M if anchor_adjacent and (basis or '').startswith('HIFLD substation') else float(radius_m or 2000)
    return [(float(lat), float(lng), r)]


def _owner_status(c, out):
    """A site the broker names only by its tracts' owners ('25 ac Smith + 23 ac Jones'): candidates.search_owner."""
    import candidates as cmod
    lines = []
    for t in c['tracts']:
        size = f"{t['acres']:,.1f} ac" if t.get('acres') else 'size not stated'
        if t['matches']:
            lines.append(f"'{t['name']}' ({size}): {len(t['matches'])} parcel{'s' if len(t['matches']) > 1 else ''} under that name of about that size")
        else:
            lines.append(f"'{t['name']}' ({size}): no parcel under that name of about that size" +
                         (f" (the name holds {len(t['others'])} other parcel{'s' if len(t['others']) > 1 else ''} there, none within 15 %)" if t['others'] else ''))
    base = f"No coordinate, but the broker names the tracts. Parcels searched by owner name in {c['area']}: " + '; '.join(lines) + '.'
    n = c['n']
    k = 0
    heads = []
    for t in c['tracts']:
        m = len(t['matches'])
        heads.append(f"'{t['name']}' ({t['acres']:,.1f} ac): " + (f"{m} candidate{'s' if m > 1 else ''} ({', '.join(chr(65 + k + i) for i in range(m))})"
                                                                  if m else 'not found under that name') if t.get('acres') else f"'{t['name']}': {m} found")
        k += m
    out = {**out, 'headline': 'Tracts searched by owner name: ' + '; '.join(heads) + '.'}
    if 1 <= n <= cmod.MAX_ASK:
        opts = [f"{chr(65 + k)}: the {x['tract']} tract is APN {x['apn']}: {x['acres']:,.1f} ac, {x['owner']}" + (f", {x['address']}" if x['address'] else '')
                for k, x in enumerate(c['candidates'])]
        return {**out, 'status': 'needs_input', 'note': 'tract names',
                'assessment': base, 'question': "Are these the broker's tracts? Tick each one that is.", 'options': opts + ['None of these']}
    return {**out, 'status': 'not_locatable', 'note': 'tract names', 'assessment': base + (' Too many to choose from.' if n else '')}


def classify(tier, stage, has_acres, basis='', radius_m=None, pc=None, cands=None, acres=None):
    """{'status', 'note', 'assessment', 'question', 'options'} for one site.
    pc: the parcel check (<site>_parcel_check.json) for L1/L2 sites; cands: the candidate search (<site>_candidates.json)
    for L3 sites; acres: the broker's stated acreage."""
    out = {'note': '', 'question': None, 'options': []}
    if tier in SITE_LEVEL:
        if pc:
            v = pc['verdict']
            return {**out, **{k: v.get(k) for k in ('status', 'note', 'assessment', 'question')}, 'options': v.get('options') or []}
        return {**out, 'status': 'confirmed', 'note': 'no parcel data',
                'assessment': "The broker's pin is taken as the site; no parcel was available to compare with the stated size."}
    if no_site(stage, has_acres, tier):
        return {**out, 'status': 'no_site', 'assessment': 'The broker says no site is identified yet: a power position with a search area, nothing to locate.'}
    if cands and cands.get('kind') == 'owner' and cands.get('n') is not None:
        return _owner_status(cands, out)
    km = f'{float(radius_m) / 1000:,.1f} km' if radius_m else 'the area'
    if tier == 'L3':
        where = basis.replace('HIFLD substation ', 'substation ').split(' (')[0] if basis else 'a named anchor'
        if cands and cands.get('n') is not None:
            import candidates as cmod
            n, a = cands['n'], acres
            r_km = f"{cands['areas'][0][2] / 1000:,.1f} km"
            if 1 <= n <= cmod.MAX_ASK:
                opts = [f"{chr(65 + k)}: APN {c['apn']}: {c['acres']:,.1f} ac, {c['owner'] or 'no owner'}; {c['from_centre_m']:,} m from {where}" for k, c in enumerate(cands['candidates'])]
                return {**out, 'status': 'needs_input', 'note': 'near a named anchor',
                        'assessment': f"Placed near {where}. {n} parcel{'s' if n > 1 else ''} of about {a:,.1f} ac (within 15 %) lie within {r_km} of it.",
                        'question': 'Is the site one of these parcels?', 'options': opts + ['None of these']}
            return {**out, 'status': 'not_locatable', 'note': 'near a named anchor',
                    'assessment': f"Placed near {where}. " + (f"No parcel of about {a:,.1f} ac lies within {r_km} of it." if n == 0 else
                                                             f"{n} parcels of about {a:,.1f} ac lie within {r_km} of it: too many to choose from.")}
        return {**out, 'status': 'not_locatable', 'note': 'near a named anchor',
                'assessment': f"Placed near {where} (the site could be anywhere within ~{km}); " +
                              ('no acreage is stated to search for the parcel by.' if not has_acres else 'the candidate search has not been run.')}
    if tier == 'L4':
        return {**out, 'status': 'not_locatable', 'note': 'ZIP only', 'assessment': 'Only the ZIP is known.'}
    if tier == 'L5':
        return {**out, 'status': 'not_locatable', 'note': 'county only', 'assessment': 'Only the county is known.'}
    return {**out, 'status': 'not_locatable', 'note': 'no location', 'assessment': 'No location clue could be placed.'}
