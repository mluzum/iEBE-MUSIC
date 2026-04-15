#!/usr/bin/env bash
set -euo pipefail

PROFILE="quick"

usage() {
  cat <<'EOF'
Usage: ./run_full_stack_tests.sh [quick|build|full] [--timeout SECONDS]

Options:
  --timeout SECONDS   Override full simulation timeout (default: 1800)
  -h, --help          Show this help message
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    quick|build|full)
      PROFILE="$1"
      shift
      ;;
    --timeout)
      if [[ $# -lt 2 ]]; then
        echo "--timeout requires a value in seconds" >&2
        exit 2
      fi
      SIM_TIMEOUT_SECONDS="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "${REPO_ROOT}"

RUN_DOCKER_BUILD="${RUN_DOCKER_BUILD:-0}"
RUN_FETCH_AND_COMPILE="${RUN_FETCH_AND_COMPILE:-0}"
RUN_FULL_SIM="${RUN_FULL_SIM:-0}"
RUN_TRENTO_SMOKE="${RUN_TRENTO_SMOKE:-0}"

SIM_TIMEOUT_SECONDS="${SIM_TIMEOUT_SECONDS:-1800}"
if [[ ! "${SIM_TIMEOUT_SECONDS}" =~ ^[0-9]+$ ]] || [[ "${SIM_TIMEOUT_SECONDS}" -le 0 ]]; then
  echo "SIM_TIMEOUT_SECONDS must be a positive integer, got: ${SIM_TIMEOUT_SECONDS}" >&2
  exit 2
fi
DOCKER_IMAGE_TAG="${DOCKER_IMAGE_TAG:-iebe-music:test-local}"

case "${PROFILE}" in
  quick)
    ;;
  build)
    RUN_FETCH_AND_COMPILE=1
    ;;
  full)
    RUN_DOCKER_BUILD=1
    RUN_FETCH_AND_COMPILE=1
    RUN_FULL_SIM=1
    ;;
  *)
    echo "Unknown profile: ${PROFILE}" >&2
    echo "Usage: $0 [quick|build|full]" >&2
    exit 2
    ;;
esac

stage() {
  echo
  echo "============================================================"
  echo "[STAGE] $1"
  echo "============================================================"
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Required command not found: $1" >&2
    exit 1
  }
}

run_cmd() {
  echo "+ $*"
  "$@"
}

run_cmd_timeout() {
  local timeout_s=$1
  shift
  if command -v timeout >/dev/null 2>&1; then
    echo "+ timeout ${timeout_s}s $*"
    timeout "${timeout_s}" "$@"
  else
    echo "timeout command not found; running without timeout"
    echo "+ $*"
    "$@"
  fi
}

need_cmd python3
need_cmd bash

stage "Python Unit And Smoke Tests"
run_cmd python3 -m py_compile \
  generate_jobs.py \
  Cluster_supports/OSG/generate_submission_script.py \
  test_option_validation.py \
  test_configuration_matrix.py \
  test_build_smoke.py \
  test_e2e_runner_smoke.py

run_cmd python3 -m unittest \
  test_option_validation.py \
  test_configuration_matrix.py \
  test_build_smoke.py \
  test_e2e_runner_smoke.py

stage "CLI Smoke Checks"
run_cmd python3 generate_jobs.py -h >/dev/null
run_cmd python3 Cluster_supports/OSG/generate_submission_script.py -h >/dev/null

if [[ "${RUN_DOCKER_BUILD}" == "1" ]]; then
  stage "Docker Build"
  need_cmd docker
  run_cmd docker build -f docker/Dockerfile -t "${DOCKER_IMAGE_TAG}" .
else
  echo "Skipping Docker build stage (set RUN_DOCKER_BUILD=1 or profile=full)"
fi

if [[ "${RUN_FETCH_AND_COMPILE}" == "1" ]]; then
  stage "External Package Download And Compile"
  pushd codes >/dev/null
  run_cmd ./get_code_packages.sh
  run_cmd ./compile_code_packages.sh
  popd >/dev/null
else
  echo "Skipping fetch/compile stage (set RUN_FETCH_AND_COMPILE=1 or profile=build/full)"
fi

stage "Job Generation Smoke (3DMCGlauber)"
SMOKE_ROOT="$(mktemp -d /tmp/iebe-smoke-XXXXXX)"
cleanup() {
  rm -rf "${SMOKE_ROOT}"
}
trap cleanup EXIT

has_generation_sources=1
for src_dir in MUSIC MUSIC_code iSS_code hadronic_afterburner_toolkit hadronic_afterburner_toolkit_code 3dMCGlauber_code; do
  if [[ ! -d "codes/${src_dir}" ]]; then
    has_generation_sources=0
    break
  fi
done

if [[ "${has_generation_sources}" != "1" ]]; then
  if [[ "${RUN_FETCH_AND_COMPILE}" == "1" ]]; then
    echo "Required generation source directories are missing under codes/ after fetch stage." >&2
    exit 1
  fi
  echo "Skipping generation smoke stage (missing sources in codes/: need get_code_packages.sh or profile=build/full)"
else
  SMOKE_PAR="config/parameters_dict_user_3DMCGlauber_dynamical.py"
  if [[ "${RUN_FETCH_AND_COMPILE}" != "1" ]]; then
    # Quick mode should not require compiled UrQMD binaries.
    SMOKE_PAR="${SMOKE_ROOT}/parameters_dict_user_3DMCGlauber_decay_smoke.py"
    run_cmd cp config/parameters_dict_user_3DMCGlauber_dynamical.py "${SMOKE_PAR}"
    cat >> "${SMOKE_PAR}" <<'EOF'

# Overridden for compile-free smoke testing.
control_dict["afterburner_type"] = "decay"
EOF
  fi

  run_cmd python3 generate_jobs.py \
    -w "${SMOKE_ROOT}/playground_3dglb" \
    -c local \
    -par "${SMOKE_PAR}" \
    -n 1 -n_hydro 1 -n_urqmd 1 -n_th 1 \
    --nocopy
fi

if [[ "${RUN_TRENTO_SMOKE}" == "1" ]]; then
  stage "Job Generation Smoke (TRENTo + SMASH wiring)"
  if [[ -z "${ISOBAR_SEED_FILE:-}" ]]; then
    echo "RUN_TRENTO_SMOKE=1 requires ISOBAR_SEED_FILE to be set" >&2
    exit 1
  fi
  if [[ ! -f "${ISOBAR_SEED_FILE}" ]]; then
    echo "ISOBAR_SEED_FILE does not exist: ${ISOBAR_SEED_FILE}" >&2
    exit 1
  fi

  TRENTO_PAR="${SMOKE_ROOT}/parameters_dict_user_TRENTo_smoke.py"
  run_cmd cp config/parameters_dict_user_TRENTo.py "${TRENTO_PAR}"
  run_cmd sed -i "s#\"nucleon-seeds.hdf\"#\"${ISOBAR_SEED_FILE}\"#g" "${TRENTO_PAR}"

  run_cmd python3 generate_jobs.py \
    -w "${SMOKE_ROOT}/playground_trento" \
    -c local \
    -par "${TRENTO_PAR}" \
    -n 1 -n_hydro 1 -n_urqmd 1 -n_th 1 \
    --nocopy
else
  echo "Skipping TRENTo smoke stage (set RUN_TRENTO_SMOKE=1 and ISOBAR_SEED_FILE=/abs/path/file.hdf)"
fi

if [[ "${RUN_FULL_SIM}" == "1" ]]; then
  stage "Full Simulation Smoke (single event)"
  echo "Using full simulation timeout: ${SIM_TIMEOUT_SECONDS}s"
  EVENT_DIR="${SMOKE_ROOT}/playground_3dglb/event_0"
  if [[ ! -d "${EVENT_DIR}" ]]; then
    echo "Expected event folder missing: ${EVENT_DIR}" >&2
    exit 1
  fi
  run_cmd_timeout "${SIM_TIMEOUT_SECONDS}" bash -lc "cd '${EVENT_DIR}' && bash submit_job.script 0"
else
  echo "Skipping full simulation stage (set RUN_FULL_SIM=1 or profile=full)"
fi

stage "All Requested Stages Completed"
echo "Profile: ${PROFILE}"
echo "RUN_DOCKER_BUILD=${RUN_DOCKER_BUILD}"
echo "RUN_FETCH_AND_COMPILE=${RUN_FETCH_AND_COMPILE}"
echo "RUN_FULL_SIM=${RUN_FULL_SIM}"
echo "RUN_TRENTO_SMOKE=${RUN_TRENTO_SMOKE}"
