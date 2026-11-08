#!/usr/bin/env python3
"""Add the user-provided 0050 month-end total-return reference to the result report."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


REFERENCE_NAME = "0050_user_month_end_total_return_reference"


def _reference_metrics(returns: pd.DataFrame) -> pd.DataFrame:
    values = returns["net_return"].astype(float)
    equity = (1.0 + values).cumprod()
    years = len(values) / 12.0
    annual_volatility = float(values.std(ddof=1) * np.sqrt(12))
    return pd.DataFrame(
        [
            {
                "strategy": REFERENCE_NAME,
                "periods": len(values),
                "total_return": float(equity.iloc[-1] - 1.0),
                "cagr": float(equity.iloc[-1] ** (1.0 / years) - 1.0),
                "annual_volatility": annual_volatility,
                "sharpe_rf0": float(values.mean() * 12 / annual_volatility),
                "max_drawdown": float((equity / equity.cummax() - 1.0).min()),
                "average_turnover": 0.0,
                "total_transaction_cost": 0.0,
                "total_commission_cost": 0.0,
                "total_tax_cost": 0.0,
                "total_slippage_cost": 0.0,
                "stale_price_uses": 0,
                "max_price_staleness_days": 0,
            }
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default="data/production")
    parser.add_argument("--results-dir", default="results/real_proxy_in_sample")
    parser.add_argument("--start", default="2015-01-01")
    parser.add_argument("--end", default="2022-12-31")
    args = parser.parse_args()

    data_dir = Path(args.data_dir).resolve()
    results_dir = Path(args.results_dir).resolve()
    monthly = pd.read_csv(data_dir / "0050_monthly.csv", parse_dates=["date"])
    monthly = monthly[monthly["date"].between(args.start, args.end)].sort_values("date")
    monthly["period_start"] = monthly["date"].shift(1)
    monthly = monthly.dropna(subset=["month_end_close_return", "period_start"])
    reference = pd.DataFrame(
        {
            "strategy": REFERENCE_NAME,
            "period_start": monthly["period_start"],
            "period_end": monthly["date"],
            "gross_return": monthly["month_end_close_return"],
            "turnover": 0.0,
            "transaction_cost": 0.0,
            "commission_cost": 0.0,
            "tax_cost": 0.0,
            "slippage_cost": 0.0,
            "net_return": monthly["month_end_close_return"],
            "stale_start_price_count": 0,
            "stale_end_price_count": 0,
            "max_price_staleness_days": 0,
        }
    )
    reference.to_csv(results_dir / "0050_reference_monthly_returns.csv", index=False)

    metrics = pd.read_csv(results_dir / "metrics.csv")
    metrics["period_basis"] = "next-trading-day execution boundary"
    metrics["comparison_note"] = "aligned strategy and benchmark periods"
    reference_metrics = _reference_metrics(reference)
    reference_metrics["period_basis"] = "calendar month-end adjusted close"
    reference_metrics["comparison_note"] = (
        "reference only; user workbook matches official TWSE total-return reconstruction "
        "in the validated 2015-2018 overlap, but execution boundaries differ"
    )
    comparison = pd.concat([metrics, reference_metrics], ignore_index=True)
    comparison.to_csv(results_dir / "comparison_metrics.csv", index=False)
    print(comparison.to_string(index=False))


if __name__ == "__main__":
    main()
