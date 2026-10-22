#!/usr/bin/env bash

set -euo pipefail

# download the code package

clone_repo_at_commit() {
  local repo_url=$1
  local repo_dir=$2
  local target_commit=$3
  local target_branch=${4:-}

  rm -fr "${repo_dir}"
  if [ -n "${target_branch}" ]; then
    git clone --depth=1 -b "${target_branch}" "${repo_url}" "${repo_dir}"
  else
    git clone --depth=1 "${repo_url}" "${repo_dir}"
  fi
  (
    cd "${repo_dir}"
    git fetch --depth=1 origin "${target_commit}"
    git checkout "${target_commit}"
    test "$(git rev-parse HEAD)" = "${target_commit}"
  )
  rm -fr "${repo_dir}/.git"
}

clone_repo_at_tag() {
  local repo_url=$1
  local repo_dir=$2
  local target_tag=$3

  rm -fr "${repo_dir}"
  git clone --depth=1 -b "${target_tag}" "${repo_url}" "${repo_dir}"
  rm -fr "${repo_dir}/.git"
}

# This repository owns codes/isobar_sampler_code/exec/build_isobars.py as a tracked
# fork (see EMULATOR_SWEEP_PLAN.md decision D1), and the short-range-correlation data
# file correlation_files/Ru_correlation_Alvioli.npy, without which the sampler's
# "realistic" correlation path cannot run at all -- the upstream repository carries the
# file but the fork commit that introduced build_isobars.py did not, and the clone
# below does `rm -fr` on isobar_sampler_code, which would delete it anyway. So stash
# both and restore them afterwards. Everything else in isobar_sampler_code (notably
# make_seeds.py) still comes from upstream at the pin below.
ISO_BAR_FORK_BACKUP="$(mktemp)"
if [ -f isobar_sampler_code/exec/build_isobars.py ]; then
    cp isobar_sampler_code/exec/build_isobars.py "${ISO_BAR_FORK_BACKUP}"
else
    rm -f "${ISO_BAR_FORK_BACKUP}"
    echo "WARNING: in-tree Isobar-Sampler fork not found; upstream build_isobars.py will be used." >&2
fi
ISO_BAR_CORR_BACKUP="$(mktemp)"
if [ -f isobar_sampler_code/correlation_files/Ru_correlation_Alvioli.npy ]; then
    cp isobar_sampler_code/correlation_files/Ru_correlation_Alvioli.npy "${ISO_BAR_CORR_BACKUP}"
else
    rm -f "${ISO_BAR_CORR_BACKUP}"
    echo "WARNING: in-tree Alvioli correlation file not found; the realistic short-range"
    echo "         correlation path will not be available." >&2
fi

# download Isobar-Sampler (used by TRENTo initial conditions)
clone_repo_at_commit \
  https://github.com/mluzum/Isobar-Sampler.git \
  isobar_sampler_code \
  bc586de03c26a3f3e4d6749e385ea015dcb204f2

if [ -f "${ISO_BAR_FORK_BACKUP}" ]; then
    cp "${ISO_BAR_FORK_BACKUP}" isobar_sampler_code/exec/build_isobars.py
    rm -f "${ISO_BAR_FORK_BACKUP}"
    echo "Restored in-tree Isobar-Sampler fork over upstream clone."
fi
if [ -f "${ISO_BAR_CORR_BACKUP}" ]; then
    mkdir -p isobar_sampler_code/correlation_files
    cp "${ISO_BAR_CORR_BACKUP}" isobar_sampler_code/correlation_files/Ru_correlation_Alvioli.npy
    rm -f "${ISO_BAR_CORR_BACKUP}"
    echo "Restored in-tree Alvioli correlation file."
fi
fi

# download TRENTo (used by TRENTo initial conditions)
clone_repo_at_commit \
  https://github.com/jppicchetti/trento_sync.git \
  trento_code \
  48370133999300b10d0a1b061c8b9c365e3ee4f2

# download 3DMCGlauber
clone_repo_at_commit \
  https://github.com/mluzum/3dMCGlauber \
  3dMCGlauber_code \
  1d9856c6ce2bbad28059ed8815ebdf246aa37cdf

# download IPGlasma
clone_repo_at_commit \
  https://github.com/chunshen1987/ipglasma \
  ipglasma_code \
  bf92fe1758a61acc5cf84dff2428b83570ea81fa \
  ipglasma_jimwlk

# download KoMPoST
clone_repo_at_commit \
  https://github.com/chunshen1987/KoMPoST \
  kompost_code \
  ad5fe9d3b26434bb1d5c29820499ef26808b5a47

# download MUSIC (XSCAPE branch for SMASH/UrQMD compatibility)
clone_repo_at_commit \
  https://github.com/MUSIC-fluid/MUSIC \
  MUSIC_code \
  cfcc26455450588961e81139045dc0eef387437c \
  XSCAPE

# download iSS particle sampler (XSCAPE branch for OSCAR2013 output compatible with SMASH)
clone_repo_at_commit \
  https://github.com/chunshen1987/iSS \
  iSS_code \
  d242555306930f813881caca500f0e6f82036b2e \
  XSCAPE

# download photonEmission wrapper
clone_repo_at_commit \
  https://github.com/chunshen1987/photonEmission_hydroInterface \
  photonEmission_hydroInterface_code \
  b80fb78c154cc9131162c8205615faffc86d6a49

# download UrQMD afterburner
clone_repo_at_commit \
  https://Chunshen1987@bitbucket.org/Chunshen1987/urqmd_afterburner.git \
  urqmd_code \
  09eeac28b5861d68d166c1f89b2e97e0a0ebfe8f

# download SMASH afterburner
clone_repo_at_tag \
  https://github.com/smash-transport/smash.git \
  smash_code \
  SMASH-3.2.2

# download and build Pythia8 (required to compile SMASH)
#
# Cloned from the ALICE mirror at an exact commit instead of downloaded from
# pythia.org. Every pythia.org tarball path now returns 404 from CI, including
# the current release, and those paths are not stable anyway -- the previous
# pythia8315.tgz URL worked when this image was last built on 2026-10-08 and
# stopped working afterwards. A git pin is immutable in a way a URL is not.
# The tag is v8315-alice1, i.e. PYTHIA 8.3.15, the version SMASH is built against.
#
# PYTHIA_INSTALL_DIR must remain ${HOME}/pythia8315: compile_code_packages.sh
# hardcodes that path via -DPythia_CONFIG_EXECUTABLE when configuring SMASH.
PYTHIA_REPO="https://github.com/alisw/pythia8.git"
PYTHIA_COMMIT="3c980c58fc8fd2a089e5f3aa40135208463c9b38"  # tag v8315-alice1
PYTHIA_VERSION="pythia8315"
PYTHIA_INSTALL_DIR="${HOME}/${PYTHIA_VERSION}"
if [ ! -f "${PYTHIA_INSTALL_DIR}/bin/pythia8-config" ]; then
    echo "Building Pythia8 (${PYTHIA_VERSION}) in ${PYTHIA_INSTALL_DIR} ..."
    (
        cd /tmp
        rm -rf pythia8-src
        git clone --quiet "${PYTHIA_REPO}" pythia8-src
        cd pythia8-src
        git checkout --quiet "${PYTHIA_COMMIT}"
        test "$(git rev-parse HEAD)" = "${PYTHIA_COMMIT}"
        # Defensive: some CI/container checkouts run with core.fileMode=false,
        # which would leave configure non-executable.
        chmod +x configure
        ./configure --prefix="${PYTHIA_INSTALL_DIR}"
        make -j2
        make install
        cd /tmp
        rm -rf pythia8-src
    )
    if [ ! -f "${PYTHIA_INSTALL_DIR}/bin/pythia8-config" ]; then
        echo "ERROR: Pythia8 install did not produce ${PYTHIA_INSTALL_DIR}/bin/pythia8-config" >&2
        exit 1
    fi
else
    echo "Pythia8 already installed at ${PYTHIA_INSTALL_DIR}, skipping."
fi


# download hadronic afterburner toolkit
clone_repo_at_commit \
  https://github.com/chunshen1987/hadronic_afterburner_toolkit \
  hadronic_afterburner_toolkit_code \
  2326ba21a76d7bb533aa1d39a50f3dca298ef9c3 \
  main

#download deltaf_tables for iSS
(
  cd iSS_code/iSS_tables/deltaf_tables/urqmd
  # Older iSS layouts required downloading these tables; the pinned commit
  # already ships them. Keep backward compatibility by running the script
  # only when it exists.
  if [ -x download_NEoS4D_deltafCoeffs.sh ]; then
    bash download_NEoS4D_deltafCoeffs.sh
  elif [ -f download_NEoS4D_deltafCoeffs.sh ]; then
    bash ./download_NEoS4D_deltafCoeffs.sh
  else
    echo "download_NEoS4D_deltafCoeffs.sh not found; using bundled deltaf tables"
  fi
)

# download nucleus configurations for 3D-Glauber
(cd 3dMCGlauber_code/tables; bash download_nucleusTables.sh;)
# download nucleus configurations for IP-Glasma
(cd ipglasma_code/nucleusConfigurations; bash download_nucleusTables.sh;)
# download essential EOS files for hydro simulations
# SMASH_binary argument provides binary EOS tables required when SMASH is the afterburner
(cd MUSIC_code/EOS; bash download_hotQCD.sh SMASH_binary; bash download_hotQCD.sh; bash download_Neos2D.sh bqs;)