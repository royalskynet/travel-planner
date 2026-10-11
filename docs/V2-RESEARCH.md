# V2 能力調研與實作規格

查證日期：2026-09-19。此文件定義 V2 範圍，不代表目前版本已支援。

## 結論

V2 應從「活動裝箱 CLI」升級為 Hermes 可操作的「可查證旅程模型」：多航段航班、景點探索與資料補全、開放時間與移動時間感知排程、住宿／預約錨點、完整預算、地圖與行事曆輸出，以及能分辨失敗原因的 provider 層。

不應把 TREK 整套搬入：帳號、協作、社交、PWA、相簿、外掛市集與管理後台不直接提升單人 Hermes 規劃品質，延後處理。TREK 為 AGPL-3.0；本專案維持 MIT，只借鏡產品能力與邊界，不複製其程式碼。

Google Flights 逆向搜尋可做隔離的本機實驗 adapter，但不得成為預設或唯一來源。正式路徑先採目前可用的 Duffel，取得 Partnerships 核准後再加入 Skyscanner；未核准時提供 Google Flights／Skyscanner 深連結，由使用者自行確認。原因：`fli` 呼叫未公開 Google RPC，存在條款、429、回應格式漂移及錯價風險。

## 現行系統模型

目前流程：

```text
input.json
  ├─ validate_input：基本型別、IATA、日期、活動來源
  ├─ schedule：興趣分數 + 開放星期 + 每日分鐘上限
  ├─ FlightProvider：mock / Duffel / 停用的 Skyscanner
  ├─ Open-Meteo：取第一個已排活動座標，限 16 日內
  └─ plan.json + plan.md
```

已支援：

- 單一起點、單一目的地、連續日期。
- 使用者先提供的活動；來源 URL、查證時間、座標、星期、費用驗證。
- 確定性逐日分配，不重複、不超過步調分鐘。
- Duffel 單一去程搜尋、離線 mock、可選 Open-Meteo。
- JSON／Markdown；無訂位、付款或寫入第三方服務。

## 目前不支援清單

以下由 `src/`、CLI、測試與 Skill 實際介面核對，不只依 README：

### 航班

- 去回程、多城市、開口行程、不同機場組合、多段與轉機細節。
- 兒童／嬰兒、艙等輸入、行李、停靠數、航空公司、聯盟、時間窗與轉機時間篩選。
- 彈性日期價曆、鄰近機場、價格排序、碳排與可訂購深連結。
- Skyscanner create/poll、Indicative Prices、session expiry；Google Flights provider。
- Offer 過期／價格變更重查、分頁、部分結果、快取、重試、退避、rate limit、circuit breaker。
- 「查無航班」與「provider 失敗」的結構化區分。

### 行程與地理

- 自動探索 POI；目前活動必須由 Hermes 或使用者先整理。
- 真正的開放時段、最後入場、休館例外、預約時段、時區。
- 活動開始／結束時間、用餐、休息、機場、飯店、固定事件錨點。
- 景點間距離、步行／開車／大眾運輸時間、路線排序與跨區警告。
- 壞天氣替代方案、無障礙、飲食限制、兒童／長者負荷與時差緩衝。
- 使用者鎖定項目後局部重排；目前只能修改輸入後全部重跑。

### 旅程資料

- 住宿搜尋或住宿區間；餐廳庫存；交通票券。
- 航班、住宿、餐廳、活動等統一 reservation 模型與確認碼／附件。
- EML、PDF、PKPass、HTML、GPX、KML、KMZ、Google Maps 清單匯入。
- SQLite 持久化、版本、歷史、使用者偏好或跨次旅程資料。

### 預算與輸出

- 航班、住宿、當地交通、餐飲、保險、購物等分類預算。
- 多幣別、匯率來源／凍結時間、多人分帳與結算。
- 互動地圖、路線、GeoJSON／KML／GPX、ICS、PDF。
- 打包清單、待辦、預訂檢查清單與到期提醒。

### Provider 與安全

- Provider capability negotiation、統一 response schema、資料 provenance／freshness。
- 契約 fixture、sandbox 整合測試、可觀測性與錯誤 taxonomy。
- 來源 URL 只驗證 scheme，沒有 DNS／私網／重導向 SSRF 防護或 host allowlist。
- 金鑰遮罩、呼叫稽核、每 provider 配額與成本上限。

### 產品層

- Web UI、PWA、離線同步、即時協作、帳號／權限、公開分享。
- MCP server；目前由 Hermes Skill 呼叫本機 CLI。
- 訂位、持有票價、購票與付款，且 V2 仍不納入。

## TREK 差距矩陣

上游快照：[liketrek/TREK](https://github.com/liketrek/TREK)，約 14,035 stars、AGPL-3.0、最新查得 release `v4.2.1`。星數僅為採用度訊號，不是品質保證。

| 能力 | TREK | 現行版本 | V2 決策 |
|---|---|---|---|
| 逐日規劃 | 拖曳、排序、鎖定、復原 | 分鐘裝箱 | **實作**時間軸、固定錨點、鎖定與局部重排 |
| 地圖／POI | OSM／Google Places、Overpass、Wikidata／Wikipedia | 無 | **實作** OSM 優先探索與可追溯 enrichment；Google Places 僅有 key 才啟用 |
| 路線 | 最近鄰 + 2-opt、OSRM、飯店錨點 | 無 | **實作** travel-time matrix、步行／開車排序與降級 |
| 大眾運輸 | Transitous | 無 | **實作實驗 adapter**；無覆蓋時輸出人工查核連結 |
| 天氣 | 16 日預報、遠期 archive | 單一座標、16 日內 | **實作**每日區域天氣；遠期只標示歷史氣候參考，不冒充預報 |
| 航班／火車 | 多段、時區、機場資料 | Duffel 單程摘要 | **實作**多航段與正規化 flight schema；火車先作 reservation／連結 |
| 住宿 | 跨日 stay | 無 | **實作**住宿錨點與使用者輸入 reservation；即時庫存取決於核准 provider |
| 預訂匯入 | KItinerary 多格式 | 無 | **延後至 V2.2**，先做結構化 JSON／ICS 匯入 |
| 費用 | 多幣別、分帳、結算 | 活動費總和 | **實作**分類預算與匯率 provenance；分帳列 V2.2 |
| 清單／待辦 | 打包、指派、提醒 | 無 | **實作**單人打包與預訂 checklist；多人指派延後 |
| 匯出 | GPX、ICS、PDF | JSON、Markdown | **實作** ICS + GeoJSON/KML；PDF／GPX 列 V2.2 |
| 協作／分享 | WebSocket、角色、邀請、公開頁 | 無 | **不納入 V2** |
| Journal／Atlas／Vacay／Collections | 完整模組 | 無 | **不納入 V2** |
| PWA／離線寫入 | IndexedDB、queue、衝突處理 | 本機 CLI | **不納入 V2**；本機 SQLite 本來可離線 |
| 外掛系統 | sandbox、權限、簽章 registry | Python provider 類別 | **不納入 V2**；只做明確 adapter 介面 |
| MCP | OAuth、細粒度 scopes、大量工具 | Hermes Skill + CLI | **V2 先強化 Skill**；MCP 延後，避免重複介面 |
| 帳號／安全後台 | OIDC、2FA、passkey、SSRF、audit | 無伺服器 | **只實作適用部分**：SSRF、secret redaction、provider audit |

## Google Flights 逆向能力

研究對象：[punitarani/fli](https://github.com/punitarani/fli)，約 3,173 stars、MIT、Python 套件名稱 `flights` 0.10.0。它不是 Google 官方 SDK，也不是 HTML scraper；程式碼以瀏覽器 impersonation 對未公開端點送出編碼請求：

- `FlightsFrontendService/GetShoppingResults`：指定日期航班。
- `FlightsFrontendService/GetCalendarGraph`：彈性日期價曆；每批最多 61 日，文件稱最遠 305 日。
- `FlightsFrontendService/GetBookingResults`：選定 itinerary 的航空公司／OTA 選項。
- 解碼 JSONP-like `wrb.fr` chunk 與位置式陣列；依賴未公開 payload／response shape。

### 可提供能力

- 單程、去回程、多城市；多起點／目的地機場。
- 經濟／豪經／商務／頭等、旅客數、基本經濟艙排除。
- 最大停靠數、出發時間窗、航空公司／聯盟 include/exclude、轉機上下限。
- 行李、較低碳排篩選、價格／時間／時長等排序。
- 價格、幣別、完整 legs、轉機、機型／腿部空間等部分資訊。
- Google Flights 搜尋／itinerary 深連結、航空公司與 OTA 訂購選項。
- MCP 提供 `search_flights`、`search_dates`、`get_booking_options`、`find_airports`；CLI 另有 multi-city。
- 自帶 10 req/s token bucket、最多三次 exponential-backoff retry、typed network errors。

### 已知限制與風險

| 風險 | 證據 | V2 控制 |
|---|---|---|
| 非公開契約隨時改 | parser 明確有 `SearchParseError` 處理 response shape change | 隔離 subprocess／adapter、fixture canary、立即停用開關 |
| 服務條款 | [Google Terms](https://policies.google.com/terms) 限制逆向專有資訊及違反 machine-readable 指示的自動存取 | 正式環境預設禁用；產品啟用前做法律／條款審查 |
| 429／封鎖 | [fli #203](https://github.com/punitarani/fli/issues/203) | 單程序低配額、cache、jitter、circuit breaker；不承諾可用性 |
| 空結果語義錯 | [fli #234](https://github.com/punitarani/fli/issues/234) | adapter 必須回 `empty`、`timeout`、`blocked`、`parse_error` 等不同狀態 |
| 航線／篩選錯誤 | [fli #223](https://github.com/punitarani/fli/issues/223)、[#235](https://github.com/punitarani/fli/issues/235) | 與官方 provider 或人工深連結交叉查核，不自動選為唯一「最佳」 |
| 價格／解析錯 | [fli #127](https://github.com/punitarani/fli/issues/127)；過往亦有幣別與 LCC 解析修正 | 價格帶 `checked_at`、來源、幣別；零價／異常價剔除；購買前重查 |
| MCP 多城市缺口 | [fli #214](https://github.com/punitarani/fli/issues/214) | V2 直接用 Python adapter 或 CLI multi，不假設 MCP 支援 |
| Python 版本／依賴增重 | `fli` 需 Python 3.10+、Pydantic、curl-cffi、Tenacity 等 | optional extra 或隔離 venv，不污染零相依核心 |

Google 的公開 Flights 開發者頁面面向航空公司／OTA 合作夥伴，部分整合資料為 NDA 與 invite-only；它不是供一般應用任意查詢消費者航班的公開 API。因此「能逆向取得」與「適合正式整合」是兩件事。

### V2 provider 政策

```text
FlightSearchService
  ├─ SkyscannerProvider       official, approval required
  ├─ DuffelProvider           official, available now
  ├─ GoogleFlightsLink        no search; deterministic handoff link
  └─ FliExperimentalProvider  unofficial; disabled by default
```

規則：

1. Provider 宣告 capabilities，呼叫前不猜測功能。
2. 官方 provider 優先；實驗來源不得靜默 fallback 成正式結果。
3. `FliExperimentalProvider` 需使用者明確 opt-in、獨立設定、來源標籤與健康狀態；不用 Google 帳號 cookies，不繞過 CAPTCHA／封鎖。
4. 任何價格都輸出 `provider`、`retrieved_at`、`expires_at`（若有）、`currency`、`is_live`、`booking_url` 與 warning。
5. Hermes 只能搜尋／比較／開啟連結；不得建立訂單、輸入付款資料或宣稱已保留價格。

## V2 必做需求

### P0：可相信的規劃核心

#### V2-DOM：旅程模型與持久化

- `Trip`、`Day`、`Place`、`Activity`、`TravelLeg`、`Stay`、`Reservation`、`Expense`、`ChecklistItem`、`SourceSnapshot` 分離。
- `flight_segments[]` 支援 1..N 段、各段日期／機場／時區；原本 `origin`／`destination` 輸入提供一次明確 migration。
- SQLite 儲存 trip revision；每次重新規劃保留輸入、provider 查詢摘要與產出版本。
- 每個外部事實保存來源、查證時間、原始時區、freshness；推測值明確標示 `estimated`。

驗收：舊範例可遷移；去回程、三段多城市與 open-jaw 不丟段；同一輸入與同一 provider fixture 產生相同結果。

#### V2-PLAN：時間／路線感知排程

- 活動改用日期例外 + 每日 opening intervals，而非只有星期。
- 支援 fixed time、最早／最晚開始、停留長度、buffer、priority、locked、室內／室外標籤。
- 飯店、機場、訂位、用餐為 day anchors；排程納入點間 travel time。
- 以地理 clustering + route matrix 排序；OSRM 失效時降級 haversine 估算並標示 estimated。
- 局部重排不得移動 locked items；無解時列出衝突，不靜默刪除。

驗收：跨城來回不被排進同一時段；休館／固定預約／移動時間均能造成可解釋的重排；provider 失效仍可產生帶警告的行程。

#### V2-SOURCE：POI 探索與查證

- OSM／Overpass 搜尋候選；Wikipedia／Wikidata／Wikimedia 補描述與圖片 provenance。
- Google Places 僅在使用者有合法 key 時啟用，不作必需相依。
- Hermes 研究工作流保留官方景點、政府旅遊、交通官網的高優先級。
- 合併去重依座標、名稱與外部 ID；不同來源衝突不得任選，保留差異供 Hermes 判斷。

驗收：只給城市與興趣也能產生候選集；每個排入活動有可開啟 URL、查證時間、座標與開放時間狀態。

#### V2-FLIGHT：多 provider 航班搜尋

- 正規化一程／去回／多城市、legs／segments、當地時間與 offset、價格、行李、停靠、航空公司、深連結。
- 搜尋條件支援旅客類型、艙等、最大停靠、時間窗、航空公司與轉機時間。
- Duffel 擴成多 slice；完成 timeout、HTTP／schema error mapping、offer expiry 與異常價格處理。
- Skyscanner 實作 create/poll 與 session expiry，但只有核准 API key 才可啟用。
- 彈性日期：正式優先 Skyscanner Indicative；`fli` 僅 opt-in 實驗來源。
- 統一結果狀態：`ok`、`empty`、`timeout`、`rate_limited`、`blocked`、`auth_error`、`parse_error`、`unavailable`。

驗收：fixture 覆蓋單程、去回、多段、無結果、timeout、429、schema drift、過期 offer；任一 provider 故障不會偽裝成零結果。

#### V2-OPS：provider 基礎設施

- capability registry、timeout、bounded retry、rate limit、cache、circuit breaker、request id。
- 紀錄 provider、延遲、狀態與結果數，不記 token、完整個資或付款資料。
- 外部 URL 僅允許 HTTPS；DNS 解析後拒絕 loopback／private／link-local，限制重導向與 response size。
- 契約 fixture 與可選 live smoke test 分開；CI 不依賴即時價格。

### P1：完整可用旅程

#### V2-STAY／RESERVATION

- 住宿跨日、check-in／out、地址與座標；每日以住宿作起終點。
- 航班、火車、住宿、餐廳、活動採統一 reservation envelope。
- 先支援手動／JSON／ICS 匯入；飯店 live inventory 僅在核准 Skyscanner 或其他正式 API 後啟用。

#### V2-BUDGET

- 交通、住宿、活動、餐飲、保險、購物、其他分類；planned／quoted／paid 狀態。
- 多幣別匯率含來源與 `rate_at`，規劃時凍結；不把預估寫成已付款。
- 每日與全程餘額、超支警告；V2.2 再做多人分帳。

#### V2-EXPORT

- Markdown／JSON 保持；新增 ICS 與 GeoJSON/KML。
- ICS 正確時區；地圖輸出含日別、排序、來源連結與路線估算標記。
- 打包清單、預訂 checklist、出發前重查清單。

#### V2-WEATHER

- 依每日主要區域取得 Open-Meteo，不再共用單一活動座標。
- 16 日外顯示歷史氣候參考或 unavailable，禁止標成實際預報。
- 室外活動因雨重排時保留原計畫與原因。

### Hermes 介面

V2 先維持 Skill + CLI，避免同時維護 MCP：

```text
trip create       建立／遷移旅程
trip research     探索 POI 並保存來源快照
trip plan         產生時間軸與路線
trip replan       以 revision + locked items 局部重排
flight search     比較 providers
flight dates      彈性日期
trip export       markdown/json/ics/geojson/kml
trip explain      解釋衝突、取捨、警告與來源 freshness
```

Skill 驗收：Hermes 能從自然語言建立旅程、只追問會改變結果的缺失欄位、執行命令、讀回產物並清楚區分已查證／預估／不可用。

## 明確延後

- 訂位、付款、保留票價、取消／退款。
- Web UI、PWA、多人即時協作、公開分享、帳號／SSO／2FA。
- TREK 類 plugin marketplace、journal、Atlas、Vacay、Collections。
- 餐廳即時庫存、火車全球即時庫存；沒有合規 provider 前只做 reservation／連結。
- Google Flights 價格預測、價格追蹤通知；非公開資料源不支撐服務承諾。
- PDF、GPX、多人大帳與 KItinerary 文件解析延到 V2.2。

## 建議模組邊界

```text
src/travel_assistant/
  domain/          trip、place、reservation、money、source
  planning/        constraints、scheduler、routing、replan
  providers/
    flights/       duffel、skyscanner、fli_experimental、links
    places/        osm、overpass、wikidata、google_places
    routes/        osrm、transitous、haversine
    weather/       open_meteo
    currency/      frankfurter
  services/        research、flight_search、plan、export
  storage/         sqlite、migrations、revisions
  exporters/       markdown、json、ics、geojson、kml
  cli.py
```

Provider 與 domain 間只交換正規化模型。排程器不直接呼叫網路；research/service 先取得帶 provenance 的 snapshot，再交給純函式規劃，才能重現與測試。

## 交付順序

1. **V2.0-A 基座**：domain schema、SQLite、revision、provider error taxonomy、舊格式 migration。
2. **V2.0-B 航班**：Duffel 多 slice、正規化結果、深連結、Skyscanner gated adapter；`fli` 先交付 adapter 邊界與離線 canary fixtures，通過條款／法律門檻後才允許 live call。
3. **V2.0-C 規劃**：opening intervals、anchors、OSRM／haversine、locked replan、衝突解釋。
4. **V2.0-D 研究**：OSM／Overpass、Wikidata／Wikipedia enrichment、來源衝突與 freshness。
5. **V2.1 旅程完整度**：stay／reservation、預算／匯率、天氣重排、ICS／GeoJSON／KML、Hermes Skill 升級。
6. **V2.2 後續**：文件匯入、PDF／GPX、分帳；通過實際需求驗證後才評估 UI／MCP。

每一階段都必須保持 mock／fixture 完整離線可驗收；live provider 測試為顯式 opt-in。

## 上線門檻

- 所有外部結果可追溯，錯誤不偽裝為空結果，價格不偽裝為保證。
- 多航段、時區、固定預約與移動時間有 fixtures；舊輸入 migration 有 golden tests。
- 無 token／個資寫入輸出或 log；SSRF、redirect、response-size 測試通過。
- Duffel sandbox contract test 通過；Skyscanner 只有 Partnerships 核准後才解除停用。
- `fli` 需另過條款／法律決策，預設關閉；失效時官方 provider／深連結仍可用。
- Hermes 端到端：建立、研究、規劃、局部重排、航班比較、匯出與解釋全部可由 Skill 操作。

## 主要來源

- [TREK README 與功能清單](https://github.com/liketrek/TREK)
- [fli README 與原始碼](https://github.com/punitarani/fli)
- [Google Flights Search partner documentation](https://developers.google.com/travel/flights)
- [Google Terms of Service](https://policies.google.com/terms)
- [Google Flights 結果與排名說明](https://support.google.com/travel/answer/7664728)
- [Skyscanner Travel APIs](https://developers.skyscanner.net/docs/intro)
- [Skyscanner 認證與 Partnerships 申請](https://developers.skyscanner.net/docs/getting-started/authentication)
- [Skyscanner Flights Live Prices](https://developers.skyscanner.net/docs/flights-live-prices/overview)
- [Skyscanner Flights Indicative Prices](https://developers.skyscanner.net/docs/flights-indicative-prices/overview)
- [Duffel Offer Requests](https://duffel.com/docs/api/offer-requests)
- [Duffel test mode](https://duffel.com/docs/api/overview/test-mode)
