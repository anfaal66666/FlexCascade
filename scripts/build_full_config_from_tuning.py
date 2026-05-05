#!/usr/bin/env python3
"""Build a full-data config from tuning results."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tuning-dir", required=True)
    parser.add_argument("--base-config", required=True)
    parser.add_argument("--output-config", required=True)
    parser.add_argument("--system", default="cascade_with_fallback")
    parser.add_argument("--metric", default="macro_f1")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    tuning_dir = Path(args.tuning_dir)
    metrics_path = tuning_dir / "metrics_summary.csv"
    registry_path = tuning_dir / "model_registry.json"

    metrics_rows = list(csv.DictReader(metrics_path.open()))
    registry = json.loads(registry_path.read_text())
    base_config = json.loads(Path(args.base_config).read_text())

    best_by_model: dict[str, tuple[str, float]] = {}
    for run_name, run_info in registry.items():
      model_type = run_info["hierarchy"]["stage1_model"]
      matching = [
          row for row in metrics_rows
          if row["algorithm"] == run_name and row["system"] == args.system
      ]
      if not matching:
          continue
      score = float(matching[0][args.metric])
      current = best_by_model.get(model_type)
      if current is None or score > current[1]:
          best_by_model[model_type] = (run_name, score)

    comparison_runs = []
    for model_type in ("svm", "random_forest", "xgboost"):
      if model_type not in best_by_model:
          continue
      run_name, _score = best_by_model[model_type]
      run_info = registry[run_name]
      base_config["models"][model_type] = run_info["model_params"][model_type]
      comparison_runs.append(
          {
              "name": f"{model_type}_full_allstates",
              "hierarchy": {
                  "stage1_model": model_type,
                  "stage2_model": model_type,
                  "fallback_model": model_type,
              },
          }
      )

    base_config["comparison_runs"] = comparison_runs
    Path(args.output_config).write_text(json.dumps(base_config, indent=2))
    print(f"Wrote {args.output_config}")
    print(json.dumps(best_by_model, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
