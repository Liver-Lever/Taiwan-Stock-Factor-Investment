from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    data_dir: Path
    output_dir: Path
    start_date: str
    end_date: str
    electronic_index_id: str
    benchmark_index_id: str
    ma_window: int = 20
    hysteresis_band: float = 0.02
    electronics_cut_fraction: float = 0.25
    momentum_lookback: int = 126
    volatility_lookback: int = 60
    top_n: int = 10
    liquidity_lookback: int = 20
    minimum_average_trading_value: float = 50_000_000
    commission_bps: float = 14.25
    tax_bps: float = 30.0
    slippage_bps: float = 5.0
    allow_synthetic: bool = False
    allow_constituent_proxy: bool = False

    @classmethod
    def from_json(cls, path: str | Path) -> "Config":
        config_path = Path(path).resolve()
        raw = json.loads(config_path.read_text(encoding="utf-8"))
        root = config_path.parent.parent
        raw["data_dir"] = (root / raw["data_dir"]).resolve()
        raw["output_dir"] = (root / raw["output_dir"]).resolve()
        return cls(**raw)

    def validate(self) -> None:
        if not 0 <= self.hysteresis_band < 1:
            raise ValueError("hysteresis_band must be in [0, 1)")
        if not 0 <= self.electronics_cut_fraction <= 1:
            raise ValueError("electronics_cut_fraction must be in [0, 1]")
        if self.ma_window < 2 or self.momentum_lookback < 2 or self.volatility_lookback < 2:
            raise ValueError("lookback windows must be at least 2")
        if self.top_n < 1:
            raise ValueError("top_n must be positive")
        if self.liquidity_lookback < 2 or self.minimum_average_trading_value < 0:
            raise ValueError("liquidity settings are invalid")
        if min(self.commission_bps, self.tax_bps, self.slippage_bps) < 0:
            raise ValueError("cost assumptions cannot be negative")

