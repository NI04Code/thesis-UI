#!/usr/bin/env python3
"""Generate the event-aligned Actual Usage Evictor failure heatmap."""

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


def failure_counts(run_dir: Path) -> tuple[np.ndarray, int, int]:
    event_time = parse_time((run_dir / "event-time.txt").read_text())
    failures = np.zeros(WINDOW_SECONDS, dtype=int)
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
                failures[int(elapsed)] += 1

    return failures, int(failures.sum()), completed


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
        default=Path("assets/pics/actual-usage/failure_timeline_heatmap.png"),
    )
    args = parser.parse_args()

    rows = []
    totals = {}
    eviction_offsets = {}
    for run, relative_path in RUN_PATHS.items():
        run_dir = args.data_root / relative_path
        counts, failed, completed = failure_counts(run_dir)
        rows.append(counts)
        totals[run] = (failed, completed)
        eviction_offsets[run] = api_eviction_offset(run_dir)

    values = np.vstack(rows)
    colors = [
        "#f7f7f7",
        "#fee8c8",
        "#fdbb84",
        "#fc8d59",
        "#e34a33",
        "#b30000",
    ]
    bounds = [-0.5, 0.5, 2.5, 4.5, 6.5, 7.5, 8.5]
    norm = BoundaryNorm(bounds, len(colors))

    fig, ax = plt.subplots(figsize=(12.5, 4.4))
    image = ax.imshow(
        values,
        aspect="auto",
        cmap=ListedColormap(colors),
        norm=norm,
        interpolation="nearest",
        extent=(0, WINDOW_SECONDS, len(RUN_PATHS), 0),
    )

    ax.set_xticks(np.arange(0, WINDOW_SECONDS, 5))
    ax.set_xticklabels(np.arange(0, WINDOW_SECONDS, 5))
    ax.set_xticks(np.arange(0, WINDOW_SECONDS + 1, 1), minor=True)
    ax.set_yticks(np.arange(len(RUN_PATHS)) + 0.5)
    ax.set_yticklabels(
        [
            f"{run}   ({totals[run][0]}/{totals[run][1]})"
            for run in RUN_PATHS
        ]
    )
    ax.set_yticks(np.arange(0, len(RUN_PATHS) + 1, 1), minor=True)
    ax.grid(which="minor", color="white", linewidth=0.8)
    ax.tick_params(which="minor", bottom=False, left=False)
    ax.tick_params(axis="both", labelsize=10)
    ax.set_xlabel("Seconds after Descheduler event", fontsize=11)
    ax.set_ylabel("Run (failed/completed)", fontsize=11)

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
    ax.axhline(4, color="#555555", linewidth=1.4)

    for row, run in enumerate(RUN_PATHS):
        offset = eviction_offsets[run]
        if offset is None:
            continue
        ax.vlines(
            offset,
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
        image,
        ax=ax,
        pad=0.015,
        fraction=0.035,
        ticks=[0, 2, 4, 6, 8],
    )
    colorbar.set_label("HTTP failures completed per second", fontsize=10)
    colorbar.ax.tick_params(labelsize=9)

    for spine in ax.spines.values():
        spine.set_visible(False)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(args.output, dpi=240, bbox_inches="tight")
    plt.close(fig)

    for run, (failed, completed) in totals.items():
        eviction = eviction_offsets[run]
        eviction_text = f", API eviction at {eviction:.3f} s" if eviction else ""
        print(
            f"{run}: {failed}/{completed} failures in [0,{WINDOW_SECONDS}) s"
            f"{eviction_text}"
        )
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
