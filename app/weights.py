from __future__ import annotations

import pandas as pd


def normalize(weights: pd.Series) -> pd.Series:
    weights = weights.astype(float)
    total = weights.sum()
    if total <= 0:
        raise ValueError("weights must have a positive sum")
    result = weights / total
    if (result < 0).any():
        raise ValueError("negative weights are not supported")
    return result


def reduce_electronics(
    base_weights: pd.Series,
    sectors: pd.Series,
    cut_fraction: float = 0.25,
) -> pd.Series:
    if not 0 <= cut_fraction <= 1:
        raise ValueError("cut_fraction must be in [0, 1]")
    base = normalize(base_weights)
    sectors = sectors.reindex(base.index)
    electronic = sectors.eq("electronic")
    non_electronic = sectors.eq("non_electronic")
    if not electronic.any() or not non_electronic.any():
        raise ValueError("both electronic and non-electronic stocks are required")
    result = base.copy()
    released = float(base[electronic].sum() * cut_fraction)
    result.loc[electronic] = base[electronic] * (1.0 - cut_fraction)
    receiver = base[non_electronic] / base[non_electronic].sum()
    result.loc[non_electronic] = base[non_electronic] + receiver * released
    return normalize(result)


def equal_weight_top_n(scores: pd.DataFrame, top_n: int) -> pd.Series:
    if top_n < 1:
        raise ValueError("top_n must be positive")
    chosen = scores.sort_values(["combined_score"], ascending=False).head(top_n).index
    if len(chosen) < top_n:
        raise ValueError(f"only {len(chosen)} eligible stocks for top_n={top_n}")
    return pd.Series(1.0 / len(chosen), index=chosen, name="weight")

