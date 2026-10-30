#!/bin/bash
# HTCondor job: one design point. Arguments: CAMPAIGN POINT IMAGE [run_xsec options]
# The scratch is the node's local job directory; the output goes straight to the
# shared /data over NFS, renamed into place only when complete.
campaign=$1
point=$2
image=$3
shift 3
scratch=${_CONDOR_SCRATCH_DIR:-$PWD}/xsec
mkdir -p "$scratch"
exec singularity exec --contain -B /data/mluzum -B "$scratch" "$image" \
  python3 /data/mluzum/GeSe/scripts/cross_section/run_xsec.py \
  --campaign "$campaign" --points "$point" --workers 1 --scratch "$scratch" \
  --log "$scratch/run.log" "$@"
