# -*- coding: utf-8 -*-
"""Is the identified parcel the broker's site? The evidence a person needs to judge it.

Used by figure.py (the 'parcels' exhibit) and read back by memo.py (the appendix). For one site:

  * the parcels around the identified one, from the same registered parcel service (an envelope query,
    or an envelope `identify` for services that disable /query, like TxGIO) - cached like every answer
  * which of them touch the identified parcel, and which share its owner
  * a precise broker pin is trusted: a parcel under it that matches the stated size is the site, and no neighbour is
    offered instead; a stated site much smaller than the parcel is a carve-out of it (stated or probable), a larger
    one spans several parcels. Neither needs a person (Tucker, 2026-09-25)
  * an approximate pin whose parcel does not match: candidates.py lists every parcel of about the stated size in the
    area the site can be in (the pin's uncertainty radius, plus 400 m around a substation the broker says it adjoins).
    No combinations of parcels are guessed
  * the substation check: when the broker says the site is adjacent to (or a distance from) a named existing
    substation, whether the identified parcel - and a likely neighbour - actually borders it (HIFLD point; the
    substation's own parcel when the parcel service returns it)
  * which parcel's situs address matches a listing address the broker gave
  * the verdict: the location status (location_status.py), one plain statement of stated vs found acreage, and
    for a site that needs a person, the question and its options

Nothing here changes a workbook value; the parcel producer's choice stands until a person decides.
"""
import hashlib, json, math, os, re

from shapely.geometry import shape, box
from shapely.ops import unary_union, transform
from pyproj import Transformer

from cache import coord_key
from geom import arcgis_envelope_query
from producers import parcel as parcel_mod
import registry

AC = 4046.8564224
MATCH_TOL = 0.15             # identified parcel within 15 % of the stated acreage = a match
APPROX_R_M = 500             # an approximate broker coordinate: the site is within this of it (locate.py RADIUS)
QUERY_PAD_M = 300            # neighbours are fetched for the identified parcel's bbox plus this
STOP = {'ET', 'AL', 'ETAL', 'ETUX', 'LLC', 'LP', 'LLP', 'LTD', 'INC', 'CO', 'CORP', 'TR', 'TRUST', 'TRUSTEE', 'THE', 'AND', 'FAMILY',
        'EST', 'ESTATE', 'OF', 'PTSHP', 'PARTNERSHIP', 'LIVING', 'REVOCABLE'}
# words too common in company names to identify an owner on their own
GENERIC = {'LAND', 'LANDS', 'PROPERTY', 'PROPERTIES', 'HOLDINGS', 'DEVELOPMENT', 'INVESTMENTS', 'INVESTMENT', 'PARTNERS', 'GROUP', 'TEXAS',
           'ASSOCIATION', 'OWNERS', 'COMMERCIAL', 'REAL', 'RANCH', 'CATTLE', 'CAPITAL', 'VENTURES', 'ENTERPRISES', 'MANAGEMENT', 'COMPANY'}


def owner_tokens(owner):
    """The distinctive words of an owner name: 'FRANCIS E ONEILL FAMILY LP' -> {'FRANCIS', 'ONEILL'}. A name made only of
    generic words keeps them ('ACME DEVELOPMENT LLC' -> {'ACME'}; 'LAND HOLDINGS LLC' -> {'LAND', 'HOLDINGS'})."""
    toks = [t for t in re.findall(r'[A-Z0-9]+', (owner or '').upper()) if len(t) > 1 and t not in STOP]
    dist = {t for t in toks if t not in GENERIC}
    return dist or set(toks)


def same_owner(a, b):
    """Two owner names read as the same owner: one's distinctive words contain the other's, or they share two.
    'FRANCIS E ONEILL FAMILY LP' ~ 'FRANCIS ONEILL LTD PTSHP'; 'SMITH JOHN' !~ 'SMITH MARY'. Blank never matches."""
    ta, tb = owner_tokens(a), owner_tokens(b)
    return bool(ta and tb and (ta <= tb or tb <= ta or len(ta & tb) >= 2))


ADDR_ALIAS = {'COUNTY': 'CR', 'CO': 'CR', 'ROAD': 'RD', 'STREET': 'ST', 'HIGHWAY': 'HWY', 'FARM': 'FM', 'DRIVE': 'DR', 'LANE': 'LN'}
ADDR_SKIP = {'RD', 'ST', 'DR', 'LN', 'AVE', 'BLVD', 'N', 'S', 'E', 'W', 'TX', 'US'}


def addr_parts(addr):
    """'1902 County Rd 52, Rosharon, TX' -> ('1902', {'CR', '52'}): house number + street words (aliases folded), or None."""
    street = (addr or '').split(',')[0]
    m = re.match(r'\s*(\d+)\s+(.+)', street)
    if not m:
        return None
    words = {ADDR_ALIAS.get(w, w) for w in re.findall(r'[A-Z0-9]+', m.group(2).upper())}
    return m.group(1), words - ADDR_SKIP


def same_address(a, b):
    pa, pb = addr_parts(a), addr_parts(b)
    return bool(pa and pb and pa[0] == pb[0] and pa[1] & pb[1])


def request(svc, bbox):
    """URL for every parcel in a lng/lat bbox from a registered service, or None when it cannot do envelopes."""
    proto = svc.get('protocol', 'query')
    if proto == 'identify':
        env = ','.join(f'{v:.6f}' for v in bbox)
        return (f"{svc['base']}/identify?f=json&geometryType=esriGeometryEnvelope&sr=4326&tolerance=0&layers=all:{svc['layer']}"
                f"&returnGeometry=true&geometry={env}&mapExtent={env}&imageDisplay=1200,1200,96")
    if proto == 'query':
        return arcgis_envelope_query(f"{svc['base']}/{svc['layer']}", bbox, '*', precision=7)
    return None


def analyse(site, fp, cache, broker_acres=None, parent_acres=None, listing_address=None, carve_out=False, pin_approx=False, substation=None):
    """Returns (result dict, error). result['neighbours'] carry shapely lng/lat geometry under 'geom' (not serialised)."""
    r = fp.get('parcel') or {}
    if fp.get('basis') != 'parcel boundary' or not r.get('svc'):
        return None, 'no identified parcel'
    svc = r['svc']
    la, ln = float(site['lat']), float(site['lng'])
    ident = fp['ll']
    fwd = Transformer.from_crs('EPSG:4326', f'+proj=laea +lat_0={la} +lon_0={ln} +datum=WGS84 +units=m', always_xy=True).transform
    minx, miny, maxx, maxy = ident.bounds
    dlat, dlng = QUERY_PAD_M / 110540, QUERY_PAD_M / (111320 * max(0.2, abs(math.cos(math.radians(la)))))
    bbox = (minx - dlng, miny - dlat, maxx + dlng, maxy + dlat)
    url = request(svc, bbox)
    if not url:
        return None, f"parcel service protocol {svc.get('protocol')!r} cannot return neighbours"
    tag = hashlib.md5(repr([round(v, 6) for v in bbox]).encode()).hexdigest()[:10]
    resp, fetched, err = cache.get_json('parcel', coord_key(la, ln, f'neighbours_{tag}'), url)
    if err:
        return None, err
    feats = parcel_mod.features(resp, svc)
    ident_m = transform(fwd, ident)
    ip = r['feature'].get('properties') or {}
    i_apn, i_owner = registry.pick(ip, svc, 'apn'), registry.pick(ip, svc, 'owner')
    seen, nbrs = set(), []
    for f in feats:
        g = f.get('geometry') or {}
        if not g.get('coordinates'):
            continue
        try:
            geom = shape(g)
            geom = geom if geom.is_valid else geom.buffer(0)
        except Exception:
            continue
        gm = transform(fwd, geom)
        if gm.is_empty or gm.area < 20:                     # slivers and road remnants under ~0.005 ac
            continue
        p = f.get('properties') or {}
        apn = registry.pick(p, svc, 'apn')
        ov = gm.intersection(ident_m).area / max(gm.area, 1)
        if ov > 0.9 or (apn and i_apn and str(apn) == str(i_apn)):
            continue                                        # the identified parcel itself (or a duplicate of it)
        k = (str(apn), round(gm.area))
        if k in seen:
            continue
        seen.add(k)
        owner = registry.pick(p, svc, 'owner')
        addr = registry.pick(p, svc, 'address')
        nbrs.append({'apn': apn, 'owner': (owner or '').strip(), 'address': (addr or '').strip(), 'acres': round(parcel_mod.geometry_area_m2(g) / AC, 2),
                     'touches': gm.distance(ident_m) <= 3.0, 'same_owner': same_owner(owner, i_owner),
                     'geom': geom, 'm': gm})
    i_acres = round(parcel_mod.geometry_area_m2(r['feature'].get('geometry')) / AC, 2)
    i_addr = (registry.pick(ip, svc, 'address') or '').strip()
    addr_match = None
    if addr_parts(listing_address):
        if same_address(i_addr, listing_address):
            addr_match = {'where': 'identified parcel', 'address': i_addr}
        else:
            hit = next((n for n in nbrs if same_address(n['address'], listing_address)), None)
            addr_match = {'where': f"neighbour APN {hit['apn']} ({hit['acres']} ac)", 'address': hit['address']} if hit else \
                         {'where': 'no parcel in the neighbourhood', 'address': ''}
    res = {'identified': {'apn': i_apn, 'owner': (i_owner or '').strip(), 'address': i_addr, 'acres': i_acres,
                          'hits_at_pin': r.get('hits', 1), 'internal_only': bool(r.get('exclusion'))},
           'broker_acres': broker_acres, 'parent_acres': parent_acres, 'carve_out': carve_out, 'pin_approx': pin_approx,
           'listing_address': listing_address, 'address_match': addr_match,
           'neighbours': nbrs, 'candidates': None, 'service': svc.get('name'), 'fetched_at': fetched, 'query_bbox': bbox}
    res['substation'] = substation_check(substation, ident_m, None, nbrs, fwd) if substation else None
    sc = res['substation'] or {}
    sub_bad = bool(sc.get('claim') and sc.get('supports') is None and sc.get('identified') is not None)
    matches = bool(broker_acres) and abs(i_acres - broker_acres) / broker_acres <= MATCH_TOL
    if pin_approx and broker_acres and (not matches or sub_bad):
        import candidates
        areas = [(la, ln, APPROX_R_M)]
        if sc.get('claim') == 'adjacent' and sc.get('lat') is not None:
            areas.append((sc['lat'], sc['lng'], NEAR_M))
        cres, cerr = candidates.search(areas, broker_acres, cache, substation=sc if sc.get('lat') is not None else None, owner_like=i_owner)
        res['candidates'] = cres or {'n': None, 'candidates': [], 'error': cerr}
    res['verdict'] = verdict(res)
    return res, None


ADJ_M = 150         # within this of the HIFLD substation point = adjacent (the point can be tens of metres off; a road may lie between)
NEAR_M = 400        # up to this = near: plausible, check imagery; beyond it the broker's 'adjacent' is not consistent


def substation_check(sub, ident_m, likely, nbrs, fwd):
    """Does the identified parcel (and the likely neighbour) border the substation the broker names?
    sub = {'name', 'claim': 'adjacent' | 'distance', 'stated_mi', 'lat', 'lng', 'hifld'} or without lat/lng when not found."""
    from shapely.geometry import Point
    out = {'name': sub['name'], 'claim': sub.get('claim'), 'stated_mi': sub.get('stated_mi'), 'hifld': sub.get('hifld'),
           'lat': sub.get('lat'), 'lng': sub.get('lng')}
    if sub.get('lat') is None:
        out['text'] = f"The broker names {sub['name']} substation, but no substation of that name was found in HIFLD (2021) near the pin."
        return out
    pt = Point(*fwd(sub['lng'], sub['lat']))
    host = next((n for n in nbrs if n['m'].buffer(1).contains(pt)), None)      # the substation's own parcel, if returned

    def rel(geom):
        d = round(geom.distance(pt))
        adj = d <= ADJ_M or (host is not None and host['m'].distance(geom) <= 3.0)
        return {'dist_m': d, 'adjacent': bool(adj), 'near': bool(not adj and d <= NEAR_M)}
    out['identified'] = rel(ident_m)
    out['likely'] = rel(likely['m']) if likely else None
    out['sub_parcel'] = {'apn': host['apn'], 'owner': host['owner']} if host else None
    nm = sub['name']
    i, l = out['identified'], out['likely']
    if sub.get('claim') == 'adjacent':
        if i['adjacent']:
            out['text'], out['supports'] = (f"Consistent: {nm} substation is " + ('next to' if i['dist_m'] else 'on') +
                                            f" the identified parcel ({i['dist_m']:,} m), as the broker states."), 'identified'
        elif l and l['adjacent']:
            out['text'], out['supports'] = (f"The likely parcel is next to {nm} substation ({l['dist_m']:,} m), as the broker states; the identified parcel "
                                            f"is {i['dist_m']:,} m from it."), 'likely'
        elif i['near'] or (l and l['near']):
            out['text'], out['supports'] = (f"Near but not adjacent: {nm} substation is {i['dist_m']:,} m from the identified parcel"
                                            + (f" and {l['dist_m']:,} m from the likely one" if l else '') +
                                            ' (HIFLD points can sit tens of metres off; consistent).'), 'near'
        else:
            out['text'], out['supports'] = (f"Not consistent: the broker says the site is adjacent to {nm} substation, but the identified parcel is "
                                            f"{i['dist_m']:,} m from it" + (f" and the likely parcel {l['dist_m']:,} m" if l else '') + '.'), None
    elif sub.get('stated_mi'):
        mi = i['dist_m'] / 1609.344
        ok = abs(mi - sub['stated_mi']) <= max(0.5, 0.5 * sub['stated_mi'])
        out['text'], out['supports'] = (f"The broker puts {nm} substation ~{sub['stated_mi']:g} mi away; it is {mi:.1f} mi from the identified parcel"
                                        + (' (consistent).' if ok else ' (not consistent).')), ('identified' if ok else None)
    else:
        out['text'], out['supports'] = f"{nm} substation is {i['dist_m']:,} m from the identified parcel.", None
    return out


def ac(x):
    return f'{x:,.1f} ac' if x is not None else '?'


def verdict(res):
    """The location status (location_status.py keys) and the plain statement the exhibit and the memo lead with:
    {'status', 'note', 'match', 'stated', 'found', 'assessment', 'question', 'options'}."""
    i, b = res['identified'], res['broker_acres']
    ia = i['acres']
    stated = ('not stated' if not b else ac(b) + (f" (a carve-out of a ~{ac(res['parent_acres'])} parent tract)" if res['carve_out'] and res['parent_acres']
                                                  else ' (a carve-out)' if res['carve_out'] else ''))
    found = f"{ac(ia)} (APN {i['apn']})" + ('; the broker marks the coordinate approximate' if res['pin_approx'] else '')
    sc = res.get('substation') or {}
    sub_bad = bool(sc.get('claim') and sc.get('supports') is None and sc.get('identified') is not None)
    sub_txt = (' ' + sc['text']) if sub_bad and sc.get('text') else ''
    out = {'stated': stated, 'found': found, 'question': None, 'options': []}
    here = f"APN {i['apn']} ({ac(ia)}{', ' + i['owner'] if i['owner'] else ''})"
    if not b:
        if res['pin_approx']:
            return {**out, 'status': 'needs_input', 'note': 'approximate coordinate, no acreage', 'match': 'unknown',
                    'assessment': 'The broker marks the coordinate approximate and gives no acreage, so the parcel under it cannot be checked.',
                    'question': 'Is the parcel under the approximate coordinate the site?', 'options': [f'Yes: {here}', 'No']}
        return {**out, 'status': 'confirmed', 'note': 'acreage not stated', 'match': 'unknown',
                'assessment': "The broker's pin is taken as the site; no acreage is stated to compare with the parcel under it." + sub_txt}
    diff = (ia - b) / b
    pct = f'{100 * diff:+.0f} %'
    if not res['pin_approx']:
        if sub_bad:
            return {**out, 'status': 'needs_input', 'note': 'substation claim not consistent', 'match': 'yes' if abs(diff) <= MATCH_TOL else 'no',
                    'assessment': f"The parcel under the broker's pin is {ac(ia)} against {ac(b)} stated ({pct}).{sub_txt}",
                    'question': f"The broker says the site is next to {sc['name']} substation, but the parcel under the pin is {sc['identified']['dist_m']:,} m "
                                f"from it. Is the parcel under the pin the site?", 'options': [f'Yes: {here}', 'No']}
        if abs(diff) <= MATCH_TOL:
            return {**out, 'status': 'confirmed', 'note': '', 'match': 'yes',
                    'assessment': f"Match ({pct}): the broker's pin is in a parcel of the stated size."}
        if b < ia:
            said = 'stated' if res['carve_out'] else 'probable'
            return {**out, 'status': 'confirmed_partial', 'note': f'carve-out ({said})', 'match': 'carve-out',
                    'assessment': (f"Carve-out ({'as the broker states' if res['carve_out'] else 'probable: the broker does not say so'}): the {ac(b)} site is part of "
                                   f"the {ac(ia)} parcel under the pin. Where within it is not stated, so parcel figures (flood, wetlands) describe the whole "
                                   f"parcel.")}
        return {**out, 'status': 'confirmed_partial', 'note': 'spans several parcels', 'match': 'spans',
                'assessment': (f"Spans several parcels: the {ac(b)} site is larger than the {ac(ia)} parcel under the pin, so it takes in neighboring "
                               f"parcels. Which ones is not stated, so parcel figures describe this parcel only.")}
    # approximate coordinate
    if abs(diff) <= MATCH_TOL and not sub_bad:
        return {**out, 'status': 'confirmed', 'note': 'approximate coordinate', 'match': 'yes',
                'assessment': f"Match ({pct}): the parcel under the broker's approximate coordinate is the stated size."}
    cr = res.get('candidates') or {}
    cands = cr.get('candidates') or []
    nm = sc.get('name')

    def opt(c):
        return (f"APN {c['apn']}: {ac(c['acres'])}, {c['owner'] or 'no owner'}" + (' (same owner as the parcel under the coordinate)' if c['same_owner'] else '') +
                (f"; {c['sub_m']:,} m from {nm} substation" if c.get('sub_m') is not None else ''))
    why = (f"The broker marks the coordinate approximate, and the parcel under it is {ac(ia)} against {ac(b)} stated ({pct})"
           if abs(diff) > MATCH_TOL else f"The parcel under the broker's approximate coordinate matches the size ({pct})") + '.' + sub_txt
    if cr.get('n') is None:
        return {**out, 'status': 'needs_input', 'note': 'approximate coordinate', 'match': 'no',
                'assessment': why + f" The candidate search failed ({cr.get('error')}): rerun.", 'question': 'Which parcel is the site?', 'options': []}
    import candidates as cmod
    if not cands or len(cands) > cmod.MAX_ASK:
        return {**out, 'status': 'not_locatable', 'note': 'approximate coordinate', 'match': 'no',
                'assessment': why + (f" No other parcel of about {ac(b)} lies within the area searched." if not cands else
                                     f" {len(cands)} parcels of about {ac(b)} lie within the area searched: too many to choose from without more information.")}
    in_list = any(str(c['apn']) == str(i['apn']) for c in cands)
    return {**out, 'status': 'needs_input', 'note': 'approximate coordinate', 'match': 'no',
            'headline': (f"Approximate coordinate; the parcel under it is {ac(ia)} against {ac(b)} stated ({pct}). {len(cands)} candidate parcel"
                         f"{'s' if len(cands) > 1 else ''} of the stated size (A{'-' + chr(64 + len(cands)) if len(cands) > 1 else ''})"
                         + (f"; {nm} substation is {sc['identified']['dist_m']:,} m away, not adjacent." if sub_bad else '.')),
            'assessment': why + f" {len(cands)} parcel{'s' if len(cands) > 1 else ''} of about {ac(b)} (within 15 %) lie in the area the site can be in.",
            'question': 'Which parcel is the site?',
            'options': [f'{chr(65 + k)}: ' + opt(c) for k, c in enumerate(cands)] + ([] if in_list else [f"The parcel under the coordinate: {here}"]) + ['None of these']}


def to_json(res):
    """Serialisable copy for <site>_parcel_check.json (geometry dropped)."""
    def n(x):
        return {k: v for k, v in x.items() if k not in ('geom', 'm', 'utm')}
    out = {k: v for k, v in res.items() if k not in ('neighbours', 'candidates', 'ref_square')}
    if res.get('candidates'):
        import candidates
        out['candidates'] = candidates.to_json(res['candidates']) if res['candidates'].get('n') is not None else res['candidates']
    touch = [n(x) for x in res['neighbours'] if x['touches']]
    out['touching'] = sorted(touch, key=lambda x: (not x['same_owner'], -x['acres']))
    out['neighbours_total'] = len(res['neighbours'])
    out['same_owner_nearby'] = [n(x) for x in res['neighbours'] if x['same_owner']]
    return out
