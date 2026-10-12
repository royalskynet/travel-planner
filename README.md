# Travel Planner Assistant V2

MIT 授權、Python 3.10+、離線優先的可查證旅遊規劃核心；只搜尋，不訂位或付款。

MIT-licensed, offline-first, source-verifiable trip planning core for personal or group travel. It searches and plans — it never books and never takes payments.

**Language / 語言**：[English](#english) · [繁體中文](#繁體中文)

---

## English

### Quick install

One line, straight from GitHub. You need Python 3.10+ and [uv](https://docs.astral.sh/uv/):

```sh
git clone https://github.com/royalskynet/travel-planner && cd travel-planner && uv sync --python 3.12
```

That creates `.venv/`, installs the dependencies locked in `uv.lock`, and puts the `travel-assistant` CLI on the path, so `uv run travel-assistant --help` works right away. No credentials are needed: the default `mock` flight provider is completely offline. Prefer plain pip? `python3 -m venv .venv && .venv/bin/pip install -e .` installs the same CLI.

### Run the bundled example

```sh
uv run python -m unittest discover -s tests -v
uv run travel-assistant trip create examples/v2-input.json --database output/trips.db
uv run travel-assistant trip plan osaka-v2 --database output/trips.db --output-dir output/osaka-v2
```

Planning writes append-only SQLite revisions plus `plan.json`, `plan.md`, `plan.ics`, `plan.geojson` and `plan.kml` into the output directory. The V1 command is still supported:

```sh
uv run travel-assistant plan examples/input.json --output-dir output/legacy --flight-provider mock
```

### What V2 does

- Multiple flight segments, lodging, reservations, categorized costs, checklists, source snapshots.
- Opening windows, fixed and locked items, buffers, priority, travel time, machine-readable conflicts.
- Append-only SQLite revisions; deterministic migration of V1 JSON.
- Duffel multi-slice, gated Skyscanner create/poll, Google Flights query links, `fli` experimental boundary refused by default.
- Bounded OSRM and Overpass clients; scheduling falls back to haversine estimates when they fail.
- JSON, Markdown, ICS, GeoJSON and KML output.

CLI:

```sh
travel-assistant trip create INPUT --database DB [--trip-id ID]
travel-assistant trip plan ID --database DB --output-dir DIR
travel-assistant trip replan ID --database DB --output-dir DIR
travel-assistant trip explain ID --database DB
travel-assistant trip export ID --database DB --format ics --output trip.ics
travel-assistant flight search REQUEST --provider mock|duffel|skyscanner|google-link|fli-experimental
```

`trip export --format` accepts `json`, `markdown`, `ics`, `geojson` or `kml`.

### Flight providers

| Provider | Behaviour |
|---|---|
| `mock` | Fully offline; returns query shapes only, never invents prices |
| `duffel` | Reads `DUFFEL_ACCESS_TOKEN`, uses official Offer Requests, multi-slice; searches only, never orders |
| `skyscanner` | Requires Partnerships approval, `SKYSCANNER_API_KEY` and an explicit `--enable-skyscanner` |
| `google-link` | Builds a Google Flights query link only, and never claims live results |
| `fli-experimental` | Hard-refused by default; only the injected adapter boundary is kept, no built-in reverse-engineered live calls |

### Input schema and limits

The V2 schema strictly rejects unknown fields and dangling place or source references. A verified source must carry a URL; estimated and unavailable data must carry a status. Scheduling never moves locked items; when no solution exists it emits a conflict instead of silently dropping anything. Flight prices, schedules and opening hours still have to be re-checked — this tool never books and never pays.

### Hermes Skill

Register the repository's `skills/` directory with Hermes `skills.external_dirs`; existing directories are preserved:

```sh
python3 scripts/install_hermes_skill.py
```

The installer creates `.venv/`, installs the locked dependencies and registers the skill. Once installed you can ask Hermes directly: "Plan a four-day free trip from Taipei to Osaka in October for two people, budget 40,000, we like food and history." Hermes collects the missing details, stores sources, creates a revision, plans, and emits all five formats.

### Documentation

- [V1 research](docs/RESEARCH.md) — the sources behind the first design.
- [V2 capability research](docs/V2-RESEARCH.md) and [V2 engineering plan](docs/V2-PLAN.md) — TREK gap analysis, wheel selection, safety boundaries and acceptance.
- [Hermes skill](skills/travel-planner-assistant/SKILL.md) — the operating rules for the agent.

### Boundaries

- Search and plan only: no hotel availability lookups, no restaurant or ticket bookings, no payments.
- API keys are read from environment variables only, and must never be written into JSON, Markdown, logs or Git. Copy `.env.example` to get started.
- Offline-first: every third-party service is isolated behind an adapter with bounded timeouts and response sizes.

---

## 繁體中文

### 快速安裝

一行指令，直接從 GitHub 取用。需要 Python 3.10+ 與 [uv](https://docs.astral.sh/uv/)：

```sh
git clone https://github.com/royalskynet/travel-planner && cd travel-planner && uv sync --python 3.12
```

這會建立 `.venv/`、安裝 `uv.lock` 鎖定的相依套件，並把 `travel-assistant` CLI 放進執行路徑，馬上就能 `uv run travel-assistant --help`。不需要任何憑證：預設的 `mock` provider 完全離線。想用純 pip 也可以：`python3 -m venv .venv && .venv/bin/pip install -e .` 會裝出同樣的 CLI。

### 跑內建範例

```sh
uv run python -m unittest discover -s tests -v
uv run travel-assistant trip create examples/v2-input.json --database output/trips.db
uv run travel-assistant trip plan osaka-v2 --database output/trips.db --output-dir output/osaka-v2
```

規劃會寫入 append-only 的 SQLite revisions，並在輸出目錄產生 `plan.json`、`plan.md`、`plan.ics`、`plan.geojson`、`plan.kml`。V1 指令仍可使用：

```sh
uv run travel-assistant plan examples/input.json --output-dir output/legacy --flight-provider mock
```

### V2 功能

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
travel-assistant flight search REQUEST --provider mock|duffel|skyscanner|google-link|fli-experimental
```

`trip export --format` 可用 `json`、`markdown`、`ics`、`geojson`、`kml`。

### Provider

| Provider | 行為 |
|---|---|
| `mock` | 完全離線；只回查詢形狀，不捏造價格 |
| `duffel` | 讀 `DUFFEL_ACCESS_TOKEN`，官方 Offer Request，多 slice；只搜尋、不下單 |
| `skyscanner` | 需 Partnerships 核准、`SKYSCANNER_API_KEY` 與明確 `--enable-skyscanner` |
| `google-link` | 只產生 Google Flights 查詢連結，不宣稱即時結果 |
| `fli-experimental` | 預設硬拒絕；只保留 injected adapter 邊界，不內建逆向 live call |

### 輸入與限制

V2 schema 嚴格拒絕未知欄位與懸空 place/source reference。Verified source 必須有 URL；估算與不可用資料必須帶狀態。排程不移動 locked 項目；無解時輸出 conflict，不靜默刪除。航班價格、班次、開放時間仍需重查；本工具不代訂、不付款。

### Hermes Skill

將 repo 的 `skills/` 註冊到 Hermes `skills.external_dirs`；會保留既有目錄：

```sh
python3 scripts/install_hermes_skill.py
```

安裝器會建立 `.venv`、安裝鎖定相依並註冊 Skill。安裝後可直接對 Hermes 說：「幫我規劃 10 月從台北到大阪的四天自由行，兩人、預算 4 萬、喜歡美食與歷史。」Hermes 會蒐集必要資訊、保存來源、建立 revision、規劃並輸出五種格式。

### 文件

- [V1 research](docs/RESEARCH.md)：第一版設計背後的研究依據。
- [V2 能力調研](docs/V2-RESEARCH.md) 與 [V2 工程計劃](docs/V2-PLAN.md)：TREK 差距、輪子選型、安全界線與驗收。
- [Hermes 操作規則](skills/travel-planner-assistant/SKILL.md)：Agent 的操作規範。

### 邊界

- 只搜尋與規劃：不查飯店庫存、不做餐廳或票券預訂、不付款。
- API key 只從環境變數讀取，不得寫入 JSON、Markdown、日誌或 Git；可從 `.env.example` 開始。
- 離線優先：所有第三方服務都隔離在 adapter 後方，並限制逾時與回應大小。
