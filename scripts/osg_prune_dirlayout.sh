#!/bin/bash
# Delete campaign-1 directory-layout residue on the AP, after verifying that
# every event h5 in it is already inside the local merged h5.
#
# Before dp0461 the worker left batch 1 as loose per-event files in
# <dp>/spvn_results/ (h5 + TRENTo summaries + csv) instead of one archive per
# job.  The ordinary pruner only looks at *.tar.gz, so these trees -- 6,000 files
# per design point, 83 % of the A=76 footprint -- survive every archive prune.
#
# They are removable because the physics is merged: for each point this script
# lists the event ids present on the AP, compares them with the group names of
# merged/<dp>/<dp>.h5, and deletes only if the AP set is a subset.  The per-event
# TRENTo summaries in those trees are not duplicated locally and are lost; that
# is accepted for these retired campaign-1 points (campaign 2 keeps them inside
# the job archives).
#
# Usage:
#   IBEM_BASE=/ospool/.../ge76_prod IBEM_LOCAL=/data/mluzum/ge76_results \
#       osg_prune_dirlayout.sh [--apply] [DP_LIST]
# Without --apply it only verifies and reports.
set -u
BASE=${IBEM_BASE:?IBEM_BASE required}
LOCAL=${IBEM_LOCAL:?IBEM_LOCAL required}
DARGS=${DARGS:-"1 500"}
APPLY=0
[ "${1:-}" = "--apply" ] && { APPLY=1; shift; }
PAR=${PAR:-2}
CM=${IBEM_CM:-/tmp/opencode/cm_pull}
SSH_OPTS="-o ControlMaster=auto -o ControlPath=$CM -o ControlPersist=600 -o ConnectTimeout=20"

verify_and_delete() {
  i=$1
  dp=$(printf 'dp%04d' "$i")
  remote=$BASE/$dp/spvn_results
  merged=$LOCAL/merged/$dp/$dp.h5

  if [ ! -f "$merged" ]; then
    echo "$dp KEEP no_local_merged"
    return
  fi
  ids=$(ssh $SSH_OPTS osg "ls $remote/*.h5 2>/dev/null" 2>/dev/null \
        | sed -E 's#.*spvn_results_([0-9]+)\.h5#\1#' | sort -n | tr '\n' ' ')
  if [ -z "$ids" ]; then
    # no event h5 files: the tree is only summaries/csv, still safe to drop
    n=$(ssh $SSH_OPTS osg "ls $remote 2>/dev/null | wc -l" 2>/dev/null)
    if [ "${n:-0}" -eq 0 ]; then echo "$dp empty"; return; fi
    [ "$APPLY" = 1 ] && ssh $SSH_OPTS osg "rm -rf $remote" 2>/dev/null
    echo "$dp deleted files=$n (no h5, summaries+csv only)"
    return
  fi
  verdict=$(python3 - "$merged" $ids <<'PY'
import h5py, re, sys
f = h5py.File(sys.argv[1], 'r')
local = {int(re.sub(r'.*spvn_results_', '', k)) for k in f.keys()}
ap = {int(x) for x in sys.argv[2:] if x.isdigit()}
missing = ap - local
print("ok %d %d" % (len(ap), len(missing)) if not missing
      else "keep %d %d %s" % (len(ap), len(missing), sorted(missing)[:5]))
PY
)
  case "$verdict" in
    ok*)
      set -- $verdict
      n=$2
      if [ "$APPLY" = 1 ]; then
        ssh $SSH_OPTS osg "rm -rf $remote" 2>/dev/null
        echo "$dp deleted events=$n"
      else
        echo "$dp would_delete events=$n"
      fi
      ;;
    keep*)
      set -- $verdict
      echo "$dp KEEP events=$2 missing_local=$3 e.g.$4"
      ;;
    *)
      echo "$dp VERIFY_FAIL"
      ;;
  esac
}
export -f verify_and_delete
export BASE LOCAL SSH_OPTS APPLY
if [ -n "${DP_LIST:-}" ]; then LIST=$(cat "$DP_LIST"); else LIST=$(seq $DARGS); fi
printf '%s\n' $LIST | xargs -P "$PAR" -I{} bash -c 'verify_and_delete {}' 2>&1
echo DIRLAYOUT_PRUNE_DONE
