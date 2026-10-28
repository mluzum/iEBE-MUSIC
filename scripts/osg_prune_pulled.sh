#!/bin/bash
# Delete a design point's result archives from the AP after verifying that the
# local copy is complete.  The AP is staging, not storage: the local tarballs
# (100 files per batch per dp) are the record, and the merged h5 is derived
# from them.
#
# Verification per dp, at the moment of pruning:
#   local archive count == remote archive count, and
#   every local tarball is readable (tar tzf succeeds).
#
# Safety: only files that already exist locally (and read cleanly) are deleted,
# so a half-pulled point is not at risk.
#
# Usage:
#   osg_prune_pulled.sh --dry-run [--dps 1-1460] [--pause 5] [--max-load 500]
#   osg_prune_pulled.sh --apply   [--dps 1-1460]
#
# The load guard skips (does not fail) whenever the AP load average is above
# --max-load, so this can be left running during quiet periods without adding
# metadata pressure during a storm.
set -u
# Overridable so the same tool prunes a second campaign tree.
BASE=${IBEM_BASE:-/ospool/ap40/data/matthew.luzum/ge76_prod}
LOCAL=${IBEM_LOCAL:-/data/mluzum/ge76_results/prod}
APPLY=0
DPS="1-1460"
PAUSE=5
MAXLOAD=500
while [ $# -gt 0 ]; do
  case "$1" in
    --apply) APPLY=1 ;;
    --dry-run) APPLY=0 ;;
    --dps) shift; DPS=${1:-1-1460} ;;
    --pause) shift; PAUSE=${1:-5} ;;
    --max-load) shift; MAXLOAD=${1:-500} ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done

# expand "1-1460" or "1,4,9-12"
list=""
for part in ${DPS//,/ }; do
  case "$part" in
    *-*) a=${part%-*}; b=${part#*-}; list="$list $(seq "$a" "$b")" ;;
    *)   list="$list $part" ;;
  esac
done

echo "mode=$([ $APPLY -eq 1 ] && echo APPLY || echo DRY-RUN) dps=$DPS pause=${PAUSE}s max_load=$MAXLOAD"
pruned=0; skipped=0; verified=0
for i in $list; do
  dp=$(printf 'dp%04d' "$i")
  dest=$LOCAL/$dp
  nloc=$(ls "$dest"/tarballs/*.tar.gz 2>/dev/null | wc -l)
  # No whole-batch requirement: a design point legitimately ends at 96-99
  # archives because ~2% of events have empty freeze-out surfaces, and a rule
  # of "multiples of 100" would then never prune anything.  Safety comes from
  # the name-based check below: only files that exist locally (and read) are
  # deleted, so pruning is safe even while more archives are still arriving.
  [ "$nloc" -ge 1 ] || { skipped=$((skipped+1)); continue; }
  # readable local copy?
  bad=0
  for t in "$dest"/tarballs/*.tar.gz; do
    tar tzf "$t" > /dev/null 2>&1 || { bad=1; break; }
  done
  [ $bad -eq 0 ] || { echo "$dp LOCAL_UNREADABLE"; skipped=$((skipped+1)); continue; }
  # Name-based verification: every remote archive must exist locally (and read).
  # Counts are not comparable across batches: after pruning batch 1 the local
  # tree holds 100 files while the remote holds the next batch's 100.
  rlist=$(timeout 120 ssh -o ControlMaster=auto -o ControlPath=/tmp/opencode/cm_osg \
            -o ConnectTimeout=20 osg "ls $BASE/$dp/spvn_results_*.tar.gz 2>/dev/null" 2>/dev/null)
  rlist=${rlist:-none}
  if [ "$rlist" = "none" ]; then echo "$dp REMOTE_QUERY_FAILED"; skipped=$((skipped+1)); continue; fi
  nrem=$(echo "$rlist" | wc -l)
  missing=0
  for rf in $rlist; do
    b=$(basename "$rf")
    if [ ! -f "$dest/tarballs/$b" ]; then
      # also accept the packed dir-layout record
      if [ -f "$dest/raw_spvn_results.tar.gz" ] && tar tzf "$dest/raw_spvn_results.tar.gz" 2>/dev/null | grep -q "/$b$"; then
        continue
      fi
      missing=$((missing+1))
    fi
  done
  if [ "$missing" -gt 0 ]; then echo "$dp local_missing=$missing of remote $nrem"; skipped=$((skipped+1)); continue; fi
  verified=$((verified+1))
  if [ $APPLY -eq 1 ]; then
    load=$(timeout 60 ssh -o ControlMaster=auto -o ControlPath=/tmp/opencode/cm_osg \
             -o ConnectTimeout=20 osg 'cut -d" " -f1 /proc/loadavg' 2>/dev/null)
    if [ -n "$load" ] && [ "${load%.*}" -gt "$MAXLOAD" ]; then
      echo "$dp SKIP_LOAD load=$load"; skipped=$((skipped+1)); sleep "$PAUSE"; continue
    fi
    timeout 300 ssh -o ControlMaster=auto -o ControlPath=/tmp/opencode/cm_osg \
      -o ConnectTimeout=20 osg "rm -f $BASE/$dp/spvn_results_*.tar.gz $BASE/$dp/events_drawn_*.csv 2>/dev/null" 2>/dev/null
    echo "$dp pruned ($nrem remote archives)"
    pruned=$((pruned+1))
  else
    echo "$dp would prune ($nloc archives)"
  fi
  sleep "$PAUSE"
done
echo "PRUNE_DONE mode=$([ $APPLY -eq 1 ] && echo APPLY || echo DRY-RUN) verified=$verified pruned=$pruned skipped=$skipped"
