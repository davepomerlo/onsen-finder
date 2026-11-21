"""Read water data from the 日本の温泉地 (onsen area) infobox of Japanese Wikipedia articles.

For every Wikidata item that links to a ja.wikipedia article, extracts 泉質 (spring type), 泉温 (source
temperature), 湧出量 (flow), pH, 液性の分類 (acidity class) and 浸透圧の分類 (tonicity), and saves them
to data/wikipedia.json keyed by Wikidata Q-number.
"""
import json
import os
import re
import sys

from common import DATA, http_get, load_json, save_json

API = 'https://ja.wikipedia.org/w/api.php'
TEMPLATE_NAMES = ('日本の温泉地', 'Infobox 温泉', '温泉地', 'Infobox 日本の温泉地')
FIELDS = {'泉質': 'ss', '泉温': 't', '湧出量': 'flow', 'pH': 'ph', 'ｐH': 'ph', '液性の分類': 'liq',
          '浸透圧の分類': 'osm', '宿泊施設数': 'inns'}


# ---------- wikitext parsing ----------
def find_template(text):
    """Return the inner text of the first onsen infobox template, or None."""
    for m in re.finditer(r'\{\{\s*([^|{}\n]+?)\s*[|\n]', text):
        name = m.group(1).strip().replace('_', ' ')
        if name not in TEMPLATE_NAMES:
            continue
        depth, i = 0, m.start()
        while i < len(text) - 1:
            two = text[i:i + 2]
            if two == '{{':
                depth += 1; i += 2; continue
            if two == '}}':
                depth -= 1; i += 2
                if depth == 0:
                    return text[m.start() + 2:i - 2]
                continue
            i += 1
    return None


def split_params(inner):
    """Split template text on top-level pipes; returns {name: value}."""
    parts, buf, depth_c, depth_s = [], [], 0, 0
    i = 0
    while i < len(inner):
        two = inner[i:i + 2]
        if two in ('{{', '[['):
            if two == '{{': depth_c += 1
            else: depth_s += 1
            buf.append(two); i += 2; continue
        if two in ('}}', ']]'):
            if two == '}}': depth_c -= 1
            else: depth_s -= 1
            buf.append(two); i += 2; continue
        if inner[i] == '|' and depth_c == 0 and depth_s == 0:
            parts.append(''.join(buf)); buf = []; i += 1; continue
        buf.append(inner[i]); i += 1
    parts.append(''.join(buf))
    out = {}
    for p in parts[1:]:
        if '=' in p:
            k, v = p.split('=', 1)
            out[k.strip()] = v.strip()
    return out


def clean(v):
    v = re.sub(r'<!--.*?-->', '', v, flags=re.S)
    v = re.sub(r'<ref[^>/]*/>', '', v)
    v = re.sub(r'<ref[^>]*>.*?</ref>', '', v, flags=re.S)
    v = re.sub(r'<br\s*/?>', ' / ', v, flags=re.I)
    v = re.sub(r'\[\[(?:[^|\]]*\|)?([^\]]*)\]\]', r'\1', v)
    v = re.sub(r'\[https?://\S+\s+([^\]]+)\]', r'\1', v)
    for _ in range(3):
        v = re.sub(r'\{\{(?:lang|Lang|nowrap|Nowrap|small|en|Ja)\|(?:[^|{}]*\|)?([^{}|]*)\}\}', r'\1', v)
        v = re.sub(r'\{\{[^{}]*\}\}', '', v)
    v = re.sub(r'<[^>]+>', '', v)
    v = re.sub(r"'''?", '', v)
    v = v.replace('&nbsp;', ' ')
    v = re.sub(r'\s*/\s*(/\s*)+', ' / ', v)
    v = re.sub(r'\s+', ' ', v).strip(' /・、')
    return v


TYPE_RULES = [
    ('cl', r'塩化物|食塩|強塩'),
    ('hc', r'炭酸水素塩|重曹|重炭酸'),
    ('so4', r'硫酸塩|芒硝|石膏|正苦味|明礬|ミョウバン'),
    ('co2', r'二酸化炭素|炭酸泉|炭酸ガス'),
    ('fe', r'鉄'),
    ('ac', r'(?<!弱)酸性(?!度)'),
    ('i', r'よう素|ヨウ素|沃素'),
    ('s2', r'硫黄|硫化水素'),
    ('rn', r'放射能|ラジウム|ラドン'),
]


def spring_types(text):
    found = [code for code, pat in TYPE_RULES if re.search(pat, text)]
    if re.search(r'単純温泉|単純泉|アルカリ性単純|弱アルカリ性単純', text) or (re.search(r'単純', text) and not found):
        found.insert(0, 's')
    return found


def flow_lpm(text):
    """Best-effort litres/minute from a 湧出量 string (None when unclear)."""
    t = text.replace(',', '').replace('，', '')
    m = re.search(r'(\d+(?:\.\d+)?)\s*(万)?\s*(?:L|ℓ|リットル)\s*/\s*(?:分|min)', t)
    if m:
        n = float(m.group(1)) * (10000 if m.group(2) else 1)
        return int(n)
    m = re.search(r'毎分\s*(?:約)?\s*(\d+(?:\.\d+)?)\s*(万)?\s*(?:L|ℓ|リットル)', t)
    if m:
        return int(float(m.group(1)) * (10000 if m.group(2) else 1))
    return None


def parse_infobox(wikitext):
    inner = find_template(wikitext or '')
    if inner is None:
        return None
    params = split_params(inner)
    rec = {}
    for k, v in params.items():
        key = FIELDS.get(k)
        if key and v:
            c = clean(v)
            if c:
                rec[key] = c[:160]
    if not rec:
        return None
    if 'ss' in rec:
        rec['types'] = spring_types(rec['ss'])
    if 'flow' in rec:
        f = flow_lpm(rec['flow'])
        if f:
            rec['lpm'] = f
    return rec


# ---------- fetching ----------
def fetch_pages(titles):
    params = {'action': 'query', 'prop': 'revisions', 'rvprop': 'content|ids', 'rvslots': 'main',
              'format': 'json', 'formatversion': '2', 'redirects': '1', 'titles': '|'.join(titles), 'maxlag': '5'}
    status, body = http_get(API, params=params)
    if status != 200:
        raise RuntimeError(f'HTTP {status}')
    data = json.loads(body)
    redirect = {}
    for r in data.get('query', {}).get('redirects', []) + data.get('query', {}).get('normalized', []):
        redirect[r['from']] = r['to']
    pages = {}
    for p in data.get('query', {}).get('pages', []):
        if p.get('missing') or not p.get('revisions'):
            continue
        rev = p['revisions'][0]
        pages[p['title']] = (rev.get('revid'), rev.get('slots', {}).get('main', {}).get('content', ''))
    return redirect, pages


def main():
    items = load_json('wikidata.json', []) or []
    old = load_json('wikipedia.json', {}) or {}
    todo = [(r['q'], r['jawiki']) for r in items if r.get('jawiki')]
    out, n_box = {}, 0
    for i in range(0, len(todo), 40):
        batch = todo[i:i + 40]
        try:
            redirect, pages = fetch_pages([t for _, t in batch])
        except Exception as e:  # keep previous data for this batch
            print('batch failed:', e, file=sys.stderr)
            for q, _ in batch:
                if str(q) in old:
                    out[str(q)] = old[str(q)]
            continue
        for q, title in batch:
            t = title
            for _ in range(3):
                t = redirect.get(t, t)
            if t not in pages:
                continue
            revid, text = pages[t]
            rec = parse_infobox(text)
            if rec:
                rec['title'] = t
                rec['rev'] = revid
                out[str(q)] = rec
                n_box += 1
    if old and len(out) < 0.8 * len(old):
        sys.exit(f'Refusing to overwrite: {len(out)} infoboxes vs {len(old)} before (partial fetch?)')
    save_json(os.path.join(DATA, 'wikipedia.json'), out)
    print(f'Wikipedia: {len(todo)} articles checked, {n_box} with an onsen infobox; '
          f'{sum(1 for r in out.values() if r.get("ph"))} with pH, {sum(1 for r in out.values() if r.get("types"))} with spring types.')


if __name__ == '__main__':
    main()
