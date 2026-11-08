from __future__ import annotations

import argparse
from pathlib import Path

from .config import Config
from .data import load_bundle
from .demo_data import generate
from .engine import run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Taiwan smart-factor strategy MVP")
    subparsers = parser.add_subparsers(dest="command", required=True)

    demo = subparsers.add_parser("make-demo-data", help="create deterministic synthetic fixture data")
    demo.add_argument("--output-dir", default="data/demo")

    validate = subparsers.add_parser("validate", help="validate data contracts and point-in-time manifest")
    validate.add_argument("--data-dir", required=True)
    validate.add_argument("--allow-synthetic", action="store_true")
    validate.add_argument("--allow-constituent-proxy", action="store_true")

    execute = subparsers.add_parser("run", help="run all strategies and write CSV results")
    execute.add_argument("--config", required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "make-demo-data":
        generate(Path(args.output_dir))
        print(f"demo data written to {Path(args.output_dir).resolve()}")
    elif args.command == "validate":
        bundle = load_bundle(
            args.data_dir,
            allow_synthetic=args.allow_synthetic,
            allow_constituent_proxy=args.allow_constituent_proxy,
        )
        print(
            f"validated {len(bundle.prices):,} prices, "
            f"{len(bundle.constituents):,} constituent rows"
        )
    elif args.command == "run":
        paths = run(Config.from_json(args.config))
        for name, path in paths.items():
            print(f"{name}: {path}")


if __name__ == "__main__":
    main()

