#!/bin/zsh
set -euo pipefail
cd /Users/anfaalkhan/Documents/FlexCascade
mkdir -p logs results
Rscript run_experiment.R --config config/all_states_full_random_forest.json > logs/all_states_full_random_forest.log 2>&1
