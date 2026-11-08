from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


def generate(output_dir: str | Path, seed: int = 20261107) -> None:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2013-12-02", "2023-02-10")
    electronic = [f"E{i:02d}" for i in range(1, 41)]
    non_electronic = [f"N{i:02d}" for i in range(1, 21)]
    tickers = electronic + non_electronic

    market = rng.normal(0.00025, 0.009, len(dates))
    cycle = np.sin(np.arange(len(dates)) / 95.0) * 0.0007
    electronic_factor = market + cycle + rng.normal(0, 0.004, len(dates))
    defensive_factor = 0.65 * market - 0.25 * cycle + rng.normal(0, 0.0035, len(dates))

    price_rows = []
    close_matrix = {}
    liquidity_base = {
        ticker: (25_000_000 if number >= 50 else 80_000_000 + number * 4_000_000)
        for number, ticker in enumerate(tickers)
    }
    for number, ticker in enumerate(tickers):
        is_electronic = ticker.startswith("E")
        common = electronic_factor if is_electronic else defensive_factor
        daily = common + rng.normal(0, 0.0045 + number * 0.00005, len(dates))
        overnight = daily * 0.32 + rng.normal(0, 0.0015, len(dates))
        intraday = daily - overnight
        opens = np.empty(len(dates))
        closes = np.empty(len(dates))
        prior_close = 50.0 + number * 3.0
        for i in range(len(dates)):
            opens[i] = prior_close * np.exp(overnight[i])
            closes[i] = opens[i] * np.exp(intraday[i])
            prior_close = closes[i]
        close_matrix[ticker] = closes
        price_rows.extend(
            {
                "date": date,
                "ticker": ticker,
                "adj_open": opens[i],
                "adj_close": closes[i],
                "trading_value": liquidity_base[ticker] * float(rng.lognormal(0, 0.25)),
            }
            for i, date in enumerate(dates)
        )
    pd.DataFrame(price_rows).to_csv(root / "prices.csv", index=False)

    index_electronic = electronic[:10]
    index_non_electronic = non_electronic[:6]
    raw_e = np.linspace(1.5, 0.6, len(index_electronic))
    raw_n = np.linspace(1.2, 0.7, len(index_non_electronic))
    constituent_rows = []
    quarter_starts = pd.date_range("2013-10-01", "2023-01-01", freq="QS")
    for q, calendar_date in enumerate(quarter_starts):
        effective = dates[dates.searchsorted(calendar_date)]
        available_index = max(0, dates.get_loc(effective) - 3)
        available = dates[available_index]
        e_weights = raw_e * (1.0 + 0.04 * np.sin(q / 3.0 + np.arange(len(raw_e))))
        n_weights = raw_n * (1.0 + 0.04 * np.cos(q / 4.0 + np.arange(len(raw_n))))
        e_weights = e_weights / e_weights.sum() * 0.75
        n_weights = n_weights / n_weights.sum() * 0.25
        for ticker, weight in zip(index_electronic, e_weights):
            constituent_rows.append(
                {
                    "effective_date": effective,
                    "available_date": available,
                    "ticker": ticker,
                    "weight": weight,
                    "sector": "electronic",
                }
            )
        for ticker, weight in zip(index_non_electronic, n_weights):
            constituent_rows.append(
                {
                    "effective_date": effective,
                    "available_date": available,
                    "ticker": ticker,
                    "weight": weight,
                    "sector": "non_electronic",
                }
            )
    pd.DataFrame(constituent_rows).to_csv(root / "constituents.csv", index=False)

    universe_rows = []
    for number, ticker in enumerate(tickers):
        universe_rows.append(
            {
                "ticker": ticker,
                "listing_date": "2010-01-01",
                "delisting_date": "",
                "market": "TWSE" if number % 4 else "TPEX",
                "security_type": "ordinary_stock",
            }
        )
    pd.DataFrame(universe_rows).to_csv(root / "universe.csv", index=False)

    fundamental_rows = []
    quarter_ends = pd.period_range("2013Q3", "2022Q4", freq="Q").to_timestamp("Q")
    base_market_cap = np.geomspace(30_000_000_000, 2_000_000_000, len(tickers))
    base_earnings_yield = np.linspace(0.035, 0.10, len(tickers))
    base_roe = np.linspace(0.22, 0.06, len(tickers))
    for q, quarter_end in enumerate(quarter_ends):
        target = quarter_end + pd.Timedelta(days=45)
        position = min(dates.searchsorted(target), len(dates) - 1)
        available_date = dates[position]
        for number, ticker in enumerate(tickers):
            fundamental_rows.append(
                {
                    "available_date": available_date,
                    "ticker": ticker,
                    "market_cap": base_market_cap[number] * np.exp(0.012 * q + rng.normal(0, 0.04)),
                    "earnings_yield": base_earnings_yield[number] + 0.008 * np.sin(q / 2 + number) + rng.normal(0, 0.003),
                    "roe": base_roe[number] + 0.02 * np.cos(q / 3 + number) + rng.normal(0, 0.006),
                }
            )
    pd.DataFrame(fundamental_rows).to_csv(root / "fundamentals.csv", index=False)

    close_frame = pd.DataFrame(close_matrix, index=dates)
    electronic_index = (close_frame[electronic] / close_frame[electronic].iloc[0]).mean(axis=1) * 1000.0
    pd.DataFrame(
        {"date": dates, "index_id": "TWSE_ELECTRONICS", "close": electronic_index.to_numpy()}
    ).to_csv(root / "index_prices.csv", index=False)

    stock_returns = close_frame.pct_change(fill_method=None).fillna(0)
    broad_return = stock_returns.mean(axis=1) + (0.018 / 252.0)
    tri = (1.0 + broad_return).cumprod() * 1000.0
    pd.DataFrame(
        {"date": dates, "index_id": "TAIEX_TR", "total_return_index": tri.to_numpy()}
    ).to_csv(root / "benchmark.csv", index=False)

    manifest = {
        "data_kind": "synthetic_fixture",
        "point_in_time_constituents": True,
        "seed": seed,
        "warning": "For software verification only. Do not interpret results as Taiwan market evidence.",
        "sources": ["Deterministic generator in app/demo_data.py"],
    }
    (root / "source_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

