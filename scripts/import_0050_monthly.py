#!/usr/bin/env python3
"""Import the user-provided 0050 month-end workbook without altering it."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook


EXPECTED_HEADERS = (
    "年月日",
    "開盤價(元)",
    "最高價(元)",
    "最低價(元)",
    "收盤價(元)",
    "成交量(千股)",
    "成交值(千元)",
    "報酬率％",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_xlsx")
    parser.add_argument("--output-dir", default="data/production")
    args = parser.parse_args()

    source = Path(args.input_xlsx).expanduser().resolve()
    output_dir = Path(args.output_dir).resolve()
    raw_dir = output_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    workbook = load_workbook(source, read_only=True, data_only=True)
    if len(workbook.sheetnames) != 1:
        raise ValueError(f"expected one worksheet, got {workbook.sheetnames}")
    sheet = workbook[workbook.sheetnames[0]]
    headers = tuple(cell.value for cell in sheet[2])
    if headers != EXPECTED_HEADERS:
        raise ValueError(f"unexpected headers: {headers}")

    rows = list(sheet.iter_rows(min_row=3, values_only=True))
    frame = pd.DataFrame(
        rows,
        columns=[
            "date",
            "open",
            "high",
            "low",
            "close",
            "volume_thousand_shares",
            "trading_value_thousand_twd",
            "source_daily_return_pct",
        ],
    )
    frame["date"] = pd.to_datetime(frame["date"], errors="raise")
    frame = frame.sort_values("date").reset_index(drop=True)
    if frame["date"].duplicated().any():
        raise ValueError("duplicate dates in source workbook")
    expected_months = pd.period_range(frame["date"].min(), frame["date"].max(), freq="M")
    actual_months = pd.PeriodIndex(frame["date"], freq="M")
    missing = expected_months.difference(actual_months)
    if len(missing):
        raise ValueError(f"missing months: {list(map(str, missing))}")

    frame["volume_shares"] = frame.pop("volume_thousand_shares") * 1000
    frame["trading_value_twd"] = frame.pop("trading_value_thousand_twd") * 1000
    frame["month_end_close_return"] = frame["close"].pct_change()
    frame["date"] = frame["date"].dt.strftime("%Y-%m-%d")
    ordered = frame[
        [
            "date",
            "open",
            "high",
            "low",
            "close",
            "volume_shares",
            "trading_value_twd",
            "source_daily_return_pct",
            "month_end_close_return",
        ]
    ]
    output = output_dir / "0050_monthly.csv"
    ordered.to_csv(output, index=False)

    manifest = {
        "imported_at": datetime.now().astimezone().isoformat(),
        "source_kind": "user_provided_workbook",
        "source_filename": source.name,
        "source_sha256": sha256(source),
        "rows": len(ordered),
        "first_date": ordered["date"].iloc[0],
        "last_date": ordered["date"].iloc[-1],
        "missing_months": [],
        "interpretation": {
            "prices": "month-end observations; historical prices appear split-adjusted",
            "source_daily_return_pct": "return for the observation trading day, not monthly return",
            "month_end_close_return": "calculated from consecutive month-end closes",
        },
    }
    (raw_dir / "0050_monthly_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"imported {len(ordered)} month-end rows: {output}")
    print(f"range: {ordered['date'].iloc[0]} to {ordered['date'].iloc[-1]}")


if __name__ == "__main__":
    main()
