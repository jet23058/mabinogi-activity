# 瑪奇活動與韓台改版時間軸資料

此 repository 提供活動提醒擴充功能使用的公開 JSON。

- `remote-overrides.json`：活動日期與延長修正。
- `gacha-overrides.json`：轉蛋分類例外。
- [`update-timeline.json`](update-timeline.json)：韓台改版時間軸。

## 自動更新

[`Update KR-TW timeline`](.github/workflows/update-timeline.yml) 每天台灣時間 **10:35** 執行，也可從 Actions → Run workflow 手動執行。修改產生器、已確認資料或測試時，會自動執行；排程可能因 GitHub 排隊而延遲。

只需 repository 內建的 `GITHUB_TOKEN`（`contents: write`），不用另外申請 AI API 或第三方服務。Actions 會測試解析器，抓取韓服官方公告及台服官網 API，產生 JSON，並將有變動的結果提交回 `main`。失敗會保留前一份成功結果；產物也可從 workflow artifact 下載。

```text
https://raw.githubusercontent.com/jet23058/mabinogi-activity/main/update-timeline.json
```

## 資料格式

`schemaVersion: 1`，`events` 依 `kr.date` 由早到晚排序，`groups` 將分部與階段合併成可展開的大項目。每個 event 有穩定 `id`、`title`、`category`、`groupId`、`importance`、`needsReview`、`kr`、`tw`。

| category | 顯示名稱 | 範例 |
| --- | --- | --- |
| `story` | 劇情大項目 | G28 第一、二部 |
| `major` | 改版大項目 | RE:ACTION 第一、二階段 |
| `minor` | 小項目 | 技能改善、每週正式服更新 |
| `collaboration` | 合作 | 瑪奇 × 魔法帽的工作室 |

`kr` / `tw` 包含 `date`（`YYYY-MM-DD` 或 `null`）、`status`（`released` / `announced` / `pending`）、`sources`（官方網址與標題）。韓服測試服、事前預約、直播與開發預告不作為正式實裝日；提前刊登的維護公告採正文或標題中的維護日。

台服的 `candidateSources` 可能來自開機公告或月份改善正文的關鍵字命中，**只供核對**，不能直接當作台版更新日。`pending` 是「尚未找到台版公告（待確認）」，不代表尚未實裝，也不推算台版上線日期。完整性以 `coverage.complete` 為準，目前為 `false`。自動收錄的中文名稱與分類待核對時，`needsReview` 為 `true`。

## 維護與人工修正

編輯 [`timeline/curated.json`](timeline/curated.json)，不要直接修改產生的 JSON：

1. 將自動項目的 `id` 保留，補齊台灣官方名稱、正確分類、群組與官方來源。
2. 台服已確認上線時，設定 `tw.status: released`、`tw.date`、`tw.sources`；只公告未上線可使用 `announced`。
3. 同一更新的開發者筆記、正式服公告都放到 `kr.sources`，避免被當成不同項目再次收錄。
4. `twSearchTerms` 可設定中文關鍵字，讓產生器從官網的月份改善與開機公告找候選對應。
5. 合作各自獨立，不併入一般改版；同一主線或改版的各階段沿用相同 `groupId`。

[`timeline/source-index.json`](timeline/source-index.json) 保存已找到的來源及台服公告正文索引，使舊公告不會因移出首頁而消失。HTTP 頁面快取在 Actions cache，近期列表保留 6 小時、舊列表保留 7 天。首次會回溯 2025 年起公告，之後以快取減少官方流量。只儲存文字索引與連結，不下載圖片。

## 本機驗證（Python 3.13，無額外套件）

```sh
python -m unittest discover -s tests -v
python scripts/update_timeline.py --offline
python scripts/update_timeline.py
```

最後一個指令會連線官網。`--offline` 只使用已保存的來源產生 JSON，不代表已即時核對官方。`--today YYYY-MM-DD` 可固定產出日期以重現結果。


## 繁體中文名稱

- `timeline/localization.json` 維護台版官方名詞、來源與暫譯，例如聖盾守衛、禁忌鍊金士、布里萊赫、回音石。
- 固定格式的每週更新公告離線翻譯；尚未定名的專有名詞保留原文並附 `（繁中譯名，暫譯）`。
- 未知的公告標題與引號內新名詞使用 Google 公開網頁翻譯端點轉成 `zh-TW`。這不是具 SLA 的付費 Cloud Translation API；只傳送公開標題，不傳送公告內文或使用者資料。
- `timeline/translations.json` 保存逐字串翻譯快取；已翻過的標題不會重複請求。增修官方名稱時，優先修改詞庫並提高 `revision`。
- 新翻譯失敗、仍含未處理韓文或改動已保護的專有名詞時，本輪產生失敗並保留上一份有效 JSON，不以原文標題覆蓋。
- 原文保存在 `originalTitle` 與來源索引，對外顯示使用 `title`；自動翻譯以 `titleTranslation.method = machine` 標記，不能當作台版官方定名或實裝證據。
- `python scripts/update_timeline.py --offline` 使用來源索引、詞庫與已保存的翻譯快取，完全不連外。
