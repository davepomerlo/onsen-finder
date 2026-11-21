"""Build the site data (docs/onsen.json, docs/prefs.json, docs/japan.json) from data/.

Inputs
  data/wikidata.json   onsen items from Wikidata (fetch_wikidata.py)
  data/wikipedia.json  infobox water data from Japanese Wikipedia (fetch_wikipedia.py)
  data/curated.py      hand-compiled water data and awards for major onsen areas
  data/romaji.txt      English readings for items without an English label
  data/japan.topojson  prefecture boundaries (dataofjapan/land, from GSI Global Map Japan)
"""
import importlib.util
import json
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from common import DATA, DOCS, load_json, save_json_lines  # noqa: E402

spec = importlib.util.spec_from_file_location('curated', os.path.join(DATA, 'curated.py'))
cur_mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(cur_mod)
C, YUCHELIN, HYAKUSEN, JALAN, SANMEISEN = cur_mod.C, cur_mod.YUCHELIN, cur_mod.HYAKUSEN, cur_mod.JALAN, cur_mod.SANMEISEN

CLASS_TYPE = {11408869: 's', 11428612: 'cl', 11587679: 's2', 11567142: 'hc', 11587674: 'so4', 11498934: 'rn',
              3046709: 'fe', 11371830: 'co2', 11644442: 'ac', 11416420: 'so4'}
CLASS_FLAG = {11562971: 'kyo', 11645813: 'wild', 83471: 'geyser', 10856214: 'roten'}


def region(pid):
    if pid == 1: return 'hokkaido'
    if pid <= 7: return 'tohoku'
    if pid <= 14: return 'kanto'
    if pid <= 23: return 'chubu'
    if pid <= 30: return 'kinki'
    if pid <= 35: return 'chugoku'
    if pid <= 39: return 'shikoku'
    return 'kyushu'


# ---------- prefectures from TopoJSON ----------
topo = json.load(open(os.path.join(DATA, 'japan.topojson'), encoding='utf-8'))
sx, sy = topo['transform']['scale']; tx, ty = topo['transform']['translate']
ARCS = []
for a in topo['arcs']:
    x = y = 0; pts = []
    for dx, dy in a:
        x += dx; y += dy; pts.append((x * sx + tx, y * sy + ty))
    ARCS.append(pts)


def ring_from(idx, arcs):
    out = []
    for i in idx:
        pts = arcs[i] if i >= 0 else arcs[~i][::-1]
        out.extend(pts if not out else pts[1:])
    return out


PREFS = []
for g in topo['objects']['japan']['geometries']:
    p = g['properties']
    polys = g['arcs'] if g['type'] == 'MultiPolygon' else [g['arcs']]
    rings = []
    for poly in polys:
        r = ring_from(poly[0], ARCS)
        xs = [c[0] for c in r]; ys = [c[1] for c in r]
        rings.append((min(xs), min(ys), max(xs), max(ys), r))
    en = re.sub(r' (Ken|Fu|To)$', '', p['nam']).replace('Hokkai Do', 'Hokkaido')
    PREFS.append(dict(id=p['id'], ja=p['nam_ja'], en=en, rings=rings, geom=g))
PNAME = {p['id']: (p['ja'], p['en']) for p in PREFS}


def pip(x, y, ring):
    inside = False; j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]; xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi + 1e-15) + xi:
            inside = not inside
        j = i
    return inside


def find_pref(lat, lon):
    for p in PREFS:
        for (a, b, c, d, ring) in p['rings']:
            if a <= lon <= c and b <= lat <= d and pip(lon, lat, ring):
                return p['id']
    best, bid = 1e9, None
    for p in PREFS:
        for (a, b, c, d, ring) in p['rings']:
            if lon < a - .5 or lon > c + .5 or lat < b - .5 or lat > d + .5: continue
            for (x, y) in ring:
                dd = (x - lon) ** 2 + (y - lat) ** 2
                if dd < best: best, bid = dd, p['id']
    return bid


def simplified_map(eps=0.008, min_area=0.0015):
    def dp(pts):
        if len(pts) < 3: return pts
        a, b = pts[0], pts[-1]; dx, dy = b[0] - a[0], b[1] - a[1]; L = math.hypot(dx, dy) or 1e-12
        md, mi = -1, 0
        for i in range(1, len(pts) - 1):
            q = pts[i]
            d = abs(dy * (q[0] - a[0]) - dx * (q[1] - a[1])) / L if (dx or dy) else math.hypot(q[0] - a[0], q[1] - a[1])
            if d > md: md, mi = d, i
        return dp(pts[:mi + 1])[:-1] + dp(pts[mi:]) if md > eps else [a, b]
    sarcs = [dp(a) for a in ARCS]
    def area(r): return abs(sum(r[i][0] * r[i - 1][1] - r[i - 1][0] * r[i][1] for i in range(len(r)))) / 2
    feats = []
    for p in PREFS:
        g = p['geom']; polys = g['arcs'] if g['type'] == 'MultiPolygon' else [g['arcs']]
        mp = []
        for poly in polys:
            rings = [ring_from(r, sarcs) for r in poly]
            if area(rings[0]) < min_area: continue
            mp.append([[[round(x, 3), round(y, 3)] for x, y in r] for r in rings if len(r) >= 4])
        feats.append({'type': 'Feature', 'properties': {'id': p['id']}, 'geometry': {'type': 'MultiPolygon', 'coordinates': mp}})
    return {'type': 'FeatureCollection', 'features': feats}


# ---------- names ----------
ROMA = {}
for line in open(os.path.join(DATA, 'romaji.txt'), encoding='utf-8'):
    if '|' in line:
        a, b = line.rstrip('\n').split('|', 1); ROMA[a] = b


def clean_disambig(s):
    return re.sub(r'\s*[（(][^）)]*[）)]\s*$', '', s).strip()


EN_FIX = {'Tamagwa Onsen': 'Tamagawa Onsen'}


def english(ja, base, raw_en):
    if raw_en:
        en0 = clean_disambig(raw_en)
        en = re.sub(r'\s*Hot[ -]?[Ss]pa$|\s*[Hh]ot [Ss]prings?$|\s*[Oo]nsen$|\s*Spa$', '', en0).strip() or en0
        if en != en0: en += ' Onsen'
        return EN_FIX.get(en, en)
    if ja in ROMA:
        return ROMA[ja] + (' Onsen-kyō' if ja.endswith('温泉郷') else '')
    if ja.endswith('温泉') and base in ROMA:
        return ROMA[base] + ' Onsen'
    if base in ROMA:
        return ROMA[base]
    return None


FACILITY_RE = re.compile(r'道の駅|ホテル|旅館|センター|ランド|館|万華郷|ラクーア|リゾート|うるり|山王閣|山下家|四季亭|滔々庵|の湯$|BOX|リブマックス|チャレンジャー|シエスパ|アロマ')


def main():
    wd = load_json('wikidata.json', [])
    wk = load_json('wikipedia.json', {}) or {}
    out, missing_en = [], []
    for r in wd:
        ja = clean_disambig(r['ja'])
        base = re.sub(r'温泉$', '', ja)
        en = english(ja, base, r.get('en', ''))
        if not en:
            missing_en.append(ja); en = ''
        types = {CLASS_TYPE[c] for c in r.get('classes', []) if c in CLASS_TYPE}
        flags = {CLASS_FLAG[c] for c in r.get('classes', []) if c in CLASS_FLAG}
        kind = 'area'
        if FACILITY_RE.search(ja): kind = 'facility'
        if ('地獄' in ja and 33.2 < r['lat'] < 33.4 and r['lon'] > 131.4) or 'geyser' in flags or '間歇' in ja: kind = 'sight'
        o = dict(q=r['q'], ja=ja, base=base, en=en, lat=r['lat'], lon=r['lon'], pref=find_pref(r['lat'], r['lon']),
                 types=types, flags=flags, kind=kind)
        w = wk.get(str(r['q']))
        if w:
            o['wk'] = {k: w[k] for k in ('ph', 't', 'flow', 'lpm', 'ss', 'liq', 'osm', 'title') if w.get(k)}
            o['types'] |= set(w.get('types', []))
        out.append(o)

    # de-duplicate near-identical items (same name within ~1 km)
    seen, ded = {}, []
    for o in out:
        key = (o['base'], round(o['lat'], 2), round(o['lon'], 2))
        if key in seen:
            prev = seen[key]; prev['types'] |= o['types']
            if not prev['en'] and o['en']: prev['en'] = o['en']
            if 'wk' in o and 'wk' not in prev: prev['wk'] = o['wk']
            continue
        seen[key] = o; ded.append(o)
    out = ded
    byq = {o['q']: o for o in out}

    # curated layer
    for c in C:
        if 'new' in c:
            n = c['new']
            o = dict(q=None, ja=n['ja'], base=re.sub('温泉$', '', n['ja']), en=n['en'], lat=n['lat'], lon=n['lon'],
                     pref=find_pref(n['lat'], n['lon']), types=set(), flags=set(), kind=n.get('kind', 'area'))
            out.append(o)
        else:
            o = byq.get(c['q'])
            if o is None:
                print('warning: curated item not on Wikidata any more:', c['q'], c['ja'][:12]); continue
        if c.get('name_en'): o['en'] = c['name_en']
        o['types'] |= set(c['types'].split())
        o['flags'] |= set(c.get('flags', '').split())
        o['cur'] = dict(ph=c.get('ph'), t=c.get('temp'), flow=c.get('flow'), sup=c.get('supply'), self=c.get('self', False),
                        color=c.get('color'), dja=c['ja'], den=c['en'], baths=split_baths(c.get('baths', '')))
        key = c['q'] if 'q' in c else c['new']['ja']
        if key in YUCHELIN: o['yu3'] = 1
        if key in SANMEISEN: o['sanmei'] = 1
    for q, rk in HYAKUSEN.items():
        if q in byq: byq[q]['h100'] = rk
    for k, d in JALAN.items():
        for q, rk in d.items():
            if q in byq: byq[q].setdefault('jalan', {})[k] = rk

    for o in out:
        pj = PNAME[o['pref']][0] if o['pref'] else ''
        if o['base'] in HOYOU.get(pj, '').split() or o['ja'] in HOYOU.get(pj, '').split():
            o['hoyou'] = 1
        o['sc'], o['scw'], o['scr'] = score(o)

    data = [compact(o) for o in sorted(out, key=lambda o: (-o['sc'], o['ja']))]
    save_json_lines(os.path.join(DOCS, 'onsen.json'), data)
    with open(os.path.join(DOCS, 'prefs.json'), 'w', encoding='utf-8') as f:
        json.dump([dict(id=i, ja=PNAME[i][0], en=PNAME[i][1], r=region(i)) for i in sorted(PNAME)], f, ensure_ascii=False)
    with open(os.path.join(DOCS, 'japan.json'), 'w', encoding='utf-8') as f:
        json.dump(simplified_map(), f, separators=(',', ':'))
    with open(os.path.join(DOCS, 'meta.json'), 'w', encoding='utf-8') as f:
        json.dump({'count': len(data), 'curated': sum(1 for d in data if 'cur' in d),
                   'wikipedia': sum(1 for d in data if 'wk' in d)}, f)
    print(f'Built {len(data)} onsen: {sum(1 for d in data if "cur" in d)} curated, '
          f'{sum(1 for d in data if "wk" in d)} with Wikipedia water data.')
    if missing_en:
        print(f'{len(missing_en)} names have no English reading yet (add them to data/romaji.txt):', ', '.join(missing_en[:30]))


def split_baths(s):
    segs = []
    for part in s.split(';'):
        if not part: continue
        if '|' in part or not segs: segs.append(part)
        else: segs[-1] += '、' + part.strip()
    return [x.split('|') for x in segs]


HOYOU = {
 "北海道": "カルルス ニセコ ニセコ湯本 ニセコ昆布 ニセコ薬師 ニセコ新見 ニセコ五色 五色 芦別 ながぬま 豊富",
 "青森県": "酸ヶ湯", "岩手県": "金田一 八幡平温泉郷 藤七", "秋田県": "八幡平温泉郷 後生掛 蒸ノ湯 大深 田沢湖高原 田沢湖高原温泉郷 秋ノ宮温泉郷",
 "宮城県": "鳴子 東鳴子 川渡 中山平 鬼首", "山形県": "蔵王 銀山 碁点 肘折 湯田川 湯野浜 あつみ 由良",
 "福島県": "岳 新甲子 土湯 高湯 二岐 岩瀬湯本 天栄", "栃木県": "日光湯元 板室",
 "群馬県": "四万 鹿沢 新鹿沢 上牧 奈女沢 湯宿 川古 猿ヶ京 法師", "神奈川県": "芦之湯",
 "新潟県": "岩室 六日町 関 燕 五頭温泉郷 出湯 村杉", "石川県": "白山 中宮 岩間 新岩間 白山一里野",
 "山梨県": "下部 増富", "長野県": "鹿教湯 霊泉寺 大塩 田沢 沓掛 小谷 白骨 美ヶ原",
 "岐阜県": "奥飛騨温泉郷 平湯 新平湯 福地 栃尾 新穂高 白川郷平瀬 小坂温泉郷 濁河", "静岡県": "畑毛 梅ヶ島 梅ヶ島コンヤ",
 "京都府": "るり渓", "兵庫県": "浜坂温泉郷 浜坂 七釜", "奈良県": "十津川 湯泉地 上湯",
 "和歌山県": "湯の峰 川湯 渡瀬 龍神", "鳥取県": "鹿野 吉岡 関金 岩井", "島根県": "三瓶 鷺ノ湯",
 "岡山県": "湯原 奥津 湯郷", "広島県": "湯来 湯の山 矢野", "山口県": "俵山 三丘", "香川県": "塩江",
 "愛媛県": "湯ノ浦", "福岡県": "筑後川 吉井", "長崎県": "壱岐湯ノ本",
 "熊本県": "下田 黒川 田の原 わいた温泉郷 湯の児 湯の鶴", "大分県": "長湯 竹田 由布院 湯平 塚原 鉄輪 明礬 柴石",
 "鹿児島県": "霧島温泉郷 丸尾 栄之尾 新川渓谷温泉郷 日当山 妙見 安楽",
}

RARE = {'ac': .04, 's2': .03, 'co2': .04, 'rn': .03, 'fe': .02, 'i': .03}


def nums(s):
    return [float(x) for x in re.findall(r'\d+(?:\.\d+)?', s or '')]


def score(o):
    """湯スコア: 3.00 base; water & freshness first, then a recognition bonus. Capped at 4.80."""
    w = min(sum(RARE.get(t, 0) for t in o['types']) + (.02 if o['types'] else 0), .10)
    c = o.get('cur')
    if c:
        w += {'K': .30, 'M': .12, 'C': 0}.get(c['sup'], 0)
        if c['self']: w += .08
        ch = 0
        ph = [x for x in nums(c['ph']) if x <= 14]
        if ph and (min(ph) < 3 or max(ph) >= 9.5): ch += .08
        if (c.get('flow') or 0) >= 5000: ch += .08
        if 'ashimoto' in o['flags']: ch += .06
        if 'tank' in o['flags']: ch += .06
        w += min(ch, .16) + .04
    elif o.get('wk'):
        k = o['wk']; w += .03
        ph = [x for x in nums(k.get('ph')) if x <= 14]
        if ph and (min(ph) < 3 or max(ph) >= 9.5): w += .05
        if (k.get('lpm') or 0) >= 5000: w += .05
    rcg = 0.0
    if o.get('yu3'): rcg += .35
    if o.get('h100'): rcg += .25 - .01 * (o['h100'] - 1)
    jb = sum({'satisfaction': .10, 'hidden': .08, 'hidden_sat': .08, 'revisit': .06, 'dream': .05}[k] * (1 - (rk - 1) * .05)
             for k, rk in o.get('jalan', {}).items())
    rcg += min(jb, .18)
    if o.get('sanmei'): rcg += .05
    if o.get('hoyou'): rcg += .05
    return round(min(3.0 + w + rcg, 4.8), 2), round(3.0 + w, 2), round(rcg, 2)


def compact(o):
    d = dict(id=o['q'] or ('x' + o['base']), ja=o['ja'], en=o['en'] or '', la=round(o['lat'], 3), lo=round(o['lon'], 3),
             p=o['pref'], ty=sorted(o['types']), fl=sorted(o['flags']), k=o['kind'], sc=o['sc'], sw=o['scw'], sr=o['scr'])
    for k in ('yu3', 'h100', 'jalan', 'sanmei', 'hoyou', 'cur', 'wk'):
        if o.get(k): d[k] = o[k]
    return d


if __name__ == '__main__':
    main()
