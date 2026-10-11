# V2 Provider 規則

所有航班結果必須有 `provider`、`status`、`retrieved_at`、`warning`；`empty` 與 timeout／429／auth／parse／unavailable 不可混為一談。

## mock

預設、完全離線。回傳多航段查詢形狀，`price: null`；不得當報價。

## Duffel

設定 `DUFFEL_ACCESS_TOKEN` 後用 `flight search ... --provider duffel`。支援多 slice 與精簡 offer normalization；只搜尋，不建立 order。缺 token fail loud。

## Skyscanner

官方 Travel API 需 Partnerships 審核。只有已核准、設定 `SKYSCANNER_API_KEY`，並顯式加 `--enable-skyscanner` 才能用。採 create → poll；session 未完成回 timeout，不假裝空結果。

## google-link

建立 Google Flights 搜尋深連結；`is_live: false`，沒有價格。適合人工交叉查證。

## fli-experimental

預設硬拒絕，不安裝、不 import、不自行 live call。程式只保留 `enabled + injected adapter` 邊界供未來獨立條款審核；不得繞過 CAPTCHA、封鎖或使用 Google cookies。

## OSRM／Overpass

只允許 HTTPS 公網；預設官方 host，禁止 redirect，限制 timeout、座標／查詢數與 response size。自訂 endpoint 必須搭配 injected transport，私網仍拒絕。失敗時排程用 haversine estimated fallback；POI 查詢失敗則標 unavailable。
