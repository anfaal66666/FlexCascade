#!/usr/bin/env python3
"""Export HFforLegal/case-law to a flat CSV for the R pipeline."""

from __future__ import annotations

import argparse
import pathlib

from datasets import load_dataset

REQUIRED_COLUMNS = [
    "title",
    "citation",
    "docket_number",
    "state",
    "issuer",
    "document",
    "timestamp",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--cache-dir", default="data/hf_cache")
    parser.add_argument("--split", default="us")
    parser.add_argument("--max-rows", type=int, default=None)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--states", nargs="*", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_path = pathlib.Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    dataset = load_dataset(
        "HFforLegal/case-law",
        split=args.split,
        cache_dir=args.cache_dir,
        verification_mode="no_checks",
    )
    if args.states:
        wanted = {state.strip() for state in args.states if state.strip()}
        dataset = dataset.filter(lambda row: (row.get("state") or "").strip() in wanted)
    if args.max_rows is not None and args.max_rows < len(dataset):
        dataset = dataset.shuffle(seed=args.seed).select(range(args.max_rows))

    frame = dataset.to_pandas()[REQUIRED_COLUMNS]
    frame.to_csv(output_path, index=False)
    print(f"Wrote {len(frame):,} rows to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
