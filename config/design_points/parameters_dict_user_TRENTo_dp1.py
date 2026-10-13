#!/usr/bin/env python3
"""
Design point 1 for TRENTo + free-streaming + MUSIC + UrQMD test batch.
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
            "gamma": {"description": "Triaxiality angle gamma_lit (rad), Bohr-Mottelson convention: 0 = axial prolate, pi/6 = max triaxial, pi/3 = axial oblate", "value": 0.0},
            "beta_3": {"description": "Octupolar deformation", "value": 0.0},
            "sigma_beta_2": {"description": "Event-by-event width of beta_2; 0 fixes the shape", "value": 0.0},
            "sigma_beta_3": {"description": "Event-by-event width of beta_3; 0 fixes the shape", "value": 0.0},
            "sigma_gamma": {"description": "Event-by-event width of gamma_lit (rad); folded onto [0, pi/3], 0 fixes gamma", "value": 0.0},
            "beta_max": {"description": "Upper bound on quadrupole strength (Option B); uniform wedge prior is beta_max/2 with sd beta_max/sqrt(12)", "value": 0.5},
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
            "gamma": {"description": "Triaxiality angle gamma_lit (rad), Bohr-Mottelson convention: 0 = axial prolate, pi/6 = max triaxial, pi/3 = axial oblate", "value": 0.0},
            "beta_3": {"description": "Octupolar deformation", "value": 0.0},
            "sigma_beta_2": {"description": "Event-by-event width of beta_2; 0 fixes the shape", "value": 0.0},
            "sigma_beta_3": {"description": "Event-by-event width of beta_3; 0 fixes the shape", "value": 0.0},
            "sigma_gamma": {"description": "Event-by-event width of gamma_lit (rad); folded onto [0, pi/3], 0 fixes gamma", "value": 0.0},
            "beta_max": {"description": "Upper bound on quadrupole strength (Option B); uniform wedge prior is beta_max/2 with sd beta_max/sqrt(12)", "value": 0.5},
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
    'reduced-thickness': -0.2,
    'fluctuation': 1.4,
    'nucleon-width': 0.8,
    'cross-section': 4.23,
    'normalization': 20.0,
    'b-min': 0,
    'b-max': 3,
    'grid-max': 10,
    'grid-step': 0.2,
}

free_streaming_dict = {
    'tau': 0.8,
    'grid_max': 10.0,
    'grid_step': 0.2,
}

music_dict = {
    'Initial_profile': 92,
    's_factor': 1.000,
    'Initial_time_tau_0': 0.2,
    'Delta_Tau': 0.005,
    'boost_invariant': 1,
    'EOS_to_use': 9,
    'Eta_grid_size': 1.0,
    'Grid_size_in_eta': 1.0,
    'X_grid_size_in_fm': 18.0,
    'Y_grid_size_in_fm': 18.0,
    'Grid_size_in_x': 90,
    'Grid_size_in_y': 90,
    'quest_revert_strength': 1.0,
    'Viscosity_Flag_Yes_1_No_0': 1,
    'Include_Shear_Visc_Yes_1_No_0': 1,
    'Shear_to_S_ratio': 0.16,
    'T_dependent_Shear_to_S_ratio': 0,
    'Include_Bulk_Visc_Yes_1_No_0': 1,
    'T_dependent_zeta_over_s': 8,
    'Include_second_order_terms': 1,
    'Include_vorticity_terms': 0,
    'N_freeze_out': 1,
    'eps_freeze_max': 0.18,
    'eps_freeze_min': 0.18,
}

iss_dict = {
    'hydro_mode': 2,
    'include_deltaf_shear': 1,
    'include_deltaf_bulk': 1,
    'bulk_deltaf_kind': 1,
    'include_deltaf_diffusion': 0,
    'sample_upto_desired_particle_number': 1,
    'number_of_particles_needed': 50000,
    'local_charge_conservation': 0,
    'global_momentum_conservation': 0,
    'output_samples_into_files': 1,
    'store_samples_in_memory': 0,
}

hadronic_afterburner_toolkit_dict = {
    'event_buffer_size': 100000,
    'compute_correlation': 0,
    'flag_charge_dependence': 0,
    'compute_corr_rap_dep': 0,
    'resonance_weak_feed_down_flag': 1,
}
