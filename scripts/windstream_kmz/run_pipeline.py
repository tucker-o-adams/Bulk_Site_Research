# -*- coding: utf-8 -*-
"""Rebuild TBDI_WS_Combined_3.kmz from project inputs only.

Steps (each script is standalone; this just runs them in order and stops on failure):
    parse_kmz               broker KMZ -> ws_broker_sites.csv (the Interesting Sites list)
    build_kmz               sites + frozen HIFLD 5 km segments        -> WS_Sites_and_Transmission_3.kmz
    merge_kmz               + broker overview + parcel results (B, C) -> TBDI_WS_Combined_3.kmz
    add_folders             + nearest segment / connector per site (D), Interesting Sites (E)
    add_verify              + per-site verification folders by state (F)
    add_interesting_verify  + Interesting-only subset inside F
    add_parcels             + parcel polygons (G, and into F)

Inputs that come from the network are NOT fetched here. Run the fetch_*.py
scripts first when you want to refresh them:
    fetch_hifld_segments.py   -> hifld_tx_segments_5km.geojson, hifld_tx_nearest_segments.geojson
    fetch_parcel_polygons.py  -> parcel_polygons.geojson

Usage (from anywhere):
    .venv_fema/Scripts/python.exe scripts/windstream_kmz/run_pipeline.py
"""
import os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
STEPS = ['parse_kmz', 'build_kmz', 'merge_kmz', 'add_folders', 'add_verify',
         'add_interesting_verify', 'add_parcels']

from paths import HIFLD_5KM, HIFLD_NEAREST, PARCEL_POLYS, BROKER_KMZ, TX_CSV, PARCEL_CSV

for label, p in [('HIFLD 5 km segments', HIFLD_5KM), ('HIFLD nearest segments', HIFLD_NEAREST),
                 ('parcel polygons', PARCEL_POLYS), ('broker KMZ', BROKER_KMZ),
                 ('transmission CSV', TX_CSV), ('parcel CSV', PARCEL_CSV)]:
    if not os.path.exists(p):
        sys.exit(f'missing input: {label} -> {p}')

t0 = time.time()
for step in STEPS:
    print(f'\n{"=" * 20} {step} {"=" * 20}', flush=True)
    r = subprocess.run([sys.executable, os.path.join(HERE, step + '.py')], cwd=HERE)
    if r.returncode != 0:
        sys.exit(f'{step} failed (exit {r.returncode})')
print(f'\npipeline complete in {time.time() - t0:.0f}s')
