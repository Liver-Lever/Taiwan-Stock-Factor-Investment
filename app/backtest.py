from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class BacktestResult:
    returns: pd.DataFrame
    weights: pd.DataFrame


def _price_at(
    open_pivot: pd.DataFrame,
    close_pivot: pd.DataFrame,
    date: pd.Timestamp,
    tickers: pd.Index,
    max_staleness_days: int = 20,
) -> tuple[pd.Series, pd.Series]:
    if date not in open_pivot.index:
        raise ValueError(f"missing execution-date prices on {pd.Timestamp(date).date()}")
    date = pd.Timestamp(date)
    values = open_pivot.loc[date].reindex(tickers).copy()
    staleness = pd.Series(0, index=tickers, dtype=int)
    for ticker in values[values.isna()].index:
        history = close_pivot.loc[close_pivot.index <= date, ticker].dropna()
        if history.empty:
            raise ValueError(f"no historical adjusted price for {ticker} on {date.date()}")
        observed_date = pd.Timestamp(history.index[-1])
        lag = int((date - observed_date).days)
        if lag > max_staleness_days:
            raise ValueError(
                f"stale adjusted close for {ticker} on {date.date()}: "
                f"last observation {observed_date.date()} ({lag} days)"
            )
        values.loc[ticker] = float(history.iloc[-1])
        staleness.loc[ticker] = lag
    return values.astype(float), staleness


def run_target_backtest(
    prices: pd.DataFrame,
    targets: dict[pd.Timestamp, pd.Series],
    ordered_execution_dates: list[pd.Timestamp],
    commission_bps: float,
    tax_bps: float,
    slippage_bps: float,
    strategy_name: str,
) -> BacktestResult:
    open_pivot = prices.pivot(index="date", columns="ticker", values="adj_open").sort_index()
    close_field = "adj_close" if "adj_close" in prices.columns else "adj_open"
    close_pivot = prices.pivot(index="date", columns="ticker", values=close_field).sort_index()
    prior_end_weights: pd.Series | None = None
    return_rows = []
    weight_rows = []

    for start, end in zip(ordered_execution_dates[:-1], ordered_execution_dates[1:]):
        target = targets[pd.Timestamp(start)].astype(float)
        target = target[target > 0]
        target = target / target.sum()

        if prior_end_weights is None:
            turnover = 1.0
            buy_notional = 1.0
            sell_notional = 0.0
        else:
            names = target.index.union(prior_end_weights.index)
            differences = target.reindex(names, fill_value=0) - prior_end_weights.reindex(names, fill_value=0)
            buy_notional = float(differences.clip(lower=0).sum())
            sell_notional = float((-differences.clip(upper=0)).sum())
            turnover = 0.5 * (buy_notional + sell_notional)

        start_prices, start_staleness = _price_at(
            open_pivot, close_pivot, pd.Timestamp(start), target.index
        )
        end_prices, end_staleness = _price_at(
            open_pivot, close_pivot, pd.Timestamp(end), target.index
        )
        asset_returns = end_prices / start_prices - 1.0
        gross_return = float((target * asset_returns).sum())
        commission_cost = (buy_notional + sell_notional) * commission_bps / 10_000.0
        tax_cost = sell_notional * tax_bps / 10_000.0
        slippage_cost = (buy_notional + sell_notional) * slippage_bps / 10_000.0
        cost = commission_cost + tax_cost + slippage_cost
        net_return = (1.0 - cost) * (1.0 + gross_return) - 1.0

        end_values = target * (1.0 + asset_returns)
        prior_end_weights = end_values / end_values.sum()
        return_rows.append(
            {
                "strategy": strategy_name,
                "period_start": pd.Timestamp(start),
                "period_end": pd.Timestamp(end),
                "gross_return": gross_return,
                "turnover": turnover,
                "transaction_cost": cost,
                "commission_cost": commission_cost,
                "tax_cost": tax_cost,
                "slippage_cost": slippage_cost,
                "net_return": net_return,
                "stale_start_price_count": int((start_staleness > 0).sum()),
                "stale_end_price_count": int((end_staleness > 0).sum()),
                "max_price_staleness_days": int(
                    max(start_staleness.max(), end_staleness.max())
                ),
            }
        )
        for ticker, weight in target.items():
            weight_rows.append(
                {
                    "strategy": strategy_name,
                    "execution_date": pd.Timestamp(start),
                    "ticker": ticker,
                    "target_weight": float(weight),
                }
            )
    return BacktestResult(pd.DataFrame(return_rows), pd.DataFrame(weight_rows))


def benchmark_returns(
    benchmark: pd.DataFrame,
    index_id: str,
    ordered_execution_dates: list[pd.Timestamp],
) -> pd.DataFrame:
    series = (
        benchmark[benchmark["index_id"] == index_id]
        .sort_values("date")
        .set_index("date")["total_return_index"]
    )
    if series.empty:
        raise ValueError(f"benchmark index not found: {index_id}")

    rows = []
    for start, end in zip(ordered_execution_dates[:-1], ordered_execution_dates[1:]):
        start_available = series.index[series.index <= start]
        end_available = series.index[series.index <= end]
        if start_available.empty or end_available.empty:
            raise ValueError("benchmark does not cover the requested execution dates")
        value_start = float(series.loc[start_available[-1]])
        value_end = float(series.loc[end_available[-1]])
        net_return = value_end / value_start - 1.0
        rows.append(
            {
                "strategy": index_id,
                "period_start": pd.Timestamp(start),
                "period_end": pd.Timestamp(end),
                "gross_return": net_return,
                "turnover": 0.0,
                "transaction_cost": 0.0,
                "commission_cost": 0.0,
                "tax_cost": 0.0,
                "slippage_cost": 0.0,
                "net_return": net_return,
                "stale_start_price_count": 0,
                "stale_end_price_count": 0,
                "max_price_staleness_days": 0,
            }
        )
    return pd.DataFrame(rows)


def performance_metrics(returns: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for strategy, group in returns.groupby("strategy", sort=False):
        values = group.sort_values("period_end")["net_return"].astype(float)
        equity = (1.0 + values).cumprod()
        total_return = float(equity.iloc[-1] - 1.0)
        years = len(values) / 12.0
        cagr = float(equity.iloc[-1] ** (1.0 / years) - 1.0) if years > 0 else np.nan
        annual_vol = float(values.std(ddof=1) * np.sqrt(12))
        annual_return = float(values.mean() * 12)
        sharpe = annual_return / annual_vol if annual_vol > 0 else np.nan
        drawdown = equity / equity.cummax() - 1.0
        rows.append(
            {
                "strategy": strategy,
                "periods": len(values),
                "total_return": total_return,
                "cagr": cagr,
                "annual_volatility": annual_vol,
                "sharpe_rf0": sharpe,
                "max_drawdown": float(drawdown.min()),
                "average_turnover": float(group["turnover"].mean()),
                "total_transaction_cost": float(group["transaction_cost"].sum()),
                "total_commission_cost": float(group["commission_cost"].sum()),
                "total_tax_cost": float(group["tax_cost"].sum()),
                "total_slippage_cost": float(group["slippage_cost"].sum()),
                "stale_price_uses": int(
                    group["stale_start_price_count"].sum()
                    + group["stale_end_price_count"].sum()
                ),
                "max_price_staleness_days": int(group["max_price_staleness_days"].max()),
            }
        )
    return pd.DataFrame(rows)

