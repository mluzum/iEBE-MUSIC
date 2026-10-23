#!/bin/bash
# Pull design points, handling both result layouts:
#   layout A (dp0001-0460): <dp>/spvn_results/        (directory of loose files)
#   layout B (dp0461+):     <dp>/spvn_results_<n>.tar.gz  (one archive per job)
#
# Why archives: the AP pays ~90 ms of CephFS metadata latency per file, so a
# directory of ~4000 files takes minutes to pack there, while 100 archives take
# seconds.  The transfer itself is not the bottleneck.
#
# Connection discipline: the AP blackholes port 22 for ~30 min after a burst,
# so this uses 2 connections per design point and <= 4 workers.
set -u
BASE=/ospool/ap40/data/matthew.luzum/ge76_prod
TAR=/ospool/ap40/data/matthew.luzum/tmp_pull
LOCAL=/data/mluzum/ge76_results/prod
START=${1:-21}
END=${2:-60}
PAR=${3:-3}
SSH="ssh -o ControlMaster=no -o ControlPath=none -o ConnectTimeout=15"
SCP="scp -q -o ControlMaster=no -o ControlPath=none"
mkdir -p /tmp/opencode/tars

pull_one() {
  i=$1
  dp=$(printf 'dp%04d' "$i")
  dest=$LOCAL/$dp
  mkdir -p "$dest"

  kind=$($SSH osg "if [ -d $BASE/$dp/spvn_results ]; then echo dir; elif ls $BASE/$dp/spvn_results_*.tar.gz >/dev/null 2>&1; then echo tars; else echo none; fi" 2>/dev/null)
  case "$kind" in
    dir)
      rc=$($SSH osg "mkdir -p $TAR && cd $BASE/$dp && tar czf $TAR/$dp.tgz spvn_results && ls $BASE/$dp/spvn_results/spvn_results_*.h5 | wc -l" 2>/dev/null) \
        || { echo "$dp TAR FAILED"; return 1; }
      $SCP osg:$TAR/$dp.tgz /tmp/opencode/tars/ || { echo "$dp SCP FAILED"; return 1; }
      tar xzf /tmp/opencode/tars/$dp.tgz -C "$dest" || { echo "$dp EXTRACT FAILED"; return 1; }
      rm -f /tmp/opencode/tars/$dp.tgz
      $SSH osg "rm -f $TAR/$dp.tgz" 2>/dev/null
      lc=$(ls "$dest"/spvn_results/spvn_results_*.h5 2>/dev/null | wc -l)
      echo "$dp layout=dir local=$lc remote=$rc"
      [ "$lc" = "$rc" ] || echo "$dp COUNT MISMATCH"
      ;;
    tars)
      mkdir -p "$dest/tarballs"
      rc=$($SSH osg "ls $BASE/$dp/spvn_results_*.tar.gz | wc -l" 2>/dev/null) \
        || { echo "$dp QUERY FAILED"; return 1; }
      $SCP "osg:$BASE/$dp/spvn_results_*.tar.gz" "$dest/tarballs/" || { echo "$dp SCP FAILED"; return 1; }
      ntar=$(ls "$dest"/tarballs/*.tar.gz 2>/dev/null | wc -l)
      # unpack, and count the h5 members as the authoritative expected number
      exp=0
      for t in "$dest"/tarballs/*.tar.gz; do
        exp=$((exp + $(tar tzf "$t" | grep -c '\.h5$')))
        tar xzf "$t" -C "$dest" || { echo "$dp EXTRACT FAILED"; return 1; }
      done
      lc=$(ls "$dest"/spvn_results/spvn_results_*.h5 2>/dev/null | wc -l)
      echo "$dp layout=tars archives=$ntar/$rc h5=$lc/$exp"
      [ "$lc" = "$exp" ] || echo "$dp COUNT MISMATCH"
      rm -rf "$dest/tarballs"
      ;;
    *)
      echo "$dp no results yet"
      ;;
  esac
}

for i in $(seq "$START" "$END"); do
  while [ "$(jobs -rp | wc -l)" -ge "$PAR" ]; do wait -n; done
  pull_one "$i" &
done
wait
echo BUNDLE_PULL_DONE
