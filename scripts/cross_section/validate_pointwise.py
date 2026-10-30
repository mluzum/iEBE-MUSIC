#!/usr/bin/env python3
"""Check the exact P(b) against the TRENTo binary at fixed impact parameters.

For one design point: builds pools of n_conf configurations per side, computes
the exact collision probability <P(b)> at a few b around b_max, and runs TRENTo
with b-min = b-max = b on the same pool files. The hit fraction must agree with
<P(b)> within errors. Run inside the production image.

Usage: validate_pointwise.py PARAM_FILE SCRATCH [N_CONF] [N_TRENTO]
"""
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xsec_point as xp  # noqa: E402

OFFSETS = (-3.0, -1.0, 0.0, 1.5, 3.0, 5.0)  # fm, relative to b_max


def main():
    param_file, scratch = sys.argv[1], sys.argv[2]
    n_conf = int(sys.argv[3]) if len(sys.argv) > 3 else 1000
    n_trento = int(sys.argv[4]) if len(sys.argv) > 4 else 40000
    n_orient = 8
    dp = xp.load_point(param_file)
    td = dp.trento_dict
    w = float(td['nucleon-width'])
    b_max = float(td['b-max'])
    sgg = xp.sigma_gg(float(td['cross-section']), w)
    tgt_hdf, tgt = xp.build_pool(dp.isobars_conf_dict_target, n_conf,
                                 xp.TARGET_ADDRESS_BASE,
                                 os.path.join(scratch, 'target'))
    prj_hdf, prj = xp.build_pool(dp.isobars_conf_dict_projectile, n_conf,
                                 xp.PROJECTILE_ADDRESS_BASE,
                                 os.path.join(scratch, 'projectile'))
    b_vals = b_max + np.array(OFFSETS)
    phis = (np.arange(8) + 0.5) * math.pi / 8
    uni = xp.orientation_uniforms(n_conf, n_orient)
    p = np.zeros((n_conf, len(b_vals)))
    for i in range(n_conf):
        for k in range(n_orient):
            a = tgt[i] @ xp.euler_rotation(uni[i, k, 0]).T
            b = prj[i] @ xp.euler_rotation(uni[i, k, 1]).T
            dxy = (a[:, None, :2] - b[None, :, :2]).reshape(-1, 2)
            p[i] += xp.collision_probability(dxy, b_vals, phis, sgg, w)
    p /= n_orient
    print(f'{os.path.basename(param_file)}  w={w:.3f}  b_max={b_max:.3f}  '
          f'n_conf={n_conf}  TRENTo draws/b={n_trento}')
    print('   b      exact <P>          TRENTo hit fraction     z')
    chi2 = 0.0
    for j, bv in enumerate(b_vals):
        pe = p[:, j].mean()
        se = p[:, j].std(ddof=1) / math.sqrt(n_conf)
        hits, _ = xp.run_trento(td, tgt_hdf, prj_hdf, bv, bv, n_trento, 11 + j,
                                os.path.join(scratch, f'trento_{j}'))
        pt = len(hits) / n_trento
        st = math.sqrt(max(pt * (1 - pt), 1.0 / n_trento) / n_trento)
        z = (pt - pe) / math.hypot(se, st)
        chi2 += z * z
        print(f'{bv:6.2f}  {pe:.5f} +- {se:.5f}   {pt:.5f} +- {st:.5f}   '
              f'{z:+.2f}')
    print(f'chi2 = {chi2:.2f} for {len(b_vals)} points')


if __name__ == '__main__':
    main()
