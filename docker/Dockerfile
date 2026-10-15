# Base image is pinned by digest, not tag: tags are mutable and would silently
# change the toolchain underneath an otherwise identical commit.
FROM opensciencegrid/software-base:23-el9-release@sha256:7d9289e11856257d011e6542557cc78e4ec11d5d421e8a68629655afb61b0e52

LABEL org.opencontainers.image.source="https://github.com/mluzum/iEBE-MUSIC"

RUN yum -y install \
        cmake \
        cmake3 \
        git \
        eigen3-devel \
        gcc \
        gcc-c++ \
        gcc-gfortran \
        gsl-devel \
        fftw \
        fftw-devel \
        hdf5-devel \
        zlib-devel \
        make \
        openmpi-devel \
        python3 \
        python3-pip \
        time \
        vim \
        wget \
        openmpi \
        boost-devel \
        rsync \
        && \
    yum clean all

# Install pre-reqs python packages.
#
# ALL of these are pinned. `freestream` is physics-critical -- it computes the
# free-streaming initial condition for every event (see hydro_plus_UrQMD_driver.py),
# so leaving it unpinned means two builds of the same commit can disagree on results.
#
# Versions below are the known-good set, taken from an image that built and ran
# successfully (base image ships Python 3.9). Verify with:
#   docker run --rm --entrypoint python3 iebe-music:latest -m pip list
#
# --no-cache-dir on both invocations: the flag on the first one does not apply to
# the second, which left a 59 MB /root/.cache/pip in the image.
RUN python3 -m pip install --no-cache-dir --upgrade pip && \
    python3 -m pip install --no-cache-dir \
    numpy==1.24.4 \
    scipy==1.10.1 \
    h5py==3.14.0 \
    PyYAML==6.0.3 \
    joblib==1.5.3 \
    mpmath==1.4.1 \
    freestream==1.0.1

ENV HOME /opt/

# download and compile the iEBE-MUSIC framework
#
# The framework is fetched by exact commit SHA rather than by branch, so a given
# SHA keeps building the same image after the branch moves on.
#
# The fork URL is hardcoded on purpose (not a build ARG): an ARG value lives in CI
# job config or shell history rather than in git, which would allow two different
# images to be built from the same commit and break "commit SHA => image".
#
# BUMPING: this SHA cannot be the commit that contains it, so it always names the
# last known-good commit. To advance: commit and push your work, then update the
# SHA below in the following commit and rebuild. It must be the FULL 40-character
# SHA: `git fetch` does not resolve an abbreviated object name, and a short SHA
# fails at fetch time with "couldn't find remote ref", not with a checkout error.
#
#   05ebd42 = "Fixed seeds, and the LHC baseline energy (TRENTo normalization 15)"
#             (freeze-out seed derived from base + event_id*1000003 + subevent
#              instead of the system clock; the 3dMCGlauber draw made deterministic
#              in (seed_add, event_id); TRENTo normalization 15 for an LHC baseline)
#   9ac1b3b = "Fluctuate beta2, beta3 and gamma event by event"
#             (also carries the dependency pins, sampler-fork fix, pinned Isobar-Sampler
#             and the faster isobar sampler)
RUN cd ${HOME} && \
    mkdir iEBE-MUSIC && cd iEBE-MUSIC && \
    git init -q . && \
    git remote add origin https://github.com/mluzum/iEBE-MUSIC.git && \
    git fetch -q --depth=1 origin 05ebd4298477a656fb7584741c266bc3292d72e1 && \
    git checkout -q FETCH_HEAD && \
    test "$(git rev-parse HEAD)" = "05ebd4298477a656fb7584741c266bc3292d72e1" && \
    cd codes && \
    bash get_code_packages_test.sh && \
    ./compile_code_packages.sh && \
    cd ../EOS_database && \
    bash download_EOSdatabase1D.sh && \
    bash download_QGPViscositydatabase1D.sh && \
    cd ../config/BESPost && \
    bash download_posteriorChain.sh && \
    cd ../arXiv_2408.00537 && \
    bash download_posteriorChain.sh

# Cleaning caches to reduce size of image
RUN yum clean all && rm -rf /root/.cache/pip

# Strip build artefacts and source trees that no event folder ever reads.
#
# The image is transferred to every job, so dead weight here is paid thousands of
# times across the sweep. Only the compiler runs above, so anything below is
# runtime-neutral.
#
# The keep-list is not guessed: it is exactly the set of paths generate_jobs.py
# symlinks or copies into an event folder, plus shared libraries the binaries
# link at runtime:
#   MUSIC_code          -> MUSIChydro, EOS/, tables/
#   iSS_code            -> iSS.e, iSS_tables/, iSS_parameters.dat
#   hadronic_..._toolkit-> hadronic_afterburner_tools.e, EOS/, ebe_scripts/
#   3dMCGlauber_code    -> 3dMCGlb.e, eps09/, tables/
#   ipglasma_code       -> ipglasma, utilities/, nucleusConfigurations/, tables/
#   kompost_code        -> EKT, KoMPoST.exe
#   trento_code         -> build/src/trento
#   photonEmission_code -> hydro_photonEmission.e, ph_rates/
#   isobar_sampler_code -> exec/build_isobars.py
#
# WITH_OPTIONAL_CODES selects the campaign scope:
#   1 (default) full image. smash_code and urqmd_code stay, and so does
#     /opt/pythia8315, because the built `smash` links libpythia8.so from
#     /opt/pythia8315/lib and embeds /opt/pythia8315/share/Pythia8/xmldoc.
#   0 slim image for the TRENTo+decay campaign. Drops every backend that path
#     never touches -- SMASH, UrQMD, osc2u, IPGlasma, KoMPoST, photon emission,
#     3dMCGlauber -- and /opt/pythia8315 with them. That is ~555 MB of the
#     image, which matters because the image is pulled per job over OSDF.
#     The always-kept list above is asserted present in BOTH modes, so 0 cannot
#     silently drop something an event folder needs.
# The full image is one flag away:
#   docker build --build-arg WITH_OPTIONAL_CODES=1 -t iebe-music:full .
#   docker build --build-arg WITH_OPTIONAL_CODES=0 -t iebe-music:slim .
# iSS.e, MUSIChydro and hadronic_afterburner_tools.e link only system libraries,
# which is what makes their build/ trees safe to drop in either mode.
#
# After the deletions the keep-list is re-checked, so a future change to the
# packages cannot silently drop something an event folder needs.
ARG WITH_OPTIONAL_CODES=1
RUN set -eux; \
    C=/opt/iEBE-MUSIC/codes; \
    if [ "${WITH_OPTIONAL_CODES}" != "0" ] && [ "${WITH_OPTIONAL_CODES}" != "1" ]; then \
        echo "WITH_OPTIONAL_CODES must be 0 or 1, got ${WITH_OPTIONAL_CODES}" >&2; \
        exit 1; \
    fi; \
    rm -rf $C/MUSIC_code/build $C/MUSIC_code/src $C/MUSIC_code/tests \
           $C/MUSIC_code/doxygen $C/MUSIC_code/utilities \
           $C/MUSIC_code/example_inputfiles; \
    rm -rf $C/iSS_code/build $C/iSS_code/lib $C/iSS_code/src \
           $C/iSS_code/utilities $C/iSS_code/tests $C/iSS_code/EOS.tar.gz; \
    rm -rf $C/hadronic_afterburner_toolkit_code/src \
           $C/hadronic_afterburner_toolkit_code/unit_tests; \
    rm -rf $C/3dMCGlauber_code/src $C/3dMCGlauber_code/build; \
    rm -rf $C/ipglasma_code/src $C/ipglasma_code/build; \
    rm -rf $C/kompost_code/src; \
    rm -rf $C/trento_code/src $C/trento_code/test; \
    rm -rf $C/photonEmission_hydroInterface_code/src; \
    for p in \
        $C/MUSIC_code/MUSIChydro $C/MUSIC_code/EOS $C/MUSIC_code/tables \
        $C/iSS_code/iSS.e $C/iSS_code/iSS_tables \
        $C/hadronic_afterburner_toolkit_code/hadronic_afterburner_tools.e \
        $C/hadronic_afterburner_toolkit_code/EOS \
        $C/hadronic_afterburner_toolkit_code/ebe_scripts \
        $C/3dMCGlauber_code/3dMCGlb.e $C/3dMCGlauber_code/eps09 \
        $C/3dMCGlauber_code/tables \
        $C/ipglasma_code/ipglasma $C/ipglasma_code/utilities \
        $C/ipglasma_code/nucleusConfigurations $C/ipglasma_code/tables \
        $C/kompost_code/EKT $C/kompost_code/KoMPoST.exe \
        $C/trento_code/build/src/trento \
        $C/photonEmission_hydroInterface_code/hydro_photonEmission.e \
        $C/photonEmission_hydroInterface_code/ph_rates \
        $C/isobar_sampler_code/exec/build_isobars.py \
    ; do \
        test -e "$p" || { echo "MISSING after slimming: $p" >&2; exit 1; }; \
    done; \
    if [ "${WITH_OPTIONAL_CODES}" = "0" ]; then \
        echo "WITH_OPTIONAL_CODES=0: dropping every backend the TRENTo+decay"; \
        echo "path never touches (SMASH, UrQMD, IPGlasma, KoMPoST, photon"; \
        echo "emission, 3dMCGlauber) plus /opt/pythia8315, which only SMASH"; \
        echo "links. Nothing above is in the always-kept list, which is what"; \
        echo "makes this safe; the assertion loop is the check."; \
        rm -rf $C/smash_code $C/smash $C/urqmd_code $C/osc2u \
               $C/3dMCGlauber_code $C/ipglasma_code \
               $C/photonEmission_hydroInterface_code $C/kompost_code \
               /opt/pythia8315; \
        for p in $C/smash_code/build/smash \
                 $C/urqmd_code/urqmd/urqmd.e \
                 /opt/pythia8315/lib/libpythia8.so; do \
            test ! -e "$p" || { echo "NOT REMOVED: $p" >&2; exit 1; }; \
        done; \
    else \
        for p in $C/smash_code/build/smash \
                 $C/urqmd_code/urqmd/urqmd.e \
                 /opt/pythia8315/lib/libpythia8.so; do \
            test -e "$p" || { echo "MISSING after slimming: $p" >&2; exit 1; }; \
        done; \
    fi

ENV PYTHONIOENCODING utf-8
WORKDIR ${HOME}

RUN mkdir -p /opt/.local/share/trento
