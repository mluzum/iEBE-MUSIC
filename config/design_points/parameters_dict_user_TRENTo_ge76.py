# 76Ge + 76Ge, the first system for the emulator campaign.
#
# TRENTo initial conditions, decay afterburner, rigid deformation (all widths
# zero) -- this is the reference design point and the timing/reproducibility
# baseline, not a sweep point.
#
# Self-contained on purpose: it does not wrap another template, because this
# file is imported by generate_jobs.py running INSIDE the container, where the
# repo lives at /opt/iEBE-MUSIC. afterburner_type is written as a literal
# because the OSG and HTCondor generators detect it with a regex over the raw
# file text, so it must appear literally even though control_dict is built here.

control_dict = {
    "initial_state_type": "TRENTo",
    "afterburner_type": "decay",
    "save_hydro_surfaces": False,
    "save_UrQMD_files": False,
    "save_ipglasma_results": False,
    "walltime": "01:00:00",
}

trento_dict = {
    "type": "self",
    "projectile": ["nuclei_target/target.hdf",
                   "nuclei_projectile/projectile.hdf"],
    "number-events": 1,
    "quiet": False,
    "output": "initial_condition",
    "reduced-thickness": 0.0,
    "fluctuation": 1.0,
    "nucleon-width": 0.5,
    "cross-section": 4.23,
    "normalization": 5.73,
    "b-min": 0,
    "b-max": 0.75,
    "grid-max": 15.0,
    "grid-step": 0.2,
}

# grid_max MUST agree with trento_dict["grid-max"]: the driver rebuilds the
# table with n_grid = 2*grid_max/grid_step and rejects a TRENTo matrix of a
# different size. Leaving these at their defaults (10.0/0.2 -> n_grid=100)
# against a TRENTo grid-max of 15.0 (-> 150x150) fails with
# "Input matrix shape (150, 150) does not match n_grid=100".
free_streaming_dict = {
    "tau": 1.0,
    "grid_max": 15.0,
    "grid_step": 0.2,
}

music_dict = {
    "smash": {
        "ic": 0,
        "eosL": 1,
        "eos": 1,
        "pt": 0.16,
        "delta": 0.46,
        "alpha": 0.9,
        "bulkvisc": 0,
        "chempot": 0.04,
        "tmax": 25,
        "pre": 0.15,
        "tau0": 0.1,
        "nb": 200,
    },
    "urqmd": {
        "UrQMD": 0,
    },
}

iss_dict = {
    "UrQMD": 0,
}

hadronic_afterburner_toolkit_dict = {
    "multicore": 0,
    "analysis": {"spvn": 1},
}

isobars_conf_dict_target = {
    "isobar_properties": {
        "description": "Nuclear properties of isobars to be sampled.",
        "isobar1": {
            "isobar_name": "target",
            "WS_radius": {
                "description": "Woods-Saxon radius parameter R",
                "value": 7.2,
            },
            "WS_diffusiveness": {
                "description": "Woods-Saxon diffusiveness parameter a",
                "value": 0.5,
            },
            "beta_2": {
                "description": "Quadrupole deformation",
                "value": 0.10,
            },
            "gamma": {
                "description": "Triaxiality angle gamma_lit (rad)",
                "value": 0.4363,
            },
            "beta_3": {
                "description": "Octupole deformation",
                "value": 0.0,
            },
            "sigma_beta_2": {
                "description": "Event-by-event width of beta_2; 0 fixes the shape",
                "value": 0.0,
            },
            "sigma_beta_3": {
                "description": "Event-by-event width of beta_3; 0 fixes the shape",
                "value": 0.0,
            },
            "sigma_gamma": {
                "description": "Event-by-event width of gamma_lit (rad)",
                "value": 0.0,
            },
            "beta_max": {
                "description": "Upper bound on quadrupole strength (Option B)",
                "value": 0.5,
            },
            "shape_distribution": {
                "description": "How the per-event shape is drawn",
                "value": "wedge",
            },
            "sigma_plane": {
                "description": "Width of the plane-form Gaussian; 0 is rigid",
                "value": 0.0,
            },
            "plane_anisotropy": {
                "description": "Splits sigma_plane with fixed geometric mean",
                "value": 0.0,
            },
            "correlation_length": {
                "description": "Correlation length of the correlation function",
                "value": 0.4,
            },
            "correlation_strength": {
                "description": "Strength of the correlation function",
                "value": 0.0,
            },
        },
    },
    "isobar_samples": {
        "description": "Configuration sampling settings.",
        "number_configs": {
            "description": "Number of configurations to be sampled.",
            "value": 1,
        },
        "number_nucleons": {
            "description": "Mass number A of the nuclei.",
            "value": 76,
        },
        "seed_source": {
            "description": "Nucleon seeds: philox (deterministic)",
            "value": "philox",
        },
        "master_seed": {
            "description": "Master seed for the philox source.",
            "value": 8675309,
        },
        "pool_modulus": {
            "description": "Size of the virtual nucleus pool, 2**32.",
            "value": 4294967296,
        },
        "output_path": {
            "description": "Output directory where to save",
            "dirname": "nuclei_target",
        },
        "number_of_parallel_processes": {
            "description": "Number of processes to compute in parallel.",
            "value": -1,
        },
        "start_configuration": {
            "description": "x",
            "value": 0,
        },
    },
}

isobars_conf_dict_projectile = {
    "isobar_properties": {
        "description": "Nuclear properties of isobars to be sampled.",
        "isobar1": {
            "isobar_name": "projectile",
            "WS_radius": {
                "description": "Woods-Saxon radius parameter R",
                "value": 7.2,
            },
            "WS_diffusiveness": {
                "description": "Woods-Saxon diffusiveness parameter a",
                "value": 0.5,
            },
            "beta_2": {
                "description": "Quadrupole deformation",
                "value": 0.10,
            },
            "gamma": {
                "description": "Triaxiality angle gamma_lit (rad)",
                "value": 0.4363,
            },
            "beta_3": {
                "description": "Octupole deformation",
                "value": 0.0,
            },
            "sigma_beta_2": {
                "description": "Event-by-event width of beta_2",
                "value": 0.0,
            },
            "sigma_beta_3": {
                "description": "Event-by-event width of beta_3",
                "value": 0.0,
            },
            "sigma_gamma": {
                "description": "Event-by-event width of gamma_lit",
                "value": 0.0,
            },
            "beta_max": {
                "description": "Upper bound on quadrupole strength (Option B)",
                "value": 0.5,
            },
            "shape_distribution": {
                "description": "How the per-event shape is drawn",
                "value": "wedge",
            },
            "sigma_plane": {
                "description": "Width of the plane-form Gaussian; 0 is rigid",
                "value": 0.0,
            },
            "plane_anisotropy": {
                "description": "Splits sigma_plane with fixed geometric mean",
                "value": 0.0,
            },
            "correlation_length": {
                "description": "Correlation length of the correlation function",
                "value": 0.4,
            },
            "correlation_strength": {
                "description": "Strength of the correlation function",
                "value": 0.0,
            },
        },
    },
    "isobar_samples": {
        "description": "Configuration sampling settings.",
        "number_configs": {
            "description": "Number of configurations to be sampled.",
            "value": 1,
        },
        "number_nucleons": {
            "description": "Mass number A of the nuclei.",
            "value": 76,
        },
        "seed_source": {
            "description": "Nucleon seeds: philox (deterministic)",
            "value": "philox",
        },
        "master_seed": {
            "description": "Master seed for the philox source.",
            "value": 8675309,
        },
        "pool_modulus": {
            "description": "Size of the virtual nucleus pool, 2**32.",
            "value": 4294967296,
        },
        "output_path": {
            "description": "Output directory where to save",
            "dirname": "nuclei_projectile",
        },
        "number_of_parallel_processes": {
            "description": "Number of processes to compute in parallel.",
            "value": -1,
        },
        "start_configuration": {
            "description": "x",
            "value": 2654435761,
        },
    },
}

isobar_seed_file = ""