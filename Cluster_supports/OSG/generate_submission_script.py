#!/usr/bin/env python3
"""This script generates the job submission script on OSG"""


import re
import sys
import shutil
from os import path, makedirs, getcwd, chmod
import argparse
import random

FILENAME = "singularity.submit"


def find_repo_root():
    """Find the iEBE-MUSIC repository root by looking for known markers."""
    current = path.abspath(path.join(path.dirname(__file__), "..", ".."))
    while current != path.dirname(current):
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


def detect_seed_file(param_file):
    """Return the isobar seed file referenced by the parameter file, if any."""
    try:
        with open(param_file, 'r') as f:
            content = f.read()
        m = re.search(r"isobar_seed_file\s*[=:]\s*['\"]([^'\"]+)['\"]", content)
        if m:
            seed_path = m.group(1)
            if path.isabs(seed_path):
                return seed_path if path.exists(seed_path) else None

            candidates = []
            param_dir = path.dirname(path.abspath(param_file))
            candidates.append(path.join(param_dir, seed_path))
            repo_root = find_repo_root()
            if repo_root:
                candidates.append(path.join(repo_root, seed_path))
            candidates.append(path.join(getcwd(), seed_path))
            candidates.append(path.join(getcwd(), "shared_seeds", path.basename(seed_path)))

            for candidate in candidates:
                if path.exists(candidate):
                    return candidate
    except Exception:
        pass
    return None


def normalize_singularity_image_path(image_path):
    """Expand environment variables and return a valid OSDF image URL."""
    expanded_path = path.expandvars(image_path)
    if "$" in expanded_path:
        raise ValueError(
            "Unexpanded variable in singularity image path: {}".format(
                image_path))
    if expanded_path.startswith("osdf://"):
        return expanded_path
    return "osdf://{}".format(expanded_path)


def build_transfer_output_tarball_name():
    """Return the single per-job tarball name transferred from each OSG worker.

    Each HTCondor job owns a specific global event range. The only reliable way to
    transfer files for that range is to archive the generated outputs into one
    tarball that is unique to the process id, rather than trying to list every
    other process's files in a static transfer_output_files entry.
    """
    return "job_output_$(Process).tar.gz"


# ── UrQMD mode (original logic) ──────────────────────────────────────────────

def write_submission_script_urqmd(para_dict_):
    jobName = "iEBEMUSIC_{}".format(para_dict_["job_name"])
    random_seed = random.SystemRandom().randint(0, 10000000)
    seed_file = None
    if declared_seed_source(para_dict_["param_file"]) != "philox":
        seed_file = detect_seed_file(para_dict_["param_file"])
    script = open(FILENAME, "w")
    singularity_image_url = normalize_singularity_image_path(
        para_dict_["singularity_image_path"])
    home_log_dir = path.join(path.expanduser("~"), "log")
    makedirs(home_log_dir, exist_ok=True)
    transfer_seed_file = None
    if seed_file:
        transfer_seed_file = path.basename(seed_file)
        local_seed_file = path.join(getcwd(), transfer_seed_file)
        if path.abspath(seed_file) != path.abspath(local_seed_file):
            shutil.copy2(seed_file, local_seed_file)
        seed_file = local_seed_file

    param_basename = path.basename(para_dict_["param_file"])
    if para_dict_["bayesFlag"]:
        args = "{0} $(Process) {1} {2} {3} {4}".format(
            param_basename, para_dict_["n_events_per_job"],
            para_dict_["n_threads"], random_seed, para_dict_["bayes_file"])
        if seed_file:
            args += " {}".format(path.basename(seed_file))
        script.write("""universe = vanilla
executable = run_singularity.sh
arguments = {0}
""".format(args))
    else:
        args = "{0} $(Process) {1} {2} {3}".format(
            param_basename, para_dict_["n_events_per_job"],
            para_dict_["n_threads"], random_seed)
        if seed_file:
            args += " {}".format(path.basename(seed_file))
        script.write("""universe = vanilla
executable = run_singularity.sh
arguments = {0}
""".format(args))

    script.write("""
JobBatchName = {0}

should_transfer_files = YES
WhenToTransferOutput = ON_EXIT

container_image = "{1}"
+SingularityImage = "{1}"
Requirements = (TARGET.HasSingularity || SINGULARITY_CAN_USE_SIF) && StringListIMember("stash", HasFileTransferPluginMethods)
""".format(jobName, singularity_image_url))

    input_files = [para_dict_['param_file']]
    if para_dict_['bayesFlag']:
        input_files.append(para_dict_['bayes_file'])
    if seed_file:
        input_files.append(transfer_seed_file)
    script.write("\ntransfer_input_files = {}\n".format(
        ", ".join(input_files)))

    quiet_mode = para_dict_.get("output_mode", "quiet") == "quiet"
    if not quiet_mode:
        script.write(
            "transfer_checkpoint_files = job_output_$(Process).tar.gz\n")

    if quiet_mode:
        transfer_output = "spvn_results"
    else:
        transfer_output = build_transfer_output_tarball_name()

    script.write("""
transfer_output_files = {3}

error = {4}/job.$(Cluster).$(Process).error
output = {4}/job.$(Cluster).$(Process).output
log = {4}/job.$(Cluster).$(Process).log

#+JobDurationCategory = "Long"
max_idle = 1000

# remove the failed jobs
periodic_remove = (ExitCode == 73)

# auto release hold jobs if they are caused by data transfer issues on OSG
periodic_release = ((HoldReasonCode == 13 || HoldReasonCode == 26) && (time() - EnteredCurrentStatus) > 1200 )

checkpoint_exit_code = 85

# Send the job to Held state on failure.
on_exit_hold = (ExitBySignal == True) || (ExitCode != 0 && ExitCode != 73)

# The below are good base requirements for first testing jobs on OSG,
# if you don't have a good idea of memory and disk usage.
request_cpus = {0:d}
request_memory = {1:d} GB
request_disk = {5:d} GB

# Queue one job with the above specifications.
queue {2:d}""".format(para_dict_["n_threads"], para_dict_["memory_per_job"],
                      para_dict_["n_jobs"], transfer_output, home_log_dir,
                      para_dict_["disk_per_job"]))
    script.close()


def write_job_running_script_urqmd(para_dict_):
    seed_file = None
    if declared_seed_source(para_dict_["param_file"]) != "philox":
        seed_file = detect_seed_file(para_dict_["param_file"])
    script = open("run_singularity.sh", "w")
    script.write("""#!/usr/bin/env bash
set -e

parafile=$1
processId=$2
nHydroEvents=$3
nthreads=$4
nUrqmdSamples=__NURQMD_SAMPLES__
seed=$5
output_mode="__OUTPUT_MODE__"

export PYTHONIOENCODING=utf-8
export PATH="${PATH}:/usr/lib64/openmpi/bin:/usr/local/gsl/2.5/x86_64/bin"
export LD_LIBRARY_PATH="${LD_LIBRARY_PATH}:/usr/local/lib:/usr/local/gsl/2.5/x86_64/lib64"

SCRATCH_DIR="${PWD}"
cd "${SCRATCH_DIR}"
export HOME="${SCRATCH_DIR}"
export XDG_DATA_HOME="${HOME}/.local/share"
export XDG_CACHE_HOME="${HOME}/.cache"
export TRENTO_CACHE="${HOME}/.trento"
mkdir -p "${XDG_DATA_HOME}"
mkdir -p "${XDG_CACHE_HOME}"
mkdir -p "${TRENTO_CACHE}"
mkdir -p "${XDG_DATA_HOME}/trento"
export HOME="${SCRATCH_DIR}"
export XDG_DATA_HOME="${HOME}/.local/share"
export XDG_CACHE_HOME="${HOME}/.cache"
export TRENTO_CACHE="${HOME}/.trento"
mkdir -p "${XDG_DATA_HOME}"
mkdir -p "${XDG_CACHE_HOME}"
mkdir -p "${TRENTO_CACHE}"
mkdir -p "${XDG_DATA_HOME}/trento"

if [ ! -f "$(basename "${parafile}")" ] && [ -f "${parafile}" ]; then
    cp "${parafile}" "$(basename "${parafile}")"
fi
if [ ! -f "$(basename "${parafile}")" ]; then
    echo "Missing parameter file in scratch dir: ${parafile}" >&2
    ls -la "${SCRATCH_DIR}" >&2 || true
    exit 1
fi
parafile="$(basename "${parafile}")"

printf "Start time: `/bin/date`\\n"
printf "Job is running on node: `/bin/hostname`\\n"
printf "system kernel: `uname -r`\\n"
printf "Job running as user: `/usr/bin/id`\\n"
printf "Working directory: ${SCRATCH_DIR}\\n"

""".replace("__NURQMD_SAMPLES__", str(para_dict_["n_urqmd_per_hydro"])
              ).replace("__OUTPUT_MODE__", para_dict_.get("output_mode", "quiet")))
    if seed_file:
        script.write("""
seedfile="${6:-}"
seed_base=$(basename "${seedfile:-${parafile}}")
mkdir -p shared_seeds
seed_source=""
if [ -n "${seedfile}" ] && [ -f "${seedfile}" ]; then
    seed_source="${seedfile}"
else
    seed_source=$(find "${SCRATCH_DIR}" -name "${seed_base}" -type f -print -quit)
fi
echo "seedfile arg: ${seedfile:-<unset>}"
echo "seed_base: ${seed_base}"
echo "seed_source: ${seed_source:-<unset>}"
if [ -z "${seed_source}" ] || [ ! -f "${seed_source}" ]; then
    echo "Seed file missing from sandbox after transfer: ${seedfile:-<unset>}" >&2
    ls -la "${SCRATCH_DIR}" >&2 || true
    ls -la shared_seeds >&2 || true
    exit 1
fi
if [ ! -f "shared_seeds/${seed_base}" ]; then
    cp "${seed_source}" "shared_seeds/${seed_base}"
fi
echo "shared_seeds contents:"
ls -la shared_seeds
echo "rewritten parameter file seed line:"
grep -n "isobar_seed_file" "${parafile}" || true
python3 - "${parafile}" "shared_seeds/${seed_base}" <<'PY'
from pathlib import Path
import sys
param_path = Path(sys.argv[1])
seed_name = sys.argv[2]
text = param_path.read_text()
updated = False
for marker in ["isobar_seed_file = ", "isobar_seed_file: ", "isobar_seed_file= "]:
    idx = text.find(marker)
    if idx < 0:
        continue
    start = idx + len(marker)
    end = text.find("\\n", start)
    if end < 0:
        end = len(text)
    quote = text[start] if start < len(text) and text[start] in ('"', "'") else '"'
    prefix = text[:start]
    suffix = text[end:]
    text = prefix + quote + seed_name + quote + suffix
    updated = True
    break
if not updated:
    raise SystemExit("isobar_seed_file not found in parameter file")
if not Path(seed_name).exists():
    raise SystemExit(f"Seed file not found after copy: {seed_name}")
param_path.write_text(text)
PY
""")

    if para_dict_["bayesFlag"]:
        script.write("""bayesFile=$6
seedfile="${7:-}"
seed_name=$(basename "${seedfile:-}")

if [ -n "${seed_name}" ] && [ -f "${seed_name}" ] && [ ! -f "shared_seeds/${seed_name}" ]; then
    mkdir -p shared_seeds
    cp "${seed_name}" "shared_seeds/${seed_name}"
fi
if [ -n "${seed_name}" ] && [ ! -f "shared_seeds/${seed_name}" ]; then
    echo "Seed file missing from sandbox after transfer: ${seedfile:-<unset>}" >&2
    exit 1
fi

event_start_id=$(( processId * nHydroEvents ))
event_end_id=${event_start_id}

/opt/iEBE-MUSIC/generate_jobs.py -w playground -c OSG -par ${parafile} -id ${processId} -n_th ${nthreads} -n_urqmd ${nUrqmdSamples} -n_hydro ${nHydroEvents} -seed ${seed} --event_start_id ${event_start_id} --event_end_id ${event_end_id} --nocopy --continueFlag -b ${bayesFile}
status=$?
if [ $status -ne 0 ]; then
    echo "generate_jobs.py failed with exit code ${status}" >&2
    exit $status
fi
""")
    else:
        script.write("""
seedfile="${6:-}"
seed_name=$(basename "${seedfile:-}")
if [ -n "${seed_name}" ] && [ -f "${seed_name}" ] && [ ! -f "shared_seeds/${seed_name}" ]; then
    mkdir -p shared_seeds
    cp "${seed_name}" "shared_seeds/${seed_name}"
fi
if [ -n "${seed_name}" ] && [ ! -f "shared_seeds/${seed_name}" ]; then
    echo "Seed file missing from sandbox after transfer: ${seedfile:-<unset>}" >&2
    exit 1
fi

event_start_id=$(( processId * nHydroEvents ))
event_end_id=${event_start_id}

/opt/iEBE-MUSIC/generate_jobs.py -w playground -c OSG -par ${parafile} -id ${processId} -n_th ${nthreads} -n_urqmd ${nUrqmdSamples} -n_hydro ${nHydroEvents} -seed ${seed} --event_start_id ${event_start_id} --event_end_id ${event_end_id} --nocopy --continueFlag
status=$?
if [ $status -ne 0 ]; then
    echo "generate_jobs.py failed with exit code ${status}" >&2
    exit $status
fi
""")

    script.write("""
event_start_id=${event_start_id:-0}
event_end_id=${event_end_id:-$(( event_start_id + nHydroEvents - 1 ))}

job_event_dirs=()
for (( ev = event_start_id; ev <= event_end_id; ev++ )); do
    candidate="${SCRATCH_DIR}/playground/event_${ev}"
    if [ -d "${candidate}" ] && [ -f "${candidate}/submit_job.script" ]; then
        job_event_dirs+=("${candidate}")
    fi
done

if [ ${#job_event_dirs[@]} -eq 0 ]; then
    echo "Missing event directories for event range ${event_start_id}..${event_end_id}" >&2
    ls -la "${SCRATCH_DIR}/playground" >&2 || true
    exit 1
fi

cleanup_job_scratch() {
    find "${SCRATCH_DIR}" -maxdepth 1 -type f \( -name 'nucleon-seeds_*.hdf' -o -name 'nucleon-seeds.hdf' \) -exec rm -f {} + || true
    rm -f "${SCRATCH_DIR}/nucleon-seeds_*.hdf" "${SCRATCH_DIR}/nucleon-seeds.hdf" || true
}

finalize_job_output() {
    cleanup_job_scratch

    quiet_out_dir="${SCRATCH_DIR}/spvn_results"
    mkdir -p "${quiet_out_dir}"
    find "${SCRATCH_DIR}/playground" -type f \( \
        -name 'spvn_results_*.h5' -o \
        -name 'trento_event_summary_*.txt' -o \
        -name 'grid_extent_*.csv' -o \
        -name 'target_nucleus.hdf' \
    \) -exec cp -f {} "${quiet_out_dir}/" \; || true

    if [ "${output_mode}" != "quiet" ]; then
        job_output_tar="${SCRATCH_DIR}/job_output_${processId}.tar.gz"
        job_paths=()
        for (( ev = event_start_id; ev <= event_end_id; ev++ )); do
            if [ -d "${SCRATCH_DIR}/playground/event_${ev}" ]; then
                job_paths+=("playground/event_${ev}")
            fi
        done

        if [ ${#job_paths[@]} -gt 0 ]; then
            tar -czf "${job_output_tar}" -C "${SCRATCH_DIR}" "${job_paths[@]}" || true
        else
            placeholder=".job_output_${processId}_empty"
            : > "${SCRATCH_DIR}/${placeholder}"
            tar -czf "${job_output_tar}" -C "${SCRATCH_DIR}" "${placeholder}" || true
            rm -f "${SCRATCH_DIR}/${placeholder}" || true
        fi
        ls -lh "${job_output_tar}" || true
    fi
}

trap finalize_job_output EXIT

event_fail=0
for event_dir in "${job_event_dirs[@]}"; do
    cd "${event_dir}"
    bash submit_job.script
    status=$?
    if [ $status -ne 0 ]; then
        echo "submit_job.script failed with exit code ${status} in ${event_dir}" >&2
        event_fail=${status}
    fi
done

if [ ${event_fail} -ne 0 ]; then
    exit ${event_fail}
fi
""")
    script.close()
    chmod("run_singularity.sh", 0o755)


# ── SMASH mode (TRENTo + isobar seeds) ───────────────────────────────────────

def write_submission_script_smash(para_dict_):
    jobName = "iEBEMUSIC_{}".format(para_dict_["job_name"])
    random_seed = random.SystemRandom().randint(0, 10000000)
    imagePathHeader = "osdf://"
    seed_file = None
    if declared_seed_source(para_dict_["param_file"]) != "philox":
        seed_file = detect_seed_file(para_dict_["param_file"])
    script = open(FILENAME, "w")
    home_log_dir = path.join(path.expanduser("~"), "log")
    makedirs(home_log_dir, exist_ok=True)

    # Build arguments: param_file $(Process) n_events n_threads seed [bayes_file] [seed_file]
    if para_dict_["bayesFlag"]:
        args_str = "{0} $(Process) {1} {2} {3} {4}".format(
            para_dict_["param_file"], para_dict_["n_events_per_job"],
            para_dict_["n_threads"], random_seed, para_dict_["bayes_file"])
    else:
        args_str = "{0} $(Process) {1} {2} {3}".format(
            para_dict_["param_file"], para_dict_["n_events_per_job"],
            para_dict_["n_threads"], random_seed)
    if seed_file:
        args_str += " {}".format(seed_file)

    script.write("""universe = vanilla
executable = run_singularity.sh
arguments = {}
""".format(args_str))

    script.write("""
JobBatchName = {0}

should_transfer_files = YES
WhenToTransferOutput = ON_EXIT

container_image = "{1}"
+SingularityImage = "{1}"
Requirements = (TARGET.HasSingularity || SINGULARITY_CAN_USE_SIF) && StringListIMember("stash", HasFileTransferPluginMethods)
""".format(jobName, imagePathHeader + para_dict_["singularity_image_path"]))

    input_files = [para_dict_['param_file']]
    if para_dict_['bayesFlag']:
        input_files.append(para_dict_['bayes_file'])
    if seed_file:
        input_files.append(seed_file)
    script.write("\ntransfer_input_files = {}\n".format(", ".join(input_files)))

    #script.write(
    #    "transfer_checkpoint_files = job_output_$(Process).tar.gz\n")

    transfer_output = build_transfer_output_tarball_name()

    script.write("""
transfer_output_files = {3}

error = {4}/job.$(Cluster).$(Process).error
output = {4}/job.$(Cluster).$(Process).output
log = {4}/job.$(Cluster).$(Process).log

#+JobDurationCategory = "Long"
max_idle = 1000

# remove the failed jobs
periodic_remove = (ExitCode == 73)

# auto release hold jobs if they are caused by data transfer issues on OSG
periodic_release = ((HoldReasonCode == 13 || HoldReasonCode == 26) && (time() - EnteredCurrentStatus) > 1200 )

checkpoint_exit_code = 85

# Send the job to Held state on failure.
on_exit_hold = (ExitBySignal == True) || (ExitCode != 0 && ExitCode != 73)

# The below are good base requirements for first testing jobs on OSG,
# if you don't have a good idea of memory and disk usage.
request_cpus = {0:d}
request_memory = {1:d} GB
request_disk = {5:d} GB

# Queue one job with the above specifications.
queue {2:d}""".format(para_dict_["n_threads"], para_dict_["memory_per_job"],
                      para_dict_["n_jobs"], transfer_output, home_log_dir,
                      para_dict_["disk_per_job"]))
    script.close()


def write_job_running_script_smash(para_dict_):
    seed_file = None
    if declared_seed_source(para_dict_["param_file"]) != "philox":
        seed_file = detect_seed_file(para_dict_["param_file"])
    # seedfile position: after bayesFile (if present), otherwise after seed ($5)
    seedfile_pos = 7 if para_dict_["bayesFlag"] else 6

    script = open("run_singularity.sh", "w")
    script.write("""#!/usr/bin/env bash
set -e

parafile=$1
processId=$2
nHydroEvents=$3
nthreads=$4
nUrqmdSamples=__NURQMD_SAMPLES__
seed=$5

export PYTHONIOENCODING=utf-8
export PATH="${PATH}:/usr/lib64/openmpi/bin:/usr/local/gsl/2.5/x86_64/bin"
export LD_LIBRARY_PATH="${LD_LIBRARY_PATH}:/usr/local/lib:/usr/local/gsl/2.5/x86_64/lib64"

SCRATCH_DIR="${PWD}"
cd "${SCRATCH_DIR}"

jobdir=$(pwd)
export JOBDIR="${jobdir}"
export TMPDIR="${jobdir}/tmp"
export HOME="${jobdir}"
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

touch "${TRENTO_CACHE}/write_test.txt" || { echo "Cannot write to TRENTO_CACHE"; exit 101; }
touch "${XDG_DATA_HOME}/write_test.txt" || { echo "Cannot write to XDG_DATA_HOME"; exit 102; }
touch "${TMPDIR}/write_test.txt" || { echo "Cannot write to TMPDIR"; exit 103; }

printf "Start time: `/bin/date`\\n"
printf "Job is running on node: `/bin/hostname`\\n"
printf "system kernel: `uname -r`\\n"
printf "Job running as user: `/usr/bin/id`\\n"
printf "Working directory: ${SCRATCH_DIR}\\n"

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

    if seed_file:
        script.write("seedfile=${{{}}}\n".format(seedfile_pos))
        script.write("mkdir -p shared_seeds\n")
        script.write("seed_base=$(basename \"${seedfile}\")\n")
        script.write("if [ -f \"${seed_base}\" ] && [ ! -f \"shared_seeds/${seed_base}\" ]; then cp \"${seed_base}\" \"shared_seeds/${seed_base}\"; fi\n")
        script.write("if [ -f \"${seedfile}\" ] && [ ! -f \"shared_seeds/${seed_base}\" ]; then cp \"${seedfile}\" \"shared_seeds/${seed_base}\"; fi\n")
        script.write("SEED_ARG=--isobar_seed_file\n")
    else:
        script.write("SEED_ARG=\"\"\n")

    if para_dict_["bayesFlag"]:
        script.write("""
/opt/iEBE-MUSIC/generate_jobs.py -w playground -c OSG -par ${parafile} -id ${processId} -n_th ${nthreads} -n_urqmd ${nUrqmdSamples} -n_hydro ${nHydroEvents} -seed ${seed} -b ${bayesFile} --nocopy --continueFlag
status=$?
if [ $status -ne 0 ]; then
    echo "generate_jobs.py failed with exit code ${status}" >&2
    exit $status
fi
""")
    else:
        script.write("""
/opt/iEBE-MUSIC/generate_jobs.py -w playground -c OSG -par ${parafile} -id ${processId} -n_th ${nthreads} -n_urqmd ${nUrqmdSamples} -n_hydro ${nHydroEvents} -seed ${seed} --nocopy --continueFlag
status=$?
if [ $status -ne 0 ]; then
    echo "generate_jobs.py failed with exit code ${status}" >&2
    exit $status
fi
""")

    script.write("""
if [ ! -d "${SCRATCH_DIR}/playground/event_0" ]; then
    echo "Missing expected job directory: ${SCRATCH_DIR}/playground/event_0" >&2
    ls -la "${SCRATCH_DIR}" >&2 || true
    ls -la "${SCRATCH_DIR}/playground" >&2 || true
    exit 1
fi

cd "${SCRATCH_DIR}/playground/event_0"
if [ ! -f "submit_job.script" ]; then
    echo "Missing submit_job.script in ${SCRATCH_DIR}/playground/event_0" >&2
    ls -la >&2
    exit 1
fi

archive_event_results() {
    if [ -d "EVENT_RESULTS_${processId}" ] && [ ! -f "EVENT_RESULTS_${processId}.tar.gz" ]; then
        tar -czf EVENT_RESULTS_${processId}.tar.gz EVENT_RESULTS_${processId}
    elif [ ! -f "EVENT_RESULTS_${processId}.tar.gz" ]; then
        tar -czf EVENT_RESULTS_${processId}.tar.gz --exclude="EVENT_RESULTS_${processId}.tar.gz" .
    fi
}

trap archive_event_results EXIT

bash submit_job.script
status=$?
if [ $status -ne 0 ]; then
    echo "submit_job.script failed with exit code ${status}" >&2
    exit $status
fi
status=$?
if [ $status -ne 0 ]; then
    exit $status
fi
""")
    script.close()
    chmod("run_singularity.sh", 0o755)


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
        description='Welcome to OSG script for the iEBE-MUSIC framework',
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
                        type=str, default="", help='singularity image path')
    parser.add_argument('-param', '--param_file', metavar='', type=str,
                        default="", help='parameter file')
    parser.add_argument('-jobid', '--job_name', metavar='', type=str,
                        default="test", help='job name')
    parser.add_argument('-bayes', '--bayes_file', metavar='', type=str,
                        default="", help='bayes file')
    parser.add_argument('-mem', '--memory_per_job', metavar='GB', type=int,
                        default=1, help='memory per job IN GIGABYTES (not MB). '
                        'Measured peak for a 19-event 76Ge batch on one core was '
                        '212 MB, so the old 4 GB default was requesting ~19x what '
                        'is used and only slows down scheduling. MEASURED peak RSS: '
                        'for dx <= 0.10 the lattice dominates and peak = 171 MB + '
                        '3.87/dx^2 MB, so dx=0.10 is 0.56 GB and dx=0.05 is 1.7 GB. '
                        'For dx >= 0.25 the peak does NOT fall with dx -- it sits at '
                        '0.6-0.9 GB at w <= 1.0, dominated by the freeze-out/'
                        'afterburner stage (measured 890 MB at w=0.5 dx=0.30, 616 MB '
                        'at w=1.0 dx=0.30, 851 MB at w=1.0 dx=0.40). At w = 1.5 the '
                        'peak rises to ~1.1 GB and is still flat in dx (1090, 1108, '
                        '1073 MB at dx=0.20/0.30), so 1 GB is NOT enough there. '
                        'Practical: -mem 2 for dx <= 0.075, or dx >= 0.25, or '
                        'w >= 1.5; -mem 1 only for 0.10 <= dx <= 0.20 and w <= 1.0. '
                        'Passing -mem 1024 means 1024 GB, which matches nothing and '
                        'leaves every job idle forever.'
                        )
    parser.add_argument('-disk', '--disk_per_job', metavar='', type=int,
                        default=10, help='scratch disk per job (GB). Events are '
                        'processed sequentially into the same working '
                        'directory, so this has to cover the whole batch, not '
                        'one event.')
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
