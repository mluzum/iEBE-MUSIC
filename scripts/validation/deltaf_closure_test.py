#!/usr/bin/env python3
"""Single-cell closure test of iSS's delta f models (linear vs PTB).

A static boost-invariant fluid cell (u = (1,0,0,0), tau = 1 fm, x = y = 0)
with prescribed pi^{ij} and Pi is written as a MUSIC text surface; iSS samples
primary hadrons from it (no decays) and the sampled T^{mu nu} in the local rest
frame is compared with the input:
    e        vs the kinetic e of the sampled hadron list (equilibrium run),
    P + Pi   vs kinetic P + Pi,
    pi^{ij}  vs the input pi^{ij}.
The cell's thermodynamics (e, T, (e+P)/T) are copied from a real freeze-out
surface so the Chapman-Enskog coefficients are those of production.

Runs inside the campaign image (docker); <iSS.e> is a path on the host
(e.g. a build of the patched iSS) or /opt/iEBE-MUSIC/codes/iSS_code/iSS.e.
Any event folder's UrQMDev_0/iSS/iSS_parameters.dat and a saved
hydro_results_<id>/surface_eps_*.dat + music_input serve as inputs (run an
event with control_dict['save_hydro_surfaces'] = True).

usage: deltaf_closure_test.py <iSS.e> <iSS_parameters.dat> <real surface.dat>
           <music_input> <workdir> [--image IMAGE] [--models 0,1]
           [--bulk-kind 21]

Reference results (zr96 dp0583 surface, T = 0.138 GeV, 3.5e6 particles per
run), pi^{ij} recovered / input:
    pi/(e+P) = 0.01: CE 1.01, PTB 1.01      0.05: CE 0.96, PTB 1.03
    pi/(e+P) = 0.15: CE 0.64, PTB 1.05 (e +4%, P +7%: second order)
    Pi/(e+P) = -0.03: P + Pi and e exact for both; n: CE -6%, PTB +14%
    (22-moment, bulk_deltaf_kind 20: pi 0.85 at 0.05, 0.53 at 0.15)
"""
import argparse
import os
import subprocess

import numpy as np

HBARC = 0.19733
SP = os.path.dirname(os.path.abspath(__file__))
IMAGE = "iebe-music:slim-3001ee9"
V_CELL = 1000.0          # fm^3 (dsigma_0 per unit eta)
N_REPEAT = 2000
Y_WIN = 10.0             # y_RB - y_LB


def write_surface(path, thermo, pi_lrf, bulk):
    """thermo = (e[1/fm^4], T[1/fm], (e+P)/T[1/fm^3]) from a real cell."""
    e, T, epT = thermo
    row = np.zeros(29)
    row[0] = 1.0                      # tau
    row[4] = V_CELL                   # dsigma_0
    row[8] = 1.0                      # u^tau
    row[12], row[13], row[17] = e, T, epT
    pxx, pyy, pxy = (x / HBARC for x in pi_lrf)
    # pi00 pi01 pi02 pi03 pi11 pi12 pi13 pi22 pi23 pi33 (tau = 1)
    row[18:28] = [0, 0, 0, 0, pxx, pxy, 0, pyy, 0, -(pxx + pyy)]
    row[28] = bulk / HBARC
    np.savetxt(path, row[None, :], fmt="%.10e")


def read_samples(path):
    raw = open(path, "rb").read()
    out = []
    i = 0
    while i < len(raw):
        n = np.frombuffer(raw, dtype=np.int32, count=1, offset=i)[0]
        i += 4
        rec = np.frombuffer(raw, dtype=np.dtype([("pid", "<i4"), ("f", "<f4", 9)]),
                            count=n, offset=i)
        out.append(rec["f"])
        i += n * 40
    return np.concatenate(out)


def lrf_tmunu(s):
    m, t, x, y, z, E, px, py, pz = s.T.astype(float)
    rap = 0.5 * np.log((E + pz) / (E - pz))
    eta = 0.5 * np.log((t + z) / (t - z))
    mT = np.sqrt(m * m + px * px + py * py)
    pzl = mT * np.sinh(rap - eta)
    El = mT * np.cosh(rap - eta)
    vol = N_REPEAT * Y_WIN * V_CELL
    p = np.stack([px, py, pzl])
    Tij = np.einsum("in,jn->ij", p, p / El) / vol
    return El.sum() / vol, Tij, len(El) / vol


def run(iss, par, surf, mi, out, args):
    mounts = []
    for p in (SP, par, surf, mi, out) + ((iss,) if os.path.exists(iss) else ()):
        d = os.path.dirname(os.path.abspath(p))
        if d not in mounts:
            mounts.append(d)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    cmd = ["docker", "run", "--rm", "--user", f"{os.getuid()}:{os.getgid()}",
           "-e", "HOME=/tmp"]
    for d in mounts:
        cmd += ["-v", f"{d}:{d}"]
    cmd += ["--entrypoint", "/bin/bash", IMAGE, f"{SP}/run_iss_standalone.sh",
           iss, par, surf, mi, out, "777",
           "perform_decays=0", "sample_upto_desired_particle_number=0",
           f"number_of_repeated_sampling={N_REPEAT}", "use_binary_format=1"] + args
    subprocess.run(cmd, check=True)
    return read_samples(os.path.join(out, "particle_samples.bin"))


def main():
    global IMAGE
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    for a in ("iss", "par", "real_surf", "mi", "work"):
        ap.add_argument(a)
    ap.add_argument("--image", default=IMAGE)
    ap.add_argument("--models", default="0,1", help="deltaf_model values")
    ap.add_argument("--bulk-kind", default="21", help="bulk_deltaf_kind")
    args = ap.parse_args()
    IMAGE = args.image
    iss, par, real_surf, mi, work = (args.iss, args.par, args.real_surf,
                                     args.mi, os.path.abspath(args.work))
    models = [int(m) for m in args.models.split(",")]
    os.makedirs(work, exist_ok=True)
    real = np.loadtxt(real_surf, max_rows=20000)
    # a typical cell at the freeze-out temperature
    Tf = np.median(real[:, 13])
    cell = real[np.argmin(np.abs(real[:, 13] - Tf))]
    thermo = (cell[12], cell[13], cell[17])
    T = thermo[1] * HBARC
    eP = thermo[2] * thermo[1] * HBARC     # e+P (hydro) GeV/fm^3
    print(f"cell: T = {T:.4f} GeV, e = {thermo[0]*HBARC:.4f} GeV/fm^3, e+P = {eP:.4f} GeV/fm^3")

    cases = [
        ("equilibrium", (0, 0, 0), 0.0, ["include_deltaf_shear=0", "include_deltaf_bulk=0"]),
        ("shear 0.01", (0.01 * eP, -0.005 * eP, 0.004 * eP), 0.0, ["include_deltaf_bulk=0"]),
        ("shear 0.05", (0.05 * eP, -0.025 * eP, 0.02 * eP), 0.0, ["include_deltaf_bulk=0"]),
        ("shear 0.15", (0.15 * eP, -0.075 * eP, 0.06 * eP), 0.0, ["include_deltaf_bulk=0"]),
        ("bulk -0.01", (0, 0, 0), -0.01 * eP, ["include_deltaf_shear=0"]),
        ("bulk -0.03", (0, 0, 0), -0.03 * eP, ["include_deltaf_shear=0"]),
        ("shear 0.05 + bulk -0.03", (0.05 * eP, -0.025 * eP, 0.02 * eP), -0.03 * eP, []),
    ]
    ref = None
    for name, pi, bulk, flags in cases:
        surf = os.path.join(work, "surface_" + name.replace(" ", "_").replace("+", "") + ".dat")
        write_surface(surf, thermo, pi, bulk)
        print(f"\n== {name}: input pi_xx,pi_yy,pi_xy = "
              + ", ".join(f"{x/eP:+.4f}" for x in pi) + f" (e+P);  Pi = {bulk/eP:+.4f} (e+P)")
        for model in models:
            out = os.path.join(work, f"out_{os.path.basename(surf)[:-4]}_m{model}")
            s = run(iss, par, surf, mi, out, flags + [f"deltaf_model={model}",
                                                      f"bulk_deltaf_kind={args.bulk_kind}"])
            e, Tij, n = lrf_tmunu(s)
            P = np.trace(Tij) / 3
            pis = Tij - P * np.eye(3)
            if ref is None:
                ref = (e, P, n)
                print(f"   kinetic gas (equilibrium sample): e = {e:.5f}, P = {P:.5f} GeV/fm^3, n = {n:.5f} /fm^3")
            print(f"   deltaf_model {model} ({'linear' if model == 0 else 'PTB   '}): N = {len(s):8d}  "
                  f"e/e_eq = {e/ref[0]:.4f}  (P+Pi)/(P_eq+Pi) = {P/(ref[1]+bulk):.4f}  n/n_eq = {n/ref[2]:.4f}  "
                  f"pi_xx,pi_yy,pi_xy,pi_zz /(e+P) = "
                  + ", ".join(f"{x/eP:+.4f}" for x in (pis[0, 0], pis[1, 1], pis[0, 1], pis[2, 2])))


if __name__ == "__main__":
    main()
