"""Shared helpers for the onsen-finder data pipeline (standard library only)."""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'data')
DOCS = os.path.join(ROOT, 'docs')

USER_AGENT = 'onsen-finder/1.0 (https://github.com/davepomerlo/onsen-finder; weekly data refresh)'


def http_get(url, params=None, data=None, headers=None, retries=4, timeout=90):
    """GET (or POST when data is given) with retries and back-off. Returns (status, bytes)."""
    if params:
        url = url + ('&' if '?' in url else '?') + urllib.parse.urlencode(params)
    h = {'User-Agent': USER_AGENT, 'Accept-Encoding': 'identity'}
    if headers:
        h.update(headers)
    body = urllib.parse.urlencode(data).encode() if isinstance(data, dict) else data
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=body, headers=h)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (404, 410):
                return e.code, b''
            if e.code == 429 or e.code >= 500:
                time.sleep(int(e.headers.get('Retry-After', 0) or 0) or 10 * (attempt + 1))
                continue
            raise
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last = e
            time.sleep(10 * (attempt + 1))
    raise RuntimeError(f'GET failed after {retries} tries: {url[:120]} ({last})')


def load_json(name, default=None):
    path = os.path.join(DATA, name)
    if not os.path.exists(path):
        return default
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def save_json_lines(path, rows):
    """Write a JSON array with one record per line (diff-friendly)."""
    with open(path, 'w', encoding='utf-8') as f:
        f.write('[\n' + ',\n'.join(json.dumps(r, ensure_ascii=False, separators=(',', ':')) for r in rows) + '\n]\n')


def save_json(path, obj):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write('\n')
