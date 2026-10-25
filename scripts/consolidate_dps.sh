#!/bin/bash
# Consolidate complete design points into one h5 each: merged/<dp>/<dp>.h5,
# with the block-level accounting kept as merged/<dp>/csv.tgz.
#
# Sources, in order of preference:
#   prod/<dp>/spvn_results/            extracted dir layout (used in place)
#   prod/<dp>/tarballs/*.tar.gz        per-job archives (extracted to a temp dir)
#   prod/<dp>/raw_spvn_results.tar.gz  a dir-layout tree packed earlier
#
# The raw tarballs are KEPT: they are the local record (100 files per dp) and
# extraction is what exhausted the local inode table.  One design point is
# extracted at a time per worker into /tmp/opencode/merge_tmp and removed
# afterwards.  Resumable: dps whose merged file already exists are skipped.
set -u
LIST=${1:-}
PROD=/data/mluzum/ge76_results/prod
OUT=/data/mluzum/ge76_results/merged
COMBINE=/data/mluzum/GeSe/combine_multiple_hdf5.py
TMP=/tmp/opencode/merge_tmp
mkdir -p "$OUT" "$TMP" || exit 1

# Without an explicit list, consolidate every design point that looks complete:
# 100 job tarballs (archive layout) or 100 blocks of events_drawn CSVs (dir).
if [ -z "$LIST" ]; then
  LIST=$TMP/complete.txt
  : > "$LIST"
  for d in "$PROD"/dp*; do
    dp=$(basename "$d")
    if [ "$(ls "$d"/tarballs/*.tar.gz 2>/dev/null | wc -l)" -eq 100 ]; then
      echo "$dp" >> "$LIST"
    elif [ "$(ls "$d"/spvn_results/events_drawn_*.csv 2>/dev/null | wc -l)" -eq 100 ]; then
      echo "$dp" >> "$LIST"
    fi
  done
  echo "auto-detected $(wc -l < "$LIST") complete design points"
fi

one() {
  dp=$1
  odir=$OUT/$dp
  if [ -s "$odir/$dp.h5" ]; then echo "$dp already merged"; return; fi
  tmpd=$TMP/$dp
  rm -rf "$tmpd"; mkdir -p "$tmpd"
  src=""
  if [ -d "$PROD/$dp/spvn_results" ]; then
    src=$PROD/$dp/spvn_results
  elif ls "$PROD/$dp"/tarballs/*.tar.gz >/dev/null 2>&1; then
    for t in "$PROD/$dp"/tarballs/*.tar.gz; do tar xzf "$t" -C "$tmpd" || { echo "$dp EXTRACT_FAILED"; return; }; done
    src=$tmpd/spvn_results
  elif [ -f "$PROD/$dp/raw_spvn_results.tar.gz" ]; then
    tar xzf "$PROD/$dp/raw_spvn_results.tar.gz" -C "$tmpd" || { echo "$dp EXTRACT_FAILED"; return; }
    src=$tmpd/spvn_results
  fi
  if [ -z "$src" ] || [ ! -d "$src" ]; then echo "$dp NO_SOURCE"; rm -rf "$tmpd"; return; fi
  n=$(ls "$src"/spvn_results_*.h5 2>/dev/null | wc -l)
  if [ "$n" -lt 1 ]; then echo "$dp NO_H5"; rm -rf "$tmpd"; return; fi
  mkdir -p "$odir"
  ( cd "$odir" && python3 "$COMBINE" "$src" > merge.log 2>&1 && mv spvn_results.h5 "$dp.h5" ) \
    || { echo "$dp MERGE_FAILED"; rm -rf "$tmpd"; return; }
  if ls "$src"/events_drawn_*.csv >/dev/null 2>&1; then
    ( cd "$src" && tar czf "$odir/csv.tgz" events_drawn_*.csv ) || echo "$dp CSV_TAR_FAILED"
  fi
  rm -rf "$tmpd"
  echo "$dp DONE $(du -h "$odir/$dp.h5" | cut -f1) h5=$n"
}
export -f one; export PROD OUT COMBINE TMP
xargs -P 2 -n 1 bash -c 'one "$0"' < "$LIST"
echo CONSOLIDATION_DONE
