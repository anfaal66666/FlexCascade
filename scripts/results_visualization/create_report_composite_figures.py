"""Create compact composite figures for the final project report.

The goal is not to dump every available metric into the report. These panels
summarize the story with a small number of readable plots:
1. data/training evidence
2. model performance and validation
"""

from pathlib import Path
import textwrap

import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
import pandas as pd
import seaborn as sns


ROOT = Path(__file__).resolve().parents[2]
TABLE_DIR = ROOT / "results" / "result_visualization_plots" / "tables"
OUT_DIR = ROOT / "results" / "result_visualization_plots" / "figures" / "core"


PALETTE = {
    "blue": "#2F6B9A",
    "green": "#2E7D32",
    "orange": "#D47A22",
    "red": "#B43C35",
    "gray": "#5E6770",
    "light_gray": "#EEF1F4",
    "dark": "#263238",
}


def percent_axis(ax, axis="y"):
    if axis == "y":
        ax.yaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=0))
    else:
        ax.xaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=0))


def finish_panel(fig, title, subtitle, outfile):
    fig.suptitle(title, fontsize=16, fontweight="bold", y=0.985, color=PALETTE["dark"])
    fig.text(0.5, 0.925, subtitle, ha="center", fontsize=9.4, color=PALETTE["gray"])
    for ax in fig.axes:
        ax.tick_params(axis="both", labelsize=8.8)
        ax.xaxis.label.set_size(9.5)
        ax.yaxis.label.set_size(9.5)
    fig.tight_layout(rect=[0, 0, 1, 0.875], w_pad=2.4)
    fig.savefig(outfile, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def make_training_panel():
    split = pd.read_csv(TABLE_DIR / "split_summary_combined.csv")
    issuer = pd.read_csv(TABLE_DIR / "test_issuer_class_balance.csv")
    concentration = pd.read_csv(TABLE_DIR / "data_analysis_label_concentration.csv")

    fig, axes = plt.subplots(1, 3, figsize=(15.5, 4.8))

    # 1. Split sizes
    ax = axes[0]
    split_order = ["train", "validation", "test"]
    split = split.set_index("split").loc[split_order].reset_index()
    bars = ax.bar(
        split["split"].str.title(),
        split["rows"],
        color=[PALETTE["blue"], PALETTE["orange"], PALETTE["green"]],
        width=0.62,
    )
    ax.set_title("Training Evidence: Split Design", fontsize=11, fontweight="bold")
    ax.set_ylabel("Rows")
    ax.set_xlabel("")
    ax.grid(axis="y", alpha=0.25)
    for bar in bars:
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 1700,
            f"{bar.get_height():,.0f}",
            ha="center",
            fontsize=8.4,
            fontweight="bold",
        )
    ax.set_ylim(0, split["rows"].max() * 1.18)

    # 2. Top issuer concentration as a Pareto-style line
    ax = axes[1]
    issuer = issuer.sort_values("count", ascending=False).reset_index(drop=True)
    issuer["rank"] = issuer.index + 1
    issuer["cumulative_share"] = issuer["percent"].cumsum()
    subset = issuer[issuer["rank"] <= 50]
    ax.plot(
        subset["rank"],
        subset["cumulative_share"],
        color=PALETTE["green"],
        linewidth=3,
        marker="o",
        markersize=3,
    )
    points = {1: 0.23167633070558344, 5: 0.48696983516841486, 20: 0.7328490455404262}
    for rank, share in points.items():
        ax.scatter([rank], [share], s=65, color=PALETTE["orange"], zorder=5)
        ax.text(rank + 1.4, share, f"Top {rank}: {share:.1%}", va="center", fontsize=8.0)
    ax.set_title("Why Macro F1 Matters", fontsize=11, fontweight="bold")
    ax.set_xlabel("Issuer rank")
    ax.set_ylabel("Cumulative test cases")
    ax.set_xlim(0, 52)
    ax.set_ylim(0, 1.0)
    percent_axis(ax)
    ax.grid(alpha=0.25)

    # 3. Feature design summary
    ax = axes[2]
    feature_groups = pd.DataFrame(
        {
            "Feature group": ["Legal text", "Case metadata", "Document structure"],
            "Signals used": [2, 5, 3],
            "Examples": [
                "TF-IDF unigrams + bigrams",
                "year, citation, docket, lengths",
                "uppercase, digits, punctuation",
            ],
        }
    )
    bars = ax.barh(
        feature_groups["Feature group"],
        feature_groups["Signals used"],
        color=[PALETTE["blue"], PALETTE["green"], PALETTE["orange"]],
        height=0.55,
    )
    ax.set_title("Feature Engineering Inputs", fontsize=11, fontweight="bold")
    ax.set_xlabel("Number of signal types")
    ax.set_xlim(0, 6.5)
    ax.grid(axis="x", alpha=0.25)
    ax.invert_yaxis()
    for i, row in feature_groups.iterrows():
        ax.text(
            row["Signals used"] + 0.12,
            i,
            textwrap.fill(row["Examples"], width=26),
            va="center",
            fontsize=7.8,
            color=PALETTE["dark"],
        )

    finish_panel(
        fig,
        "Data and Training Evidence",
        "The model was trained on a stratified split, but issuer labels are concentrated; features combine legal text and metadata.",
        OUT_DIR / "report_panel_training_1x3.png",
    )


def make_performance_panel():
    metrics = pd.read_csv(TABLE_DIR / "metrics_summary_combined.csv")
    correctness = pd.read_csv(TABLE_DIR / "prediction_correctness_counts.csv")

    metrics["approach"] = metrics["system_label"]
    metrics["label"] = metrics["model"] + " - " + metrics["approach"]

    top_models = metrics.sort_values("accuracy", ascending=False).head(5).copy()
    top_models = top_models.iloc[::-1]

    compare = metrics[
        (metrics["model"].isin(["Random Forest", "SVM", "XGBoost"]))
        & (metrics["system"] == "flat_state")
    ].copy()
    compare = compare.sort_values("accuracy")

    rf_issuer = correctness[
        (correctness["model"] == "Random Forest")
        & (correctness["system"].isin(["flat_issuer", "cascade_with_fallback"]))
    ].copy()
    rf_issuer["system_label"] = pd.Categorical(
        rf_issuer["system_label"],
        ["Flat issuer", "Cascade + fallback"],
        ordered=True,
    )
    rf_pivot = (
        rf_issuer.pivot_table(
            index="system_label", columns="category", values="count", aggfunc="sum", observed=False
        )
        .fillna(0)
        .loc[["Flat issuer", "Cascade + fallback"]]
    )
    rf_pivot = rf_pivot.div(rf_pivot.sum(axis=1), axis=0)

    fig, axes = plt.subplots(1, 3, figsize=(16.2, 4.9))

    # 1. Top model leaderboard
    ax = axes[0]
    colors = [
        PALETTE["green"] if "Random Forest" in label else PALETTE["blue"] if "SVM" in label else PALETTE["red"]
        for label in top_models["label"]
    ]
    ax.barh(top_models["label"], top_models["accuracy"], color=colors, height=0.55)
    ax.set_title("Top Models by Accuracy", fontsize=11, fontweight="bold")
    ax.set_xlabel("Accuracy")
    ax.set_xlim(0.90, 1.0)
    percent_axis(ax, axis="x")
    ax.grid(axis="x", alpha=0.25)
    for y, val in enumerate(top_models["accuracy"]):
        ax.text(val + 0.001, y, f"{val:.2%}", va="center", fontsize=8.1, fontweight="bold")

    # 2. Accuracy vs macro F1 as paired bars for flat state benchmark
    ax = axes[1]
    x = range(len(compare))
    width = 0.35
    ax.bar([i - width / 2 for i in x], compare["accuracy"], width, label="Accuracy", color=PALETTE["blue"])
    ax.bar([i + width / 2 for i in x], compare["macro_f1"], width, label="Macro F1", color=PALETTE["orange"])
    ax.set_title("Flat State Benchmark", fontsize=11, fontweight="bold")
    ax.set_xticks(list(x))
    ax.set_xticklabels(compare["model"], rotation=18, ha="right", fontsize=8.5)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Score")
    percent_axis(ax)
    ax.legend(frameon=False, loc="upper left", fontsize=8.0)
    ax.grid(axis="y", alpha=0.25)

    # 3. Validation error composition
    ax = axes[2]
    desired_order = ["Correct issuer", "Correct state, wrong issuer", "Wrong state and issuer"]
    colors = [PALETTE["green"], PALETTE["orange"], PALETTE["red"]]
    bottom = [0] * len(rf_pivot)
    xlabels = list(rf_pivot.index)
    for cat, color in zip(desired_order, colors):
        vals = rf_pivot[cat] if cat in rf_pivot.columns else [0] * len(rf_pivot)
        ax.bar(xlabels, vals, bottom=bottom, label=cat, color=color, width=0.58)
        bottom = [b + v for b, v in zip(bottom, vals)]
    ax.set_title("Issuer Validation Outcome", fontsize=11, fontweight="bold")
    ax.set_ylabel("Share of test cases")
    ax.set_ylim(0, 1)
    percent_axis(ax)
    ax.grid(axis="y", alpha=0.25)
    ax.legend(frameon=False, fontsize=7.8, loc="lower center", bbox_to_anchor=(0.5, -0.30), ncol=1)

    finish_panel(
        fig,
        "Model Performance and Validation",
        "Random Forest leads the benchmark; cascade fallback gives a small issuer-level robustness gain.",
        OUT_DIR / "report_panel_performance_1x3.png",
    )


def main():
    sns.set_theme(style="whitegrid", font="DejaVu Sans", context="paper")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    make_training_panel()
    make_performance_panel()
    print("Created:")
    print(OUT_DIR / "report_panel_training_1x3.png")
    print(OUT_DIR / "report_panel_performance_1x3.png")


if __name__ == "__main__":
    main()
