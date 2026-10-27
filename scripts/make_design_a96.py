#!/usr/bin/env python3
"""Generate the A=96 design with the SAME unit-cube Latin hypercube as A=76.

The design points are drawn in the unit cube and then mapped per axis with
x = lo + u*(hi - lo); the maximin ordering is computed on the unit points.  So
changing only the prior ranges leaves every design point's normalized
coordinates and the ordering untouched: design_000k in this file is the same
normalized point as design_000k in design/design_lhs2000.csv, and only the
physical values differ.

Editing PRIOR_A96 below and rerunning is all a prior change needs.

Usage:
    python3 scripts/make_design_a96.py
    python3 scripts/make_design_a96.py --check-against-a76
"""
import argparse
import csv
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_design as md  # noqa: E402  (latin_hypercube, maximin_order)

REPO = os.path.dirname(HERE)

# Same 20 axes in the same order as make_design.PRIOR -- required for the
# unit-cube design to be reused.  Ranges per design/A96_priors.md.
PRIOR_A96 = [
    # TRENTo and the initial state
    ("normalization", 3.0, 10.0),          # was 10-20 (200 GeV RHIC)
    ("reduced-thickness", -0.7, 0.7),
    ("nucleon-width", 0.5, 1.5),
    ("sigma_k", 0.3, 2.0),
    ("tau", 0.3, 2.0),
    # hydrodynamics
    ("shear_viscosity_3_eta_over_s_at_kink", 0.01, 0.20),
    ("shear_viscosity_3_eta_over_s_low_T_slope_in_GeV", -2.0, 0.0),
    ("shear_viscosity_3_eta_over_s_high_T_slope_in_GeV", 0.0, 2.0),
    ("shear_viscosity_3_eta_over_s_T_kink_in_GeV", 0.13, 0.30),
    ("bulk_viscosity_3_max", 0.01, 0.25),
    ("bulk_viscosity_3_T_peak_in_GeV", 0.12, 0.30),
    ("bulk_viscosity_3_width_in_GeV", 0.025, 0.15),
    ("T_freeze", 0.135, 0.165),
    # nuclear shape
    ("WS_radius", 5.0, 5.7),               # was 4.9-5.3; wider for A=96
    ("WS_diffusiveness", 0.45, 0.60),
    ("beta_2", 0.0, 0.4),                  # was 0.0-0.5
    ("gamma", 0.0, 60.0),                  # full physical range, unchanged
    ("beta_3", 0.0, 0.4),                  # was 0.0-0.2
    # shape fluctuations
    ("sigma_plane", 0.0, 0.08),
    ("sigma_beta_3", 0.0, 0.08),           # was 0.0-0.05
]

FIXED_A96 = [
    ("shear_relax_time_factor", 5.0),
    ("bulk_viscosity_3_lambda_asymm", 0.0),
    ("shape_distribution", "plane"),
    ("number_nucleons", 96),               # was 76
]

COLUMNS = (["label"] + [name for name, _, _ in PRIOR_A96] +
           [name for name, _ in FIXED_A96])


def build(seed, n):
    rng = np.random.default_rng(seed)
    unit = md.latin_hypercube(n, rng)
    order = md.maximin_order(unit)
    unit = unit[order]
    lows = np.array([lo for _, lo, _ in PRIOR_A96])
    highs = np.array([hi for _, _, hi in PRIOR_A96])
    return unit, lows + unit*(highs - lows)


def write_csv(path, design):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(COLUMNS)
        for i, row in enumerate(design, start=1):
            record = ["design_{:04d}".format(i)]
            record += ["{:.10g}".format(v) for v in row]
            record += [
                "{:.10g}".format(v) if isinstance(v, float) else v
                for _, v in FIXED_A96
            ]
            writer.writerow(record)


def check_against_a76(unit, tol=1e-6):
    """Reconstruct u from both CSVs and require them to agree row by row."""
    ref = os.path.join(REPO, "design", "design_lhs2000.csv")
    if not os.path.exists(ref):
        print("A=76 design not found at", ref)
        return False
    rows = list(csv.DictReader(open(ref)))
    if len(rows) != len(unit):
        print("row count differs: A76=%d A96=%d" % (len(rows), len(unit)))
        return False
    worst = 0.0
    worst_axis = ""
    for j, (name, lo, hi) in enumerate(md.PRIOR):
        a76 = np.array([float(r[name]) for r in rows])
        u76 = (a76 - lo)/(hi - lo)
        d = float(np.max(np.abs(u76 - unit[:, j])))
        if d > worst:
            worst, worst_axis = d, name
    print("max |u(A76) - u(A96)| = %.3e  (worst axis: %s)" %
          (worst, worst_axis))
    ok = worst <= tol
    print("VERIFIED: identical normalized design" if ok else "MISMATCH")
    return ok


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=8675309)
    ap.add_argument("--out",
                    default=os.path.join(REPO, "design",
                                         "design_lhs2000_A96.csv"))
    ap.add_argument("--check-against-a76", action="store_true")
    args = ap.parse_args()

    unit, design = build(args.seed, args.n)
    write_csv(args.out, design)
    print("wrote %d design points to %s" % (args.n, args.out))
    if args.check_against_a76:
        return 0 if check_against_a76(unit) else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
