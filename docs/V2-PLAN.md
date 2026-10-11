# V2 工程計劃書

狀態：完成

基準：`5be2e67`

目標版本：`2.0.0`

V2 最低執行環境升為 Python 3.10。原因：Python 3.9 已 EOL，且本計劃採用輪子的現行維護版本已以 3.10 為最低版本；不以鎖定舊套件換取名義相容。

## 交付定義

V2 是可由 Hermes 完整操作、離線 fixtures 可驗收的本機旅遊規劃核心，不是 Web SaaS。完成時必須同時具備：

1. 正規化旅程模型：多航段、活動時窗、住宿、預約、費用、清單、來源快照。
2. SQLite revision 儲存與 V1 JSON migration。
3. 時間／固定錨點／移動時間感知排程，支援 locked item 與可解釋衝突。
4. 統一航班 provider 契約；Duffel 多 slice、Skyscanner gated、Google 深連結、`fli` 實驗 gate。
5. Markdown、JSON、ICS、GeoJSON、KML 輸出。
6. Hermes 可執行 create、plan、replan、flight search、export、explain。
7. 所有外部結果帶 provider、時間、狀態與 warning；錯誤不偽裝成空結果。

不含：訂位、付款、帳號、Web UI、多人協作、即時餐廳／火車庫存、逆向 Google live call。

## 輪子與膠水

| 輪子 | 用途 | 授權／政策 | 決策 |
|---|---|---|---|
| [pydantic](https://github.com/pydantic/pydantic) | domain 與輸入／輸出契約 | MIT | runtime dependency |
| [httpx](https://github.com/encode/httpx) | timeout、redirect policy、transport 注入 | BSD-3-Clause | runtime dependency |
| [tenacity](https://github.com/jd/tenacity) | 有界 retry／backoff | Apache-2.0 | 已評估，V2.0 不引入；各 POST/session 的重試語義不同，不做假安全的共用 retry |
| [icalendar](https://github.com/collective/icalendar) | RFC 5545 ICS | BSD-2-Clause | runtime dependency |
| [OSRM](https://github.com/Project-OSRM/osrm-backend) | 步行／開車 route matrix | 遠端 API；不 vendoring | optional adapter；haversine 降級 |
| [Overpass API](https://github.com/drolbr/Overpass-API) | OSM POI 探索 | 遠端服務、遵守 instance policy | optional adapter；限量與 cache |
| [fli](https://github.com/punitarani/fli) | Google Flights 能力研究 | MIT；Google 非公開 RPC 風險 | 只保留 injected adapter 邊界；不加套件相依，預設禁用，V2 不做 live call |

膠水原則：domain 不依賴 provider；排程器純函式；網路結果先正規化成 snapshot；CLI 只編排 service；外部 client 可注入 fixture transport。

## 工作包

### Luna：domain、storage、planning

檔案所有權：`domain/`、`storage/`、`planning/` 與對應測試。不得修改 CLI、provider、exporter、README、Skill、package manifest。

- Pydantic domain model 與 V1 migration。
- SQLite schema／migration／revision repository。
- opening intervals、fixed/locked anchors、buffer、priority。
- haversine travel matrix、地理鄰近排序、OSRM matrix interface。
- 排程衝突與 explanation model。

判決：V1 可遷移；多航段不丟失；固定項目不移動；移動分鐘計入；無解回衝突；revision 可 round-trip。

### Terra：providers、research、exporters

檔案所有權：`providers_v2/`、`research/`、`exporters/` 與對應測試。不得修改 CLI、core、domain、storage、planning、README、Skill、package manifest。

- Provider capabilities、狀態與 typed error。
- Duffel 多 slice mapping；Skyscanner create/poll gated client。
- Google Flights query deep link；`fli` experimental disabled gate。
- OSRM／Overpass clients 必須 bounded、可注入 transport、限制結果大小。
- JSON、Markdown、ICS、GeoJSON、KML exporter。

判決：empty 與 failure 可區分；無 key fail loud；429／timeout／parse error 映射；實驗 Google 預設拒絕；export fixtures 可解析且無秘密。

### 主線整合

- package dependencies、version、public exports。
- 新 CLI 命令與舊 `plan` 相容 migration。
- services 編排、來源追溯、預算摘要。
- Hermes Skill、schema／provider references、README／範例。
- 端到端與安全驗收；裁決代理衝突。

## 介面草案

```text
travel-assistant trip create INPUT --database DB
travel-assistant trip plan TRIP_ID --database DB --output-dir DIR
travel-assistant trip replan TRIP_ID --database DB --output-dir DIR
travel-assistant trip export TRIP_ID --database DB --format ics|geojson|kml
travel-assistant trip explain TRIP_ID --database DB
travel-assistant flight search REQUEST --provider mock|duffel|skyscanner|google-link
travel-assistant plan INPUT --output-dir DIR   # V1 migration path
```

輸出禁止宣稱已訂位／已付款／價格保證。

## 驗收矩陣

| ID | 驗收 |
|---|---|
| A1 | V1 `examples/input.json` 仍能產生計畫 |
| A2 | 三段多城市航班 request 可正規化並保存 |
| A3 | fixed／locked 活動與 travel time 進入時間軸 |
| A4 | 無法排程活動輸出機器可讀 conflict reason |
| A5 | SQLite 兩次重排產生遞增 revision，舊版可讀 |
| A6 | provider 狀態涵蓋 empty、timeout、429、auth、parse、unavailable |
| A7 | Google 逆向 live path 預設無法啟動；深連結可用 |
| A8 | ICS、GeoJSON、KML 可由標準 parser 或 XML／JSON parser 讀回 |
| A9 | Hermes Skill 能走 create → plan → explain → export |
| A10 | log／輸出不含測試 token；URL guard 阻擋非 HTTPS／私網目標 |
| A11 | 單元、整合、舊回歸全過；CI 不需外網 |
| A12 | Python 3.10+ 乾淨 venv 安裝成功；package metadata 明確拒絕更舊版本 |

## 完工門檻

- `python -m unittest discover -s tests -v` 全過。
- `python -m compileall -q src skills` 全過。
- `git diff --check` 無誤。
- 離線端到端產出 JSON／Markdown／ICS／GeoJSON／KML。
- 乾淨環境安裝成功，Hermes Skill 指令可執行。
- 版本 `2.0.0`、commit 與 annotated tag `v2.0.0` 推送，遠端無 ahead commit。

驗收結果：80 項單元／整合／舊版回歸通過；Python 3.10 乾淨安裝、Hermes create → plan → explain → export、五格式 parser round-trip 均通過。發布以 annotated tag `v2.0.0` 為準。
