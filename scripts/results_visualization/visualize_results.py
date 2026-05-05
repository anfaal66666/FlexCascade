#!/usr/bin/env python3
"""Create report-ready plots from FlexCascade experiment outputs.

The R pipeline writes tabular artifacts under each results directory. This
script keeps visualization separate from training so plots can be regenerated
after a run without touching models or predictions.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from matplotlib.ticker import PercentFormatter


SYSTEM_LABELS = {
    "flat_state": "Flat state",
    "flat_issuer": "Flat issuer",
    "plain_cascade": "Plain cascade",
    "cascade_with_fallback": "Cascade + fallback",
}

METRIC_LABELS = {
    "accuracy": "Accuracy",
    "macro_f1": "Macro F1",
    "weighted_f1": "Weighted F1",
    "balanced_accuracy": "Balanced accuracy",
    "top_3_accuracy": "Top-3 accuracy",
    "log_loss": "Log loss",
}

SYSTEM_ORDER = [
    "Flat state",
    "Flat issuer",
    "Plain cascade",
    "Cascade + fallback",
]

MODEL_ORDER = ["Random Forest", "SVM", "XGBoost", "XGBoost Tuned"]

MODEL_PALETTE = {
    "Random Forest": "#2E7D32",
    "SVM": "#1565C0",
    "XGBoost": "#C62828",
    "XGBoost Tuned": "#EF6C00",
}

SYSTEM_PALETTE = {
    "Flat state": "#264653",
    "Flat issuer": "#2A9D8F",
    "Plain cascade": "#E9C46A",
    "Cascade + fallback": "#E76F51",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Visualize FlexCascade result directories.",
    )
    parser.add_argument(
        "result_dirs",
        nargs="+",
        type=Path,
        help="One or more results directories produced by run_experiment.R.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results/result_visualization_plots"),
        help="Directory where figures and combined CSVs will be written.",
    )
    parser.add_argument(
        "--metrics",
        nargs="+",
        default=["accuracy", "macro_f1", "weighted_f1"],
        help="Metric columns to include in overview plots.",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=20,
        help="Number of classes to show in per-class and confusion plots.",
    )
    parser.add_argument(
        "--metrics-csv",
        type=Path,
        default=None,
        help="Optional combined metrics CSV to use for model-comparison plots.",
    )
    return parser.parse_args()


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def figure_path(output_dir: Path, filename: str, group: str = "appendix") -> Path:
    return ensure_dir(output_dir / "figures" / group) / filename


def table_path(output_dir: Path, filename: str) -> Path:
    return ensure_dir(output_dir / "tables") / filename


def result_label(result_dir: Path) -> str:
    return result_dir.name


def read_csv_if_exists(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    return pd.read_csv(path)


def load_metrics(result_dirs: list[Path], filename: str) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for result_dir in result_dirs:
        frame = read_csv_if_exists(result_dir / filename)
        if frame is None or frame.empty:
            continue
        frame["result_dir"] = result_label(result_dir)
        frames.append(frame)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True, sort=False)


def load_metrics_from_csv(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    if "result_dir" not in frame.columns:
        frame["result_dir"] = path.parent.name
    return frame


def prepare_metrics(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    frame = frame.copy()
    frame["system_label"] = frame["system"].map(SYSTEM_LABELS).fillna(frame["system"])
    if "algorithm" in frame.columns:
        frame["model"] = frame["algorithm"].map(model_label)
        frame["run_label"] = frame["model"]
    return frame


def model_label(value: str) -> str:
    labels = {
        "svm_cascade": "SVM",
        "random_forest_cascade": "Random Forest",
        "xgboost_cascade": "XGBoost",
        "xgboost_cascade_tuned": "XGBoost Tuned",
    }
    return labels.get(value, value.replace("_", " ").title())


def ordered_unique(values: pd.Series, preferred: list[str]) -> list[str]:
    present = [value for value in preferred if value in set(values)]
    extras = sorted(value for value in values.dropna().unique() if value not in present)
    return present + extras


def add_bar_labels(ax, percent: bool = True, padding: float = 0.006) -> None:
    for container in ax.containers:
        labels = []
        for value in container.datavalues:
            if pd.isna(value):
                labels.append("")
            elif percent:
                labels.append(f"{value:.1%}")
            else:
                labels.append(f"{value:.3f}")
        ax.bar_label(container, labels=labels, padding=3, fontsize=9)


def save_core_metric_bars(metrics: pd.DataFrame, output_dir: Path) -> None:
    if metrics.empty:
        return
    available = [metric for metric in ["accuracy", "macro_f1"] if metric in metrics.columns]
    if not available:
        return

    frame = metrics.copy()
    frame["model"] = frame["algorithm"].map(model_label)
    frame["model"] = pd.Categorical(
        frame["model"],
        categories=ordered_unique(frame["model"], MODEL_ORDER),
        ordered=True,
    )
    frame["system_label"] = pd.Categorical(
        frame["system_label"],
        categories=[name for name in SYSTEM_ORDER if name in set(frame["system_label"])],
        ordered=True,
    )

    for metric in available:
        plot_data = frame.dropna(subset=[metric]).sort_values(["model", "system_label"])
        plt.figure(figsize=(12, 6.5))
        ax = sns.barplot(
            data=plot_data,
            x="model",
            y=metric,
            hue="system_label",
            palette=SYSTEM_PALETTE,
            errorbar=None,
        )
        ax.set_xlabel("")
        ax.set_ylabel(METRIC_LABELS.get(metric, metric))
        ax.set_title(f"{METRIC_LABELS.get(metric, metric)} by algorithm and modeling approach")
        ax.yaxis.set_major_formatter(PercentFormatter(1.0))
        ax.set_ylim(0, 1.08)
        add_bar_labels(ax, percent=True)
        ax.legend(title="Approach", ncols=2, loc="upper center", bbox_to_anchor=(0.5, -0.06), frameon=True)
        plt.tight_layout()
        plt.savefig(figure_path(output_dir, f"core_{metric}_comparison.png", "core"), dpi=220, bbox_inches="tight")
        plt.close()


def save_core_model_summary(metrics: pd.DataFrame, output_dir: Path) -> None:
    if metrics.empty or not {"accuracy", "macro_f1"}.issubset(metrics.columns):
        return
    frame = metrics.copy()
    frame["model"] = frame["algorithm"].map(model_label)
    frame["approach"] = frame["system_label"]
    top = frame.sort_values(["accuracy", "macro_f1"], ascending=False).head(8).copy()
    top["label"] = top["model"] + " - " + top["approach"]
    top = top.sort_values("accuracy", ascending=True)
    top.to_csv(table_path(output_dir, "core_top_models.csv"), index=False)

    plt.figure(figsize=(11, 6.5))
    ax = sns.barplot(
        data=top,
        x="accuracy",
        y="label",
        hue="model",
        palette=MODEL_PALETTE,
        errorbar=None,
        dodge=False,
    )
    ax.set_xlabel("Accuracy")
    ax.set_ylabel("")
    ax.set_title("Top model configurations by accuracy")
    ax.xaxis.set_major_formatter(PercentFormatter(1.0))
    ax.set_xlim(max(0, top["accuracy"].min() - 0.03), min(1.03, top["accuracy"].max() + 0.02))
    add_bar_labels(ax, percent=True)
    ax.legend_.remove()
    plt.tight_layout()
    plt.savefig(figure_path(output_dir, "core_top_models_by_accuracy.png", "core"), dpi=220)
    plt.close()


def save_core_error_story(metrics: pd.DataFrame, output_dir: Path) -> None:
    required = {"wrong_issuer_correct_state", "wrong_state_wrong_issuer"}
    if metrics.empty or not required.issubset(metrics.columns):
        return
    frame = metrics[metrics["system"] != "flat_state"].copy()
    frame = frame.dropna(subset=["wrong_issuer_correct_state", "wrong_state_wrong_issuer"])
    if frame.empty:
        return
    frame["model"] = frame["algorithm"].map(model_label)
    frame["total_errors_tracked"] = frame["wrong_issuer_correct_state"] + frame["wrong_state_wrong_issuer"]
    frame = frame[frame["total_errors_tracked"] > 0]
    frame["within_state_error_share"] = frame["wrong_issuer_correct_state"] / frame["total_errors_tracked"]
    frame["wrong_state_error_share"] = frame["wrong_state_wrong_issuer"] / frame["total_errors_tracked"]
    long = frame.melt(
        id_vars=["model", "system_label", "algorithm"],
        value_vars=["within_state_error_share", "wrong_state_error_share"],
        var_name="error_type",
        value_name="share",
    )
    long["error_type"] = long["error_type"].map(
        {
            "within_state_error_share": "Correct state, wrong issuer",
            "wrong_state_error_share": "Wrong state and issuer",
        }
    )
    long["configuration"] = long["model"] + " - " + long["system_label"]
    order = (
        frame.sort_values("total_errors_tracked")["model"] + " - " + frame.sort_values("total_errors_tracked")["system_label"]
    ).tolist()

    plt.figure(figsize=(11, max(5.5, 0.45 * len(order) + 2)))
    ax = sns.barplot(
        data=long,
        y="configuration",
        x="share",
        hue="error_type",
        order=order,
        palette=["#2A9D8F", "#E76F51"],
        errorbar=None,
    )
    ax.set_xlabel("Share of tracked issuer errors")
    ax.set_ylabel("")
    ax.set_title("Where issuer errors come from")
    ax.xaxis.set_major_formatter(PercentFormatter(1.0))
    ax.set_xlim(0, 1)
    ax.legend(title="Error type", loc="lower right")
    plt.tight_layout()
    plt.savefig(figure_path(output_dir, "core_issuer_error_composition.png", "core"), dpi=220)
    plt.close()


def save_accuracy_vs_macro_f1(metrics: pd.DataFrame, output_dir: Path) -> None:
    if metrics.empty or not {"accuracy", "macro_f1"}.issubset(metrics.columns):
        return
    frame = metrics.dropna(subset=["accuracy", "macro_f1"]).copy()
    frame["model"] = frame["algorithm"].map(model_label)
    frame["model"] = pd.Categorical(
        frame["model"],
        categories=ordered_unique(frame["model"], MODEL_ORDER),
        ordered=True,
    )

    plt.figure(figsize=(10, 7))
    ax = sns.scatterplot(
        data=frame,
        x="accuracy",
        y="macro_f1",
        hue="model",
        style="system_label",
        palette=MODEL_PALETTE,
        s=150,
    )
    ax.set_xlabel("Accuracy")
    ax.set_ylabel("Macro F1")
    ax.set_title("Accuracy vs macro F1")
    ax.xaxis.set_major_formatter(PercentFormatter(1.0))
    ax.yaxis.set_major_formatter(PercentFormatter(1.0))
    ax.set_xlim(max(0, frame["accuracy"].min() - 0.04), min(1.0, frame["accuracy"].max() + 0.025))
    ax.set_ylim(max(0, frame["macro_f1"].min() - 0.04), min(1.0, frame["macro_f1"].max() + 0.06))
    ax.legend(
        title="Model / approach",
        bbox_to_anchor=(1.02, 1),
        loc="upper left",
        borderaxespad=0,
        fontsize=9,
        title_fontsize=10,
    )
    legend = ax.get_legend()
    if legend is not None:
        for text in legend.get_texts():
            if text.get_text() == "model":
                text.set_text("Algorithm")
            elif text.get_text() == "system_label":
                text.set_text("Approach")
    plt.tight_layout()
    plt.savefig(figure_path(output_dir, "core_accuracy_vs_macro_f1.png", "core"), dpi=220, bbox_inches="tight")
    plt.close()


def save_performance_heatmaps(metrics: pd.DataFrame, output_dir: Path) -> None:
    if metrics.empty:
        return
    frame = metrics.copy()
    frame["model"] = frame["algorithm"].map(model_label)
    for metric in ["accuracy", "macro_f1", "weighted_f1", "balanced_accuracy"]:
        if metric not in frame.columns:
            continue
        pivot = frame.pivot_table(
            index="model",
            columns="system_label",
            values=metric,
            aggfunc="mean",
        )
        ordered_columns = [name for name in SYSTEM_ORDER if name in pivot.columns]
        pivot = pivot[ordered_columns]
        pivot = pivot.reindex(index=[name for name in MODEL_ORDER if name in pivot.index])
        plt.figure(figsize=(11, 4.8))
        ax = sns.heatmap(
            pivot,
            annot=True,
            fmt=".1%",
            cmap="crest",
            vmin=0,
            vmax=1,
            linewidths=0.7,
            linecolor="white",
            cbar_kws={"format": PercentFormatter(1.0), "label": METRIC_LABELS.get(metric, metric)},
        )
        ax.set_xlabel("Modeling approach")
        ax.set_ylabel("Algorithm")
        ax.set_title(f"{METRIC_LABELS.get(metric, metric)} heatmap")
        ax.set_xticklabels(ax.get_xticklabels(), rotation=25, ha="right")
        ax.set_yticklabels(ax.get_yticklabels(), rotation=0)
        plt.tight_layout()
        group = "core" if metric in {"accuracy", "macro_f1"} else "appendix"
        plt.savefig(figure_path(output_dir, f"{group}_heatmap_{metric}.png", group), dpi=220)
        plt.close()


def save_cascade_delta(metrics: pd.DataFrame, output_dir: Path) -> None:
    if metrics.empty or "accuracy" not in metrics.columns:
        return
    frame = metrics[metrics["system"].isin(["flat_issuer", "plain_cascade", "cascade_with_fallback"])].copy()
    if frame.empty:
        return
    baseline = frame[frame["system"] == "flat_issuer"][["result_dir", "algorithm", "accuracy"]].rename(
        columns={"accuracy": "flat_issuer_accuracy"}
    )
    deltas = frame.merge(baseline, on=["result_dir", "algorithm"], how="left")
    deltas["accuracy_delta"] = deltas["accuracy"] - deltas["flat_issuer_accuracy"]
    deltas = deltas[deltas["system"] != "flat_issuer"]
    if deltas.empty:
        return
    deltas["model"] = deltas["algorithm"].map(model_label)
    deltas["model"] = pd.Categorical(
        deltas["model"],
        categories=ordered_unique(deltas["model"], MODEL_ORDER),
        ordered=True,
    )
    deltas.to_csv(table_path(output_dir, "cascade_accuracy_delta.csv"), index=False)

    plt.figure(figsize=(10, 6))
    ax = sns.barplot(
        data=deltas,
        x="model",
        y="accuracy_delta",
        hue="system_label",
        palette=SYSTEM_PALETTE,
        errorbar=None,
    )
    ax.axhline(0, color="black", linewidth=1)
    ax.set_xlabel("Algorithm")
    ax.set_ylabel("Accuracy change vs flat issuer")
    ax.set_title("Cascade trade-off relative to the flat issuer baseline")
    ax.yaxis.set_major_formatter(PercentFormatter(1.0))
    add_bar_labels(ax, percent=True)
    ax.legend(title="Approach", loc="best")
    plt.tight_layout()
    plt.savefig(figure_path(output_dir, "core_cascade_accuracy_delta.png", "core"), dpi=220)
    plt.close()


def save_selected_config_plot(result_dirs: list[Path], output_dir: Path) -> None:
    rows = []
    for result_dir in result_dirs:
        path = result_dir / "selected_configs.json"
        if not path.exists():
            continue
        selected = json.loads(path.read_text(encoding="utf-8"))
        for algorithm, config in selected.items():
            rows.append({"result_dir": result_label(result_dir), "algorithm": algorithm, **config})
    frame = pd.DataFrame(rows)
    if frame.empty:
        return
    frame["model"] = frame["algorithm"].map(model_label)
    frame.to_csv(table_path(output_dir, "selected_configs_combined.csv"), index=False)

    long = frame.melt(
        id_vars=["result_dir", "algorithm", "model"],
        value_vars=["confidence_threshold", "top_k_states", "global_weight"],
        var_name="parameter",
        value_name="value",
    )
    plt.figure(figsize=(10, 6))
    ax = sns.barplot(data=long, x="model", y="value", hue="parameter", palette="Set2", errorbar=None)
    plt.xlabel("Model")
    plt.ylabel("Selected value")
    plt.title("Tuned fallback parameters")
    ax.legend(title="Parameter", loc="upper right")
    plt.tight_layout()
    plt.savefig(figure_path(output_dir, "appendix_selected_fallback_parameters.png", "appendix"), dpi=220)
    plt.close()


def save_metric_overview(metrics: pd.DataFrame, output_dir: Path, metric_names: list[str]) -> None:
    if metrics.empty:
        return

    available = [metric for metric in metric_names if metric in metrics.columns]
    if not available:
        return

    long = metrics.melt(
        id_vars=["result_dir", "algorithm", "system", "system_label", "run_label"],
        value_vars=available,
        var_name="metric",
        value_name="value",
    ).dropna(subset=["value"])
    long["metric_label"] = long["metric"].map(METRIC_LABELS).fillna(long["metric"])
    long["model"] = long["algorithm"].map(model_label)
    long["run_label"] = long["model"]

    for metric in available:
        subset = long[long["metric"] == metric]
        if subset.empty:
            continue
        height = max(5, 0.45 * subset["run_label"].nunique() + 3)
        plt.figure(figsize=(12, height))
        sns.barplot(
            data=subset,
            x="value",
            y="run_label",
            hue="system_label",
            palette=SYSTEM_PALETTE,
            errorbar=None,
        )
        plt.xlabel(METRIC_LABELS.get(metric, metric))
        plt.ylabel("Run")
        plt.title(f"{METRIC_LABELS.get(metric, metric)} by system")
        if metric != "log_loss":
            plt.xlim(0, min(1.0, max(0.05, subset["value"].max() * 1.12)))
        plt.legend(title="System", loc="lower right")
        plt.tight_layout()
        plt.savefig(figure_path(output_dir, f"appendix_metric_{metric}_by_system.png"), dpi=180)
        plt.close()

    plt.figure(figsize=(12, max(5, 0.45 * long["run_label"].nunique() + 3)))
    sns.catplot(
        data=long,
        kind="bar",
        x="value",
        y="system_label",
        hue="run_label",
        col="metric_label",
        col_wrap=2,
        sharex=False,
        errorbar=None,
        height=4,
        aspect=1.35,
    )
    plt.savefig(figure_path(output_dir, "appendix_metrics_overview_faceted.png"), dpi=180, bbox_inches="tight")
    plt.close("all")


def save_split_metrics(metrics_by_split: pd.DataFrame, output_dir: Path) -> None:
    if metrics_by_split.empty or "split" not in metrics_by_split.columns:
        return
    metrics_by_split = prepare_metrics(metrics_by_split)
    available = [metric for metric in ["accuracy", "macro_f1", "weighted_f1"] if metric in metrics_by_split.columns]
    if not available:
        return

    long = metrics_by_split.melt(
        id_vars=["result_dir", "algorithm", "system", "system_label", "split"],
        value_vars=available,
        var_name="metric",
        value_name="value",
    ).dropna(subset=["value"])
    long["metric_label"] = long["metric"].map(METRIC_LABELS).fillna(long["metric"])

    grid = sns.catplot(
        data=long,
        kind="bar",
        x="split",
        y="value",
        hue="system_label",
        col="metric_label",
        row="result_dir",
        errorbar=None,
        height=3.6,
        aspect=1.25,
        sharey=False,
    )
    grid.set_axis_labels("Split", "Metric value")
    grid.set_titles("{row_name} / {col_name}")
    plt.savefig(figure_path(output_dir, "appendix_metrics_by_split.png"), dpi=180, bbox_inches="tight")
    plt.close("all")


def save_error_breakdown(metrics: pd.DataFrame, output_dir: Path) -> None:
    required = {"wrong_issuer_correct_state", "wrong_state_wrong_issuer"}
    if metrics.empty or not required.issubset(metrics.columns):
        return

    issuer_rows = metrics[metrics["system"] != "flat_state"].copy()
    if issuer_rows.empty:
        return

    long = issuer_rows.melt(
        id_vars=["result_dir", "algorithm", "system_label"],
        value_vars=sorted(required),
        var_name="error_type",
        value_name="count",
    ).dropna(subset=["count"])
    long["error_type"] = long["error_type"].map(
        {
            "wrong_issuer_correct_state": "Wrong issuer, correct state",
            "wrong_state_wrong_issuer": "Wrong state and issuer",
        }
    )
    long["run_label"] = long["algorithm"].map(model_label)

    plt.figure(figsize=(12, max(5, 0.5 * long["run_label"].nunique() + 3)))
    sns.barplot(
        data=long,
        x="count",
        y="run_label",
        hue="error_type",
        errorbar=None,
    )
    plt.xlabel("Error count")
    plt.ylabel("Run")
    plt.title("Issuer error breakdown")
    plt.legend(title="Error type")
    plt.tight_layout()
    plt.savefig(figure_path(output_dir, "appendix_issuer_error_breakdown_counts.png"), dpi=180)
    plt.close()


def save_split_summary(result_dirs: list[Path], output_dir: Path) -> None:
    rows: list[dict[str, object]] = []
    for result_dir in result_dirs:
        path = result_dir / "split_summary.json"
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8") as handle:
            summary = json.load(handle)
        for key in ["train_rows", "validation_rows", "test_rows"]:
            if key in summary:
                rows.append(
                    {
                        "result_dir": result_label(result_dir),
                        "split": key.replace("_rows", ""),
                        "rows": summary[key],
                    }
                )

    frame = pd.DataFrame(rows)
    if frame.empty:
        return
    frame.to_csv(table_path(output_dir, "split_summary_combined.csv"), index=False)

    plt.figure(figsize=(10, max(4, 0.45 * frame["result_dir"].nunique() + 3)))
    sns.barplot(data=frame, x="rows", y="result_dir", hue="split", errorbar=None)
    plt.xlabel("Rows")
    plt.ylabel("Result directory")
    plt.title("Train/validation/test split sizes")
    plt.tight_layout()
    plt.savefig(figure_path(output_dir, "core_split_sizes.png", "core"), dpi=220)
    plt.close()


def iter_named_csvs(result_dirs: list[Path], subdir: str, suffix: str) -> list[tuple[Path, Path]]:
    paths: list[tuple[Path, Path]] = []
    for result_dir in result_dirs:
        directory = result_dir / "evaluation" / subdir
        if not directory.exists():
            continue
        for path in sorted(directory.glob(f"*{suffix}")):
            paths.append((result_dir, path))
    return paths


def save_per_class_plots(result_dirs: list[Path], output_dir: Path, top_n: int) -> None:
    for result_dir, path in iter_named_csvs(result_dirs, "per_class", "_per_class.csv"):
        frame = pd.read_csv(path)
        if frame.empty or "f1" not in frame.columns:
            continue
        frame = frame.sort_values(["f1", "support"], ascending=[True, False]).head(top_n)
        label = f"{result_label(result_dir)}__{path.stem.replace('__', '_')}"

        plt.figure(figsize=(12, max(5, 0.38 * len(frame) + 2)))
        ax = sns.barplot(data=frame, x="f1", y="class", hue="support", dodge=False, palette="crest")
        ax.set_xlabel("F1 score")
        ax.set_ylabel("")
        ax.set_title(f"Lowest per-class F1: {path.stem}")
        ax.xaxis.set_major_formatter(PercentFormatter(1.0))
        ax.set_xlim(0, 1)
        ax.legend(title="Support", loc="lower right")
        plt.tight_layout()
        plt.savefig(figure_path(output_dir, f"appendix_per_class_low_f1__{label}.png"), dpi=180)
        plt.close()


def save_confusion_heatmaps(result_dirs: list[Path], output_dir: Path, top_n: int) -> None:
    for result_dir, path in iter_named_csvs(result_dirs, "confusion", "_confusion.csv"):
        frame = pd.read_csv(path)
        if frame.empty or not {"truth", "predicted", "count"}.issubset(frame.columns):
            continue
        support = frame.groupby("truth", as_index=False)["count"].sum()
        top_classes = support.sort_values("count", ascending=False).head(top_n)["truth"]
        subset = frame[frame["truth"].isin(top_classes) & frame["predicted"].isin(top_classes)]
        if subset.empty:
            continue
        matrix = subset.pivot_table(
            index="truth",
            columns="predicted",
            values="count",
            aggfunc="sum",
            fill_value=0,
        )
        matrix = matrix.reindex(index=top_classes, columns=top_classes, fill_value=0)
        row_sums = matrix.sum(axis=1).replace(0, pd.NA)
        matrix_pct = matrix.div(row_sums, axis=0).fillna(0)

        width = max(8, 0.42 * len(matrix.columns) + 4)
        height = max(7, 0.42 * len(matrix.index) + 3)
        plt.figure(figsize=(width, height))
        ax = sns.heatmap(
            matrix_pct,
            cmap="rocket_r",
            square=True,
            vmin=0,
            vmax=1,
            linewidths=0.2,
            linecolor="white",
            cbar_kws={"format": PercentFormatter(1.0), "label": "Row-normalized share"},
        )
        ax.set_xlabel("Predicted")
        ax.set_ylabel("Truth")
        ax.set_title(f"Top-class confusion, normalized by true class: {path.stem}")
        ax.set_xticklabels(ax.get_xticklabels(), rotation=45, ha="right", fontsize=8)
        ax.set_yticklabels(ax.get_yticklabels(), rotation=0, fontsize=8)
        plt.tight_layout()
        label = f"{result_label(result_dir)}__{path.stem.replace('__', '_')}"
        plt.savefig(figure_path(output_dir, f"appendix_confusion_top_{top_n}__{label}.png"), dpi=190)
        plt.close()


def save_top_confusion_pairs(result_dirs: list[Path], output_dir: Path, top_n: int) -> None:
    rows = []
    for result_dir, path in iter_named_csvs(result_dirs, "confusion", "_confusion.csv"):
        frame = pd.read_csv(path)
        if frame.empty or not {"truth", "predicted", "count"}.issubset(frame.columns):
            continue
        frame = frame[(frame["truth"] != frame["predicted"]) & (frame["count"] > 0)].copy()
        if frame.empty:
            continue
        run_name, system_name = path.stem.replace("_confusion", "").split("__", 1)
        frame["result_dir"] = result_label(result_dir)
        frame["algorithm"] = run_name
        frame["model"] = frame["algorithm"].map(model_label)
        frame["system"] = system_name
        frame["system_label"] = frame["system"].map(SYSTEM_LABELS).fillna(frame["system"])
        rows.append(frame)
    if not rows:
        return
    combined = pd.concat(rows, ignore_index=True)
    top = combined.sort_values("count", ascending=False).head(top_n).copy()
    top["pair"] = top["truth"] + " -> " + top["predicted"]
    top.to_csv(table_path(output_dir, "top_confusion_pairs.csv"), index=False)

    plt.figure(figsize=(12, max(6, 0.35 * len(top) + 2)))
    ax = sns.barplot(data=top, x="count", y="pair", hue="model", palette=MODEL_PALETTE, errorbar=None)
    ax.set_xlabel("Count")
    ax.set_ylabel("Truth -> predicted")
    ax.set_title(f"Top {top_n} off-diagonal confusion pairs")
    ax.legend(title="Algorithm", loc="lower right")
    plt.tight_layout()
    plt.savefig(figure_path(output_dir, "core_top_confusion_pairs.png", "core"), dpi=220)
    plt.close()


def save_prediction_correctness(result_dirs: list[Path], output_dir: Path) -> None:
    rows = []
    for result_dir, path in iter_named_csvs(result_dirs, "predictions", "_predictions.csv"):
        frame = pd.read_csv(path)
        if frame.empty:
            continue
        run_name, system_name = path.stem.replace("_predictions", "").split("__", 1)
        if {"state_correct", "issuer_correct"}.issubset(frame.columns):
            categories = pd.Series("Wrong state and issuer", index=frame.index)
            categories[frame["state_correct"] & ~frame["issuer_correct"]] = "Correct state, wrong issuer"
            categories[frame["state_correct"] & frame["issuer_correct"]] = "Correct issuer"
        elif "correct" in frame.columns:
            categories = frame["correct"].map({True: "Correct state", False: "Wrong state"})
        else:
            continue
        counts = categories.value_counts().reset_index()
        counts.columns = ["category", "count"]
        counts["result_dir"] = result_label(result_dir)
        counts["algorithm"] = run_name
        counts["model"] = counts["algorithm"].map(model_label)
        counts["system"] = system_name
        counts["system_label"] = counts["system"].map(SYSTEM_LABELS).fillna(counts["system"])
        rows.append(counts)
    if not rows:
        return
    combined = pd.concat(rows, ignore_index=True)
    combined.to_csv(table_path(output_dir, "prediction_correctness_counts.csv"), index=False)

    for (result_dir, algorithm), subset in combined.groupby(["result_dir", "algorithm"]):
        pivot = subset.pivot_table(
            index="system_label",
            columns="category",
            values="count",
            aggfunc="sum",
            fill_value=0,
        )
        ordered_index = [name for name in SYSTEM_ORDER if name in pivot.index]
        pivot = pivot.reindex(ordered_index)
        ax = pivot.plot(kind="barh", stacked=True, figsize=(11, 6), color=["#2A9D8F", "#E9C46A", "#E76F51", "#264653"])
        ax.set_xlabel("Predictions")
        ax.set_ylabel("System")
        ax.set_title(f"Prediction correctness: {model_label(algorithm)}")
        plt.tight_layout()
        safe_name = f"{result_dir}__{algorithm}".replace("/", "_").replace("\\", "_")
        plt.savefig(figure_path(output_dir, f"appendix_prediction_correctness__{safe_name}.png"), dpi=180)
        plt.close()


def save_class_balance_plots(result_dirs: list[Path], output_dir: Path, top_n: int) -> None:
    state_rows = []
    issuer_rows = []
    seen_state_sources = set()
    seen_issuer_sources = set()

    for result_dir, path in iter_named_csvs(result_dirs, "predictions", "_predictions.csv"):
        frame = pd.read_csv(path)
        if frame.empty:
            continue
        run_name, system_name = path.stem.replace("_predictions", "").split("__", 1)
        source_key = (result_label(result_dir), run_name)

        if "truth_state" in frame.columns and source_key not in seen_state_sources:
            counts = frame["truth_state"].value_counts().reset_index()
            counts.columns = ["state", "count"]
            counts["percent"] = counts["count"] / counts["count"].sum()
            state_rows.append(counts)
            seen_state_sources.add(source_key)

        if "truth_issuer" in frame.columns and source_key not in seen_issuer_sources:
            counts = frame["truth_issuer"].value_counts().reset_index()
            counts.columns = ["issuer", "count"]
            counts["percent"] = counts["count"] / counts["count"].sum()
            issuer_rows.append(counts)
            seen_issuer_sources.add(source_key)

    state_balance = pd.DataFrame()
    issuer_balance = pd.DataFrame()

    if state_rows:
        state_balance = (
            pd.concat(state_rows, ignore_index=True)
            .groupby("state", as_index=False)["count"]
            .max()
            .sort_values("count", ascending=False)
        )
        state_balance["percent"] = state_balance["count"] / state_balance["count"].sum()
        state_balance.to_csv(table_path(output_dir, "test_state_class_balance.csv"), index=False)

        plt.figure(figsize=(10, 5.8))
        ax = sns.barplot(data=state_balance, x="state", y="count", color="#2A9D8F", errorbar=None)
        ax.set_xlabel("True state label")
        ax.set_ylabel("Test cases")
        ax.set_title("Test-set class balance by state")
        for container in ax.containers:
            ax.bar_label(container, labels=[f"{value:,.0f}" for value in container.datavalues], padding=3, fontsize=9)
        plt.tight_layout()
        plt.savefig(figure_path(output_dir, "core_state_class_balance.png", "core"), dpi=220)
        plt.close()

    if issuer_rows:
        issuer_balance = (
            pd.concat(issuer_rows, ignore_index=True)
            .groupby("issuer", as_index=False)["count"]
            .max()
            .sort_values("count", ascending=False)
        )
        issuer_balance["percent"] = issuer_balance["count"] / issuer_balance["count"].sum()
        issuer_balance.to_csv(table_path(output_dir, "test_issuer_class_balance.csv"), index=False)

        issuer_balance["rank"] = range(1, len(issuer_balance) + 1)
        issuer_balance["cumulative_percent"] = issuer_balance["percent"].cumsum()
        top_1_share = issuer_balance["percent"].iloc[0]
        top_5_share = issuer_balance["percent"].head(5).sum()
        top_20_share = issuer_balance["percent"].head(20).sum()
        top_50_share = issuer_balance["percent"].head(50).sum()
        effective_classes = 1 / (issuer_balance["percent"] ** 2).sum()
        summary = pd.DataFrame(
            [
                {"metric": "issuer_classes", "value": len(issuer_balance)},
                {"metric": "largest_class_share", "value": top_1_share},
                {"metric": "top_5_share", "value": top_5_share},
                {"metric": "top_20_share", "value": top_20_share},
                {"metric": "top_50_share", "value": top_50_share},
                {"metric": "effective_number_of_classes", "value": effective_classes},
            ]
        )
        summary.to_csv(table_path(output_dir, "data_analysis_label_concentration.csv"), index=False)

        plt.figure(figsize=(10.5, 6.4))
        ax = sns.lineplot(data=issuer_balance, x="rank", y="cumulative_percent", color="#2F6F9F", linewidth=2.4)
        ax.scatter([1, 5, 20, 50], [top_1_share, top_5_share, top_20_share, top_50_share], color="#C44536", zorder=5)
        for x_value, y_value, label in [
            (1, top_1_share, f"Top 1: {top_1_share:.1%}"),
            (5, top_5_share, f"Top 5: {top_5_share:.1%}"),
            (20, top_20_share, f"Top 20: {top_20_share:.1%}"),
            (50, top_50_share, f"Top 50: {top_50_share:.1%}"),
        ]:
            ax.annotate(
                label,
                xy=(x_value, y_value),
                xytext=(8, 8),
                textcoords="offset points",
                fontsize=9,
                bbox={"boxstyle": "round,pad=0.2", "facecolor": "white", "edgecolor": "#D0D7DE"},
            )
        ax.yaxis.set_major_formatter(PercentFormatter(1.0))
        ax.set_xlim(1, len(issuer_balance))
        ax.set_ylim(0, 1.02)
        ax.set_xlabel("Issuer classes ranked from most to least frequent")
        ax.set_ylabel("Cumulative share of test cases")
        ax.set_title("Issuer-label concentration: a few courts dominate, many courts form a long tail")
        note = (
            f"{len(issuer_balance)} issuer classes\n"
            f"Effective classes: {effective_classes:.1f}\n"
            "Interpretation: accuracy must be paired with macro F1"
        )
        ax.text(
            0.58,
            0.12,
            note,
            transform=ax.transAxes,
            fontsize=10.5,
            bbox={"boxstyle": "round,pad=0.45", "facecolor": "#F4F6F8", "edgecolor": "#CAD3DC"},
        )
        plt.tight_layout()
        plt.savefig(figure_path(output_dir, "core_issuer_pareto_concentration.png", "core"), dpi=220, bbox_inches="tight")
        plt.close()

        top = issuer_balance.head(top_n).sort_values("count", ascending=True)
        plt.figure(figsize=(11, max(6, 0.32 * len(top) + 2)))
        ax = sns.barplot(data=top, x="count", y="issuer", color="#1565C0", errorbar=None)
        ax.set_xlabel("Test cases")
        ax.set_ylabel("True issuer label")
        ax.set_title(f"Top {len(top)} issuer classes in the test set")
        plt.tight_layout()
        plt.savefig(figure_path(output_dir, "core_issuer_class_balance_top.png", "core"), dpi=220)
        plt.close()

        story_top = issuer_balance.head(12).sort_values("count", ascending=True).copy()
        top_1_share = issuer_balance["percent"].iloc[0]
        top_5_share = issuer_balance["percent"].head(5).sum()
        long_tail_count = max(len(issuer_balance) - 12, 0)

        fig, ax = plt.subplots(figsize=(12, 7.2))
        sns.barplot(data=story_top, x="percent", y="issuer", color="#2F6F9F", errorbar=None, ax=ax)
        ax.xaxis.set_major_formatter(PercentFormatter(1.0))
        ax.set_xlabel("Share of test cases")
        ax.set_ylabel("")
        ax.set_title("Issuer distribution shows a concentrated classification problem")
        for container in ax.containers:
            ax.bar_label(container, labels=[f"{value:.1%}" for value in container.datavalues], padding=4, fontsize=9)

        note = (
            f"161 issuer classes in test set\n"
            f"Largest class: {top_1_share:.1%} of cases\n"
            f"Top 5 issuers: {top_5_share:.1%} of cases\n"
            f"Remaining long tail: {long_tail_count} issuers"
        )
        ax.text(
            0.64,
            0.08,
            note,
            transform=ax.transAxes,
            fontsize=11,
            va="bottom",
            ha="left",
            bbox={"boxstyle": "round,pad=0.45", "facecolor": "#F4F6F8", "edgecolor": "#CAD3DC"},
        )
        plt.tight_layout()
        plt.savefig(figure_path(output_dir, "core_issuer_distribution_story.png", "core"), dpi=220, bbox_inches="tight")
        plt.close()

    if not state_balance.empty and not issuer_balance.empty:
        top_issuers = issuer_balance.head(min(top_n, 15)).sort_values("count", ascending=True)
        fig, axes = plt.subplots(1, 2, figsize=(15, 6.4), gridspec_kw={"width_ratios": [1, 1.35]})

        sns.barplot(data=state_balance, x="state", y="count", color="#2A9D8F", errorbar=None, ax=axes[0])
        axes[0].set_title("State balance")
        axes[0].set_xlabel("State label")
        axes[0].set_ylabel("Test cases")
        for container in axes[0].containers:
            axes[0].bar_label(container, labels=[f"{value:,.0f}" for value in container.datavalues], padding=3, fontsize=8)

        sns.barplot(data=top_issuers, x="count", y="issuer", color="#1565C0", errorbar=None, ax=axes[1])
        axes[1].set_title(f"Top {len(top_issuers)} issuer classes")
        axes[1].set_xlabel("Test cases")
        axes[1].set_ylabel("")

        fig.suptitle("Test-set class balance: broad state labels vs. fine-grained issuer labels", y=1.02)
        plt.tight_layout()
        plt.savefig(figure_path(output_dir, "core_data_balance_overview.png", "core"), dpi=220, bbox_inches="tight")
        plt.close()


def save_report_training_architecture(output_dir: Path) -> None:
    fig, ax = plt.subplots(figsize=(12, 6.5))
    ax.axis("off")

    boxes = [
        {
            "xy": (0.07, 0.58),
            "title": "Flat state",
            "body": "Document features -> state\nBroad jurisdiction baseline",
            "color": "#264653",
        },
        {
            "xy": (0.56, 0.58),
            "title": "Flat issuer",
            "body": "Document features -> issuer\nDirect fine-grained baseline",
            "color": "#2A9D8F",
        },
        {
            "xy": (0.07, 0.20),
            "title": "Plain cascade",
            "body": "Stage 1: predict state\nStage 2: issuer model for predicted state",
            "color": "#E9C46A",
        },
        {
            "xy": (0.56, 0.20),
            "title": "Cascade + fallback",
            "body": "Use local issuer model when confident\nUse global issuer model when uncertain",
            "color": "#E76F51",
        },
    ]

    for item in boxes:
        x, y = item["xy"]
        ax.add_patch(
            plt.Rectangle(
                (x, y),
                0.37,
                0.24,
                transform=ax.transAxes,
                facecolor="#FBFCFF",
                edgecolor=item["color"],
                linewidth=2.2,
                zorder=2,
            )
        )
        ax.text(x + 0.025, y + 0.17, item["title"], transform=ax.transAxes, fontsize=16, fontweight="bold", color=item["color"])
        ax.text(x + 0.025, y + 0.07, item["body"], transform=ax.transAxes, fontsize=11.5, color="#333333", va="center")

    ax.text(0.5, 0.93, "Model training setups compared in the experiment", ha="center", transform=ax.transAxes, fontsize=20)
    ax.text(
        0.5,
        0.89,
        "All setups use the same processed legal text and metadata features; they differ in how labels are predicted.",
        ha="center",
        transform=ax.transAxes,
        fontsize=11.5,
        color="#555555",
    )
    ax.annotate("", xy=(0.56, 0.70), xytext=(0.44, 0.70), xycoords="axes fraction", arrowprops={"arrowstyle": "->", "lw": 1.8, "color": "#9AA4B2"})
    ax.annotate("", xy=(0.56, 0.32), xytext=(0.44, 0.32), xycoords="axes fraction", arrowprops={"arrowstyle": "->", "lw": 1.8, "color": "#9AA4B2"})
    ax.text(0.50, 0.51, "same features,\ndifferent prediction design", ha="center", transform=ax.transAxes, fontsize=10.5, color="#555555")

    plt.savefig(figure_path(output_dir, "core_report_training_architecture.png", "core"), dpi=220, bbox_inches="tight")
    plt.close()


def save_report_model_selection(metrics: pd.DataFrame, output_dir: Path) -> None:
    if metrics.empty or not {"algorithm", "system", "accuracy", "macro_f1"}.issubset(metrics.columns):
        return

    wanted = [
        ("random_forest_cascade", "flat_state"),
        ("svm_cascade", "flat_state"),
        ("random_forest_cascade", "cascade_with_fallback"),
        ("random_forest_cascade", "flat_issuer"),
        ("xgboost_cascade", "flat_state"),
    ]
    rows = []
    for algorithm, system in wanted:
        match = metrics[(metrics["algorithm"] == algorithm) & (metrics["system"] == system)]
        if not match.empty:
            rows.append(match.iloc[0])
    if not rows:
        return

    frame = pd.DataFrame(rows).copy()
    frame["model"] = frame["algorithm"].map(model_label)
    frame["approach"] = frame["system"].map(SYSTEM_LABELS).fillna(frame["system"])
    frame["label"] = frame["model"] + " - " + frame["approach"]
    frame = frame.sort_values("accuracy", ascending=True)
    colors = frame["model"].map(MODEL_PALETTE).fillna("#666666")

    fig, ax = plt.subplots(figsize=(11.5, 6.4))
    bars = ax.barh(frame["label"], frame["accuracy"], color=colors)
    ax.xaxis.set_major_formatter(PercentFormatter(1.0))
    ax.set_xlim(0, 1.05)
    ax.set_xlabel("Test accuracy")
    ax.set_ylabel("")
    ax.set_title("Model selection summary: Random Forest is the strongest practical choice")
    ax.grid(axis="x", alpha=0.25)

    for bar, (_, row) in zip(bars, frame.iterrows()):
        text = f"{row['accuracy']:.1%} accuracy | macro F1 {row['macro_f1']:.3f}"
        ax.text(min(row["accuracy"] + 0.015, 1.01), bar.get_y() + bar.get_height() / 2, text, va="center", fontsize=10)

    plt.tight_layout()
    plt.savefig(figure_path(output_dir, "core_report_model_selection.png", "core"), dpi=220, bbox_inches="tight")
    plt.close()


def save_report_validation_breakdown(metrics: pd.DataFrame, output_dir: Path) -> None:
    required = {"algorithm", "system", "accuracy", "wrong_issuer_correct_state", "wrong_state_wrong_issuer"}
    if metrics.empty or not required.issubset(metrics.columns):
        return

    wanted = [
        ("random_forest_cascade", "flat_issuer"),
        ("random_forest_cascade", "cascade_with_fallback"),
        ("svm_cascade", "flat_issuer"),
        ("svm_cascade", "cascade_with_fallback"),
    ]
    rows = []
    for algorithm, system in wanted:
        match = metrics[(metrics["algorithm"] == algorithm) & (metrics["system"] == system)]
        if not match.empty:
            row = match.iloc[0].copy()
            wrong_total = row["wrong_issuer_correct_state"] + row["wrong_state_wrong_issuer"]
            if pd.isna(wrong_total) or wrong_total <= 0 or row["accuracy"] >= 1:
                continue
            estimated_total = wrong_total / (1 - row["accuracy"])
            row["correct_issuer_share"] = row["accuracy"]
            row["correct_state_wrong_issuer_share"] = row["wrong_issuer_correct_state"] / estimated_total
            row["wrong_state_and_issuer_share"] = row["wrong_state_wrong_issuer"] / estimated_total
            rows.append(row)
    if not rows:
        return

    frame = pd.DataFrame(rows)
    frame["label"] = frame["algorithm"].map(model_label) + " - " + frame["system"].map(SYSTEM_LABELS).fillna(frame["system"])
    frame = frame.iloc[::-1]

    categories = [
        ("correct_issuer_share", "Correct issuer", "#2A9D8F"),
        ("correct_state_wrong_issuer_share", "Correct state, wrong issuer", "#E9C46A"),
        ("wrong_state_and_issuer_share", "Wrong state and issuer", "#E76F51"),
    ]

    fig, ax = plt.subplots(figsize=(12, 5.7))
    left = pd.Series(0, index=frame.index, dtype=float)
    for column, label, color in categories:
        ax.barh(frame["label"], frame[column], left=left, color=color, label=label)
        left = left + frame[column]

    ax.xaxis.set_major_formatter(PercentFormatter(1.0))
    ax.set_xlim(0, 1)
    ax.set_xlabel("Share of test cases")
    ax.set_ylabel("")
    ax.set_title("Validation view: where issuer predictions succeed or fail")
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, -0.28), ncols=3, frameon=True)
    ax.grid(axis="x", alpha=0.25)

    for idx, row in frame.iterrows():
        ax.text(row["correct_issuer_share"] / 2, row["label"], f"{row['correct_issuer_share']:.1%}", ha="center", va="center", fontsize=10, color="white", fontweight="bold")

    plt.tight_layout()
    plt.savefig(figure_path(output_dir, "core_report_validation_breakdown.png", "core"), dpi=220, bbox_inches="tight")
    plt.close()


def main() -> None:
    args = parse_args()
    output_dir = ensure_dir(args.output_dir)
    sns.set_theme(style="whitegrid", context="notebook", font_scale=1.08)
    plt.rcParams.update({
        "figure.titlesize": 16,
        "axes.titlesize": 15,
        "axes.labelsize": 12,
        "xtick.labelsize": 10,
        "ytick.labelsize": 10,
        "legend.fontsize": 10,
        "legend.title_fontsize": 11,
    })

    if args.metrics_csv is not None:
        metrics = prepare_metrics(load_metrics_from_csv(args.metrics_csv))
    else:
        metrics = prepare_metrics(load_metrics(args.result_dirs, "metrics_summary.csv"))
    metrics_by_split = load_metrics(args.result_dirs, "metrics_by_split.csv")

    if not metrics.empty:
        metrics.to_csv(table_path(output_dir, "metrics_summary_combined.csv"), index=False)
    if not metrics_by_split.empty:
        metrics_by_split.to_csv(table_path(output_dir, "metrics_by_split_combined.csv"), index=False)

    save_core_metric_bars(metrics, output_dir)
    save_core_model_summary(metrics, output_dir)
    save_core_error_story(metrics, output_dir)
    save_metric_overview(metrics, output_dir, args.metrics)
    save_accuracy_vs_macro_f1(metrics, output_dir)
    save_performance_heatmaps(metrics, output_dir)
    save_cascade_delta(metrics, output_dir)
    save_selected_config_plot(args.result_dirs, output_dir)
    save_split_metrics(metrics_by_split, output_dir)
    save_error_breakdown(metrics, output_dir)
    save_split_summary(args.result_dirs, output_dir)
    save_per_class_plots(args.result_dirs, output_dir, args.top_n)
    save_confusion_heatmaps(args.result_dirs, output_dir, args.top_n)
    save_top_confusion_pairs(args.result_dirs, output_dir, args.top_n)
    save_prediction_correctness(args.result_dirs, output_dir)
    save_class_balance_plots(args.result_dirs, output_dir, args.top_n)
    save_report_training_architecture(output_dir)
    save_report_model_selection(metrics, output_dir)
    save_report_validation_breakdown(metrics, output_dir)

    print(f"Wrote visualizations to {output_dir}")


if __name__ == "__main__":
    main()
