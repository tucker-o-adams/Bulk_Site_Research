# -*- coding: utf-8 -*-
"""USFWS National Wetlands Inventory at and around the site point.

  status    Wetlands_Status L0   is this area mapped at all (Digital / No Data / ...)
  vintage   Data_Source L2       imagery year the mapping was interpreted from
  at point  Wetlands L0          the NWI polygon under the pin, if any
  nearby    Wetlands L0, 500 m   nearest NWI polygon: distance, Cowardin type, code, acres;
                                 count and summed polygon acres within the buffer

Zero is not the same as no wetlands (tbdi-pasa): an unmapped area returns no
polygons too, so `nwi_mapping_status` travels with every row. Even a mapped
zero is not a clearance — NWI is photointerpreted and FWS states it is not a
jurisdictional determination. Acres are the full NWI polygon's acres, not a
clip to anything.
"""
from geom import arcgis_query, geojson_polygon_dist_m
from provenance import Value, absent, failed, now_iso
from cache import coord_key

NAME = 'wetlands'
BASE = 'https://fwspublicservices.wim.usgs.gov/wetlandsmapservice/rest/services'
WET = f'{BASE}/Wetlands/MapServer/0'
STATUS = f'{BASE}/Wetlands_Status/MapServer/0'
IMGYR = f'{BASE}/Data_Source/MapServer/2'
LYR = WET
SOURCE = 'USFWS National Wetlands Inventory (NWI)'
VINTAGE = None                      # per site: imagery year from Data_Source
SEARCH_M = 500
METHOD = (f'NWI point queries: Wetlands polygon at the point; nearest Wetlands polygon within {SEARCH_M} m '
          'by exact point-to-polygon distance (geometry simplified to ~2 m); Wetlands_Status for mapping coverage; Data_Source for imagery year')
NOTE = 'NWI is photointerpreted, not a jurisdictional determination; acres are whole NWI polygons, not clipped'

FIELDS = ['nwi_mapping_status', 'nwi_image_year', 'nwi_project', 'nwi_at_point', 'nwi_type_at_point',
          'nwi_code_at_point', 'nwi_nearest_m', 'nwi_nearest_type', 'nwi_nearest_code', 'nwi_nearest_acres',
          f'nwi_count_within_{SEARCH_M}m', f'nwi_polygon_acres_within_{SEARCH_M}m']


def _attr(props, suffix):
    for k, v in (props or {}).items():
        if k.upper().endswith(suffix.upper()):
            return v
    return None


def run(site, cache):
    la, ln = site.lat, site.lng
    st, f1, e1 = cache.get_json(NAME, coord_key(la, ln, 'status'), arcgis_query(STATUS, la, ln, 'STATUS'))
    iy, f2, e2 = cache.get_json(NAME, coord_key(la, ln, 'imgyr'), arcgis_query(IMGYR, la, ln, 'PROJECT_NAME,IMAGE_YR'))
    # geometry simplified to ~2 m: a riverine polygon (e.g. the Ohio River) otherwise comes back at 100+ MB
    near, f3, e3 = cache.get_json(NAME, coord_key(la, ln, f'near{SEARCH_M}'),
                                  arcgis_query(WET, la, ln, '*', distance_m=SEARCH_M, geometry=True,
                                               fmt='geojson', precision=6, max_offset_m=2))
    fetched = f3 or now_iso()
    if e3:
        return [failed(f, SOURCE, WET, METHOD, e3) for f in FIELDS]

    status = None if e1 else (((st.get('features') or [{}])[0].get('attributes') or {}).get('STATUS'))
    yr_row = None if e2 else (((iy.get('features') or [{}])[0].get('attributes') or {}))
    year = yr_row.get('IMAGE_YR') if yr_row else None
    project = yr_row.get('PROJECT_NAME') if yr_row else None
    vint = str(year) if year else None

    def mk(fld, val, note=NOTE):
        return Value(fld, val, SOURCE, WET, METHOD, vintage=vint, fetched_at=fetched, note=note)

    out = []
    out.append(failed('nwi_mapping_status', SOURCE, STATUS, METHOD, e1) if e1 else
               mk('nwi_mapping_status', status) if status else
               absent('nwi_mapping_status', SOURCE, STATUS, METHOD, note='no Wetlands_Status polygon at the point (unmapped)'))
    if e2:
        out += [failed(f, SOURCE, IMGYR, METHOD, e2) for f in ('nwi_image_year', 'nwi_project')]
    else:
        out += [mk('nwi_image_year', year) if year else absent('nwi_image_year', SOURCE, IMGYR, METHOD, note='no Data_Source record at the point'),
                mk('nwi_project', project) if project else absent('nwi_project', SOURCE, IMGYR, METHOD, note='no Data_Source record at the point')]

    feats = near.get('features') or []
    scored = []
    for f in feats:
        p = f.get('properties') or {}
        d = geojson_polygon_dist_m(f.get('geometry'), ln, la)
        scored.append((d, _attr(p, 'WETLAND_TYPE'), _attr(p, 'ATTRIBUTE'), _attr(p, 'ACRES')))
    scored.sort(key=lambda x: x[0])
    at = [s for s in scored if s[0] == 0.0]
    unmapped_note = None if status else 'area is not NWI-mapped; absence of polygons is not evidence of no wetlands'

    if at:
        out += [mk('nwi_at_point', True), mk('nwi_type_at_point', at[0][1]), mk('nwi_code_at_point', at[0][2])]
    else:
        out += [mk('nwi_at_point', False, note=unmapped_note or NOTE),
                absent('nwi_type_at_point', SOURCE, WET, METHOD, note=unmapped_note or 'no NWI polygon at the point', vintage=vint),
                absent('nwi_code_at_point', SOURCE, WET, METHOD, note=unmapped_note or 'no NWI polygon at the point', vintage=vint)]
    if scored:
        d, t, c, a = scored[0]
        out += [mk('nwi_nearest_m', round(d, 1)), mk('nwi_nearest_type', t), mk('nwi_nearest_code', c),
                mk('nwi_nearest_acres', round(float(a), 3) if a is not None else None)]
    else:
        out += [absent(f, SOURCE, WET, METHOD, note=unmapped_note or f'no NWI polygon within {SEARCH_M} m', vintage=vint)
                for f in ('nwi_nearest_m', 'nwi_nearest_type', 'nwi_nearest_code', 'nwi_nearest_acres')]
    total = sum(float(s[3]) for s in scored if s[3] is not None)
    out += [mk(f'nwi_count_within_{SEARCH_M}m', len(scored), note=unmapped_note or NOTE),
            mk(f'nwi_polygon_acres_within_{SEARCH_M}m', round(total, 3), note=unmapped_note or NOTE)]
    return out
