#!/usr/bin/env python3
"""Write a design with new prior ranges on the SAME normalized Latin hypercube.

Every design point keeps its unit-cube coordinate u = (x - lo)/(hi - lo) on
every axis; the axes given with --range are mapped onto their new interval,
x' = lo' + u (hi' - lo').  All other columns, the labels and the row order (the
maximin ordering) are copied verbatim, so design_000k in the new file is the
same normalized point as in the old one -- and as in every other design built
on this hypercube (A=76 and A=96 share it; see make_design_a96.py).  Nothing
is redrawn, so the correspondence does not depend on reproducing the RNG.

The old ranges come from the generator that made the input:
    --prior a76   make_design.PRIOR        (design/design_lhs2000.csv)
    --prior a96   make_design_a96.PRIOR_A96 (design/design_lhs2000_A96.csv)

Usage:
    python3 scripts/remap_design_prior.py design/design_lhs2000_A96.csv \\
        design/design_lhs2000_A96_c2.csv --prior a96 --range normalization=6,13
"""
import argparse
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("design_in")
    ap.add_argument("design_out")
    ap.add_argument("--prior", choices=["a76", "a96"], required=True)
    ap.add_argument("--range", action="append", required=True,
                    help="axis=lo,hi (repeatable)")
    args = ap.parse_args()

    if args.prior == "a76":
        import make_design as m
        prior = {name: (lo, hi) for name, lo, hi in m.PRIOR}
    else:
        import make_design_a96 as m
        prior = {name: (lo, hi) for name, lo, hi in m.PRIOR_A96}

    new = {}
    for spec in args.range:
        name, _, bounds = spec.partition("=")
        lo, hi = (float(x) for x in bounds.split(","))
        if name not in prior:
            sys.exit("unknown axis %r" % name)
        if not hi > lo:
            sys.exit("empty range for %s" % name)
        new[name] = (lo, hi)

    with open(args.design_in, newline="") as f:
        first = f.readline()
        eol = "\r\n" if first.endswith("\r\n") else "\n"
        f.seek(0)
        reader = csv.DictReader(f)
        fields = reader.fieldnames
        rows = list(reader)

    worst = 0.0
    for r in rows:
        for name, (lo2, hi2) in new.items():
            lo, hi = prior[name]
            x = float(r[name])
            if not lo - 1e-9 <= x <= hi + 1e-9:
                sys.exit("%s: %s = %r outside the old prior [%g, %g]"
                         % (r["label"], name, x, lo, hi))
            u = (x - lo)/(hi - lo)
            r[name] = "%.10g" % (lo2 + u*(hi2 - lo2))
            worst = max(worst, abs((float(r[name]) - lo2)/(hi2 - lo2) - u))

    with open(args.design_out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator=eol)
        w.writeheader()
        w.writerows(rows)
    for name, (lo2, hi2) in new.items():
        print("%s: [%g, %g] -> [%g, %g]" % ((name,) + prior[name] + (lo2, hi2)))
    print("%d rows; max |u_new - u_old| = %.1e; all other columns copied"
          % (len(rows), worst))


if __name__ == "__main__":
    main()
