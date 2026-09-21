# -*- coding: utf-8 -*-
"""FEMA flood hazard at the site point, from the National Flood Hazard Layer.

Four questions, four NFHL layers, all point queries:

  zone         L28 Flood Hazard Zones      FLD_ZONE, ZONE_SUBTY, SFHA_TF, STATIC_BFE at the point
  coverage     L22 Political Jurisdictions ANI_TF = T means FEMA carries the area as
                                           "Area Not Included" on the effective FIRM
               L0  NFHL Availability       whether any NFHL study covers the point
  panel        L3  FIRM Panels             effective panel + date (the citation)
  proximity    L28 again, 1 km buffer, SFHA_TF = 'T', with geometry: distance to the
                                           nearest Special Flood Hazard Area polygon

Unmapped is not absent (tbdi-pasa D-008). A point that returns no zone is
either "Area Not Included" or "no NFHL data" and `fema_determination` says
which. Zone X is only reported when the layer actually returned Zone X.

This is the point under the pin, not the parcel. A parcel-clipped SFHA acreage
is a later, per-survivor step.
"""
from datetime import datetime, timezone
from geom import arcgis_query, geojson_polygon_dist_m
from provenance import Value, absent, failed, now_iso

NAME = 'flood'
NFHL = 'https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer'
LYR = NFHL
SOURCE = 'FEMA National Flood Hazard Layer (NFHL)'
VINTAGE = None                      # per site: the effective FIRM panel date
SFHA_ZONES = {'A', 'AE', 'AH', 'AO', 'AR', 'A99', 'V', 'VE'}
SFHA_SEARCH_M = 1000
METHOD = ('NFHL point queries: L28 Flood Hazard Zones at the point; L22 Political Jurisdictions '
          'ANI_TF and L0 NFHL Availability for coverage; L3 FIRM Panels for the effective panel; '
          f'nearest SFHA polygon (SFHA_TF=T) within {SFHA_SEARCH_M} m by exact point-to-polygon distance')
NOTE = 'point under the pin, not the parcel; Area Not Included / no-data is never reported as Zone X'

FIELDS = ['fema_determination', 'fema_flood_zone', 'fema_zone_subtype', 'fema_sfha',
          'fema_static_bfe_ft', 'fema_dfirm_id', 'fema_firm_panel', 'fema_panel_effective',
          'fema_nearest_sfha_m', 'fema_nearest_sfha_zone']


def _epoch_to_date(ms):
    try:
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date().isoformat()
    except (TypeError, ValueError, OSError):
        return None


def _q(cache, site, key, url):
    resp, fetched, err = cache.get_json(NAME, f'{site.site_id}_{key}', url)
    if err:
        return None, fetched, err
    return [f for f in (resp.get('features') or [])], fetched, None


def run(site, cache):
    la, ln = site.lat, site.lng
    zones, f1, e1 = _q(cache, site, 'zone', arcgis_query(f'{NFHL}/28', la, ln, 'FLD_ZONE,ZONE_SUBTY,SFHA_TF,STATIC_BFE,DFIRM_ID'))
    pol, f2, e2 = _q(cache, site, 'pol', arcgis_query(f'{NFHL}/22', la, ln, 'POL_NAME1,ANI_TF,CID'))
    avail, f3, e3 = _q(cache, site, 'avail', arcgis_query(f'{NFHL}/0', la, ln, 'STUDY_ID'))
    pans, f4, e4 = _q(cache, site, 'panel', arcgis_query(f'{NFHL}/3', la, ln, 'DFIRM_ID,FIRM_PAN,EFF_DATE'))
    sfha, f5, e5 = _q(cache, site, 'sfha1km', arcgis_query(f'{NFHL}/28', la, ln, 'FLD_ZONE,SFHA_TF',
                                                             distance_m=SFHA_SEARCH_M, geometry=True,
                                                             where="SFHA_TF='T'", fmt='geojson',
                                                             precision=6, max_offset_m=5))
    fetched = f1 or now_iso()
    if e1:   # no zone answer at all: nothing below can be trusted
        return [failed(f, SOURCE, NFHL, METHOD, e1) for f in FIELDS]
    pol = pol or []
    avail = avail or []

    # --- panel: prefer the one whose DFIRM matches the zone's DFIRM (panels are quads and overlap counties)
    zone = (zones[0]['attributes'] if zones else {})
    dfirm = zone.get('DFIRM_ID')
    panel = None
    if pans and not e4:
        cands = [p['attributes'] for p in pans]
        panel = next((p for p in cands if dfirm and str(p.get('FIRM_PAN', '')).startswith(str(dfirm))), cands[0])
    eff = _epoch_to_date(panel.get('EFF_DATE')) if panel else None
    vint = eff

    def mk(fld, val, note=NOTE):
        return Value(fld, val, SOURCE, NFHL, METHOD, vintage=vint, fetched_at=fetched, note=note)

    # --- determination (coverage queries may have failed independently of the zone query)
    ani = any((p['attributes'].get('ANI_TF') or '').upper() == 'T' for p in pol)
    if zones:
        det = 'mapped'
    elif e2 or e3:
        det = None                    # no zone, and the coverage layers did not answer: cannot say why
    elif ani:
        det = 'area_not_included'
    elif not avail:
        det = 'no_nfhl_data'
    else:
        det = 'no_zone_returned'      # study exists but the point fell in no zone polygon (rare; check)

    out = [mk('fema_determination', det) if det else
           failed('fema_determination', SOURCE, NFHL, METHOD, '; '.join(e for e in (e2, e3) if e))]
    if zones:
        z = zone.get('FLD_ZONE')
        bfe = zone.get('STATIC_BFE')
        bfe = None if bfe is None or float(bfe) <= -9999 else float(bfe)
        out += [mk('fema_flood_zone', z), mk('fema_zone_subtype', zone.get('ZONE_SUBTY')),
                mk('fema_sfha', (zone.get('SFHA_TF') or '').upper() == 'T' or z in SFHA_ZONES),
                mk('fema_static_bfe_ft', bfe), mk('fema_dfirm_id', dfirm)]
    else:
        why = {'area_not_included': 'FEMA carries this point as Area Not Included on the effective FIRM (L22 ANI_TF=T); no flood determination exists',
               'no_nfhl_data': 'no NFHL study covers this point (L0 Availability empty)',
               'no_zone_returned': 'NFHL study exists but L28 returned no zone polygon at the point',
               None: 'no zone polygon at the point and the coverage layers (L22/L0) did not answer'}[det]
        out += [absent(f, SOURCE, NFHL, METHOD, note=why, vintage=vint)
                for f in ('fema_flood_zone', 'fema_zone_subtype', 'fema_sfha', 'fema_static_bfe_ft', 'fema_dfirm_id')]

    if panel:
        out += [mk('fema_firm_panel', panel.get('FIRM_PAN')), mk('fema_panel_effective', eff)]
    elif e4:
        out += [failed(f, SOURCE, NFHL, METHOD, e4) for f in ('fema_firm_panel', 'fema_panel_effective')]
    else:
        out += [absent(f, SOURCE, NFHL, METHOD, note='no FIRM panel at the point', vintage=vint)
                for f in ('fema_firm_panel', 'fema_panel_effective')]

    # --- nearest SFHA within 1 km
    if e5:
        out += [failed(f, SOURCE, NFHL, METHOD, e5) for f in ('fema_nearest_sfha_m', 'fema_nearest_sfha_zone')]
    else:
        best = None
        for f in sfha:
            d = geojson_polygon_dist_m(f.get('geometry'), ln, la)
            if best is None or d < best[0]:
                best = (d, (f.get('properties') or {}).get('FLD_ZONE'))
        if best:
            out += [mk('fema_nearest_sfha_m', round(best[0], 1)), mk('fema_nearest_sfha_zone', best[1])]
        else:
            out += [absent(f, SOURCE, NFHL, METHOD, note=f'no SFHA polygon within {SFHA_SEARCH_M} m', vintage=vint)
                    for f in ('fema_nearest_sfha_m', 'fema_nearest_sfha_zone')]
    return out
