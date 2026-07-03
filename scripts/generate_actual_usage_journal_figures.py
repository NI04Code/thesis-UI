#!/usr/bin/env python3
"""Generate HNU/LNU figures for the Actual Usage Evictor journal paper."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.lines import Line2D


RUN_PATHS = {
    "H0": "results/highnodeutilization/h0-load/20260614-162913",
    "H1": "results/highnodeutilization/h1-load/20260614-134836",
    "L0": "results/lownodeutilization/l0-load/20260614-182752",
    "L1": "results/lownodeutilization/l1-load/20260614-183116",
}
WINDOW_SECONDS = 30


def parse_time(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.strip().replace("Z", "+00:00"))


def collect_run(run_dir: Path) -> tuple[np.ndarray, int, int, list[float]]:
    event_time = parse_time((run_dir / "event-time.txt").read_text())
    failures = np.zeros(WINDOW_SECONDS, dtype=int)
    completed = 0
    fail_times: list[float] = []

    with (run_dir / "api-load.json").open() as source:
        for line in source:
            item = json.loads(line)
            if item.get("metric") != "http_req_duration":
                continue
            data = item.get("data", {})
            if not data.get("time"):
                continue
            elapsed = (parse_time(data["time"]) - event_time).total_seconds()
            if not 0 <= elapsed < WINDOW_SECONDS:
                continue
            completed += 1
            status = str(data.get("tags", {}).get("status", ""))
            if not status.startswith("2"):
                failures[int(elapsed)] += 1
                fail_times.append(elapsed)

    return failures, int(failures.sum()), completed, fail_times


def api_eviction_offset(run_dir: Path) -> float | None:
    event_time = parse_time((run_dir / "event-time.txt").read_text())
    pattern = re.compile(
        r"^[A-Z]\d{4} (?P<time>\d{2}:\d{2}:\d{2}\.\d+).*"
        r'"Evicted pod".*pod="[^"]*/workload-api-(?!fallback-)[^"]*"'
    )
    for line in (run_dir / "descheduler.log").read_text().splitlines():
        match = pattern.search(line)
        if not match:
            continue
        eviction_time = parse_time(
            f"{event_time.date().isoformat()}T{match.group('time')}+00:00"
        )
        return (eviction_time - event_time).total_seconds()
    return None


def observed_failure_span(fail_times: list[float]) -> float:
    return max(fail_times) - min(fail_times) if fail_times else 0.0


def generate_heatmap(
    details: dict[str, dict[str, object]],
    output: Path,
) -> None:
    values = np.vstack([details[run]["failures"] for run in RUN_PATHS])
    colors = ["#f7f7f7", "#fee8c8", "#fdbb84", "#fc8d59", "#e34a33", "#b30000"]
    bounds = [-0.5, 0.5, 2.5, 4.5, 6.5, 7.5, 8.5]
    norm = BoundaryNorm(bounds, len(colors))

    fig, ax = plt.subplots(figsize=(11.2, 3.5))
    image = ax.imshow(
        values,
        aspect="auto",
        cmap=ListedColormap(colors),
        norm=norm,
        interpolation="nearest",
        extent=(0, WINDOW_SECONDS, len(RUN_PATHS), 0),
    )
    ax.set_xticks(np.arange(0, WINDOW_SECONDS, 5))
    ax.set_xticks(np.arange(0, WINDOW_SECONDS + 1, 1), minor=True)
    ax.set_yticks(np.arange(len(RUN_PATHS)) + 0.5)
    ax.set_yticklabels(
        [
            f"{run}   ({details[run]['failed']}/{details[run]['completed']})"
            for run in RUN_PATHS
        ]
    )
    ax.set_yticks(np.arange(0, len(RUN_PATHS) + 1, 1), minor=True)
    ax.grid(which="minor", color="white", linewidth=0.8)
    ax.tick_params(which="minor", bottom=False, left=False)
    ax.set_xlabel("Seconds after Descheduler event")
    ax.set_ylabel("Run (failed/completed)")

    for row in range(values.shape[0]):
        for second in range(values.shape[1]):
            value = values[row, second]
            if value:
                ax.text(
                    second + 0.5,
                    row + 0.5,
                    str(value),
                    ha="center",
                    va="center",
                    color="white" if value >= 5 else "#4a1a12",
                    fontsize=8.5,
                    fontweight="bold",
                )

    ax.axhline(2, color="#555555", linewidth=1.4)
    for row, run in enumerate(RUN_PATHS):
        offset = details[run]["eviction"]
        if offset is not None:
            ax.vlines(
                float(offset),
                row + 0.06,
                row + 0.94,
                color="#0066cc",
                linewidth=2.2,
                linestyle="--",
                zorder=4,
            )
    ax.legend(
        handles=[
            Line2D(
                [0],
                [0],
                color="#0066cc",
                linewidth=2.2,
                linestyle="--",
                label="API eviction",
            )
        ],
        loc="upper right",
        frameon=False,
        fontsize=9,
    )
    colorbar = fig.colorbar(
        image, ax=ax, pad=0.015, fraction=0.035, ticks=[0, 2, 4, 6, 8]
    )
    colorbar.set_label("HTTP failures completed per second")
    for spine in ax.spines.values():
        spine.set_visible(False)

    output.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(output, dpi=240, bbox_inches="tight")
    plt.close(fig)


def generate_summary(
    details: dict[str, dict[str, object]],
    output: Path,
) -> None:
    pairs = [("H0", "H1"), ("L0", "L1")]
    labels = ["HighNodeUtil\n(H0 / H1)", "LowNodeUtil\n(L0 / L1)"]
    control_color = "#d95f02"
    treatment_color = "#1b9e77"
    x = np.arange(len(pairs))
    width = 0.32

    control_rates = [
        100 * int(details[c]["failed"]) / int(details[c]["completed"])
        for c, _ in pairs
    ]
    treatment_rates = [
        100 * int(details[t]["failed"]) / int(details[t]["completed"])
        for _, t in pairs
    ]
    control_durations = [float(details[c]["duration"]) for c, _ in pairs]
    treatment_durations = [float(details[t]["duration"]) for _, t in pairs]

    fig, axes = plt.subplots(1, 2, figsize=(11.2, 4.1))
    panels = [
        (
            axes[0],
            control_rates,
            treatment_rates,
            "HTTP Failure Rate (%)",
            lambda value: f"{value:.2f}%",
        ),
        (
            axes[1],
            control_durations,
            treatment_durations,
            "Observed Failure Span (s)",
            lambda value: f"{value:.3f} s",
        ),
    ]

    for ax, controls, treatments, ylabel, formatter in panels:
        control_bars = ax.bar(
            x - width / 2,
            controls,
            width,
            label="Control (DefaultEvictor)",
            color=control_color,
        )
        treatment_bars = ax.bar(
            x + width / 2,
            treatments,
            width,
            label="Treatment (+ActualUsageEvictor)",
            color=treatment_color,
        )
        maximum = max(controls + treatments)
        offset = maximum * 0.045
        for bars, values in (
            (control_bars, controls),
            (treatment_bars, treatments),
        ):
            for bar, value in zip(bars, values):
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    value + offset,
                    formatter(value),
                    ha="center",
                    va="bottom",
                    fontsize=9,
                    fontweight="bold",
                )
        ax.set_xticks(x)
        ax.set_xticklabels(labels)
        ax.set_ylabel(ylabel)
        ax.set_ylim(0, maximum * 1.28)
        ax.yaxis.grid(True, linestyle="--", alpha=0.35)
        ax.set_axisbelow(True)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

    axes[0].set_title("(a)", loc="left", fontweight="bold")
    axes[1].set_title("(b)", loc="left", fontweight="bold")
    handles, legend_labels = axes[0].get_legend_handles_labels()
    fig.legend(
        handles,
        legend_labels,
        loc="upper center",
        ncol=2,
        frameon=False,
        bbox_to_anchor=(0.5, 1.03),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    fig.savefig(output, dpi=240, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path("../descheduler-custom-real-usage-fixed")
        / "experiments"
        / "actual-usage-evictor-v2",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("assets/pics/actual-usage"),
    )
    args = parser.parse_args()

    details: dict[str, dict[str, object]] = {}
    for run, relative_path in RUN_PATHS.items():
        run_dir = args.data_root / relative_path
        failures, failed, completed, fail_times = collect_run(run_dir)
        details[run] = {
            "failures": failures,
            "failed": failed,
            "completed": completed,
            "duration": observed_failure_span(fail_times),
            "eviction": api_eviction_offset(run_dir),
        }

    heatmap = args.output_dir / "failure_timeline_hnu_lnu.png"
    summary = args.output_dir / "availability_summary_hnu_lnu.png"
    generate_heatmap(details, heatmap)
    generate_summary(details, summary)

    for run, values in details.items():
        failed = int(values["failed"])
        completed = int(values["completed"])
        rate = 100 * failed / completed if completed else 0.0
        print(
            f"{run}: {failed}/{completed} ({rate:.2f}%), "
            f"failure_span={float(values['duration']):.3f}s, "
            f"eviction={values['eviction']}"
        )
    print(f"Wrote {heatmap}")
    print(f"Wrote {summary}")


if __name__ == "__main__":
    main()
