# Travel Planner Assistant V2

MIT 授權、Python 3.10+、離線優先的可查證旅遊規劃核心；只搜尋，不訂位或付款。

## 安裝與 Quickstart

```sh
uv sync --python 3.12
uv run python -m unittest discover -s tests -v
uv run travel-assistant trip create examples/v2-input.json --database output/trips.db
uv run travel-assistant trip plan osaka-v2 --database output/trips.db --output-dir output/osaka-v2
```

產生 SQLite revisions 與 `plan.json`、`plan.md`、`plan.ics`、`plan.geojson`、`plan.kml`。V1 指令仍可用：

```sh
uv run travel-assistant plan examples/input.json --output-dir output/legacy --flight-provider mock
```

## V2 功能

- 多航段、住宿、預約、分類費用、checklist、來源快照。
- Opening windows、fixed／locked 項目、buffer、priority、移動時間與機器可讀衝突。
- SQLite append-only revisions；V1 JSON deterministic migration。
- Duffel 多 slice、Skyscanner gated create/poll、Google Flights 查詢連結、`fli` 實驗邊界預設拒絕。
- OSRM／Overpass bounded clients；失效時排程可用 haversine 降級。
- JSON、Markdown、ICS、GeoJSON、KML。

CLI：

```sh
travel-assistant trip create INPUT --database DB [--trip-id ID]
travel-assistant trip plan ID --database DB --output-dir DIR
travel-assistant trip replan ID --database DB --output-dir DIR
travel-assistant trip explain ID --database DB
travel-assistant trip export ID --database DB --format ics --output trip.ics
travel-assistant flight search REQUEST --provider mock|duffel|skyscanner|google-link
```

## Provider

| Provider | 行為 |
|---|---|
| `mock` | 完全離線；只回查詢形狀，不捏造價格 |
| `duffel` | 讀 `DUFFEL_ACCESS_TOKEN`，官方 Offer Request，多 slice；只搜尋、不下單 |
| `skyscanner` | 需 Partnerships 核准、`SKYSCANNER_API_KEY` 與明確 `--enable-skyscanner` |
| `google-link` | 只產生 Google Flights 查詢連結，不宣稱即時結果 |
| `fli-experimental` | 預設硬拒絕；只保留 injected adapter 邊界，不內建逆向 live call |

## 輸入與限制

V2 schema 嚴格拒絕未知欄位與懸空 place/source reference。Verified source 必須有 URL；估算與不可用資料必須帶狀態。排程不移動 locked 項目；無解時輸出 conflict，不靜默刪除。航班價格、班次、開放時間仍需重查；本工具不代訂、不付款。

完整研究依據見 [V1 research](docs/RESEARCH.md)；[V2 能力調研](docs/V2-RESEARCH.md) 與 [V2 工程計劃](docs/V2-PLAN.md) 涵蓋 TREK 差距、輪子選型、安全界線與驗收。Hermes 操作規則見 [Skill](skills/travel-planner-assistant/SKILL.md)。

## Hermes Skill

將 repo 的 `skills/` 註冊到 Hermes `skills.external_dirs`；會保留既有目錄：

```sh
python3 scripts/install_hermes_skill.py
```

安裝器會建立 `.venv`、安裝鎖定相依並註冊 Skill。安裝後可直接對 Hermes 說：「幫我規劃 10 月從台北到大阪的四天自由行，兩人、預算 4 萬、喜歡美食與歷史。」Hermes 會蒐集必要資訊、保存來源、建立 revision、規劃並輸出五種格式。
