#!/usr/bin/env python3
"""Fetch real daily benchmark and electronic-sector index observations.

Sources:
* FinMind TaiwanStockTotalReturnIndex for the TAIEX total-return benchmark.
* TWSE monthly report pages for the electronic price index through 2021-01.
* Taiwan Index Plus (TIP) t13 records for the electronic price index from 2021.

The TWSE/TIP overlap is validated before the final daily series is written.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd


START = date(2014, 6, 1)
STUDY_START = date(2015, 1, 1)
END = date(2026, 9, 30)
TWSE_END = date(2021, 1, 31)
TWSE_ENDPOINT = "https://wwwc.twse.com.tw/rwd/zh/TAIEX/EFTRI_HIST"
TIP_ENDPOINT = "https://backend.taiwanindex.com.tw/api/indexes/t13/records"
FINMIND_ENDPOINT = "https://api.finmindtrade.com/api/v4/data"


def _get_json(url: str, params: dict[str, str], attempts: int = 5) -> dict:
    full_url = f"{url}?{urlencode(params)}"
    for attempt in range(attempts):
        request = Request(
            full_url,
            headers={
                "User-Agent": "Mozilla/5.0 (academic research; tw-factor-mvp/1.0)",
                "Accept": "application/json,text/plain,*/*",
            },
        )
        try:
            with urlopen(request, timeout=60) as response:
                body = response.read().decode("utf-8-sig")
            payload = json.loads(body)
            return payload
        except Exception:
            if attempt == attempts - 1:
                raise
            time.sleep(2.0 * (attempt + 1))
    raise RuntimeError("unreachable")


def _number(value: str) -> float:
    return float(str(value).replace(",", "").strip())


def _roc_date(value: str) -> str:
    year, month, day = (int(part) for part in value.strip().split("/"))
    return date(year + 1911, month, day).isoformat()


def _months(start: date, end: date) -> list[str]:
    stamps = pd.date_range(
        pd.Timestamp(start.year, start.month, 1),
        pd.Timestamp(end.year, end.month, 1),
        freq="MS",
    )
    return [stamp.strftime("%Y%m01") for stamp in stamps]


def _fetch_twse_month(month: str, cache_dir: Path) -> list[dict[str, object]]:
    cache_path = cache_dir / f"{month}.json"
    if cache_path.exists():
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    else:
        url = f"{TWSE_ENDPOINT}?{urlencode({'date': month, 'response': 'json'})}"
        last_error = ""
        for attempt in range(5):
            result = subprocess.run(
                [
                    "curl",
                    "-sS",
                    "-L",
                    "--max-time",
                    "45",
                    "-A",
                    "Mozilla/5.0 (academic research; tw-factor-mvp/1.0)",
                    url,
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            try:
                payload = json.loads(result.stdout)
                if payload.get("stat") == "OK":
                    cache_path.write_text(
                        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
                    )
                    break
                last_error = f"TWSE status={payload.get('stat')}"
            except Exception as exc:
                last_error = f"curl={result.returncode}, parse={exc}, stderr={result.stderr[:200]}"
            if attempt < 4:
                time.sleep(2.0 * (attempt + 1))
        else:
            raise RuntimeError(last_error)
    if payload.get("stat") != "OK":
        raise RuntimeError(f"TWSE status for {month}: {payload.get('stat')}")
    return [
        {"date": _roc_date(row[0]), "close": _number(row[1]), "source": "TWSE"}
        for row in payload.get("data", [])
    ]


def fetch_twse_electronic(workers: int, cache_dir: Path) -> pd.DataFrame:
    months = _months(START, TWSE_END)
    cache_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    failures: list[str] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_fetch_twse_month, month, cache_dir): month for month in months
        }
        for count, future in enumerate(as_completed(futures), start=1):
            month = futures[future]
            try:
                rows.extend(future.result())
            except Exception as exc:
                failures.append(f"{month}: {exc}")
            if count % 12 == 0 or count == len(months):
                print(f"TWSE electronic reports {count}/{len(months)}; failures={len(failures)}", flush=True)
    if failures:
        raise RuntimeError("TWSE requests failed: " + " | ".join(failures[:5]))
    return pd.DataFrame(rows).drop_duplicates("date", keep="last").sort_values("date")


def fetch_tip_electronic() -> pd.DataFrame:
    payload = _get_json(
        TIP_ENDPOINT,
        {"start": "2021-01-01", "end": END.isoformat()},
    )
    if payload.get("empty"):
        raise RuntimeError("TIP returned no t13 electronic index history")
    data = payload["data"]
    price_sets = [item for item in data["datasets"] if item.get("value_type") == "price"]
    if len(price_sets) != 1:
        raise RuntimeError(f"expected one TIP price series, got {len(price_sets)}")
    values = price_sets[0]["data"]
    if len(values) != len(data["labels"]):
        raise RuntimeError("TIP labels and price observations have different lengths")
    return pd.DataFrame(
        {
            "date": [pd.Timestamp(value).strftime("%Y-%m-%d") for value in data["labels"]],
            "close": [float(value) for value in values],
            "source": "TIP",
        }
    )


def fetch_finmind_taiex_tr() -> pd.DataFrame:
    payload = _get_json(
        FINMIND_ENDPOINT,
        {
            "dataset": "TaiwanStockTotalReturnIndex",
            "data_id": "TAIEX",
            "start_date": START.isoformat(),
            "end_date": END.isoformat(),
        },
    )
    if payload.get("status") != 200 or payload.get("msg") != "success":
        raise RuntimeError(f"FinMind error: status={payload.get('status')} msg={payload.get('msg')}")
    frame = pd.DataFrame(payload["data"])
    frame = frame.rename(columns={"price": "total_return_index"})
    return frame[["date", "total_return_index"]].sort_values("date")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="data/production")
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()

    output_dir = Path(args.output_dir).resolve()
    raw_dir = output_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    taiex_tr = fetch_finmind_taiex_tr()
    tip = fetch_tip_electronic()
    twse = fetch_twse_electronic(args.workers, raw_dir / "twse_electronic_monthly")

    overlap = twse.merge(tip, on="date", suffixes=("_twse", "_tip"))
    if overlap.empty:
        raise RuntimeError("TWSE and TIP electronic series have no overlap")
    overlap["abs_diff"] = (overlap["close_twse"] - overlap["close_tip"]).abs()
    if overlap["abs_diff"].max() > 0.01:
        sample = overlap.loc[overlap["abs_diff"] > 0.01].head().to_dict("records")
        raise RuntimeError(f"TWSE/TIP electronic values disagree: {sample}")

    electronic = pd.concat(
        [twse[twse["date"] < "2021-01-01"], tip], ignore_index=True
    ).drop_duplicates("date", keep="last").sort_values("date")
    electronic = electronic[electronic["date"] <= END.isoformat()].copy()

    twse.to_csv(raw_dir / "twse_electronic_daily.csv", index=False)
    tip.to_csv(raw_dir / "tip_electronic_daily.csv", index=False)
    taiex_tr.to_csv(raw_dir / "finmind_taiex_total_return_daily.csv", index=False)

    pd.DataFrame(
        {
            "date": electronic["date"],
            "index_id": "TWSE_ELECTRONICS",
            "close": electronic["close"],
        }
    ).to_csv(output_dir / "index_prices.csv", index=False)

    study_benchmark = taiex_tr[taiex_tr["date"] >= STUDY_START.isoformat()]
    pd.DataFrame(
        {
            "date": study_benchmark["date"],
            "index_id": "TAIEX_TR",
            "total_return_index": study_benchmark["total_return_index"],
        }
    ).to_csv(output_dir / "benchmark.csv", index=False)

    monthly_reference_path = output_dir / "electronic_monthly.csv"
    monthly_check = None
    if monthly_reference_path.exists():
        monthly_reference = pd.read_csv(monthly_reference_path)
        month_end = electronic.assign(period=pd.to_datetime(electronic["date"]).dt.to_period("M"))
        month_end = month_end.groupby("period", as_index=False).tail(1)
        monthly_reference["period"] = pd.to_datetime(monthly_reference["date"]).dt.to_period("M")
        check = month_end.merge(
            monthly_reference[["period", "electronic_close"]], on="period", how="inner"
        )
        check["abs_diff"] = (check["close"] - check["electronic_close"]).abs()
        monthly_check = {
            "matched_months": int(len(check)),
            "max_absolute_difference": float(check["abs_diff"].max()),
        }
        if check["abs_diff"].max() > 0.01:
            raise RuntimeError("daily electronic series fails user month-end workbook validation")

    manifest = {
        "downloaded_at": datetime.now().astimezone().isoformat(),
        "study_period": [STUDY_START.isoformat(), END.isoformat()],
        "warmup_start": START.isoformat(),
        "sources": {
            "electronic_2014_2020": TWSE_ENDPOINT,
            "electronic_2021_2026": TIP_ENDPOINT,
            "taiex_total_return": FINMIND_ENDPOINT,
        },
        "rows": {
            "electronic": int(len(electronic)),
            "taiex_total_return": int(len(study_benchmark)),
        },
        "twse_tip_overlap_rows": int(len(overlap)),
        "twse_tip_max_absolute_difference": float(overlap["abs_diff"].max()),
        "user_month_end_validation": monthly_check,
    }
    (raw_dir / "real_indices_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"electronic: {len(electronic)} daily rows ({electronic['date'].min()} to {electronic['date'].max()})")
    print(f"benchmark: {len(study_benchmark)} daily rows ({study_benchmark['date'].min()} to {study_benchmark['date'].max()})")
    print(f"TWSE/TIP overlap max difference: {overlap['abs_diff'].max():.6f}")
    if monthly_check:
        print(f"user month-end validation max difference: {monthly_check['max_absolute_difference']:.6f}")


if __name__ == "__main__":
    main()
