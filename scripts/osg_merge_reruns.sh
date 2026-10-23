#!/bin/bash
# Fold re-run block outputs back into their design point, for both layouts:
#   directory layout: rerun/pN/spvn_results/*.h5   -> dp/spvn_results/
#   archive layout:   rerun/pN/spvn_results_0.tar.gz -> dp/spvn_results_<N>.tar.gz
# Re-runs are submitted as single jobs (-n 1), so their ProcessId is 0 while the
# block they cover is N; the archive is renamed accordingly so the dp keeps one
# archive per block.
set -u
BASE=${1:-/ospool/ap40/data/matthew.luzum/ge76_prod}
for d in $BASE/dp*/rerun/p*; do
  [ -d "$d" ] || continue
  dp=$(dirname "$(dirname "$d")")
  blk=$(basename "$d" | sed 's/^p//')
  if [ -d "$d/spvn_results" ]; then
    n=$(ls "$d"/spvn_results/spvn_results_*.h5 2>/dev/null | wc -l)
    [ "$n" = "0" ] && continue
    echo "merge $(basename "$dp") block $blk (dir): $n h5"
    cp -n "$d"/spvn_results/spvn_results_*.h5 "$dp"/spvn_results/ 2>/dev/null
    cp -n "$d"/spvn_results/trento_event_summary_*.txt "$dp"/spvn_results/ 2>/dev/null
    [ -f "$d/spvn_results/events_drawn_0.csv" ] && \
      mv "$d/spvn_results/events_drawn_0.csv" "$dp/spvn_results/events_drawn_${blk}.csv"
  elif [ -f "$d/spvn_results_0.tar.gz" ]; then
    echo "merge $(basename "$dp") block $blk (archive)"
    cp -n "$d/spvn_results_0.tar.gz" "$dp/spvn_results_${blk}.tar.gz"
  fi
done
echo "merged"
