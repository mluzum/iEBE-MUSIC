# iEBE-MUSIC
This is a repository is an overarching numerical framework for event-by-event simulations of relativistic heavy-ion collisions.

If you have any questions, please email to the iEBE-MUSIC google groups, iebe-music@googlegroups.com

## Setup & Ingradients:
All the code packages can be downloaded from online git repositories. Please use `codes/get_code_packages.sh` to download the code packages and `codes/compile_code_packages.sh` to compile all the packages before event-by-event simulations.

Initial conditions:

- [IPGlasma](https://github.com/schenke/ipglasma)
- [3DMCGlauber](https://github.com/chunshen1987/3dMCGlauber): a 3D Monte-Carlo Glauber model for heavy-ion collisions

Pre-equilibrium evolution:

- [KoMPoST](https://github.com/KMPST/KoMPoST)

Hydrodynamics:

- [MUSIC](https://github.com/MUSIC-fluid/MUSIC)

Particlization & hadronic transport:

- [iSS](https://github.com/chunshen1987/iSS) + [UrQMD](https://Chunshen1987@bitbucket.org/Chunshen1987/urqmd_afterburner.git)

## Usage:

type `./generate_jobs.py -h` for help information

## Smoke Tests

This repository provides a staged smoke-test runner:

```bash
./run_full_stack_tests.sh quick
./run_full_stack_tests.sh build
./run_full_stack_tests.sh full
```

- `quick`: Python syntax/unit tests and lightweight CLI checks.
- `build`: includes external package fetch/compile and job-generation smoke.
- `full`: includes Docker build plus a single-event full simulation smoke.

Useful toggles:

```bash
RUN_TRENTO_SMOKE=1 ISOBAR_SEED_FILE=/abs/path/nucleon-seeds.hdf ./run_full_stack_tests.sh build
SIM_TIMEOUT_SECONDS=3600 ./run_full_stack_tests.sh full
```

There is also a consolidated pre-push validator:

```bash
python3 test_pre_push_validation.py
```

### 3DMCGlauber Light-Ion Tables

Standard 3DMCGlauber tables are downloaded by `codes/get_code_packages.sh`.

If you also have local reweighting tables (for example:
`O16_NLEFT_reweighting.bin.in` and `Ne20_NLEFT_reweighting.bin.in`),
`codes/get_code_packages.sh` will link them into
`codes/3dMCGlauber_code/tables` when present.

Default lookup path:

```bash
/data/mluzum/light_ion_simulations
```

To use a different location:

```bash
LIGHT_ION_TABLES_DIR=/custom/path/to/tables ./codes/get_code_packages.sh
```

## Parameters:
Users can pass model parameters through a python script `parameters_dict_user.py`. It contains multiple dictionaries, which are related to each code module inside the iEBE-MUSIC framework. This script will update the master parameters dictionaries in `config/parameters_dict_master.py`. One can read `config/parameters_dict_master.py` for all the available parameters options for each module. If a user want to modify any parameters, he can add it in the `parameters_dict_user.py`.

#### initial_dict
The `initial_dict` dictionary specify the type of the initial condition to use,

- IPGlasma
- 3DMCGlauber

For the IPGlasma initial condition, the user needs to specify the HDF5 database filename. 

For the 3DMCGlauber initial condition,

1. If `database_name : "self"`, initial condition will be generated on the fly with the rest part of the simulations.

2. If `database_name : database_file`, the code package will use the pre-generated initial coniditions stored in the database (HDF5).

#### music_dict
The `music_dict` has all the parameters to run MUSIC for (3+1)D hydrodynamic simulations. 

    'Initial_profile': 9,  for IPGlasma initial condition
        - 9: IPGlasma (full Tmunu),
        - 91: e and u^\mu,
        - 92: e only,
        - 93: e, u^\mu, and pi^\munu
    'Initial_profile': 13,  for 3D MCGlauber initial condition
        - 13: 3D MCGlauber initial condition with dynamical initialization,
        - 131: 3D MCGlauber initial condition with instantaneous initialization

## Settings on NERSC:

The clusters on NERSC does not use utf-8 as default. To run the script properly, one needs to add the following commands in the ~/.bashrc.ext file,

```
export PYTHONIOENCODING=utf-8
export LC_CTYPE=en_US.UTF8
```

## Docker Support

The iEBE-MUSIC has its official docker image on docker hub [iebe-music](https://hub.docker.com/r/chunshen1987/iebe-music).

## Coding Style

We use YAPF to impose coding format for the python scripts. Before every commit, please use

    yapf -i filename.py

to apply the uniformed format to the source code files
