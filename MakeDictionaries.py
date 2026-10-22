#!/usr/bin/env python3
"""Generate one parameter dictionary per design-point row.

The script reads the design matrix in the repository root (default: ./design),
uses the realistic TRENTo template as the base configuration, and writes one
folder per design point named DesignPoint1, DesignPoint2, ... under the current
working directory. Each folder contains a generated Python parameter file named
parameter_dictionary_design_point_{k}.py with k = 1, 2, 3, ...

Usage:
    python3 MakeDictionaries.py
    python3 MakeDictionaries.py design
    python3 MakeDictionaries.py --design /path/to/design --start-design-point 1 --end-design-point 250

Design-matrix columns (csv.DictReader; every one is required unless noted):

    WS_radius, WS_diffusiveness, beta_2, gamma, beta_3
        Woods-Saxon radius [fm], diffusiveness [fm], quadrupole deformation,
        triaxiality [deg], octupole deformation (magnitude).
    sigma_k            standard deviation of the gamma-distributed nucleon
                       weight gamma_i (arXiv:2011.01430's fluctuation axis).
                       Converted here to TRENTo's `fluctuation` k = 1/sigma_k^2.
                       A `fluctuation` column (k itself) is still accepted and
                       used only when `sigma_k` is absent.
    nucleon-width      w [fm]
    normalization      optional; TRENTo energy-deposition normalization, defaults
                       to the template's 5.73
    reduced-thickness  TRENTo reduced thickness
    tau                tau_0 and the free-streaming time [fm/c]
    beta_max           optional; support of the bounded beta_2 draw, defaults to
                       the template value or 0.5 if the template has none
    number_nucleons    optional; mass number A, defaults to the template value
    shear_viscosity_3_eta_over_s_T_kink_in_GeV, ..._low_T_slope_in_GeV,
    ..._high_T_slope_in_GeV, ..._at_kink
                       T_eta, a_low, a_high, (eta/s)_kink
    shear_relax_time_factor    b_pi (fixed in the current design)
    bulk_viscosity_3_max, bulk_viscosity_3_T_peak_in_GeV,
    bulk_viscosity_3_width_in_GeV, bulk_viscosity_3_lambda_asymm
                       (zeta/s)_max, T_zeta, w_zeta, lambda_zeta
    T_freeze           freeze-out temperature [GeV]
"""

from __future__ import annotations

import argparse
import csv
import math
import pprint
from pathlib import Path
import runpy


DEFAULT_DESIGN_NAME = "design"


def default_template_config() -> dict:
    """Return a built-in realistic template configuration.

    The script can run in arbitrary directories without a repo checkout because the
    default behavior is based on this embedded template instead of a repository file.
    """
    return {
        "control_dict": {
            "initial_state_type": "TRENTo",
            "walltime": "20:00:00",
            "afterburner_type": "UrQMD",
            "save_hydro_surfaces": False,
            "save_UrQMD_files": False,
        },
        "isobars_conf_dict_target": {
            "isobar_samples": {
                "description": "Options for the isobar nucleon-position samples",
                "number_configs": {"description": "Number of configurations to be sampled.", "value": 1},
                "number_nucleons": {"description": "Mass number A of the nuclei.", "value": 96},
                "seed_source": {"description": "Nucleon seeds: 'philox' (deterministic, no file) or 'file' (HDF5 pool).", "value": "philox"},
                "master_seed": {"description": "Master seed for the philox source. Never change once events exist.", "value": 8675309},
                "pool_modulus": {"description": "Size of the virtual nucleus pool, 2**32.", "value": 4294967296},
                "output_path": {"description": "Output directory where to save", "dirname": "nuclei_target"},
                "number_of_parallel_processes": {"description": "Number of processes to compute in parallel.", "value": -1},
            },
            "isobar_properties": {
                "description": "Nuclear properties of isobars to be sampled.",
                "isobar1": {
                    "isobar_name": "target",
                    "WS_radius": {"description": "Woods-Saxon radius parameter R", "value": 6.38},
                    "WS_diffusiveness": {"description": "Woods-Saxon diffusiveness parameter a", "value": 0.535},
                    "beta_2": {"description": "Quadrupolar deformation", "value": 0.0},
                    "gamma": {"description": "Quadrupolar deformation angle (rad)", "value": 0.0},
                    "beta_3": {"description": "Octupolar deformation", "value": 0.0},
                    "correlation_length": {"description": "Short-range correlation length (fm)", "value": 0.4},
                    "correlation_strength": {"description": "Short-range correlation strength", "value": 0.0},
                },
            },
        },
        "isobars_conf_dict_projectile": {
            "isobar_samples": {
                "description": "Options for the isobar nucleon-position samples",
                "number_configs": {"description": "Number of configurations to be sampled.", "value": 1},
                "number_nucleons": {"description": "Mass number A of the nuclei.", "value": 96},
                "seed_source": {"description": "Nucleon seeds: 'philox' (deterministic, no file) or 'file' (HDF5 pool).", "value": "philox"},
                "master_seed": {"description": "Master seed for the philox source. Never change once events exist.", "value": 8675309},
                "pool_modulus": {"description": "Size of the virtual nucleus pool, 2**32.", "value": 4294967296},
                "output_path": {"description": "Output directory where to save", "dirname": "nuclei_projectile"},
                "number_of_parallel_processes": {"description": "Number of processes to compute in parallel.", "value": -1},
            },
            "isobar_properties": {
                "description": "Nuclear properties of isobars to be sampled.",
                "isobar1": {
                    "isobar_name": "projectile",
                    "WS_radius": {"description": "Woods-Saxon radius parameter R", "value": 6.38},
                    "WS_diffusiveness": {"description": "Woods-Saxon diffusiveness parameter a", "value": 0.535},
                    "beta_2": {"description": "Quadrupolar deformation", "value": 0.0},
                    "gamma": {"description": "Quadrupolar deformation angle (rad)", "value": 0.0},
                    "beta_3": {"description": "Octupolar deformation", "value": 0.0},
                    "correlation_length": {"description": "Short-range correlation length (fm)", "value": 0.4},
                    "correlation_strength": {"description": "Short-range correlation strength", "value": 0.0},
                },
            },
        },
        "trento_dict": {
            "type": "self",
            "projectile": ["nuclei_target/target.hdf", "nuclei_projectile/projectile.hdf"],
            "number-events": 1,
            "quiet": False,
            "output": "initial_condition",
            "reduced-thickness": 0.0,
            # k, the gamma shape parameter of the nucleon weights. It is derived
            # from the design matrix's sigma_k as k = 1/sigma_k**2; the value
            # here is only a placeholder for a bare template run.
            "fluctuation": 1.0,
            "nucleon-width": 0.5,
            "cross-section": 4.23,
            "normalization": 5.73,
            "b-min": 0,
            "b-max": 0.75,
            "grid-max": 15.0,
            "grid-step": 0.2,
        },
        "free_streaming_dict": {
            "tau": 1.0,
            "grid_max": 15.0,
            "grid_step": 0.2,
        },
        "music_dict": {
            "beastMode": 2,
            "Initial_profile": 92,
            "s_factor": 1.0,
            "Initial_time_tau_0": 1.0,
            "Delta_Tau": 0.005,
            "X_grid_size_in_fm": 30.0,
            "Y_grid_size_in_fm": 30.0,
            "Grid_size_in_x": 150,
            "Grid_size_in_y": 150,
            "boost_invariant": 1,
            "EOS_to_use": 9,
            "quest_revert_strength": 1.0,
            "Viscosity_Flag_Yes_1_No_0": 1,
            "Include_Shear_Visc_Yes_1_No_0": 1,
            "T_dependent_Shear_to_S_ratio": 3,
            "shear_viscosity_3_eta_over_s_T_kink_in_GeV": 0.18,
            "shear_viscosity_3_eta_over_s_low_T_slope_in_GeV": -1.0,
            "shear_viscosity_3_eta_over_s_high_T_slope_in_GeV": 0.0,
            "shear_viscosity_3_eta_over_s_at_kink": 0.12,
            "shear_relax_time_factor": 5.0,
            "Include_Bulk_Visc_Yes_1_No_0": 1,
            "T_dependent_zeta_over_s": 3,
            "bulk_viscosity_3_max": 0.1,
            "bulk_viscosity_3_T_peak_in_GeV": 0.18,
            "bulk_viscosity_3_width_in_GeV": 0.05,
            "bulk_viscosity_3_lambda_asymm": 0.0,
            "Include_second_order_terms": 1,
            "Include_vorticity_terms": 0,
            "use_eps_for_freeze_out": 0,
            "T_freeze": 0.12,
            "N_freeze_out": 1,
        },
        "iss_dict": {
            "hydro_mode": 1,
            "include_deltaf_shear": 1,
            "include_deltaf_bulk": 1,
            "bulk_deltaf_kind": 21,
            "sample_upto_desired_particle_number": 1,
            "number_of_particles_needed": 100000,
            "local_charge_conservation": 0,
            "global_momentum_conservation": 0,
        },
        "hadronic_afterburner_toolkit_dict": {
            "event_buffer_size": 100000,
            "compute_correlation": 0,
            "flag_charge_dependence": 0,
            "compute_corr_rap_dep": 0,
            "resonance_weak_feed_down_flag": 1,
            "pT_min": 0.2,
            "pT_max": 2.0,
            "rap_min": -1.0,
            "rap_max": 1.0,
            "rap_type": 1,
            "vn_rapidity_dis_pT_min": 0.2,
            "vn_rapidity_dis_pT_max": 2.0,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "design",
        nargs="?",
        type=Path,
        default=None,
        help="Path to the design matrix file. Defaults to ./design in the working directory.",
    )
    parser.add_argument(
        "--design",
        dest="design_flag",
        type=Path,
        default=None,
        help="Alternative flag form for the design matrix path.",
    )
    parser.add_argument(
        "--template",
        type=Path,
        default=None,
        help="Path to the template parameter file. Defaults to the realistic template in this repo.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory in which to create DesignPointN folders. Defaults to the current working directory.",
    )
    parser.add_argument(
        "--start-design-point",
        type=int,
        default=1,
        help="First design-point number to generate, inclusive.",
    )
    parser.add_argument(
        "--end-design-point",
        type=int,
        default=None,
        help="Last design-point number to generate, inclusive. Defaults to the final row.",
    )
    args = parser.parse_args()
    if args.design_flag is not None:
        args.design = args.design_flag
    return args


def find_template_path(template_arg: Path | None, cwd: Path) -> Path | None:
    if template_arg is not None:
        template_path = template_arg.resolve()
        if not template_path.exists():
            raise FileNotFoundError(f"Template file not found: {template_path}")
        return template_path

    candidates = [
        cwd / "parameters_dict_user_TRENTo_realistic.py",
        cwd / "config" / "design_points" / "parameters_dict_user_TRENTo_realistic.py",
    ]

    repo_root = Path(__file__).resolve().parent
    candidates.extend(
        [
            repo_root / "config" / "design_points" / "parameters_dict_user_TRENTo_realistic.py",
            repo_root / "parameters_dict_user_TRENTo_realistic.py",
        ]
    )

    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()

    return None


def find_design_path(design_arg: Path | None, cwd: Path) -> Path:
    if design_arg is not None:
        return design_arg.resolve()

    candidate = cwd / DEFAULT_DESIGN_NAME
    if candidate.exists():
        return candidate.resolve()

    raise FileNotFoundError(
        f"Could not locate the design matrix at {candidate}. Use --design to provide the path explicitly."
    )


def load_template(template_path: Path | None):
    if template_path is None:
        return default_template_config()

    ns = runpy.run_path(str(template_path))
    # Keep only the variables defined in the template file; they are required by the generated dictionaries.
    return ns


def bmax_from_design(row: dict[str, str]) -> float:
    """Compute the TRENTo maximum impact parameter from the design-point values.

    This follows the exact design expression:

        b_max = 1.789 * sqrt{ R^2 * [1 + (7*pi/4) * (beta_2^2 + beta_3^2)]
        + (7*pi^2/3) * a^2 } + w + 0.5

    where R is WS_radius, a is WS_diffusiveness, and w is nucleon-width.
    """
    R = float(row["WS_radius"])
    a = float(row["WS_diffusiveness"])
    w = float(row["nucleon-width"])
    beta_2 = float(row["beta_2"])
    beta_3 = float(row["beta_3"])

    deformation_term = (7.0 / (4.0 * math.pi)) * (beta_2 ** 2 + beta_3 ** 2)
    bmax = 1.789 * math.sqrt(R ** 2 * (1.0 + deformation_term) + (7.0 * math.pi ** 2 / 3.0) * (a ** 2)) + w + 0.5
    return bmax


def set_target_and_projectile_shapes(config: dict, row: dict[str, str]) -> None:
    for section_name in ("target", "projectile"):
        if section_name == "target":
            section = config["isobars_conf_dict_target"]["isobar_properties"]["isobar1"]
        else:
            section = config["isobars_conf_dict_projectile"]["isobar_properties"]["isobar1"]

        section["WS_radius"]["value"] = float(row["WS_radius"])
        section["WS_diffusiveness"]["value"] = float(row["WS_diffusiveness"])
        section["beta_2"]["value"] = float(row["beta_2"])
        section["gamma"]["value"] = float(row["gamma"])
        section["beta_3"]["value"] = float(row["beta_3"])


def update_template_values(config: dict, row: dict[str, str]) -> None:
    # Keep the same dictionary structure and defaults as the realistic template.
    set_target_and_projectile_shapes(config, row)

    free_stream = config["free_streaming_dict"]
    music = config["music_dict"]
    trento = config["trento_dict"]

    free_stream["tau"] = float(row["tau"])
    music["Initial_time_tau_0"] = float(row["tau"])

    # design file values for all TRENTo and hydro parameters
    trento["reduced-thickness"] = float(row["reduced-thickness"])
    # TRENTo's `fluctuation` is k, the *shape* parameter of the gamma
    # distribution that weights each nucleon (gamma_param_unit_mean(k): unit
    # mean, variance 1/k, so standard deviation 1/sqrt(k)). The JETSCAPE design
    # axis is sigma_k, the standard deviation of that same gamma, so
    #     k = 1 / sigma_k**2
    # exactly. arXiv:2011.01430 varies sigma_k over [0.3, 2.0], which maps to
    # k in [0.25, 11.1]. Either column is accepted; sigma_k wins if both exist
    # because it is the parameter with the physical meaning.
    if "sigma_k" in row:
        sigma_k = float(row["sigma_k"])
        if sigma_k <= 0.0:
            raise ValueError(f"sigma_k must be positive, got {sigma_k}")
        trento["fluctuation"] = 1.0 / sigma_k**2
        print(f"  sigma_k = {sigma_k:.4f} -> TRENTo fluctuation k = "
              f"{trento['fluctuation']:.4f}")
    else:
        trento["fluctuation"] = float(row["fluctuation"])
    trento["nucleon-width"] = float(row["nucleon-width"])
    # TRENTo normalization, the paper's overall multiplicity scale. It used to be
    # frozen at the template's 5.73, which made the single most important design
    # axis unreachable from the design matrix.
    if str(row.get("normalization", "")).strip():
        trento["normalization"] = float(row["normalization"])
    trento["b-max"] = bmax_from_design(row)

    music["shear_viscosity_3_eta_over_s_T_kink_in_GeV"] = float(
        row["shear_viscosity_3_eta_over_s_T_kink_in_GeV"]
    )
    music["shear_viscosity_3_eta_over_s_low_T_slope_in_GeV"] = float(
        row["shear_viscosity_3_eta_over_s_low_T_slope_in_GeV"]
    )
    music["shear_viscosity_3_eta_over_s_high_T_slope_in_GeV"] = float(
        row["shear_viscosity_3_eta_over_s_high_T_slope_in_GeV"]
    )
    music["shear_viscosity_3_eta_over_s_at_kink"] = float(
        row["shear_viscosity_3_eta_over_s_at_kink"]
    )
    music["shear_relax_time_factor"] = float(row["shear_relax_time_factor"])

    music["bulk_viscosity_3_max"] = float(row["bulk_viscosity_3_max"])
    music["bulk_viscosity_3_T_peak_in_GeV"] = float(row["bulk_viscosity_3_T_peak_in_GeV"])
    music["bulk_viscosity_3_width_in_GeV"] = float(row["bulk_viscosity_3_width_in_GeV"])
    music["bulk_viscosity_3_lambda_asymm"] = float(row["bulk_viscosity_3_lambda_asymm"])

    music["T_freeze"] = float(row["T_freeze"])


def format_python_string(value: str, in_list: bool = False, quote: str = '"') -> str:
    escaped = value.replace('\\', '\\\\')
    escaped = escaped.replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
    if quote == "'":
        escaped = escaped.replace("'", "\\'")
    else:
        escaped = escaped.replace('"', '\\"')
    return quote + escaped + quote


def format_python_value(value, indent: int = 0, in_list: bool = False, key_quote: str = "'", string_quote: str = '"'):
    pad = " " * indent
    next_pad = " " * (indent + 4)

    if isinstance(value, dict):
        if not value:
            return "{}"
        lines = ["{"]
        items = list(value.items())
        for index, (key, item) in enumerate(items):
            suffix = ","
            nested_value = format_python_value(item, indent + 4, in_list=False, key_quote='"', string_quote=string_quote)
            lines.append(f"{next_pad}{key_quote}{key}{key_quote}: {nested_value}{suffix}")
        lines.append(f"{pad}}}")
        return "\n".join(lines)

    if isinstance(value, list):
        if not value:
            return "[]"

        rendered_items = []
        for item in value:
            if isinstance(item, str):
                rendered_items.append(format_python_string(item, in_list=True, quote="'"))
            elif isinstance(item, (int, float, bool)) or item is None:
                rendered_items.append(repr(item))
            else:
                rendered_items = None
                break

        if rendered_items is not None:
            rendered = ", ".join(rendered_items)
            if len(rendered) <= 80:
                return f"[{rendered}]"

        lines = ["["]
        for index, item in enumerate(value):
            suffix = ","
            nested_value = format_python_value(item, indent + 4, in_list=True, key_quote='"', string_quote='"')
            lines.append(f"{next_pad}{nested_value}{suffix}")
        lines.append(f"{pad}]")
        return "\n".join(lines)

    if isinstance(value, str):
        return format_python_string(value, in_list=in_list, quote=string_quote)

    if isinstance(value, bool):
        return "True" if value else "False"

    if value is None:
        return "None"

    return repr(value)


def python_literal(value):
    return format_python_value(value, indent=0, in_list=False, key_quote="'", string_quote='"')


def f_sigma(row: dict[str, str], key: str) -> float:
    """Read an optional deformation-width column; absent means a fixed shape."""
    return float(row[key]) if str(row.get(key, "")).strip() else 0.0


def f_str(row: dict[str, str], key: str, default: str) -> str:
    """Read an optional string column; absent means the default."""
    v = str(row.get(key, "")).strip()
    return v if v else default


def f_beta_max(row: dict[str, str], samples: dict) -> float:
    """Upper bound on the quadrupole strength for the bounded Beta draw.

    Absent means "use the template's value". This is the support of the Option B
    draw, so a design point asking for a mean and width wider than beta_max can
    represent is rejected at generation time rather than silently clipped.
    """
    if str(row.get("beta_max", "")).strip():
        return float(row["beta_max"])
    template_value = samples.get("beta_max", {}).get("value")
    if template_value is not None:
        return float(template_value)
    # The embedded template carries no beta_max, so a design matrix that omits
    # the column used to die here even though the column is documented optional.
    # Fall back to the top of the beta_2 prior used for 76Ge/76Se.
    return 0.5


def format_isobar_dict(section_name: str, row: dict[str, str], samples: dict) -> str:
    label = "target" if section_name == "target" else "projectile"
    seed_source = samples["seed_source"]["value"]
    master_seed = samples["master_seed"]["value"]
    pool_modulus = samples["pool_modulus"]["value"]
    # Mass number comes from the design matrix when the column is present. It
    # used to be hardcoded to 96, which silently pinned every generated design
    # point to Zr/Ru even when the CSV asked for something else.
    if str(row.get("number_nucleons", "")).strip():
        n_nucleons = int(float(row["number_nucleons"]))
    else:
        n_nucleons = int(samples["number_nucleons"]["value"])
    lines = [
        f'isobars_conf_dict_{section_name} = {{',
        '    "isobar_samples": {',
        '        "description": "Options for the isobar nucleon-position samples",',
        '        "number_configs": {',
        '            "description": "Number of configurations to be sampled.",',
        '            "value": 1,',
        '        },',
        '        "number_nucleons": {',
        '            "description": "Mass number A of the nuclei.",',
        f'            "value": {n_nucleons},',
        '        },',
        '        "seed_source": {',
        '            "description": "Nucleon seeds: philox (deterministic from master_seed and pool address) or file (HDF5 pool).",',
        f'            "value": "{seed_source}",',
        '        },',
        '        "master_seed": {',
        '            "description": "Master seed for the philox source. Must never change once events exist; recorded in EMULATOR_SWEEP_PLAN.md.",',
        f'            "value": {master_seed},',
        '        },',
        '        "pool_modulus": {',
        '            "description": "Size of the virtual nucleus pool, 2**32. Event g maps to addresses (2g)*2654435761 and (2g+1)*2654435761 mod this.",',
        f'            "value": {pool_modulus},',
        '        },',
        '        "output_path": {',
        '            "description": "Output directory where to save",',
        f'            "dirname": "nuclei_{label}",',
        '        },',
        '        "number_of_parallel_processes": {',
        '            "description": "Number of processes to compute in parallel.",',
        '            "value": -1,',
        '        },',
        '    },',
        '    "isobar_properties": {',
        '        "description": "Nuclear properties of isobars to be sampled.",',
        '        "isobar1": {',
        f'            "isobar_name": "{label}",',
        f'            "WS_radius": {{"description": "Woods-Saxon radius parameter R", "value": {float(row["WS_radius"])}}},',
        f'            "WS_diffusiveness": {{"description": "Woods-Saxon diffusiveness parameter a", "value": {float(row["WS_diffusiveness"])}}},',
        f'            "beta_2": {{"description": "Quadrupolar deformation", "value": {float(row["beta_2"])}}},',
        f'            "gamma": {{"description": "Quadrupolar deformation angle (rad)", "value": {float(row["gamma"])}}},',
        f'            "beta_3": {{"description": "Octupolar deformation", "value": {float(row["beta_3"])}}},',
        # Event-by-event deformation widths. Optional CSV columns; absent (or 0)
        # keeps the design point at a fixed shape, i.e. the previous behaviour.
        f'            "sigma_beta_2": {{"description": "Event-by-event width of beta_2; 0 fixes the shape", "value": {f_sigma(row, "sigma_beta_2")}}},',
        f'            "sigma_beta_3": {{"description": "Event-by-event width of beta_3; 0 fixes the shape", "value": {f_sigma(row, "sigma_beta_3")}}},',
        f'            "sigma_gamma": {{"description": "Event-by-event width of gamma_lit (rad); folded onto [0, pi/3], 0 fixes gamma", "value": {f_sigma(row, "sigma_gamma")}}},',
        f'            "beta_max": {{"description": "Upper bound on quadrupole strength (Option B); uniform wedge prior is beta_max/2 with sd beta_max/sqrt(12)", "value": {f_beta_max(row, samples)}}},',
        f'            "shape_distribution": {{"description": "Per-event shape draw: wedge (Option B) or plane (Gaussian in the deformation plane, folded per draw)", "value": "{f_str(row, "shape_distribution", "wedge")}"}},',
        f'            "sigma_plane": {{"description": "Width of the plane-form Gaussian; 0 is rigid, and works at beta_2 = 0", "value": {f_sigma(row, "sigma_plane")}}},',
        f'            "plane_anisotropy": {{"description": "Splits sigma_plane with fixed geometric mean; 0 is isotropic, positive favours prolate/oblate, negative favours triaxial", "value": {f_sigma(row, "plane_anisotropy")}}},',
        '            "correlation_length": {"description": "Short-range correlation length (fm)", "value": 0.4},',
        '            "correlation_strength": {"description": "Short-range correlation strength", "value": 0.0},',
        '        },',
        '    },',
        '}',
    ]
    return "\n".join(lines)


def write_design_point_file(output_dir: Path, index_one_based: int, config: dict, row: dict[str, str]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    file_name = f"parameter_dictionary_design_point_{index_one_based}.py"
    output_path = output_dir / file_name
    # Defaults (seed_source, master_seed, pool_modulus, mass number) come from
    # the template this design point is generated against.
    samples = config["isobars_conf_dict_target"]["isobar_samples"]

    lines = [
        "#!/usr/bin/env python3",
        '"""',
        f"Design point {index_one_based} for TRENTo + free-streaming + MUSIC + UrQMD test batch.",
        '"""',
        "",
        "# control parameters",
        "",
        f"control_dict = {python_literal(config['control_dict'])}",
        "",
        "# No isobar_seed_file: nucleon positions are generated deterministically",
        "# from isobars_conf_dict_*['isobar_samples']['seed_source'] (\"philox\").",
        "# Only the legacy seed_source \"file\" reads a pool; generate one with",
        "# utilities/make_seed_pool.py and set isobar_seed_file to its path.",
        "",
        "# isobar-sample",
        "",
        format_isobar_dict("target", row, samples),
        "",
        format_isobar_dict("projectile", row, samples),
        "",
    ]

    for name in [
        "trento_dict",
        "free_streaming_dict",
        "music_dict",
        "iss_dict",
        "hadronic_afterburner_toolkit_dict",
    ]:
        value = config[name]
        lines.append(f"{name} = {python_literal(value)}")
        lines.append("")

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    output_path.chmod(0o755)


def main() -> None:
    args = parse_args()
    cwd = Path.cwd()
    output_dir = (args.output_dir or cwd).resolve()
    design_path = find_design_path(args.design, cwd)
    template_path = find_template_path(args.template, cwd)

    rows = []
    with design_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    if not rows:
        raise RuntimeError(f"No design points found in {design_path}.")

    start_design_point = args.start_design_point
    end_design_point = args.end_design_point or len(rows)
    if start_design_point < 1 or end_design_point < start_design_point:
        raise ValueError("Design-point range must satisfy 1 <= start <= end.")
    if end_design_point > len(rows):
        raise ValueError(
            f"Design-point range ends at {end_design_point}, but the design has only {len(rows)} rows."
        )

    template_ns = load_template(template_path)
    base_config = {
        name: template_ns[name]
        for name in [
            "control_dict",
            "isobars_conf_dict_target",
            "isobars_conf_dict_projectile",
            "trento_dict",
            "free_streaming_dict",
            "music_dict",
            "iss_dict",
            "hadronic_afterburner_toolkit_dict",
        ]
    }

    for zero_based_index, row in enumerate(rows):
        one_based_index = zero_based_index + 1
        if one_based_index < start_design_point or one_based_index > end_design_point:
            continue
        config = {key: value.copy() if isinstance(value, dict) else value for key, value in base_config.items()}
        # deep-copy the nested dicts to avoid cross-design pollution
        config["control_dict"] = dict(base_config["control_dict"])
        config["isobars_conf_dict_target"] = {
            k: (v.copy() if isinstance(v, dict) else v) for k, v in base_config["isobars_conf_dict_target"].items()
        }
        config["isobars_conf_dict_projectile"] = {
            k: (v.copy() if isinstance(v, dict) else v) for k, v in base_config["isobars_conf_dict_projectile"].items()
        }
        config["trento_dict"] = dict(base_config["trento_dict"])
        config["free_streaming_dict"] = dict(base_config["free_streaming_dict"])
        config["music_dict"] = dict(base_config["music_dict"])
        config["iss_dict"] = dict(base_config["iss_dict"])
        config["hadronic_afterburner_toolkit_dict"] = dict(base_config["hadronic_afterburner_toolkit_dict"])
        config["control_dict"]["walltime"] = "20:00:00"

        update_template_values(config, row)

        dir_name = f"DesignPoint{one_based_index}"
        point_dir = output_dir / dir_name
        write_design_point_file(point_dir, one_based_index, config, row)

    generated_count = end_design_point - start_design_point + 1
    print(f"Generated {generated_count} design-point folders under {output_dir}")


if __name__ == "__main__":
    main()
