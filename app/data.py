from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


@dataclass
class DataBundle:
    prices: pd.DataFrame
    constituents: pd.DataFrame
    universe: pd.DataFrame
    fundamentals: pd.DataFrame
    index_prices: pd.DataFrame
    benchmark: pd.DataFrame
    manifest: dict


SCHEMAS = {
    "prices.csv": {"date", "ticker", "adj_open", "adj_close", "trading_value"},
    "constituents.csv": {
        "effective_date",
        "available_date",
        "ticker",
        "weight",
        "sector",
    },
    "universe.csv": {"ticker", "listing_date", "delisting_date", "market", "security_type"},
    "fundamentals.csv": {
        "available_date",
        "ticker",
        "earnings_yield",
        "roe",
    },
    "index_prices.csv": {"date", "index_id", "close"},
    "benchmark.csv": {"date", "index_id", "total_return_index"},
}


def _read_csv(path: Path, date_columns: tuple[str, ...]) -> pd.DataFrame:
    frame = pd.read_csv(path)
    for column in date_columns:
        frame[column] = pd.to_datetime(frame[column], errors="raise")
    return frame


def load_bundle(
    data_dir: str | Path,
    allow_synthetic: bool = False,
    allow_constituent_proxy: bool = False,
) -> DataBundle:
    root = Path(data_dir)
    missing = [name for name in [*SCHEMAS, "source_manifest.json"] if not (root / name).exists()]
    if missing:
        raise FileNotFoundError(f"missing data files: {', '.join(missing)}")

    for filename, expected in SCHEMAS.items():
        columns = set(pd.read_csv(root / filename, nrows=0).columns)
        absent = expected - columns
        if absent:
            raise ValueError(f"{filename} missing columns: {sorted(absent)}")

    manifest = json.loads((root / "source_manifest.json").read_text(encoding="utf-8"))
    if manifest.get("data_kind") == "synthetic_fixture" and not allow_synthetic:
        raise ValueError("synthetic data is disabled; pass --allow-synthetic only for engine verification")
    if manifest.get("data_kind") != "synthetic_fixture":
        if manifest.get("point_in_time_constituents") is not True:
            proxy_allowed = (
                allow_constituent_proxy
                and manifest.get("data_kind") == "real_constituent_proxy"
                and bool(manifest.get("proxy_disclosure"))
            )
            if not proxy_allowed:
                raise ValueError(
                    "production manifest must assert point_in_time_constituents=true; "
                    "a disclosed real-data proxy requires explicit allow_constituent_proxy"
                )
        if not manifest.get("sources"):
            raise ValueError("production manifest must document data sources")

    bundle = DataBundle(
        prices=_read_csv(root / "prices.csv", ("date",)),
        constituents=_read_csv(root / "constituents.csv", ("effective_date", "available_date")),
        universe=_read_csv(root / "universe.csv", ("listing_date", "delisting_date")),
        fundamentals=_read_csv(root / "fundamentals.csv", ("available_date",)),
        index_prices=_read_csv(root / "index_prices.csv", ("date",)),
        benchmark=_read_csv(root / "benchmark.csv", ("date",)),
        manifest=manifest,
    )
    validate_bundle(bundle)
    return bundle


def validate_bundle(bundle: DataBundle) -> None:
    prices = bundle.prices
    if prices.duplicated(["date", "ticker"]).any():
        raise ValueError("prices contain duplicate date/ticker rows")
    if not np.isfinite(prices[["adj_open", "adj_close", "trading_value"]].to_numpy()).all():
        raise ValueError("prices contain non-finite values")
    if (prices[["adj_open", "adj_close"]] <= 0).any().any():
        raise ValueError("adjusted prices must be positive")
    if (prices["trading_value"] < 0).any():
        raise ValueError("trading_value cannot be negative")

    constituents = bundle.constituents
    if constituents.duplicated(["effective_date", "ticker"]).any():
        raise ValueError("constituents contain duplicate effective_date/ticker rows")
    if (constituents["available_date"] > constituents["effective_date"]).any():
        raise ValueError("available_date cannot be later than effective_date in this MVP contract")
    weight_sums = constituents.groupby("effective_date")["weight"].sum()
    if not np.allclose(weight_sums.to_numpy(), 1.0, atol=1e-8):
        raise ValueError("constituent weights must sum to 1 for every snapshot")
    if (constituents["weight"] <= 0).any():
        raise ValueError("constituent weights must be positive")
    if not set(constituents["sector"].unique()).issubset({"electronic", "non_electronic"}):
        raise ValueError("sector must be electronic or non_electronic")

    universe = bundle.universe
    if universe["ticker"].duplicated().any():
        raise ValueError("universe contains duplicate tickers")
    if not set(universe["market"].unique()).issubset({"TWSE", "TPEX"}):
        raise ValueError("market must be TWSE or TPEX")
    if not set(universe["security_type"].unique()).issubset({"ordinary_stock"}):
        raise ValueError("MVP universe only accepts ordinary_stock")

    fundamentals = bundle.fundamentals
    if fundamentals.duplicated(["available_date", "ticker"]).any():
        raise ValueError("fundamentals contain duplicate available_date/ticker rows")
    if "market_cap" in fundamentals and (fundamentals["market_cap"] <= 0).any():
        raise ValueError("market_cap must be positive when provided")
    numeric_columns = ["earnings_yield", "roe"]
    if "market_cap" in fundamentals:
        numeric_columns.insert(0, "market_cap")
    if not np.isfinite(fundamentals[numeric_columns].to_numpy()).all():
        raise ValueError("fundamentals contain non-finite values")

    if bundle.index_prices.duplicated(["date", "index_id"]).any():
        raise ValueError("index_prices contain duplicate date/index rows")
    if bundle.benchmark.duplicated(["date", "index_id"]).any():
        raise ValueError("benchmark contains duplicate date/index rows")


def constituent_snapshot(constituents: pd.DataFrame, signal_date: pd.Timestamp) -> pd.DataFrame:
    signal_date = pd.Timestamp(signal_date)
    eligible = constituents[
        (constituents["available_date"] <= signal_date)
        & (constituents["effective_date"] <= signal_date)
    ]
    if eligible.empty:
        raise ValueError(f"no point-in-time constituent snapshot available on {signal_date.date()}")
    effective_date = eligible["effective_date"].max()
    snapshot = eligible[eligible["effective_date"] == effective_date].copy()
    if (snapshot["available_date"] > signal_date).any():
        raise AssertionError("future constituent information reached the strategy")
    snapshot["weight"] = snapshot["weight"] / snapshot["weight"].sum()
    return snapshot.sort_values("ticker").reset_index(drop=True)


def eligible_universe(
    bundle: DataBundle,
    signal_date: pd.Timestamp,
    liquidity_lookback: int,
    minimum_average_trading_value: float,
) -> pd.DataFrame:
    signal_date = pd.Timestamp(signal_date)
    active = bundle.universe[
        (bundle.universe["listing_date"] <= signal_date)
        & (bundle.universe["delisting_date"].isna() | (bundle.universe["delisting_date"] > signal_date))
        & bundle.universe["security_type"].eq("ordinary_stock")
    ].copy()
    if active.empty:
        raise ValueError(f"no active ordinary stocks on {signal_date.date()}")

    price_history = bundle.prices[
        (bundle.prices["date"] <= signal_date) & bundle.prices["ticker"].isin(active["ticker"])
    ].sort_values(["ticker", "date"])
    liquidity = (
        price_history.groupby("ticker", group_keys=False)
        .tail(liquidity_lookback)
        .groupby("ticker")["trading_value"]
        .agg(["mean", "count"])
        .rename(columns={"mean": "average_trading_value", "count": "liquidity_observations"})
    )
    liquid = liquidity[
        (liquidity["liquidity_observations"] >= liquidity_lookback)
        & (liquidity["average_trading_value"] >= minimum_average_trading_value)
    ].reset_index()

    available_fundamentals = bundle.fundamentals[
        (bundle.fundamentals["available_date"] <= signal_date)
        & bundle.fundamentals["ticker"].isin(active["ticker"])
    ].sort_values(["ticker", "available_date"])
    latest = available_fundamentals.groupby("ticker", as_index=False).tail(1)
    result = active.merge(liquid, on="ticker", how="inner").merge(latest, on="ticker", how="inner")
    if result.empty:
        raise ValueError(f"no stocks pass point-in-time and liquidity filters on {signal_date.date()}")
    if (result["available_date"] > signal_date).any():
        raise AssertionError("future fundamentals reached the strategy")
    return result.sort_values("ticker").reset_index(drop=True)

