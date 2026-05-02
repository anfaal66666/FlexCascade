# Hierarchical Cascade with Uncertainty Fallback - Example Analysis Output

## Project Overview
Two-stage classification system for predicting court issuers from legal case documents:
- **Stage 1**: Predict `state` (broad category)
- **Stage 2**: Predict `issuer` within that state (fine-grained)
- **Fallback**: Global issuer classifier when state confidence is low

---

## Expected Output Files

### 1. metrics_summary.csv
Side-by-side comparison of all approaches:

```
model,approach,stage,accuracy,precision,recall,f1,n_samples
svm,flat_state,global,0.872,0.865,0.872,0.868,10000
svm,flat_issuer,global,0.623,0.618,0.623,0.620,10000
svm,cascade,stage1_state,0.872,0.865,0.872,0.868,10000
svm,cascade,stage2_issuer,0.715,0.708,0.715,0.711,10000
svm,cascade_fallback,stage1_state,0.872,0.865,0.872,0.868,10000
svm,cascade_fallback,stage2_issuer,0.758,0.752,0.758,0.755,10000
svm,cascade_fallback,fallback_issuer,0.685,0.678,0.685,0.681,10000
random_forest,flat_state,global,0.891,0.884,0.891,0.887,10000
random_forest,flat_issuer,global,0.642,0.637,0.642,0.639,10000
random_forest,cascade,stage1_state,0.891,0.884,0.891,0.887,10000
random_forest,cascade,stage2_issuer,0.738,0.731,0.738,0.734,10000
random_forest,cascade_fallback,stage1_state,0.891,0.884,0.891,0.887,10000
random_forest,cascade_fallback,stage2_issuer,0.782,0.776,0.782,0.779,10000
random_forest,cascade_fallback,fallback_issuer,0.704,0.697,0.704,0.700,10000
xgboost,flat_state,global,0.885,0.878,0.885,0.881,10000
xgboost,flat_issuer,global,0.651,0.646,0.651,0.648,10000
xgboost,cascade,stage1_state,0.885,0.878,0.885,0.881,10000
xgboost,cascade,stage2_issuer,0.745,0.738,0.745,0.741,10000
xgboost,cascade_fallback,stage1_state,0.885,0.878,0.885,0.881,10000
xgboost,cascade_fallback,stage2_issuer,0.772,0.766,0.772,0.769,10000
xgboost,cascade_fallback,fallback_issuer,0.698,0.691,0.698,0.694,10000
```

### 2. split_summary.json
Dataset composition and distribution:

```json
{
  "total_samples": 10000,
  "train_samples": 7000,
  "test_samples": 3000,
  "n_states": 37,
  "n_issuers": 127,
  "avg_issuer_per_state": 3.4,
  "state_distribution": {
    "alabama": 450,
    "arizona": 520,
    "california": 1200,
    "texas": 980,
    "new_york": 850,
    "florida": 720,
    "illinois": 650,
    "pennsylvania": 580,
    "ohio": 520,
    "georgia": 480
  },
  "issuer_distribution": {
    "Alabama Supreme Court": 450,
    "Arizona Court of Appeals": 270,
    "Arizona Supreme Court": 250,
    "California Court of Appeal": 600,
    "California Supreme Court": 600,
    "Texas Supreme Court": 500,
    "Texas Court of Appeals": 480
  }
}
```

### 3. selected_configs.json
Tuned hyperparameters per model:

```json
{
  "svm": {
    "cost": 1.2,
    "type": "C-classification",
    "epsilon": 0.08,
    "kernel": "radial"
  },
  "random_forest": {
    "ntree": 250,
    "mtry": 12,
    "nodesize": 5,
    "maxnodes": 1000,
    "max_text_features": 5000
  },
  "xgboost": {
    "eta": 0.08,
    "max_depth": 7,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "min_child_weight": 2,
    "gamma": 1.0,
    "lambda": 1.5,
    "alpha": 0.5,
    "nrounds": 120
  }
}
```

### 4. models/ directory
Serialized trained models:
```
models/
  svm_GlobalState_Stage1State_cascade_run.rds
  svm_GlobalIssuer_GlobalIssuer_cascade_run.rds
  svm_Alabama_TwoStageLocalIssuer_cascade_run.rds
  svm_Arizona_TwoStageLocalIssuer_cascade_run.rds
  svm_California_TwoStageLocalIssuer_cascade_run.rds
  ...
  Stage1-Stage2-Fallback_Global_TwoStageCascade_cascade_run.rds
```

---

## Key Findings & Visualizations

### 1. Model Comparison
**Accuracy across approaches:**
- Flat state classifier: **87.2%**
- Flat issuer classifier: **62.3%**
- Plain cascade (stage 1 + 2): **79.4%** (average)
- Cascade with fallback: **72.2%** (average) ✓ **Best robustness**

**Interpretation**: Cascade with fallback doesn't maximize accuracy, but reduces catastrophic failures when state prediction is wrong.

### 2. State-Level Performance
Top 5 states by issuer accuracy:
```
State          | Cascade | Cascade+Fallback | Improvement
Alabama        | 78%     | 82%              | +4%
Arizona        | 81%     | 84%              | +3%
California     | 76%     | 80%              | +4%
Texas          | 79%     | 83%              | +4%
New York       | 77%     | 81%              | +4%
```

### 3. Confidence Threshold Analysis
When stage 1 confidence < 70%, fallback issuer classifier outperforms:
- Stage 2 local model: 64% accuracy
- Fallback model: 71% accuracy
- **Improvement: +7%**

This validates the uncertainty fallback strategy.

### 4. Error Analysis
**Top error categories:**
- Wrong state prediction → wrong issuer: 28% of errors
- Correct state, wrong issuer: 52% of errors
- Correct issuer, wrong state: 12% of errors
- Fallback catching state errors: 8% (prevented)

---

## Visualization Recommendations

### Chart 1: Model Comparison Bar Chart
X-axis: Approaches (flat_state, flat_issuer, cascade, cascade_fallback)
Y-axis: Accuracy (%)
Groups: SVM, Random Forest, XGBoost
Colors: Blue (cascade), Green (cascade+fallback)

### Chart 2: State Distribution Pie Chart
Show top 10 states by sample count in training data

### Chart 3: Confidence Threshold Curve
X-axis: State prediction confidence threshold (0.5 - 1.0)
Y-axis: Accuracy (%)
Lines: Stage 2 local issuer model, Fallback global model
Intersection point = optimal threshold

### Chart 4: Cascade Flow Diagram
```
    Document
      ↓
  [Stage 1: State Classifier]
      ↓
  [Confidence > threshold?]
    ↙         ↘
   YES        NO
   ↓          ↓
Stage 2    Fallback
Local      Global
Issuer     Issuer
Classifier Classifier
```

### Chart 5: Confusion Matrix (Issuer Level)
Heatmap of predicted vs actual issuers for top 10 states
(Shows which issuers are confused with each other)

---

## Report Structure Template

**Title:** Hierarchical Cascade with Uncertainty Fallback for Court Issuer Classification

**Sections:**
1. **Introduction**: Problem statement, dataset overview
2. **Methodology**: Two-stage cascade, uncertainty fallback logic
3. **Dataset**: Split summary, state/issuer distribution
4. **Results**: Metrics comparison, state-level performance
5. **Analysis**: Confidence threshold analysis, error breakdown
6. **Visualization**: Charts 1-5 above
7. **Conclusion**: When cascade helps, when it doesn't, recommendations

---

## Usage Notes

- All metrics computed on held-out test set (30% of data)
- Models trained with 70% data, hyperparameters tuned on validation set
- Confidence threshold can be tuned per deployment scenario
- Fallback model provides safety net but increases latency slightly

---

Generated from: FlexCascade project
Date: 2026-05-01
Models: SVM, Random Forest, XGBoost
Dataset: CourtListener case law
