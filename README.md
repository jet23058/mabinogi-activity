# 瑪奇活動與韓台改版時間軸資料

提供活動提醒擴充功能使用的公開 JSON：

- `remote-overrides.json`：活動日期與分類修正。
- `gacha-overrides.json`：轉蛋分類例外。
- `update-timeline.json`：依韓版正式更新日排序的功能改版時間軸。

## 收錄原則

時間軸採 `selectionPolicy.mode = curated-features`，每筆代表一項具體功能、劇情章節、改版階段或合作活動。例如 NEW RISE 第1波、生產配方收藏、喀輪巴斯深淵難度，而非每週的「正式伺服器更新內容公告」。

- `timeline/curated.json` 是已確認的基準與人工修正；AI讀取韓版公告內文，拆解具體功能，提供逐字證據後自動增補 `events`，不以公告標題當作功能。
- 每週例行更新公告仍保存在 `timeline/source-index.json` 作為證據，可以用同一份公告支援多個具體功能。
- 尚未收錄的具體公告先進入 `reviewQueue`，整理成有意義的功能項目並補上來源後，再加入 `curated.json`。
- 四種分類維持「劇情大項目、改版大項目、小項目、合作」；同一主線或改版階段可使用相同 `groupId`。
- 請維持既有功能的穩定 `id`，不要因更名或換來源連結而建立重複項目。

## 台版對照與保留條件

`kr`、`tw` 含 `date`、`status`、`sources`。日期格式為 `YYYY-MM-DD`；待確認日期為 `null`。

- 已實裝：`status = released`，提供具體實裝日期與官方來源。
- 尚未查得實裝日：`status = pending`，不得以整章、整包的公告日取代個別部份的實裝日。
- `tw.matchStatus = partial` 表示部分對應，日期代表相關台版調整的更新日，不能當作全部數值與規格完全相同。
- `pending` 可以附上相關官方來源，但不因此改成已實裝。例如 G27 第2部保留台版 G27 公告，獨立開放日仍為待確認。
- `candidateSources` 只是關鍵字找到的候選證據，永遠不會自動覆蓋人工整理的日期與狀態。
- 沒找到台版公告不代表台版尚未實裝。

## 自動更新

[Update KR-TW timeline](.github/workflows/update-timeline.yml) 每天台灣時間 10:35 執行，也支援手動執行及相關檔案變更觸發。排程時間可能因 GitHub 排隊延後。

Action 執行測試、抓取韓台官網、更新來源索引，依已整理的功能清單產生 JSON，將變更提交回 `main`。抓取或翻譯失敗會保留上一份有效 JSON。前幾頁 HTTP 快取保留六小時，較舊頁面保留七天，失敗時也保存已取得的快取。

公開資料網址：

```text
https://raw.githubusercontent.com/jet23058/mabinogi-activity/main/update-timeline.json
```

## 繁體中文名稱

`timeline/localization.json` 維護台版官方用語及來源，優先使用聖盾守衛、禁忌鍊金士、布里萊赫、回音石等名稱。未定名專有名詞保留原文並附 `（繁中譯名，暫譯）`。

固定格式離線翻譯；未知標題與引號內新名詞視需要使用 Google 公開網頁翻譯端點轉成 `zh-TW`，逐字串保存於 `timeline/translations.json`。這不是具 SLA 的付費 Cloud API，僅傳送公開標題，不傳送公告內文或使用者資料。增修官方詞庫時請提高 `revision`。

原文保存在 `originalTitle`；對外顯示使用 `title`。機器翻譯不能作為台版官方定名或實裝證據。若翻譯失敗、仍含未處理韓文或改動受保護的名稱，本輪不覆蓋有效資料。

## 本機驗證

Python 3.13，無額外套件：

```sh
python -m unittest discover -s tests -v
python scripts/update_timeline.py --offline
python scripts/update_timeline.py
```

`--offline` 使用已保存的來源索引、詞庫與翻譯快取，完全不連外。`--today YYYY-MM-DD` 可固定資料日期以重現輸出。


## 公告內文研究流程

Action 使用 `--research`：

1. 保存韓版正式公告完整文字，依內容雜湊快取功能提取結果。一篇每週公告可拆出多個功能；例行維護、商城與零碎修BUG不列入。
2. 讀取台版公告內文，並追蹤官方 EventAD／月份改善事項連結，取得實際指南內容。
3. AI以功能內容與官方繁中名稱找到候選文章，再逐篇比對。實裝日須有來源原文引用與完整日期，程式驗證引用確實存在，不能使用固定落差或關鍵字命中直接判定。
4. 保留既有人工日期、部分對應與G27日期待確認等註記；AI新發現的候選修正列入待核對資料。
5. 新功能自動加入輸出；資料不足保持待確認，查證結果以 `research-state.json` 與 Actions 快取避免重複請求。失敗不覆蓋已發布JSON。

需要在此儲存庫的 Settings → Secrets and variables → Actions 設定：

- Secret `TIMELINE_AI_API_KEY`，或沿用 `GEMINI_API_KEY`。
- 可選 Variables：`TIMELINE_AI_BASE_URL`、`TIMELINE_AI_MODEL`，支援 OpenAI 相容的 HTTPS Chat Completions 服務。
- 預設使用 Gemini 官方相容端點與 `gemini-3.8-flash`；可指定其他供應商與模型。

只送出公開官方公告及詞庫。缺少金鑰會在設定檢查步驟明確失敗，不會把「僅爬完資料」宣稱成研究完成。首次回補需分析2025年起的公告，後續以內容與台版來源指紋快取增量更新。API用量依供應商方案計費。

研究測試使用模型替身，驗證提取、台版匹配、逐字證據、日期與快取；它不代表已完成真實供應商的端到端驗證。

英文改版與品牌名稱（例如 NEW RISE、NEW LIFE、RE:ACTION）保留英文，不額外加上中文直譯；括弧暫譯僅用於需要說明的韓文或日文專有名詞。


## Copilot Free／Copilot CLI（目前預設）

Action 已改用 Copilot CLI 1.0.103，透過內建 `GITHUB_TOKEN` 與 `copilot-requests: write` 呼叫個人帳號的 Copilot。不必設定 Gemini 金鑰，也不必另外申請 PAT。

- 開通儲存庫擁有者的 Copilot Free 後，可在 Actions → Update KR-TW timeline → Run workflow 手動執行；每天10:35也會排程。
- 為節省免費額度，每次只研究1篇公告、最多4次未命中快取的模型呼叫，優先處理近期與內容有變更的公告，之後逐批回補。
- 已提取功能與台版對應結果會保存，額度上限到達時保留已完成進度與未確認項目，下一次接續。
- 一次CLI呼叫仍可能消耗多個模型回合及token，呼叫數上限不等於費用或免費額度保證。額度不足或帳號驗證失敗時不覆蓋有效JSON。
- CLI只接受stdin內的公開資料並輸出JSON；停用內建MCP及工具，不授權讀寫專案檔案或執行shell。
- Gemini／OpenAI相容API後端仍可透過 `TIMELINE_AI_PROVIDER` 改為其他值並提供原先的API設定，在本機研究時使用。Action目前固定選用Copilot。

上方 Gemini 金鑰設定只適用於替代API後端，目前預設Action不需要那些Secrets。
