# 正式資料契約

## `prices.csv`

| 欄位 | 說明 |
|---|---|
| `date` | 交易日 |
| `ticker` | 股票代碼 |
| `adj_open` | 含公司行動調整因子的開盤價 |
| `adj_close` | 含公司行動調整因子的收盤價 |
| `trading_value` | 當日成交金額，用於流動性篩選 |

資料至少需涵蓋 2014 年的因子暖機期，並延伸至 2023 年 1 月下一次調倉日，才能完整評估 2015/01–2022/12。

## `universe.csv`

`ticker,listing_date,delisting_date,market,security_type`。`market` 為 `TWSE` 或 `TPEX`，`security_type` 為 `ordinary_stock`。系統依訊號日排除尚未上市或已下市股票。

## `fundamentals.csv`

| 欄位 | 說明 |
|---|---|
| `available_date` | 市場當時可取得資料的日期，不是財報期末日 |
| `ticker` | 股票代碼 |
| `market_cap` | 當時市值（可選；本版來源未提供時不作為必要欄位） |
| `earnings_yield` | 盈餘殖利率，價值因子 |
| `roe` | 股東權益報酬率，品質因子 |

每個訊號日只取 `available_date` 不晚於訊號日的最新資料。本版以同日公開 PER、PBR 推導 `earnings_yield=1/PER` 與品質代理 `roe=PBR/PER`。

## `constituents.csv`

| 欄位 | 說明 |
|---|---|
| `effective_date` | 成分與權重開始生效日 |
| `available_date` | 研究者在當時可取得完整快照的日期 |
| `ticker` | 股票代碼 |
| `weight` | 該快照的 0050 權重，整組合計 1 |
| `sector` | `electronic` 或 `non_electronic` |

`available_date` 必須來自公告或檔案時間戳，不可事後用 `effective_date` 代替。若只有季成分名單而沒有可驗證的歷史權重，必須在報告中把原 0050 組合標成代理組合。

`taiwan50_membership_proxy.csv` 僅是依公開成分變動表回推的月級代理名單；`point_in_time_constituents=false`，不得改名或宣稱為精確的歷史 0050 持股。`taiwan50_weight_snapshot_2025_09.csv` 只有單一時點權重，不能向前填補成 2015 年起的正式權重。

## `index_prices.csv`

`date,index_id,close`。電子訊號優先使用臺灣證券交易所電子類股現貨指數，`index_id` 設為 `TWSE_ELECTRONICS`。

## `benchmark.csv`

`date,index_id,total_return_index`。作業正式 benchmark 為臺灣加權報酬指數（含息），`index_id` 設為 `TAIEX_TR`。不可拿價格指數代替報酬指數。

## `0050_monthly.csv`

使用者提供的 0050 月底觀測資料，涵蓋 2015/01–2026/09。`source_daily_return_pct` 是月底該交易日的單日報酬，不能當成月報酬；研究使用 `month_end_close_return`，由相鄰月底收盤價重新計算。此檔可核對 0050 的月底走勢，但不能取代逐期成分股與權重。

## `electronic_monthly.csv`

使用者提供的臺灣證交所電子類現貨指數月底資料，涵蓋 2015/01–2026/09，並保留法人交易與融資融券欄位。`month_end_close_return` 由相鄰月底收盤重新計算。因每月只有一筆，此檔不能計算 20 個交易日均線；正式訊號仍必須使用 `index_prices.csv` 的每日 `TWSE_ELECTRONICS` 資料。

## `source_manifest.json`

正式資料至少包含：

```json
{
  "data_kind": "production",
  "point_in_time_constituents": true,
  "sources": [
    "各檔案來源、下載日期、版本與授權"
  ]
}
```

正式模式會拒絕 `synthetic_fixture`，也會拒絕沒有 point-in-time 聲明或來源紀錄的資料集。

