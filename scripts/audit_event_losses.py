#!/usr/bin/env python3
"""Per-design-point event accounting for a decays-only iSS production set.

Every event that TRENTo draws is written to `events_drawn.csv` (keyed by global
event id), including the ones that never collide.  An event can then fail to
produce `spvn_results_<id>.h5` for one of three reasons:

  no_collision : TRENTo returned mult = 0 (the two nuclei missed).  Physical.
  no_surface   : mult > 0 but the freeze-out surface was empty, so the driver
                 skipped the event.  Physical, and strongly peripheral.
  missing_block: the whole 20-event job produced nothing (nothing was
                 transferred).  This is data loss, not physics; it is repaired
                 by re-running the block and must not be counted as an
                 efficiency.

The denominator for centrality percentiles must be the *drawn* set, which is
identical across design points because the seeds are a pure function of the
global event id.  Sorting on survivors instead would make the percentile edges
parameter-dependent exactly where the loss is largest.

Usage:
  python3 audit_event_losses.py RESULTS_ROOT [--blocks 100] [--events-per-block 20]
      [--write-classes]
"""
import argparse
import csv
import glob
import os
import re
import sys
from collections import defaultdict

BIN_EDGES = [i / 20 for i in range(21)]  # 0.05 wide in b/bmax


def load_drawn(dpdir):
    events = {}
    blocks = set()
    for f in glob.glob(os.path.join(dpdir, 'spvn_results', 'events_drawn_*.csv')):
        m = re.search(r'events_drawn_(\d+)\.csv$', f)
        if not m:
            continue
        blocks.add(int(m.group(1)))
        with open(f) as fh:
            for row in csv.DictReader(fh):
                eid = int(row['event_id'])
                events[eid] = dict(b=float(row['b']),
                                   bmax=float(row['b_max']),
                                   ratio=float(row['b_over_bmax']),
                                   mult=float(row['mult']),
                                   status=row['status'])
    return events, blocks


def h5_ids(dpdir):
    out = set()
    for f in glob.glob(os.path.join(dpdir, 'spvn_results', 'spvn_results_*.h5')):
        m = re.search(r'spvn_results_(\d+)\.h5$', f)
        if m:
            out.add(int(m.group(1)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('root')
    ap.add_argument('--blocks', type=int, default=100,
                    help='jobs (blocks) per design point that were submitted')
    ap.add_argument('--events-per-block', type=int, default=20)
    ap.add_argument('--write-classes', action='store_true',
                    help='write event_classes_<dp>.csv next to each events_drawn set')
    args = ap.parse_args()

    dps = sorted(d for d in glob.glob(os.path.join(args.root, 'dp*'))
                 if os.path.isdir(os.path.join(d, 'spvn_results')))
    if not dps:
        sys.exit('no design points found under %s' % args.root)

    expected_events = args.blocks * args.events_per_block
    summary = []
    bins = defaultdict(lambda: [0, 0])  # bin -> [attempted, captured]
    drawn_ratios = {}

    for d in dps:
        dp = os.path.basename(d)
        drawn, blocks = load_drawn(d)
        have = h5_ids(d)
        cls = {}
        for eid, e in drawn.items():
            if e['mult'] <= 0:
                cls[eid] = 'no_collision'
            elif eid in have:
                cls[eid] = 'captured'
            else:
                cls[eid] = 'no_surface'
        n0 = sum(1 for c in cls.values() if c == 'no_collision')
        ns = sum(1 for c in cls.values() if c == 'no_surface')
        nc = sum(1 for c in cls.values() if c == 'captured')
        lost_blocks = sorted(set(range(args.blocks)) - blocks)
        attempted = n0 + ns + nc

        summary.append(dict(dp=dp, blocks=len(blocks), drawn=len(drawn),
                            no_collision=n0, captured=nc, no_surface=ns,
                            lost_blocks=len(lost_blocks),
                            attempted=attempted,
                            frac_no_surface=(ns / attempted) if attempted else 0.0))

        for eid, e in drawn.items():
            if cls[eid] == 'no_collision':
                continue
            b = min(int(e['ratio'] / 0.05), 19)
            bins[b][0] += 1
            if cls[eid] == 'captured':
                bins[b][1] += 1

        if args.write_classes:
            out = os.path.join(d, 'spvn_results', 'event_classes_%s.csv' % dp)
            with open(out, 'w', newline='') as fh:
                w = csv.writer(fh)
                w.writerow(['event_id', 'b', 'b_over_bmax', 'mult', 'class'])
                for eid in sorted(drawn):
                    e = drawn[eid]
                    w.writerow([eid, '%.10g' % e['b'], '%.10g' % e['ratio'],
                                '%.10g' % e['mult'], cls[eid]])

        if lost_blocks:
            print('%s: %d blocks missing -> drawn %d of %d'
                  % (dp, len(lost_blocks), len(drawn), expected_events))

        drawn_ratios[dp] = {eid: e['ratio'] for eid, e in drawn.items()}

    # Centrality edges must be identical across design points: the draws are a
    # pure function of the global event id, so a percentile cut on the drawn set
    # is the same cut for every design point.
    if drawn_ratios:
        # compare quantiles on the ids every design point has, so a missing block
        # cannot masquerade as a percentile shift
        common_ids = set.intersection(*(set(v) for v in drawn_ratios.values()))
        common_ids = sorted(common_ids)
        worst = (0.0, None, None)
        for p in (0.1, 0.3, 0.5, 0.6, 0.7, 0.8, 0.9):
            idx = min(len(common_ids) - 1, int(p * len(common_ids)))
            vals = [sorted(drawn_ratios[dp][i] for i in common_ids)[idx]
                    for dp in drawn_ratios]
            spread = max(vals) - min(vals)
            if spread > worst[0]:
                worst = (spread, p, (min(vals), max(vals)))
        print('\nb/bmax percentile edges on the %d event ids common to all design '
              'points: max spread %.1e (p=%.1f: %.9f..%.9f)'
              % (len(common_ids), worst[0], worst[1] or 0.0,
                 worst[2][0] if worst[2] else 0.0,
                 worst[2][1] if worst[2] else 0.0))

    print('\n%-8s %6s %6s %6s %8s %8s %10s %9s' %
          ('dp', 'blocks', 'drawn', 'mult=0', 'captured', 'no_surf', 'lost_blk', 'loss%'))
    for s in summary:
        print('%-8s %6d %6d %6d %8d %8d %10d %8.2f' %
              (s['dp'], s['blocks'], s['drawn'], s['no_collision'], s['captured'],
               s['no_surface'], s['lost_blocks'], 100 * s['frac_no_surface']))

    tot = {k: sum(s[k] for s in summary) for k in
           ('drawn', 'no_collision', 'captured', 'no_surface', 'lost_blocks')}
    attempted = tot['drawn'] - tot['no_collision']
    print('\ntotal: drawn=%d  mult=0=%d  attempted=%d  captured=%d  no_surface=%d '
          '(%.2f%% of attempted)  lost_blocks=%d (repairable, not physics)'
          % (tot['drawn'], tot['no_collision'], attempted, tot['captured'],
             tot['no_surface'], 100 * tot['no_surface'] / max(1, attempted),
             tot['lost_blocks']))

    print('\ncapture fraction vs b/bmax (all design points):')
    for b in range(20):
        att, cap = bins[b]
        if att:
            print('  %.2f-%.2f  %6d attempted  %8.2f%% captured' %
                  (b * 0.05, (b + 1) * 0.05, att, 100.0 * cap / att))


if __name__ == '__main__':
    main()
