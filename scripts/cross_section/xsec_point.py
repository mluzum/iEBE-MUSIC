#!/usr/bin/env python3
"""Inelastic A+A cross section of one design point, from TRENTo's own collision rule.

sigma_inel is the cross section for at least one nucleon-nucleon collision. In the
production TRENTo fork (jppicchetti/trento_sync, 4837013) that is exactly the
condition mult > 0: the fork removed upstream's "resample until a collision" loop
and its 6-width pair cutoff, and decides each nucleon pair with one Bernoulli draw
of probability

    P_pair(d) = 1 - exp(-sigma_gg T_pp(d)),   T_pp(d) = exp(-d^2/4w^2) / (4 pi w^2).

For two fixed, oriented nuclei the probability that a draw at impact-parameter
vector b collides is therefore known exactly,

    P(b) = 1 - exp(-sigma_gg sum_ij T_pp(|r_i - r_j + b|)),

and sigma_inel = < int d^2b P(b) > over configurations and orientations. Averaging
P instead of sampling the coin flips removes the Bernoulli noise, which is ~200x
the variance of one exact evaluation (see README.md).

Nuclei come from the production build_isobars.py, called once per side with
n_conf consecutive pool addresses from a dedicated block that is the same for
every design point, so all points see the same nucleon seeds and orientations.
TRENTo is then run twice on the same pool files (b in [0, b_max] and in
[b_max, b_far]) to give a brute-force cross-check of sigma_inel and the share of
peripheral events that the campaign's b_max cut removed.

Run inside the production image; see run_xsec.py.
"""
import hashlib
import importlib.util
import math
import os
import shutil
import subprocess
import time

import h5py
import numpy as np
import yaml
from scipy.optimize import brentq
from scipy.special import expi

SAMPLER = '/opt/iEBE-MUSIC/codes/isobar_sampler_code/exec/build_isobars.py'
TRENTO = '/opt/iEBE-MUSIC/codes/trento_code/build/src/trento'

# Dedicated pool-address blocks (consecutive addresses, as build_isobars.py
# uses natively). They do not depend on any parameter, so every design point
# gets the same nucleon seeds and shape latents.
TARGET_ADDRESS_BASE = 1000000000
PROJECTILE_ADDRESS_BASE = 3000000000
# Orientation stream, also identical for every design point.
ORIENTATION_KEY = 0x5EC7105E
PRUNE_WIDTHS = 14.0

DEFAULTS = {
    'n_conf': 2000,  # configurations per side; pair i is (target i, projectile i)
    'n_orient': 8,  # orientation pairs per configuration pair
    'n_phi': 4,  # stratified azimuths of b, on [0, pi)
    'db': 0.2,  # fm, trapezoid step in |b|
    'below_bmax': 6.0,  # fm, b_lo = b_max - below_bmax must have P == 1
    'n_trento_inner': 20000,
    'n_trento_tail': 20000,
}
CENTRALITIES = (40, 50, 60, 70, 80)
# Both ends of the |b| grid are checked by the cross section they could hide,
# relative to sigma_inel: below b_lo, pi b_lo^2 <1 - P(b_lo)>; beyond b_far,
# 2 pi b_far <P(b_far)> * EDGE_DECAY_FM, a generous e-fold length for the tail.
EDGE_TOLERANCE = 1e-5
EDGE_DECAY_FM = 2.0
SOURCE_SHA256 = hashlib.sha256(open(__file__, 'rb').read()).hexdigest()


def sigma_gg(sigma_nn, w):
    """TRENTo's analytic sigma_partonic for one constituent (nucleon.cxx)."""
    c = 9.0  # max_impact_widths**2 / 4; the fork keeps it in the fit
    rhs = sigma_nn / (4 * math.pi * w * w)
    x = brentq(lambda x: c - expi(-math.exp(x)) + expi(-math.exp(x - c)) - rhs,
               -10, 20, xtol=1e-15, rtol=1e-15)
    return math.exp(x) * 4 * math.pi * w * w


def b_far_of(b_max, w):
    # P(b_far) < ~1e-8 at w = 1.5 fm and far smaller at narrower widths.
    return b_max + 4.0 + 6.0 * w


def load_point(path):
    spec = importlib.util.spec_from_file_location('design_point', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def file_md5(path):
    with open(path, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()


def build_pool(conf_dict, n_conf, start, workdir, sampler=SAMPLER):
    """Run the stock sampler once for n_conf consecutive addresses."""
    os.makedirs(workdir, exist_ok=True)
    conf = yaml.safe_load(yaml.safe_dump(conf_dict))
    samples = conf['isobar_samples']
    samples['number_configs']['value'] = int(n_conf)
    samples['number_of_parallel_processes']['value'] = 1
    samples['start_configuration'] = {
        'description': 'First pool address (cross-section block)',
        'value': int(start),
    }
    with open(os.path.join(workdir, 'conf.yaml'), 'w') as f:
        yaml.safe_dump(conf, f, sort_keys=False)
    with open(os.path.join(workdir, 'sampler.log'), 'w') as log:
        subprocess.run(['python3', sampler, 'conf.yaml'],
                       cwd=workdir,
                       stdout=log,
                       stderr=subprocess.STDOUT,
                       check=True)
    name = conf['isobar_properties']['isobar1']['isobar_name']
    path = os.path.join(workdir, samples['output_path']['dirname'],
                        name + '.hdf')
    with h5py.File(path, 'r') as f:
        # float32 on disk, and TRENTo reads it as float32 as well
        positions = np.array(f[name][:], dtype=np.float64)
    return path, positions


def euler_rotation(u):
    """ManualNucleus::sample_nucleons_impl's rotation from three uniforms."""
    a1 = 2 * math.pi * u[0]
    c2 = 2 * u[1] - 1
    a3 = 2 * math.pi * u[2]
    c1, s1, c3, s3 = math.cos(a1), math.sin(a1), math.cos(a3), math.sin(a3)
    s2 = math.sqrt(1 - c2 * c2)
    return np.array([[c1 * c3 - c2 * s1 * s3, -(c3 * s1 + c1 * c2 * s3), s2 * s3],
                     [c1 * s3 + c2 * c3 * s1, -(s1 * s3 - c1 * c2 * c3),
                      -c3 * s2], [s1 * s2, c1 * s2, c2]])


def orientation_uniforms(n_conf, n_orient):
    rng = np.random.Generator(np.random.Philox(key=ORIENTATION_KEY))
    # C order: pair i's draws do not depend on n_conf
    return rng.random((n_conf, n_orient, 2, 3))


def collision_probability(dxy, b_grid, phis, sgg, w):
    """P(b) averaged over the azimuths phis, for pair offsets dxy (N, 2).

    With u, v the components of a pair offset along and across b, the squared
    distance is (u + b)^2 + v^2. Pairs farther than PRUNE_WIDTHS widths from
    overlap at every b of the grid are skipped: each such term is below
    exp(-PRUNE_WIDTHS^2 / 4) = 5e-22, so P is unchanged to machine precision.
    """
    inv4w2 = 1.0 / (4 * w * w)
    pref = sgg / (4 * math.pi * w * w)
    cut = PRUNE_WIDTHS * w
    p = np.zeros(len(b_grid))
    for phi in phis:
        c, s = math.cos(phi), math.sin(phi)
        u = dxy[:, 0] * c + dxy[:, 1] * s
        v = dxy[:, 1] * c - dxy[:, 0] * s
        keep = ((np.abs(v) < cut) & (u + b_grid[0] < cut) &
                (u + b_grid[-1] > -cut))
        g = np.exp(-v[keep]**2 * inv4w2)
        t = np.exp(-(u[keep][None, :] + b_grid[:, None])**2 * inv4w2)
        p -= np.expm1(-pref * (t @ g))
    return p / len(phis)


def run_trento(td, target_hdf, projectile_hdf, b_min, b_max, n_events, seed,
               workdir):
    """Run the production binary on the pool files; return (b, mult) of hits."""
    os.makedirs(workdir, exist_ok=True)
    xdg = os.path.join(workdir, 'xdg')
    os.makedirs(xdg, exist_ok=True)
    keys = dict(td)
    keys.pop('type', None)
    keys.pop('output', None)  # no per-event files
    keys.update({
        'projectile': [target_hdf, projectile_hdf],
        'number-events': int(n_events),
        'quiet': False,
        'b-min': b_min,
        'b-max': b_max,
    })
    with open(os.path.join(workdir, 'input'), 'w') as f:
        for key, value in keys.items():
            for v in (value if isinstance(value, list) else [value]):
                f.write(f'{key} = {v}\n')
    out = subprocess.run([TRENTO, '-c', 'input', f'--random-seed={seed}'],
                         cwd=workdir,
                         env=dict(os.environ, XDG_DATA_HOME=xdg),
                         capture_output=True,
                         text=True,
                         check=True).stdout
    # The fork prints a line only for npart > 0:
    # event, b, npart, mult, entropy, eccentricities
    rows = [l.split() for l in out.splitlines() if l[:1].isspace() or
            l[:1].isdigit()]
    rows = [r for r in rows if r and r[0].isdigit()]
    hits = np.array([(float(r[1]), float(r[3])) for r in rows]).reshape(-1, 2)
    with open(os.path.join(xdg, 'trento', 'cross_section.cache')) as f:
        cached_sgg = float(f.read().split()[4])
    return hits, cached_sgg


def tail_diagnostics(inner, tail, w_inner, w_tail, sigma_inel):
    """Share of events above each centrality threshold that come from b > b_max.

    Thresholds are TRENTo mult values, set on the weighted union of both runs
    with the exact sigma_inel as the denominator. 'naive' is the centrality the
    campaign would assign to that threshold counting b < b_max events only.
    """
    mult = np.concatenate([inner[:, 1], tail[:, 1]])
    weight = np.concatenate(
        [np.full(len(inner), w_inner),
         np.full(len(tail), w_tail)])
    is_tail = np.concatenate(
        [np.zeros(len(inner), bool),
         np.ones(len(tail), bool)])
    order = np.argsort(-mult, kind='stable')
    cum = np.cumsum(weight[order])
    out = {}
    for c in CENTRALITIES:
        k = min(np.searchsorted(cum, c / 100 * sigma_inel), len(order) - 1)
        above = order[:k + 1]
        s_tail = weight[above][is_tail[above]].sum()
        s_all = weight[above].sum()
        out[f'tail_share_c{c}'] = s_tail / s_all
        out[f'naive_centrality_c{c}'] = 100 * (s_all - s_tail) / sigma_inel
        out[f'mult_threshold_c{c}'] = mult[order[k]]
    return out


def trento_seeds(label):
    """Point-dependent TRENTo seeds.

    The TRENTo runs are a cross-check, so they must be independent between
    points for their average over a campaign to test anything: with one seed for
    all points every point consumes the same random stream (the number of draws
    per event is fixed), and the pulls share one fluctuation.
    """
    k = int(''.join(ch for ch in label if ch.isdigit()) or 0)
    return 2 * k + 1, 2 * k + 2


def compute(param_file, label, out_path, scratch, settings=None, log=print):
    s = dict(DEFAULTS)
    s.update(settings or {})
    t_start = time.time()
    dp = load_point(param_file)
    td = dp.trento_dict
    w = float(td['nucleon-width'])
    sigma_nn = float(td['cross-section'])
    b_max = float(td['b-max'])
    sgg = sigma_gg(sigma_nn, w)
    work = os.path.join(scratch, label)
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)

    # 1. configuration pools, one sampler call per side
    t0 = time.time()
    tgt_hdf, tgt = build_pool(dp.isobars_conf_dict_target, s['n_conf'],
                              TARGET_ADDRESS_BASE,
                              os.path.join(work, 'target'))
    prj_hdf, prj = build_pool(dp.isobars_conf_dict_projectile, s['n_conf'],
                              PROJECTILE_ADDRESS_BASE,
                              os.path.join(work, 'projectile'))
    t_pool = time.time() - t0

    # 2. exact collision probability
    t0 = time.time()
    db = s['db']
    n_lo = int(round(s['below_bmax'] / db))
    b_lo = max(0.0, b_max - n_lo * db)
    i_bmax = int(round((b_max - b_lo) / db))  # b_max is a grid point
    b_far = b_far_of(b_max, w)
    b_grid = b_lo + db * np.arange(int(math.ceil((b_far - b_lo) / db)) + 1)
    trap = 2 * math.pi * b_grid * db
    trap[0] *= 0.5
    trap[-1] *= 0.5
    trap_in = 2 * math.pi * b_grid[:i_bmax + 1] * db
    trap_in[0] *= 0.5
    trap_in[-1] *= 0.5
    phis = (np.arange(s['n_phi']) + 0.5) * math.pi / s['n_phi']
    uni = orientation_uniforms(s['n_conf'], s['n_orient'])
    sig = np.empty((s['n_conf'], s['n_orient']))
    sig_in = np.empty_like(sig)
    p_sum = np.zeros(len(b_grid))
    p_sq = np.zeros(len(b_grid))
    one_minus_p_lo = np.zeros(2)  # sum, max
    p_far = np.zeros(2)
    for i in range(s['n_conf']):
        for k in range(s['n_orient']):
            a = tgt[i] @ euler_rotation(uni[i, k, 0]).T
            b = prj[i] @ euler_rotation(uni[i, k, 1]).T
            dxy = (a[:, None, :2] - b[None, :, :2]).reshape(-1, 2)
            p = collision_probability(dxy, b_grid, phis, sgg, w)
            sig[i, k] = math.pi * b_lo**2 + trap @ p
            sig_in[i, k] = math.pi * b_lo**2 + trap_in @ p[:i_bmax + 1]
            p_sum += p
            p_sq += p * p
            one_minus_p_lo += (1.0 - p[0], 0.0)
            one_minus_p_lo[1] = max(one_minus_p_lo[1], 1.0 - p[0])
            p_far += (p[-1], 0.0)
            p_far[1] = max(p_far[1], p[-1])
    n_eval = s['n_conf'] * s['n_orient']
    per_pair = sig.mean(axis=1)
    sigma_inel = per_pair.mean()
    sigma_err = per_pair.std(ddof=1) / math.sqrt(s['n_conf'])
    per_pair_in = sig_in.mean(axis=1)
    sigma_below = per_pair_in.mean()
    sigma_below_err = per_pair_in.std(ddof=1) / math.sqrt(s['n_conf'])
    p_mean = p_sum / n_eval
    p_sd = np.sqrt(np.maximum(p_sq / n_eval - p_mean**2, 0.0))
    t_exact = time.time() - t0
    lo_hidden = math.pi * b_lo**2 * one_minus_p_lo[0] / n_eval
    far_hidden = 2 * math.pi * b_far * EDGE_DECAY_FM * p_far[0] / n_eval
    if max(lo_hidden, far_hidden) > EDGE_TOLERANCE * sigma_inel:
        raise RuntimeError(f'{label}: grid edges hide {lo_hidden:.2e} (b_lo) '
                           f'and {far_hidden:.2e} (b_far) fm^2 of '
                           f'{sigma_inel:.1f}')

    # 3. brute-force TRENTo on the same pools
    t0 = time.time()
    seed_inner, seed_tail = trento_seeds(label)
    inner, sgg_t1 = run_trento(td, tgt_hdf, prj_hdf, 0.0, b_max,
                               s['n_trento_inner'], seed_inner,
                               os.path.join(work, 'trento_inner'))
    tail, sgg_t2 = run_trento(td, tgt_hdf, prj_hdf, b_max, b_far,
                              s['n_trento_tail'], seed_tail,
                              os.path.join(work, 'trento_tail'))
    t_trento = time.time() - t0
    w_inner = math.pi * b_max**2 / s['n_trento_inner']
    w_tail = math.pi * (b_far**2 - b_max**2) / s['n_trento_tail']
    h_in, h_tail = len(inner), len(tail)
    sigma_trento = w_inner * h_in + w_tail * h_tail
    sigma_trento_err = math.sqrt(
        w_inner**2 * h_in * (1 - h_in / s['n_trento_inner']) +
        w_tail**2 * h_tail * (1 - h_tail / s['n_trento_tail']))
    diag = tail_diagnostics(inner, tail, w_inner, w_tail, sigma_inel)
    if abs(sgg_t1 / sgg - 1) > 1e-6 or sgg_t2 != sgg_t1:
        raise RuntimeError(f'{label}: sigma_gg {sgg} vs TRENTo {sgg_t1}')

    attrs = {
        'label': label,
        'param_file': os.path.abspath(param_file),
        'A': int(dp.isobars_conf_dict_target['isobar_samples']
                 ['number_nucleons']['value']),
        'nucleon_width': w,
        'sigma_nn_fm2': sigma_nn,
        'sigma_gg_fm2': sgg,
        'sigma_gg_trento_cache_fm2': sgg_t1,
        'b_max': b_max,
        'b_lo': b_lo,
        'b_far': b_far,
        'sigma_inel_fm2': sigma_inel,
        'sigma_inel_err_fm2': sigma_err,
        'sigma_below_bmax_fm2': sigma_below,
        'sigma_below_bmax_err_fm2': sigma_below_err,
        'frac_below_bmax': sigma_below / sigma_inel,
        'p_hit_below_bmax': sigma_below / (math.pi * b_max**2),
        'mean_1_minus_P_at_b_lo': one_minus_p_lo[0] / n_eval,
        'max_1_minus_P_at_b_lo': one_minus_p_lo[1],
        'mean_P_at_b_far': p_far[0] / n_eval,
        'max_P_at_b_far': p_far[1],
        'edge_bound_b_lo_fm2': lo_hidden,
        'edge_bound_b_far_fm2': far_hidden,
        'sigma_inel_trento_fm2': sigma_trento,
        'sigma_inel_trento_err_fm2': sigma_trento_err,
        'trento_hits_inner': h_in,
        'trento_hits_tail': h_tail,
        'target_address_base': TARGET_ADDRESS_BASE,
        'projectile_address_base': PROJECTILE_ADDRESS_BASE,
        'orientation_key': ORIENTATION_KEY,
        'trento_seeds': [seed_inner, seed_tail],
        'sampler_md5': file_md5(SAMPLER),
        'trento_md5': file_md5(TRENTO),
        'xsec_point_sha256': SOURCE_SHA256,
        'seconds_pool': t_pool,
        'seconds_exact': t_exact,
        'seconds_trento': t_trento,
        'seconds_total': time.time() - t_start,
    }
    attrs.update({k: v for k, v in s.items()})
    attrs.update(diag)
    tmp = out_path + '.tmp'
    with h5py.File(tmp, 'w') as f:
        for k, v in attrs.items():
            f.attrs[k] = v
        f['b_grid'] = b_grid
        f['P_mean'] = p_mean
        f['P_sd'] = p_sd
        f['sigma_orientation_fm2'] = sig
        f['sigma_below_bmax_orientation_fm2'] = sig_in
        f['trento_inner_b_mult'] = inner.astype(np.float32)
        f['trento_tail_b_mult'] = tail.astype(np.float32)
    os.replace(tmp, out_path)
    shutil.rmtree(work, ignore_errors=True)
    log(f'{label}: sigma_inel = {sigma_inel:.2f} +- {sigma_err:.2f} fm^2 '
        f'({100 * sigma_err / sigma_inel:.3f}%), below b_max '
        f'{100 * sigma_below / sigma_inel:.1f}%, TRENTo '
        f'{sigma_trento:.1f} +- {sigma_trento_err:.1f}, tail share at 60% '
        f'{100 * diag["tail_share_c60"]:.2f}%, {attrs["seconds_total"]:.0f} s '
        f'(pool {t_pool:.0f}, exact {t_exact:.0f}, trento {t_trento:.0f})')
    return attrs
