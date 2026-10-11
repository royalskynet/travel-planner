# V1 研究依據

截至 2026-09-19，V1 設計僅借鏡分層與 provider 邊界，未複製程式碼。V2 的現行決策以 `V2-RESEARCH.md` 與 `V2-PLAN.md` 為準。

- [TREK](https://github.com/liketrek/TREK)：2026-09-19 查得約 14k stars（查證日期快照，非永久事實）；AGPL-3.0；以行程、預算、清單分層作為概念參考，不納入程式碼，因授權與範圍不適合本 MIT 專案。
- [punitarani/fli](https://github.com/punitarani/fli)：2026-09-19 查得約 3.1k stars（查證日期快照，非永久事實）；MIT；逆向 Google Flights，僅作研究中的 provider 邊界參考，不作正式或預設來源，避免逆向抓取與服務穩定性風險。
- [Duffel Offer Requests](https://duffel.com/docs/api/offer-requests)：官方 API；支援 test mode；本專案只建立 offer request 搜尋，不下單。
- [Skyscanner API](https://developers.skyscanner.net/docs/intro)：官方 API 需 Partnerships 審核與 `x-api-key`；本專案沒有假造結果，未核准或未設定時明確失敗。
- [Open-Meteo API](https://open-meteo.com/en/docs)：無 key；天氣 adapter 僅作可選網路補充，失敗返回 `None`，不阻擋離線行程。

V1 選擇理由：標準函式庫足以完成當時的 schema、排程、CLI 與 HTTP；mock 是預設離線路徑。V2 為嚴格 domain 契約、bounded transport 與 RFC 5545 匯出新增 Pydantic、HTTPX、icalendar，仍維持第三方服務隔離在 adapter。
