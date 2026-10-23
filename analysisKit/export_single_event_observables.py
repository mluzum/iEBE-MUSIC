#!/usr/bin/env python3
"""Export and plot observables for a single event stored in QnVectors pickle.

This script is intended as a lightweight sanity-check helper for a single-event
run. It writes a few text tables and PNG plots for the charged-hadron spectrum,
charged-hadron vn(pT), and dNch/deta.
"""

from __future__ import annotations

import argparse
import os
import pickle
from typing import Any, Dict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def load_event(database_file: str,
               event_name: str | None) -> tuple[str, Dict[str, Any]]:
    with open(database_file, "rb") as pf:
        data = pickle.load(pf)

    if not data:
        raise ValueError(f"No events found in {database_file}")

    if event_name is None:
        event_name = next(iter(data.keys()))

    if event_name not in data:
        raise KeyError(f"Event {event_name} not found in {database_file}")

    return event_name, data[event_name]


def ensure_dir(dir_path: str) -> None:
    os.makedirs(dir_path, exist_ok=True)


def write_text_table(file_path: str, header: str, table: np.ndarray) -> None:
    np.savetxt(file_path, table, fmt="%.8e", header=header)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pickle_file", help="Path to QnVectors pickle")
    parser.add_argument("--event", default=None, help="Event key to export")
    parser.add_argument("--outdir", default=None, help="Output directory")
    args = parser.parse_args()

    event_name, event = load_event(args.pickle_file, args.event)
    outdir = args.outdir or os.path.join(os.path.dirname(args.pickle_file),
                                         "observables")
    ensure_dir(outdir)

    pT = np.asarray(event["pTArr"])
    ch_sp = np.asarray(event["ch_pTArr"])
    spectrum = np.real(ch_sp[0, :])
    vn_complex = [ch_sp[i, :] for i in range(1, min(ch_sp.shape[0], 5))]

    # Build a compact pT table with real/imag parts and magnitudes.
    columns = [pT, spectrum]
    header_cols = ["pT", "dN_d2pT"]
    for i, arr in enumerate(vn_complex, start=1):
        columns.extend([np.real(arr), np.imag(arr), np.abs(arr)])
        header_cols.extend([f"v{i}_re", f"v{i}_im", f"v{i}_abs"])
    pT_table = np.column_stack(columns)
    write_text_table(
        os.path.join(outdir, "charged_hadron_pT_observables.dat"),
        "  ".join(header_cols),
        pT_table,
    )

    eta = np.asarray(
        event.get("etaArr", np.linspace(-7.0, 7.0, len(event["dNch/deta"]))))
    dNch_deta = np.asarray(event["dNch/deta"])
    eta_table = np.column_stack([eta, dNch_deta])
    write_text_table(
        os.path.join(outdir, "charged_hadron_eta_observables.dat"),
        "eta  dNch_deta",
        eta_table,
    )

    summary_lines = [
        f"event = {event_name}",
        f"Nch = {event.get('Nch', np.nan)}",
        f"mean_pT_ch = {event.get('mean_pT_ch', np.nan)}",
        f"ET = {event.get('ET', np.nan)}",
        f"Npart = {event.get('Npart', np.nan)}",
        f"Ncoll = {event.get('Ncoll', np.nan)}",
        f"b = {event.get('b', np.nan)}",
    ]
    with open(os.path.join(outdir, "summary.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(summary_lines) + "\n")

    # Plot charged hadron spectrum and vn(pT).
    fig, axes = plt.subplots(2,
                             1,
                             figsize=(8.2, 8.2),
                             sharex=True,
                             constrained_layout=True)

    axes[0].plot(pT, spectrum, color="#1f77b4", lw=2)
    axes[0].set_ylabel(r"$dN/d^2p_T$")
    axes[0].set_yscale("log")
    axes[0].grid(alpha=0.25)
    axes[0].set_title(f"{event_name}: charged hadron spectrum")

    for i, arr in enumerate(vn_complex, start=1):
        axes[1].plot(pT, np.abs(arr), lw=2, label=rf"$|v_{i}|$")
    axes[1].set_xlabel(r"$p_T$ [GeV]")
    axes[1].set_ylabel(r"$|v_n(p_T)|$")
    axes[1].grid(alpha=0.25)
    axes[1].legend(frameon=False, ncol=2)

    fig.savefig(os.path.join(outdir, "charged_hadron_pT_observables.png"),
                dpi=180)
    plt.close(fig)

    # Plot dNch/deta.
    fig, ax = plt.subplots(figsize=(8.2, 4.8), constrained_layout=True)
    ax.plot(eta, dNch_deta, color="#d62728", lw=2)
    ax.set_xlabel(r"$\eta$")
    ax.set_ylabel(r"$dN_{ch}/d\eta$")
    ax.set_title(f"{event_name}: charged-hadron rapidity density")
    ax.grid(alpha=0.25)
    fig.savefig(os.path.join(outdir, "charged_hadron_eta_observables.png"),
                dpi=180)
    plt.close(fig)

    print(f"Wrote observables to {outdir}")


if __name__ == "__main__":
    main()
