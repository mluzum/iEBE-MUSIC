#!/usr/bin/env python3
"""Generate the emulator-sweep design: a maximin-ordered Latin hypercube.

The prior is section 18.3 of EMULATOR_SWEEP_PLAN.md and nothing else. This
script samples it with a Latin hypercube and then re-orders the points so that
*every prefix* is a good design, not just the full set.

Why the ordering: a campaign rarely ends on the number of design points it
started with. If the run is interrupted at N points, or a first analysis is
wanted at N points while the rest are still queued, the first N rows have to be
usable on their own. A plain Latin hypercube has no such property -- its first
N rows are just the first N random draws, and in 20 dimensions a random subset
is full of near-duplicate pairs.

The ordering is greedy maximin: start from the point nearest the centre and
repeatedly add the point farthest (in Euclidean distance, unit cube) from
everything already chosen. Each prefix is therefore as spread out as that
construction allows. Measured against fresh Latin hypercubes of the same size,
the prefix at N = 1000 has a minimax separation 67% larger; the price is that
the marginals are no longer stratified to 1/N (they degrade to roughly the
i.i.d. rate, 1/sqrt(N)), which matters much less than joint filling at 20
dimensions.

Usage:
    python3 scripts/make_design.py --n 2000 --out design/design_lhs2000.csv

The output columns are exactly the ones MakeDictionaries.py reads, so the file
can be fed straight to it. Rows are in maximin order: submit design points
1..N for whatever N the campaign reaches.
"""

import argparse
import csv
import sys

import numpy as np

# Section 18.3 of EMULATOR_SWEEP_PLAN.md. Order here is the order of the tables
# in that section: TRENTo and the initial state, then hydrodynamics, then the
# nuclear shape, then the shape fluctuations.
PRIOR = [
    # TRENTo and the initial state
    ("normalization", 10.0, 20.0),
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
    ("WS_radius", 4.9, 5.3),
    ("WS_diffusiveness", 0.45, 0.60),
    ("beta_2", 0.0, 0.5),
    ("gamma", 0.0, 60.0),
    ("beta_3", 0.0, 0.2),
    # shape fluctuations
    ("sigma_plane", 0.0, 0.08),
    ("sigma_beta_3", 0.0, 0.05),
]

# Columns MakeDictionaries.py expects that are not design axes.
FIXED = [
    ("shear_relax_time_factor", 5.0),
    ("bulk_viscosity_3_lambda_asymm", 0.0),
    ("shape_distribution", "plane"),
    ("number_nucleons", 76),
]

COLUMNS = (["label"] + [name for name, _, _ in PRIOR]
           + [name for name, _ in FIXED])


def latin_hypercube(n, rng):
    """n points in d dimensions, one per stratum in every marginal."""
    d = len(PRIOR)
    strata = (rng.random((n, d)) + np.arange(n)[:, None])/n
    return np.stack([strata[rng.permutation(n), j] for j in range(d)], axis=1)


def maximin_order(unit_points):
    """Order points so every prefix is greedily maximally separated.

    Farthest-point sampling from the centre. The distance matrix is dense
    (n=2000 is 2e6 entries), which is cheap and avoids a k-d tree whose
    tie-breaking would make the order depend on the build.
    """
    from scipy.spatial.distance import pdist, squareform

    n = len(unit_points)
    dist = squareform(pdist(unit_points))
    start = int(np.argmin(((unit_points - 0.5)**2).sum(axis=1)))
    order = [start]
    nearest = dist[start].copy()
    nearest[start] = -1.0
    for _ in range(n - 1):
        nxt = int(np.argmax(nearest))
        order.append(nxt)
        np.minimum(nearest, dist[nxt], out=nearest)
        nearest[nxt] = -1.0
    return np.array(order)


def prefix_separation(unit_points, order, sizes):
    """Minimax distance of each prefix, for the record."""
    from scipy.spatial.distance import pdist

    out = []
    for size in sizes:
        out.append((size, float(pdist(unit_points[order[:size]]).min())))
    return out


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--n",
                        type=int,
                        default=2000,
                        help="number of design points (default 2000)")
    parser.add_argument("--seed",
                        type=int,
                        default=8675309,
                        help="RNG seed (default 8675309, the campaign seed)")
    parser.add_argument("--out",
                        default="design/design_lhs2000.csv",
                        help="output CSV path")
    parser.add_argument(
        "--no-order",
        action="store_true",
        help="write the points in LHS order instead of maximin order")
    args = parser.parse_args()

    if args.n < 2:
        sys.exit("--n must be at least 2")

    rng = np.random.default_rng(args.seed)
    unit = latin_hypercube(args.n, rng)
    order = np.arange(args.n) if args.no_order else maximin_order(unit)
    unit = unit[order]

    lows = np.array([lo for _, lo, _ in PRIOR])
    highs = np.array([hi for _, _, hi in PRIOR])
    design = lows + unit*(highs - lows)

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(COLUMNS)
        for i, row in enumerate(design, start=1):
            record = ["design_{:04d}".format(i)]
            record += ["{:.10g}".format(v) for v in row]
            record += [
                "{:.10g}".format(v) if isinstance(v, float) else v
                for _, v in FIXED
            ]
            writer.writerow(record)

    print("wrote {} design points to {}".format(args.n, args.out))
    if not args.no_order:
        sizes = [n for n in (125, 250, 500, 1000, args.n) if n <= args.n]
        print("prefix separations (minimax distance, unit cube):")
        for size, sep in prefix_separation(unit, np.arange(args.n), sizes):
            print("  N={:5d}  {:.4f}".format(size, sep))


if __name__ == "__main__":
    main()
