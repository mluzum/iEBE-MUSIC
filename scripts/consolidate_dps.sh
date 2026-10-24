#!/bin/bash
# Consolidate design points into one h5 per dp: all event groups of
# prod/<dp>/spvn_results/*.h5 copied into merged/<dp>/<dp>.h5 with the repo's
# combine_multiple_hdf5.py (h5copy-based, one group per event, group = event id).
# Skips dps whose output already exists, so it is resumable.  Two dps in
# parallel; both streams are purely local (no AP load).
set -u
LIST=${1:-/tmp/opencode/complete_dps.txt}
PROD=/data/mluzum/ge76_results/prod
OUT=/data/mluzum/ge76_results/merged
COMBINE=/data/mluzum/GeSe/combine_multiple_hdf5.py
mkdir -p "$OUT" || exit 1

one() {
  dp=$1
  odir=$OUT/$dp
  if [ -s "$odir/$dp.h5" ]; then echo "$dp already merged"; return; fi
  mkdir -p "$odir"
  ( cd "$odir" && python3 "$COMBINE" "$PROD/$dp/spvn_results" > merge.log 2>&1 \
    && mv spvn_results.h5 "$dp.h5" && echo "$dp DONE $(du -h "$dp.h5" | cut -f1)" ) \
    || { echo "$dp FAILED"; }
}
export -f one; export OUT PROD COMBINE
xargs -P 2 -n 1 bash -c 'one "$0"' <"$LIST"
echo CONSOLIDATION_DONE
