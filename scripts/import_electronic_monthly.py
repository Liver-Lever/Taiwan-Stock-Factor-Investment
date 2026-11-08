#!/usr/bin/env python3
"""Import the user-provided electronic-sector month-end workbook unchanged."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook


REQUIRED_HEADERS = {
    "年月日",
    "未調整收盤價(元)",
    "外資買賣超(張)",
    "投信買賣超(張)",
    "自營買賣超(張)",
    "合計買賣超(張)",
    "外資成交比重",
    "法人成交比重",
    "信用交易比重",
    "融資餘額(張)",
    "融券餘額(張)",
    "券資比",
}


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
    headers = [cell.value for cell in sheet[2]]
    missing_headers = REQUIRED_HEADERS.difference(headers)
    if missing_headers:
        raise ValueError(f"missing required headers: {sorted(missing_headers)}")

    rows = list(sheet.iter_rows(min_row=3, values_only=True))
    source_frame = pd.DataFrame(rows, columns=headers)
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(source_frame["年月日"], errors="raise"),
            "electronic_close": pd.to_numeric(source_frame["未調整收盤價(元)"], errors="raise"),
            "foreign_net_lots": pd.to_numeric(source_frame["外資買賣超(張)"], errors="coerce"),
            "investment_trust_net_lots": pd.to_numeric(source_frame["投信買賣超(張)"], errors="coerce"),
            "dealer_net_lots": pd.to_numeric(source_frame["自營買賣超(張)"], errors="coerce"),
            "institutional_net_lots": pd.to_numeric(source_frame["合計買賣超(張)"], errors="coerce"),
            "foreign_turnover_pct": pd.to_numeric(source_frame["外資成交比重"], errors="coerce"),
            "institutional_turnover_pct": pd.to_numeric(source_frame["法人成交比重"], errors="coerce"),
            "margin_turnover_pct": pd.to_numeric(source_frame["信用交易比重"], errors="coerce"),
            "margin_balance_lots": pd.to_numeric(source_frame["融資餘額(張)"], errors="coerce"),
            "short_balance_lots": pd.to_numeric(source_frame["融券餘額(張)"], errors="coerce"),
            "short_margin_ratio_pct": pd.to_numeric(source_frame["券資比"], errors="coerce"),
        }
    ).sort_values("date").reset_index(drop=True)

    if frame["date"].duplicated().any():
        raise ValueError("duplicate dates in source workbook")
    expected_months = pd.period_range(frame["date"].min(), frame["date"].max(), freq="M")
    actual_months = pd.PeriodIndex(frame["date"], freq="M")
    missing_months = expected_months.difference(actual_months)
    if len(missing_months):
        raise ValueError(f"missing months: {list(map(str, missing_months))}")
    if frame["electronic_close"].isna().any():
        raise ValueError("missing electronic index closes")

    frame["month_end_close_return"] = frame["electronic_close"].pct_change()
    frame["date"] = frame["date"].dt.strftime("%Y-%m-%d")
    output = output_dir / "electronic_monthly.csv"
    frame.to_csv(output, index=False)

    manifest = {
        "imported_at": datetime.now().astimezone().isoformat(),
        "source_kind": "user_provided_workbook",
        "source_filename": source.name,
        "source_sha256": sha256(source),
        "rows": len(frame),
        "first_date": frame["date"].iloc[0],
        "last_date": frame["date"].iloc[-1],
        "missing_months": [],
        "interpretation": {
            "electronic_close": "TWSE electronic-sector spot index month-end close",
            "month_end_close_return": "calculated from consecutive month-end closes",
            "ma20_limit": "monthly observations cannot calculate a 20-trading-day moving average; daily official data is still required",
            "flow_fields": "monthly/observation-period fields retained as supplied and not used as stock-level point-in-time factors",
        },
    }
    (raw_dir / "electronic_monthly_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"imported {len(frame)} month-end rows: {output}")
    print(f"range: {frame['date'].iloc[0]} to {frame['date'].iloc[-1]}")


if __name__ == "__main__":
    main()
