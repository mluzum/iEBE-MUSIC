#!/bin/bash
# Pull design points, handling both result layouts:
#   layout A (dp0001-0460): <dp>/spvn_results/            (directory of loose files)
#   layout B (dp0461+):     <dp>/spvn_results_<n>.tar.gz  (one archive per job)
#
# Why archives: the AP pays ~90 ms of CephFS metadata latency per file, so a
# directory of ~4000 files takes minutes to pack there, while 100 archives take
# seconds.  The transfer itself is not the bottleneck.
#
# Connection discipline: the AP blackholes port 22 for ~30 min after a burst,
# so this uses <= 2 connections per design point and <= 4 workers.
#
# Usage: osg_pull_results.sh START END [PAR] [LISTFILE]
#   LISTFILE: optional file with one design-point index per line; when given,
#   only those indices are pulled (use it to re-do gaps without repacking
#   design points that are already local).
set -u
BASE=/ospool/ap40/data/matthew.luzum/ge76_prod
TAR=/ospool/ap40/data/matthew.luzum/tmp_pull
LOCAL=/data/mluzum/ge76_results/prod
START=${1:-21}
END=${2:-60}
PAR=${3:-3}
LISTFILE=${4:-}
# Multiplex everything over ONE TCP connection: the AP blackholes port 22 for
# ~30 min after a burst of new connections, and a per-dp probe+count+copy cycle
# is three connections.  With ControlMaster=auto the first connection becomes
# the master and every later ssh/scp reuses it until ControlPersist expires.
SSH="ssh -o ControlMaster=auto -o ControlPath=/tmp/opencode/cm_osg -o ControlPersist=600 -o ConnectTimeout=15"
SCP="scp -q -o ControlMaster=auto -o ControlPath=/tmp/opencode/cm_osg -o ControlPersist=600"
mkdir -p /tmp/opencode/tars

pull_dir_layout() {
  dp=$1; dest=$2
  # Stream the remote tar straight to a LOCAL FILE (one tarball per dp) instead
  # of extracting it: extraction costs ~2000 files/dp and is what exhausted the
  # local inode table.  Writing the tarball on the AP is impossible once the
  # data disk is at its file quota, so the stream goes through ssh to local disk.
  rc=$($SSH osg "ls $BASE/$dp/spvn_results/spvn_results_*.h5 | wc -l" 2>/dev/null) \
    || { echo "$dp COUNT FAILED"; return 1; }
  $SSH osg "cd $BASE/$dp && tar czf - spvn_results" 2>/dev/null > "$dest/raw_spvn_results.tar.gz" \
    || { echo "$dp STREAM FAILED"; rm -f "$dest/raw_spvn_results.tar.gz"; return 1; }
  lc=$(tar tzf "$dest/raw_spvn_results.tar.gz" 2>/dev/null | grep -c 'spvn_results_[0-9]*\.h5$')
  echo "$dp layout=dir h5_in_tar=$lc/$rc"
  [ "$lc" = "$rc" ]
}

pull_tar_layout() {
  dp=$1; dest=$2
  # Keep the per-job tarballs as the local record; do NOT extract them here.
  # Extracting costs ~6200 files per design point (20 events x h5 + TRENTO
  # summary + grid extent, plus target_nucleus.hdf per job), which exhausted
  # the local inode table at ~160 points.  100 tarballs per dp carry the same
  # data and are extracted only when a design point is consolidated.
  mkdir -p "$dest/tarballs"
  $SCP "osg:$BASE/$dp/spvn_results_*.tar.gz" "$dest/tarballs/" || { echo "$dp SCP FAILED"; return 1; }
  ntar=$(ls "$dest"/tarballs/*.tar.gz 2>/dev/null | wc -l)
  rtar=$($SSH osg "ls $BASE/$dp/spvn_results_*.tar.gz 2>/dev/null | wc -l" 2>/dev/null)
  exp=0; bad=0
  for t in "$dest"/tarballs/*.tar.gz; do
    c=$(tar tzf "$t" 2>/dev/null | grep -c '\.h5$'); [ -z "$c" ] && c=0
    exp=$((exp + c))
    [ "$c" -eq 0 ] && bad=$((bad+1))
  done
  echo "$dp layout=tars archives=$ntar/$rtar h5_in_tars=$exp bad=$bad"
  [ "$ntar" = "$rtar" ] && [ "$bad" -eq 0 ]
}

pull_one() {
  i=$1
  dp=$(printf 'dp%04d' "$i")
  dest=$LOCAL/$dp
  mkdir -p "$dest"
  probe() {
    $SSH osg "if [ -d $BASE/$dp/spvn_results ]; then echo dir; elif ls $BASE/$dp/spvn_results_*.tar.gz >/dev/null 2>&1; then echo tars; else echo none; fi" 2>/dev/null
  }
  kind=$(probe); st=$?
  # An empty answer means the probe failed (timeout/route flap), NOT that the
  # design point is empty.  Conflating the two silently skipped 45 points.
  if [ $st -ne 0 ] || [ -z "$kind" ]; then
    sleep 20
    kind=$(probe)
  fi
  case "$kind" in
    "")   echo "$dp PROBE FAILED (skipped, re-run later)" ;;

    dir)  pull_dir_layout "$dp" "$dest" || { echo "$dp RETRY"; sleep 20; pull_dir_layout "$dp" "$dest" || echo "$dp GAVE UP"; } ;;
    tars) pull_tar_layout "$dp" "$dest" || { echo "$dp RETRY"; sleep 20; pull_tar_layout "$dp" "$dest" || echo "$dp GAVE UP"; } ;;
    *)    echo "$dp no results yet" ;;
  esac
}

if [ -n "$LISTFILE" ]; then
  IDX=$(cat "$LISTFILE")
else
  IDX=$(seq "$START" "$END")
fi

for i in $IDX; do
  while [ "$(jobs -rp | wc -l)" -ge "$PAR" ]; do wait -n; done
  pull_one "$i" &
done
wait
echo BUNDLE_PULL_DONE
