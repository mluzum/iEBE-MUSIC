#!/bin/bash
# Consolidate design points into one h5 each: merged/<dp>/<dp>.h5,
# with the block-level accounting kept as merged/<dp>/csv.tgz.
#
# Sources, in order of preference:
#   prod/<dp>/spvn_results/            extracted dir layout (used in place)
#   prod/<dp>/tarballs/*.tar.gz        per-job archives (extracted to a temp dir)
#   prod/<dp>/raw_spvn_results.tar.gz  a dir-layout tree packed earlier
#
# The raw tarballs are KEPT: they are the local record (100 files per batch per
# dp) and extraction is what exhausted the local inode table.  One design point
# is extracted at a time per worker into /tmp/opencode/merge_tmp.
#
# Re-merging: merged/<dp>/sources.txt records how many source archives went
# into the h5.  A design point is re-merged when its source count changes (the
# augmentation adds 100 more archives per batch: 100 -> 300 -> 500).  Only
# counts that are a multiple of 100 are merged, so a half-delivered batch never
# produces a partial file.
set -u
LIST=${1:-}
PROD=/data/mluzum/ge76_results/prod
OUT=/data/mluzum/ge76_results/merged
MERGE=/data/mluzum/GeSe/scripts/merge_dp_h5.py
TMP=/tmp/opencode/merge_tmp
mkdir -p "$OUT" "$TMP" || exit 1

# Source count for a dp (archives, or blocks for the dir/packed layouts).
src_count() {
  local d=$1
  if [ "$(ls "$d"/tarballs/*.tar.gz 2>/dev/null | wc -l)" -gt 0 ]; then
    ls "$d"/tarballs/*.tar.gz 2>/dev/null | wc -l
  elif [ -d "$d/spvn_results" ]; then
    ls "$d"/spvn_results/events_drawn_*.csv 2>/dev/null | wc -l
  elif [ -f "$d/raw_spvn_results.tar.gz" ]; then
    tar tzf "$d/raw_spvn_results.tar.gz" 2>/dev/null | grep -c 'events_drawn_.*\.csv$'
  else
    echo 0
  fi
}

# Build the work list: dps whose source count is a complete batch multiple and
# differs from the count recorded in their merged file.
if [ -z "$LIST" ]; then
  LIST=$TMP/worklist.txt
  : > "$LIST"
  for d in "$PROD"/dp*; do
    dp=$(basename "$d")
    n=$(src_count "$d")
    [ "$n" -ge 100 ] || continue
    [ $((n % 100)) -eq 0 ] || continue
    if [ -s "$OUT/$dp/$dp.h5" ] && [ "$(cat "$OUT/$dp/sources.txt" 2>/dev/null)" = "$n" ]; then
      continue
    fi
    echo "$dp" >> "$LIST"
  done
  echo "work list: $(wc -l < "$LIST") design points"
fi

one() {
  dp=$1
  odir=$OUT/$dp
  tmpd=$TMP/$dp
  d=$PROD/$dp
  n=$(src_count "$d")
  if [ "$n" -lt 100 ] || [ $((n % 100)) -ne 0 ]; then echo "$dp SKIP count=$n"; return; fi
  if [ -s "$odir/$dp.h5" ] && [ "$(cat "$odir/sources.txt" 2>/dev/null)" = "$n" ]; then
    echo "$dp up-to-date ($n sources)"; return
  fi
  rm -rf "$tmpd"; mkdir -p "$tmpd"
  src=""
  if [ -d "$d/spvn_results" ]; then
    src=$d/spvn_results
  elif [ "$(ls "$d"/tarballs/*.tar.gz 2>/dev/null | wc -l)" -gt 0 ]; then
    for t in "$d"/tarballs/*.tar.gz; do
      tar xzf "$t" -C "$tmpd" || { echo "$dp EXTRACT_FAILED"; rm -rf "$tmpd"; return; }
    done
    src=$tmpd/spvn_results
  elif [ -f "$d/raw_spvn_results.tar.gz" ]; then
    tar xzf "$d/raw_spvn_results.tar.gz" -C "$tmpd" || { echo "$dp EXTRACT_FAILED"; rm -rf "$tmpd"; return; }
    src=$tmpd/spvn_results
  fi
  if [ -z "$src" ] || [ ! -d "$src" ]; then echo "$dp NO_SOURCE"; rm -rf "$tmpd"; return; fi
  mkdir -p "$odir"
  if ! python3 "$MERGE" "$src" "$odir/$dp.h5.tmp" > "$odir/merge.log" 2>&1; then
    echo "$dp MERGE_FAILED"; rm -f "$odir/$dp.h5.tmp"; rm -rf "$tmpd"; return
  fi
  mv "$odir/$dp.h5.tmp" "$odir/$dp.h5"
  echo "$n" > "$odir/sources.txt"
  if ls "$src"/events_drawn_*.csv >/dev/null 2>&1; then
    ( cd "$src" && tar czf "$odir/csv.tgz" events_drawn_*.csv ) || echo "$dp CSV_TAR_FAILED"
  fi
  rm -rf "$tmpd"
  echo "$dp DONE $(du -h "$odir/$dp.h5" | cut -f1) sources=$n"
}
export -f one src_count; export PROD OUT MERGE TMP
xargs -P 2 -n 1 bash -c 'one "$0"' < "$LIST"
echo CONSOLIDATION_DONE
