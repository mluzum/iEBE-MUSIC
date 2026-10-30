#!/usr/bin/env bash
# Re-run ONE global event id of a campaign design point inside the container,
# exactly as the OSG job that owned it did, optionally with a replacement
# driver.  Called by scripts/rerun_events_local.py; cwd = an empty scratch dir.
#
#   rerun_event_inner.sh <param.py> <event id> <events per job> [driver.py]
#
# The job folder must be the one the campaign used (event_<block>, generated
# with -id <process> -n_hydro <events per job>): iSS's base seed is derived
# from the folder's id, and the per-event streams from the global id.  Only the
# driver call is narrowed to the one event (n_hydro 1, first id = the event).
set -e
parafile=$1
ev=$2
per_job=$3
driver=${4:-}

export PYTHONIOENCODING=utf-8
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export PATH="${PATH}:/usr/lib64/openmpi/bin:/usr/local/gsl/2.5/x86_64/bin"
export LD_LIBRARY_PATH="${LD_LIBRARY_PATH}:/usr/local/lib:/usr/local/gsl/2.5/x86_64/lib64"
export HOME="${PWD}"
export XDG_DATA_HOME="${HOME}/.local/share"
export XDG_CACHE_HOME="${HOME}/.cache"
export TRENTO_CACHE="${HOME}/.trento"
mkdir -p "${XDG_DATA_HOME}/trento" "${XDG_CACHE_HOME}" "${TRENTO_CACHE}"

proc=$(( (ev % 2000) / per_job ))
block=$(( ev - ev % per_job ))
cp "${parafile}" .
par=$(basename "${parafile}")

/opt/iEBE-MUSIC/generate_jobs.py -w playground -c OSG -par "${par}" \
    -id ${proc} -n_th 1 -n_urqmd 1 -n_hydro ${per_job} -seed 0 \
    --event_start_id ${block} --event_end_id ${block} --nocopy --continueFlag \
    > generate.log 2>&1

cd "playground/event_${block}"
sed -i "s/hydro_plus_UrQMD_driver.py \([^ ]*\) \([^ ]*\) ${per_job} ${block} /hydro_plus_UrQMD_driver.py \1 \2 1 ${ev} /" \
    submit_job.script
grep -q "hydro_plus_UrQMD_driver.py [^ ]* [^ ]* 1 ${ev} " submit_job.script
if [ -n "${driver}" ]; then
    cp "${driver}" hydro_plus_UrQMD_driver.py
fi
{
    grep -H "Initial_profile\|Initial_time_tau_0\|preEqVisFactor\|quest_revert" \
        ../model_parameters/MUSIC/music_input_mode_2
    grep -H "include_deltaf\|bulk_deltaf_kind" ../model_parameters/iSS/iSS_parameters.dat
    grep -H "^python3 hydro_plus_UrQMD_driver.py" submit_job.script
} > ../../effective_parameters.txt 2>/dev/null || true
bash submit_job.script > ../../run.log 2>&1
