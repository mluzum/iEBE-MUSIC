#!/usr/bin/env python3
"""
Design point 0 for TRENTo + free-streaming + MUSIC + UrQMD test batch.
"""

# control parameters
control_dict = {
    'initial_state_type': "TRENTo",
    'walltime': "10:00:00",
    'afterburner_type': "decay",
    'save_hydro_surfaces': False,
    'save_UrQMD_files': False,
    # Each hydro surface is particlized once per delta f model, with the same
    # seeds; results in spvn_results_<id>/deltaf_<name>.  Grad22 and CE are the
    # linear 22-moment and Chapman-Enskog delta f (clamped to [-1, 1] by the
    # sampler); PTB is the positive-definite modified equilibrium
    # (codes/patches/iSS_PTB_deltaf.patch).
    'deltaf_models': {
        'Grad22': {'deltaf_model': 0, 'bulk_deltaf_kind': 20},
        'CE': {'deltaf_model': 0, 'bulk_deltaf_kind': 21},
        'PTB': {'deltaf_model': 1, 'bulk_deltaf_kind': 21},
    },
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
            "value": 96,
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
            "isobar_name": "target",
            "WS_radius": {"description": "Woods-Saxon radius parameter R", "value": 6.38},
            "WS_diffusiveness": {"description": "Woods-Saxon diffusiveness parameter a", "value": 0.535},
            "beta_2": {"description": "Quadrupolar deformation", "value": 0.0},
            "gamma": {"description": "Triaxiality angle gamma_lit (rad), Bohr-Mottelson convention: 0 = axial prolate, pi/6 = max triaxial, pi/3 = axial oblate", "value": 0.0},
            "beta_3": {"description": "Octupolar deformation", "value": 0.0},
            "sigma_beta_2": {"description": "Event-by-event width of beta_2; 0 fixes the shape", "value": 0.0},
            "sigma_beta_3": {"description": "Event-by-event width of beta_3; 0 fixes the shape", "value": 0.0},
            "sigma_gamma": {"description": "Event-by-event width of gamma_lit (rad); folded onto [0, pi/3], 0 fixes gamma", "value": 0.0},
            "beta_max": {"description": "Upper bound on quadrupole strength (Option B); uniform wedge prior is beta_max/2 with sd beta_max/sqrt(12)", "value": 0.5},
            "shape_distribution": {"description": "How the per-event shape is drawn: 'wedge' = Option B bounded Beta on (beta, gamma_lit); 'plane' = Gaussian in the (beta20, beta22) deformation plane about the mean tensor, folded per draw, which can express zero mean deformation with real shape fluctuations", "value": "plane"},
            "sigma_plane": {"description": "Width of the plane-form Gaussian in (beta20, beta22); 0 is exactly rigid, at any mean including beta_2 = 0", "value": 0.0},
            "plane_anisotropy": {"description": "Splits sigma_plane into two plane widths with fixed geometric mean; 0 is isotropic, positive favours prolate/oblate excursions, negative favours triaxial wandering", "value": 0.0},
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
            "value": 96,
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
            "isobar_name": "projectile",
            "WS_radius": {"description": "Woods-Saxon radius parameter R", "value": 6.38},
            "WS_diffusiveness": {"description": "Woods-Saxon diffusiveness parameter a", "value": 0.535},
            "beta_2": {"description": "Quadrupolar deformation", "value": 0.0},
            "gamma": {"description": "Triaxiality angle gamma_lit (rad), Bohr-Mottelson convention: 0 = axial prolate, pi/6 = max triaxial, pi/3 = axial oblate", "value": 0.0},
            "beta_3": {"description": "Octupolar deformation", "value": 0.0},
            "sigma_beta_2": {"description": "Event-by-event width of beta_2; 0 fixes the shape", "value": 0.0},
            "sigma_beta_3": {"description": "Event-by-event width of beta_3; 0 fixes the shape", "value": 0.0},
            "sigma_gamma": {"description": "Event-by-event width of gamma_lit (rad); folded onto [0, pi/3], 0 fixes gamma", "value": 0.0},
            "beta_max": {"description": "Upper bound on quadrupole strength (Option B); uniform wedge prior is beta_max/2 with sd beta_max/sqrt(12)", "value": 0.5},
            "shape_distribution": {"description": "How the per-event shape is drawn: 'wedge' = Option B bounded Beta on (beta, gamma_lit); 'plane' = Gaussian in the (beta20, beta22) deformation plane about the mean tensor, folded per draw, which can express zero mean deformation with real shape fluctuations", "value": "plane"},
            "sigma_plane": {"description": "Width of the plane-form Gaussian in (beta20, beta22); 0 is exactly rigid, at any mean including beta_2 = 0", "value": 0.0},
            "plane_anisotropy": {"description": "Splits sigma_plane into two plane widths with fixed geometric mean; 0 is isotropic, positive favours prolate/oblate excursions, negative favours triaxial wandering", "value": 0.0},
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
    'output': 'initial_condition',
    'reduced-thickness': 0.0,
    'fluctuation': 1.0,
    'nucleon-width': 0.5,
    'cross-section': 4.23,
    'normalization': 5.73,
    'b-min': 0,
    'b-max': 0.75,
    'grid-max': 15.0,
    'grid-step': 0.2,
}

free_streaming_dict = {
    'tau': 1.0,
    'grid_max': 15.0,
    'grid_step': 0.2,
}

music_dict = {
    'beastMode': 2,
    'Initial_profile': 9,    # type of initial condition
                            # 9: full T^munu (the free-streaming e, u^mu,
                            #    pi^munu and Pi = e/3 - P_eos); 92 dropped the
                            #    flow and ~17% of the energy (first campaigns)
                            #   -- 91: e and u^\mu,
                            #   -- 92: e only,
                            #   -- 93: e, u^\mu, and pi^\munu
    's_factor': 1.0,      # normalization factor read in initial data file
    'Initial_time_tau_0': 1.0,  # starting time of the hydrodynamic evolution (fm/c)
    'Delta_Tau': 0.005,         # time step to use in the evolution [fm/c]
    'X_grid_size_in_fm': 30.0,
    'Y_grid_size_in_fm': 30.0,
    'Grid_size_in_x': 150,
    'Grid_size_in_y': 150,
    'boost_invariant':  1,      # whether the simulation is boost-invariant
    'EOS_to_use': 9,            # type of the equation of state
                                # 9: hotQCD EOS with UrQMD
    # transport coefficients
    'quest_revert_strength': 1.0,          # the strength of the viscous regulation
    'Viscosity_Flag_Yes_1_No_0': 1,        # turn on viscosity in the evolution
    'Include_Shear_Visc_Yes_1_No_0': 1,    # include shear viscous effect
    'T_dependent_Shear_to_S_ratio': 3,     # flag to use temperature dep. \eta/s(T)
    'shear_viscosity_3_eta_over_s_T_kink_in_GeV': 0.18,
    'shear_viscosity_3_eta_over_s_low_T_slope_in_GeV': -1.0,
    'shear_viscosity_3_eta_over_s_high_T_slope_in_GeV': 0.0,
    'shear_viscosity_3_eta_over_s_at_kink': 0.12,
    'shear_relax_time_factor': 5.0,        # b_pi
    'Include_Bulk_Visc_Yes_1_No_0': 1,     # include bulk viscous effect
    'T_dependent_zeta_over_s': 3,          # parameterization of \zeta/s(T)
    'bulk_viscosity_3_zeta_over_s_max': 0.1,           # the peak value of \zeta/s(T)
    'bulk_viscosity_3_zeta_over_s_T_peak_in_GeV': 0.18,
    'bulk_viscosity_3_zeta_over_s_width_in_GeV': 0.05,
    'bulk_viscosity_3_zeta_over_s_lambda_asymm': 0.0,
    'Include_second_order_terms': 1,       # include second order non-linear coupling terms
    'Include_vorticity_terms': 0,          # include vorticity coupling terms

    # parameters for freeze out and Cooper-Frye
    'use_eps_for_freeze_out': 0,           # 0: use temperature, 1: use energy density
    'T_freeze': 0.12,
    'N_freeze_out': 1,
}

iss_dict = {
    'hydro_mode': 1,    # mode for reading in freeze out information 
    'include_deltaf_shear': 1,      # include delta f contribution from shear
    'include_deltaf_bulk': 1,       # include delta f contribution from bulk
    'bulk_deltaf_kind': 21,         # 21: relaxation time approximation (both shear and bulk)
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
    # Charged particles (particle_monval=9999) use this as -1 < eta < 1;
    # identified particles use it as -1 < y < 1 because rap_type=1.
    # pT bins for the identified-particle tables: edges
    # pT_min + i (pT_max - pT_min)/npT, i.e. 0.05 GeV bins on 0-5 GeV, so every
    # experimental cut in use (0.15, 0.2, 0.3, 0.5, 2, 3, 5 GeV) is an edge.
    # (The first campaigns had 0.2-2.0 GeV in 41 bins of 0.0439 GeV.)
    'pT_min': 0.0,
    'pT_max': 5.0,
    'npT': 100,
    'rap_min': -1.0,
    'rap_max': 1.0,
    'rap_type': 1,
    'vn_rapidity_dis_pT_min': 0.2,
    'vn_rapidity_dis_pT_max': 2.0,
}