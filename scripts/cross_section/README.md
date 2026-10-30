# TRENTo-only inelastic cross sections

Per design point, the A+A inelastic cross section `sigma_inel` that anchors
centrality percentiles, plus the share of peripheral events that the campaign's
`b_max` cut removed. Background and the original task: `CROSS_SECTION_HANDOFF.md`.

## What is computed

`sigma_inel` = cross section for at least one nucleon-nucleon collision. In the
production TRENTo fork (`jppicchetti/trento_sync`, commit `4837013`) this is exactly
`mult > 0`: the fork removed upstream's "resample until a collision" loop and its
6-width pair cutoff, and decides each nucleon pair with one Bernoulli draw of
probability `1 - exp(-sigma_gg T_pp(d))`, `T_pp(d) = exp(-d^2/4w^2)/(4 pi w^2)`.
Units are fm^2 (1 fm^2 = 10 mb; `summary_*.csv` also has `sigma_inel_mb`).

There is no "total" or elastic cross section here. With the pair cutoff gone,
`P(b)` falls off smoothly with no edge, so `pi b_zero^2` is undefined, and TRENTo
has no elastic channel. "Total" in the sense of *not truncated at `b_max`* is what
`sigma_inel` is: the integral runs until `P(b) < 1e-8`.

## Method

For two fixed, oriented nuclei, the probability that a draw at impact-parameter
vector `b` collides is known in closed form:

    P(b) = 1 - exp(-sigma_gg * sum_ij T_pp(|r_i - r_j + b|))

so `sigma_inel = < int d^2b P(b) >` over configurations and orientations. Averaging
`P` instead of sampling the coin flips removes the Bernoulli noise. At A96 dp1, one
TRENTo draw carries ~200x the variance of one exact evaluation: about 8e5 draws vs
about 1e4 oriented pairs for +-0.1%.

Per design point (`xsec_point.py`):

1. **Pools.** The stock `build_isobars.py` from the image is called once per side
   with `n_conf` consecutive pool addresses from a dedicated block (target from
   1,000,000,000, projectile from 3,000,000,000). These are *not* the campaign's
   nuclei. The addresses do not depend on any parameter, so every design point sees
   the same nucleon seeds and shape latents.
2. **Exact integral.** Configuration pair `i` = (target `i`, projectile `i`), with
   `n_orient` isotropic orientation pairs each (TRENTo's own Euler construction,
   drawn from a fixed Philox stream, also the same at every point). It uses `n_phi`
   stratified azimuths of `b`, and the trapezoid rule in `|b|` with step `db` from
   `b_lo = b_max - 6 fm` to `b_far = b_max + 4 + 6w`, plus `pi b_lo^2` for the
   inside. Both edges are checked by the cross section they could hide:
   `pi b_lo^2 <1 - P(b_lo)>` and `2 pi b_far <P(b_far)> * 2 fm` must each be below
   1e-5 of `sigma_inel` (`edge_bound_*` columns; the worst single pair is recorded
   as `max_*`). Rare strongly deformed pairs reach `P(b_far) ~ 1e-3`, which is why
   the check is on the mean. `sigma_gg` is TRENTo's analytic fit, re-derived; every
   job checks it against TRENTo's own cache.
   - The error is `sd(per-pair sigma)/sqrt(n_conf)`; pairs are independent.
3. **TRENTo on the same pool files.** The production binary runs twice:
   `b` in `[0, b_max]` and in `[b_max, b_far]`, 20k draws each. This gives
   - a brute-force `sigma_inel` (+-0.3-0.6% per point), and
   - the `mult` distribution beyond `b_max`. From that come `tail_share_cXX`, the
     fraction of all events above the `XX%` multiplicity threshold that have
     `b > b_max`, and `naive_centrality_cXX`, where that threshold lands if only
     `b < b_max` events are counted.

   TRENTo seeds are `2k+1`, `2k+2` for point `k`, so this check is independent
   between points. The exact part deliberately is not: pools and orientations are
   shared (common random numbers), which keeps `sigma_inel` smooth across the
   design.

Production settings: `n_conf = 2000`, `n_orient = 8`, `n_phi = 4`, `db = 0.2 fm`,
20k + 20k TRENTo draws. The relative error is ~0.06% at w = 1.5 fm and up to
~0.10% (A96) or ~0.115% (A76, larger beta_2) at w = 0.5 fm, where the orientation
spread is largest. An A96 point takes ~19 min on one core of qgp1-4, ~2.3x that on
qgp (all hyperthreads busy) and ~9x on usphydro (3x lower KFlops; probably also
memory-bound with 78 jobs), so usphydro was excluded for A76. A96 used 613 core-h
(about 4 h wall); A76 used 274 core-h (median 9 min per point, 2 h 15 min wall on 132
slots).

Because pools and orientations are shared, most of a point's error is common to
all points:

| | per point (median) | common offset | two random points | nearest neighbours |
|---|---|---|---|---|
| A96 | 0.076% | 0.074% | 0.028% | 0.009% |
| A76 | 0.085% | 0.085% | 0.028% | 0.008% |

The last two columns are errors of the *difference* between two points. The
common offset shifts every centrality by the same relative amount; for an emulator
the relevant noise is the point-to-point part.

## Validation (2026-10-30, A96 dp1 / dp401 / dp715: w = 0.91 / 1.50 / 0.50 fm)

- `sigma_gg` equals TRENTo's cache value to all 7 printed digits.
- **Integrated** `sigma` on identical pools, exact vs 6M TRENTo draws:
  -0.031% +- 0.063%, -0.040% +- 0.061%, +0.007% +- 0.067%. That is no bias at the
  0.1% level.
- **Pointwise** `P(b)` vs TRENTo at fixed `b` (6 values each, b_max - 3 ... b_max + 5):
  chi2 = 20.4 for 18 points. TRENTo is slightly high in the far tail (b_max + 5:
  +1.9 sigma and +1.2 sigma with 400k draws). The tail contributes ~2e-5 of
  `sigma_inel`, and no offset survives in the integral. No mechanism was found:
  per-event state is reset, there is one constituent at the nucleon centre, and the
  rotation is orthogonal and isotropic.
- **Campaign draws:** the predicted hit fraction on `[0, b_max]` agrees with
  `events_drawn` at every pilot point (|pull| <= 1.13). Their mean offset,
  +0.13%, is *not* a 1/sqrt(N) measurement. The campaign uses the same event ids
  and seeds at every point, so these pulls share most of one fluctuation (their
  spread is 0.49, not 1), and the mean is worth about one point (~0.3%).
- **Pilot, 18 A96 points** at the extremes of every nuclear and TRENTo-geometry
  axis, with n_conf = 1500:
  - relative error: median 0.082%, max 0.108% (hence 2000 in production);
  - TRENTo vs exact: +0.015% +- 0.053% on average;
  - grid-edge bounds: <= 4e-5 fm^2;
  - tail share above the 60% threshold: median 0.07%, max 0.41% (dp401,
    w = 1.5 fm).
- The pruned integrator equals the unpruned one to 1e-15.

## Results (2026-10-30)

### A96

`/data/mluzum/cross_sections/a96/summary_a96.csv` (one row per point) and
`cross_sections_a96.h5` (P(b) curves, per-pair sigma).
- 1000/1000 points; `sigma_inel` = 423-720 fm^2, of which 74.5-94.1% is below
  `b_max`.
- Relative error: median 0.076%, max 0.104% (2 points above 0.1%, both
  w ~ 0.55 fm with large beta_2 and beta_3).
- Edge bounds <= 4.3e-7 of `sigma_inel`.
- TRENTo vs exact: pull sd 0.93, one |pull| > 3 (3.11) of 1000, mean relative
  difference -0.028%. This is within the exact side's common offset (0.043-0.074%,
  see above); the printed +-0.012% assumes independent points and does not apply.
- Campaign hit fraction (945 points with draw records): pull sd 0.59, max |pull|
  2.01, mean +0.14%, within the campaign's own common fluctuation (~0.3%).
- Tail share above the 60% threshold: median 0.07%, p90 0.29%, max 0.86% (dp65,
  w = 1.44 fm). 18 points are above 0.5%, all with w >= 1.28 fm. At 50%: max
  0.14%; at 70%: median 0.71%, max 3.4%.
- dp0130 has one `events_drawn` row with status `no_trento` (no b, no mult; TRENTo
  did not run). The collector skips it, and it should not be counted in
  `N_drawn`.

### A76

`/data/mluzum/cross_sections/a76/summary_a76.csv` and `cross_sections_a76.h5`.
- 1500/1500 points; `sigma_inel` = 385-627 fm^2, of which 78.0-94.6% is below
  `b_max`.
- Relative error: median 0.085%, max 0.115%. 227 points are above 0.1% and 12 above
  0.11%, all with w <= 0.85 fm. Nearly all of it is the common offset (table above).
- Edge bounds <= 8.1e-7 of `sigma_inel`.
- TRENTo vs exact: pull sd 0.97, 4 of 1500 with |pull| > 3 (max 3.43; ~3 expected),
  mean relative difference +0.043%, within the common offset (0.047-0.085%). A96
  gave -0.028%: opposite signs, as expected of common offsets rather than a bias.
- Campaign hit fraction (1339 points with draw records): pull sd 0.67, max |pull|
  2.29, mean +0.16%.
- Tail share above the 60% threshold: median 0.07%, p90 0.32%, max 0.84%
  (dp1455, w = 1.47 fm; 60% lands at 59.50%, a 50-60% bin lacks ~4.7%). 31 points
  are above 0.5%, all with w >= 1.13 fm. At 50%: max 0.16%; at 70%: median 0.68%,
  max 3.2%.

## Running

**Local HTCondor** (210 cores; every node sees `/data/mluzum` over NFS and has
Singularity), one job per point. This is how A96 was run, from
`/data/mluzum/cross_sections/a96/condor/` (A76: `a76/condor/`, `seq 1 1500`):

    universe = vanilla
    executable = /data/mluzum/GeSe/scripts/cross_section/condor_xsec.sh
    arguments = a96 $(point) /data/mluzum/iebe-music_slim_e340bbb.sif
    output = logs/dp$(point).out
    error = logs/dp$(point).err
    log = xsec_a96.log
    requirements = (Machine != "usphydro")   # A76 only; see above
    request_cpus = 1
    request_memory = 1000
    request_disk = 204800
    should_transfer_files = YES
    when_to_transfer_output = ON_EXIT
    queue point from seq 1 1000 |

Jobs import the scripts from NFS when they start, so do not edit them while a run
is queued.

**One machine:**

    singularity exec --contain -B /data/mluzum -B SCRATCH \
      /data/mluzum/iebe-music_slim_e340bbb.sif \
      python3 /data/mluzum/GeSe/scripts/cross_section/run_xsec.py \
        --campaign a96 --points 1-1000 --workers 40 --scratch SCRATCH

Either way the run is resumable: existing `points/dpNNNN.h5` files are skipped, and
outputs are renamed into place only when complete. Then:

    singularity exec --contain -B /data/mluzum IMAGE \
      python3 /data/mluzum/GeSe/scripts/cross_section/collect_xsec.py --campaign a96

writes `/data/mluzum/cross_sections/<campaign>/summary_<campaign>.csv` and
`cross_sections_<campaign>.h5` (P(b) curves and per-pair sigma), and prints the two
pull tests.

Other tools:
- `validate_pointwise.py` repeats the fixed-`b` check for any point.
- `xsec_point.compute()` can be called on its own.

## Using it for centrality

Campaign events were drawn area-uniform in `[0, b_max]`. Each drawn event, including
`mult = 0` rows of `events_drawn*.csv`, stands for `pi b_max^2 / N_drawn` of cross
section. The event ranked `r`-th by multiplicity is at centrality

    c = r * pi b_max^2 / (N_drawn * sigma_inel)

This holds while `tail_share` at `c` is negligible. When it is not, the ranking
puts the campaign events too central: the threshold the formula calls `c` is truly
at `naive_centrality_c` (`c (1 - tail_share_c)`). At 60% that is 59.49-60.00% for
A96 and 59.50-60.00% for A76 (median 59.96% for both). The missing events are concentrated just above the threshold,
so a 50-60% bin at the worst point lacks ~4.7% of its events (dp65). The tail shares use
TRENTo `mult` as a proxy for the experimental multiplicity estimator, whose extra
fluctuations make the real share somewhat larger. `trento_tail_b_mult` in each
point file holds the tail draws if a correction is wanted.
