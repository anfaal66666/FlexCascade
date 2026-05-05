# Results Visualization Scripts

This folder contains the visualization and analysis scripts for turning model result artifacts into report-ready charts and tables.

## Main Script

```powershell
py -3.10 scripts\results_visualization\visualize_results.py results\r_run
```

If a finalized combined metrics file is available, use it for the model-comparison charts:

```powershell
py -3.10 scripts\results_visualization\visualize_results.py results\r_run --metrics-csv results\result_visualization_plots\tables\metrics_summary_combined.csv
```

By default, outputs are written to:

```text
results/result_visualization_plots/
```

Use `--output-dir` to write somewhere else.

## Inputs

The visualizer reads the standard experiment outputs:

- `metrics_summary.csv`
- `split_summary.json`
- `selected_configs.json`
- `evaluation/confusion/*.csv`
- `evaluation/per_class/*.csv`
- `evaluation/predictions/*.csv`

## Output Organization

Recommended generated output layout:

- `results/result_visualization_plots/figures/core/` - the main report/presentation plots.
- `results/result_visualization_plots/figures/appendix/` - detailed diagnostic plots.
- `results/result_visualization_plots/tables/` - combined CSV summaries and ranked tables.

## Visualization Logic

The main report should not use every generated graph. The core idea is:

1. Establish dataset scale and split quality.
2. Compare model families with accuracy.
3. Re-check conclusions with macro F1 because issuer classes are imbalanced.
4. Evaluate whether cascade/fallback helps or only adds complexity.
5. Use error-composition and top-confusion plots for interpretation.

Dense confusion matrices and per-class F1 charts belong in the appendix, not the main report.
