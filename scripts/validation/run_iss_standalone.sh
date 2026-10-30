#!/bin/bash
# Run one iSS sampling on a saved MUSIC surface, inside the campaign image.
#   run_iss_standalone.sh <iSS.e> <iSS_parameters.dat> <surface.dat> <music_input> <outdir> <seed> [key=value ...]
set -e
iss=$1; par=$2; surf=$3; mi=$4; out=$5; seed=$6; shift 6
rm -rf "$out"; mkdir -p "$out/results"
cp "$par" "$out/iSS_parameters.dat"
ln -s /opt/iEBE-MUSIC/codes/iSS_code/iSS_tables "$out/iSS_tables"
ln -s "$surf" "$out/results/surface.dat"
cp "$mi" "$out/results/music_input"
cd "$out"
export OMP_NUM_THREADS=1
"$iss" randomSeed=$seed "$@" > run.log 2>&1
