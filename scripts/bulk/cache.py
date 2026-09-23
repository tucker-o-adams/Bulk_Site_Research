# -*- coding: utf-8 -*-
"""Raw-response cache, shared across batches.

Every service answer is saved once per (producer, key). Keys are built from the
query location (see `coord_key`), not the site_id, so the same place fetched in
any batch is never fetched twice, and a rerun of any batch is offline. A failed
query is never cached, so a rerun retries exactly the gaps.

Layout:  <repo>/data/cache/<producer>/<key>.json
         {"fetched_at": ..., "url": ..., "response": <parsed JSON>}
Delete a file (or a producer folder) to refresh from source. A cached answer is reused only when it
came from the same service endpoint (host + path) the code asks now, so replacing a registered parcel
service refetches rather than serving the old service's answer.
"""
import json, os, re, time, urllib.parse, urllib.request
from datetime import datetime, timezone

UA = {'User-Agent': 'Mozilla/5.0 (TBDI bulk site research)'}


def coord_key(lat, lng, suffix=''):
    """Cache key for a point query: coordinates to 1e-5 deg (~1 m), plus a sub-query tag."""
    return f'{lat:.5f}_{lng:.5f}' + (f'_{suffix}' if suffix else '')


def endpoint(url):
    """The service a URL asks (host + path, lower-cased), ignoring the query string. Query parameters
    drift harmlessly (float formatting, a simplification tolerance added later); the endpoint changing
    means a different service answered."""
    s = urllib.parse.urlsplit(url or '')
    return f'{s.netloc}{s.path}'.lower().rstrip('/')


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
        stale = None
        if os.path.exists(p):
            rec = json.load(open(p, encoding='utf-8'))
            if endpoint(rec.get('url')) == endpoint(url):
                self.hits += 1
                return rec['response'], rec['fetched_at'], None
            # Same place, different service (a parcel registry entry replaced): the cached answer is not
            # this service's. Refetch; the file is overwritten only when the new service answers.
            stale = f"cached answer came from {endpoint(rec.get('url'))}, not {endpoint(url)}"
        self.misses += 1
        if self.offline and stale:
            return None, None, f'{stale} (offline: rerun run.py)'
        if self.offline:
            return None, None, 'not in cache (offline)'
        err = None
        for i in range(tries):
            try:
                resp = _fetch(url, timeout)
                if isinstance(resp, dict) and 'error' in resp:
                    err = f"service error: {str(resp['error'])[:160]}"
                    break                      # a real answer from the service; don't hammer it
                pages = 1
                if _truncated(resp):
                    # ArcGIS caps a query at the layer's maxRecordCount and flags it. A capped answer would
                    # undercount (schools within 5 km in a metro) or miss the true nearest, so page through
                    # the rest; if the service cannot page, it is a failure, never cached.
                    resp, pages, err = _page(url, resp, timeout)
                    if err:
                        break
                fetched = datetime.now(timezone.utc).isoformat(timespec='seconds')
                rec = {'fetched_at': fetched, 'url': url, 'response': resp}
                if pages > 1:
                    rec['pages'] = pages
                with open(p, 'w', encoding='utf-8') as f:
                    json.dump(rec, f, separators=(',', ':'))
                return resp, fetched, None
            except Exception as e:
                err = f'{type(e).__name__}: {str(e)[:160]}'
                if i < tries - 1:
                    time.sleep(1.5 * (i + 1))
        return None, None, err


MAX_PAGES = 50


def _fetch(url, timeout):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8', 'replace'))


def _truncated(resp):
    return isinstance(resp, dict) and bool(resp.get('exceededTransferLimit') or
                                           (resp.get('properties') or {}).get('exceededTransferLimit'))


def _page(url, first, timeout):
    """(merged response, pages, error). Follows resultOffset until the service stops flagging
    exceededTransferLimit. Records are never de-duplicated - a source can hold identical records (three
    IRS filings geocoded to one address) and the count must match a single uncapped request. A page that
    repeats the first page means the service ignores resultOffset: report it, never a partial answer."""
    parts = urllib.parse.urlsplit(url)
    if not parts.path.rstrip('/').endswith('/query'):
        return None, 1, 'result truncated at the service record limit and the request is not a pageable /query'
    q = [(k, v) for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True) if k != 'resultOffset']
    feats = list(first.get('features') or [])
    head = json.dumps(feats[:3], sort_keys=True)
    resp, pages = first, 1
    while _truncated(resp):
        if pages >= MAX_PAGES:
            return None, pages, f'result still truncated after {pages} pages - use a smaller radius'
        nxt = urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(q + [('resultOffset', len(feats))])))
        resp = _fetch(nxt, timeout)
        if isinstance(resp, dict) and 'error' in resp:
            return None, pages, f"result truncated and paging failed: {str(resp['error'])[:120]}"
        page = resp.get('features') or []
        if not page or json.dumps(page[:3], sort_keys=True) == head:
            return None, pages, ('result truncated at the service record limit and the service does not page '
                                 '(resultOffset ignored) - use a smaller radius')
        feats += page
        pages += 1
    merged = dict(first)
    merged['features'] = feats
    merged.pop('exceededTransferLimit', None)
    if isinstance(merged.get('properties'), dict):
        merged['properties'] = {k: v for k, v in merged['properties'].items() if k != 'exceededTransferLimit'}
    return merged, pages, None
