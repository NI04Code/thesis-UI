#!/usr/bin/env python3
"""Generate the Actual Usage Evictor HTTP failure-rate bar chart."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


RUN_PATHS = {
    "R0": "results/walkthrough/r0-load/20260610-152748",
    "R1": "results/walkthrough/r1-load/20260610-153257",
    "H0": "hnu/results/h0-load/20260614-162913",
    "H1": "hnu/results/h1-load/20260614-134836",
    "L0": "lnu/results/l0-load/20260614-182752",
    "L1": "lnu/results/l1-load/20260614-183116",
}

WINDOW_SECONDS = 30


def parse_time(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.strip().replace("Z", "+00:00"))


def failure_rate(run_dir: Path) -> tuple[float, int, int]:
    """Return (failure_rate, failed, completed) for the 30s post-event window."""
    event_time = parse_time((run_dir / "event-time.txt").read_text())
    failed = 0
    completed = 0

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
                failed += 1

    rate = failed / completed * 100 if completed else 0.0
    return rate, failed, completed


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
        "--output",
        type=Path,
        default=Path("assets/pics/actual-usage/failure_rate_bar.png"),
    )
    args = parser.parse_args()

    runs = list(RUN_PATHS.keys())
    rates = []
    details = {}
    for run in runs:
        run_dir = args.data_root / RUN_PATHS[run]
        rate, failed, completed = failure_rate(run_dir)
        rates.append(rate)
        details[run] = (rate, failed, completed)

    # Group into control/treatment pairs
    pairs = [("R0", "R1"), ("H0", "H1"), ("L0", "L1")]
    pair_labels = [
        "ResourceDefrag\n(R0 / R1)",
        "HighNodeUtil\n(H0 / H1)",
        "LowNodeUtil\n(L0 / L1)",
    ]

    control_rates = [details[c][0] for c, _ in pairs]
    treatment_rates = [details[t][0] for _, t in pairs]

    x = np.arange(len(pairs))
    width = 0.32

    fig, ax = plt.subplots(figsize=(8, 4.5))

    bars_ctrl = ax.bar(
        x - width / 2,
        control_rates,
        width,
        label="Control (DefaultEvictor only)",
        color="#e34a33",
        edgecolor="white",
        linewidth=0.8,
    )
    bars_treat = ax.bar(
        x + width / 2,
        treatment_rates,
        width,
        label="Treatment (+ActualUsageEvictor)",
        color="#31a354",
        edgecolor="white",
        linewidth=0.8,
    )

    # Annotate bars with exact values
    for bar, (ctrl_name, _) in zip(bars_ctrl, pairs):
        rate, failed, completed = details[ctrl_name]
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.4,
            f"{rate:.2f}%\n({failed}/{completed})",
            ha="center",
            va="bottom",
            fontsize=9,
            fontweight="bold",
            color="#b30000",
        )

    for bar, (_, treat_name) in zip(bars_treat, pairs):
        rate, failed, completed = details[treat_name]
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.4,
            f"{rate:.2f}%\n({failed}/{completed})",
            ha="center",
            va="bottom",
            fontsize=9,
            fontweight="bold",
            color="#006d2c",
        )

    ax.set_ylabel("HTTP Failure Rate (%)", fontsize=11)
    ax.set_xticks(x)
    ax.set_xticklabels(pair_labels, fontsize=10)
    ax.set_ylim(0, max(control_rates) * 1.35)
    ax.legend(fontsize=9, loc="upper right", frameon=True, edgecolor="#cccccc")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(axis="both", labelsize=10)
    ax.yaxis.grid(True, linestyle="--", alpha=0.4)
    ax.set_axisbelow(True)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(args.output, dpi=240, bbox_inches="tight")
    plt.close(fig)

    for run, (rate, failed, completed) in details.items():
        print(f"{run}: {rate:.2f}% ({failed}/{completed})")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
