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
# Only dps whose local count is a multiple of 100 are considered, i.e. whole
# batches; a half-pulled point is never pruned.
#
# Usage:
#   osg_prune_pulled.sh --dry-run [--dps 1-1460] [--pause 5] [--max-load 500]
#   osg_prune_pulled.sh --apply   [--dps 1-1460]
#
# The load guard skips (does not fail) whenever the AP load average is above
# --max-load, so this can be left running during quiet periods without adding
# metadata pressure during a storm.
set -u
BASE=/ospool/ap40/data/matthew.luzum/ge76_prod
LOCAL=/data/mluzum/ge76_results/prod
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
  [ "$nloc" -ge 100 ] || { skipped=$((skipped+1)); continue; }
  [ $((nloc % 100)) -eq 0 ] || { skipped=$((skipped+1)); continue; }
  # readable local copy?
  bad=0
  for t in "$dest"/tarballs/*.tar.gz; do
    tar tzf "$t" > /dev/null 2>&1 || { bad=1; break; }
  done
  [ $bad -eq 0 ] || { echo "$dp LOCAL_UNREADABLE"; skipped=$((skipped+1)); continue; }
  # one remote query: archive count for this dp
  nrem=$(timeout 120 ssh -o ControlMaster=auto -o ControlPath=/tmp/opencode/cm_osg \
            -o ConnectTimeout=20 osg "ls $BASE/$dp/spvn_results_*.tar.gz 2>/dev/null | wc -l" 2>/dev/null)
  nrem=${nrem:-none}
  if [ "$nrem" = "none" ]; then echo "$dp REMOTE_QUERY_FAILED"; skipped=$((skipped+1)); continue; fi
  if [ "$nrem" != "$nloc" ]; then echo "$dp count_mismatch local=$nloc remote=$nrem"; skipped=$((skipped+1)); continue; fi
  verified=$((verified+1))
  if [ $APPLY -eq 1 ]; then
    load=$(timeout 60 ssh -o ControlMaster=auto -o ControlPath=/tmp/opencode/cm_osg \
             -o ConnectTimeout=20 osg 'cut -d" " -f1 /proc/loadavg' 2>/dev/null)
    if [ -n "$load" ] && [ "${load%.*}" -gt "$MAXLOAD" ]; then
      echo "$dp SKIP_LOAD load=$load"; skipped=$((skipped+1)); sleep "$PAUSE"; continue
    fi
    timeout 300 ssh -o ControlMaster=auto -o ControlPath=/tmp/opencode/cm_osg \
      -o ConnectTimeout=20 osg "rm -f $BASE/$dp/spvn_results_*.tar.gz $BASE/$dp/events_drawn_*.csv 2>/dev/null" 2>/dev/null
    echo "$dp pruned ($nloc archives)"
    pruned=$((pruned+1))
  else
    echo "$dp would prune ($nloc archives)"
  fi
  sleep "$PAUSE"
done
echo "PRUNE_DONE mode=$([ $APPLY -eq 1 ] && echo APPLY || echo DRY-RUN) verified=$verified pruned=$pruned skipped=$skipped"
