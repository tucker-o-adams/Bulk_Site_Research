# -*- coding: utf-8 -*-
"""Broker-stated facts and their wording: one place, so the memos (memo.py), the workbook (excel.py) and the ratings
(rate.py) say the same thing in the same words.

Reads input/evidence_checked.csv rows (the checked broker-text extraction, EXTRACTION.md). Nothing here is our check.
"""
import csv, os, re
from collections import OrderedDict

# confidence tags: the short label inside a tagged value ("35 MW (confirmed)"), and the full name of each level
TAG = {'confirmed_written': 'confirmed', 'confirmed_prescreen': 'pre-screen', 'utility_estimate': 'utility est.',
       'broker_estimate': 'broker est.', 'pending': 'pending', 'untagged': ''}
TAG_FULL = OrderedDict([('confirmed_written', 'confirmed in writing'), ('confirmed_prescreen', 'confirmed at pre-screen'),
                        ('utility_estimate', 'utility estimate (verbal)'), ('broker_estimate', 'broker estimate'), ('pending', 'pending'),
                        ('untagged', '')])
STAGE = OrderedDict([('under_contract', 'Under contract'), ('loi_or_negotiating', 'LOI / negotiating'), ('owner_identified', 'Owner identified, no terms'),
                     ('tract_identified', 'Tract identified, no terms'), ('no_site_yet', 'No site yet (searching)'), ('no_site_control', 'No site control (stated)')])
MW_KIND = {'actual': 'stated available', 'request': 'requested', 'up_to': 'up to'}


def rd(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def num(v):
    try:
        return float(str(v).replace(',', ''))
    except (TypeError, ValueError):
        return None


def g(v, suffix=''):
    x = num(v)
    if x is None:
        return '—' if v in (None, '') else str(v)
    return (f'{x:,.0f}' if abs(x) >= 100 or x.is_integer() else f'{x:,.1f}') + suffix


def tagged(value, tag):
    t = TAG.get(tag, tag)
    return f'{value} ({t})' if t else str(value)


def dedupe(xs):
    """Drop a statement whose words are all inside another one (the same caveat stated twice, shorter)."""
    w = [(x, set(re.findall(r'[a-z0-9]+', x.lower()))) for x in xs]
    return [x for i, (x, s) in enumerate(w) if not any(j != i and s < s2 or (s == s2 and j < i) for j, (_, s2) in enumerate(w))]


def market_of(section):
    """The market (MSA) a site_list.csv section heading files the site under."""
    return section.split(' (')[0].split(' · ')[0].title().replace('Msa', 'MSA')


class Broker:
    """Key broker-stated facts for one site, from evidence_checked.csv."""
    def __init__(self, rows):
        self.rows = rows

    def get(self, dim, fld, kinds=None):
        return [r for r in self.rows if r['dimension'] == dim and r['field'] == fld and (kinds is None or r['kind'] in kinds)]

    def first(self, dim, fld, kinds=None):
        x = self.get(dim, fld, kinds)
        return x[0] if x else None

    def vals(self, dim, fld):
        return [r['value'] for r in self.get(dim, fld)]

    def mw(self):
        """(headline MW, kind, tag, text): an actual figure first, then a target/request, then an 'up to'."""
        for fld, kinds, label in (('mw', ('actual',), ''), ('mw_full', ('actual',), ''), ('mw', ('target',), 'requested '), ('mw', ('range_high',), 'up to ')):
            r = self.first('power_capacity', fld, kinds)
            if r:
                return num(r['value']), ('actual' if not label else 'request' if label.startswith('req') else 'up_to'), r['tag_norm'], f"{label}{g(r['value'])} MW"
        return None, None, None, '—'

    def timing(self):
        for fld in ('available', 'initial_available', 'full_available'):
            r = self.first('power_timing', fld)
            if r:
                full = self.first('power_timing', 'full_available')
                txt = r['value'] + (f"; full {full['value']}" if fld == 'initial_available' and full else '')
                return tagged(txt, r['tag_norm'])
        return ''

    def connection(self):
        u = self.first('power_connection', 'utility')
        kv = self.first('power_connection', 'voltage_kv')
        sub = self.first('power_connection', 'substation')
        st = self.first('power_connection', 'substation_status')
        parts = [u['value'] if u else '', f"{g(kv['value'])} kV" if kv else '',
                 (f"sub {sub['value']}" + (' (new)' if st and st['value'] == 'new_or_planned' and '(new)' not in sub['value'] else '')) if sub else '']
        return ' · '.join(p for p in parts if p)

    def cost(self):
        """All-in power cost: '8.0–8.5 ¢/kWh (broker est.)', one decimal as in the summary memo's Power table."""
        rs = self.get('power_cost', 'cents_per_kwh')
        xs = sorted(x for x in (num(r['value']) for r in rs) if x is not None)
        if not xs:
            return ''
        txt = (f'{xs[0]:.1f}' if xs[0] == xs[-1] else f'{xs[0]:.1f}–{xs[-1]:.1f}') + ' ¢/kWh'
        return tagged(txt, rs[0]['tag_norm'])

    def fiber(self):
        s = self.first('fiber', 'status')
        if not s:
            return ''
        if s['value'] != 'quoted':
            return s['value'].replace('_', ' ')
        nrc = self.first('fiber', 'nrc_usd'); r1 = self.first('fiber', 'route1_ft'); r2 = self.first('fiber', 'route2_ft')
        c = self.first('fiber', 'carrier')
        return (f"{c['value'] if c else ''} build ${num(nrc['value']) / 1e6:,.2f}M" if nrc else 'quoted') + \
               (f"; routes {g(r1['value'])} / {g(r2['value'])} ft" if r1 and r2 else '')

    def acres(self):
        a = self.first('acreage', 'acres', ('actual',))
        if a:
            return num(a['value']), tagged(f"{g(a['value'])} ac", a['tag_norm'])
        t = self.first('acreage', 'acres', ('target',))
        return None, (f"target ~{g(t['value'])} ac" if t else '')

    def zoning(self):
        """Jurisdiction · zoning · use permitted · noise rule, tagged with the zoning statement's tag."""
        j, z, u, n = (self.first('zoning_neighbours', f) for f in ('jurisdiction', 'zoning', 'use_permitted', 'noise_rule'))
        parts = [j['value'] if j else '', z['value'] if z else '', f"use permitted: {u['value']}" if u else '', n['value'] if n else '']
        txt = ' · '.join(p for p in parts if p)
        lead = z or j or u or n
        return tagged(txt, lead['tag_norm']) if txt else ''

    def stage(self):
        r = self.first('site_control', 'stage')
        return r['value'] if r else ''

    def owner(self):
        """What the broker says about the owner (the summary memo's Appendix B)."""
        return '; '.join(self.vals('site_control', 'owner_type') + self.vals('site_control', 'detail'))

    def constraints(self):
        return [r['value'] for r in self.get('grid_constraints', 'constraint')]

    def caveats(self):
        """Grid constraints and other notes, a statement kept once (the summary memo's Appendix A)."""
        return dedupe(self.constraints() + self.vals('other', 'detail'))

    def flood_claims(self):
        return [r['value'] for r in self.get('flood_wetlands', 'claim')]
