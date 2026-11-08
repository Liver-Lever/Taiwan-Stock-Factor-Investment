#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "$0")/.." && pwd)"
cd "$project_dir"

if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv .venv
  .venv/bin/python -m pip install -r requirements.txt
fi

.venv/bin/python -m app.cli make-demo-data --output-dir data/demo
.venv/bin/python -m app.cli validate --data-dir data/demo --allow-synthetic
.venv/bin/behave
.venv/bin/python -m app.cli run --config configs/demo.json

if [[ -f data/production/source_manifest.json ]]; then
  .venv/bin/python -m app.cli validate \
    --data-dir data/production --allow-constituent-proxy
  .venv/bin/python -m app.cli run --config configs/real_proxy.json
  .venv/bin/python scripts/build_in_sample_comparison.py \
    --data-dir data/production --results-dir results/real_proxy_in_sample
  .venv/bin/python -m app.cli run \
    --config configs/real_proxy_out_of_sample_through_2026_08.json
  .venv/bin/python scripts/build_in_sample_comparison.py \
    --data-dir data/production \
    --results-dir results/real_proxy_out_of_sample_through_2026_08 \
    --start 2023-01-01 --end 2026-08-31
fi

echo "Reproduction complete: tests, demo, real in-sample, and OOS-through-2026-08 outputs are ready."

