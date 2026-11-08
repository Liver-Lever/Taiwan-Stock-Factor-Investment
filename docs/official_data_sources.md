# 正式資料來源指引

以下連結用來建立正式資料集。下載時仍須在 `source_manifest.json` 記錄實際下載日期、檔案版本與授權。

## 本版實際使用

- 電子類現貨指數：TWSE 官方月報端點（至 2020）＋臺灣指數公司歷史端點（2021 起），重疊區最大差異為 0。
- 臺灣加權報酬指數：FinMind 處理的公開市場資料。
- 個股日行情、PER／PBR、股利與減資：FinMind；2311 因端點額度限制，改由 TWSE `STOCK_DAY`、`BWIBBU`、`TWT49U` 官方端點補齊。
- 臺灣 50 成分時間線：Wikipedia 公開異動表作為次級來源；2016/11 華亞科事件與 2018/04 日月光／矽品事件另以臺灣指數公司公告修正。
- 0050 與電子指數月底資料：使用者提供工作簿；電子月底值與日資料逐月核對最大差異為 0。

以上來源與下載時間均記錄在 `data/production/raw/*manifest.json`。成分時間線仍是月級代理，並非正式授權的逐期 0050 權重檔。

## 電子類股現貨指數

- [TWSE 指數資訊入口](https://www.twse.com.tw/zh/indices/indices/series.html)
- [TWSE 每日市場報表](https://www.twse.com.tw/exchangeReport/MI_INDEX?response=html&type=ALLBUT0999)
- [TWSE OpenAPI](https://openapi.twse.com.tw/)

研究訊號應選「電子類指數」價格序列。若改用電子類報酬指數，必須另開策略版本，不能與原規格混在一起。

## 臺灣加權報酬指數

- [臺灣指數公司：發行量加權股價指數](https://taiwanindex.com.tw/indexes/t00)
- [臺灣指數公司指數看板](https://taiwanindex.com.tw/indexes/board/twse)

`benchmark.csv` 必須填入含息的「發行量加權股價報酬指數」，不能只使用 TAIEX 價格指數。

## 0050 成分與權重

- [臺灣指數公司：臺灣50指數](https://taiwanindex.com.tw/indexes/TW50)
- [元大台灣50 基本資訊](https://www.yuantaetfs.com/product/detail/0050/Basic_information)
- [TWSE 網路資訊商店](https://www.twse.com.tw/zh/products/dataeshop.html)

公開頁面適合核對定期審核與生效日。若要得到 2015–2022 每個調倉點的可驗證權重，可能需要授權資料、校內資料庫，或逐期保存的基金持股檔。不可用 2026 年成分與權重回推。

## 個股價格與公司行動

- [TWSE OpenAPI](https://openapi.twse.com.tw/)
- [TWSE 歷史指數資料入口](https://www.twse.com.tw/zh/indices/taiex/mi-5min-hist.html)

本專案需要調整後開盤與收盤價。若來源只提供未調整行情，必須另取得除權息、分割與減資資料建立調整因子；不可把未調整價格直接填入 `adj_open`／`adj_close`。

