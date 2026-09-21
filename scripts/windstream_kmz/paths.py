# -*- coding: utf-8 -*-
"""Project-relative paths shared by the Windstream KMZ pipeline.

Everything resolves from this file's location, so the pipeline runs from any
checkout of the repo. Nothing here points at a prior KMZ: every geometry input
is either a project data file frozen from its source by a fetch_*.py script, or
the broker's own overview KMZ.
"""
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

# --- inputs ---
WS_DATA = os.path.join(ROOT, 'Windstream site data')
XLS_OUT = os.path.join(ROOT, 'Outputs', 'Excel outputs')
KMZ_OUT = os.path.join(ROOT, 'Outputs', 'KMZ outputs')
REFERENCE = os.path.join(ROOT, 'Reference')

WS200_XLSX = os.path.join(WS_DATA, 'TBDI Windstream Top 200 COs v6.29.26 vTA.xlsx')
BROKER_KMZ = os.path.join(REFERENCE, 'WS Targeted Sites Overview 26.8.20.kmz')

TX_CSV = os.path.join(XLS_OUT, 'WS_Top200_Transmission_Distance.csv')
PARCEL_CSV = os.path.join(XLS_OUT, 'WS_Sites_Parcel_Sizes_FINAL.csv')

# frozen-from-source geometry (written by fetch_hifld_segments.py / fetch_parcel_polygons.py)
HIFLD_5KM = os.path.join(WS_DATA, 'hifld_tx_segments_5km.geojson')
HIFLD_NEAREST = os.path.join(WS_DATA, 'hifld_tx_nearest_segments.geojson')
PARCEL_POLYS = os.path.join(WS_DATA, 'parcel_polygons.geojson')
WS_SITES_CSV = os.path.join(WS_DATA, 'ws_broker_sites.csv')   # written by parse_kmz.py

# --- outputs ---
TX_KMZ = os.path.join(KMZ_OUT, 'WS_Sites_and_Transmission_3.kmz')   # step 2 intermediate
COMBINED_KMZ = os.path.join(KMZ_OUT, 'TBDI_WS_Combined_3.kmz')     # steps 3-6 build this in place


def load_geojson_lines(*paths):
    """Return {HIFLD ID (str): (props, [ [ (lng,lat), ... ], ... ])} from GeoJSON files.
    Later files do not overwrite earlier ones."""
    import json
    lines = {}
    for p in paths:
        for f in json.load(open(p, encoding='utf-8'))['features']:
            props = f.get('properties') or {}
            lid = props.get('ID')
            if lid is None or str(lid) in lines:
                continue
            g = f.get('geometry') or {}
            parts = ([g['coordinates']] if g.get('type') == 'LineString'
                     else g.get('coordinates') if g.get('type') == 'MultiLineString' else [])
            if parts:
                lines[str(lid)] = (props, parts)
    return lines
