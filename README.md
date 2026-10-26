# 瑪奇活動與韓台改版時間軸資料

提供活動提醒擴充功能使用的公開 JSON：

- `remote-overrides.json`：活動日期與分類修正。
- `gacha-overrides.json`：轉蛋分類例外。
- `update-timeline.json`：依韓版正式更新日排序的功能改版時間軸。

## 收錄原則

時間軸採 `selectionPolicy.mode = curated-features`，每筆代表一項具體功能、劇情章節、改版階段或合作活動。例如 NEW RISE 第1波、生產配方收藏、喀輪巴斯深淵難度，而非每週的「正式伺服器更新內容公告」。

- `events` 只從 `timeline/curated.json` 產生；不自動把抓到的公告變成卡片。
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
