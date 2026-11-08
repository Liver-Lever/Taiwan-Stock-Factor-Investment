#!/usr/bin/env python3
"""Fetch real stock-level data for the Taiwan 50 membership proxy.

Raw closes are converted to a forward return index using FinMind ex-right/
ex-dividend reference prices. The resulting adjusted series is a transparent
research proxy, not a vendor-certified adjusted price series.
"""

from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd


API = "https://api.finmindtrade.com/api/v4/data"
START = "2014-06-01"
END = "2026-09-30"
PER_TICKER_DATASETS = (
    "TaiwanStockPrice",
    "TaiwanStockPER",
    "TaiwanStockDividendResult",
    "TaiwanStockCapitalReductionReferencePrice",
)
ELECTRONIC_CATEGORIES = {
    "半導體業",
    "電腦及週邊設備業",
    "光電業",
    "通信網路業",
    "電子零組件業",
    "電子通路業",
    "資訊服務業",
    "其他電子業",
    "電子工業",
}


def _fetch(params: dict[str, str], attempts: int = 8) -> dict:
    url = f"{API}?{urlencode(params)}"
    last_error = ""
    for attempt in range(attempts):
        request = Request(url, headers={"User-Agent": "tw-factor-mvp/1.0 academic-research"})
        try:
            with urlopen(request, timeout=90) as response:
                payload = json.loads(response.read().decode("utf-8-sig"))
            if payload.get("status") == 200 and payload.get("msg") == "success":
                return payload
            last_error = f"status={payload.get('status')} msg={payload.get('msg')}"
        except Exception as exc:
            last_error = str(exc)
        if attempt < attempts - 1:
            time.sleep(min(60, 3 * (attempt + 1)))
    raise RuntimeError(last_error)


def _cached_ticker(cache_root: Path, dataset: str, ticker: str) -> tuple[str, str, int]:
    cache_dir = cache_root / dataset
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{ticker}.json"
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
    else:
        payload = _fetch(
            {
                "dataset": dataset,
                "data_id": ticker,
                "start_date": START,
                "end_date": END,
            }
        )
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return dataset, ticker, len(payload.get("data", []))


def _load_cached(cache_root: Path, dataset: str, tickers: list[str]) -> pd.DataFrame:
    rows = []
    for ticker in tickers:
        path = cache_root / dataset / f"{ticker}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows.extend(payload.get("data", []))
    return pd.DataFrame(rows)


def _single_dataset(cache_root: Path, dataset: str) -> dict:
    path = cache_root / f"{dataset}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    params = {"dataset": dataset}
    if dataset != "TaiwanStockInfo":
        params.update({"start_date": START, "end_date": END})
    payload = _fetch(params)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return payload


def _event_references(dividends: pd.DataFrame, cache_root: Path, tickers: set[str]) -> pd.DataFrame:
    events = []
    if not dividends.empty:
        for row in dividends.itertuples(index=False):
            reference = getattr(row, "reference_price", None)
            if reference is None or not np.isfinite(float(reference)) or float(reference) <= 0:
                reference = getattr(row, "after_price", None)
            if reference is not None and float(reference) > 0:
                events.append(
                    {
                        "date": row.date,
                        "ticker": str(row.stock_id),
                        "reference_price": float(reference),
                        "event_type": "dividend_or_right",
                    }
                )

    for dataset, after_field in (
        ("TaiwanStockSplitPrice", "after_price"),
        ("TaiwanStockParValueChange", "after_ref_close"),
    ):
        payload = _single_dataset(cache_root, dataset)
        for row in payload.get("data", []):
            ticker = str(row.get("stock_id", ""))
            reference = row.get(after_field)
            if ticker in tickers and reference is not None and float(reference) > 0:
                events.append(
                    {
                        "date": row["date"],
                        "ticker": ticker,
                        "reference_price": float(reference),
                        "event_type": dataset,
                    }
                )
    capital_reductions = _load_cached(
        cache_root, "TaiwanStockCapitalReductionReferencePrice", sorted(tickers)
    )
    if not capital_reductions.empty:
        for row in capital_reductions.itertuples(index=False):
            reference = float(row.PostReductionReferencePrice)
            if reference > 0:
                events.append(
                    {
                        "date": row.date,
                        "ticker": str(row.stock_id),
                        "reference_price": reference,
                        "event_type": "capital_reduction",
                    }
                )
    if not events:
        return pd.DataFrame(columns=["date", "ticker", "reference_price", "event_type"])
    return pd.DataFrame(events).sort_values(["ticker", "date", "event_type"]).drop_duplicates(
        ["date", "ticker"], keep="last"
    )


def _build_adjusted_prices(raw: pd.DataFrame, events: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    raw = raw.rename(
        columns={
            "stock_id": "ticker",
            "Trading_money": "trading_value",
            "Trading_Volume": "volume",
        }
    )
    raw["ticker"] = raw["ticker"].astype(str)
    raw["date"] = pd.to_datetime(raw["date"])
    raw = raw[raw["close"] > 0].copy()
    raw["vwap"] = raw["trading_value"] / raw["volume"].replace(0, np.nan)
    bad_source_rows = raw["vwap"].notna() & (
        (raw["close"] / raw["vwap"] < 0.5) | (raw["close"] / raw["vwap"] > 1.5)
    )
    raw = raw[~bad_source_rows].copy()
    raw.loc[raw["open"] <= 0, "open"] = raw.loc[raw["open"] <= 0, "close"]
    raw = raw.drop_duplicates(["date", "ticker"], keep="last").sort_values(["ticker", "date"])
    if not events.empty:
        events = events.copy()
        events["date"] = pd.to_datetime(events["date"])
        raw = raw.merge(events, on=["date", "ticker"], how="left")
    else:
        raw["reference_price"] = np.nan
        raw["event_type"] = np.nan

    outputs = []
    unresolved = []
    for ticker, group in raw.groupby("ticker", sort=True):
        group = group.sort_values("date").copy()
        group["previous_close"] = group["close"].shift(1)
        group["denominator"] = group["reference_price"].fillna(group["previous_close"])
        group.loc[group["denominator"].isna(), "denominator"] = group["close"]
        group["gross_return_factor"] = group["close"] / group["denominator"]
        group["open_factor"] = group["open"] / group["denominator"]
        suspicious = (
            group["reference_price"].isna()
            & group["previous_close"].notna()
            & ((group["gross_return_factor"] < 0.6) | (group["gross_return_factor"] > 1.6))
        )
        if suspicious.any():
            unresolved.append(
                group.loc[
                    suspicious,
                    ["date", "ticker", "previous_close", "open", "close", "gross_return_factor"],
                ]
            )
        group["adj_close"] = 100.0 * group["gross_return_factor"].cumprod()
        group["previous_adj_close"] = group["adj_close"].shift(1)
        group.loc[group["previous_adj_close"].isna(), "previous_adj_close"] = 100.0
        group["adj_open"] = group["previous_adj_close"] * group["open_factor"]
        outputs.append(
            group[
                [
                    "date",
                    "ticker",
                    "adj_open",
                    "adj_close",
                    "trading_value",
                    "open",
                    "close",
                    "event_type",
                ]
            ]
        )
    unresolved_frame = (
        pd.concat(unresolved, ignore_index=True)
        if unresolved
        else pd.DataFrame(
            columns=["date", "ticker", "previous_close", "open", "close", "gross_return_factor"]
        )
    )
    return pd.concat(outputs, ignore_index=True), unresolved_frame


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default="data/production")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    data_dir = Path(args.data_dir).resolve()
    raw_dir = data_dir / "raw"
    cache_root = raw_dir / "finmind"
    cache_root.mkdir(parents=True, exist_ok=True)

    membership = pd.read_csv(data_dir / "taiwan50_membership_proxy.csv", dtype={"ticker": str})
    tickers = sorted(membership["ticker"].unique().tolist())
    tasks = [(dataset, ticker) for dataset in PER_TICKER_DATASETS for ticker in tickers]
    failures = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(_cached_ticker, cache_root, dataset, ticker): (dataset, ticker)
            for dataset, ticker in tasks
        }
        for count, future in enumerate(as_completed(futures), start=1):
            dataset, ticker = futures[future]
            try:
                future.result()
            except Exception as exc:
                failures.append(f"{dataset}/{ticker}: {exc}")
            if count % 20 == 0 or count == len(tasks):
                print(f"FinMind files {count}/{len(tasks)}; failures={len(failures)}", flush=True)
    if failures:
        (raw_dir / "finmind_stock_panel_failures.json").write_text(
            json.dumps(failures, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        raise RuntimeError(f"{len(failures)} FinMind requests failed; rerun resumes cached files")

    prices_raw = _load_cached(cache_root, "TaiwanStockPrice", tickers)
    per = _load_cached(cache_root, "TaiwanStockPER", tickers)
    dividends = _load_cached(cache_root, "TaiwanStockDividendResult", tickers)
    events = _event_references(dividends, cache_root, set(tickers))
    prices, unresolved = _build_adjusted_prices(prices_raw, events)
    unresolved.to_csv(raw_dir / "unresolved_corporate_action_jumps.csv", index=False)
    prices.to_csv(data_dir / "prices.csv", index=False)

    per = per.rename(columns={"stock_id": "ticker", "date": "available_date"})
    per["ticker"] = per["ticker"].astype(str)
    per["PER"] = pd.to_numeric(per["PER"], errors="coerce")
    per["PBR"] = pd.to_numeric(per["PBR"], errors="coerce")
    per["dividend_yield"] = pd.to_numeric(per["dividend_yield"], errors="coerce")
    per = per[(per["PER"] > 0) & (per["PBR"] > 0)].copy()
    per["earnings_yield"] = 1.0 / per["PER"]
    per["roe"] = per["PBR"] / per["PER"]
    per["book_to_price"] = 1.0 / per["PBR"]
    fundamentals = per[
        [
            "available_date",
            "ticker",
            "earnings_yield",
            "roe",
            "book_to_price",
            "dividend_yield",
            "PER",
            "PBR",
        ]
    ].drop_duplicates(["available_date", "ticker"], keep="last")
    fundamentals.to_csv(data_dir / "fundamentals.csv", index=False)

    info_payload = _single_dataset(cache_root, "TaiwanStockInfo")
    info = pd.DataFrame(info_payload["data"])
    info["stock_id"] = info["stock_id"].astype(str)
    info = info[info["stock_id"].isin(tickers)].copy()
    info = info.sort_values(["stock_id", "date"]).groupby("stock_id", as_index=False).tail(1)
    info_map = info.set_index("stock_id")

    coverage = prices.groupby("ticker")["date"].agg(["min", "max"]).reset_index()
    coverage["listing_date"] = coverage["min"].dt.strftime("%Y-%m-%d")
    coverage["delisting_date"] = coverage["max"].where(
        coverage["max"] < pd.Timestamp(END), pd.NaT
    )
    coverage["delisting_date"] = coverage["delisting_date"].dt.strftime("%Y-%m-%d")
    coverage["market"] = "TWSE"
    coverage["security_type"] = "ordinary_stock"
    coverage[["ticker", "listing_date", "delisting_date", "market", "security_type"]].to_csv(
        data_dir / "universe.csv", index=False
    )

    sector_map = {
        ticker: (
            "electronic"
            if ticker in info_map.index
            and str(info_map.loc[ticker, "industry_category"]) in ELECTRONIC_CATEGORIES
            else "non_electronic"
        )
        for ticker in tickers
    }
    (raw_dir / "sector_classification.json").write_text(
        json.dumps(sector_map, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    manifest = {
        "downloaded_at": datetime.now().astimezone().isoformat(),
        "source": API,
        "source_provider": "FinMind (processed TWSE data)",
        "period": [START, END],
        "tickers": len(tickers),
        "rows": {
            "prices": int(len(prices)),
            "fundamentals": int(len(fundamentals)),
            "corporate_action_events": int(len(events)),
            "unresolved_large_price_jumps": int(len(unresolved)),
        },
        "adjustment_method": "forward return index; ex-right/ex-dividend denominator replaced by public reference price",
        "quality_factor": "implied ROE = PBR / PER using same-day published valuation ratios",
        "limitations": [
            "not a vendor-certified adjusted-price series",
            "large unexplained price jumps are listed separately and must be resolved before empirical claims",
            "membership input is a secondary month-level Taiwan 50 proxy",
        ],
    }
    (raw_dir / "finmind_stock_panel_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"prices: {len(prices)} rows; fundamentals: {len(fundamentals)} rows")
    print(f"unresolved large jumps: {len(unresolved)}")


if __name__ == "__main__":
    main()
