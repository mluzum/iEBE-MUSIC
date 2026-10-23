#!/usr/bin/env python3
"""Raise request_memory on held-on-memory OSG jobs and release them.

Why this exists: peak RSS is a property of the design point, not of the job
length (one 76Ge design point sat at 733 MB median while every other point was
at 245-270 MB, and its jobs peaked at 1221 MB).  Asking for 1 GB keeps the
common case maximally schedulable; the rare design point that needs more is
patched here instead, so the whole campaign does not pay for the exception.

Usage:
  python3 osg_memory_sweep.py [--memory 1600] [--dry-run]
"""
import argparse
import math
import re
import subprocess

MEM_REASON = 'memory usage exceeded'


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--memory', type=int, default=1600,
                    help='request_memory to set on held jobs, MB (default 1600)')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    out = run(['condor_q', '-af:h', 'ClusterId', 'ProcId', 'JobStatus',
               'MemoryUsage', 'RequestMemory', 'HoldReason']).stdout.splitlines()
    held = []
    for ln in out[1:]:
        parts = ln.split()
        if len(parts) < 6 or parts[2] != '5':
            continue
        reason = ln[ln.find(parts[5]):]
        if MEM_REASON not in reason:
            continue
        peak = int(parts[3]) if re.match(r'^\d+$', parts[3]) else 0
        held.append((parts[0], parts[1], peak))

    if not held:
        print('no memory-held jobs')
        return

    for cid, pid, peak in sorted(held):
        want = args.memory
        if peak:
            want = max(want, int(math.ceil(peak * 1.25 / 100.0)) * 100)
        job = '%s.%s' % (cid, pid)
        if args.dry_run:
            print('would set %s request_memory=%d (peak %s MB)' % (job, want, peak))
            continue
        e = run(['condor_qedit', job, 'RequestMemory', str(want)])
        r = run(['condor_release', job])
        print('%s peak=%sMB -> %dMB edit=%s release=%s'
              % (job, peak, want, 'OK' if e.returncode == 0 else 'FAIL',
                 'OK' if r.returncode == 0 else 'FAIL'))

    print('%d job(s) %s' % (len(held), 'would be released' if args.dry_run else 'released'))


if __name__ == '__main__':
    main()
