#!/usr/bin/env python3
"""
    This script contains all the user modified parameters in
    the iEBE-MUSIC package.
"""

# control parameters
control_dict = {
    'initial_state_type': "TRENTo",
    'walltime': "10:00:00",  # walltime to run
    'afterburner_type': "SMASH",  # hadronic afterburner type
    'save_hydro_surfaces': False,  # flag to save hydro surfaces
    'save_UrQMD_files': True,  # flag to save UrQMD files
    }

# isobar-sample
isobars_conf_dict_target = {
    "isobar_samples": {
        "description": "Options for the isobar nucleon‑position samples",
        "number_configs": {
            "description": "Number of configurations to be sampled.",
            "value": 1,
        },
        "number_nucleons": {
            "description": "Mass number A of the nuclei.",
            "value": 197,
        },
        "seeds_file": {
            "description": "Input file with list of seeds for nucleon positions.",
            "filename": "nucleon-seeds.hdf",
        },
        "output_path": {
            "description": "Output directory where to save",
            "dirname": "nuclei_target",
        },
        "number_of_parallel_processes": {
            "description": (
                "Number of processes to compute in parallel. A value of -1 "
                "automatically selects the number of CPUs present."
            ),
            "value": -1,
        },
    },
    "isobar_properties": {
        "description": (
            "Nuclear properties of isobars to be sampled. "
            "Entries = isobar1, isobar2, ... Results are saved to isobar_name.hdf"
        ),
        "isobar1": {
            "isobar_name": "Au",
            "WS_radius": {"description": "Woods‑Saxon radius parameter R", "value": 6.38},
            "WS_diffusiveness": {"description": "Woods‑Saxon diffusiveness parameter a", "value": 0.535},
            "beta_2": {"description": "Quadrupolar deformation β₂", "value": 0},
            "gamma": {"description": "Quadrupolar deformation angle (rad)", "value": 0},
            "beta_3": {"description": "Octupolar deformation β₃", "value": 0},
            "correlation_length": {"description": "Radius of step‑function correlation C(r) (fm)", "value": 0.4},
            "correlation_strength": {"description": "Depth of correlation (≥ −1)", "value": -1},
        },
    },
}


isobars_conf_dict_projectile = {
    "isobar_samples": {
        "description": "Options for the isobar nucleon‑position samples",
        "number_configs": {
            "description": "Number of configurations to be sampled.",
            "value": 1,
        },
        "number_nucleons": {
            "description": "Mass number A of the nuclei.",
            "value": 197,
        },
        "seeds_file": {
            "description": "Input file with list of seeds for nucleon positions.",
            "filename": "nucleon-seeds.hdf",
        },
        "output_path": {
            "description": "Output directory where to save",
            "dirname": "nuclei_projectile",
        },
        "number_of_parallel_processes": {
            "description": (
                "Number of processes to compute in parallel. A value of -1 "
                "automatically selects the number of CPUs present."
            ),
            "value": -1,
        },
    },
    "isobar_properties": {
        "description": (
            "Nuclear properties of isobars to be sampled. "
            "Entries = isobar1, isobar2, ... Results are saved to isobar_name.hdf"
        ),
        "isobar1": {
            "isobar_name": "Au",
            "WS_radius": {"description": "Woods‑Saxon radius parameter R", "value": 6.38},
            "WS_diffusiveness": {"description": "Woods‑Saxon diffusiveness parameter a", "value": 0.535},
            "beta_2": {"description": "Quadrupolar deformation β₂", "value": 0},
            "gamma": {"description": "Quadrupolar deformation angle (rad)", "value": 0},
            "beta_3": {"description": "Octupolar deformation β₃", "value": 0},
            "correlation_length": {"description": "Radius of step‑function correlation C(r) (fm)", "value": 0.4},
            "correlation_strength": {"description": "Depth of correlation (≥ −1)", "value": -1},
        },
    },
}


# TRENTo 
trento_dict = {
    'type': "self", # self: generate initial condition on the fly #'database_name?'
    'projectile': ['nuclei_target/Au.hdf', 'nuclei_projectile/Au.hdf'], # projectile nucleus name
    #'projectile: "Pb", # projectile/target nucleus name
    'number-events': 1, # number of events
    'quiet': True, ###
    'output': 'test_path.dat',
    'reduced-thickness': 0, ###
    'fluctuation': 1 ,      # gamma fluctuations
    'nucleon-width': 0.5,    # nucleon width
    'cross-section': 4.23,   # inelastic nucleon-nucleon cross-section
    'normalization': 15,      # normalization
    'b-min': 0,              # minimum b
    'b-max': 0,             # maximum b
    'grid-max': 10,          #####
    'grid-step': 0.2,        #####
}

# MUSIC
music_dict = {
    'Initial_profile': 92,  # type of initial condition 
    # 13: dynamical initialization (3dMCGlauber_dynamical)
    #   -- 131: 3dMCGlauber with zero nucleus thickness
    's_factor': 1.000,  # normalization factor read in initial data file
    'Initial_time_tau_0':
        0.2,  # starting time of the hydrodynamic evolution (fm/c)
    'Delta_Tau': 0.005,  # time step to use in the evolution [fm/c]
    'boost_invariant': 1,  # whether the simulation is boost-invariant
    'EOS_to_use': 9,  # type of the equation of state
    # 9: hotQCD EOS with UrQMD
    # transport coefficients
    'Eta_grid_size': 1.0,
    'Grid_size_in_eta': 1.0,
    'X_grid_size_in_fm': 18.0,
    'Y_grid_size_in_fm': 18.0,
    'Grid_size_in_x': 90,  # number of the grid points in x direction
    'Grid_size_in_y': 90, 
    'quest_revert_strength': 1.0,  # the strength of the viscous regulation
    'Viscosity_Flag_Yes_1_No_0': 1,  # turn on viscosity in the evolution
    'Include_Shear_Visc_Yes_1_No_0': 1,  # include shear viscous effect
    'Shear_to_S_ratio': 0.12,  # value of \eta/s
    'T_dependent_Shear_to_S_ratio': 0,  # flag to use temperature dep. \eta/s(T)
    'Include_Bulk_Visc_Yes_1_No_0': 1,  # include bulk viscous effect
    'T_dependent_zeta_over_s': 8,  # parameterization of \zeta/s(T)
    'Include_second_order_terms':
        1,  # include second order non-linear coupling terms
    'Include_vorticity_terms': 0,  # include vorticity coupling terms

    # parameters for freeze out and Cooper-Frye
    'N_freeze_out': 1,
    'eps_freeze_max': 0.18,
    'eps_freeze_min': 0.18,
}

# iSS
iss_dict = {
    'hydro_mode': 2,  # mode for reading in freeze out information 
    'include_deltaf_shear': 1,  # include delta f contribution from shear
    'include_deltaf_bulk': 0,  # include delta f contribution from bulk
    'include_deltaf_diffusion':
        0,  # include delta f contribution from diffusion
    'sample_upto_desired_particle_number':
        1,  # 1: flag to run sampling until desired
    # particle numbers is reached
    'number_of_particles_needed': 100000,  # number of hadrons to sample
    'local_charge_conservation': 0,  # flag to impose local charge conservation
    'global_momentum_conservation': 0,  # flag to impose GMC
}

smash_config_dict = {
    "Logging": {
        "default": "INFO",
    },
    "General": {
        "Modus": "List",
        "Time_Step_Mode": "None",
        "Delta_Time": 0.1,
        "End_Time": 100.0,
        "Randomseed": -1,
        "Nevents": 1,
    },
    "Output": {
        "Output_Interval": 10.0,
        "Particles": {
            "Format": ["Binary"], # Options: "ASCII", "Binary", "Oscar2013"
            "Extended": True,
            "Quantities": [ "t","x","y","z",
              "mass","p0","px","py","pz",
              "pdg","ID","charge",
              "ncoll","form_time","xsecfac",
              "proc_id_origin","proc_type_origin","time_last_coll",
              "pdg_mother1","pdg_mother2",
              "baryon_number","strangeness"
             ],
        },
    },
    "Modi": {
        "List": {
            "File_Directory": "list",
            "File_Prefix": "OSCAR.DAT",
            "Shift_Id": 0,
        },
    },
}

# hadronic afterburner toolkit
hadronic_afterburner_toolkit_dict = {
    'event_buffer_size': 100000,  # the number of events read in at once
    'compute_correlation': 0,  # flag to compute correlation function
    'flag_charge_dependence':
        0,  # flag to compute charge dependence correlation
    'compute_corr_rap_dep':
        0,  # flag to compute the rapidity dependent multi-particle correlation
    'resonance_weak_feed_down_flag': 0,  # include weak feed down contribution
}
