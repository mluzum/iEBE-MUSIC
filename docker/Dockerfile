FROM opensciencegrid/software-base:23-el9-release

LABEL maintainer="Chun Shen <chunshen@wayne.edu>"

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
        openmpi \
        python3 \
        python3-pip \
        time \
        vim \
        wget \
        boost-devel \
        rsync \
        && \
    yum clean all

# Install pre-reqs python packages
RUN python3 -m pip install --no-cache-dir --upgrade pip && \
    python3 -m pip install --no-cache-dir \
        numpy==1.24.4 \
        scipy==1.10.1 \
        h5py \
        PyYAML \
        joblib \
        mpmath \
        freestream

ENV HOME=/opt/

# Build and install Pythia8 from source (required by SMASH)
RUN cd /tmp && \
    wget --no-check-certificate https://pythia.org/download/pythia83/pythia8315.tgz && \
    tar xzf pythia8315.tgz && \
    cd pythia8315 && \
    ./configure --prefix=${HOME}/pythia8315 && \
    make -j2 && \
    make install && \
    cd /tmp && \
    rm -rf pythia8315 pythia8315.tgz

# Build the iEBE-MUSIC framework from the local workspace
COPY . ${HOME}/iEBE-MUSIC

RUN cd ${HOME}/iEBE-MUSIC/codes && \
    ./get_code_packages.sh && \
    ./compile_code_packages.sh && \
    cd ../EOS_database && \
    bash download_EOSdatabase1D.sh && \
    bash download_QGPViscositydatabase1D.sh && \
    cd ../initialcondition_database && \
    bash download_smoothTATB.sh && \
    cd ../config/arXiv_2507.11394 && \
    bash download_posteriorChains.sh && \
    cd ../arXiv_2408.00537 && \
    bash download_posteriorChain.sh

# Cleaning caches to reduce size of image
RUN yum clean all

ENV PYTHONIOENCODING=utf-8
WORKDIR ${HOME}

RUN mkdir -p /opt/.local/share/trento
