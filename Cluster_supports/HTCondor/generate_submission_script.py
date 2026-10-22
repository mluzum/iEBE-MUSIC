#!/usr/bin/env python3
"""This script generates the job submission script for a generic HTCondor cluster
with Singularity support (non-OSG).

Singularity is invoked explicitly via `singularity exec` inside run_singularity.sh
rather than through HTCondor's +SingularityImage / SINGULARITY_CAN_USE_SIF mechanism,
so no special ClassAd is required on the worker nodes."""


import re
import sys
import os
from os import path, makedirs, getcwd
import argparse
import random

FILENAME = "singularity.submit"


def find_repo_root():
    """Find the iEBE-MUSIC repository root by looking for known markers."""
    current = path.abspath(".")
    while current != path.dirname(current):  # Stop at filesystem root
        if (path.exists(path.join(current, "README.md")) and
            path.exists(path.join(current, "config")) and
            path.exists(path.join(current, "Cluster_supports"))):
            return current
        current = path.dirname(current)
    return None


def detect_afterburner(param_file):
    """Return afterburner_type string read from the parameter file."""
    try:
        with open(param_file, 'r') as f:
            content = f.read()
        m = re.search(r"['\"]afterburner_type['\"]\s*:\s*['\"](\w+)['\"]", content)
        if m:
            return m.group(1)
    except Exception:
        pass
    return "UrQMD"


# ── Common random numbers: the campaign seed ────────────────────────────────
#
# Every event's freeze-out seed is np.random.default_rng([seed_add, event_id,
# iev]) in hydro_plus_UrQMD_driver.py, and the nucleon pool address depends only
# on the global event id. So an event is fully identified by
# (MASTER_SEED, seed_add, event_id, iev), and "event 37 means the same thing at
# every design point" holds if and only if seed_add is the same everywhere.
#
# This used to be random.SystemRandom().randint(0, 10000000) drawn once per
# submission, which gave each design point its own private set of events and
# silently destroyed the common random numbers the whole ensemble rests on: the
# 2026-10-22 corner runs used 9418965, 4477493 and 1182519. Fix it to a
# campaign constant instead, and let IBEM_SEED_ADD override it only for
# deliberately uncorrelated exploratory runs.
CAMPAIGN_SEED_ADD = 0


def campaign_seed_add():
    """Return the seed_add shared by every design point and every batch."""
    override = os.environ.get("IBEM_SEED_ADD")
    if override is None or override.strip() == "":
        return CAMPAIGN_SEED_ADD
    value = int(override)
    if value < 0:
        raise SystemExit("IBEM_SEED_ADD must be non-negative, got {}".format(value))
    return value


def detect_initial_state_type(param_file):
    """Return control_dict initial_state_type string from parameter file."""
    try:
        with open(param_file, 'r') as f:
            content = f.read()
        m = re.search(r"['\"]initial_state_type['\"]\s*:\s*['\"]([^'\"]+)['\"]", content)
        if m:
            return m.group(1)
    except Exception:
        pass
    return ""


def detect_seed_files(param_file):
    """Extract isobar_seed_file path from parameter file and resolve it.
    
    Tries to resolve relative paths in this order:
    1. Absolute paths (return as-is if exists)
    2. Relative to the parameter file location
    3. Relative to the repo root (iEBE-MUSIC/)
    4. Relative to current working directory
    """
    try:
        with open(param_file, 'r') as f:
            content = f.read()
        # Match isobar_seed_file = "..." or isobar_seed_file: "..."
        m = re.search(r"isobar_seed_file\s*[=:]\s*['\"]([^'\"]+)['\"]", content)
        if m:
            seed_path = m.group(1)
            
            # Handle absolute paths
            if path.isabs(seed_path):
                if path.exists(seed_path):
                    return seed_path
                return None
            
            # Handle relative paths - try multiple resolution strategies
            candidates = []
            
            # 1. Relative to param file location
            param_dir = path.dirname(path.abspath(param_file))
            candidates.append(path.join(param_dir, seed_path))
            
            # 2. Relative to repo root
            repo_root = find_repo_root()
            if repo_root:
                candidates.append(path.join(repo_root, seed_path))
            
            # 3. Relative to current working directory
            candidates.append(path.join(getcwd(), seed_path))
            
            # 4. In current dir under shared_seeds/ (legacy fallback)
            candidates.append(path.join(getcwd(), "shared_seeds", path.basename(seed_path)))
            
            # Return the first candidate that exists
            for candidate in candidates:
                if path.exists(candidate):
                    return candidate
    except Exception:
        pass
    return None


def declared_seed_source(param_file):
    """Return isobar_samples.seed_source from the parameter file, default 'file'.

    With 'philox' the nucleon rows are generated from (master_seed, pool
    address), so there is no seed file to ship to the worker at all.
    """
    try:
        with open(param_file, 'r') as f:
            content = f.read()
        m = re.search(r'seed_source', content)
        if not m:
            return "file"
        # The key sits in a nested dict whose "value" entry is on a later line,
        # so search a window after it rather than assuming one-line layout.
        window = content[m.start():m.start() + 800]
        v = re.search(r'value\W{1,4}["\']?(\w+)', window)
        return v.group(1).lower() if v else "file"
    except OSError:
        return "file"


def declared_seed_file(param_file):
    """Return the raw isobar_seed_file value, or None if not declared."""
    try:
        with open(param_file, 'r') as f:
            content = f.read()
        m = re.search(r"isobar_seed_file\s*[=:]\s*['\"]([^'\"]+)['\"]", content)
        return m.group(1) if m else None
    except OSError:
        return None


def require_seed_file(param_file):
    """Resolve the isobar seed, failing loudly if it is declared but unfindable.

    Without this the generator simply omits the seed from transfer_input_files
    and still emits a full queue, and every job then dies inside
    generate_jobs.py with "Specified isobar seed file not found". That is an
    expensive way to learn the generator was run from the wrong directory:
    note that the parameter file's relative path is resolved by
    generate_jobs.py against its *working* directory at run time, so the
    generator must be run where that same path resolves.
    """
    if declared_seed_source(param_file) == "philox":
        return None
    seed_file_path = detect_seed_files(param_file)
    if seed_file_path and path.exists(seed_file_path):
        return seed_file_path
    declared = declared_seed_file(param_file)
    if declared:
        raise SystemExit(
            "Error: parameter file declares isobar_seed_file = {!r} but it "
            "could not be resolved from {} (tried the parameter file's "
            "directory, the repo root, the current directory and "
            "<cwd>/shared_seeds). Run this generator from a directory where "
            "that relative path resolves -- e.g. the repository root, or a "
            "design-point folder holding shared_seeds/.".format(
                declared, path.abspath(param_file)))
    return None


# ── UrQMD mode ────────────────────────────────────────────────────────────────

def collect_head(para_dict_):
    """Event-range arithmetic, the EXIT trap, and nothing else.

    Emitted BEFORE generate_jobs.py runs: the range must be known to build the
    command line, and registering the trap first means a run that dies partway
    still transfers the events that completed. The part that actually executes
    submit_job.script lives in collect_tail(), which must come after
    generate_jobs.py -- it depends on the event folder that creates.
    """
    verbose = para_dict_.get("output_mode", "quiet") == "verbose"
    extra_collect = """
    for ev in "${SCRATCH_DIR}"/playground/event_*/EVENT_RESULTS_*; do
        if [ -d "${ev}" ]; then cp -r "${ev}" "${out_dir}/"; fi
    done
    for ev in "${SCRATCH_DIR}"/playground/event_*/TRENTo; do
        if [ -d "${ev}" ]; then cp -r "${ev}" "${out_dir}/"; fi
    done
""" if verbose else ""

    return '''
# Global event ids: job $(Process) owns events [Process*N, Process*N+N-1].
# Mirrors the OSG generator, so the same event numbering applies on both paths.
event_start_id=$(( processId * nHydroEvents ))
event_end_id=${event_start_id}
event_dir="${SCRATCH_DIR}/playground/event_${event_start_id}"

finalize_job_output() {
    local status=$?
    out_dir="${SCRATCH_DIR}/results_${processId}"
    mkdir -p "${out_dir}"

    # Flow observables and the TRENTo event summary, named with the global event
    # id, so they stay joinable across jobs.
    find "${SCRATCH_DIR}/playground" -type f \\
        \\( -name 'spvn_results_*.h5' -o -name 'trento_event_summary_*.txt' \\) \\
        -exec cp -f {} "${out_dir}/" \\; 2>/dev/null || true
    # The driver runs once per event, so each event writes its own
    # events_drawn.csv with a single row. Concatenate them into one table per
    # job, keeping the header from the first file only.
    drawn_csv="${out_dir}/events_drawn_${processId}.csv"
    rm -f "${drawn_csv}"
    for drawn in $(find "${SCRATCH_DIR}/playground" -type f -name 'events_drawn.csv'); do
        if [ ! -s "${drawn_csv}" ]; then
            cp -f "${drawn}" "${drawn_csv}"
        else
            tail -n +2 "${drawn}" >> "${drawn_csv}"
        fi
    done || true
''' + extra_collect + '''
    # Checkpoint archive. Seeds are excluded: they are large and already on input.
    tar -czf "${SCRATCH_DIR}/job_output_${processId}.tar.gz" \\
        -C "${SCRATCH_DIR}" playground \\
        --exclude='*/shared_seeds/*' --exclude='nucleon-seeds*.hdf' 2>/dev/null || true

    printf 'Collected %s file(s) for events %s..%s\\n' \\
        "$(find "${out_dir}" -type f | wc -l)" "${event_start_id}" \\
        "$(( event_start_id + nHydroEvents - 1 ))"
    return ${status}
}
trap finalize_job_output EXIT
'''


def collect_tail():
    """Run the generated event. Emitted AFTER generate_jobs.py.

    Note the `|| status=$?` idiom rather than `if ! cmd; then status=$?`.
    Under `if !`, `$?` inside the branch is the status of the negation (always
    0), so a failed simulation would exit 0 and HTCondor's
    `periodic_remove = (ExitCode == 73)` / `on_exit_hold` rules would never fire.
    The `||` form also keeps `set -e` from aborting before the status is read.
    """
    return '''
if [ ! -d "${event_dir}" ]; then
    echo "Missing event directory: ${event_dir}" >&2
    ls -la "${SCRATCH_DIR}/playground" >&2 || true
    exit 1
fi

cd "${event_dir}"
status=0
singularity exec --bind "${SCRATCH_DIR}:${SCRATCH_DIR}" "${SIF}" bash submit_job.script || status=$?
if [ "${status}" -ne 0 ]; then
    echo "submit_job.script failed with exit code ${status}" >&2
    exit "${status}"
fi
'''


def write_submission_script_urqmd(para_dict_):
    jobName = "iEBEMUSIC_{}".format(para_dict_["job_name"])
    random_seed = campaign_seed_add()
    sif = para_dict_["singularity_image_path"]
    script = open(FILENAME, "w")

    if para_dict_["bayesFlag"]:
        script.write("""universe = vanilla
executable = run_singularity.sh
arguments = {0} $(Process) {1} {2} {3} {4} {5}
""".format(para_dict_["param_file"], para_dict_["n_events_per_job"],
           para_dict_["n_threads"], random_seed, para_dict_["bayes_file"], sif))
    else:
        script.write("""universe = vanilla
executable = run_singularity.sh
arguments = {0} $(Process) {1} {2} {3} {4}
""".format(para_dict_["param_file"], para_dict_["n_events_per_job"],
           para_dict_["n_threads"], random_seed, sif))

    script.write("""
JobBatchName = {0}

should_transfer_files = YES
WhenToTransferOutput = ON_EXIT
""".format(jobName))

    # Build transfer_input_files list
    transfer_list = [para_dict_['param_file']]
    
    # Add bayes file if present
    if para_dict_['bayesFlag']:
        transfer_list.append(para_dict_['bayes_file'])
    
    # Detect and add seed files from parameter file
    seed_file_path = require_seed_file(para_dict_['param_file'])
    if seed_file_path:
        transfer_list.append(seed_file_path)
    
    # Add singularity image
    transfer_list.append(sif)
    
    script.write("\ntransfer_input_files = {}\n".format(", ".join(transfer_list)))

    # Outputs are collected by run_singularity.sh's EXIT trap into
    # results_$(Process)/ instead of being globbed here.
    #
    # The previous globs, playground/event_0/EVENT_RESULTS_$(Process)/..., could
    # never work for two independent reasons:
    #   * the event folder is named event_${processId * nHydroEvents}, which is
    #     not expressible as a $(Process) macro once more than one event per job
    #     is requested;
    #   * the driver names results after the *global* event id
    #     (EVENT_RESULTS_<event_id>), not after $(Process). Only Process 0 ever
    #     matched, so every other job silently transferred nothing.
    # The trap approach is what the OSG generator already does.
    initial_state_type = detect_initial_state_type(para_dict_["param_file"])
    transfer_output = "results_$(Process)"
    script.write("\ntransfer_checkpoint_files = job_output_$(Process).tar.gz\n")

    script.write("""
transfer_output_files = {3}

error = log/job.$(Cluster).$(Process).error
output = log/job.$(Cluster).$(Process).output
log = log/job.$(Cluster).$(Process).log

max_idle = 1000

# remove the failed jobs
periodic_remove = (ExitCode == 73)

periodic_release = ((HoldReasonCode == 13 || HoldReasonCode == 26) && (time() - EnteredCurrentStatus) > 1200 )

checkpoint_exit_code = 85

# Send the job to Held state on failure.
on_exit_hold = (ExitBySignal == True) || (ExitCode != 0 && ExitCode != 73)

request_cpus = {0:d}
request_memory = {1:d} GB
request_disk = 2 GB

# Avoid known problematic host where Singularity extraction fails
Requirements = (TARGET.Machine != "gpusphydro")

queue {2:d}""".format(para_dict_["n_threads"], para_dict_["memory_per_job"],
                      para_dict_["n_jobs"], transfer_output))
    script.close()


def write_job_running_script_urqmd(para_dict_):
    # sif is the last positional arg: $6 (no bayes) or $7 (bayes)
    sif_pos = 7 if para_dict_["bayesFlag"] else 6

    script = open("run_singularity.sh", "w")
    script.write("""#!/usr/bin/env bash
set -eo pipefail

parafile=$1
processId=$2
nHydroEvents=$3
nthreads=$4
nUrqmdSamples=__NURQMD_SAMPLES__
seed=$5

export PYTHONIOENCODING=utf-8
export PATH="${PATH}:/usr/lib64/openmpi/bin:/usr/local/gsl/2.5/x86_64/bin"
export LD_LIBRARY_PATH="${LD_LIBRARY_PATH}:/usr/local/lib:/usr/local/gsl/2.5/x86_64/lib64"

jobdir=$(pwd)
export JOBDIR="${jobdir}"
export TMPDIR="${jobdir}/tmp"
export XDG_DATA_HOME="${jobdir}/.local/share"
export XDG_CACHE_HOME="${jobdir}/.cache"
export TRENTO_CACHE="${jobdir}/.trento"
export SEED_DIR="${jobdir}/shared_seeds"

export SINGULARITYENV_TMPDIR="${TMPDIR}"
export SINGULARITYENV_XDG_DATA_HOME="${XDG_DATA_HOME}"
export SINGULARITYENV_XDG_CACHE_HOME="${XDG_CACHE_HOME}"
export SINGULARITYENV_TRENTO_CACHE="${TRENTO_CACHE}"

mkdir -p "${TMPDIR}"
mkdir -p "${XDG_DATA_HOME}"
mkdir -p "${XDG_CACHE_HOME}"
mkdir -p "${TRENTO_CACHE}"
mkdir -p "${XDG_DATA_HOME}/trento"
mkdir -p "${SEED_DIR}"

# HTCondor transfers seed files with relative paths; copy them into shared_seeds/
# if they're in a subdirectory (e.g., shared_seeds/nucleon-seeds.hdf)
for seed_hdf in *.hdf; do
    if [ -f "${jobdir}/${seed_hdf}" ] && [ ! -f "${SEED_DIR}/${seed_hdf}" ]; then
        cp "${jobdir}/${seed_hdf}" "${SEED_DIR}/${seed_hdf}"
    fi
done

# Also handle the case where seed files are already transferred into shared_seeds
if [ -d "${jobdir}/shared_seeds" ] && [ ! -d "${SEED_DIR}" ]; then
    cp -r "${jobdir}/shared_seeds" "${SEED_DIR}"
fi

printf "Start time: `/bin/date`\\n"
printf "Job is running on node: `/bin/hostname`\\n"
printf "system kernel: `uname -r`\\n"
printf "Job running as user: `/usr/bin/id`\\n"

""".replace("__NURQMD_SAMPLES__", str(para_dict_["n_urqmd_per_hydro"])))
    if para_dict_["bayesFlag"]:
        script.write("bayesFile=$6\n")

    script.write("SINGULARITY_IMAGE=${{{}}}\n\n".format(sif_pos))

    # HTCondor transfers the .sif as basename into the scratch dir.
    # Capture scratch dir and build absolute SIF path before any cd.
    script.write('SCRATCH_DIR="${PWD}"\n')
    script.write('SIF="${SCRATCH_DIR}/$(basename ${SINGULARITY_IMAGE})"\n\n')

    # Trap and event-range arithmetic are emitted BEFORE generate_jobs.py, so a
    # run that fails partway still transfers the events that did complete
    # instead of discarding them.
    script.write(collect_head(para_dict_))

    extra = " -b ${bayesFile}" if para_dict_["bayesFlag"] else ""
    # `|| status=$?` rather than `if ! cmd; then`: inside an `if !` branch `$?`
    # is the status of the negation (always 0), which would hide the failure
    # from HTCondor. The `||` form is also safe under `set -e`.
    script.write('''
status=0
singularity exec --bind "${SCRATCH_DIR}:${SCRATCH_DIR}" "${SIF}" \\
        /opt/iEBE-MUSIC/generate_jobs.py -w playground -c OSG \\
        -par ${parafile} -id ${processId} -n_th ${nthreads} \\
        -n_urqmd ${nUrqmdSamples} -n_hydro ${nHydroEvents} -seed ${seed} \\
        --event_start_id ${event_start_id} --event_end_id ${event_end_id} \\
        --nocopy --continueFlag''' + extra + ''' || status=$?
if [ "${status}" -ne 0 ]; then
    echo "generate_jobs.py failed with exit code ${status}" >&2
    exit "${status}"
fi
''')
    script.write(collect_tail())
    script.close()


# ── SMASH mode (TRENTo + isobar seeds) ───────────────────────────────────────

def write_submission_script_smash(para_dict_):
    jobName = "iEBEMUSIC_{}".format(para_dict_["job_name"])
    random_seed = campaign_seed_add()
    sif = para_dict_["singularity_image_path"]
    script = open(FILENAME, "w")

    # Argument order: param_file $(Process) n_events n_threads seed
    #                 [bayes_file] singularity_image
    #
    # There is no seed_file positional argument: the isobar seed is declared by
    # the parameter file's `isobar_seed_file` and transferred as an input file,
    # exactly as in the UrQMD branch. The previous code read a `seed_file` key
    # that no argparse option ever populated, and then passed it on to
    # generate_jobs.py as `--isobar_seed_file`, which that script does not accept.
    if para_dict_["bayesFlag"]:
        args_str = "{0} $(Process) {1} {2} {3} {4}".format(
            para_dict_["param_file"], para_dict_["n_events_per_job"],
            para_dict_["n_threads"], random_seed, para_dict_["bayes_file"])
    else:
        args_str = "{0} $(Process) {1} {2} {3}".format(
            para_dict_["param_file"], para_dict_["n_events_per_job"],
            para_dict_["n_threads"], random_seed)
    # singularity image is always last
    args_str += " {}".format(sif)

    script.write("""universe = vanilla
executable = run_singularity.sh
arguments = {}
""".format(args_str))

    script.write("""
JobBatchName = {0}

should_transfer_files = YES
WhenToTransferOutput = ON_EXIT
""".format(jobName))

    # The .sif is included so HTCondor copies it to the worker scratch dir.
    # In run_singularity.sh we reference it via $(basename ...).
    input_files = [para_dict_['param_file']]
    if para_dict_['bayesFlag']:
        input_files.append(para_dict_['bayes_file'])
    seed_file_path = require_seed_file(para_dict_['param_file'])
    if seed_file_path:
        input_files.append(seed_file_path)
    input_files.append(sif)
    script.write("\ntransfer_input_files = {}\n".format(", ".join(input_files)))

    initial_state_type = detect_initial_state_type(para_dict_["param_file"])

    # Same collected-directory scheme as the UrQMD branch; the old globs here
    # referenced EVENT_RESULTS_$(Process), which never matches because the driver
    # names results after the global event id.
    transfer_output = "results_$(Process)"
    script.write("\ntransfer_checkpoint_files = job_output_$(Process).tar.gz\n")

    script.write("""
transfer_output_files = {3}

error = log/job.$(Cluster).$(Process).error
output = log/job.$(Cluster).$(Process).output
log = log/job.$(Cluster).$(Process).log

max_idle = 1000

# remove the failed jobs
periodic_remove = (ExitCode == 73)

periodic_release = ((HoldReasonCode == 13 || HoldReasonCode == 26) && (time() - EnteredCurrentStatus) > 1200 )

checkpoint_exit_code = 85

# Send the job to Held state on failure.
on_exit_hold = (ExitBySignal == True) || (ExitCode != 0 && ExitCode != 73)

request_cpus = {0:d}
request_memory = {1:d} GB
request_disk = 2 GB

queue {2:d}""".format(para_dict_["n_threads"], para_dict_["memory_per_job"],
                      para_dict_["n_jobs"], transfer_output))
    script.close()


def write_job_running_script_smash(para_dict_):
    # singularity image is the last positional arg: $6 (no bayes) or $7 (bayes)
    sif_pos = 7 if para_dict_["bayesFlag"] else 6

    script = open("run_singularity.sh", "w")
    script.write("""#!/usr/bin/env bash
set -eo pipefail

parafile=$1
processId=$2
nHydroEvents=$3
nthreads=$4
nUrqmdSamples=__NURQMD_SAMPLES__
seed=$5

export PYTHONIOENCODING=utf-8
export PATH="${PATH}:/usr/lib64/openmpi/bin:/usr/local/gsl/2.5/x86_64/bin"
export LD_LIBRARY_PATH="${LD_LIBRARY_PATH}:/usr/local/lib:/usr/local/gsl/2.5/x86_64/lib64"

jobdir=$(pwd)
export JOBDIR="${jobdir}"
export TMPDIR="${jobdir}/tmp"
export HOME="${jobdir}"
export SEED_DIR="${jobdir}/shared_seeds"
export XDG_DATA_HOME="${jobdir}/.local/share"
export XDG_CACHE_HOME="${jobdir}/.cache"
export TRENTO_CACHE="${jobdir}/.trento"

export SINGULARITYENV_HOME="${HOME}"
export SINGULARITYENV_TMPDIR="${TMPDIR}"
export SINGULARITYENV_XDG_DATA_HOME="${XDG_DATA_HOME}"
export SINGULARITYENV_XDG_CACHE_HOME="${XDG_CACHE_HOME}"
export SINGULARITYENV_TRENTO_CACHE="${TRENTO_CACHE}"

mkdir -p "${TMPDIR}"
mkdir -p "${XDG_DATA_HOME}"
mkdir -p "${XDG_CACHE_HOME}"
mkdir -p "${TRENTO_CACHE}"
mkdir -p "${XDG_DATA_HOME}/trento"
mkdir -p "${SEED_DIR}"

# generate_jobs.py resolves `isobar_seed_file` (e.g. shared_seeds/nucleon-seeds.hdf)
# with os.path.abspath against its working directory, so the transferred seed has
# to sit under shared_seeds/ for the path in the parameter file to resolve.
for seed_hdf in *.hdf; do
    if [ -f "${jobdir}/${seed_hdf}" ] && [ ! -f "${SEED_DIR}/${seed_hdf}" ]; then
        cp "${jobdir}/${seed_hdf}" "${SEED_DIR}/${seed_hdf}"
    fi
done

touch "${TRENTO_CACHE}/write_test.txt" || { echo "Cannot write to TRENTO_CACHE"; exit 101; }
touch "${XDG_DATA_HOME}/write_test.txt" || { echo "Cannot write to XDG_DATA_HOME"; exit 102; }
touch "${TMPDIR}/write_test.txt" || { echo "Cannot write to TMPDIR"; exit 103; }

printf "Start time: `/bin/date`\\n"
printf "Job is running on node: `/bin/hostname`\\n"
printf "system kernel: `uname -r`\\n"
printf "Job running as user: `/usr/bin/id`\\n"

echo "==== Environment debug ===="
echo "PWD=${PWD}"
echo "HOME=${HOME}"
echo "TMPDIR=${TMPDIR}"
echo "XDG_DATA_HOME=${XDG_DATA_HOME}"
echo "XDG_CACHE_HOME=${XDG_CACHE_HOME}"
echo "TRENTO_CACHE=${TRENTO_CACHE}"
echo "==========================="

""".replace("__NURQMD_SAMPLES__", str(para_dict_["n_urqmd_per_hydro"])))

    if para_dict_["bayesFlag"]:
        script.write("bayesFile=$6\n")

    script.write("SINGULARITY_IMAGE=${{{}}}\n".format(sif_pos))
    # HTCondor transfers the .sif as basename into the scratch dir.
    # Capture scratch dir and build absolute SIF path before any cd.
    script.write('SCRATCH_DIR="${PWD}"\n')
    script.write('SIF="${SCRATCH_DIR}/$(basename ${SINGULARITY_IMAGE})"\n\n')

    # Trap and event-range arithmetic are emitted BEFORE generate_jobs.py, so a
    # run that fails partway still transfers the events that did complete
    # instead of discarding them.
    script.write(collect_head(para_dict_))

    extra = " -b ${bayesFile}" if para_dict_["bayesFlag"] else ""
    # `|| status=$?` rather than `if ! cmd; then`: inside an `if !` branch `$?`
    # is the status of the negation (always 0), which would hide the failure
    # from HTCondor. The `||` form is also safe under `set -e`.
    script.write('''
status=0
singularity exec --bind "${SCRATCH_DIR}:${SCRATCH_DIR}" "${SIF}" \\
        /opt/iEBE-MUSIC/generate_jobs.py -w playground -c OSG \\
        -par ${parafile} -id ${processId} -n_th ${nthreads} \\
        -n_urqmd ${nUrqmdSamples} -n_hydro ${nHydroEvents} -seed ${seed} \\
        --event_start_id ${event_start_id} --event_end_id ${event_end_id} \\
        --nocopy --continueFlag''' + extra + ''' || status=$?
if [ "${status}" -ne 0 ]; then
    echo "generate_jobs.py failed with exit code ${status}" >&2
    exit "${status}"
fi
''')
    script.write(collect_tail())
    script.close()


# ── Entry point ───────────────────────────────────────────────────────────────

def main(para_dict_):
    afterburner = detect_afterburner(para_dict_["param_file"])
    print("Detected afterburner: {}".format(afterburner))

    if afterburner == "SMASH":
        write_submission_script_smash(para_dict_)
        write_job_running_script_smash(para_dict_)
    else:
        write_submission_script_urqmd(para_dict_)
        write_job_running_script_urqmd(para_dict_)

    logFolderName = "log"
    if not path.exists(logFolderName):
        makedirs(logFolderName)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='HTCondor + Singularity submission script for iEBE-MUSIC',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument('-n', '--n_jobs', metavar='', type=int, default=1,
                        help='number of jobs')
    parser.add_argument('-nev', '--n_events_per_job', metavar='', type=int,
                        default=1, help='number of events per job')
    parser.add_argument('-nth', '--n_threads', metavar='', type=int, default=1,
                        help='number of threads per job')
    parser.add_argument('-nurqmd', '--n_urqmd_per_hydro', metavar='', type=int,
                        default=None,
                        help='number of UrQMD samples per hydro event')
    parser.add_argument('-singularity', '--singularity_image_path', metavar='',
                        type=str, default="",
                        help='absolute path to the .sif Singularity image '
                             '(must be accessible on all worker nodes)')
    parser.add_argument('-param', '--param_file', metavar='', type=str,
                        default="", help='parameter file')
    parser.add_argument('-jobid', '--job_name', metavar='', type=str,
                        default="test", help='job name')
    parser.add_argument('-bayes', '--bayes_file', metavar='', type=str,
                        default="", help='bayes file')
    parser.add_argument('-mem', '--memory_per_job', metavar='', type=int,
                        default=4, help='memory per job (GB)')
    parser.add_argument('-output_mode', '--output_mode', metavar='', type=str,
                        default='quiet', choices=['quiet', 'verbose'],
                        help='output transfer mode: quiet=spvn only, verbose=full EVENT_RESULTS')

    if len(sys.argv) < 2:
        parser.print_help()
        exit(0)

    para_dict = vars(parser.parse_args())
    if para_dict["n_urqmd_per_hydro"] is None:
        para_dict["n_urqmd_per_hydro"] = para_dict["n_threads"]
    para_dict["bayesFlag"] = para_dict["bayes_file"] != ""

    main(para_dict)