"""Refresh data/wikidata.json: every onsen / hot-spring item in Japan with coordinates and a Japanese label.

Also records each item's instance-of classes (Wikidata encodes many spring types this way) and the title of
its Japanese Wikipedia article, which fetch_wikipedia.py reads for water data.
"""
import json
import os
import sys

from common import DATA, http_get, load_json, save_json_lines

ENDPOINT = 'https://query.wikidata.org/sparql'
QUERY = """
SELECT ?i (SAMPLE(?jl) AS ?ja) (SAMPLE(?el) AS ?en) (SAMPLE(?lat0) AS ?lat) (SAMPLE(?lon0) AS ?lon)
       (GROUP_CONCAT(DISTINCT STRAFTER(STR(?c), "/entity/Q"); separator=",") AS ?classes)
       (SAMPLE(?wt) AS ?jawiki)
WHERE {
  ?i wdt:P31/wdt:P279* wd:Q177380 ;
     wdt:P17 wd:Q17 ;
     p:P625/psv:P625 [ wikibase:geoLatitude ?lat0 ; wikibase:geoLongitude ?lon0 ] .
  ?i rdfs:label ?jl . FILTER(LANG(?jl) = "ja")
  OPTIONAL { ?i rdfs:label ?el . FILTER(LANG(?el) = "en") }
  OPTIONAL { ?i wdt:P31 ?c }
  OPTIONAL { ?art schema:about ?i ; schema:isPartOf <https://ja.wikipedia.org/> ; schema:name ?wt }
}
GROUP BY ?i
"""


def main():
    status, body = http_get(ENDPOINT, data={'query': QUERY, 'format': 'json'},
                            headers={'Accept': 'application/sparql-results+json'}, timeout=180)
    if status != 200:
        sys.exit(f'Wikidata query failed: HTTP {status}')
    rows = []
    for b in json.loads(body)['results']['bindings']:
        try:
            q = int(b['i']['value'].rsplit('Q', 1)[1])
            lat = round(float(b['lat']['value']), 4)
            lon = round(float(b['lon']['value']), 4)
        except (KeyError, ValueError):
            continue
        if not (20 <= lat <= 46.5 and 122 <= lon <= 154):
            continue
        classes = sorted({int(x) for x in b.get('classes', {}).get('value', '').split(',') if x.isdigit()})
        rows.append(dict(q=q, ja=b['ja']['value'], en=b.get('en', {}).get('value', ''), lat=lat, lon=lon,
                         classes=classes, jawiki=b.get('jawiki', {}).get('value')))
    rows.sort(key=lambda r: r['q'])

    old = load_json('wikidata.json', []) or []
    if old and len(rows) < 0.85 * len(old):
        sys.exit(f'Refusing to overwrite: got {len(rows)} items, previously {len(old)} (partial result?)')
    old_q = {r['q'] for r in old}
    new = [r['ja'] for r in rows if r['q'] not in old_q]
    save_json_lines(os.path.join(DATA, 'wikidata.json'), rows)
    print(f'Wikidata: {len(rows)} onsen items ({len(new)} new). '
          f'{sum(1 for r in rows if r["jawiki"])} have a Japanese Wikipedia article.')
    if new:
        print('New:', ', '.join(new[:40]) + (' …' if len(new) > 40 else ''))


if __name__ == '__main__':
    main()
