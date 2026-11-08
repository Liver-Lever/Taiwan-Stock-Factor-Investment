# 作業要求對照表

本表依先前上傳的《智慧因子投資MVP.pdf》要求摘要，以及《台股智慧因子投資策略：第 1 週三小時課程(1).pptx》第 2 週 MVP 頁面整理。

| 要求 | 專案位置 | 驗收方式 |
|---|---|---|
| 至少 5 則使用者故事，每則含 AC | `requirements/user_stories.md` | 5 則故事，每則 4–5 條 AC |
| 至少 5 個 Gherkin 情境 | `features/` | 4 Features、9 Scenarios |
| ADR | `docs/adr/0001-point-in-time-event-driven-backtest.md` | 記錄決策、替代方案與後果 |
| 至少 5 個因子、3 類別 | `app/factors.py` | 5 個因子、4 類別 |
| 前 N 名等權 baseline | `app/weights.py` | BDD 驗證入選數與權重 |
| 樣本內月調倉、扣交易成本 | `configs/real_proxy.json`、`app/backtest.py` | 真實資料 2015/01–2022/12，共 96 期，成本分項 |
| behave 全部通過 | `features/steps/mvp_steps.py` | 4 features、9 scenarios、27 steps |
| AI 日誌至少三筆，含一筆錯誤 | `ai_log/` | 第三筆記錄同日成交錯誤與修正 |
| README 與可重現執行 | `README.md`、`scripts/reproduce.sh` | 一個指令重建資料、測試與輸出 |
| 正式 benchmark 為臺灣加權報酬指數 | `data/production/benchmark.csv`、`TAIEX_TR` | 真實含息基準輸出 |
| 0050 參考比較 | `0050_monthly.csv`、`comparison_metrics.csv` | 月底含息調整參考，另標示成交邊界不同 |
| 樣本內／外分離 | 兩份 `real_proxy` 設定檔 | 樣本外未調參；已結算至 2026/08 |
| 避免成分股與公布時點洩漏 | `app/data.py` | `available_date` 與 `effective_date` 雙重限制 |
| 月底確認、下一交易日成交 | `app/calendar.py` | BDD 與 audit CSV |

## 本次研究規則

| 項目 | MVP 初始值 |
|---|---|
| 電子訊號 | 電子類股現貨指數月底收盤相對 MA20 |
| 轉弱 | 收盤低於 MA20 的 98% |
| 轉強 | 收盤高於 MA20 的 102% |
| 中間區間 | 延續前一期狀態 |
| 弱勢配置 | 電子股原權重減少 25% |
| 資金去向 | 依原權重比例分配至非電子股 |
| 執行 | 下一交易日調整後開盤價 |
| 初始交易成本 | 手續費 14.25 bps、賣出稅 30 bps、滑價 5 bps |

## 尚未完成的最終研究資料

逐期可驗證的 0050 原始歷史權重仍缺，因此目前三種 0050 核心組合皆使用「臺灣 50 歷史成分等權代理」。這不影響第 2 週 MVP 的需求、測試、成本回測與可重現性，但會限制最終研究對「超越原 0050」的因果結論。

