"""Geocode addresses of hand-added onsen (data/curated.py) with the GSI address search (国土地理院).

Results are cached in data/geocode.json as {address: [lat, lon, matched_title]} so each address is looked
up once. Run before build.py.
"""
import importlib.util
import json
import os
import time
import urllib.parse

from common import DATA, http_get, load_json, save_json

GSI = 'https://msearch.gsi.go.jp/address-search/AddressSearch?q='


def main():
    spec = importlib.util.spec_from_file_location('curated', os.path.join(DATA, 'curated.py'))
    cur = importlib.util.module_from_spec(spec); spec.loader.exec_module(cur)
    addrs = [e['new']['addr'] for e in list(cur.C) + list(getattr(cur, 'H', [])) if 'new' in e and e['new'].get('addr')]
    cache = load_json('geocode.json', {}) or {}
    done = 0
    for a in addrs:
        if a in cache:
            continue
        try:
            status, body = http_get(GSI + urllib.parse.quote(a), retries=2, timeout=30)
            res = json.loads(body) if status == 200 else []
        except Exception as e:
            print('geocode failed:', a, e); continue
        if res:
            lon, lat = res[0]['geometry']['coordinates']
            cache[a] = [round(lat, 5), round(lon, 5), res[0]['properties'].get('title', '')]
            print(f'{a} -> {lat:.5f}, {lon:.5f} ({cache[a][2]})')
            done += 1
        else:
            print('no match:', a)
        time.sleep(1)
    save_json(os.path.join(DATA, 'geocode.json'), cache)
    print(f'Geocoded {done} new address(es); {len(cache)} cached.')


if __name__ == '__main__':
    main()
