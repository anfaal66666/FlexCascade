#!/bin/zsh
set -euo pipefail

cd /Users/anfaalkhan/Documents/FlexCascade

mkdir -p logs results

Rscript run_experiment.R --config config/all_states_tuning_20k.json > logs/all_states_tuning_20k.log 2>&1
python3 scripts/build_full_config_from_tuning.py \
  --tuning-dir results/all_states_tuning_20k \
  --base-config config/all_states_full_best.json \
  --output-config config/all_states_full_selected.json > logs/all_states_config_select.log 2>&1
Rscript run_experiment.R --config config/all_states_full_selected.json > logs/all_states_full_selected.log 2>&1
