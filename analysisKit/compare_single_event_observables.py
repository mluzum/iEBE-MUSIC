#!/usr/bin/env python3
"""Compare single-event observables across multiple runs.

This script overlays the exported observables produced by
`export_single_event_observables.py` for each run directory.

Expected input layout for each run directory:
  <run>/event_0/EVENT_RESULTS_0/observables/
    - charged_hadron_pT_observables.dat
    - charged_hadron_eta_observables.dat
    - summary.txt
"""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


@dataclass
class RunData:
    label: str
    run_dir: str
    pT: np.ndarray
    pT_table: np.ndarray
    eta: np.ndarray
    eta_table: np.ndarray
    summary: Dict[str, float]


def parse_summary(summary_path: str) -> Dict[str, float]:
    summary: Dict[str, float] = {}
    if not os.path.isfile(summary_path):
        return summary
    with open(summary_path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or "=" not in line:
                continue
            key, value = [chunk.strip() for chunk in line.split("=", 1)]
            try:
                summary[key] = float(value)
            except ValueError:
                continue
    return summary


def load_table(path: str) -> np.ndarray:
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    return np.loadtxt(path)


def load_run(label: str, run_dir: str) -> RunData:
    obs_dir = os.path.join(run_dir, "event_0", "EVENT_RESULTS_0", "observables")
    pT_table = load_table(
        os.path.join(obs_dir, "charged_hadron_pT_observables.dat"))
    eta_table = load_table(
        os.path.join(obs_dir, "charged_hadron_eta_observables.dat"))
    summary = parse_summary(os.path.join(obs_dir, "summary.txt"))
    return RunData(
        label=label,
        run_dir=run_dir,
        pT=pT_table[:, 0],
        pT_table=pT_table,
        eta=eta_table[:, 0],
        eta_table=eta_table,
        summary=summary,
    )


def plot_pT_comparison(runs: Sequence[RunData], outdir: str) -> None:
    fig, axes = plt.subplots(5,
                             1,
                             figsize=(8.8, 14.0),
                             sharex=True,
                             constrained_layout=True)

    for run in runs:
        axes[0].plot(run.pT, run.pT_table[:, 1], lw=2, label=run.label)
    axes[0].set_ylabel(r"$dN/d^2p_T$")
    axes[0].set_yscale("log")
    axes[0].grid(alpha=0.25)
    axes[0].legend(frameon=False)
    axes[0].set_title("Charged-hadron spectrum comparison")

    # vn columns: pT, dN, then (re, im, abs) for v1..v4
    for harmonic in range(1, 5):
        abs_col = 2 + (harmonic - 1)*3 + 2
        for run in runs:
            axes[harmonic].plot(run.pT,
                                run.pT_table[:, abs_col],
                                lw=2,
                                label=run.label)
        axes[harmonic].set_ylabel(rf"$|v_{harmonic}(p_T)|$")
        axes[harmonic].grid(alpha=0.25)
        axes[harmonic].legend(frameon=False)

    axes[-1].set_xlabel(r"$p_T$ [GeV]")

    fig.savefig(os.path.join(outdir, "comparison_charged_hadron_pT.png"),
                dpi=180)
    plt.close(fig)


def plot_eta_comparison(runs: Sequence[RunData], outdir: str) -> None:
    fig, ax = plt.subplots(figsize=(8.6, 4.9), constrained_layout=True)
    for run in runs:
        ax.plot(run.eta, run.eta_table[:, 1], lw=2, label=run.label)
    ax.set_xlabel(r"$\eta$")
    ax.set_ylabel(r"$dN_{ch}/d\eta$")
    ax.set_title("Charged-hadron rapidity density comparison")
    ax.grid(alpha=0.25)
    ax.legend(frameon=False)
    fig.savefig(os.path.join(outdir, "comparison_charged_hadron_eta.png"),
                dpi=180)
    plt.close(fig)


def plot_summary_comparison(runs: Sequence[RunData], outdir: str) -> None:
    metrics = ["Nch", "mean_pT_ch", "ET"]
    labels = [run.label for run in runs]
    values = np.array([
        [run.summary.get(metric, np.nan) for metric in metrics] for run in runs
    ])

    fig, axes = plt.subplots(3, 1, figsize=(8.4, 8.5), constrained_layout=True)
    x = np.arange(len(runs))
    for i, metric in enumerate(metrics):
        axes[i].bar(x, values[:, i], color=["#1f77b4", "#ff7f0e"][:len(runs)])
        axes[i].set_xticks(x)
        axes[i].set_xticklabels(labels)
        axes[i].set_ylabel(metric)
        axes[i].grid(axis="y", alpha=0.25)
        axes[i].set_title(metric)
    axes[0].set_title("Summary observable comparison")
    fig.savefig(os.path.join(outdir, "comparison_summary.png"), dpi=180)
    plt.close(fig)


def write_delta_table(runs: Sequence[RunData], outdir: str) -> None:
    metrics = ["Nch", "mean_pT_ch", "ET"]
    with open(os.path.join(outdir, "comparison_summary.txt"),
              "w",
              encoding="utf-8") as handle:
        handle.write("metric")
        for run in runs:
            handle.write(f"  {run.label}")
        handle.write("  delta(last-first)\n")
        for metric in metrics:
            handle.write(metric)
            vals = []
            for run in runs:
                val = run.summary.get(metric, np.nan)
                vals.append(val)
                handle.write(f"  {val:.8e}")
            if len(vals) >= 2 and np.all(np.isfinite(vals[:2])):
                handle.write(f"  {(vals[-1] - vals[0]):.8e}")
            else:
                handle.write("  nan")
            handle.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("runs", nargs="+", help="Run directories to compare")
    parser.add_argument("--labels",
                        nargs="*",
                        default=None,
                        help="Optional labels for the runs")
    parser.add_argument("--outdir",
                        default="comparison_observables",
                        help="Output directory for comparison plots")
    args = parser.parse_args()

    if args.labels is not None and len(args.labels) not in (0, len(args.runs)):
        raise ValueError(
            "If provided, --labels must have the same length as runs")

    labels = args.labels if args.labels else [
        f"run{i+1}" for i in range(len(args.runs))
    ]
    runs = [
        load_run(label, run_dir) for label, run_dir in zip(labels, args.runs)
    ]

    os.makedirs(args.outdir, exist_ok=True)
    plot_pT_comparison(runs, args.outdir)
    plot_eta_comparison(runs, args.outdir)
    plot_summary_comparison(runs, args.outdir)
    write_delta_table(runs, args.outdir)
    print(f"Wrote comparison outputs to {args.outdir}")


if __name__ == "__main__":
    main()
