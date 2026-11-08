from __future__ import annotations

import numpy as np
import pandas as pd


def factor_scores(
    prices: pd.DataFrame,
    tickers: list[str],
    as_of_date: pd.Timestamp,
    fundamentals: pd.DataFrame,
    momentum_lookback: int = 126,
    volatility_lookback: int = 60,
) -> pd.DataFrame:
    history = prices[(prices["date"] <= pd.Timestamp(as_of_date)) & prices["ticker"].isin(tickers)]
    pivot = history.pivot(index="date", columns="ticker", values="adj_close").sort_index()
    required = max(momentum_lookback + 1, volatility_lookback + 1)
    if len(pivot) < required:
        raise ValueError(f"insufficient price history on {pd.Timestamp(as_of_date).date()}: need {required} rows")

    latest = pivot.iloc[-1]
    momentum = latest / pivot.iloc[-(momentum_lookback + 1)] - 1.0
    reversal = -(latest / pivot.iloc[-21] - 1.0)
    returns = pivot.pct_change(fill_method=None)
    volatility = returns.iloc[-volatility_lookback:].std(ddof=1) * np.sqrt(252)

    point_in_time = fundamentals.set_index("ticker").reindex(tickers)
    scores = pd.DataFrame(
        {
            "momentum_126d": momentum,
            "reversal_20d": reversal,
            "volatility_60d": volatility,
            "earnings_yield": point_in_time["earnings_yield"],
            "roe": point_in_time["roe"],
        }
    ).dropna()
    scores["momentum_score"] = scores["momentum_126d"].rank(method="average", pct=True)
    scores["reversal_score"] = scores["reversal_20d"].rank(method="average", pct=True)
    scores["low_vol_score"] = scores["volatility_60d"].rank(method="average", pct=True, ascending=False)
    scores["value_score"] = scores["earnings_yield"].rank(method="average", pct=True)
    scores["quality_score"] = scores["roe"].rank(method="average", pct=True)
    scores["combined_score"] = scores[
        ["momentum_score", "reversal_score", "low_vol_score", "value_score", "quality_score"]
    ].mean(axis=1)
    scores.index.name = "ticker"
    return scores.sort_values(["combined_score", "ticker"], ascending=[False, True])

