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
# Overridable for a second campaign tree.
PROD=${IBEM_PROD:-/data/mluzum/ge76_results/prod}
OUT=${IBEM_OUT:-/data/mluzum/ge76_results/merged}
MERGE=/data/mluzum/GeSe/scripts/merge_dp_h5.py
TMP=/tmp/opencode/merge_tmp
# A complete batch of 100 jobs yields ~96-99 archives (some events have empty
# freeze-out surfaces), so requiring 100 sources would never merge a
# single-batch point.  Treat a batch as complete at MIN_SOURCES.
MIN_SOURCES=${MIN_SOURCES:-90}
mkdir -p "$OUT" "$TMP" || exit 1

# Source fingerprint for a dp: how many archives and how many packed dir blocks
# are present.  Different batches add archives (100 -> 300 -> 500); a purged
# dir-layout tree exists only as raw_spvn_results.tar.gz.  Both are merged
# together (event ids are unique across batches, so their h5 names never clash),
# which is why the fingerprint keeps the two numbers separate.
src_fingerprint() {
  local d=$1
  local tars=0 raw=0 dir=0
  [ -d "$d/tarballs" ] && tars=$(ls "$d"/tarballs/*.tar.gz 2>/dev/null | wc -l)
  [ -f "$d/raw_spvn_results.tar.gz" ] && \
    raw=$(tar tzf "$d/raw_spvn_results.tar.gz" 2>/dev/null | grep -c 'events_drawn_.*\.csv$')
  [ -d "$d/spvn_results" ] && \
    dir=$(ls "$d"/spvn_results/events_drawn_*.csv 2>/dev/null | wc -l)
  echo "tars=${tars} raw=${raw} dir=${dir}"
}

src_total() {
  local f
  f=$(src_fingerprint "$1")
  echo "$f" | sed -E 's/[a-z]+=//g' | awk '{print $1+$2+$3}'
}

# Build the work list: dps whose source count is a complete batch multiple and
# differs from the count recorded in their merged file.
if [ -z "$LIST" ]; then
  LIST=$TMP/worklist.txt
  : > "$LIST"
  for d in "$PROD"/dp*; do
    dp=$(basename "$d")
    fp=$(src_fingerprint "$d")
    n=$(src_total "$d")
    [ "$n" -ge "$MIN_SOURCES" ] || continue
    if [ -s "$OUT/$dp/$dp.h5" ] && [ "$(cat "$OUT/$dp/sources.txt" 2>/dev/null)" = "$fp" ]; then
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
  fp=$(src_fingerprint "$d")
  n=$(src_total "$d")
  if [ "$n" -lt "$MIN_SOURCES" ]; then echo "$dp SKIP sources=$n"; return; fi
  if [ -s "$odir/$dp.h5" ] && [ "$(cat "$odir/sources.txt" 2>/dev/null)" = "$fp" ]; then
    echo "$dp up-to-date ($fp)"; return
  fi
  rm -rf "$tmpd"; mkdir -p "$tmpd"
  src=""
  if [ -d "$d/spvn_results" ]; then
    src=$d/spvn_results
  else
    # Extract EVERY source into one tree: tagged batch archives and the packed
    # dir-layout tree.  Files are named after the global event id, so batches
    # never collide and the merge sees the union.
    src=$tmpd/spvn_results
    if [ "$(ls "$d"/tarballs/*.tar.gz 2>/dev/null | wc -l)" -gt 0 ]; then
      for t in "$d"/tarballs/*.tar.gz; do
        tar xzf "$t" -C "$tmpd" || { echo "$dp EXTRACT_FAILED"; rm -rf "$tmpd"; return; }
      done
    fi
    if [ -f "$d/raw_spvn_results.tar.gz" ]; then
      tar xzf "$d/raw_spvn_results.tar.gz" -C "$tmpd" || { echo "$dp EXTRACT_FAILED"; rm -rf "$tmpd"; return; }
    fi
  fi
  if [ -z "$src" ] || [ ! -d "$src" ]; then echo "$dp NO_SOURCE"; rm -rf "$tmpd"; return; fi
  mkdir -p "$odir"
  if ! python3 "$MERGE" "$src" "$odir/$dp.h5.tmp" > "$odir/merge.log" 2>&1; then
    echo "$dp MERGE_FAILED"; rm -f "$odir/$dp.h5.tmp"; rm -rf "$tmpd"; return
  fi
  mv "$odir/$dp.h5.tmp" "$odir/$dp.h5"
  echo "$fp" > "$odir/sources.txt"
  if ls "$src"/events_drawn_*.csv >/dev/null 2>&1; then
    ( cd "$src" && tar czf "$odir/csv.tgz" events_drawn_*.csv ) || echo "$dp CSV_TAR_FAILED"
  fi
  rm -rf "$tmpd"
  echo "$dp DONE $(du -h "$odir/$dp.h5" | cut -f1) sources=$n [$fp]"
}
export -f one src_fingerprint src_total; export MIN_SOURCES export PROD OUT MERGE TMP
xargs -P 2 -n 1 bash -c 'one "$0"' < "$LIST"
echo CONSOLIDATION_DONE
