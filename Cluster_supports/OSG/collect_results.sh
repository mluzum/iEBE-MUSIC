#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

run=${1%/}

if [ -z "${run}" ]; then
    echo "Usage: $0 /absolute/or/relative/path/to/run_folder"
    exit 1
fi

run_abs="$(cd "${run}" && pwd)"

# Shared filesystems (OSDF/NFS/CVMFS-like backends) can produce transient
# HDF5 lock errors; collection is single-process, so disable file locking.
export HDF5_USE_FILE_LOCKING=FALSE

echo "Collecting from: ${run_abs}"
(
    cd "${run_abs}"
    "${SCRIPT_DIR}/combine_multiple_hdf5.py" "${run_abs}"
)
echo "Collection finished in: ${run_abs}"
