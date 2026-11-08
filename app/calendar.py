from __future__ import annotations

import pandas as pd


def rebalance_events(trading_dates: pd.Series | pd.DatetimeIndex) -> pd.DataFrame:
    dates = pd.DatetimeIndex(pd.to_datetime(pd.Series(trading_dates).drop_duplicates())).sort_values()
    if len(dates) < 2:
        raise ValueError("at least two trading dates are required")
    month_ends = pd.Series(dates, index=dates).groupby(dates.to_period("M")).max().tolist()
    rows = []
    for signal_date in month_ends:
        position = dates.searchsorted(signal_date, side="right")
        if position < len(dates):
            execution_date = dates[position]
            if execution_date <= signal_date:
                raise AssertionError("execution must occur after the signal close")
            rows.append({"signal_date": signal_date, "execution_date": execution_date})
    return pd.DataFrame(rows)


def evaluation_events(
    trading_dates: pd.Series | pd.DatetimeIndex,
    start_date: str | pd.Timestamp,
    end_date: str | pd.Timestamp,
) -> pd.DataFrame:
    events = rebalance_events(trading_dates)
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    chosen = events[(events["execution_date"] >= start) & (events["execution_date"] <= end)].copy()
    if chosen.empty:
        raise ValueError("no rebalance events fall inside the evaluation window")
    final_execution = events[events["execution_date"] > chosen["execution_date"].max()].head(1)
    if final_execution.empty:
        raise ValueError("prices must extend through the next rebalance after end_date")
    return pd.concat([chosen, final_execution], ignore_index=True)

