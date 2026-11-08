# AI 協作日誌 001：拆解 MVP 驗收範圍

- 日期：2026-11-07
- 目的：把課程要求轉成可驗收的專案結構
- 使用者提示摘要：至少 3 則使用者故事、每則 3–5 條 AC、3 個 Feature／6 個情境、ADR、兩類因子、前 N 等權 baseline、月調倉扣成本回測、behave、README 與可重現執行。
- 關鍵提示詞原文：`請依作業 PDF 建立至少 5 則使用者故事（含 AC）、至少 5 個 Gherkin 情境與 1 份 ADR，並整理成可逐項驗收的交件結構。`
- AI 建議：將交付物分成 requirements、features、docs/adr、app、ai_log、configs 與 results；把個股因子和電子產業狀態訊號分開。
- 人工判斷：採納。電子指數 MA20 是市場狀態變數，不足以單獨滿足「兩種不同類別因子」，因此另外採用動能與低波動。
- 驗證：`MVP_CHECKLIST.md` 可逐項對照，`behave` 覆蓋核心接受標準。

