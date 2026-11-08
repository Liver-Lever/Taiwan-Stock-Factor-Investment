#!/usr/bin/env python3
"""Fetch official TWSE history for legacy ASE code 2311 and merge it into the bundle."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd


BASE = "https://www.twse.com.tw/exchangeReport"
TICKER = "2311"
START_MONTH = pd.Period("2014-06", freq="M")
END_MONTH = pd.Period("2018-04", freq="M")


def _roc_date(value: str) -> pd.Timestamp:
    numbers = [int(item) for item in re.findall(r"\d+", value)]
    if len(numbers) < 3:
        raise ValueError(f"unparseable ROC date: {value}")
    return pd.Timestamp(numbers[0] + 1911, numbers[1], numbers[2])


def _number(value: object) -> float:
    text = str(value).replace(",", "").strip()
    if text in {"", "-", "--", "---"}:
        return np.nan
    return float(text)


def _download(url: str, attempts: int = 5) -> dict:
    last_error = ""
    for attempt in range(attempts):
        try:
            request = Request(url, headers={"User-Agent": "tw-factor-mvp/1.0 academic-research"})
            try:
                with urlopen(request, timeout=45) as response:
                    body = response.read()
            except Exception as urllib_error:
                if "redirect" not in str(urllib_error).lower():
                    raise
                body = subprocess.run(
                    ["curl", "-fsSL", "--max-time", "45", url],
                    check=True,
                    capture_output=True,
                ).stdout
            payload = json.loads(body.decode("utf-8-sig"))
            if payload.get("stat") == "OK":
                return payload
            last_error = str(payload.get("stat"))
        except Exception as exc:
            last_error = str(exc)
        time.sleep(1 + attempt)
    raise RuntimeError(f"TWSE request failed: {last_error}")


def _month_url(dataset: str, month: pd.Period) -> str:
    params = {"response": "json", "date": month.start_time.strftime("%Y%m%d"), "stockNo": TICKER}
    return f"{BASE}/{dataset}?{urlencode(params)}"


def _cached_month(raw_root: Path, dataset: str, month: pd.Period) -> Path:
    directory = raw_root / dataset
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{month.strftime('%Y%m')}_{TICKER}.json"
    if not path.exists():
        payload = _download(_month_url(dataset, month))
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        time.sleep(0.25)
    return path


def _price_rows(paths: list[Path]) -> pd.DataFrame:
    rows = []
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        for row in payload["data"]:
            rows.append(
                {
                    "date": _roc_date(row[0]),
                    "ticker": TICKER,
                    "trading_value": _number(row[2]),
                    "open": _number(row[3]),
                    "close": _number(row[6]),
                }
            )
    return pd.DataFrame(rows).dropna(subset=["open", "close"]).sort_values("date")


def _fundamental_rows(paths: list[Path]) -> pd.DataFrame:
    rows = []
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        for row in payload["data"]:
            per, dividend_yield, pbr = (_number(row[1]), _number(row[2]), _number(row[3]))
            if per > 0 and pbr > 0:
                rows.append(
                    {
                        "available_date": _roc_date(row[0]),
                        "ticker": TICKER,
                        "earnings_yield": 1.0 / per,
                        "roe": pbr / per,
                        "book_to_price": 1.0 / pbr,
                        "dividend_yield": dividend_yield,
                        "PER": per,
                        "PBR": pbr,
                    }
                )
    return pd.DataFrame(rows).sort_values("available_date")


def _exright_events(raw_root: Path) -> pd.DataFrame:
    path = raw_root / "TWT49U_20140601_20180430.json"
    if not path.exists():
        params = {"response": "json", "startDate": "20140601", "endDate": "20180430"}
        payload = _download(f"{BASE}/TWT49U?{urlencode(params)}")
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for row in payload["data"]:
        if str(row[1]).strip() == TICKER:
            rows.append(
                {
                    "date": _roc_date(row[0]),
                    "reference_price": _number(row[4]),
                    "event_type": "twse_ex_right_or_dividend",
                }
            )
    return pd.DataFrame(rows)


def _adjust(prices: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    frame = prices.merge(events, on="date", how="left")
    frame["previous_close"] = frame["close"].shift(1)
    frame["denominator"] = frame["reference_price"].fillna(frame["previous_close"])
    frame.loc[frame["denominator"].isna(), "denominator"] = frame["close"]
    frame["gross_return_factor"] = frame["close"] / frame["denominator"]
    frame["open_factor"] = frame["open"] / frame["denominator"]
    frame["adj_close"] = 100.0 * frame["gross_return_factor"].cumprod()
    previous_adjusted = frame["adj_close"].shift(1).fillna(100.0)
    frame["adj_open"] = previous_adjusted * frame["open_factor"]
    return frame[
        ["date", "ticker", "adj_open", "adj_close", "trading_value", "open", "close", "event_type"]
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default="data/production")
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()

    data_dir = Path(args.data_dir).resolve()
    raw_root = data_dir / "raw" / "twse_legacy_2311"
    raw_root.mkdir(parents=True, exist_ok=True)
    months = list(pd.period_range(START_MONTH, END_MONTH, freq="M"))
    paths: dict[str, list[Path]] = {"STOCK_DAY": [], "BWIBBU": []}
    jobs = [(dataset, month) for dataset in paths for month in months]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(_cached_month, raw_root, dataset, month): (dataset, month)
            for dataset, month in jobs
        }
        for count, future in enumerate(as_completed(futures), start=1):
            dataset, _ = futures[future]
            paths[dataset].append(future.result())
            if count % 20 == 0 or count == len(jobs):
                print(f"TWSE legacy files {count}/{len(jobs)}", flush=True)

    raw_prices = _price_rows(paths["STOCK_DAY"])
    fundamentals_2311 = _fundamental_rows(paths["BWIBBU"])
    events = _exright_events(raw_root)
    prices_2311 = _adjust(raw_prices, events)

    prices = pd.read_csv(data_dir / "prices.csv", dtype={"ticker": str}, parse_dates=["date"])
    prices = pd.concat([prices[prices["ticker"] != TICKER], prices_2311], ignore_index=True)
    prices.sort_values(["ticker", "date"]).to_csv(data_dir / "prices.csv", index=False)

    fundamentals = pd.read_csv(
        data_dir / "fundamentals.csv", dtype={"ticker": str}, parse_dates=["available_date"]
    )
    fundamentals = pd.concat(
        [fundamentals[fundamentals["ticker"] != TICKER], fundamentals_2311], ignore_index=True
    )
    fundamentals.sort_values(["ticker", "available_date"]).to_csv(
        data_dir / "fundamentals.csv", index=False
    )

    universe = pd.read_csv(data_dir / "universe.csv", dtype={"ticker": str})
    universe = universe[universe["ticker"] != TICKER]
    universe.loc[len(universe)] = {
        "ticker": TICKER,
        "listing_date": raw_prices["date"].min().strftime("%Y-%m-%d"),
        "delisting_date": "2018-04-30",
        "market": "TWSE",
        "security_type": "ordinary_stock",
    }
    universe.sort_values("ticker").to_csv(data_dir / "universe.csv", index=False)

    sector_path = data_dir / "raw" / "sector_classification.json"
    sector_map = json.loads(sector_path.read_text(encoding="utf-8"))
    sector_map[TICKER] = "electronic"
    sector_path.write_text(json.dumps(sector_map, ensure_ascii=False, indent=2), encoding="utf-8")

    manifest = {
        "downloaded_at": datetime.now().astimezone().isoformat(),
        "source": BASE,
        "ticker": TICKER,
        "datasets": ["STOCK_DAY", "BWIBBU", "TWT49U"],
        "period": [str(raw_prices["date"].min().date()), str(raw_prices["date"].max().date())],
        "rows": {"prices": len(prices_2311), "fundamentals": len(fundamentals_2311), "events": len(events)},
        "adjustment_method": "official ex-right/ex-dividend reference-price forward return index",
    }
    (data_dir / "raw" / "twse_legacy_2311_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        f"2311 merged: {len(prices_2311)} price rows, "
        f"{len(fundamentals_2311)} valuation rows, {len(events)} corporate-action events"
    )


if __name__ == "__main__":
    main()
