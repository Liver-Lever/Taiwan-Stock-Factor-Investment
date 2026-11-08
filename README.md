# 台股智慧因子投資策略：第 2 週 MVP

本專案實作兩條互相獨立、可比較的研究線：

1. 作業指定的規則式 baseline：在當時已上市的 TWSE／TPEX 普通股中，先以 20 日平均成交金額排除流動性不足者，再以 6 個月動能、1 個月反轉、60 日低波動、盈餘殖利率與 ROE 五個因子合成分數，選前 N 名等權。
2. 研究主題：月底用電子類股現貨指數收盤相對 MA20 的位置判斷狀態。低於 MA20 的 98% 進入弱勢，高於 102% 恢復強勢，中間區間延續前一期。弱勢時把電子股原權重減少 25%，資金依原權重比例轉至非電子股。

月底收盤只負責產生訊號，所有新權重都在下一交易日才生效。回測比較：

- 臺灣 50 歷史成分等權代理（不是原 0050 歷史權重）
- 固定把電子股原權重減少 25%
- 依 MA20 遲滯狀態動態減碼
- 五因子合成分數前 N 名等權 baseline
- 臺灣加權報酬指數（含息，正式作業 benchmark）
- 使用者提供的 0050 含息調整後月底參考序列（另列，成交邊界不同）

## 目前資料狀態

`data/demo/` 仍只供工程驗證。正式成果已改用 `data/production/` 的真實市場資料：91 檔股票、257,705 筆日行情、電子類現貨指數日資料、臺灣加權報酬指數，以及使用者提供的 0050／電子指數月底檔。2311 的歷史資料由 TWSE 官方行情、估值及除權息端點補齊。

唯一尚未取得的是「每一期可驗證的 0050 原始歷史權重」。目前成分名單由公開異動表回推，並補入 2016/11 與 2018/04 官方特殊事件，再採等權。因此所有結果名稱都含 `proxy`，不得宣稱為原 0050 權重策略。正式模式必須顯式傳入 `--allow-constituent-proxy` 才會接受這份資料。

使用者提供的 0050 月底序列在 2015–2018 可核對區間，和 TWSE 官方除權息重建報酬的相關係數約為 0.999999995、平均絕對差約 0.00028 個百分點；因此作為 0050 含息月底參考，但它不是次日開盤成交序列。

## 真實資料結果摘要

樣本內 2015/01–2022/12（已扣成本）：

| 策略 | CAGR | 年化波動 | 最大回撤 |
|---|---:|---:|---:|
| 臺灣 50 成分等權代理 | 5.88% | 13.99% | -24.04% |
| 固定減碼電子 25% | 5.86% | 13.69% | -22.54% |
| 動態減碼電子 25% | 5.25% | 13.99% | -23.91% |
| 五因子前 10 名等權 | 5.60% | 16.24% | -26.85% |
| 臺灣加權報酬指數 | 9.68% | 15.93% | -25.34% |
| 0050 月底含息參考 | 9.68% | 17.28% | -29.33% |

樣本內結論：2% 遲滯＋弱勢減碼 25% 並未提升報酬，也沒有明顯改善最大回撤；固定減碼的波動與回撤稍低，但仍落後市場基準。這是目前資料與事前參數下的結果，不代表策略已被證明有效。

樣本外已完整結算 2023/01–2026/08；2026/09 的訊號與市場資料已保存，但要完成該月績效仍需要 2026/10 的個股成交邊界，所以不把它混入已結算數字。

作業逐項對照見 `docs/requirements_traceability.md`，正式資料取得方向見 `docs/official_data_sources.md`。

## 交付物

- 需求與設計：`requirements/`、`features/`、`docs/adr/`
- 可執行程式與測試：`app/`、`pipeline/`、`tests/`、`scripts/reproduce.sh`
- 9 頁回測報告簡報：[Canva｜台股智慧因子投資策略 MVP](https://www.canva.com/d/G8NDbYEvtJn1JR_)
- AI 使用紀錄：`ai_log/`（三筆，含一筆錯誤與修正）
- 作業對照與限制：`MVP_CHECKLIST.md`、`docs/requirements_traceability.md`

依題意，本交付包不含五分鐘現場展示。簡報第 7 頁已更新為本 README 所列的樣本內真實資料結果，並清除舊版文字殘影。

## 一鍵重現

macOS 或 Linux：

```bash
chmod +x scripts/reproduce.sh
./scripts/reproduce.sh
```

或分步執行：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m app.cli make-demo-data --output-dir data/demo
.venv/bin/python -m app.cli validate --data-dir data/demo --allow-synthetic
.venv/bin/behave
.venv/bin/python -m app.cli run --config configs/demo.json
```

## 正式資料執行

把符合契約的七個檔案放入 `data/production/`：

```text
prices.csv
constituents.csv
universe.csv
fundamentals.csv
index_prices.csv
benchmark.csv
source_manifest.json
```

再執行：

```bash
.venv/bin/python -m app.cli validate --data-dir data/production --allow-constituent-proxy
.venv/bin/python -m app.cli run --config configs/real_proxy.json
.venv/bin/python scripts/build_in_sample_comparison.py \
  --data-dir data/production --results-dir results/real_proxy_in_sample
```

## 輸出

每次執行會產生：

- `monthly_returns.csv`：各策略逐期毛報酬、換手、成本與淨報酬
- `metrics.csv`：總報酬、年化報酬、年化波動、Sharpe、最大回撤與成本
- `target_weights.csv`：各調倉日目標權重
- `factor_scores.csv`：每次訊號日的因子值與排序
- `regime_signals.csv`：電子指數、MA20、上下閾值與狀態
- `point_in_time_audit.csv`：訊號日、成交日及所用成分股快照日期
- `comparison_metrics.csv`：加入 0050 月底含息參考並標示不同成交邊界

## 回測定義

- 樣本內：2015/01–2022/12。
- 樣本外：2023/01–2026/09；目前可完整結算至 2026/08，且未用樣本外調參。
- 動能：訊號日前 126 個交易日調整後收盤總報酬。
- 反轉：最近 20 個交易日報酬乘以 -1，短期跌幅較大者分數較高。
- 低波動：訊號日前 60 個日報酬標準差，波動較低者分數較高。
- 價值：當時已公布的盈餘殖利率，數值較高者分數較高。
- 品質：當時已公布的 ROE，數值較高者分數較高。
- 合成分數：五個橫斷面百分位分數等權平均。
- 換手率：首次建倉為 100%，其後為新目標與前期漂移後權重差異絕對值的一半。
- 成本：買賣手續費 14.25 bps、賣出證交稅 30 bps、買賣滑價各 5 bps，三者分項輸出；皆為可修改的初始假設。
- 成交價：下一交易日調整後開盤價。
- 暫停交易／事件下市：若邊界日沒有開盤價，採邊界日前 20 日內最近調整後收盤估值，並輸出使用次數與最長落後日數；不使用未來價格。

## 專案導覽

```text
app/                 策略、資料驗證與回測程式
requirements/        使用者故事與接受標準
features/            Gherkin 規格與 behave 步驟
spec/                規格交件索引
pipeline/            資料與回測管線索引
tests/               測試交件索引
docs/adr/             架構決策紀錄
docs/data_contract.md 正式資料欄位與來源要求
ai_log/               三筆 AI 協作紀錄
report/               Canva 連結與 9 頁內容大綱
configs/              模擬與正式設定
MVP_CHECKLIST.md       作業逐項核對
```

## 已知限制

1. 目前只有真實歷史成分變動代理，沒有逐期原始 0050 權重；代理組合採等權，不能宣稱為原 0050。
2. 個股調整後價格能處理多數股利與分割，但資料商的調整方法仍需記錄。
3. 臺灣加權報酬指數是含息 benchmark；不可用臺灣加權價格指數替代。
4. 電子股減碼仍然是全股票配置，不構成真正避險。
5. 2% 遲滯、25% 減碼、N=10 與成本設定都是事前初始值，不是已證明的最適參數。
6. 樣本內有 5 次停牌／事件下市的過期價格估值，最長 15 日；因子 baseline 有 2 次，最長 17 日，均已在結果中揭露。

