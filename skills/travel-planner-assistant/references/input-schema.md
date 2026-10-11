# V2 輸入格式

完整範例：repo `examples/v2-input.json`。

頂層必要欄位：

- `schema_version`: 固定 `2`
- `id`、`title`
- `start_date`、`end_date`
- `timezone`: IANA 名稱，例如 `Asia/Tokyo`
- `travellers`、`currency`
- `places[]`: `id`、`name`、`location.latitude/longitude`
- `activities[]`: `id`、`name`、`place_id`、`duration_minutes`

可選模型：

- `flight_segments[]`: 多航段 IATA、departure／arrival 與時區。
- `days[]`: 日期與每日起終點。
- `travel_legs[]`: 已知移動時間與是否 estimated。
- `stays[]`、`reservations[]`。
- `expenses[]`: 類別、金額、幣別、planned／quoted／paid。
- `checklist[]`: packing／booking／document／recheck。
- `sources[]`: provenance snapshot。

活動約束：

- `opening_windows[]`: `weekday` 或 `on_date`，加 `start`／`end`。
- `fixed_start`: 固定時段。
- `locked`: 必須同時有 `fixed_start` 或 `scheduled_start`。
- `earliest_start`、`latest_start`、`buffer_before_minutes`、`buffer_after_minutes`。
- `priority`: `0..100`。
- `source_ids`: 指向 `sources[]`。

來源規則：

- `verified` 必須有真實可開啟 URL。
- `estimated`、`stale`、`unavailable` 可沒有 URL，但要在 `facts` 寫明原因。
- 禁止 `example.com`、搜尋摘要或未開啟網址冒充來源。
- 所有 place／source reference 必須存在；未知欄位會 fail loud。

V1 JSON 仍可交給 `trip create`，系統會 deterministic migration；因 V1 沒有航班時間，航段只會是 estimated placeholder，不得當真實班次。
