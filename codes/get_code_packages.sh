#!/usr/bin/env bash

# download the code package

# This repository owns codes/isobar_sampler_code/exec/build_isobars.py as a tracked
# fork (see EMULATOR_SWEEP_PLAN.md decision D1). Stash it before the clone below
# wipes the directory, and restore it afterwards.
ISO_BAR_FORK_BACKUP="$(mktemp)"
if [ -f isobar_sampler_code/exec/build_isobars.py ]; then
    cp isobar_sampler_code/exec/build_isobars.py "${ISO_BAR_FORK_BACKUP}"
else
    rm -f "${ISO_BAR_FORK_BACKUP}"
    echo "WARNING: in-tree Isobar-Sampler fork not found; upstream build_isobars.py will be used." >&2
fi

#download Isobar-Sampler
# Pinned to the same commit and fork that get_code_packages_test.sh uses, so that a
# local run and a container run build the same sampler. This script previously cloned
# genilssom/Isobar-Sampler at the moving branch `test-newchain`, which meant local
# development was not reproducible and could silently diverge from the container.
rm -fr isobar_sampler_code
git clone https://github.com/mluzum/Isobar-Sampler.git isobar_sampler_code
# This script does not run under `set -e`, so the pin is enforced explicitly here:
# without this, a failed fetch/checkout would silently leave the clone at the
# default branch HEAD, which is exactly the unpinned state we are removing.
(
  cd isobar_sampler_code || exit 1
  git fetch --depth=1 origin bc586de03c26a3f3e4d6749e385ea015dcb204f2 || exit 1
  git checkout bc586de03c26a3f3e4d6749e385ea015dcb204f2 || exit 1
  test "$(git rev-parse HEAD)" = "bc586de03c26a3f3e4d6749e385ea015dcb204f2" || exit 1
) || {
    echo "ERROR: could not check out pinned Isobar-Sampler bc586de0." >&2
    echo "       Refusing to continue with an unpinned sampler." >&2
    exit 1
}
rm -fr isobar_sampler_code/.git

if [ -f "${ISO_BAR_FORK_BACKUP}" ]; then
    cp "${ISO_BAR_FORK_BACKUP}" isobar_sampler_code/exec/build_isobars.py
    rm -f "${ISO_BAR_FORK_BACKUP}"
    echo "Restored in-tree Isobar-Sampler fork over upstream clone."
fi

# download TRENTo
rm -fr trento_code
git clone https://github.com/jppicchetti/trento_sync.git trento_code
#(cd trento_code; git checkout ...)
#rm -fr trento_code/.gits

# download 3DMCGlauber
rm -fr 3dMCGlauber_code
git clone --depth=5 https://github.com/chunshen1987/3dMCGlauber 3dMCGlauber_code
#(cd 3dMCGlauber_code; git checkout 22955a36969429e99a85957eb6b3c231870a2015)
rm -fr 3dMCGlauber_code/.git

# download IPGlasma
rm -fr ipglasma_code
git clone --depth=1 https://github.com/chunshen1987/ipglasma -b ipglasma_jimwlk ipglasma_code
#(cd ipglasma_code; git checkout 4d4392724d05502c94bb8c512e382b6d9be9dec8)
rm -fr ipglasma_code/.git

# download KoMPoST
rm -fr kompost_code
git clone --depth=1 https://github.com/chunshen1987/KoMPoST kompost_code
#(cd kompost_code; git checkout ad5fe9d3b26434bb1d5c29820499ef26808b5a47)
rm -fr kompost_code/.git

# download MUSIC
rm -fr MUSIC_code
git clone https://github.com/MUSIC-fluid/MUSIC -b public_stable MUSIC_code
#(cd MUSIC_code; git checkout e898cc826efc0303f2dd688602e6c604c9ef0f91)
rm -fr MUSIC_code/.git

# download iSS particle sampler
rm -fr iSS_code
git clone https://github.com/chunshen1987/iSS -b XSCAPE iSS_code
#(cd iSS_code; git checkout b612a8e425d3e1dfc2d2b71cd208df6810c783be)
rm -fr iSS_code/.git

# download photonEmission wrapper
rm -fr photonEmission_hydroInterface_code
git clone --depth=1 https://github.com/chunshen1987/photonEmission_hydroInterface photonEmission_hydroInterface_code
#(cd photonEmission_hydroInterface_code; git checkout b80fb78c154cc9131162c8205615faffc86d6a49)
rm -fr photonEmission_hydroInterface_code/.git

# download UrQMD afterburner
rm -fr urqmd_code
git clone https://Chunshen1987@bitbucket.org/Chunshen1987/urqmd_afterburner.git urqmd_code
#(cd urqmd_code; git checkout 704c886)
rm -fr urqmd_code/.git

# download SMASH afterburner
rm -rf smash_code
git clone --depth=1 https://github.com/smash-transport/smash.git -b SMASH-3.2.2  smash_code
rm -rf smash_code/.git

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
#
# Unlike get_code_packages_test.sh this script does not run under `set -e`, so
# the subshell enables it explicitly; otherwise a failed clone or checkout would
# be followed by a confusing configure error instead of a clear one.
PYTHIA_REPO="https://github.com/alisw/pythia8.git"
PYTHIA_COMMIT="3c980c58fc8fd2a089e5f3aa40135208463c9b38"  # tag v8315-alice1
PYTHIA_VERSION="pythia8315"
PYTHIA_INSTALL_DIR="${HOME}/${PYTHIA_VERSION}"
if [ ! -f "${PYTHIA_INSTALL_DIR}/bin/pythia8-config" ]; then
    echo "Building Pythia8 (${PYTHIA_VERSION}) in ${PYTHIA_INSTALL_DIR} ..."
    (
        set -e
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



# download hadronic afterburner (pinned: the boost-invariant dN/dy patch below
# is generated against this commit, so do not let it float)
rm -fr hadronic_afterburner_toolkit_code
git clone https://github.com/chunshen1987/hadronic_afterburner_toolkit -b main hadronic_afterburner_toolkit_code
(cd hadronic_afterburner_toolkit_code; git checkout 2326ba21a76d7bb533aa1d39a50f3dca298ef9c3)
rm -fr hadronic_afterburner_toolkit_code/.git

# Boost-invariant (2+1)-d dN/dy: keep every particle and divide by the rapidity
# width iSS sampled the parents from, instead of cutting at an acceptance window
# and dividing by that window. Without this the yield is biased low by the
# daughters that leak outside the window, and it costs ~10x the statistics.
(
  cd hadronic_afterburner_toolkit_code
  patch -p1 --forward < ../patches/hadronic_afterburner_toolkit_boost_invariant_dNdy.patch
)

#download deltaf_tables for iSS
(
  cd iSS_code/iSS_tables/deltaf_tables/urqmd
  bash download_NEoS4D_deltafCoeffs.sh
)

# download nucleus configurations for 3D-Glauber
(cd 3dMCGlauber_code/tables; bash download_nucleusTables.sh;)
# download nucleus configurations for IP-Glasma
(cd ipglasma_code/nucleusConfigurations; bash download_nucleusTables.sh;)
# download essential EOS files for hydro simulations
(cd MUSIC_code/EOS; bash download_hotQCD.sh; bash download_hotQCD.sh SMASH_binary; bash download_Neos2D.sh bqs;)
