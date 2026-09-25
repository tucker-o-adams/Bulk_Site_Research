# -*- coding: utf-8 -*-
"""The value record every producer returns.

A field without its source is not a result. Each value the pipeline writes
carries where it came from, when, by what method, and whether the source
actually answered — so the workbook can defend every cell in a data room and
an honest "absent" or "failed" never masquerades as a number.

status:
    ok       the source returned a value
    absent   the source confirmed there is nothing there (e.g. no line within
             the search radius). This is an answer, not an error.
    failed   the source could not be reached or returned an error; value is None
    manual   supplied by a person (reserved: no producer writes it today)
    not_assessable  the site's location is too rough for this field (location tier L3-L5, see tiers.py);
             value is None. Not a gap in the source and not a finding about the site.
"""
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Optional

STATUSES = ('ok', 'absent', 'failed', 'manual', 'not_assessable')


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


@dataclass
class Value:
    field: str                      # column name in the Sites sheet
    value: Any                      # the number/string, or None when absent/failed
    source: str                     # short source name, e.g. "HIFLD Electric Power Transmission Lines (mirror)"
    source_url: str                 # the service or download URL
    method: str                     # one line: how the value was derived
    status: str = 'ok'
    vintage: Optional[str] = None   # the source's own data date, when it publishes one
    fetched_at: str = field(default_factory=now_iso)
    note: Optional[str] = None      # caveat that travels with the value

    def __post_init__(self):
        if self.status not in STATUSES:
            raise ValueError(f'bad status {self.status!r} for {self.field}')
        if self.status in ('absent', 'failed', 'not_assessable') and self.value is not None:
            raise ValueError(f'{self.field}: status {self.status} must carry value None')

    def row(self, site_id: str) -> dict:
        d = asdict(self)
        d['site_id'] = site_id
        return d


PROVENANCE_COLUMNS = ['site_id', 'field', 'value', 'status', 'source', 'source_url',
                      'vintage', 'fetched_at', 'method', 'note']


def absent(field, source, source_url, method, note=None, vintage=None) -> Value:
    return Value(field, None, source, source_url, method, status='absent', note=note, vintage=vintage)


def not_assessable(field, source, source_url, method, note) -> Value:
    return Value(field, None, source, source_url, method, status='not_assessable', note=note)


def failed(field, source, source_url, method, note) -> Value:
    return Value(field, None, source, source_url, method, status='failed', note=note)
