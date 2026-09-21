# -*- coding: utf-8 -*-
"""Raw-response cache: every service answer is saved once per (producer, key),
so a rerun of the same batch makes no network calls and reproduces exactly
what the first run saw. Delete a file (or the folder) to refresh from source.

Layout:  <out>/cache/<producer>/<key>.json
         {"fetched_at": ..., "url": ..., "response": <parsed JSON>}
"""
import json, os, re, time, urllib.request
from datetime import datetime, timezone

UA = {'User-Agent': 'Mozilla/5.0 (TBDI bulk site research)'}


def _safe(key: str) -> str:
    return re.sub(r'[^A-Za-z0-9._-]+', '_', key)[:120]


class Cache:
    def __init__(self, root: str):
        self.root = root
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
        err = None
        for i in range(tries):
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                    body = r.read().decode('utf-8', 'replace')
                resp = json.loads(body)
                if isinstance(resp, dict) and 'error' in resp:
                    err = f"service error: {str(resp['error'])[:160]}"
                    break                      # a real answer from the service; don't hammer it
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
