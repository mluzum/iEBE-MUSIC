#!/usr/bin/env python3
"""
Design point 661 for TRENTo + free-streaming + MUSIC + UrQMD test batch.
"""

# control parameters

control_dict = {
    'initial_state_type': "TRENTo",
    'walltime': "20:00:00",
    'afterburner_type': "decay",
    'save_hydro_surfaces': False,
    'save_UrQMD_files': False,
}

# No isobar_seed_file: nucleon positions are generated deterministically
# from isobars_conf_dict_*['isobar_samples']['seed_source'] ("philox").
# Only the legacy seed_source "file" reads a pool; generate one with
# utilities/make_seed_pool.py and set isobar_seed_file to its path.

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
            "value": 76,
        },
        "seed_source": {
            "description": "Nucleon seeds: philox (deterministic from master_seed and pool address) or file (HDF5 pool).",
            "value": "philox",
        },
        "master_seed": {
            "description": "Master seed for the philox source. Must never change once events exist; recorded in EMULATOR_SWEEP_PLAN.md.",
            "value": 8675309,
        },
        "pool_modulus": {
            "description": "Size of the virtual nucleus pool, 2**32. Event g maps to addresses (2g)*2654435761 and (2g+1)*2654435761 mod this.",
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
            "isobar_name": "target",
            "WS_radius": {"description": "Woods-Saxon radius parameter R", "value": 4.986742817},
            "WS_diffusiveness": {"description": "Woods-Saxon diffusiveness parameter a", "value": 0.5580608829},
            "beta_2": {"description": "Quadrupolar deformation", "value": 0.2343114309},
            "gamma": {"description": "Quadrupolar deformation angle (rad); design matrix supplies degrees", "value": 0.829316220912059},
            "beta_3": {"description": "Octupolar deformation", "value": 0.1815434478},
            "sigma_beta_2": {"description": "Event-by-event width of beta_2; 0 fixes the shape", "value": 0.0},
            "sigma_beta_3": {"description": "Event-by-event width of beta_3; 0 fixes the shape", "value": 0.04478293188},
            "sigma_gamma": {"description": "Event-by-event width of gamma_lit (rad); folded onto [0, pi/3], 0 fixes gamma", "value": 0.0},
            "beta_max": {"description": "Upper bound on quadrupole strength (Option B); uniform wedge prior is beta_max/2 with sd beta_max/sqrt(12)", "value": 0.5},
            "shape_distribution": {"description": "Per-event shape draw: wedge (Option B) or plane (Gaussian in the deformation plane, folded per draw)", "value": "plane"},
            "sigma_plane": {"description": "Width of the plane-form Gaussian; 0 is rigid, and works at beta_2 = 0", "value": 0.0631436362},
            "plane_anisotropy": {"description": "Splits sigma_plane with fixed geometric mean; 0 is isotropic, positive favours prolate/oblate, negative favours triaxial", "value": 0.0},
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
            "value": 76,
        },
        "seed_source": {
            "description": "Nucleon seeds: philox (deterministic from master_seed and pool address) or file (HDF5 pool).",
            "value": "philox",
        },
        "master_seed": {
            "description": "Master seed for the philox source. Must never change once events exist; recorded in EMULATOR_SWEEP_PLAN.md.",
            "value": 8675309,
        },
        "pool_modulus": {
            "description": "Size of the virtual nucleus pool, 2**32. Event g maps to addresses (2g)*2654435761 and (2g+1)*2654435761 mod this.",
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
            "isobar_name": "projectile",
            "WS_radius": {"description": "Woods-Saxon radius parameter R", "value": 4.986742817},
            "WS_diffusiveness": {"description": "Woods-Saxon diffusiveness parameter a", "value": 0.5580608829},
            "beta_2": {"description": "Quadrupolar deformation", "value": 0.2343114309},
            "gamma": {"description": "Quadrupolar deformation angle (rad); design matrix supplies degrees", "value": 0.829316220912059},
            "beta_3": {"description": "Octupolar deformation", "value": 0.1815434478},
            "sigma_beta_2": {"description": "Event-by-event width of beta_2; 0 fixes the shape", "value": 0.0},
            "sigma_beta_3": {"description": "Event-by-event width of beta_3; 0 fixes the shape", "value": 0.04478293188},
            "sigma_gamma": {"description": "Event-by-event width of gamma_lit (rad); folded onto [0, pi/3], 0 fixes gamma", "value": 0.0},
            "beta_max": {"description": "Upper bound on quadrupole strength (Option B); uniform wedge prior is beta_max/2 with sd beta_max/sqrt(12)", "value": 0.5},
            "shape_distribution": {"description": "Per-event shape draw: wedge (Option B) or plane (Gaussian in the deformation plane, folded per draw)", "value": "plane"},
            "sigma_plane": {"description": "Width of the plane-form Gaussian; 0 is rigid, and works at beta_2 = 0", "value": 0.0631436362},
            "plane_anisotropy": {"description": "Splits sigma_plane with fixed geometric mean; 0 is isotropic, positive favours prolate/oblate, negative favours triaxial", "value": 0.0},
            "correlation_length": {"description": "Short-range correlation length (fm)", "value": 0.4},
            "correlation_strength": {"description": "Short-range correlation strength", "value": 0.0},
        },
    },
}

trento_dict = {
    'type': "self",
    'projectile': ['nuclei_target/target.hdf', 'nuclei_projectile/projectile.hdf'],
    'number-events': 1,
    'quiet': False,
    'output': "initial_condition",
    'reduced-thickness': 0.4747825938,
    'fluctuation': 1.5171757159569919,
    'nucleon-width': 0.8259807853,
    'cross-section': 4.23,
    'normalization': 19.98203331,
    'b-min': 0,
    'b-max': 11.888503687350251,
    'grid-max': 15.0,
    'grid-step': 0.2,
}

free_streaming_dict = {
    'tau': 0.3373354782,
    'grid_max': 15.0,
    'grid_step': 0.2,
}

music_dict = {
    'beastMode': 2,
    'Initial_profile': 92,
    's_factor': 1.0,
    'Initial_time_tau_0': 0.3373354782,
    'Delta_Tau': 0.005,
    'X_grid_size_in_fm': 30.0,
    'Y_grid_size_in_fm': 30.0,
    'Grid_size_in_x': 150,
    'Grid_size_in_y': 150,
    'boost_invariant': 1,
    'EOS_to_use': 9,
    'quest_revert_strength': 1.0,
    'Viscosity_Flag_Yes_1_No_0': 1,
    'Include_Shear_Visc_Yes_1_No_0': 1,
    'T_dependent_Shear_to_S_ratio': 3,
    'shear_viscosity_3_eta_over_s_T_kink_in_GeV': 0.2935399857,
    'shear_viscosity_3_eta_over_s_low_T_slope_in_GeV': -1.070301716,
    'shear_viscosity_3_eta_over_s_high_T_slope_in_GeV': 1.615052442,
    'shear_viscosity_3_eta_over_s_at_kink': 0.09223051519,
    'shear_relax_time_factor': 5.0,
    'Include_Bulk_Visc_Yes_1_No_0': 1,
    'T_dependent_zeta_over_s': 3,
    'bulk_viscosity_3_zeta_over_s_max': 0.01419442689,
    'bulk_viscosity_3_zeta_over_s_T_peak_in_GeV': 0.160722225,
    'bulk_viscosity_3_zeta_over_s_width_in_GeV': 0.05943251871,
    'bulk_viscosity_3_zeta_over_s_lambda_asymm': 0.0,
    'Include_second_order_terms': 1,
    'Include_vorticity_terms': 0,
    'use_eps_for_freeze_out': 0,
    'T_freeze': 0.1357756838,
    'N_freeze_out': 1,
}

iss_dict = {
    'hydro_mode': 1,
    'include_deltaf_shear': 1,
    'include_deltaf_bulk': 1,
    'bulk_deltaf_kind': 21,
    'sample_upto_desired_particle_number': 1,
    'number_of_particles_needed': 100000,
    'local_charge_conservation': 0,
    'global_momentum_conservation': 0,
}

hadronic_afterburner_toolkit_dict = {
    'event_buffer_size': 100000,
    'compute_correlation': 0,
    'flag_charge_dependence': 0,
    'compute_corr_rap_dep': 0,
    'resonance_weak_feed_down_flag': 1,
    'pT_min': 0.2,
    'pT_max': 2.0,
    'rap_min': -1.0,
    'rap_max': 1.0,
    'rap_type': 1,
    'vn_rapidity_dis_pT_min': 0.2,
    'vn_rapidity_dis_pT_max': 2.0,
}

