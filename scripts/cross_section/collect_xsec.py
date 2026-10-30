#!/usr/bin/env python3
"""Collect per-point cross sections into summary.csv and one HDF5, and test them.

Two acceptance tests, each a pull distribution over all points:
  * trento: sigma_inel against the brute-force TRENTo estimate made on the same
    pools inside each job. TRENTo seeds are point-dependent, so the TRENTo side
    is independent between points and the mean pull is a real test; what
    remains common is the exact side's own error (shared pools, ~0.08%).
  * campaign: the predicted hit fraction for area-uniform b on [0, b_max],
    sigma_below_bmax / (pi b_max^2), against N(mult > 0) / N_drawn in the
    campaign's own events_drawn CSVs (merged/<dp>/csv.tgz), where present.
    The campaign uses the same event ids, nucleus seeds and TRENTo seeds at
    every point (common random numbers), so these pulls share most of one
    fluctuation: their spread across points is well below 1 and their mean is
    worth about one point (~0.2-0.4%), not 1/sqrt(N). Check that individual
    pulls are O(1), not that the mean is zero to 1/sqrt(N).

The exact side is itself correlated between points by design: every point uses
the same pools and orientations, so most of its error is one common offset. The
collector measures it from the per-pair sigmas (sigma_pair / point mean, averaged
over points) and prints it, together with the error of the difference between two
points. Judge the mean TRENTo offset against that common error, not the printed
1/sqrt(N) one: the part of it TRENTo does not share lies between the
orientation-only value and the total.

Usage: collect_xsec.py --campaign a96 [--points-dir DIR] [--merged-dir DIR]
"""
import argparse
import csv
import glob
import io
import math
import os
import tarfile

import h5py
import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
DESIGN = {
    'a76': os.path.join(REPO, 'design', 'design_lhs2000.csv'),
    'a96': os.path.join(REPO, 'design', 'design_lhs2000_A96.csv'),
}
MERGED = {
    'a76': '/data/mluzum/ge76_results/merged',
    'a96': '/data/mluzum/zr96_results/merged',
}
DESIGN_COLUMNS = ('WS_radius', 'WS_diffusiveness', 'beta_2', 'gamma', 'beta_3',
                  'sigma_plane', 'sigma_beta_3', 'nucleon-width')
SUMMARY_COLUMNS = (
    'sigma_inel_fm2', 'sigma_inel_err_fm2', 'sigma_below_bmax_fm2',
    'sigma_below_bmax_err_fm2', 'frac_below_bmax', 'p_hit_below_bmax', 'b_max',
    'b_lo', 'b_far', 'mean_P_at_b_far', 'max_P_at_b_far',
    'edge_bound_b_lo_fm2', 'edge_bound_b_far_fm2', 'sigma_nn_fm2', 'sigma_gg_fm2',
    'sigma_inel_trento_fm2', 'sigma_inel_trento_err_fm2', 'tail_share_c40',
    'tail_share_c50', 'tail_share_c60', 'tail_share_c70', 'tail_share_c80',
    'naive_centrality_c50', 'naive_centrality_c60', 'naive_centrality_c70',
    'n_conf', 'n_orient', 'n_phi', 'db', 'n_trento_inner', 'n_trento_tail',
    'seconds_total')


def campaign_counts(tgz):
    """(n_drawn, n_hit, b_max values, n_skipped) from a merged/<dp>/csv.tgz.

    Rows are keyed by event id. A row without a mult (status 'no_trento': TRENTo
    itself did not run) was never drawn and is skipped.
    """
    events = {}
    b_max = set()
    skipped = 0
    with tarfile.open(tgz) as tar:
        for member in tar.getmembers():
            if not member.isfile() or not member.name.endswith('.csv'):
                continue
            text = tar.extractfile(member).read().decode()
            for row in csv.DictReader(io.StringIO(text)):
                if row['mult'] == '':
                    skipped += 1
                    continue
                events[int(row['event_id'])] = float(row['mult'])
                b_max.add(float(row['b_max']))
    mult = np.array(list(events.values()))
    return len(mult), int((mult > 0).sum()), b_max, skipped


def pull_summary(name, pulls, rel):
    pulls = np.asarray(pulls)
    if len(pulls) == 0:
        print(f'{name}: no points')
        return
    rel = np.asarray(rel)
    print(f'{name}: {len(pulls)} points, pull mean {pulls.mean():+.3f} '
          f'+- {1 / math.sqrt(len(pulls)):.3f}, pull sd {pulls.std(ddof=1):.3f}, '
          f'chi2/ndf {np.sum(pulls**2) / len(pulls):.3f}; '
          f'mean relative difference {100 * rel.mean():+.4f}% '
          f'+- {100 * rel.std(ddof=1) / math.sqrt(len(rel)):.4f}%')


def common_mode(ratios):
    """Print how much of the exact error is shared between points."""
    n = ratios.shape[1]
    pair = ratios.mean(axis=2)
    per_point = pair.std(axis=1, ddof=1) / math.sqrt(n)
    avg = ratios.mean(axis=0)
    total = avg.mean(axis=1).std(ddof=1) / math.sqrt(n)
    orient = math.sqrt(avg.var(axis=1, ddof=1).mean() / avg.shape[1] / n)
    rng = np.random.default_rng(0)
    j, k = rng.integers(0, len(pair), (2, 2000))
    diff = (pair[j] - pair[k]).std(axis=1, ddof=1)[j != k] / math.sqrt(n)
    print(f'exact error: per point median {100 * np.median(per_point):.4f}%; '
          f'common to all points {100 * total:.4f}% (orientation part '
          f'{100 * orient:.4f}%); difference of two random points median '
          f'{100 * np.median(diff):.4f}%')


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--campaign', choices=sorted(DESIGN), required=True)
    ap.add_argument('--points-dir', default=None)
    ap.add_argument('--merged-dir', default=None)
    ap.add_argument('--out-dir', default=None)
    args = ap.parse_args()
    base = os.path.join('/data/mluzum/cross_sections', args.campaign)
    points_dir = args.points_dir or os.path.join(base, 'points')
    merged_dir = args.merged_dir or MERGED[args.campaign]
    out_dir = args.out_dir or base
    design = list(csv.DictReader(open(DESIGN[args.campaign])))

    rows = []
    camp_pull, camp_rel, tr_pull, tr_rel = [], [], [], []
    ratios = []  # per point: (n_conf, n_orient) sigma / point mean
    h5_out = os.path.join(out_dir, f'cross_sections_{args.campaign}.h5')
    with h5py.File(h5_out + '.tmp', 'w') as out:
        for path in sorted(glob.glob(os.path.join(points_dir, 'dp*.h5'))):
            label = os.path.basename(path)[:-3]
            n = int(label[2:])
            with h5py.File(path, 'r') as f:
                a = dict(f.attrs)
                g = out.create_group(label)
                for key in ('b_grid', 'P_mean', 'P_sd'):
                    g[key] = f[key][:]
                so = f['sigma_orientation_fm2'][:]
                g['sigma_pair_fm2'] = so.mean(axis=1)
                ratios.append(so / so.mean())
                for key, value in a.items():
                    g.attrs[key] = value
            d = design[n - 1]
            row = {'campaign': args.campaign, 'dp': n, 'design_label': d['label'],
                   'A': a['A']}
            row.update({c: d[c] for c in DESIGN_COLUMNS})
            row.update({c: a[c] for c in SUMMARY_COLUMNS})
            row['sigma_inel_mb'] = 10 * a['sigma_inel_fm2']
            row['sigma_inel_rel_err'] = a['sigma_inel_err_fm2'] / a[
                'sigma_inel_fm2']

            # brute-force TRENTo on the same pools
            diff = a['sigma_inel_trento_fm2'] - a['sigma_inel_fm2']
            err = math.hypot(a['sigma_inel_trento_err_fm2'],
                             a['sigma_inel_err_fm2'])
            row['trento_pull'] = diff / err
            tr_pull.append(diff / err)
            tr_rel.append(diff / a['sigma_inel_fm2'])

            # the campaign's own draws on [0, b_max]
            tgz = os.path.join(merged_dir, label, 'csv.tgz')
            row.update({'campaign_n_drawn': '', 'campaign_n_hit': '',
                        'campaign_pull': ''})
            if os.path.exists(tgz):
                n_drawn, n_hit, b_max_csv, skipped = campaign_counts(tgz)
                if skipped:
                    print(f'{label}: skipped {skipped} campaign row(s) without '
                          'a mult')
                if any(abs(b - a['b_max']) > 1e-5 for b in b_max_csv):
                    print(f'{label}: campaign b_max {sorted(b_max_csv)} != '
                          f'{a["b_max"]:.6f}; skipping campaign test')
                elif n_drawn:
                    p = a['p_hit_below_bmax']
                    p_err = a['sigma_below_bmax_err_fm2'] / (math.pi *
                                                             a['b_max']**2)
                    pull = (n_hit / n_drawn - p) / math.sqrt(
                        p * (1 - p) / n_drawn + p_err**2)
                    row.update({'campaign_n_drawn': n_drawn,
                                'campaign_n_hit': n_hit,
                                'campaign_pull': pull})
                    camp_pull.append(pull)
                    camp_rel.append((n_hit / n_drawn - p) / p)
            rows.append(row)
    os.replace(h5_out + '.tmp', h5_out)

    summary = os.path.join(out_dir, f'summary_{args.campaign}.csv')
    with open(summary, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f'{len(rows)} points -> {summary}, {h5_out}')
    rel_err = np.array([r['sigma_inel_rel_err'] for r in rows])
    print(f'relative statistical error: median {100 * np.median(rel_err):.3f}%,'
          f' max {100 * rel_err.max():.3f}%')
    share = np.array([r['tail_share_c60'] for r in rows])
    print(f'tail share above the 60% threshold: median {100 * np.median(share):.2f}%, '
          f'max {100 * share.max():.2f}%')
    if len({r.shape for r in ratios}) == 1:
        common_mode(np.array(ratios))
    pull_summary('TRENTo brute force vs exact', tr_pull, tr_rel)
    pull_summary('campaign hit fraction below b_max vs exact '
                 '(correlated across points; see docstring)', camp_pull,
                 camp_rel)
    if camp_pull:
        print(f'  largest |campaign pull|: {np.max(np.abs(camp_pull)):.2f}')


if __name__ == '__main__':
    main()
