#!/usr/bin/env python3
"""Build a transparent Taiwan 50 membership proxy from the public change table.

This is a secondary-source, month-level proxy. It is intentionally not labelled
as exact point-in-time 0050 holdings or weights.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen

import pandas as pd


SOURCE_URL = "https://zh.wikipedia.org/wiki/%E8%87%BA%E7%81%A350%E6%8C%87%E6%95%B8"
SPECIAL_2016_URL = "https://taiwanindex.com.tw/news/30"
SPECIAL_2018_URL = "https://taiwanindex.com.tw/news/85"
ANCHOR_MONTH = pd.Period("2025-09", freq="M")
START_MONTH = pd.Period("2014-12", freq="M")
END_MONTH = pd.Period("2026-09", freq="M")


def _download() -> str:
    request = Request(SOURCE_URL, headers={"User-Agent": "tw-factor-mvp/1.0 academic-research"})
    with urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8")


def _codes(value: object) -> list[str]:
    return re.findall(r"(?<!\d)(\d{4})(?!\d)", str(value))


def _period(value: object) -> pd.Period:
    match = re.search(r"(\d{4})年(\d{1,2})月", str(value))
    if not match:
        raise ValueError(f"cannot parse change month: {value}")
    return pd.Period(f"{match.group(1)}-{int(match.group(2)):02d}", freq="M")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="data/production")
    args = parser.parse_args()

    output_dir = Path(args.output_dir).resolve()
    raw_dir = output_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    html = _download()
    raw_path = raw_dir / "taiwan50_wikipedia.html"
    raw_path.write_text(html, encoding="utf-8")
    tables = pd.read_html(io.StringIO(html))
    if len(tables) < 2:
        raise RuntimeError("Taiwan 50 page does not contain expected tables")

    anchor_table = tables[0]
    anchor_rows: list[dict[str, object]] = []
    for suffix in ("", ".1"):
        code_column = f"股票代號{suffix}"
        name_column = f"名稱{suffix}"
        weight_column = f"比重(%){suffix}"
        for _, row in anchor_table.iterrows():
            codes = _codes(row[code_column])
            if len(codes) != 1:
                raise ValueError(f"unexpected anchor code: {row[code_column]}")
            anchor_rows.append(
                {
                    "ticker": codes[0],
                    "name": str(row[name_column]),
                    "weight": float(row[weight_column]) / 100.0,
                }
            )
    anchor = pd.DataFrame(anchor_rows).drop_duplicates("ticker")
    if len(anchor) != 50:
        raise RuntimeError(f"expected 50 anchor constituents, got {len(anchor)}")

    change_table = tables[1]
    changes: list[dict[str, object]] = []
    for _, row in change_table.iterrows():
        month = _period(row["日期"])
        if START_MONTH <= month <= END_MONTH:
            added = _codes(row["納入指數"])
            removed = _codes(row["剔除指數"])
            if len(added) != len(removed):
                raise RuntimeError(f"unbalanced change at {month}: +{added} -{removed}")
            changes.append({"month": month, "added": added, "removed": removed})

    by_month = {item["month"]: item for item in changes}
    if ANCHOR_MONTH not in by_month:
        raise RuntimeError("anchor month is absent from change table")

    snapshots: dict[pd.Period, set[str]] = {}
    current = set(anchor["ticker"])
    for month in sorted((m for m in by_month if m <= ANCHOR_MONTH), reverse=True):
        snapshots[month] = set(current)
        change = by_month[month]
        current.difference_update(change["added"])
        current.update(change["removed"])
    snapshots[START_MONTH] = set(current)

    current = set(anchor["ticker"])
    for month in sorted(m for m in by_month if m > ANCHOR_MONTH):
        change = by_month[month]
        current.update(change["added"])
        current.difference_update(change["removed"])
        snapshots[month] = set(current)

    # The secondary quarterly table omits two official, event-driven changes.
    # Correct the predecessor code before ASE Holding existed, then insert the
    # official effective-month snapshots without moving later regular reviews.
    for month, members in snapshots.items():
        if month <= pd.Period("2018-03", freq="M") and "3711" in members:
            members.remove("3711")
            members.add("2311")

    before_2016_event = set(snapshots[max(m for m in snapshots if m < pd.Period("2016-11", freq="M"))])
    before_2016_event.discard("3474")
    before_2016_event.add("2823")
    snapshots[pd.Period("2016-11", freq="M")] = before_2016_event

    before_2018_event = set(snapshots[max(m for m in snapshots if m < pd.Period("2018-04", freq="M"))])
    before_2018_event.discard("2311")
    before_2018_event.discard("2325")
    before_2018_event.add("3711")
    before_2018_event.add("2327")
    snapshots[pd.Period("2018-04", freq="M")] = before_2018_event

    bad_sizes = {str(month): len(members) for month, members in snapshots.items() if len(members) != 50}
    if bad_sizes:
        raise RuntimeError(f"membership snapshots are not size 50: {bad_sizes}")

    snapshot_rows = []
    for month, members in sorted(snapshots.items()):
        for ticker in sorted(members):
            snapshot_rows.append(
                {
                    "effective_month_end": month.end_time.strftime("%Y-%m-%d"),
                    "available_date_proxy": month.end_time.strftime("%Y-%m-%d"),
                    "ticker": ticker,
                    "source_quality": "secondary_month_level_proxy",
                }
            )
    snapshots_frame = pd.DataFrame(snapshot_rows)
    snapshots_frame.to_csv(output_dir / "taiwan50_membership_proxy.csv", index=False)

    change_rows = []
    for item in sorted(changes, key=lambda value: value["month"]):
        for action, tickers in (("add", item["added"]), ("remove", item["removed"])):
            for ticker in tickers:
                change_rows.append(
                    {
                        "month_end_proxy": item["month"].end_time.strftime("%Y-%m-%d"),
                        "action": action,
                        "ticker": ticker,
                    }
                )
    change_rows.extend(
        [
            {
                "month_end_proxy": "2016-11-30",
                "action": "remove",
                "ticker": "3474",
                "source": SPECIAL_2016_URL,
            },
            {
                "month_end_proxy": "2016-11-30",
                "action": "add",
                "ticker": "2823",
                "source": SPECIAL_2016_URL,
            },
            {
                "month_end_proxy": "2018-04-30",
                "action": "remove",
                "ticker": "2311",
                "source": SPECIAL_2018_URL,
            },
            {
                "month_end_proxy": "2018-04-30",
                "action": "remove",
                "ticker": "2325",
                "source": SPECIAL_2018_URL,
            },
            {
                "month_end_proxy": "2018-04-30",
                "action": "add",
                "ticker": "3711",
                "source": SPECIAL_2018_URL,
            },
            {
                "month_end_proxy": "2018-04-30",
                "action": "add",
                "ticker": "2327",
                "source": SPECIAL_2018_URL,
            },
        ]
    )
    pd.DataFrame(change_rows).to_csv(output_dir / "taiwan50_membership_changes.csv", index=False)

    anchor_output = anchor.assign(
        as_of_date="2025-09-30", source_quality="single_secondary_weight_snapshot"
    )
    anchor_output.to_csv(output_dir / "taiwan50_weight_snapshot_2025_09.csv", index=False)

    manifest = {
        "downloaded_at": datetime.now().astimezone().isoformat(),
        "source": SOURCE_URL,
        "supplemental_official_sources": [SPECIAL_2016_URL, SPECIAL_2018_URL],
        "raw_sha256": _sha256_bytes(html.encode("utf-8")),
        "anchor_date": "2025-09-30",
        "anchor_constituents": int(len(anchor)),
        "anchor_weight_sum": float(anchor["weight"].sum()),
        "membership_snapshot_months": int(len(snapshots)),
        "point_in_time_constituents": False,
        "limitations": [
            "secondary Wikipedia change table, not an official timestamped constituent file",
            "change effective dates are represented conservatively at calendar month-end",
            "historical weights are unavailable; only the 2025-09 anchor weights are retained",
            "official event-driven changes in 2016-11 and 2018-04 are inserted separately",
            "must be labelled Taiwan 50 membership proxy and not exact historical 0050 holdings",
        ],
    }
    (raw_dir / "taiwan50_membership_proxy_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"membership proxy: {len(snapshots)} snapshots x 50 constituents")
    print(f"anchor weight sum: {anchor['weight'].sum():.6f}")


if __name__ == "__main__":
    main()
