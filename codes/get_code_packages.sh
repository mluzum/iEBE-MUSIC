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

# download Isobar-Sampler (used by TRENTo initial conditions)
clone_repo_at_commit \
  https://github.com/mluzum/Isobar-Sampler.git \
  isobar_sampler_code \
  bc586de03c26a3f3e4d6749e385ea015dcb204f2

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
(cd MUSIC_code/EOS; bash download_hotQCD.sh SMASH_binary; bash download_Neos2D.sh bqs;)
