#!/bin/bash
# Pull only those AP archives whose basenames are missing locally, bundled.
#
# Two problems make a per-file pull unusable on the campaign-1 A=76 augmentation
# points (dp1-500 hold ~300 archives each while the local tree holds ~100):
#   * the ordinary pull re-downloads the 100-200 archives we already have, and
#   * opening files one at a time from CephFS runs at ~0.5 MB/s, i.e. ~5 min per
#     design point, or ~20 h for the range.
# So: list the directory once, diff basenames locally, tar the missing files on
# the AP into one bundle on its *local* /tmp (not the CephFS home), move that one
# file, and extract it.  One metadata walk plus one transfer per design point.
#
# Usage:
#   IBEM_BASE=/ospool/.../ge76_prod IBEM_LOCAL=/data/.../ge76_results/prod \
#       osg_pull_missing.sh START END [WORKERS]
#   IBEM_CM=/tmp/opencode/cm_pull   # dedicated ControlMaster (default)
set -u
BASE=${IBEM_BASE:?IBEM_BASE required}
LOCAL=${IBEM_LOCAL:?IBEM_LOCAL required}
S=${1:-1}
E=${2:-500}
PAR=${3:-2}
# Sharing one ControlMaster with a long-lived sync loop stalls every call behind
# that loop's channels (a 300-entry glob took 1301 s shared vs 3.2 s private).
CM=${IBEM_CM:-/tmp/opencode/cm_pull}
SSH_OPTS="-o ControlMaster=auto -o ControlPath=$CM -o ControlPersist=600 -o ConnectTimeout=20"

pull_one() {
  i=$1
  dp=$(printf 'dp%04d' "$i")
  dest=$LOCAL/$dp/tarballs
  mkdir -p "$dest" || { echo "$dp MKDIR_FAIL"; return; }

  # 1. one readdir+stat on the AP for the whole directory
  rlist=$(ssh $SSH_OPTS osg "ls $BASE/$dp/*.tar.gz 2>/dev/null") \
    || { echo "$dp SSH_FAIL"; return; }
  if [ -z "$rlist" ]; then echo "$dp no_remote"; return; fi

  # 2. diff basenames locally (no extra round trip)
  missing=""
  n=0
  for f in $rlist; do
    b=$(basename "$f")
    [ -f "$dest/$b" ] && continue
    missing="$missing $b"
    n=$((n+1))
  done
  if [ "$n" -eq 0 ]; then echo "$dp already_complete"; return; fi

  # 3. bundle on the AP's local /tmp, so CephFS is read once and written never
  bundle=/tmp/ibem_$dp.tar
  err=$(ssh $SSH_OPTS osg "cd $BASE/$dp && rm -f $bundle && tar cf $bundle $missing" 2>&1)
  if [ $? -ne 0 ]; then
    echo "$dp TAR_FAIL n=$n: $(echo "$err" | tail -1)"
    ssh $SSH_OPTS osg "rm -f $bundle" 2>/dev/null
    return
  fi

  # 4. one transfer, then unpack
  if scp -q $SSH_OPTS "osg:$bundle" "$dest/.bundle.tar" 2>/dev/null; then
    tar xf "$dest/.bundle.tar" -C "$dest" && rm -f "$dest/.bundle.tar"
    m=$(ls "$dest"/*.tar.gz 2>/dev/null | wc -l)
    echo "$dp pulled=$n local_total=$m"
  else
    echo "$dp SCP_FAIL n=$n"
    rm -f "$dest/.bundle.tar"
  fi
  ssh $SSH_OPTS osg "rm -f $bundle" 2>/dev/null
}
export -f pull_one
export BASE LOCAL SSH_OPTS
seq "$S" "$E" | xargs -P "$PAR" -I{} bash -c 'pull_one {}'
echo PULL_MISSING_DONE
