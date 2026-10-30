#!/usr/bin/env python3
"""Check the free-streaming -> MUSIC hand-off table (freestream_to_music_table).

Run where `freestream` is importable (the container), from the repo root:

    python3 scripts/check_freestream_table.py [TRENTo profile] [tau_fs]

Without a profile a lumpy, asymmetric test profile is used.  Checks:

1. Columns 0-4 and the header are byte-identical to convert_matrix_to_table, so
   Initial_profile 92 (e only) runs are unchanged.
2. Reading the table exactly as MUSIC's Init::initial_IPGlasma_XY_with_pi does
   and rebuilding T^munu = (e + P) u u - P g + pi, with P + Pi = e/3 (what
   Initial_profile 9 sets), reproduces FreeStreamer.Tuv in MUSIC's frame, and
   the longitudinal pressure tau^2 T^etaeta vanishes (massless free streaming).
3. The flow points down the energy-density gradient in MUSIC's frame.  The
   same statistic with the x/y components left in TRENTo's frame is printed
   for contrast; it must be clearly worse, or the check cannot see the error.

Exit status 1 if any check fails.
"""

import os
import sys
import tempfile

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for sub in ("codes", "utilities/IPGlasma_database",
            "utilities/3DMCGlauber_database"):
    sys.path.insert(0, os.path.join(ROOT, sub))

import freestream  # noqa: E402
import hydro_plus_UrQMD_driver as drv  # noqa: E402

GRID_MAX = 15.0
GRID_STEP = 0.2


def test_profile():
    n = int(round(2*GRID_MAX/GRID_STEP))
    x = np.linspace(-GRID_MAX + GRID_STEP/2, GRID_MAX - GRID_STEP/2, n)
    X, Y = np.meshgrid(x, x, indexing='xy')  # rows = y, as TRENTo writes
    rng = np.random.default_rng(3)
    prof = np.zeros((n, n))
    for _ in range(40):
        x0, y0 = rng.normal(0.8, 2.2), rng.normal(-0.4, 1.6)
        prof += rng.uniform(5, 30)*np.exp(-((X - x0)**2 + (Y - y0)**2)/(2*0.5**2))
    return prof


def read_like_music(path, tau0):
    """Parse the table the way MUSIC does: slow index = ix, fast index = iy."""
    with open(path) as fh:
        head = fh.readline().split()
    n = int(head[6])
    d = np.loadtxt(path, skiprows=1)
    col = lambda c: d[:, c].reshape(n, n)  # [ix, iy]
    e = col(3)
    ux, uy, ueta = col(5), col(6), col(7)*tau0
    pixx, pixy, pixeta = col(12), col(13), col(14)*tau0
    piyy, piyeta = col(15), col(16)*tau0
    utau = np.sqrt(1 + ux*ux + uy*uy + ueta*ueta)
    pietaeta = ((2*(ux*uy*pixy + ux*ueta*pixeta + uy*ueta*piyeta)
                 - (utau*utau - ux*ux)*pixx - (utau*utau - uy*uy)*piyy)
                / (utau*utau - ueta*ueta))
    pitaux = (pixx*ux + pixy*uy + pixeta*ueta)/utau
    pitauy = (pixy*ux + piyy*uy + piyeta*ueta)/utau
    pitaueta = (pixeta*ux + piyeta*uy + pietaeta*ueta)/utau
    pitautau = (pitaux*ux + pitauy*uy + pitaueta*ueta)/utau
    u = np.stack([utau, ux, uy], -1)
    pi = np.empty((n, n, 3, 3))
    pi[..., 0, 0], pi[..., 1, 1], pi[..., 2, 2] = pitautau, pixx, piyy
    pi[..., 0, 1] = pi[..., 1, 0] = pitaux
    pi[..., 0, 2] = pi[..., 2, 0] = pitauy
    pi[..., 1, 2] = pi[..., 2, 1] = pixy
    return e, u, pi*drv.HBARC, pietaeta*drv.HBARC


def main():
    prof = np.loadtxt(sys.argv[1]) if len(sys.argv) > 1 else test_profile()
    tau = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
    n = prof.shape[0]
    grid_max = n*GRID_STEP/2.0
    fs = freestream.FreeStreamer(prof, grid_max, tau)
    ok = True
    tmp = tempfile.mkdtemp()

    # 1. e-only part unchanged
    e_path = os.path.join(tmp, "e.dat")
    np.savetxt(e_path, fs.energy_density())
    old = os.path.join(tmp, "old.dat")
    new = os.path.join(tmp, "new.dat")
    drv.convert_matrix_to_table(e_path, old, n_grid=n, lower=-grid_max,
                                upper=grid_max)
    drv.freestream_to_music_table(fs, new, grid_max)
    with open(old) as fo, open(new) as fn:
        lo, ln = fo.read().splitlines(), fn.read().splitlines()
    same = (len(lo) == len(ln) and lo[0] == ln[0]
            and all(a.split()[:5] == b.split()[:5] for a, b in zip(lo[1:], ln[1:])))
    print(f"1. header + columns 0-4 identical to the e-only table: {same}")
    ok &= same

    # 2. T^munu round trip in MUSIC's frame
    e, u, pi, pietaeta = read_like_music(new, tau)
    g = np.diag([1., -1., -1.])
    P = e/3.
    T = ((e + P)[..., None, None]*np.einsum('...i,...j', u, u)
         - P[..., None, None]*g + pi)
    perm = [0, 2, 1]  # MUSIC x = TRENTo y
    T_fs = fs.Tuv()[..., perm, :][..., :, perm]
    live = fs.energy_density() > 1e-3*fs.energy_density().max()
    scale = fs.Tuv(0, 0).max()
    dT = np.abs(T - T_fs)[live].max()/scale
    PL = np.abs(P + pietaeta)[live].max()/scale
    print(f"2. max |T_MUSIC - T_freestream| / max T^00 = {dT:.2e}  "
          f"(cells with e > 1e-3 max: {live.sum()})")
    print(f"   max |tau^2 T^etaeta| / max T^00 = {PL:.2e}")
    ok &= dT < 1e-5 and PL < 1e-5

    # 3. flow direction
    gx, gy = np.gradient(e, GRID_STEP)  # axis 0 = MUSIC x, axis 1 = MUSIC y
    w = e*live

    def down_gradient(ux, uy):
        dot = ux*gx + uy*gy
        norm = np.hypot(ux, uy)*np.hypot(gx, gy) + 1e-300
        return np.sum(w*dot/norm)/np.sum(w)

    good = down_gradient(u[..., 1], u[..., 2])
    swapped = down_gradient(u[..., 2], u[..., 1])
    print(f"3. e-weighted cos(u, grad e): {good:+.3f} as written, "
          f"{swapped:+.3f} with x/y left in TRENTo's frame")
    ok &= good < -0.5 and good < swapped - 0.2

    print("PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
