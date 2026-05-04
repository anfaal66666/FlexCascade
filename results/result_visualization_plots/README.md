# Result Visualization Plots

This folder is reserved for generated visualization outputs.

Suggested organization:

- `figures/core/` - the few plots that should go in the report or presentation.
- `figures/appendix/` - dense diagnostic plots such as confusion matrices and per-class F1.
- `tables/` - generated CSV summaries used by the visual analysis.

Regenerate plots with:

```powershell
py -3.10 scripts\results_visualization\visualize_results.py results\r_run
```
