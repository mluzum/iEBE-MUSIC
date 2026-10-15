# w = 0.50 fm reference ladder, re-run as a whole on image 443fecee.
#
# The earlier w = 0.50 ladder straddled two images: dx = 0.15 and 0.30 needed the
# lattice-from-array fix and so were run on the new image, while dx = 0.10, 0.20 and
# 0.25 came off the previous one. The fix only bites where TRENTo's 2L/dx arithmetic
# disagrees with its own output array by a cell, but that is an argument, not a
# measurement, and the w=0.20 number is load-bearing for the production rule. Re-running
# the whole row on one image removes the question.

# Grid-convergence study: dx = 0.1 fm, adaptive box, oversampled iSS.
# The cell count is derived from the sizing rule, so dx is exactly the grid spacing
# while the box still shrinks per event. Reference is the finest (0.10 fm).

# 76Ge + 76Ge production settings: oversampled iSS and cut-independent flow output.

# Grid-extent campaign: ref
# reference: nominal normalization, tau, T_freeze
#
# freeze-out is on temperature (use_eps_for_freeze_out=0), so T_freeze directly
# sets where the Cooper-Frye surface lands and therefore how much transverse
# space the run needs. Measured effect on the surface max extent was ~0.3 fm per
# 0.3 change in the energy scale, so it has to be part of any sizing rule.

control_dict = {
    "initial_state_type": "TRENTo",
    "afterburner_type": "decay",
    "save_hydro_surfaces": False,
    "adaptive_grid": True,
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
    "b-max": 14.0,
    "grid-max": 15.0,
    "grid-step": 0.15,
}

# grid_max MUST agree with trento_dict["grid-max"]: the driver rebuilds the
# table with n_grid = 2*grid_max/grid_step and rejects a TRENTo matrix of a
# different size. Leaving these at their defaults (10.0/0.2 -> n_grid=100)
# against a TRENTo grid-max of 15.0 (-> 150x150) fails with
# "Input matrix shape (150, 150) does not match n_grid=100".
free_streaming_dict = {
    "tau": 1.000,
    "grid_max": 15.0,
    "grid_step": 0.15,
}

music_dict = {
    # Flat MUSIC input keys. Keep this dict FLAT: parameters_dict_master.py
    # writes music_dict verbatim into music_input_mode_2, so a nested sub-dict
    # lands in the input file as a literal Python dict that MUSIC ignores. An
    # earlier version of this file nested these under "smash"/"urqmd" and the
    # whole block -- including the EOS specification -- was silently inert.
    "X_grid_size_in_fm": 15.0,
    "Y_grid_size_in_fm": 15.0,
    "Grid_size_in_x": 200,
    "Grid_size_in_y": 200,
    # Freeze-out on TEMPERATURE. With use_eps_for_freeze_out = 1 (the master
    # default) MUSIC finds the Cooper-Frye surface from eps_freeze_max/min = 0.18
    # and never reads T_freeze, which would make the switching temperature a
    # dead design axis.
    "use_eps_for_freeze_out": 0,
    "T_freeze": 0.12,
}

iss_dict = {
    "UrQMD": 0,
    # OVERSAMPLING ON. The production default has sample_upto_desired_particle_number=0,
    # which means the freeze-out distribution is resampled a fixed number of times and the
    # flow statistics therefore degrade exactly for the small, peripheral systems that the
    # adaptive grid makes cheap. Running until the desired particle number is reached makes
    # the flow statistics multiplicity-independent, which is what makes them usable as an
    # emulator input across the whole centrality range.
    "sample_upto_desired_particle_number": 1,
    "number_of_particles_needed": 100000,
    "maximum_sampling_events": 10000,
}

hadronic_afterburner_toolkit_dict = {
    "multicore": 0,
    "analysis": {"spvn": 1},
    # Flow output: wide, uncut rapidity acceptance and fine pT bins.
    #
    # These are 2D boost-invariant simulations, so rapidity carries no physics. It is only
    # a bookkeeping axis: keeping the full sampled range with no particle cuts means any
    # pseudorapidity acceptance can be formed offline by summing with the Jacobian, and it
    # guarantees no species-dependent efficiency loss. rap_min/rap_max set the window for the
    # per-species v_n output; rapidity_dis_min/max set it for the 2D (rapidity, pT, v_n)
    # density table emitted for all charged hadrons.
    "rap_min": -4.0,
    "rap_max": 4.0,
    "rapidity_distribution": 1,
    "rapidity_dis_min": -4.0,
    "rapidity_dis_max": 4.0,
    "vn_rapidity_dis_pT_min": 0.05,
    "vn_rapidity_dis_pT_max": 4.0,
    "npT": 81,
    "order_max": 10,
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