#!/usr/bin/env python3
"""Assemble the explicitly labelled real-data Taiwan 50 membership proxy bundle."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import pandas as pd


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default="data/production")
    args = parser.parse_args()
    data_dir = Path(args.data_dir).resolve()
    raw_dir = data_dir / "raw"

    membership = pd.read_csv(
        data_dir / "taiwan50_membership_proxy.csv", dtype={"ticker": str}
    )
    sector_map = json.loads((raw_dir / "sector_classification.json").read_text(encoding="utf-8"))
    membership["effective_date"] = membership["effective_month_end"]
    membership["available_date"] = membership["available_date_proxy"]
    membership["weight"] = membership.groupby("effective_date")["ticker"].transform(
        lambda values: 1.0 / len(values)
    )
    membership["sector"] = membership["ticker"].map(sector_map)
    if membership["sector"].isna().any():
        missing = membership.loc[membership["sector"].isna(), "ticker"].unique().tolist()
        raise RuntimeError(f"missing sector classification: {missing}")
    constituents = membership[
        ["effective_date", "available_date", "ticker", "weight", "sector"]
    ].copy()
    if not constituents.groupby("effective_date")["weight"].sum().round(12).eq(1.0).all():
        raise RuntimeError("proxy constituent weights do not sum to one")
    constituents.to_csv(data_dir / "constituents.csv", index=False)

    stock_manifest = json.loads(
        (raw_dir / "finmind_stock_panel_manifest.json").read_text(encoding="utf-8")
    )
    index_manifest = json.loads(
        (raw_dir / "real_indices_manifest.json").read_text(encoding="utf-8")
    )
    membership_manifest = json.loads(
        (raw_dir / "taiwan50_membership_proxy_manifest.json").read_text(encoding="utf-8")
    )
    legacy_manifest_path = raw_dir / "twse_legacy_2311_manifest.json"
    legacy_source = []
    if legacy_manifest_path.exists():
        legacy_source.append(
            json.loads(legacy_manifest_path.read_text(encoding="utf-8"))["source"]
        )
    manifest = {
        "assembled_at": datetime.now().astimezone().isoformat(),
        "data_kind": "real_constituent_proxy",
        "point_in_time_constituents": False,
        "proxy_disclosure": (
            "Taiwan 50 membership is reconstructed at month level from a secondary public change "
            "table and weighted equally. Results are not original 0050 historical-weight returns."
        ),
        "study_period": ["2015-01-01", "2026-09-30"],
        "sources": [
            stock_manifest["source"],
            *index_manifest["sources"].values(),
            membership_manifest["source"],
            *membership_manifest.get("supplemental_official_sources", []),
            *legacy_source,
            "user-provided 0050 and electronic-index month-end workbooks",
        ],
        "unresolved_large_price_jumps": stock_manifest["rows"][
            "unresolved_large_price_jumps"
        ],
        "unresolved_jump_impact": (
            "two discontinuities remain, both more than 126 trading days before the affected "
            "stock first enters the proxy membership; they remain in the audit file"
        ),
        "factor_definitions": {
            "momentum": "126-trading-day corporate-action-adjusted return proxy",
            "reversal": "negative 20-trading-day adjusted return proxy",
            "low_volatility": "60-trading-day adjusted return volatility",
            "earnings_yield": "1 / same-day published PER",
            "quality": "implied ROE = PBR / PER",
        },
    }
    (data_dir / "source_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"assembled {len(constituents)} explicitly labelled proxy constituent rows")


if __name__ == "__main__":
    main()
