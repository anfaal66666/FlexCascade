#!/bin/zsh
set -euo pipefail
cd /Users/anfaalkhan/Documents/FlexCascade
mkdir -p logs results
Rscript run_experiment.R --config config/all_states_full_svm.json > logs/all_states_full_svm.log 2>&1
