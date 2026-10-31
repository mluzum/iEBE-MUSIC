#!/bin/bash
# Pull only those AP archives whose basenames are missing locally.
#
# The campaign-1 A=76 augmentation points (dp1-500) have 300 archives on the AP
# (batch 1 + batches 2-3) but only ~100 locally, so the ordinary pull would
# re-download 100-200 files per point.  This compares basenames first and scps
# only the missing ones in a single call per design point.
#
# Usage:
#   IBEM_BASE=/ospool/.../ge76_prod IBEM_LOCAL=/data/mluzum/ge76_results/prod \
#       osg_pull_missing.sh START END [WORKERS]
set -u
BASE=${IBEM_BASE:?IBEM_BASE required}
LOCAL=${IBEM_LOCAL:?IBEM_LOCAL required}
S=${1:-1}
E=${2:-500}
PAR=${3:-2}
SSH_OPTS="-o ControlMaster=auto -o ControlPath=/tmp/opencode/cm_osg -o ControlPersist=600 -o ConnectTimeout=20"

pull_one() {
  i=$1
  dp=$(printf 'dp%04d' "$i")
  dest=$LOCAL/$dp/tarballs
  mkdir -p "$dest" || { echo "$dp MKDIR_FAIL"; return; }
  rlist=$(ssh $SSH_OPTS osg "ls $BASE/$dp/spvn_results_*.tar.gz 2>/dev/null") \
    || { echo "$dp SSH_FAIL"; return; }
  if [ -z "$rlist" ]; then echo "$dp no_remote"; return; fi
  args=""
  n=0
  for f in $rlist; do
    b=$(basename "$f")
    [ -f "$dest/$b" ] && continue
    args="$args osg:$BASE/$dp/$b"
    n=$((n+1))
  done
  if [ "$n" -eq 0 ]; then echo "$dp already_complete"; return; fi
  if scp -q $SSH_OPTS $args "$dest/" 2>/dev/null; then
    m=$(ls "$dest"/*.tar.gz 2>/dev/null | wc -l)
    echo "$dp pulled=$n local_total=$m"
  else
    echo "$dp SCP_FAIL n=$n"
  fi
}
export -f pull_one
export BASE LOCAL SSH_OPTS
seq "$S" "$E" | xargs -P "$PAR" -I{} bash -c 'pull_one {}'
echo PULL_MISSING_DONE
