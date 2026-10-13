#!/usr/bin/env python3
"""
Design point 0 for TRENTo + free-streaming + MUSIC + UrQMD test batch.
"""

# control parameters
control_dict = {
    'initial_state_type': "TRENTo",
    'walltime': "10:00:00",
    'afterburner_type': "UrQMD",
    'save_hydro_surfaces': False,
    'save_UrQMD_files': False,
}

# No isobar_seed_file is declared on purpose. Nucleon positions are generated
# deterministically from isobars_conf_dict_*['isobar_samples']['seed_source']
# ("philox"), which needs no file. Only the legacy seed_source "file" reads a
# pool, and then this variable must be set to its path; generate one
# reproducibly with utilities/make_seed_pool.py.

# isobar-sample
isobars_conf_dict_target = {
    "isobar_samples": {
        "description": "Options for the isobar nucleon-position samples",
        "number_configs": {
            "description": "Number of configurations to be sampled.",
            "value": 1,
        },
        "number_nucleons": {
            "description": "Mass number A of the nuclei.",
            "value": 197,
        },
        "seed_source": {
            "description": ("Where nucleon seed rows come from: 'philox' generates "
                            "them deterministically from (master_seed, pool address); "
                            "'file' reads the HDF5 pool in seeds_file."),
            "value": "philox",
        },
        "master_seed": {
            "description": ("Master seed for the 'philox' source. Must never change "
                            "once events have been produced: every result depends on "
                            "it. Also recorded in EMULATOR_SWEEP_PLAN.md."),
            "value": 8675309,
        },
        "pool_modulus": {
            "description": ("Size of the virtual nucleus pool, 2**32. Event g maps to "
                            "addresses (2g)*K and (2g+1)*K mod this, with "
                            "K = 2654435761."),
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
    },
    "isobar_properties": {
        "description": "Nuclear properties of isobars to be sampled.",
        "isobar1": {
            "isobar_name": "Au",
            "WS_radius": {"description": "Woods-Saxon radius parameter R", "value": 6.38},
            "WS_diffusiveness": {"description": "Woods-Saxon diffusiveness parameter a", "value": 0.535},
            "beta_2": {"description": "Quadrupolar deformation", "value": 0.0},
            "gamma": {"description": "Quadrupolar deformation angle (rad)", "value": 0.0},
            "beta_3": {"description": "Octupolar deformation", "value": 0.0},
            "correlation_length": {"description": "Short-range correlation length (fm)", "value": 0.4},
            "correlation_strength": {"description": "Short-range correlation strength", "value": 0.0},
        },
    },
}

isobars_conf_dict_projectile = {
    "isobar_samples": {
        "description": "Options for the isobar nucleon-position samples",
        "number_configs": {
            "description": "Number of configurations to be sampled.",
            "value": 1,
        },
        "number_nucleons": {
            "description": "Mass number A of the nuclei.",
            "value": 197,
        },
        "seed_source": {
            "description": ("Where nucleon seed rows come from: 'philox' generates "
                            "them deterministically from (master_seed, pool address); "
                            "'file' reads the HDF5 pool in seeds_file."),
            "value": "philox",
        },
        "master_seed": {
            "description": ("Master seed for the 'philox' source. Must never change "
                            "once events have been produced: every result depends on "
                            "it. Also recorded in EMULATOR_SWEEP_PLAN.md."),
            "value": 8675309,
        },
        "pool_modulus": {
            "description": ("Size of the virtual nucleus pool, 2**32. Event g maps to "
                            "addresses (2g)*K and (2g+1)*K mod this, with "
                            "K = 2654435761."),
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
    },
    "isobar_properties": {
        "description": "Nuclear properties of isobars to be sampled.",
        "isobar1": {
            "isobar_name": "Au",
            "WS_radius": {"description": "Woods-Saxon radius parameter R", "value": 6.38},
            "WS_diffusiveness": {"description": "Woods-Saxon diffusiveness parameter a", "value": 0.535},
            "beta_2": {"description": "Quadrupolar deformation", "value": 0.0},
            "gamma": {"description": "Quadrupolar deformation angle (rad)", "value": 0.0},
            "beta_3": {"description": "Octupolar deformation", "value": 0.0},
            "correlation_length": {"description": "Short-range correlation length (fm)", "value": 0.4},
            "correlation_strength": {"description": "Short-range correlation strength", "value": 0.0},
        },
    },
}

trento_dict = {
    'type': "self",
    'projectile': ['nuclei_target/Au.hdf', 'nuclei_projectile/Au.hdf'],
    'number-events': 1,
    'quiet': False,
    'output': 'initial_condition',
    'reduced-thickness': 0.0,
    'fluctuation': 1.0,
    'nucleon-width': 0.5,
    'cross-section': 4.23,
    'normalization': 5.73,
    'b-min': 0,
    'b-max': 0.75,
    'grid-max': 10,
    'grid-step': 0.2,
}

free_streaming_dict = {
    'tau': 1.0,
    'grid_max': 10.0,
    'grid_step': 0.2,
}

music_dict = {
    'beastMode': 2,
    'Initial_profile': 92,   # type of initial condition 
                            # 9: IPGlasma (full Tmunu),
                            #   -- 91: e and u^\mu,
                            #   -- 92: e only,
                            #   -- 93: e, u^\mu, and pi^\munu
    's_factor': 1.0,      # normalization factor read in initial data file
    'Initial_time_tau_0': 1.0,  # starting time of the hydrodynamic evolution (fm/c)
    'Delta_Tau': 0.005,         # time step to use in the evolution [fm/c]
    'boost_invariant':  1,      # whether the simulation is boost-invariant
    'EOS_to_use': 9,            # type of the equation of state
                                # 9: hotQCD EOS with UrQMD
    # transport coefficients
    'quest_revert_strength': 1.0,          # the strength of the viscous regulation
    'Viscosity_Flag_Yes_1_No_0': 1,        # turn on viscosity in the evolution
    'Include_Shear_Visc_Yes_1_No_0': 1,    # include shear viscous effect
    'Shear_to_S_ratio': 0.120,             # value of \eta/s
    'T_dependent_Shear_to_S_ratio': 3,     # flag to use temperature dep. \eta/s(T)
    'shear_viscosity_3_eta_over_s_T_kink_in_GeV': 0.18,
    'shear_viscosity_3_eta_over_s_low_T_slope_in_GeV': -4,
    'shear_viscosity_3_eta_over_s_high_T_slope_in_GeV': 0,
    'shear_viscosity_3_eta_over_s_at_kink': 0.12,
    'Include_Bulk_Visc_Yes_1_No_0': 1,     # include bulk viscous effect
    'T_dependent_zeta_over_s': 10,         # parameterization of \zeta/s(T)
    'bulk_viscosity_10_max': 0.12,         # the peak value of \zeta/s(T)
    'bulk_viscosity_10_T_peak': 0.180,     # the peak temperature for \zeta/s(T)
    'bulk_viscosity_10_width_high': 0.12,
    'bulk_viscosity_10_width_low': 0.025,
    'Include_second_order_terms': 1,       # include second order non-linear coupling terms
    'Include_vorticity_terms': 0,          # include vorticity coupling terms

    # parameters for freeze out and Cooper-Frye
    'N_freeze_out': 1,
    'eps_switch': 0.18,
}

iss_dict = {
    'hydro_mode': 1,    # mode for reading in freeze out information 
    'include_deltaf_shear': 1,      # include delta f contribution from shear
    'include_deltaf_bulk': 1,       # include delta f contribution from bulk
    'bulk_deltaf_kind': 20,         # 21: relaxation time approximation (both shear and bulk)
    'sample_upto_desired_particle_number': 1,  # 1: flag to run sampling until desired
                                               # particle numbers is reached
    'number_of_particles_needed': 100000,      # number of hadrons to sample
    'local_charge_conservation': 0,  # flag to impose local charge conservation
    'global_momentum_conservation': 0,  # flag to impose GMC
}

hadronic_afterburner_toolkit_dict = {
    'event_buffer_size': 100000,
    'compute_correlation': 0,
    'flag_charge_dependence': 0,
    'compute_corr_rap_dep': 0,
    'resonance_weak_feed_down_flag': 1,
}
