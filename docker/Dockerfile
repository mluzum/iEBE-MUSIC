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
RUN python3 -m pip install --no-cache-dir --upgrade pip && \
    python3 -m pip install \
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
#   d02e9ec = "Speed up isobar sampling 2.8x without changing the physics"
#             (also carries the dependency pins, sampler-fork fix, pinned Isobar-Sampler
#             and the faster isobar sampler)
RUN cd ${HOME} && \
    mkdir iEBE-MUSIC && cd iEBE-MUSIC && \
    git init -q . && \
    git remote add origin https://github.com/mluzum/iEBE-MUSIC.git && \
    git fetch -q --depth=1 origin d02e9ec1fc9ee3b2bcabebe4a4e4f9d2c3b6dba1 && \
    git checkout -q FETCH_HEAD && \
    test "$(git rev-parse HEAD)" = "d02e9ec1fc9ee3b2bcabebe4a4e4f9d2c3b6dba1" && \
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
RUN yum clean all

ENV PYTHONIOENCODING utf-8
WORKDIR ${HOME}

RUN mkdir -p /opt/.local/share/trento
