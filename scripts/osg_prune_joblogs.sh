#!/bin/bash
# Prune condor job log files in $HOME/log.
#
# Every OSG job writes three small files there (job.<c>.<p>.log/.output/.error),
# and they accumulate: the A=76 campaign had produced 814k files / 12 GB, which
# is a lot of small-file traffic on the shared home filesystem.  Completed jobs'
# logs are static, so the safe rule is age-based: delete files older than N days.
#
# Usage:
#   osg_prune_joblogs.sh [--days 3] [--apply]
# Dry-run by default.
set -u
DAYS=3
APPLY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --days) shift; DAYS=${1:-3} ;;
    --apply) APPLY=1 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done
cmd="find \$HOME/log -maxdepth 1 -type f \\( -name 'job.*.log' -o -name 'job.*.output' -o -name 'job.*.error' \\) -mtime +$DAYS"
if [ $APPLY -eq 1 ]; then
  n=$(eval "$cmd" | wc -l)
  eval "$cmd -delete"
  echo "deleted $n files older than ${DAYS}d"
else
  n=$(eval "$cmd" | wc -l)
  echo "would delete $n files older than ${DAYS}d (dry-run)"
fi
