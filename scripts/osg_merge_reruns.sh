#!/bin/bash
# Fold re-run block outputs back into their design point, for both layouts:
#   directory layout: rerun/pN/spvn_results/*.h5        -> dp/spvn_results/
#   archive layout:   rerun/pN/spvn_results[_e<off>]_0.tar.gz
#                                      -> dp/spvn_results[_e<off>]_<N>.tar.gz
# Re-runs are submitted as single jobs (-n 1), so their ProcessId is 0 while the
# block they cover is N; the archive is renamed accordingly so the dp keeps one
# archive per block.  The optional _e<offset> batch tag (batch 2 onward) is
# preserved so a re-run never falls into another batch's name space.
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
    for csv in "$d"/spvn_results/events_drawn_0.csv "$d"/spvn_results/events_drawn_e*_0.csv; do
      [ -f "$csv" ] || continue
      b=$(basename "$csv"); tag=""
      case "$b" in events_drawn_e*) tag=$(echo "$b" | sed -E 's/^events_drawn(_e[0-9]+)_0\.csv$/\1/');; esac
      mv "$csv" "$dp/spvn_results/events_drawn${tag}_${blk}.csv"
    done
  else
    for src in "$d"/spvn_results_0.tar.gz "$d"/spvn_results_e*_0.tar.gz; do
      [ -f "$src" ] || continue
      b=$(basename "$src"); tag=""
      case "$b" in spvn_results_e*) tag=$(echo "$b" | sed -E 's/^spvn_results(_e[0-9]+)_0\.tar\.gz$/\1/');; esac
      echo "merge $(basename "$dp") block $blk (archive${tag})"
      cp -n "$src" "$dp/spvn_results${tag}_${blk}.tar.gz"
    done
  fi
done
echo "merged"
