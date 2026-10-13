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
# SHA below in the following commit and rebuild.
#
#   9ac1b3b = "Fluctuate beta2, beta3 and gamma event by event"
#             (also carries the dependency pins, sampler-fork fix, pinned Isobar-Sampler
#             and the faster isobar sampler)
RUN cd ${HOME} && \
    mkdir iEBE-MUSIC && cd iEBE-MUSIC && \
    git init -q . && \
    git remote add origin https://github.com/mluzum/iEBE-MUSIC.git && \
    git fetch -q --depth=1 origin 79c3a12b4211921a9c048ce6e47af601eaf4bd5a && \
    git checkout -q FETCH_HEAD && \
    test "$(git rev-parse HEAD)" = "79c3a12b4211921a9c048ce6e47af601eaf4bd5a" && \
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
# smash_code and urqmd_code are left intact, and /opt/pythia8315 is kept: the
# built `smash` links libpythia8.so from /opt/pythia8315/lib and embeds the path
# /opt/pythia8315/share/Pythia8/xmldoc, so removing it breaks SMASH at runtime.
# iSS.e, MUSIChydro and hadronic_afterburner_tools.e link only system libraries,
# which is what makes their build/ trees safe to drop.
#
# After the deletions the keep-list is re-checked, so a future change to the
# packages cannot silently drop something an event folder needs.
RUN set -eux; \
    C=/opt/iEBE-MUSIC/codes; \
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
        $C/smash_code/build/smash $C/urqmd_code/urqmd/urqmd.e \
        /opt/pythia8315/lib/libpythia8.so \
    ; do \
        test -e "$p" || { echo "MISSING after slimming: $p" >&2; exit 1; }; \
    done

ENV PYTHONIOENCODING utf-8
WORKDIR ${HOME}

RUN mkdir -p /opt/.local/share/trento
