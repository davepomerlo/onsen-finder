"""Offline tests for the Wikipedia infobox parser. Run: python tests/test_parsers.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
from fetch_wikipedia import parse_infobox, spring_types, flow_lpm  # noqa: E402

KUSATSU = """{{日本の温泉地
|名称 = 草津温泉
|画像 = Yubatake (Kusatsu Onsen).jpg
|所在地 = [[群馬県]][[吾妻郡]][[草津町]]
|座標 = {{Coord| display=inline,title }}
|泉質 = [[酸性泉]]<br/>[[硫黄泉]]<br/>[[アルミニウム]]
|泉温 = 温度44.9度（西の河原）〜94.5度（万代）
|湧出量 = 約32,300 [[リットル|L]]/分以上<br/>（最大時36,000 L/分超）
|pH = 1.0〜2.2
|液性の分類 = [[酸性]]
|浸透圧の分類 = 低張性
|宿泊施設数 = 171
|特記事項 =
}}
'''草津温泉'''（くさつおんせん）は…"""


def test_kusatsu():
    r = parse_infobox(KUSATSU)
    assert r['ss'] == '酸性泉 / 硫黄泉 / アルミニウム', r['ss']
    assert r['types'] == ['ac', 's2'], r['types']
    assert r['ph'] == '1.0〜2.2'
    assert r['lpm'] == 32300, r.get('lpm')
    assert r['liq'] == '酸性' and r['osm'] == '低張性'
    assert r['t'].startswith('温度44.9度')


def test_types():
    assert spring_types('アルカリ性単純温泉') == ['s']
    assert spring_types('単純硫黄泉') == ['s2']
    assert spring_types('ナトリウム-塩化物・炭酸水素塩泉') == ['cl', 'hc']
    assert spring_types('含二酸化炭素-鉄(II)-硫酸塩泉') == ['so4', 'co2', 'fe']
    assert spring_types('弱酸性の単純温泉') == ['s']
    assert spring_types('単純弱放射能冷鉱泉') == ['rn']


def test_flow():
    assert flow_lpm('毎分約9,000リットル') == 9000
    assert flow_lpm('1.5万L/分') == 15000
    assert flow_lpm('自噴') is None


def test_no_box():
    assert parse_infobox("'''何か'''の記事") is None


if __name__ == '__main__':
    for name, fn in list(globals().items()):
        if name.startswith('test_'):
            fn(); print('ok', name)
