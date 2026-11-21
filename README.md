# ♨ Onsen Finder 温泉ファインダー

A bilingual (English / 日本語) map of Japan's hot springs with water-quality data and a Tabelog-style rating.

**Live site:** https://davepomerlo.github.io/onsen-finder/ (served from `docs/` by GitHub Pages)

- ~1,460 onsen areas, facilities and hot-spring sights, filterable by region, prefecture, spring type (泉質),
  supply method (源泉かけ流し / 循環ろ過), bath features and awards
- Hand-compiled water data for 115 major areas: spring types, pH, source temperature, flow, colour,
  natural flow (自然湧出), typical handling (加水・加温・循環・消毒) and notable baths
- Water data for hundreds more from the 日本の温泉地 infobox of Japanese Wikipedia, refreshed weekly
- **湯スコア (Yu-score)**: a 5-point score that starts at 3.00 and rewards fresh, distinctive water first,
  then awards (湯シュラン stars, にっぽんの温泉100選, じゃらん rankings, 日本三名泉, 国民保養温泉地).
  The formula is in `scripts/build.py` (`score()`) and explained in the app's **?** panel.

## How the data updates

`.github/workflows/update.yml` runs every Monday at 03:17 JST, on demand (Actions → *Weekly data update* →
*Run workflow*), and whenever `data/curated.py`, `data/romaji.txt` or `scripts/` change on `main`.

| Step | Script | Output |
|---|---|---|
| Onsen list, coordinates, spring-type classes, ja.wikipedia titles | `scripts/fetch_wikidata.py` | `data/wikidata.json` |
| 泉質 / 泉温 / 湧出量 / pH / 液性 from article infoboxes | `scripts/fetch_wikipedia.py` | `data/wikipedia.json` |
| Geocode addresses of hand-added onsen (国土地理院 address search) | `scripts/geocode.py` | `data/geocode.json` |
| Merge with curated data, assign prefectures, score | `scripts/build.py` | `docs/onsen.json`, `docs/prefs.json`, `docs/japan.json` |
| Watch 湯シュラン, 100選 and じゃらん for new results | `scripts/watch_sources.py` | opens a GitHub issue when a source changes |

Awards are matched to onsen by hand, because a 湯シュラン star belongs to one bath, not a whole town. When the
watcher opens an issue, add the new entries to `YUCHELIN`, `HYAKUSEN` or `JALAN` in `data/curated.py` and
push; the workflow rebuilds the site.

Each fetch step refuses to overwrite good data with a suspiciously small result, so a temporary outage
leaves last week's data in place.

## Editing

- **Water data and awards:** `data/curated.py` (each entry is keyed by its Wikidata Q-number)
- **Hidden gems (秘湯・野湯):** the `H` list in `data/curated.py`. For a place that isn't on Wikidata, give
  `new=dict(ja=…, en=…, addr='住所', lat=…, lon=…)`; the workflow geocodes the address, and `lat`/`lon` are a
  fallback. List who recommends it in `src` (keys of `SRC`), so the app can link to them.
- **English readings** for places with no English label: `data/romaji.txt` (`日本語名|Romaji`; the build
  log lists names still missing one)
- **The app:** `docs/index.html` (single file; D3 from cdnjs)

Run locally (Python 3.10+, no packages needed):

```sh
python tests/test_parsers.py
python scripts/fetch_wikidata.py && python scripts/fetch_wikipedia.py   # needs internet
python scripts/build.py
cd docs && python -m http.server   # open http://localhost:8000
```

## Sources and licences

- [Wikidata](https://www.wikidata.org/) — onsen items and coordinates (CC0)
- [Japanese Wikipedia](https://ja.wikipedia.org/) — infobox water data in `data/wikipedia.json` (CC BY-SA 4.0)
- [湯シュラン (Yuchelin)](https://yuchelin.org/) — 湯シュランアワード2026, 21 three-star facilities (26 Oct 2026)
- 観光経済新聞社 — 第39回 にっぽんの温泉100選 (top 20)
- じゃらんリサーチセンター — じゃらん人気温泉地ランキング2026
- 環境省 — 国民保養温泉地 (79 designated areas)
- Hidden-gem picks: BE-PAL (秘湯探検家 渡辺裕美), ニフティ温泉 (survey of 2,300 bathers), Tofugu, GOOD LUCK TRIP,
  Atlas Obscura, The Japan Times, LINE TODAY Taiwan, ゆるーと, Visit Hokkaido, 観光庁 多言語解説, YouTube — linked per onsen
- [国土地理院 address search](https://msearch.gsi.go.jp/) — coordinates for hand-added onsen
- [dataofjapan/land](https://github.com/dataofjapan/land) — prefecture boundaries from GSI Global Map Japan (地球地図日本)

Water figures are representative values for each area. Since 2005 every bath in Japan must post whether its
water is diluted (加水), heated (加温), recirculated (循環) or treated (入浴剤・消毒); check that notice (掲示) on site.
