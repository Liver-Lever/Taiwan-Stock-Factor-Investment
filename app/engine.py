from __future__ import annotations

from pathlib import Path

import pandas as pd

from .backtest import benchmark_returns, performance_metrics, run_target_backtest
from .calendar import evaluation_events
from .config import Config
from .data import constituent_snapshot, eligible_universe, load_bundle
from .factors import factor_scores
from .regime import regime_states
from .weights import equal_weight_top_n, reduce_electronics


STRATEGY_ORIGINAL = "0050_original"
STRATEGY_FIXED = "0050_fixed_electronics_minus25"
STRATEGY_DYNAMIC = "0050_dynamic_electronics_minus25"
STRATEGY_FACTOR = "factor_topN_equal"


def run(config: Config) -> dict[str, Path]:
    config.validate()
    bundle = load_bundle(
        config.data_dir,
        allow_synthetic=config.allow_synthetic,
        allow_constituent_proxy=config.allow_constituent_proxy,
    )
    if bundle.manifest.get("data_kind") == "real_constituent_proxy":
        strategy_original = "tw50_membership_equal_proxy"
        strategy_fixed = "tw50_proxy_fixed_electronics_minus25"
        strategy_dynamic = "tw50_proxy_dynamic_electronics_minus25"
    else:
        strategy_original = STRATEGY_ORIGINAL
        strategy_fixed = STRATEGY_FIXED
        strategy_dynamic = STRATEGY_DYNAMIC
    events = evaluation_events(bundle.prices["date"], config.start_date, config.end_date)
    signal_events = events.iloc[:-1].copy()
    regimes = regime_states(
        bundle.index_prices,
        signal_events["signal_date"],
        config.electronic_index_id,
        config.ma_window,
        config.hysteresis_band,
    ).set_index("signal_date")

    targets: dict[str, dict[pd.Timestamp, pd.Series]] = {
        strategy_original: {},
        strategy_fixed: {},
        strategy_dynamic: {},
        STRATEGY_FACTOR: {},
    }
    factor_rows = []
    audit_rows = []

    for event in signal_events.itertuples(index=False):
        signal_date = pd.Timestamp(event.signal_date)
        execution_date = pd.Timestamp(event.execution_date)
        snapshot = constituent_snapshot(bundle.constituents, signal_date)
        base = snapshot.set_index("ticker")["weight"]
        sectors = snapshot.set_index("ticker")["sector"]
        state = regimes.loc[signal_date, "state"]

        targets[strategy_original][execution_date] = base
        targets[strategy_fixed][execution_date] = reduce_electronics(
            base, sectors, config.electronics_cut_fraction
        )
        targets[strategy_dynamic][execution_date] = (
            reduce_electronics(base, sectors, config.electronics_cut_fraction)
            if state == "weak"
            else base
        )

        factor_universe = eligible_universe(
            bundle,
            signal_date,
            config.liquidity_lookback,
            config.minimum_average_trading_value,
        )
        scores = factor_scores(
            bundle.prices,
            factor_universe["ticker"].tolist(),
            signal_date,
            factor_universe,
            config.momentum_lookback,
            config.volatility_lookback,
        )
        targets[STRATEGY_FACTOR][execution_date] = equal_weight_top_n(scores, config.top_n)
        scored = scores.reset_index()
        scored.insert(0, "signal_date", signal_date)
        factor_rows.append(scored)
        audit_rows.append(
            {
                "signal_date": signal_date,
                "execution_date": execution_date,
                "snapshot_effective_date": snapshot["effective_date"].max(),
                "snapshot_available_date": snapshot["available_date"].max(),
                "regime": state,
                "electronic_index_close": regimes.loc[signal_date, "close"],
                "electronic_index_ma": regimes.loc[signal_date, "ma"],
            }
        )

    execution_dates = events["execution_date"].tolist()
    all_returns = []
    all_weights = []
    for strategy, strategy_targets in targets.items():
        result = run_target_backtest(
            bundle.prices,
            strategy_targets,
            execution_dates,
            config.commission_bps,
            config.tax_bps,
            config.slippage_bps,
            strategy,
        )
        all_returns.append(result.returns)
        all_weights.append(result.weights)

    all_returns.append(
        benchmark_returns(bundle.benchmark, config.benchmark_index_id, execution_dates)
    )
    if "0050_TR_OFFICIAL_PROXY" in set(bundle.benchmark["index_id"]):
        all_returns.append(
            benchmark_returns(bundle.benchmark, "0050_TR_OFFICIAL_PROXY", execution_dates)
        )
    returns = pd.concat(all_returns, ignore_index=True)
    weights = pd.concat(all_weights, ignore_index=True)
    metrics = performance_metrics(returns)
    factors = pd.concat(factor_rows, ignore_index=True)
    audit = pd.DataFrame(audit_rows)

    output_dir = config.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "returns": output_dir / "monthly_returns.csv",
        "metrics": output_dir / "metrics.csv",
        "weights": output_dir / "target_weights.csv",
        "factors": output_dir / "factor_scores.csv",
        "audit": output_dir / "point_in_time_audit.csv",
        "regimes": output_dir / "regime_signals.csv",
    }
    returns.to_csv(paths["returns"], index=False)
    metrics.to_csv(paths["metrics"], index=False)
    weights.to_csv(paths["weights"], index=False)
    factors.to_csv(paths["factors"], index=False)
    audit.to_csv(paths["audit"], index=False)
    regimes.reset_index().to_csv(paths["regimes"], index=False)
    return paths

