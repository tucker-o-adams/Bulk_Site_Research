# -*- coding: utf-8 -*-
"""Producers: one module per field group. Each exposes

    NAME = 'transmission'
    FIELDS = [...]                       # the Sites-sheet columns it fills, in order
    def run(site, cache) -> list[Value]  # one Value per FIELD, always, in FIELD order

A producer never raises on a bad answer from its source: it returns Values with
status absent/failed and a note. It may keep extra geometry in cache for the
KMZ step, but the Values are the contract.
"""
