from __future__ import annotations

import pandas as pd


def regime_states(
    index_prices: pd.DataFrame,
    signal_dates: list[pd.Timestamp] | pd.Series,
    index_id: str,
    ma_window: int = 20,
    band: float = 0.02,
    initial_state: str = "strong",
) -> pd.DataFrame:
    series = (
        index_prices[index_prices["index_id"] == index_id]
        .sort_values("date")
        .set_index("date")["close"]
    )
    if series.empty:
        raise ValueError(f"index series not found: {index_id}")
    moving_average = series.rolling(ma_window, min_periods=ma_window).mean()
    state = initial_state
    rows = []
    for signal_date in pd.to_datetime(pd.Series(signal_dates)).sort_values():
        available = series.index[series.index <= signal_date]
        if available.empty:
            raise ValueError(f"no index observation available on {signal_date.date()}")
        observed_date = available[-1]
        close = float(series.loc[observed_date])
        ma = moving_average.loc[observed_date]
        if pd.isna(ma):
            raise ValueError(f"insufficient index history for MA{ma_window} on {signal_date.date()}")
        if close < float(ma) * (1.0 - band):
            state = "weak"
        elif close > float(ma) * (1.0 + band):
            state = "strong"
        rows.append(
            {
                "signal_date": signal_date,
                "observed_date": observed_date,
                "close": close,
                "ma": float(ma),
                "lower": float(ma) * (1.0 - band),
                "upper": float(ma) * (1.0 + band),
                "state": state,
            }
        )
    return pd.DataFrame(rows)

