#!/usr/bin/env python3
"""Compute sigma_inel for a range of design points, one process per point.

Run inside the production image, e.g.

  singularity exec --contain -B /data/mluzum -B SCRATCH IMAGE \
    python3 scripts/cross_section/run_xsec.py --campaign a96 --points 1-1000 \
      --workers 40 --scratch SCRATCH

Resumable: a point whose output file exists is skipped, and outputs are written
to a temporary name and renamed, so a killed run never leaves a partial file.
"""
import argparse
import multiprocessing as mp
import os
import sys
import time
import traceback

for _var in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ.setdefault(_var, '1')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xsec_point  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
CAMPAIGNS = {
    'a76': os.path.join(REPO, 'DesignPoint{n}',
                        'parameter_dictionary_design_point_{n}.py'),
    'a96': os.path.join(REPO, 'zr96_design', 'DesignPoint{n}',
                        'parameter_dictionary_design_point_{n}.py'),
}


def parse_points(spec):
    points = []
    for part in spec.split(','):
        lo, _, hi = part.partition('-')
        points.extend(range(int(lo), int(hi or lo) + 1))
    return points


def work(job):
    n, param_file, out_path, scratch, settings, log_path = job
    label = f'dp{n:04d}'
    try:
        lines = []
        xsec_point.compute(param_file, label, out_path, scratch, settings,
                           log=lines.append)
        msg = lines[-1]
    except Exception:
        msg = f'{label}: FAILED\n' + traceback.format_exc()
    with open(log_path, 'a') as f:
        f.write(time.strftime('%Y-%m-%d %H:%M:%S ') + msg + '\n')
    return msg


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--campaign', choices=sorted(CAMPAIGNS), required=True)
    ap.add_argument('--points', required=True, help='e.g. 1-1000 or 1,5,9-12')
    ap.add_argument('--out-dir', default=None,
                    help='default /data/mluzum/cross_sections/<campaign>')
    ap.add_argument('--scratch', required=True)
    ap.add_argument('--workers', type=int, default=1)
    ap.add_argument('--log', default=None,
                    help='append one line per point; default OUT_DIR/run.log. '
                    'Give each HTCondor job its own: NFS appends interleave.')
    for key, value in xsec_point.DEFAULTS.items():
        ap.add_argument('--' + key.replace('_', '-'), type=type(value),
                        default=value)
    args = ap.parse_args()
    out_dir = args.out_dir or os.path.join('/data/mluzum/cross_sections',
                                           args.campaign, 'points')
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(args.scratch, exist_ok=True)
    settings = {k: getattr(args, k) for k in xsec_point.DEFAULTS}
    log_path = args.log or os.path.join(out_dir, 'run.log')
    jobs = []
    for n in parse_points(args.points):
        out_path = os.path.join(out_dir, f'dp{n:04d}.h5')
        if os.path.exists(out_path):
            continue
        jobs.append((n, CAMPAIGNS[args.campaign].format(n=n), out_path,
                     args.scratch, settings, log_path))
    print(f'{len(jobs)} points to do, {args.workers} workers, out {out_dir}',
          flush=True)
    with mp.Pool(args.workers, maxtasksperchild=1) as pool:
        for msg in pool.imap_unordered(work, jobs):
            print(msg, flush=True)


if __name__ == '__main__':
    main()
