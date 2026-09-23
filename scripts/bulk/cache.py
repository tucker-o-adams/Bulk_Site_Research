# -*- coding: utf-8 -*-
"""Raw-response cache, shared across batches.

Every service answer is saved once per (producer, key). Keys are built from the
query location (see `coord_key`), not the site_id, so the same place fetched in
any batch is never fetched twice, and a rerun of any batch is offline. A failed
query is never cached, so a rerun retries exactly the gaps.

Layout:  <repo>/data/cache/<producer>/<key>.json
         {"fetched_at": ..., "url": ..., "response": <parsed JSON>}
Delete a file (or a producer folder) to refresh from source.
"""
import json, os, re, time, urllib.request
from datetime import datetime, timezone

UA = {'User-Agent': 'Mozilla/5.0 (TBDI bulk site research)'}


def coord_key(lat, lng, suffix=''):
    """Cache key for a point query: coordinates to 1e-5 deg (~1 m), plus a sub-query tag."""
    return f'{lat:.5f}_{lng:.5f}' + (f'_{suffix}' if suffix else '')


def _safe(key: str) -> str:
    return re.sub(r'[^A-Za-z0-9._-]+', '_', key)[:120]


class Cache:
    def __init__(self, root: str, offline: bool = False):
        self.root = root
        self.offline = offline      # a miss returns an error instead of fetching (kmz.py: map what was measured)
        self.hits = 0
        self.misses = 0

    def path(self, producer: str, key: str) -> str:
        d = os.path.join(self.root, producer)
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, _safe(key) + '.json')

    def get_json(self, producer: str, key: str, url: str, timeout=60, tries=3):
        """Return (parsed_json_or_None, fetched_at, error_or_None). Cached on success."""
        p = self.path(producer, key)
        if os.path.exists(p):
            rec = json.load(open(p, encoding='utf-8'))
            self.hits += 1
            return rec['response'], rec['fetched_at'], None
        self.misses += 1
        if self.offline:
            return None, None, 'not in cache (offline)'
        err = None
        for i in range(tries):
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                    body = r.read().decode('utf-8', 'replace')
                resp = json.loads(body)
                if isinstance(resp, dict) and 'error' in resp:
                    err = f"service error: {str(resp['error'])[:160]}"
                    break                      # a real answer from the service; don't hammer it
                # ArcGIS caps a query at the layer's maxRecordCount and flags it; a capped answer would
                # undercount (schools within 5 km in a metro) or miss the true nearest, so it is a failure,
                # never cached. Windstream's rural 200 never hit it; a dense-metro batch might.
                if isinstance(resp, dict) and (resp.get('exceededTransferLimit') or
                                               (resp.get('properties') or {}).get('exceededTransferLimit')):
                    err = ('result truncated at the service record limit (exceededTransferLimit) - '
                           'counts and nearest values would be wrong; needs paging or a smaller radius')
                    break
                fetched = datetime.now(timezone.utc).isoformat(timespec='seconds')
                with open(p, 'w', encoding='utf-8') as f:
                    json.dump({'fetched_at': fetched, 'url': url, 'response': resp}, f,
                              separators=(',', ':'))
                return resp, fetched, None
            except Exception as e:
                err = f'{type(e).__name__}: {str(e)[:160]}'
                if i < tries - 1:
                    time.sleep(1.5 * (i + 1))
        return None, None, err
