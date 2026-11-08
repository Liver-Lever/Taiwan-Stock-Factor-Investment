#!/usr/bin/env python3
"""Build a daily 0050 total-return proxy from official TWSE prices and reference prices."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode

import numpy as np
import pandas as pd


BASE = "https://www.twse.com.tw/exchangeReport"
TICKER = "0050"
INDEX_ID = "0050_TR_OFFICIAL_PROXY"


def _roc_date(value: str) -> pd.Timestamp:
    parts = [int(item) for item in re.findall(r"\d+", value)]
    return pd.Timestamp(parts[0] + 1911, parts[1], parts[2])


def _number(value: object) -> float:
    text = str(value).replace(",", "").strip()
    return np.nan if text in {"", "-", "--", "---"} else float(text)


def _curl_json(url: str) -> dict:
    last_error = ""
    for attempt in range(5):
        try:
            body = subprocess.run(
                ["curl", "-fsSL", "--max-time", "60", url], check=True, capture_output=True
            ).stdout
            payload = json.loads(body.decode("utf-8-sig"))
            if payload.get("stat") == "OK":
                return payload
            last_error = str(payload.get("stat"))
        except Exception as exc:
            last_error = str(exc)
        time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"TWSE request failed after retries: {last_error}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default="data/production")
    args = parser.parse_args()
    data_dir = Path(args.data_dir).resolve()
    raw_root = data_dir / "raw" / "twse_0050"
    price_root = raw_root / "STOCK_DAY"
    price_root.mkdir(parents=True, exist_ok=True)

    months = list(pd.period_range("2014-12", "2026-10", freq="M"))
    for count, month in enumerate(months, start=1):
        path = price_root / f"{month.strftime('%Y%m')}_{TICKER}.json"
        if not path.exists():
            params = {
                "response": "json",
                "date": month.start_time.strftime("%Y%m%d"),
                "stockNo": TICKER,
            }
            path.write_text(
                json.dumps(_curl_json(f"{BASE}/STOCK_DAY?{urlencode(params)}"), ensure_ascii=False),
                encoding="utf-8",
            )
            time.sleep(0.25)
        if count % 24 == 0 or count == len(months):
            print(f"0050 official month files {count}/{len(months)}", flush=True)

    exright_path = raw_root / "TWT49U_20141201_20261031.json"
    if not exright_path.exists():
        params = {"response": "json", "startDate": "20141201", "endDate": "20261031"}
        exright_path.write_text(
            json.dumps(_curl_json(f"{BASE}/TWT49U?{urlencode(params)}"), ensure_ascii=False),
            encoding="utf-8",
        )

    prices = []
    for path in sorted(price_root.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for row in payload["data"]:
            prices.append(
                {
                    "date": _roc_date(row[0]),
                    "open": _number(row[3]),
                    "close": _number(row[6]),
                }
            )
    frame = pd.DataFrame(prices).dropna().drop_duplicates("date").sort_values("date")

    events = []
    payload = json.loads(exright_path.read_text(encoding="utf-8"))
    for row in payload["data"]:
        if str(row[1]).strip() == TICKER:
            events.append({"date": _roc_date(row[0]), "reference_price": _number(row[4])})
    event_frame = pd.DataFrame(events)
    frame = frame.merge(event_frame, on="date", how="left")
    frame["previous_close"] = frame["close"].shift(1)
    frame["denominator"] = frame["reference_price"].fillna(frame["previous_close"])
    frame.loc[frame["denominator"].isna(), "denominator"] = frame["close"]
    frame["gross_factor"] = frame["close"] / frame["denominator"]
    frame["total_return_index"] = 100.0 * frame["gross_factor"].cumprod()
    output = frame[["date", "total_return_index"]].assign(index_id=INDEX_ID)
    output = output[["date", "index_id", "total_return_index"]]
    output.to_csv(data_dir / "0050_total_return_daily.csv", index=False)

    benchmark = pd.read_csv(data_dir / "benchmark.csv", parse_dates=["date"])
    benchmark = pd.concat(
        [benchmark[benchmark["index_id"] != INDEX_ID], output], ignore_index=True
    ).sort_values(["index_id", "date"])
    benchmark.to_csv(data_dir / "benchmark.csv", index=False)

    user_monthly = pd.read_csv(data_dir / "0050_monthly.csv", parse_dates=["date"])
    official_monthly = frame.set_index("date")["total_return_index"].resample("ME").last().dropna()
    comparison = user_monthly[["date", "close"]].merge(
        official_monthly.rename("official_total_return_index"),
        left_on=user_monthly["date"].dt.to_period("M"),
        right_on=official_monthly.index.to_period("M"),
        how="left",
    )
    comparison = comparison.drop(columns=["key_0"])
    comparison["user_monthly_return"] = comparison["close"].pct_change()
    comparison["official_total_return"] = comparison["official_total_return_index"].pct_change()
    comparison.to_csv(data_dir / "0050_monthly_validation.csv", index=False)

    manifest = {
        "downloaded_at": datetime.now().astimezone().isoformat(),
        "source": BASE,
        "ticker": TICKER,
        "index_id": INDEX_ID,
        "period": [str(frame["date"].min().date()), str(frame["date"].max().date())],
        "rows": len(output),
        "corporate_action_events": len(events),
        "method": "forward total-return index using official TWSE ex-right/ex-dividend reference prices",
        "limitation": "research proxy; not the fund issuer's published NAV total-return series",
    }
    (data_dir / "raw" / "twse_0050_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"0050 total-return proxy: {len(output)} daily rows, {len(events)} events")


if __name__ == "__main__":
    main()
