# 76Ge+76Ge CENTRAL convergence ladder -- LHC baseline energy.
#
# TRENTo normalization 5.73 -> 15.0, free-streaming tau = 1.0 fm/c. This is the
# baseline the user specified for an LHC collision: at normalization 5.73 the
# deposited energy and multiplicity were far too low to be an LHC-like system.
#
# Seeds are now fixed (see generate_jobs.py: run_afterburner.sh derives the iSS
# seed from base + event_id*1000003 + subevent instead of falling through to the
# system clock), so runs are reproducible AND the same event gets the same
# freeze-out randomness at every dx. That is what makes the paired comparison
# event-by-event rather than noise-dominated.
#
# ANALYSIS: do NOT average the v_n vector over events. Odd harmonics in particular
# cancel. The quantity of interest is the per-event, pT-integrated v_n vector at a
# single grid resolution, compared to its value at dx = 0.10 for the SAME event,
# with the single-event statistical error from the file as the weight.
#
# R = 5.08 fm (A=76), a = 0.5, beta_2 = 0.10, gamma = 0.4363, b-max = 4.0 (central),
# oversampling ON, master_seed 8675309.  w = 0.5 fm, dx = 0.2 fm.

# 76Ge+76Ge CENTRAL convergence ladder at the CORRECT Woods-Saxon radius.
#
# WS_radius 7.2 -> 5.08 fm = 1.2*A^(1/3) for A=76. The old value corresponds to
# A=(7.2/1.2)^3 = 216, i.e. a lead-sized nucleus holding only 76 nucleons: rms radius
# 5.88 fm instead of 4.35 fm, 1.35x too large in r_rms and 2.5x in volume. That is a
# bigger IC, so at fixed dx the old tests resolved a real 76Ge *better* than they
# did -- any convergence rule they produce is optimistic by about that factor.
#
# A=76, a=0.5, beta_2=0.10, gamma=0.4363, master_seed 8675309 and b-max=4.0 are all
# held fixed. Holding b-max fixed holds the b values bit-identical across the whole
# (w, dx) grid, which is what keeps the CRN pairing intact.
#
# w = 0.5 fm, dx = 0.2 fm. Benchmark is the pT-integrated v_n vector (real and imag
# separately) for the unidentified species, which reaches n=9.

# CENTRAL convergence ladder: b-max = 4.0 fm, w = 0.5 fm, dx = 0.2 fm.
#
# Why this batch exists. Every previous w/dx run used b-max = 14.0, which gives
# impact parameters of 5-13 fm and multiplicities of 7-89 against a central
# value near 700. Per-event precision on the pT-integrated v_n came out at
# 95-240% of the value itself, so those runs cannot bound the numerical error in
# v_3 at all -- they can only say 'consistent with zero', which they did, for
# every harmonic 1-9 at both w.
#
# b-max = 4.0 restores a detectable v_3 and roughly 60x the particles, which is
# ~8x better per-event sigma. The benchmark is the pT-integrated v_n VECTOR
# (real and imag separately, never the magnitude) for the unidentified species,
# which reaches n = 9, plus pi+ (n = 1..5) and the all-charged reference.
#
# dx = 0.10 is the reference. w = 0.25 and 0.50 bracket the regime where the
# (undocumented) MUSIC lattice proxy claimed an 11-20x sensitivity to w; the
# particle observables showed no such effect, and this tests it properly.

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
    "normalization": 15.0,
    "b-min": 0,
    "b-max": 4.0,
    "grid-max": 15.0,
    "grid-step": 0.2,
}

# grid_max MUST agree with trento_dict["grid-max"]: the driver rebuilds the
# table with n_grid = 2*grid_max/grid_step and rejects a TRENTo matrix of a
# different size. Leaving these at their defaults (10.0/0.2 -> n_grid=100)
# against a TRENTo grid-max of 15.0 (-> 150x150) fails with
# "Input matrix shape (150, 150) does not match n_grid=100".
free_streaming_dict = {
    "tau": 1.000,
    "grid_max": 15.0,
    "grid_step": 0.2,
}

music_dict = {
    # Flat MUSIC input keys. Keep this dict FLAT: parameters_dict_master.py
    # writes music_dict verbatim into music_input_mode_2, so a nested sub-dict
    # lands in the input file as a literal Python dict that MUSIC ignores. An
    # earlier version of this file nested these under "smash"/"urqmd" and the
    # whole block -- including the EOS specification -- was silently inert.
    "X_grid_size_in_fm": 15.0,
    "Y_grid_size_in_fm": 15.0,
    "Grid_size_in_x": 150,
    "Grid_size_in_y": 150,
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
                "value": 5.08,
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
                "value": 5.08,
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