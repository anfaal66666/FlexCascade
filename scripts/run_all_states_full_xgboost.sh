#!/bin/zsh
set -euo pipefail
cd /Users/anfaalkhan/Documents/FlexCascade
mkdir -p logs results
Rscript run_experiment.R --config config/all_states_full_xgboost.json > logs/all_states_full_xgboost.log 2>&1
