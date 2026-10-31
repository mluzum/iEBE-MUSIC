#!/usr/bin/env python3
"""Raise the resource on held OSG jobs and release them.

Why this exists: the per-job request is deliberately the *common* case, so the
whole campaign stays maximally schedulable, and the rare design point that needs
more is patched here instead.

  * memory: peak RSS is a property of the design point, not of the job length
    (one 76Ge design point sat at 733 MB median while every other point was at
    245-270 MB, and its jobs peaked at 1221 MB), so 1 GB is the default and the
    exception is raised to 1.25x the measured peak.
  * disk: `request_disk = 4 GB` covers the 20 events' hydro intermediates, but
    some sites advertise free space they do not have and the job dies with
    "disk usage exceeded allocated disk".  Those cannot be fixed by re-running
    into the same slot, so the request is doubled: the job then only matches
    slots that report that much room.

Both classes are counted as held jobs (JobStatus 5), so nothing is silently
dropped; a hold reason this script does not recognise is reported at the end
rather than ignored.

Usage:
  python3 osg_memory_sweep.py [--memory 1600] [--disk 8388608] [--dry-run]
"""
import argparse
import math
import re
import subprocess

MEM_REASON = 'memory usage exceeded'
DISK_REASON = 'disk usage exceeded'


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        '--memory',
        type=int,
        default=1600,
        help='request_memory to set on memory-held jobs, MB (default 1600)')
    ap.add_argument('--disk',
                    type=int,
                    default=8388608,
                    help='request_disk to set on disk-held jobs, KB '
                    '(default 8388608 = 8 GB)')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    out = run([
        'condor_q', '-af:h', 'ClusterId', 'ProcId', 'JobStatus', 'MemoryUsage',
        'RequestMemory', 'RequestDisk', 'HoldReason'
    ]).stdout.splitlines()
    mem_held, disk_held, unexplained = [], [], []
    for ln in out[1:]:
        parts = ln.split()
        if len(parts) < 7 or parts[2] != '5':
            continue
        reason = ln[ln.find(parts[6]):]
        peak = int(parts[3]) if re.match(r'^\d+$', parts[3]) else 0
        cur_disk = int(parts[5]) if re.match(r'^\d+$', parts[5]) else 0
        if MEM_REASON in reason:
            mem_held.append((parts[0], parts[1], peak))
        elif DISK_REASON in reason:
            disk_held.append((parts[0], parts[1], cur_disk))
        else:
            unexplained.append((parts[0], parts[1], reason[:90]))

    if not mem_held and not disk_held:
        print('no memory- or disk-held jobs')
        for cid, pid, reason in unexplained:
            print('  unreleased %s.%s: %s' % (cid, pid, reason))
        return

    released = 0
    for cid, pid, peak in sorted(mem_held):
        want = args.memory
        if peak:
            want = max(want, int(math.ceil(peak * 1.25 / 100.0)) * 100)
        job = '%s.%s' % (cid, pid)
        if args.dry_run:
            print('would set %s request_memory=%d (peak %s MB)' %
                  (job, want, peak))
            released += 1
            continue
        e = run(['condor_qedit', job, 'RequestMemory', str(want)])
        r = run(['condor_release', job])
        released += 1
        print('%s peak=%sMB -> memory %dMB edit=%s release=%s' %
              (job, peak, want, 'OK' if e.returncode == 0 else 'FAIL',
               'OK' if r.returncode == 0 else 'FAIL'))

    for cid, pid, cur in sorted(disk_held):
        want = max(args.disk, cur * 2)
        job = '%s.%s' % (cid, pid)
        if args.dry_run:
            print('would set %s request_disk=%d (was %d)' % (job, want, cur))
            released += 1
            continue
        e = run(['condor_qedit', job, 'RequestDisk', str(want)])
        r = run(['condor_release', job])
        released += 1
        print('%s disk %dKB -> %dKB edit=%s release=%s' %
              (job, cur, want, 'OK' if e.returncode == 0 else 'FAIL',
               'OK' if r.returncode == 0 else 'FAIL'))

    print('%d job(s) %s' % (released,
                            'would be released' if args.dry_run else 'released'))
    for cid, pid, reason in unexplained:
        print('  unreleased %s.%s: %s' % (cid, pid, reason))


if __name__ == '__main__':
    main()
