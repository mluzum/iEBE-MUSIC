#!/usr/bin/env python3
"""This is a drive script to run hydro + hadronic cascade simulation"""

from multiprocessing import Pool
from subprocess import call
from os import path, mkdir, remove, makedirs, stat
import os
import csv
import tarfile
from glob import glob
from fnmatch import fnmatch
import sys
import time
import shutil
import re
import json
import math
import h5py
import numpy as np
import freestream
from fetch_IPGlasma_event_from_hdf5_database import fecth_an_IPGlasma_event, fecth_an_IPGlasma_event_Tmunu
from fetch_3DMCGlauber_event_from_hdf5_database import fecth_an_3DMCGlauber_event


def print_usage():
    """This function prints out help messages"""
    print("\U0001F3B6  " + "Usage: {} ".format(sys.argv[0])
          + "initial_condition_type initial_condition_database "
          + "n_hydro_events hydro_event_id n_UrQMD n_threads "
          + "save_ipglasma_flag save_kompost_flag save_hydro_flag "
          + "save_urqmd_flag seed_add compute_polarization_flag "
          + "compute_photons_flag enableCheckPoint afterburner_type "
          + "kompost_filename trento_output free_stream_tau "
          + "free_stream_grid_max free_stream_grid_step")


def fecth_an_3DMCGlauber_smooth_event(database_path, iev):
    """This function returns the filename of an initial condition in the
       database_path folder
    """
    filelist = glob(path.join(database_path, 'nuclear_thickness_TA_*.dat'))
    return (filelist[iev])


def mapEventIdToCentrality(event_id):
    """This function maps the event_id to centrality bin for 3D-Glauber model
       It makes sure the centrality are evenly distributed over different
       simulation jobs when nev > 1
    """
    event_id = event_id % 100
    b = event_id % 10
    a = int((event_id - b)/10)
    centrality = 0
    if (b % 2) == 0:
        centrality = b/2*10 + a
    else:
        centrality = (9 - (b - 1)/2)*10 + a
    return (centrality)


##########################################################################################
# This function converts a matrix file to a table file for freestreaming


def convert_matrix_to_table(infile,
                            outfile,
                            n_grid=None,
                            lower=-10.0,
                            upper=10.0):
    data = np.loadtxt(infile, comments='#')

    if data.ndim == 1:
        if n_grid is None:
            n_grid_float = np.sqrt(data.size)
            n_grid = int(round(n_grid_float))
            if n_grid*n_grid != data.size:
                raise ValueError(
                    f"Cannot infer square grid size from {data.size} points")
        data = data.reshape(n_grid, n_grid)
    else:
        if data.shape[0] != data.shape[1]:
            raise ValueError(f"Input matrix is not square: {data.shape}")
        if n_grid is None:
            n_grid = data.shape[0]
        elif data.shape != (n_grid, n_grid):
            raise ValueError(
                f"Input matrix shape {data.shape} does not match n_grid={n_grid}"
            )

    step = (upper - lower)/n_grid
    x = np.linspace(lower + step/2, upper - step/2, n_grid)
    y = x
    X, Y = np.meshgrid(x, y, indexing='xy')

    eps_flat = data.ravel()
    table = np.column_stack([
        np.zeros_like(eps_flat),
        X.ravel(),
        Y.ravel(), eps_flat,
        np.ones_like(eps_flat),
        np.zeros((eps_flat.size, 13))
    ])
    header = f"# dummy 1 etamax= 0 xmax= {n_grid} ymax= {n_grid} deta= 0 dx= {step} dy= {step}"
    np.savetxt(outfile, table, fmt="%.6e", header=header, comments='')


############################################################################################


def get_initial_condition(database, initial_type, iev, event_id, seed_add,
                          final_results_folder, para_dict):
    """This funciton get initial conditions"""
    status = True
    if "IPGlasma" in initial_type:
        ipglasma_local_folder = "ipglasma/ipglasma_results"
        res_path = path.join(path.abspath(final_results_folder),
                             "ipglasma_results_{}".format(event_id))
        file_name = (f"epsilon-u-Hydro-TauHydro-{event_id}.dat")
        if "KoMPoST" in initial_type:
            file_name = (f"Tmunu-TauHydro-{event_id}.dat")
        if database == "self":
            # check existing events ...
            if not path.exists(path.join(res_path, file_name)):
                run_ipglasma(event_id)
                collect_ipglasma_event(res_path)
                if not path.exists(path.join(res_path, file_name)):
                    # IPGlasma event failed
                    print("IPGlasma event failed ... ")
                    status = False
            else:
                print("IPGlasma event exists ...")
                print("No need to rerun ...")
        else:
            if "KoMPoST" in initial_type:
                file_temp = fecth_an_IPGlasma_event_Tmunu(database, event_id)
            else:
                file_temp = fecth_an_IPGlasma_event(database, event_id)
            makedirs(ipglasma_local_folder, exist_ok=True)
            shutil.move(file_temp, path.join(ipglasma_local_folder, file_name))
            collect_ipglasma_event(res_path)
        connect_ipglasma_event(res_path, initial_type, file_name)
        return status, file_name
    ########################################################################
    elif initial_type == "TRENTo":
        res_path = path.join(path.abspath(final_results_folder),
                             "trento_results_{}".format(event_id))
        trento_output = para_dict.get('trento_output', 'test_path.dat')
        file_name = path.join(trento_output, "0.dat")
        #check existing events ...
        if not path.exists(path.join(res_path, file_name)):
            run_trento(event_id)
            collect_trento_event(res_path)
            if not path.exists(path.join(res_path, file_name)):
                # TRENTo event failed
                print("TRENTo event failed ... ")
                status = False

        else:
            print("TRENTo event exists ...")
            print("No need to rerun ...")

        write_trento_event_summary(res_path, final_results_folder, event_id,
                                   seed_add)

        grid_max = para_dict['free_stream_grid_max']
        grid_step = para_dict['free_stream_grid_step']

        if para_dict.get('adaptive_grid'):
            try:
                new_L = apply_adaptive_grid(res_path, file_name, para_dict,
                                            grid_step)
                if new_L is not None:
                    # rerun TRENTo on the chosen grid, then recollect
                    run_trento(event_id)
                    collect_trento_event(res_path)
                    write_trento_event_summary(res_path, final_results_folder,
                                               event_id, seed_add)
                    grid_max = new_L
                # keep the diagnostic honest about which grid was actually used
                para_dict['free_stream_grid_max'] = grid_max
            except Exception:
                import traceback
                print('adaptive grid failed, keeping the fixed box:\n{}'.format(
                    traceback.format_exc()),
                      flush=True)

        connect_trento_event(res_path, initial_type, file_name,
                             para_dict['free_stream_tau'], grid_max, grid_step)
        return status, file_name
    #########################################################################
    elif initial_type == "3DMCGlauber_dynamical":
        if database == "self" or database == "fixCentrality":
            file_name = "strings_event_{}.dat".format(event_id)
            specFilename = "spectators_event_{}.dat".format(event_id)
            # Deterministic in (seed_add, event_id, iev). This was
            # np.random.default_rng().integers(1e8) -- fresh OS entropy on every
            # call, so the run was irreproducible. Deriving it from the event id
            # also means the same event gets the same Glauber randomness at every
            # grid resolution.
            ran = int(
                np.random.default_rng([seed_add, event_id, iev]).integers(1e8))
            if not path.exists(file_name):
                if database == "self":
                    cenMin = mapEventIdToCentrality(event_id)
                    call("(cd 3dMCGlauber; ./3dMCGlb.e 1 input "
                         + "{} cenMin={} cenMax={};)".format(
                             seed_add + iev*ran, cenMin, cenMin + 1),
                         shell=True)
                else:
                    call("(cd 3dMCGlauber; ./3dMCGlb.e 1 input "
                         + "{};)".format(seed_add + iev*ran),
                         shell=True)
                call("mv 3dMCGlauber/strings_event_0.dat {}".format(file_name),
                     shell=True)
                call("mv 3dMCGlauber/spectators_event_0.dat {}".format(
                    specFilename),
                     shell=True)
            else:
                print("3D MC-Glauber event exists ...")
                print("No need to rerun ...")
            shutil.copy(file_name, "MUSIC/initial/strings.dat")
            shutil.copy(
                file_name,
                path.join(final_results_folder,
                          "strings_{}.dat".format(event_id)))
            shutil.copy(
                specFilename,
                path.join(final_results_folder,
                          "spectators_{}.dat".format(event_id)))
            filePatterns = ["ed_etas", "nB_etas", "ecc_ed"]
            call(
                "mv 3dMCGlauber/rapidity_shift.dat hadronic_afterburner_toolkit/",
                shell=True)
            call("mv 3dMCGlauber/ed_etas_*.dat {}".format(final_results_folder),
                 shell=True)
            call("mv 3dMCGlauber/nB_etas_*.dat {}".format(final_results_folder),
                 shell=True)
            call("mv 3dMCGlauber/ecc_ed*.dat {}".format(final_results_folder),
                 shell=True)
            return status, file_name
        else:
            file_name = fecth_an_3DMCGlauber_event(database, event_id)
            return status, file_name
    elif initial_type == "3DMCGlauber_participants":
        file_name = "participants_event_{}.dat".format(event_id)
        specFilename = "spectators_event_{}.dat".format(event_id)
        # deterministic in (seed_add, event_id) -- see the note at the other call site
        ran = int(np.random.default_rng([seed_add, event_id]).integers(1e8))
        if not path.exists(file_name):
            if database == "self":
                cenMin = mapEventIdToCentrality(event_id)
                call("(cd 3dMCGlauber; ./3dMCGlb.e 1 input "
                     + "{} cenMin={} cenMax={};)".format(
                         seed_add + iev*ran, cenMin, cenMin + 1),
                     shell=True)
            else:
                call("(cd 3dMCGlauber; ./3dMCGlb.e 1 input "
                     + "{};)".format(seed_add + iev*ran),
                     shell=True)
            call("mv 3dMCGlauber/participants_event_0.dat {}".format(file_name),
                 shell=True)
            call(
                "mv 3dMCGlauber/spectators_event_0.dat {}".format(specFilename),
                shell=True)
        else:
            print("3D MC-Glauber event exists ...")
            print("No need to rerun ...")
        shutil.copy(file_name, "MUSIC/initial/participants_event.dat")
        shutil.copy(file_name, path.join(final_results_folder, file_name))
        shutil.copy(
            specFilename,
            path.join(final_results_folder,
                      "spectators_{}.dat".format(event_id)))
        return status, file_name
    elif initial_type == "3DMCGlauber_consttau":
        file_name = fecth_an_3DMCGlauber_smooth_event(database, event_id)
        return status, file_name
    else:
        print("\U0001F6AB  "
              + "Do not recognize the initial condition type: {}".format(
                  initial_type))
        sys.exit(1)


# --- adaptive transverse grid -------------------------------------------------
#
# Measured over 141 events (b = 1.46-13.31 fm) by the grid-extent campaign. The
# freeze-out surface sits at a fixed multiple of its own RMS radius, and that
# RMS radius is predicted from the size of the TRENTo initial condition plus the
# parameters that set how far the system expands before it reaches T_freeze.
#
# Coefficients are READ FROM adaptive_grid.json in the working directory, never
# hard-coded, so they can be refitted and shipped with the parameter file without
# rebuilding the image.
#
# PLACEHOLDER VALUES: these are the fit against the POST-free-streaming R_rms.
# Free-streaming shifts R_rms by -0.20 fm (-4.9%), which is larger than sigma, so
# they must be refitted against the pre-free-streaming value before use.
ADAPTIVE_DEFAULT_COEFFS = {
    "c0": -0.182,
    "c1": 1.141,
    "c2": -0.109,
    "c3": 0.143,
    "c4": -0.810,
    "sigma": 0.165,
    "k_tail": 2.25,
    "n_sigma": 5.0,
}

# e_fo (GeV/fm^3) at which MUSIC freezes out, as a function of T_freeze, measured
# from the campaign. Interpolation is linear in ln(e_fo).
ADAPTIVE_EFO_TABLE = [(0.10, 0.0160), (0.12, 0.0486), (0.15, 0.2341)]


def read_adaptive_coeffs():
    """Sizing coefficients, from adaptive_grid.json if present."""
    coeffs = dict(ADAPTIVE_DEFAULT_COEFFS)
    fname = "adaptive_grid.json"
    for candidate in (fname, path.join("model_parameters", fname),
                      path.join("..", "model_parameters", fname)):
        if path.exists(candidate):
            try:
                with open(candidate, "r", encoding="utf-8") as f:
                    coeffs.update(json.load(f))
            except (OSError, ValueError):
                pass
            break
    return coeffs


def e_fo_from_t_freeze(t_freeze):
    """Energy density at freeze-out, interpolated from the measured table."""
    pts = ADAPTIVE_EFO_TABLE
    if t_freeze <= pts[0][0]:
        return pts[0][1]
    if t_freeze >= pts[-1][0]:
        return pts[-1][1]
    for (t0, e0), (t1, e1) in zip(pts, pts[1:]):
        if t0 <= t_freeze <= t1:
            w = (t_freeze - t0)/(t1 - t0)
            return float(
                math.exp(math.log(e0) + w*(math.log(e1) - math.log(e0))))
    return pts[-1][1]


def _split_input_line(line):
    """(key, value) from a MUSIC/TRENTo input line, or (None, None).

    Two formats are in play and mixing them up is silent: TRENTo writes
    "key = value" while MUSIC writes "key  value" with whitespace only. A patch
    that only understands the first one appears to succeed and changes nothing.
    """
    stripped = line.split("#")[0].strip()
    if not stripped:
        return None, None
    if "=" in stripped:
        name, _, val = stripped.partition("=")
        return name.strip(), val.strip()
    parts = stripped.split(None, 1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return None, None


def read_input_value(fname, key):
    """Value of `key` in a MUSIC/TRENTo style input file, or None."""
    try:
        with open(fname, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("#"):
                    continue
                name, val = _split_input_line(line)
                if name == key:
                    return val
    except OSError:
        pass
    return None


def patch_input_value(fname, key, value):
    """Rewrite the value of `key` in place. Returns True if the key was found."""
    try:
        with open(fname, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return False
    hit = False
    for i, line in enumerate(lines):
        if line.startswith("#"):
            continue
        name, _val = _split_input_line(line)
        if name == key:
            # Preserve the file's own separator. TRENTo requires "key = value"
            # and rejects a whitespace-only line outright; MUSIC uses plain
            # whitespace. Writing one format into the other file breaks the run
            # with a message that does not mention the real cause.
            if "=" in line.split("#")[0]:
                lines[i] = "{} = {}\n".format(key, value)
            else:
                lines[i] = "{}  {}\n".format(key, value)
            hit = True
    if hit:
        try:
            with open(fname, "w", encoding="utf-8") as f:
                f.writelines(lines)
        except OSError:
            return False
    return hit


def ic_rms_from_flat(e_flat, grid_max, grid_step):
    """RMS radius of a square gridded energy density, in fm."""
    n = int(round(math.sqrt(e_flat.size)))
    if n*n != e_flat.size:
        return None
    step = (2.0*grid_max)/n
    x = np.linspace(-grid_max + step/2.0, grid_max - step/2.0, n)
    X, Y = np.meshgrid(x, x, indexing='xy')
    r = np.hypot(X, Y).ravel()
    total = e_flat.sum()
    if total <= 0:
        return None
    return float(np.sqrt((e_flat*r**2).sum()/total))


def plan_adaptive_half_width(R_rms_trento,
                             t_freeze,
                             normalization,
                             tau,
                             coeffs,
                             grid_step,
                             current_grid_max,
                             fixed_cells=0):
    """Half-width the box needs, in fm, or None to leave the box alone.

    Two schemes, selected by `fixed_cells`:

    * fixed_cells == 0 -- dx is held at `grid_step` and the cell count shrinks
      with the system. Discretisation error depends on dx only.
    * fixed_cells > 0  -- the cell count is held fixed and dx = 2L/N varies with
      the system, so small systems are resolved more finely. This equalises
      dx/L rather than dx.

    Returns (half_width, n_cells, r_rms_predicted, dx_used).
    """
    e_fo = e_fo_from_t_freeze(t_freeze)
    r_rms = (coeffs["c0"] + coeffs["c1"]*R_rms_trento
             + coeffs["c2"]*math.log(e_fo)
             + coeffs["c3"]*math.log(normalization) + coeffs["c4"]*tau)
    need = coeffs["k_tail"]*(r_rms + coeffs["n_sigma"]*coeffs["sigma"])
    if fixed_cells and fixed_cells > 0:
        n_cells = int(fixed_cells)
        if n_cells < 2:
            n_cells = 2
        half = n_cells*grid_step/2.0
        # the cell count is held fixed, so the box is quantised in units of
        # grid_step; round the half-width up so the box still covers `need`
        n_cells = 2*int(math.ceil(need/grid_step - 1e-9))
        if n_cells < int(fixed_cells):
            n_cells = int(fixed_cells)
        half = n_cells*grid_step/2.0
        dx_used = half/(n_cells/2.0)
    else:
        n_cells = 2*int(math.ceil(need/grid_step - 1e-9))
        if n_cells < 2:
            n_cells = 2
        half = n_cells*grid_step/2.0
        dx_used = grid_step
    return half, n_cells, r_rms, dx_used


def apply_adaptive_grid(res_path, file_name, para_dict, grid_step):
    """Measure the TRENTo IC, choose a box, and rerun TRENTo on that grid.

    Returns the new half-width, or None if the current box was kept.
    """
    trento_input = path.join("TRENTo", "input")
    music_input = path.join("MUSIC", "music_input_mode_2")

    trento_matrix = np.loadtxt(path.join(res_path, file_name))
    trento_grid_max = float(read_input_value(trento_input, "grid-max") or 15.0)
    R_rms = ic_rms_from_flat(trento_matrix.ravel(), trento_grid_max, grid_step)
    if R_rms is None:
        return None

    normalization = float(
        read_input_value(trento_input, "normalization") or 1.0)
    t_freeze = float(read_input_value(music_input, "T_freeze") or 0.12)
    tau = float(para_dict.get("free_stream_tau", 1.0))

    coeffs = read_adaptive_coeffs()
    fixed_cells = 0
    for _k in ("adaptive_fixed_cells", "fixed_cells"):
        try:
            _v = read_input_value(trento_input, _k)
            if _v is None:
                _v = read_input_value(music_input, _k)
            if _v is not None:
                fixed_cells = int(float(_v))
                break
        except (TypeError, ValueError):
            pass
    L, n_cells, r_rms, dx_used = plan_adaptive_half_width(
        R_rms, t_freeze, normalization, tau, coeffs, grid_step, trento_grid_max,
        fixed_cells)

    current_cells = int(round(2.0*trento_grid_max/grid_step))
    # only act if it actually saves, and never grow past what was measured
    if L >= trento_grid_max - 1e-9 or n_cells >= current_cells:
        print("\U0001F9FE  adaptive grid: keeping +-{:.1f} fm (needs +-{:.1f})".
              format(trento_grid_max, L),
              flush=True)
        return None

    print(
        "\U0001F9FE  adaptive grid: TRENTo R_rms={:.2f} -> r_rms_pred={:.2f} -> "
        "+-{:.1f} fm, {} cells, dx={:.3f} requested (was +-{:.1f}, {}, dx={:.3f})"
        .format(R_rms, r_rms, L, n_cells, dx_used, trento_grid_max,
                current_cells, grid_step),
        flush=True)
    if not patch_input_value(trento_input, "grid-max", "{:.4f}".format(L)):
        return None
    patch_input_value(trento_input, "grid-step", "{:.4f}".format(grid_step))
    patch_input_value(music_input, "X_grid_size_in_fm", "{:.4f}".format(L))
    patch_input_value(music_input, "Y_grid_size_in_fm", "{:.4f}".format(L))
    patch_input_value(music_input, "Grid_size_in_x", "{:d}".format(n_cells))
    patch_input_value(music_input, "Grid_size_in_y", "{:d}".format(n_cells))
    return L


def run_trento(event_id):
    """This functions run TRENTo"""
    print(" \U0001F680  Run TRENTo \u2192 freestream...")
    call("bash ./run_trento.sh {}".format(event_id), shell=True)


def run_ipglasma(event_id):
    """This functions run IPGlasma"""
    print("\U0001F3B6  Run IPGlasma ... ")
    call("bash ./run_ipglasma.sh {}".format(event_id), shell=True)


def collect_trento_event(final_results_folder):
    """This function collects the ipglasma results"""
    if path.exists(final_results_folder):
        shutil.rmtree(final_results_folder)
    shutil.move("TRENTo/trento_results", final_results_folder)
    # Low-risk cleanup: remove per-event isobar seed symlinks left in
    # the event folder to save disk space. Only remove symlinks (not
    # the shared master seed file) and be tolerant of any errors.
    try:
        event_root = path.dirname(path.abspath(final_results_folder))
        isobar_parent = path.join(event_root, "TRENTo")
        # look for both the numbered and legacy seed filenames
        patterns = ("Isobar-Sampler_*",)
        for sub in glob(path.join(isobar_parent, "Isobar-Sampler_*")):
            for seed_pattern in ("nucleon-seeds_*.hdf", "nucleon-seeds.hdf"):
                for seed_path in glob(path.join(sub, seed_pattern)):
                    try:
                        if path.islink(seed_path):
                            remove(seed_path)
                            print(
                                f"Removed per-event seed symlink: {seed_path}")
                    except OSError:
                        # ignore failures to remove individual links
                        pass
        # Also remove any copied seed files left at the event root
        for seed_pattern in ("nucleon-seeds_*.hdf", "nucleon-seeds.hdf"):
            for seed_path in glob(path.join(event_root, seed_pattern)):
                try:
                    # do not remove files inside a shared_seeds directory
                    if "/shared_seeds/" in path.abspath(seed_path).replace(
                            '\\\\', '/'):
                        continue
                    # remove regular files or symlinks that are local copies
                    remove(seed_path)
                    print(f"Removed per-event seed file: {seed_path}")
                except OSError:
                    pass
    except Exception:
        # never fail the run because cleanup couldn't complete
        pass


def write_trento_event_summary(trento_results_folder,
                               final_results_folder,
                               event_id,
                               seed_add=None):
    """Write a compact text summary for quiet-mode output transfer."""
    impact_parameter = None
    mult = None

    event_output_files = sorted(
        glob(path.join(trento_results_folder, "**", "0.dat"), recursive=True))
    if event_output_files:
        try:
            with open(event_output_files[0], "r", encoding="utf-8") as f:
                for line in f:
                    stripped = line.strip()
                    if impact_parameter is None and stripped.startswith("# b"):
                        impact_parameter = float(stripped.split("=", 1)[1])
                    elif mult is None and stripped.startswith("# mult"):
                        mult = float(stripped.split("=", 1)[1])
                    if impact_parameter is not None and mult is not None:
                        break
        except (OSError, ValueError, IndexError):
            pass

    metadata_file = path.join(trento_results_folder, "sampling_metadata.json")
    if path.exists(metadata_file) and (impact_parameter is None
                                       or mult is None):
        try:
            with open(metadata_file, "r", encoding="utf-8") as f:
                metadata = json.load(f)
            impact_parameter = metadata.get("impact_parameter",
                                            impact_parameter)
            mult = metadata.get("mult", mult)
        except (json.JSONDecodeError, OSError):
            pass

    run_log = path.join(trento_results_folder, "run.log")
    if path.exists(run_log) and (impact_parameter is None or mult is None):
        try:
            with open(run_log, "r", encoding="utf-8") as f:
                for line in f:
                    if impact_parameter is None and line.startswith(
                            "impact_parameter "):
                        parts = line.split()
                        if len(parts) >= 2:
                            impact_parameter = float(parts[1])
                    if mult is None and line.startswith("mult "):
                        parts = line.split()
                        if len(parts) >= 2:
                            mult = float(parts[1])
                    if impact_parameter is not None and mult is not None:
                        break
        except (OSError, ValueError):
            pass

    summary_path = path.join(final_results_folder,
                             f"trento_event_summary_{event_id}.txt")
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write("impact_parameter {}\n".format("nan" if impact_parameter is
                                               None else impact_parameter))
        f.write("mult {}\n".format("nan" if mult is None else mult))

    record_drawn_event(final_results_folder, event_id, impact_parameter, mult,
                       seed_add)


def record_drawn_event(final_results_folder,
                       event_id,
                       impact_parameter,
                       mult,
                       seed_add=None):
    """Append every DRAWN event, including the ones that never collide.

    Centrality percentiles need to know how many events were thrown away, not
    just how many survived. TRENTo returns mult = 0 for a configuration with no
    overlap -- that happens at large b when the two deformed, randomly oriented
    nuclei happen to miss -- and such an event produces no spvn results, so
    without this file it is invisible downstream: the merged HDF5 simply has
    fewer rows than events were requested and nothing records that the missing
    ones were failures rather than a truncated run.

    b_max is recorded alongside b because the b draw is uniform on
    [0, b_max] and b_max is computed per design point from the shape
    parameters. b/b_max is therefore the quantity that is comparable across
    design points, and it is the variable events stay synchronised in.

    Rewrites the file each call, keyed by event id, so the adaptive-grid rerun
    (which calls write_trento_event_summary twice for one event) cannot leave
    duplicate rows. Events run as one driver process per event, so there is no
    state to carry between calls.
    """
    csv_path = path.join(final_results_folder, "events_drawn.csv")
    columns = [
        "event_id", "b", "b_max", "b_over_bmax", "mult", "status", "seed_add"
    ]
    rows = {}
    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows[int(row["event_id"])] = row
    except (OSError, KeyError, ValueError):
        rows = {}

    b_max = read_input_value(path.join("TRENTo", "input"), "b-max")
    try:
        b_max = float(b_max) if b_max is not None else None
    except ValueError:
        b_max = None

    if mult is None:
        status = "no_trento"
    elif mult <= 0.0:
        status = "no_collision"
    else:
        status = "ok"

    rows[int(event_id)] = {
        "event_id":
            int(event_id),
        "b":
            ""
            if impact_parameter is None else "{:.10g}".format(impact_parameter),
        "b_max":
            "" if b_max is None else "{:.10g}".format(b_max),
        "b_over_bmax":
            "" if (b_max in (None, 0.0) or impact_parameter is None) else
            "{:.10g}".format(impact_parameter/b_max),
        "mult":
            "" if mult is None else "{:.10g}".format(mult),
        "status":
            status,
        "seed_add":
            "" if seed_add is None else int(seed_add),
    }

    tmp_path = csv_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for key in sorted(rows):
            writer.writerow(rows[key])
    os.replace(tmp_path, csv_path)


def connect_trento_event(res_path, initial_type, filename, free_stream_tau,
                         grid_max, grid_step):
    if initial_type == "TRENTo":
        file_path = path.join(res_path, filename)
        initial = np.loadtxt(file_path)
        # Trust the array TRENTo actually produced rather than re-deriving the
        # extent from grid_max. TRENTo's own grid arithmetic disagrees with
        # 2*grid_max/grid_step by one cell for some combinations (e.g. 10.8 fm at
        # 0.15 or 0.30 fm), which made the run die with a shape mismatch. Taking
        # the extent from the array removes that whole class of rounding failure
        # and is self-consistent with FreeStreamer, whose domain is
        # grid_max*(1 - 1/n) -- exactly the cell centres for a grid of step dx.
        n_actual = initial.shape[0]
        grid_max = n_actual*grid_step/2.0
        print("   \U0001F9FE  lattice from TRENTo output: {} cells, dx={:.4f}, "
              "half-width +-{:.3f} fm".format(n_actual, grid_step, grid_max),
              flush=True)
        fs = freestream.FreeStreamer(initial, grid_max, free_stream_tau)
        e = fs.energy_density()
        e_path = path.join(res_path, "e.dat")
        np.savetxt(e_path, e)
        hydro_file = "hydro.dat"
        hydro_out = path.join(res_path, hydro_file)

        n_grid = n_actual
        convert_matrix_to_table(e_path,
                                hydro_out,
                                n_grid=n_grid,
                                lower=-grid_max,
                                upper=grid_max)
        hydro_initial_file = "MUSIC/initial/e.dat"
        if path.exists(hydro_initial_file) or path.islink(hydro_initial_file):
            remove(hydro_initial_file)
        call("ln -s {0:s} {1:s}".format(hydro_out, hydro_initial_file),
             shell=True)


def collect_ipglasma_event(final_results_folder):
    """This function collects the ipglasma results"""
    if path.exists(final_results_folder):
        shutil.rmtree(final_results_folder)
    shutil.move("ipglasma/ipglasma_results", final_results_folder)


def connect_ipglasma_event(res_path, initial_type, filename):
    if initial_type == "IPGlasma":
        hydro_initial_file = "MUSIC/initial/epsilon-u-Hydro.dat"
        if path.islink(hydro_initial_file):
            remove(hydro_initial_file)
        call("ln -s {0:s} {1:s}".format(path.join(res_path, filename),
                                        hydro_initial_file),
             shell=True)
    elif initial_type == "IPGlasma+KoMPoST":
        kompost_initial_file = "kompost/Tmunu.dat"
        if path.islink(kompost_initial_file):
            remove(kompost_initial_file)
        call("ln -s {0:s} {1:s}".format(path.join(res_path, filename),
                                        kompost_initial_file),
             shell=True)


def run_hydro_event(final_results_folder, event_id):
    """This functions run hydro"""
    logo = "\U0001F3B6"
    hydro_folder_name = "hydro_results_{}".format(event_id)
    results_folder = path.join(final_results_folder, hydro_folder_name)
    hydro_success = False

    if path.exists(results_folder):
        print("{}  Hydrodynaimc results {} exist ... ".format(
            logo, hydro_folder_name),
              flush=True)
        # check hydro finishes properly
        try:
            ftmp = open(path.join(results_folder, "run.log"),
                        'r',
                        encoding="utf-8")
            hydro_status = ftmp.readlines()[-1].split()[3]
            ftmp.close()
            if hydro_status == "Finished.":
                print("{} Hydrodynamic run finished properly ... ".format(logo),
                      flush=True)
                hydro_success = True
        except FileNotFoundError:
            hydro_success = False

        if not hydro_success:
            print("{} Hydrodynamic run failed, rerun ... ".format(logo),
                  flush=True)
            shutil.rmtree(results_folder)

    if not hydro_success:
        curr_time = time.asctime()
        print("{}  [{}] Playing MUSIC ... ".format(logo, curr_time), flush=True)
        call("bash ./run_hydro.sh", shell=True)

        # check hydro finishes properly
        ftmp = open("MUSIC/hydro_results/run.log", 'r', encoding="utf-8")
        hydro_status = ftmp.readlines()[-1].split()[3]
        if hydro_status == "Finished.":
            hydro_success = True

        # collect hydro results
        shutil.move("MUSIC/hydro_results", results_folder)

    return (hydro_success, hydro_folder_name)


def run_kompost(final_results_folder, event_id):
    """This functions run KoMPoST simulation"""
    logo = "\U0001F3B6"
    kompost_folder_name = "kompost_results_{}".format(event_id)
    results_folder = path.join(final_results_folder, kompost_folder_name)
    kompost_success = False

    if path.exists(results_folder):
        # check whether KoMPoST has already run or not
        print("{} KoMPoST results {} exist ...".format(logo,
                                                       kompost_folder_name),
              flush=True)
        kompost_success = True
        if kompost_success:
            print("{} no need to rerun KoMPoST".format(logo), flush=True)
        else:
            print("{} KoMPoST simulation failed, rerun ...".format(logo),
                  flush=True)
            shutil.rmtree(results_folder)

    if not kompost_success:
        curr_time = time.asctime()
        print("\U0001F3B6  [{}] Run KoMPoST ... ".format(curr_time), flush=True)
        call("bash ./run_kompost.sh", shell=True)

        kompost_success = True
        if kompost_success:
            # collect results
            shutil.move("kompost/kompost_results", results_folder)

    return (kompost_success, kompost_folder_name)


def prepare_evolution_files_for_photon(final_results_folder, hydro_folder_name):
    """This function prepares hydro evolution file for photon radiation"""
    evoFileName = "evolution_all_xyeta.dat"
    evo_file = path.join(final_results_folder, hydro_folder_name, evoFileName)
    photonFolderPath = path.join('photonEmission_hydroInterface', 'results')
    if path.exists(photonFolderPath):
        shutil.rmtree(photonFolderPath)
    mkdir(photonFolderPath)
    call("ln -s {0:s} {1:s}".format(path.abspath(evo_file),
                                    path.join(photonFolderPath, evoFileName)),
         shell=True)
    shutil.copy(
        path.join(final_results_folder, hydro_folder_name, "music_input"),
        photonFolderPath)


def run_photon(final_results_folder, event_id):
    """This functions run photon radiation"""
    logo = "\U0001F3B6"
    photon_folder_name = "photon_results_{}".format(event_id)
    results_folder = path.join(final_results_folder, photon_folder_name)
    photon_success = False

    if path.exists(results_folder):
        # check whether photon has already run or not
        print("{} photon results {} exist ...".format(logo, photon_folder_name),
              flush=True)
        photon_success = True
        if photon_success:
            print("{} no need to rerun photon".format(logo), flush=True)
        else:
            print("{} photon radiation failed, rerun ...".format(logo),
                  flush=True)
            shutil.rmtree(results_folder)

    if not photon_success:
        curr_time = time.asctime()
        print("\U0001F3B6  [{}] Run photon ... ".format(curr_time), flush=True)
        call("bash ./run_photon.sh", shell=True)

        photon_success = True
        if photon_success:
            # collect results
            shutil.move("photonEmission_hydroInterface/results", results_folder)

    return (photon_success, photon_folder_name)


def compute_ic_extent(e_path, grid_max, grid_step):
    """Fractional energy-density radii of the initial condition, in fm."""
    eps = np.loadtxt(e_path, comments='#')
    if eps.ndim != 2 or eps.shape[0] != eps.shape[1] or eps.sum() <= 0:
        return None
    n = eps.shape[0]
    step = (2.0*grid_max)/n
    x = np.linspace(-grid_max + step/2.0, grid_max - step/2.0, n)
    X, Y = np.meshgrid(x, x, indexing='xy')
    r = np.hypot(X, Y).ravel()
    order = np.argsort(r)
    cum = np.cumsum(eps.ravel()[order])/eps.sum()
    out = {
        'n_cells': int(n),
        'grid_max': float(grid_max),
        'grid_step': float(step)
    }
    for frac in (0.90, 0.95, 0.99, 0.999):
        idx = int(np.searchsorted(cum, frac))
        out['R{}'.format(int(frac*1000))] = float(r[order][idx])
    # RMS radius: the standard size measure, and the one expected to track the
    # freeze-out extent better than a cumulative radius, since it weights the
    # bulk of the density rather than the tail.
    e_rav = eps.ravel()
    out['R_rms'] = float(np.sqrt((e_rav*r**2).sum()/e_rav.sum()))
    return out


def compute_surface_extent(hydro_folder):
    """Transverse extent of the Cooper-Frye freeze-out surface, in fm.

    MUSIC writes energy density in column 0 and the transverse coordinates
    (x, y) in columns 1 and 2. This is the quantity that actually sets how
    large the transverse box has to be.
    """
    files = glob(path.join(hydro_folder, "surface*.dat"))
    if not files:
        return None
    surf = np.loadtxt(files[0])
    if surf.ndim != 2 or surf.shape[1] < 3:
        return None
    x, y = surf[:, 1], surf[:, 2]
    # MUSIC names the file surface_eps_<e_fo>.dat, where e_fo is the energy
    # density at freeze-out, not a time.
    e_fo = None
    stem = path.basename(files[0])
    if stem.startswith('surface_eps_'):
        try:
            e_fo = float(stem[len('surface_eps_'):].replace('.dat', ''))
        except ValueError:
            pass
    r = np.hypot(x, y)
    w = surf[:, 0]
    wsum = w.sum()
    out = {
        'n_surface_cells': int(surf.shape[0]),
        'surface_file': stem,
        'e_fo_GeV_fm3': e_fo,
        'max_abs_x': float(np.abs(x).max()),
        'max_abs_y': float(np.abs(y).max()),
        'max_r': float(r.max()),
    }
    # max_r is a max over cells and so is sensitive to a single stray cell;
    # carry an RMS and a high quantile alongside it as robust summaries.
    if wsum > 0:
        out['r_rms'] = float(np.sqrt((w*r**2).sum()/wsum))
    out['r_p999'] = float(np.percentile(r, 99.9))
    return out


def parse_iss_sampling(run_log):
    """Expected particle yields per iSS sample, from the iSS log.

    iSS does not report how many resamplings it performed, and it will not print
    "number of events: ..." at any verbosity reachable from the parameter file
    (the echo level is a compile-time module parameter). The log does, however,
    print one "dN=<x>" line per species giving the expected number of that
    species per sample, so summing them gives the expected per-sample yield E.

    These are PRE-resonance-decay yields, so they sit a factor ~1.4 below the
    final per-sample yield; the ratio is slowly varying, so E is a reliable
    proxy for recovering the sample count but not exact on its own. Both E and
    the final particle count are stored so the count can be recomputed later
    with a better decay-inflation factor.
    """
    total = 0.0
    per_pid = {}
    cur_pid = None
    try:
        with open(run_log, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                m = re.search(r'Monte-carlo index:\s*(-?\d+)', line)
                if m:
                    cur_pid = int(m.group(1))
                m2 = re.search(r'dN=([0-9]*\.?[0-9]+(?:[eE][-+]?\d+)?)', line)
                if m2 and cur_pid is not None:
                    try:
                        val = float(m2.group(1))
                    except ValueError:
                        continue
                    total += val
                    per_pid[cur_pid] = per_pid.get(cur_pid, 0.0) + val
    except OSError:
        return None, {}
    return (total if total > 0 else None), per_pid


def collect_flow_sample_counts(final_results_folder, event_id, row):
    """Record the freeze-out sample count and particle counts, exactly.

    The toolkit writes a totals row [99, total_N, total_number_of_events, 0, 0]
    at the end of every particle_<pid>_vndata_*.dat file, with the comment "this
    quantity is useful when one wants to reconst the Qn vectors". The third entry
    IS the number of iSS resamplings, so no estimate is needed: verified by
    decoding particle_list.bin directly, which contains exactly that many records
    (5740 records, 893926 particles, 155.7 per resampling).
    """
    spvn_h5 = path.join(final_results_folder,
                        'spvn_results_{}.h5'.format(event_id))
    if not path.exists(spvn_h5):
        return
    try:
        with h5py.File(spvn_h5, 'r') as h:
            found = []
            h.visititems(lambda name, obj: found.append(name)
                         if isinstance(obj, h5py.Dataset) else None)
            for name in found:
                base = path.basename(name)
                if base.startswith('particle_211_vndata_y_'):
                    data = h[name][:]
                    if data.ndim == 2 and data.shape[0] > 0:
                        tot = data[-1]
                        row['n_pions'] = int(tot[1])
                        row['n_iss_resamplings'] = int(tot[2])
                        if row['n_iss_resamplings'] > 0:
                            row['pions_per_resampling'] = round(
                                row['n_pions']/row['n_iss_resamplings'], 4)
                    break
    except (OSError, ValueError, IndexError, KeyError):
        return


def append_flow_sample_counts(final_results_folder, event_id):
    """Append the iSS sample-count ingredients to the per-event diagnostic CSV."""
    import csv
    fname = path.join(final_results_folder,
                      'grid_extent_{}.csv'.format(event_id))
    if not path.exists(fname):
        return
    with open(fname, 'r', newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return
    row = {}
    collect_flow_sample_counts(final_results_folder, event_id, row)
    if not row:
        return
    for r in rows:
        r.update(row)
    fields = list(rows[0].keys())
    with open(fname, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)


def prune_spvn_output(spvn_folder, keep_rapidity_windows=1):
    """Drop flow output we do not need for 2D boost-invariant runs.

    Rapidty carries no physics here, so the 141-rapidity-bin tables are pure
    storage. The per-species v_n vs pT arrays, the yields and the all-charged
    vectors are kept; the (rapidity, pT, v_n) table, the redundant rapidity
    windows and the space-time eccentricity diagnostics are dropped.
    """
    if not path.isdir(spvn_folder):
        return
    dropped = kept = 0
    files = glob(path.join(spvn_folder, '*.dat'))
    # Boost-invariant runs produce exactly one analysis we want: the identified
    # species with every particle kept and the yield normalised by the sampled
    # rapidity width. Those files carry a _boostinv tag, and everything else the
    # toolkit writes - the fixed experimental acceptances, the charged-hadron
    # per-pseudorapidity references, the space-time diagnostics - is noise for
    # this campaign, so keep only the tagged files.
    has_boostinv = any('_boostinv.dat' in f for f in files)
    for fname in files:
        base = path.basename(fname)
        if has_boostinv:
            drop = '_boostinv.dat' not in base or not base.endswith('.dat')
            if drop:
                try:
                    remove(fname)
                    dropped += 1
                except OSError:
                    pass
            else:
                kept += 1
            continue
        drop = ('pTeta_distribution' in base or '_evo_' in base
                or 'inverse_Reynolds' in base or 'meanpT_estimators' in base)
        if not drop and '_vndata_diff_eta_' in base:
            drop = True
        # keep the unidentified/all-charged references; the identified-species
        # _vndata_eta_ arrays duplicate the _vndata_diff_y_ ones and go
        if not drop and base.startswith('particle_9999_vndata_eta_'):
            # seven hard-coded rapidity windows; in 2D boost-invariant runs only
            # one is meaningful, so keep the mid-rapidity one the validator wants
            drop = '_eta_-0.5_0.5.dat' not in base
        if (not drop and '_vndata_eta_' in base
                and not base.startswith('particle_9999_')
                and not base.startswith('particle_99999_')):
            drop = True
        if drop:
            try:
                remove(fname)
                dropped += 1
            except OSError:
                pass
        else:
            kept += 1
    if dropped:
        print('\U0001F5D2  pruned {} flow files ({} kept)'.format(
            dropped, kept),
              flush=True)


def write_grid_extent_diagnostic(final_results_folder,
                                 event_id,
                                 hydro_folder,
                                 e_path,
                                 grid_max,
                                 grid_step,
                                 music_seconds=None):
    """Record how much transverse space this event actually needed.

    Emits one small CSV per event so a whole OSG batch can be collected cheaply
    and turned into the margin rule for an adaptive grid.
    """
    import csv

    row = {'event_id': event_id}

    summary = path.join(final_results_folder,
                        'trento_event_summary_{}.txt'.format(event_id))
    if path.exists(summary):
        try:
            with open(summary, 'r', encoding='utf-8') as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 2 and parts[0] == 'impact_parameter':
                        row['b'] = parts[1]
                    if len(parts) >= 2 and parts[0] == 'mult':
                        row['mult'] = parts[1]
        except OSError:
            pass

    try:
        ic = compute_ic_extent(e_path, grid_max, grid_step)
        if ic:
            row.update(ic)
    except (OSError, ValueError):
        pass

    # R_rms of the TRENTo output itself, before free-streaming. This is what the
    # adaptive sizing rule consumes, because it is available before MUSIC starts.
    try:
        src = path.join(final_results_folder,
                        'trento_results_{}'.format(event_id),
                        'initial_condition', '0.dat')
        if path.exists(src):
            flat = np.loadtxt(src).ravel()
            n = int(round(math.sqrt(flat.size)))
            if n*n == flat.size:
                L = read_input_value(path.join('TRENTo', 'input'), 'grid-max')
                L = float(L) if L is not None else grid_max
                rms = ic_rms_from_flat(flat, L, grid_step)
                if rms is not None:
                    row['R_rms_trento'] = rms
                    row['trento_grid_max'] = L
    except (OSError, ValueError):
        pass

    try:
        sf = compute_surface_extent(
            path.join(final_results_folder, hydro_folder))
        if sf:
            row.update(sf)
    except (OSError, ValueError):
        pass

    if music_seconds is not None:
        row['music_seconds'] = round(float(music_seconds), 1)

    out = path.join(final_results_folder, 'grid_extent_{}.csv'.format(event_id))
    try:
        with open(out, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=list(row.keys()))
            writer.writeheader()
            writer.writerow(row)
    except OSError:
        pass


def prepare_surface_files_for_urqmd(final_results_folder, hydro_folder_name,
                                    n_urqmd, afterburner_type):
    """This function prepares hydro surface for hadronic cascade"""
    sub_ev_prefix = "SMASHev" if afterburner_type == "SMASH" else "UrQMDev"
    surface_file = glob(
        path.join(final_results_folder, hydro_folder_name, "surface*.dat"))
    spectatorFileList = glob(path.join(final_results_folder, "spectator*.dat"))
    spectatorFile = ""
    if spectatorFileList != []:
        spectatorFile = spectatorFileList[0]
    if stat(surface_file[0]).st_size == 0:
        return False
    for iev in range(n_urqmd):
        hydro_surface_folder = "{0}_{1:d}/hydro_event".format(
            sub_ev_prefix, iev)
        if path.exists(hydro_surface_folder):
            shutil.rmtree(hydro_surface_folder)
        mkdir(hydro_surface_folder)
        call("ln -s {0:s} {1:s}".format(
            path.abspath(surface_file[0]),
            path.join(hydro_surface_folder, "surface.dat")),
             shell=True)
        shutil.copy(
            path.join(final_results_folder, hydro_folder_name, "music_input"),
            hydro_surface_folder)
        if spectatorFile != "":
            shutil.copy(spectatorFile,
                        path.join(hydro_surface_folder, "spectators.dat"))
    return True


def run_urqmd_event(event_id):
    """This function runs hadornic afterburner"""
    call("bash ./run_afterburner.sh {0:d}".format(event_id), shell=True)


def run_urqmd_shell(n_urqmd, final_results_folder, event_id, para_dict,
                    startTime, checkPointFileName, afterburner_type):
    """This function runs hadronic afterburner events in parallel batches."""
    logo = "\U0001F5FF"
    sub_ev_prefix = "SMASHev" if afterburner_type == "SMASH" else "UrQMDev"
    results_dir = "SMASH_results" if afterburner_type == "SMASH" else "UrQMD_results"
    urqmdResults = "particle_list_{}.bin".format(event_id)
    results_folder = path.join(final_results_folder, urqmdResults)
    urqmd_success = False

    if path.exists(results_folder):
        print("{} afterburner results {} exist ... ".format(logo, urqmdResults),
              flush=True)
        urqmd_success = True

    if not urqmd_success:
        curr_time = time.asctime()
        if para_dict["compute_polarization"]:
            spin_folder_name = "spin_results_{}".format(event_id)
            spin_folder = path.join(final_results_folder, spin_folder_name)
            if path.exists(spin_folder):
                print("{} spin results {} exist ... ".format(logo, spin_folder),
                      flush=True)
            else:
                print("{}  [{}] Running spin calculations ... ".format(
                    logo, curr_time),
                      flush=True)
                call("bash ./run_spinPol.sh {}".format(n_urqmd), shell=True)
                shutil.move(
                    "{0}_{1}/iSS/results".format(sub_ev_prefix, n_urqmd),
                    spin_folder)
                if para_dict["check_point_flag"]:
                    checkPoint(startTime, checkPointFileName,
                               final_results_folder)

        max_workers = max(1, int(para_dict.get("num_threads", 1)))
        n_workers = max(1, min(n_urqmd, max_workers))
        print(
            "{}  [{}] Running afterburner with {} workers for {} samples ... ".
            format(logo, curr_time, n_workers, n_urqmd),
            flush=True)
        with Pool(processes=n_workers) as pool1:
            pool1.map(run_urqmd_event, range(n_urqmd))

        urqmdResFile = "particle_list.bin"
        for iev in range(1, n_urqmd):
            source_file = "{0}_{1}/{2}/{3}".format(sub_ev_prefix, iev,
                                                   results_dir, urqmdResFile)
            if not path.exists(source_file):
                raise FileNotFoundError(
                    f"Missing UrQMD output file: {source_file}. "
                    "Check run_afterburner.sh / iSS / OSCAR / UrQMD logs.")
            call("cat {0} >> {1}_0/{2}/{3}".format(source_file, sub_ev_prefix,
                                                   results_dir, urqmdResFile),
                 shell=True)
            remove(source_file)
        urqmd_success = True
        primary_file = "{0}_0/{1}/{2}".format(sub_ev_prefix, results_dir,
                                              urqmdResFile)
        if not path.exists(primary_file):
            raise FileNotFoundError(
                f"Missing primary UrQMD output file: {primary_file}. "
                "Check the first afterburner subevent logs.")
        shutil.move(primary_file, results_folder)

    return (urqmd_success, results_folder)


def run_smash_analysis(smash_file_path,
                       final_results_folder,
                       event_id,
                       analysis_mode="2D"):
    """Run external SMASH analysis script and collect outputs"""
    analysis_folder = path.join(final_results_folder,
                                f"smash_results_{event_id}")

    if path.exists(analysis_folder):
        shutil.rmtree(analysis_folder)
    mkdir(analysis_folder)

    curr_time = time.asctime()
    print(
        f"\U0001F52C [{curr_time}] Running SMASH analysis on {smash_file_path} ... ",
        flush=True)

    ret = call(
        f"python3 analysis_cli_optimized.py "
        f"--mode {analysis_mode} "
        f"--format SMASH "
        f"--file {smash_file_path} ",
        shell=True)

    if ret != 0:
        print(f"\U0000274C SMASH analysis script failed. ", flush=True)
        return False

    generate_npz = smash_file_path + ".npz"
    if not path.exists(generate_npz):
        print(
            f"\U0000274C Expected analysis output not found: {generate_npz}. ",
            flush=True)
        return False

    final_npz = path.join(analysis_folder, f"smash_analysis_{event_id}.npz")
    shutil.move(generate_npz, final_npz)

    curr_time = time.asctime()
    print(
        f"\U0001F52C [{curr_time}] Finished SMASH analysis, results saved to {final_npz} ... ",
        flush=True)

    return True


def run_spvn_analysis(urqmd_file_path,
                      n_threads,
                      final_results_folder,
                      event_id,
                      para_dict_=None):
    """This function runs analysis"""
    final_results_folder = path.join(final_results_folder,
                                     "spvn_results_{0:s}".format(event_id))
    if path.exists(final_results_folder):
        shutil.rmtree(final_results_folder)
    spvn_folder = "hadronic_afterburner_toolkit/results"
    if path.exists(spvn_folder):
        shutil.rmtree(spvn_folder)
    mkdir(spvn_folder)
    call("ln -s {0:s} {1:s}".format(path.abspath(urqmd_file_path),
                                    path.join(spvn_folder,
                                              "particle_list.bin")),
         shell=True)
    # finally collect results
    curr_time = time.asctime()
    print(f"\U0001F3CD  [{curr_time}] Running spvn analysis ... ", flush=True)

    call("bash ./run_analysis_spvn.sh", shell=True)

    if para_dict_.get('prune_flow_output', True):
        prune_spvn_output(spvn_folder)

    curr_time = time.asctime()
    print(f"\U0001F3CD  [{curr_time}] Finished spvn analysis ... ", flush=True)

    call(f"rm {spvn_folder}/particle_list.bin", shell=True)
    shutil.move(spvn_folder, final_results_folder)


def check_an_event_is_good(event_folder):
    """This function checks the given event contains all required files"""
    # Only require files that survive pruning: the identified-species v_n vs pT
    # arrays and the unidentified reference.
    required_patterns = [
        'particle_211_vndata_diff_y_*_boostinv.dat',
        'particle_321_vndata_diff_y_*_boostinv.dat',
        'particle_2212_vndata_diff_y_*_boostinv.dat',
    ]
    event_file_list = [
        path.basename(f) for f in glob(path.join(event_folder, "*"))
    ]
    for pattern in required_patterns:
        if not any(fnmatch(name, pattern) for name in event_file_list):
            print("event {} is bad, missing {} ...".format(
                event_folder, pattern),
                  flush=True)
            return False
    return True


def zip_results_into_hdf5(final_results_folder, event_id, para_dict):
    """This function combines all the results into hdf5"""
    results_name = f"spvn_results_{event_id}"
    initial_state_filelist1 = [
        f'NcollList{event_id}.dat',
        f'NpartList{event_id}.dat',
        f'NpartdNdy-t0.6-{event_id}.dat',
        f'NgluonEstimators{event_id}.dat',
        f'usedParameters{event_id}.dat',
    ]
    initial_state_filelist2 = [
        f'epsilon-u-Hydro-TauHydro-{event_id}.dat',
    ]
    glauber_filelist = [
        f"strings_{event_id}.dat",
        f"spectators_{event_id}.dat",
        f"participants_event_{event_id}.dat",
        "ed_etas_distribution_*.dat",
        "nB_etas_distribution_*.dat",
        "ecc_ed_*.dat",
    ]

    pre_equilibrium_filelist = [
        "{}.music_init_flowNonLinear_pimunuTransverse.txt".format(
            para_dict['kompost_filename'])
    ]
    hydro_info_filepattern = [
        "eccentricities_evo_*.dat",
        "momentum_anisotropy_*.dat",
        "meanpT_estimators_*.dat",
        "inverse_Reynolds_number_eta_*.dat",
        "averaged_phase_diagram_trajectory_eta_*.dat",
        "global_conservation_laws.dat",
        "global_angular_momentum_*.dat",
        "vorticity_evo_*.dat",
        "FO_nBvseta.dat",
    ]
    photon_filepattern = ['*_Spvn*.dat']
    spin_filepattern = [
        "Smu_dpTdphi_*.dat", "Smu_phi_*.dat", "Smu_pT_*.dat", "Smu_y_*.dat",
        "Smu_Thermal_*.dat", "Rspin_*.dat"
    ]

    hydrofolder = path.join(final_results_folder, f"hydro_results_{event_id}")
    spvnfolder = path.join(final_results_folder, results_name)
    photonFolder = path.join(final_results_folder, f"photon_results_{event_id}")

    spinfolder = path.join(final_results_folder, f"spin_results_{event_id}")

    status = check_an_event_is_good(spvnfolder)
    if status:
        curr_time = time.asctime()
        print("[{}] {} is good, converting results to hdf5".format(
            curr_time, spvnfolder),
              flush=True)

        if (para_dict['initial_condition'] == "self"
                or para_dict['initial_condition'] == "fixCentrality"):
            # save initial conditions
            if "IPGlasma" in para_dict['initial_type']:
                initial_folder = path.join(final_results_folder,
                                           f"ipglasma_results_{event_id}")
                for inifilename in initial_state_filelist1:
                    inifile = path.join(initial_folder, inifilename)
                    if path.isfile(inifile):
                        shutil.move(inifile, spvnfolder)
                if para_dict['save_ipglasma']:
                    for inifilename in initial_state_filelist2:
                        inifile = path.join(initial_folder, inifilename)
                        if path.isfile(inifile):
                            shutil.move(inifile, spvnfolder)
            if "3DMCGlauber" in para_dict['initial_type']:
                for iniFilenamePattern in glauber_filelist:
                    iniFileList = glob(
                        path.join(final_results_folder, iniFilenamePattern))
                    for iniFile in iniFileList:
                        if path.isfile(iniFile):
                            shutil.move(iniFile, spvnfolder)

            # save pre-equilibrium results
            if (para_dict['initial_type'] == "IPGlasma+KoMPoST"
                    and para_dict['save_kompost']):
                preeq_folder = path.join(final_results_folder,
                                         f"kompost_results_{event_id}")
                for prefilename in pre_equilibrium_filelist:
                    prefile = path.join(preeq_folder, prefilename)
                    if path.isfile(prefile):
                        shutil.move(prefile, spvnfolder)

        # save hydro evolution information
        for ipattern in hydro_info_filepattern:
            hydro_info_list = glob(path.join(hydrofolder, ipattern))
            for ihydrofile in hydro_info_list:
                if path.isfile(ihydrofile):
                    shutil.move(ihydrofile, spvnfolder)

        # save photon results
        if para_dict['compute_photons']:
            for ipattern in photon_filepattern:
                photonFileList = glob(path.join(photonFolder, ipattern))
                for photonFile_i in photonFileList:
                    if path.isfile(photonFile_i):
                        shutil.move(photonFile_i, spvnfolder)

        # save spin informaiton
        if para_dict["compute_polarization"]:
            for ipattern in spin_filepattern:
                spin_list = glob(path.join(spinfolder, ipattern))
                for ispinfile in spin_list:
                    if path.isfile(ispinfile):
                        shutil.move(ispinfile, spvnfolder)

        hf = h5py.File(f"{results_name}.h5", "w")
        gtemp = hf.create_group(f"{results_name}")
        file_list = glob(path.join(spvnfolder, "*"))
        for file_path in file_list:
            file_name = file_path.split("/")[-1]
            if "usedParameters" in file_name:
                parafile = open(file_path)
                for iline, rawline in enumerate(parafile.readlines()):
                    paraline = rawline.strip('\n')
                    gtemp.attrs.create(f"{iline}", np.bytes_(paraline))
            else:
                dtemp = np.loadtxt(file_path, dtype="float32")
                h5data = gtemp.create_dataset(f"{file_name}",
                                              data=dtemp,
                                              compression="gzip",
                                              compression_opts=9)
                # save header
                ftemp = open(file_path, "r")
                header_text = str(ftemp.readline())
                ftemp.close()
                if header_text.startswith("#"):
                    h5data.attrs.create("header", np.bytes_(header_text))
        hf.close()
        shutil.move(f"{results_name}.h5", final_results_folder)
        shutil.rmtree(spvnfolder, ignore_errors=True)
    else:
        print(f"{spvnfolder} is broken, skipped", flush=True)
    return (status)


def remove_unwanted_outputs(final_results_folder, event_id, para_dict):
    """
        This function removes all hydro surface file and UrQMD results
        if they are unwanted to save space

    """
    if not para_dict["save_ipglasma"]:
        ipglasmafolder = path.join(final_results_folder,
                                   "ipglasma_results_{}".format(event_id))
        shutil.rmtree(ipglasmafolder, ignore_errors=True)

    if not para_dict["save_kompost"]:
        kompostfolder = path.join(final_results_folder,
                                  "kompost_results_{}".format(event_id))
        shutil.rmtree(kompostfolder, ignore_errors=True)

    if not para_dict["save_hydro"]:
        hydrofolder = path.join(final_results_folder,
                                "hydro_results_{}".format(event_id))
        shutil.rmtree(hydrofolder, ignore_errors=True)

    if para_dict["compute_polarization"]:
        spinfolder = path.join(final_results_folder,
                               "spin_results_{}".format(event_id))
        shutil.rmtree(spinfolder, ignore_errors=True)

    if not para_dict["save_urqmd"]:
        urqmd_results_name = "particle_list_{}.bin".format(event_id)
        remove(path.join(final_results_folder, urqmd_results_name))

    if para_dict["compute_photons"]:
        photonfolder = path.join(final_results_folder,
                                 "photon_results_{}".format(event_id))
        shutil.rmtree(photonfolder, ignore_errors=True)

    # Ensure any per-event copies of the isobar seed are removed from
    # the final results directory to save space. Skip anything living
    # under a `shared_seeds` directory.
    try:
        for seed_pattern in ("nucleon-seeds_*.hdf", "nucleon-seeds.hdf"):
            for seed_path in glob(path.join(final_results_folder,
                                            seed_pattern)):
                try:
                    if "/shared_seeds/" in path.abspath(seed_path).replace(
                            '\\\\', '/'):
                        continue
                    remove(seed_path)
                except OSError:
                    pass
    except Exception:
        pass


def checkPoint(startTime, checkPointFileName, finalResultsFolder):
    checkPointTime = time.time()
    if checkPointTime - startTime > 43200:
        # trigger the checkpoint when the simulation runs longer than 12 hours
        if path.exists(checkPointFileName):
            remove(checkPointFileName)
        tar = tarfile.open(checkPointFileName, 'w:gz')
        tar.add(finalResultsFolder)
        tar.close()
        sys.exit(85)


def main(para_dict_):
    """This is the main function"""
    startTime = time.time()
    initial_condition = para_dict_['initial_condition']
    initial_type = para_dict_['initial_type']
    num_threads = para_dict_['num_threads']
    n_urqmd = para_dict_['n_urqmd']
    curr_time = time.asctime()
    print("\U0001F3CE  [{}] Number of threads: {}".format(
        curr_time, num_threads),
          flush=True)

    idx0 = para_dict_['hydro_id0']
    nev = para_dict_['n_hydro']
    exitErrorTrigger = False
    exitErrorTriggerInitial = False
    for iev in range(nev):
        curr_time = time.asctime()

        event_id = str(iev + idx0)
        if (para_dict_['initial_condition'] != "self"
                and para_dict_['initial_condition'] != "fixCentrality"):
            initial_database_name = (
                initial_condition.split("/")[-1].split(".h5")[0])
            event_id = initial_database_name + "_" + event_id

        final_results_folder = "EVENT_RESULTS_{}".format(event_id)

        # setup OSG checkpoint file
        CHECKPOINT_FILENAME = "{}.tar.gz".format(final_results_folder)
        try:
            tar = tarfile.open("{}".format(CHECKPOINT_FILENAME), 'r:gz')
            tar.extractall()
            tar.close()
            # remove the tar file to save disk space
            remove(CHECKPOINT_FILENAME)
        except FileNotFoundError:
            pass

        if path.exists(final_results_folder):
            print("{} exists ...".format(final_results_folder), flush=True)
            results_file = path.join(final_results_folder,
                                     "spvn_results_{}.h5".format(event_id))
            status = False
            if path.exists(results_file):
                status = True
            else:
                spvnfolder = path.join(final_results_folder,
                                       "spvn_results_{}".format(event_id))
                if path.exists(spvnfolder):
                    status = check_an_event_is_good(spvnfolder)
            if status:
                print(
                    "{} finished properly. No need to rerun.".format(event_id),
                    flush=True)
                continue
            print("Rerun {} ...".format(final_results_folder), flush=True)
        else:
            mkdir(final_results_folder)
        print("[{}] Generate initial condition ... ".format(curr_time),
              flush=True)

        initStauts, ifile = get_initial_condition(initial_condition,
                                                  initial_type, iev, idx0 + iev,
                                                  para_dict_['seed_add'],
                                                  final_results_folder,
                                                  para_dict_)
        if not initStauts:
            exitErrorTriggerInitial = True
            continue

        if initial_type == "3DMCGlauber_consttau":
            filename = ifile.split("/")[-1]
            filepath = initial_condition
            shutil.copy(path.join(filepath, filename),
                        "MUSIC/initial/initial_TA.dat")
            shutil.copy(path.join(filepath, re.sub("TA", "TB", filename)),
                        "MUSIC/initial/initial_TB.dat")

        if initial_type == "IPGlasma+KoMPoST":
            kompost_success, kompost_folder_name = run_kompost(
                final_results_folder, event_id)
            hydro_initial_file = "MUSIC/initial/epsilon-u-Hydro.dat"
            if path.islink(hydro_initial_file):
                remove(hydro_initial_file)
            call("ln -s {0:s} {1:s}".format(
                path.join(path.abspath(final_results_folder),
                          kompost_folder_name,
                          (para_dict_['kompost_filename']
                           + ".music_init_flowNonLinear_pimunuTransverse.txt")),
                hydro_initial_file),
                 shell=True)

        # first run hydro
        t_hydro_start = time.time()
        hydro_success, hydro_folder_name = run_hydro_event(
            final_results_folder, event_id)

        if not hydro_success:
            # if hydro didn't finish properly, just skip this event
            print("\U000026D4  {} did not finsh properly, skipped.".format(
                hydro_folder_name),
                  flush=True)
            exitErrorTrigger = True
            continue

        # How much transverse space did this event actually use? Feeds the
        # adaptive-grid margin study. Runs before any cleanup, and the surface
        # is present regardless of save_hydro_surfaces.
        try:
            write_grid_extent_diagnostic(
                final_results_folder,
                event_id,
                hydro_folder_name,
                path.join(final_results_folder,
                          'trento_results_{}'.format(event_id), 'e.dat'),
                para_dict_['free_stream_grid_max'],
                para_dict_['free_stream_grid_step'],
                music_seconds=time.time() - t_hydro_start)
        except Exception:
            import traceback
            print('grid extent diagnostic failed:\n{}'.format(
                traceback.format_exc()),
                  flush=True)

        if (initial_type == "3DMCGlauber_dynamical"
                and (initial_condition == "self"
                     or initial_condition == "fixCentrality")):
            # save the initial condition
            shutil.move(
                "MUSIC/initial/strings.dat",
                path.join(final_results_folder, hydro_folder_name,
                          "strings_{}.dat".format(event_id)))

        if para_dict_["check_point_flag"]:
            checkPoint(startTime, CHECKPOINT_FILENAME, final_results_folder)

        if para_dict_['compute_photons']:
            # if hydro finishes properly, we continue to do photon radiation
            prepare_evolution_files_for_photon(final_results_folder,
                                               hydro_folder_name)
            photon_success, photon_folder_name = run_photon(
                final_results_folder, event_id)
            if not photon_success:
                exitErrorTrigger = True
                continue
            if not para_dict["save_hydro"]:
                evoFileName = path.join(final_results_folder, hydro_folder_name,
                                        "evolution_all_xyeta.dat")
                shutil.rmtree(evoFileName, ignore_errors=True)
            if para_dict_["check_point_flag"]:
                checkPoint(startTime, CHECKPOINT_FILENAME, final_results_folder)

        nUrQMDFolder = n_urqmd
        if para_dict_["compute_polarization"]:
            nUrQMDFolder += 1
        # if hydro finishes properly, we continue to do hadronic transport
        status_success = prepare_surface_files_for_urqmd(
            final_results_folder, hydro_folder_name, nUrQMDFolder,
            para_dict_['afterburner_type'])
        if not status_success:
            exitErrorTrigger = True
            continue

        # then run afterburner events in parallel
        urqmd_success, urqmd_file_path = run_urqmd_shell(
            n_urqmd, final_results_folder, event_id, para_dict_, startTime,
            CHECKPOINT_FILENAME, para_dict_['afterburner_type'])
        if not urqmd_success:
            print("\U000026D4  {} did not finsh properly, skipped.".format(
                urqmd_file_path),
                  flush=True)
            continue

        #########################################################################################
        if para_dict_['afterburner_type'] == "SMASH":
            curr_time = time.asctime()
            print(
                f"\U0001F4BE [{curr_time}] SMASH is finished. "
                f"Binary file saved in: {urqmd_file_path}",
                flush=True)
            status = run_smash_analysis(urqmd_file_path,
                                        final_results_folder,
                                        event_id,
                                        analysis_mode="2D")
        ##########################################################################################

        else:

            # finally collect results
            run_spvn_analysis(urqmd_file_path, num_threads,
                              final_results_folder, event_id, para_dict_)

            # zip results into a hdf5 database
            status = zip_results_into_hdf5(final_results_folder, event_id,
                                           para_dict_)

            # the freeze-out sample count is only knowable once iSS has run and
            # the flow analysis has counted the particles, so it is appended to
            # the per-event diagnostic here rather than at the grid stage
            try:
                append_flow_sample_counts(final_results_folder, event_id)
            except Exception:
                pass

        # remove the unwanted outputs if event is finished properly
        if status:
            remove_unwanted_outputs(final_results_folder, event_id, para_dict_)

    if exitErrorTriggerInitial:
        sys.exit(71)

    if exitErrorTrigger:
        sys.exit(73)

    # Final cleanup: remove any top-level per-job copies of isobar seed files
    # left in the current working directory (e.g., TestDP0). Do not remove
    # the canonical copy under `shared_seeds`.
    try:
        cwd = path.abspath('.')
        for seed_pattern in ("nucleon-seeds_*.hdf", "nucleon-seeds.hdf"):
            for seed_path in glob(path.join(cwd, seed_pattern)):
                try:
                    if "/shared_seeds/" in path.abspath(seed_path).replace(
                            '\\\\', '/'):
                        continue
                    remove(seed_path)
                    print(f"Removed top-level seed file: {seed_path}")
                except OSError:
                    pass
    except Exception:
        pass


if __name__ == "__main__":
    try:
        INITIAL_CONDITION_TYPE = str(sys.argv[1])
        INITIAL_CONDITION_DATABASE = str(sys.argv[2])
        N_HYDRO_EVENTS = int(sys.argv[3])
        HYDRO_EVENT_ID0 = int(sys.argv[4])
        N_URQMD = int(sys.argv[5])
        N_THREADS = int(sys.argv[6])
        SAVE_IPGLASMA = (sys.argv[7].lower() == "true")
        SAVE_KOMPOST = (sys.argv[8].lower() == "true")
        SAVE_HYDRO = (sys.argv[9].lower() == "true")
        SAVE_URQMD = (sys.argv[10].lower() == "true")
        SEED_ADD = int(sys.argv[11])
        COMP_POLARIZATION = (sys.argv[12].lower() == "true")
        COMP_PHOTONS = (sys.argv[13].lower() == "true")
        CHECK_POINT = (sys.argv[14].lower() == "true")
        AFTERBURNER_TYPE = str(sys.argv[15])
    except IndexError:
        print_usage()
        sys.exit(0)

    try:
        KOMPOST_FILENAME = str(sys.argv[16])
    except IndexError:
        KOMPOST_FILENAME = "ekt_tIn01_tOut08"

    try:
        TRENTO_OUTPUT = str(sys.argv[17])
    except IndexError:
        TRENTO_OUTPUT = "test_path.dat"

    try:
        FREE_STREAM_TAU = float(sys.argv[18])
    except IndexError:
        FREE_STREAM_TAU = 1.0

    try:
        FREE_STREAM_GRID_MAX = float(sys.argv[19])
    except IndexError:
        FREE_STREAM_GRID_MAX = 10.0

    try:
        FREE_STREAM_GRID_STEP = float(sys.argv[20])
    except IndexError:
        FREE_STREAM_GRID_STEP = 0.2

    # Optional: size the transverse box per event from the TRENTo initial
    # condition. Off unless explicitly enabled, so existing runs are unchanged.
    try:
        ADAPTIVE_GRID = (sys.argv[21].lower() == "true")
    except IndexError:
        ADAPTIVE_GRID = False

    known_initial_types = [
        "IPGlasma",
        "IPGlasma+KoMPoST",
        "3DMCGlauber_dynamical",
        "3DMCGlauber_participants",
        "3DMCGlauber_consttau",
        "TRENTo",
    ]
    if INITIAL_CONDITION_TYPE not in known_initial_types:
        print("\U0001F6AB  "
              + "Do not recognize the initial condition type: {}".format(
                  INITIAL_CONDITION_TYPE),
              flush=True)
        sys.exit(1)

    para_dict = {
        'initial_condition': INITIAL_CONDITION_DATABASE,
        'initial_type': INITIAL_CONDITION_TYPE,
        'n_hydro': N_HYDRO_EVENTS,
        'hydro_id0': HYDRO_EVENT_ID0,
        'n_urqmd': N_URQMD,
        'num_threads': N_THREADS,
        'save_ipglasma': SAVE_IPGLASMA,
        'save_kompost': SAVE_KOMPOST,
        'save_hydro': SAVE_HYDRO,
        'save_urqmd': SAVE_URQMD,
        'compute_polarization': COMP_POLARIZATION,
        'compute_photons': COMP_PHOTONS,
        'seed_add': SEED_ADD,
        'check_point_flag': CHECK_POINT,
        'afterburner_type': AFTERBURNER_TYPE,
        'kompost_filename': KOMPOST_FILENAME,
        'trento_output': TRENTO_OUTPUT,
        'free_stream_tau': FREE_STREAM_TAU,
        'free_stream_grid_max': FREE_STREAM_GRID_MAX,
        'free_stream_grid_step': FREE_STREAM_GRID_STEP,
        'adaptive_grid': ADAPTIVE_GRID,
    }

    main(para_dict)
