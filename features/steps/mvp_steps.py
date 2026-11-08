from __future__ import annotations

import numpy as np
import pandas as pd
from behave import given, then, when

from app.backtest import run_target_backtest
from app.calendar import rebalance_events
from app.data import constituent_snapshot
from app.factors import factor_scores
from app.regime import regime_states
from app.weights import equal_weight_top_n, reduce_electronics


@given("a stock with steadily rising prices before and after the signal date")
def step_rising_prices(context):
    dates = pd.bdate_range("2024-01-01", periods=150)
    context.signal_date = dates[129]
    context.prices = pd.DataFrame(
        {"date": dates, "ticker": "A", "adj_close": np.arange(100.0, 250.0)}
    )
    context.fundamentals = pd.DataFrame(
        {"ticker": ["A"], "earnings_yield": [0.08], "roe": [0.15]}
    )


@when("I calculate factors on the signal date")
def step_calculate_twice(context):
    first = factor_scores(context.prices, ["A"], context.signal_date, context.fundamentals, 126, 60)
    changed = context.prices.copy()
    changed.loc[changed["date"] > context.signal_date, "adj_close"] *= 100
    second = factor_scores(changed, ["A"], context.signal_date, context.fundamentals, 126, 60)
    context.first_momentum = first.loc["A", "momentum_126d"]
    context.second_momentum = second.loc["A", "momentum_126d"]


@then("changing future prices does not change its momentum")
def step_future_ignored(context):
    assert np.isclose(context.first_momentum, context.second_momentum)


@given("two stocks with equal trend but different volatility")
def step_volatility_data(context):
    dates = pd.bdate_range("2024-01-01", periods=140)
    trend = np.linspace(100, 140, len(dates))
    smooth = trend
    noisy = trend * (1 + 0.04 * np.sin(np.arange(len(dates))))
    context.signal_date = dates[-1]
    context.prices = pd.concat(
        [
            pd.DataFrame({"date": dates, "ticker": "LOW", "adj_close": smooth}),
            pd.DataFrame({"date": dates, "ticker": "HIGH", "adj_close": noisy}),
        ],
        ignore_index=True,
    )
    context.fundamentals = pd.DataFrame(
        {
            "ticker": ["LOW", "HIGH"],
            "earnings_yield": [0.08, 0.08],
            "roe": [0.15, 0.15],
        }
    )


@when("I calculate their factor scores")
def step_factor_scores(context):
    context.scores = factor_scores(
        context.prices, ["LOW", "HIGH"], context.signal_date, context.fundamentals, 126, 60
    )


@then("the lower-volatility stock has the higher low-volatility score")
def step_low_vol_higher(context):
    assert context.scores.loc["LOW", "low_vol_score"] > context.scores.loc["HIGH", "low_vol_score"]


@then("momentum, reversal, low-volatility, value and quality scores are present")
def step_five_scores_present(context):
    expected = {
        "momentum_score",
        "reversal_score",
        "low_vol_score",
        "value_score",
        "quality_score",
    }
    assert expected.issubset(context.scores.columns)


@given("five ranked stocks")
def step_five_scores(context):
    context.scores = pd.DataFrame(
        {"combined_score": [5, 4, 3, 2, 1]}, index=["A", "B", "C", "D", "E"]
    )


@when("I select the top 3 stocks")
def step_select_top_three(context):
    context.weights = equal_weight_top_n(context.scores, 3)


@then("exactly 3 stocks each have one-third weight")
def step_three_equal(context):
    assert len(context.weights) == 3
    assert np.allclose(context.weights.to_numpy(), 1 / 3)


@given("a portfolio with 80 percent electronics and 20 percent non-electronics")
def step_sector_portfolio(context):
    context.base = pd.Series({"E1": 0.5, "E2": 0.3, "N1": 0.12, "N2": 0.08})
    context.sectors = pd.Series(
        {"E1": "electronic", "E2": "electronic", "N1": "non_electronic", "N2": "non_electronic"}
    )


@when("electronic weights are reduced by 25 percent")
def step_reduce_sector(context):
    context.weights = reduce_electronics(context.base, context.sectors, 0.25)


@then("electronics total 60 percent and all weights sum to 100 percent")
def step_sector_totals(context):
    assert np.isclose(context.weights[["E1", "E2"]].sum(), 0.60)
    assert np.isclose(context.weights.sum(), 1.0)


@given("trading days spanning two month ends")
def step_trading_days(context):
    context.dates = pd.bdate_range("2024-01-01", "2024-03-05")


@when("I build monthly rebalance events")
def step_events(context):
    context.events = rebalance_events(context.dates)


@then("every execution date is later than its signal date")
def step_next_day(context):
    assert (context.events["execution_date"] > context.events["signal_date"]).all()


@given("an electronic index that first falls below and then enters the hysteresis band")
def step_regime_index(context):
    dates = pd.bdate_range("2024-01-01", periods=45)
    closes = np.full(len(dates), 100.0)
    closes[21] = 95.0
    closes[44] = 100.0
    context.index_prices = pd.DataFrame(
        {"date": dates, "index_id": "ELEC", "close": closes}
    )
    context.signal_dates = [dates[21], dates[44]]


@when("I classify month-end regimes with a 2 percent band")
def step_classify_regime(context):
    context.regimes = regime_states(context.index_prices, context.signal_dates, "ELEC", 20, 0.02)


@then("the second signal remains weak")
def step_regime_retained(context):
    assert context.regimes.iloc[0]["state"] == "weak"
    assert context.regimes.iloc[1]["state"] == "weak"


@given("one published snapshot and one future snapshot")
def step_snapshots(context):
    context.constituents = pd.DataFrame(
        [
            {"effective_date": "2024-01-01", "available_date": "2023-12-28", "ticker": "OLD", "weight": 1.0, "sector": "electronic"},
            {"effective_date": "2024-04-01", "available_date": "2024-03-28", "ticker": "NEW", "weight": 1.0, "sector": "electronic"},
        ]
    )
    for column in ["effective_date", "available_date"]:
        context.constituents[column] = pd.to_datetime(context.constituents[column])


@when("I request constituents before the future publication date")
def step_snapshot_request(context):
    context.snapshot = constituent_snapshot(context.constituents, pd.Timestamp("2024-03-20"))


@then("only the published snapshot is returned")
def step_only_published(context):
    assert context.snapshot["ticker"].tolist() == ["OLD"]


@given("a fully invested one-period portfolio")
def step_one_period(context):
    context.start = pd.Timestamp("2024-01-02")
    context.end = pd.Timestamp("2024-02-01")
    context.prices = pd.DataFrame(
        [
            {"date": context.start, "ticker": "A", "adj_open": 100.0},
            {"date": context.end, "ticker": "A", "adj_open": 110.0},
        ]
    )
    context.targets = {context.start: pd.Series({"A": 1.0})}


@when("I backtest with positive transaction costs")
def step_cost_backtest(context):
    result = run_target_backtest(
        context.prices,
        context.targets,
        [context.start, context.end],
        commission_bps=10.0,
        tax_bps=30.0,
        slippage_bps=5.0,
        strategy_name="test",
    )
    context.result = result.returns.iloc[0]


@then("net return is lower than gross return")
def step_net_lower(context):
    assert context.result["net_return"] < context.result["gross_return"]

