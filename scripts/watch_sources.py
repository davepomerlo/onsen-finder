"""Watch the rating sources for updates and open a GitHub issue when something changes.

Awards are matched to onsen by hand (a 湯シュラン star belongs to one bath, not a whole town), so this script
does not edit the ratings itself. It records a fingerprint of each source in data/watch_state.json and, when a
source changes, opens an issue listing what is new so data/curated.py can be updated.
"""
import hashlib
import html
import json
import os
import re
import urllib.error
import urllib.request

from common import DATA, http_get, load_json, save_json

SOURCES = [
    # (key, label, url, mode)
    ('yuchelin_home', '湯シュラン (Yuchelin) official site', 'https://yuchelin.org/', 'text'),
    ('yuchelin_prtimes', '湯シュラン press releases (PR TIMES)', 'https://prtimes.jp/main/html/searchrlp/company_id/191740', 'titles'),
    ('hyakusen_40', 'にっぽんの温泉100選 40th edition page', 'https://www.kankokeizai.com/100sen_40/', 'exists'),
    ('jalan_2027', 'じゃらん人気温泉地ランキング2027', 'https://jrc.jalan.net/', 'keyword:温泉地ランキング2027'),
]
KEYWORDS = re.compile(r'湯シュラン|星|認定|温泉|ランキング|Yuchelin')
SIGNAL = re.compile(r'[一二三]ツ星|つ星|認定|アワード|Award|ランキング|100選|発表')


def page_text(raw):
    t = raw.decode('utf-8', 'replace')
    t = re.sub(r'(?is)<(script|style|noscript)[^>]*>.*?</\1>', ' ', t)
    t = re.sub(r'(?s)<[^>]+>', '\n', t)
    lines = [re.sub(r'\s+', ' ', html.unescape(x)).strip() for x in t.split('\n')]
    return [x for x in lines if len(x) >= 4]


def check(key, url, mode):
    status, raw = http_get(url, retries=2, timeout=60)
    if mode == 'exists':
        return {'fp': str(status), 'items': [f'HTTP {status}'] if status == 200 else []}
    lines = page_text(raw) if status == 200 else []
    if mode.startswith('keyword:'):
        kw = mode.split(':', 1)[1]
        hits = [x for x in lines if kw in x]
        return {'fp': hashlib.sha1('\n'.join(hits).encode()).hexdigest(), 'items': hits[:20]}
    if mode == 'titles':
        titles = [x for x in lines if '湯シュラン' in x or 'Yuchelin' in x]
        return {'fp': hashlib.sha1('\n'.join(sorted(set(titles))).encode()).hexdigest(), 'items': titles[:60]}
    rel = [x for x in lines if KEYWORDS.search(x)]
    return {'fp': hashlib.sha1('\n'.join(rel).encode()).hexdigest(), 'items': rel[:200]}


def open_issue(title, body):
    token, repo = os.environ.get('GITHUB_TOKEN'), os.environ.get('GITHUB_REPOSITORY')
    if not token or not repo:
        print('No GITHUB_TOKEN; issue not opened.\n' + title + '\n' + body)
        return
    try:  # don't pile up duplicates: skip if an open data-update issue already has this title
        q = urllib.request.Request(f'https://api.github.com/repos/{repo}/issues?state=open&labels=data-update&per_page=50',
                                   headers={'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github+json',
                                            'User-Agent': 'onsen-finder-bot'})
        with urllib.request.urlopen(q, timeout=30) as r:
            if any(i.get('title') == title for i in json.loads(r.read())):
                print('An open issue already covers this; not opening another.'); return
    except Exception as e:
        print('Could not list issues:', e)
    req = urllib.request.Request(f'https://api.github.com/repos/{repo}/issues', method='POST',
                                 data=json.dumps({'title': title, 'body': body, 'labels': ['data-update']}).encode(),
                                 headers={'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github+json',
                                          'User-Agent': 'onsen-finder-bot'})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            print('Opened issue:', json.loads(r.read())['html_url'])
    except urllib.error.HTTPError as e:  # retry without the label
        print('Issue with label failed:', e.code)
        req = urllib.request.Request(req.full_url, method='POST', headers=dict(req.header_items()),
                                     data=json.dumps({'title': title, 'body': body}).encode())
        with urllib.request.urlopen(req, timeout=30) as r:
            print('Opened issue:', json.loads(r.read())['html_url'])


def main():
    state = load_json('watch_state.json', {}) or {}
    changes = []
    for key, label, url, mode in SOURCES:
        try:
            res = check(key, url, mode)
        except Exception as e:
            print(f'{label}: could not check ({e})')
            continue
        prev = state.get(key)
        seen = list(dict.fromkeys((prev or {}).get('items', []) + res['items']))[-1000:]
        state[key] = {'fp': res['fp'], 'items': seen}
        if prev is None:
            print(f'{label}: first check recorded')
            continue
        if mode == 'exists':
            if res['items'] and prev['fp'] != res['fp']:
                changes.append((label, url, res['items'])); print(f'{label}: NOW PUBLISHED')
            else:
                print(f'{label}: not yet')
            continue
        # report only lines never seen before that look like results (stars, certification, awards, rankings)
        old = set(prev.get('items', []))
        new_items = [x for x in res['items'] if x not in old and SIGNAL.search(x)]
        if new_items:
            changes.append((label, url, new_items)); print(f'{label}: {len(new_items)} new line(s)')
        else:
            print(f'{label}: no relevant change')
    save_json(os.path.join(DATA, 'watch_state.json'), state)
    if changes:
        body = ['The weekly check found updates on these rating sources. Review them and update `data/curated.py` '
                '(the `YUCHELIN`, `HYAKUSEN` or `JALAN` lists, plus water notes for any new onsen), then run the workflow again.\n']
        for label, url, items in changes:
            body.append(f'### {label}\n{url}\n')
            body.extend(f'- {html.escape(x)[:200]}' for x in items[:25])
            body.append('')
        open_issue('Rating sources updated: ' + ', '.join(c[0] for c in changes), '\n'.join(body))


if __name__ == '__main__':
    main()
