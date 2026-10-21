# Numerical precision of the iEBE-MUSIC event generator

**Scope.** How accurate are the observables we compute, as a function of the transverse grid
spacing `dx` and the time step `Delta_Tau`? This is the budget that has to sit well below the
emulator and experimental uncertainties (of order 1%) for the emulator to be meaningful, so it
has to be measured rather than assumed.

Everything below is measured on 76Ge+76Ge central events (b-max = 4.0 fm, R = 5.08 fm =
1.2·A^(1/3), a = 0.5 fm, TRENTo `normalization` = 15.0, free-streaming `tau` = 1.0 fm/c), with
the freeze-out seed fixed per event. The raw campaign is ~600 events across 30+ points; the
parameters are in `config/design_points/parameters_dict_user_TRENTo_ge76_{fin,crv,tm,tmx}*.py`
and the procedure is in `EMULATOR_SWEEP_PLAN.md`.

---

## 1. Summary of the recommendations

| | recommendation | measured error |
|---|---|---|
| **observable: v₂ only** | `dx` = 0.20 (0.50 is also acceptable) | < 1% for `dx` ≤ 0.25; < 1.9% for `dx` ≤ 0.60 |
| **observable: includes n ≥ 3** | `dx` = 0.15 | ≤ 2% for n = 1…5 at `dx` ≤ 0.15 |
| **time step** | `Delta_Tau` = 0.005 fm/c, unchanged | ≤ 1% for n ≥ 2, consistent with zero |
| **freeze-out averaging** | 10 steps, unchanged | ≤ 0.9% for n ≥ 2, consistent with zero |
| **n = 1** | not usable as an observable | see §6 |

`dx` = 0.10 is a **verified converged reference**: the error stops growing below it.

---

## 2. The method, and the two traps in it

### 2.1 What is compared

For each event `e` (same nuclei, same impact parameter at every `dx`), the pT-integrated
`v_n` vector is formed and the **complex difference** taken against the reference:

```
dv_n(e, dx) = v_n(e, dx) - v_n(e, dx_ref)
```

Real and imaginary parts are carried separately throughout; **no magnitude is taken before the
difference**. The difference is resolved into a component **parallel** to `v_n(dx_ref)` (a
flow-magnitude error) and **perpendicular** to it (a flow-plane / phase error). A statistic
over events is formed from these *differences*, never from averages of `v_n` — averaging the
flow vector across events cancels, catastrophically so for odd harmonics.

The statistic is the mean of the parallel component over events, with `SEM = std/sqrt(N)` and
`z = mean/SEM`. The perpendicular component is reported alongside.

### 2.2 Trap 1: do not average v_n over events

Averaging the `v_n` **vector** over events is not a meaningful quantity: events have different
eccentricities, orientations and magnitudes, so the average cancels, and odd harmonics such as
`v_3` average almost to zero. This was done early in the investigation and produced two
conclusions that had to be withdrawn.

### 2.3 Trap 2: the benchmark table must be the big one

The single most consequential error. The **unidentified** table
`particle_9999_vndata_eta_-0.5_0.5` was used initially; it holds **40.5 particles per
freeze-out resampling** against **602.5** for the all-charged table
`particle_99999_vndata_eta_-4_4`. A factor of 15, and therefore a factor 3.9 in σ.

602 charged particles per freeze-out sampling is the expected number for central 76Ge, so the
all-charged table has the correct multiplicity and full acceptance; the unidentified table does
not. (The identified species sum to 48.37 dN/dη and the unidentified to 40.51, together
*exceeding* the all-charged 75.31, so the tables do not share one acceptance. The exact reason
is not settled — it needs the toolkit source, not a guess — but the actionable point is
unambiguous.)

Switching to the all-charged table changes every harmonic conclusion:

| n | \|v_n\|/σ, unidentified | \|v_n\|/σ, all charged | suppression, all charged | usable? |
|---|---|---|---|---|
| 1 | 3.1 | 11.4 | 1.28× | no |
| 2 | 43 | **159** | 1.01× | yes |
| 3 | 3.9 | **15.6** | 1.10× | yes |
| 4 | 11.9 | **45.1** | 1.04× | yes |
| 5 | 5.3 | **20.1** | 1.17× | marginal |

"Suppression" is `|v_n|`(1× sampling) / `|v_n|`(100× sampling): 1.0 means the value does not
depend on how much of the freeze-out surface was sampled, i.e. the number is physical rather
than a fluctuation. **Only n = 2, 3, 4 pass this at the all-charged level**, and with the
unidentified table only n = 2 does. The 100× numbers quoted throughout are the all-charged ones.

---

## 3. Spatial convergence

### 3.1 The curve

Consecutive steps, all-charged, w = 0.50, as a percentage of `|v_n|`:

| dx step | n=1 | n=2 | n=3 | n=4 | n=5 |
|---|---|---|---|---|---|
| 0.05 → 0.075 | −0.37% | −0.45% | −0.65% | −0.37% | +0.03% |
| 0.075 → 0.10 | −1.20% | −0.11% | +1.91% | −0.32% | −1.31% |
| 0.10 → 0.15 | −2.00% | −0.27% | −0.22% | −0.80% | +0.03% |
| 0.15 → 0.20 | −0.57% | −0.49% | −5.14% | −4.81% | −7.19% |
| 0.20 → 0.25 | −0.90% | −0.19% | −5.66% | −3.53% | −5.12% |
| 0.25 → 0.30 | +2.81% | +0.35% | −3.63% | −1.93% | −2.02% |
| 0.30 → 0.35 | −0.47% | +0.52% | −2.26% | +0.76% | −0.49% |
| 0.35 → 0.40 | −3.86% | +0.78% | −0.27% | +1.18% | +1.05% |
| 0.40 → 0.50 | — | +0.50% | — | — | — |
| 0.50 → 0.60 | — | +1.41% | — | — | — |
| 0.60 → 0.75 | — | −10.7% | — | — | — |

**The error stops growing below `dx` = 0.10**, so `dx` = 0.10 is a converged reference and
every drift quoted against it stands.

### 3.2 Cumulative drift, per harmonic and per w

Cumulative paired drift from `dx` = 0.10 (w = 0.50) and from `dx` = 0.20 (w = 1.0, 1.5):

| w | dx | n=1 | n=2 | n=3 | n=4 | n=5 |
|---|---|---|---|---|---|---|
| 0.50 | 0.15 | −2.0% | −0.3% | −0.2% | −0.8% | +0.0% |
| 0.50 | 0.20 | −3.1% | −0.8% | −4.9% | −5.5% | −6.2% |
| 0.50 | 0.25 | −3.8% | −0.9% | −10.1% | −8.7% | −11.0% |
| 0.50 | 0.30 | −0.6% | −0.6% | −13.3% | −10.5% | −12.8% |
| 0.50 | 0.40 | −10.6% | +0.6% | −15.8% | −9.3% | −11.4% |
| 0.50 | 0.50 | −51.9% | +1.3% | −22.7% | −4.1% | −5.4% |
| 0.50 | 0.60 | −84.2% | +1.9% | −47.5% | −10.4% | −26.0% |
| 0.50 | 0.75 | −93.4% | −9.2% | −78.7% | −52.1% | −83.7% |
| 1.00 | 0.30 | +6.9% | +0.2% | −12.2% | −7.7% | −8.6% |
| 1.00 | 0.40 | +7.8% | +1.3% | −22.6% | −13.9% | −18.4% |
| 1.50 | 0.30 | +6.6% | +0.5% | +1.0% | −1.3% | −6.7% |
| 1.50 | 0.40 | +9.1% | +1.1% | −8.3% | −7.5% | −14.5% |

**Read this as: `dx` = 0.15 is the minimum for n ≥ 3; `dx` = 0.20 is ample for n = 2.**

Note also that larger `w` tolerates coarse `dx` better (at `dx` = 0.40 the drift is smaller at
w = 1.5 than at w = 0.5), as it should: a larger `w` means a smoother initial condition and
less structure to miss.

### 3.3 The error is a magnitude error, not a phase error

The perpendicular component is consistent with zero everywhere it was measured. A too-coarse
grid gets the **size** of the flow wrong and leaves its **direction** alone.

### 3.4 It is not dx/w that governs

At w = 0.25, `dx` = 0.20 (dx/w = 0.80) carried ~7% in v₂; at w = 0.50, `dx` = 0.40
(dx/w = 0.80) carried < 1%. Same ratio, 7× different error. **The error is governed by `dx`
itself, not by `dx` relative to `w`.** (`w` = 0.25 is outside the production prior; it was
investigated because a non-monotonicity there needed explaining, and the explanation turned out
to be the cut table — with the all-charged benchmark the `n` = 1 drift grows monotonically with
`dx`, as a discretisation error should.)

### 3.5 n = 1 is not a usable observable

`|v_1|` grows from 0.00157 at `dx` = 0.40 to 0.00688 at `dx` = 0.75 — a factor 4.3 — and the
drift reaches −93%. A quantity that changes by 4× under a resolution change is not a
measurement. It is also the least-averaged harmonic and therefore the most sensitive to the
freeze-out surface (§4).

---

## 4. Time resolution

`Delta_Tau` is a **fixed absolute value** in the master defaults (0.005 fm/c) and is *not*
tied to `dx`, so the whole `dx` ladder was a clean spatial scan at constant time step, and the
usual CFL scaling was never imposed. At `dx` = 0.20 the Courant number is 0.043 and at
`dx` = 0.15 it is 0.058 — an order of magnitude from any stability limit — so the question is
accuracy, not stability.

Measured **at dx = 0.15** (the production candidate), all-charged, 100× sampling, reference
`Delta_Tau` = 0.005 with a 10-step freeze-out average:

| varied | to | n=1 | n=2 | n=3 | n=4 | n=5 |
|---|---|---|---|---|---|---|
| hydro step (freeze-out window held at 0.05 fm/c) | dt 0.0025 | +1.07% | **−0.01%** | −0.53% | +0.51% | −0.31% |
| hydro step | dt 0.00125 | +1.53% | **−0.12%** | +1.67% | +0.35% | −0.15% |
| freeze-out window alone | 0.025 fm/c | +0.42% | **0.00%** | −0.80% | −0.32% | −0.18% |
| freeze-out window alone | 0.10 fm/c | +3.70% | **+0.04%** | +0.43% | −0.85% | −0.15% |

**Every time-related shift for n ≥ 2 is ≤ 1.7% and all are consistent with zero (|z| ≤ 1.2).**
`n` = 1 is the exception, and it is the harmonic most sensitive to the freeze-out surface
because it is the least averaged — doubling the freeze-out window moves it +3.7% at 2.2σ.

**Recommendation: `Delta_Tau` = 0.005 fm/c and a 10-step freeze-out average, unchanged.**

### 4.1 Resolved: it is the freeze-out surface averaging, not the hydro step

The `tm` series changed `dt` **and** the freeze-out averaging together, so it could not
separate the hydro step from the *quadrature* of the surface average (40 points at
dt = 0.00125 versus 10 at dt = 0.005 over the same 0.05 fm/c window). Two further points
holding the averaging at the production value of 10 close the 2×2. Cumulative paired shifts
against the production configuration, all-charged, w = 0.50, **at dx = 0.20**:

| point | dt | avg | window | n=1 | n=2 | n=3 | n=4 | n=5 |
|---|---|---|---|---|---|---|---|---|
| reference | 0.005 | 10 | 0.050 | — | — | — | — | — |
| avg=10, dt/2 | 0.0025 | 10 | 0.025 | +0.64% | +0.16% | +0.32% | +0.83% | −2.09% |
| avg=10, dt/4 | 0.00125 | 10 | 0.013 | −2.27% | −0.05% | +3.19% | −0.04% | +2.17% |
| **avg=20, dt/2** | 0.0025 | **20** | 0.050 | −2.67% | +0.48% | **+4.18%** | **+5.38%** | **+5.97%** |
| **avg=40, dt/4** | 0.00125 | **40** | 0.050 | −2.47% | +0.35% | **+5.43%** | **+5.04%** | **+7.23%** |
| avg=20, dt same | 0.005 | 20 | 0.100 | −1.40% | +0.02% | −0.37% | +0.03% | −0.17% |
| avg=5, dt same | 0.005 | 5 | 0.025 | −1.80% | +0.04% | −0.03% | −0.14% | +0.15% |

**The 5–7% is produced by the averaging count, not by the hydro step.** Holding the averaging
at the production value of 10 and changing `dt` alone moves n = 3, 4, 5 by at most 3.2%;
changing the averaging from 10 to 20 at the *same* window moves them by 4–6%. And once the
averaging is at 20, going to 40 changes nothing further (4.18 → 5.43, 5.38 → 5.04,
5.97 → 7.23) — the signature of a one-off change in how the surface is sampled, not of a
quantity converging with the hydro step.

The mechanism is that the freeze-out surface is a time-dependent object: averaging it over
0.05 fm/c means sampling it at 10 points spaced 0.005 apart, or 20 points spaced 0.0025 apart.
Those are different surfaces, and at the production spacing the n ≥ 3 result differs from the
finer one by ~5%.

**This is dx-dependent, and it matters.** The same comparison at **dx = 0.15** gives ≤ 1.7% for
n ≥ 2 (§4). So the production freeze-out averaging is well converged at dx = 0.15 and carries a
~5% error in n = 3, 4, 5 at dx = 0.20.

**That is a second, independent reason to prefer dx = 0.15 over dx = 0.20 whenever n ≥ 3 is
an observable** — not only is the grid finer, but the freeze-out surface is better resolved.

---

## 5. What the sampling can and cannot resolve

### 5.1 The consistency test, done correctly

A genuine effect of size µ gives `z_100x = µ√N/s_100x` and `z_1x = µ√N/s_1x`, and since
`s_1x = 8.72·s_100x` (measured: σ = 0.00122 vs 0.00014, from 77× the particles) a real
effect requires **`z_1x = z_100x/8.72`**. Comparing raw *shift* ratios — which is the
intuitive thing to do — is the wrong statistic and gives misleading answers.

On the grid step `dx` 0.15 → 0.20, w = 0.50:

| n | 100× shift | z₁₀₀ₓ | 1× shift | z₁ₓ | z₁ₓ expected if real |
|---|---|---|---|---|---|
| 2 | −0.00011 | −3.42 | −0.00051 | −2.97 | −0.39 |
| 4 | −0.00030 | −5.48 | −0.00084 | −4.42 | −0.63 |
| 5 | −0.00020 | −5.46 | −0.00082 | −3.67 | −0.63 |

The 1× shifts are all ≈ −0.0007 **regardless of harmonic** — a common offset — while the 100×
shifts are harmonic-dependent and smaller. That is a sampling-dependent *bias* (residual
fluctuation, not averaged out at 1×) whose `dx`-dependent part mimics a grid error.

**Two consequences.**

1. **The grid errors quoted from the 100× runs are upper bounds**, overestimates by up to ~30%
   if the contamination scales as 1/√N. The production conclusion is unaffected and becomes
   conservative.
2. **The 1× series is not a valid reference for anything** and must not be quoted.

This is the reason the "higher harmonics are far more grid-sensitive" result appeared first as
70–126% errors and had to be withdrawn: those were percentages of noise.

### 5.2 The floor: the cap is real but secondary

The residual sampling floor is set by the number of particles per event. The "100 000
resamplings" quoted throughout are **10 subevents × 10 000 iSS sampling events**, and
`iss_dict['maximum_sampling_events']` (default 10 000) is the **per-invocation** cap.

**Measured** (8 events, dx = 0.20, w = 0.50):

| | resamplings | particles/event | σ(v₂) |
|---|---|---|---|
| max_sampling_events = 10 000 | 100 000 | 53 772 228 | 0.00014 |
| max_sampling_events = 100 000 | 130 515 | 67 012 004 | **0.00012** |

So the cap *is* the binding limit at 100 000 — raising it does add particles — but the gain is
only **1.31× in resamplings, 1.25× in particles and 1.17× in σ**, for a proportional increase in
iSS cost. A new limit appears at ~131 000, set by the per-subevent sampling structure. The n ≥ 3
floor therefore stays near ~0.4σ.

**Conclusion: the floor is close to where it can be with this knob, and pushing it further is
not worth the compute.** Breaking it would need a change to how the subevents are structured
(the `for iev in {0..9}` loop in the generated `run_afterburner.sh` is hardcoded to 10, and the
`afterburner_type` is `decay` so the subevents are cheap — raising the count is the natural
lever, but it is a code change to `generate_jobs.py` and therefore a new image).

**A first attempt at this probe was invalid** and its result discarded: the parameter files
were written by a helper that discarded the return value of the mutation, so all seven points
were submitted as duplicates of the reference configuration. The files were rebuilt and then
verified **end-to-end by emitting the configuration with `parameters_dict_master.py` and reading
back the emitted `music_input_mode_2`, `TRENTo/input` and `iSS_parameters.dat`** — the source
parameter file is not what the run uses, so that is the only check that means anything. The
verification table is reproduced in §9.

### 5.3 What is out of reach

Per-event, `|v_n|` for n ≥ 6 is at or below the particle noise (`|v_8| = 0.00048` against
σ = 0.00054 is 0.9σ), so n ≥ 6 is not a single-event measurement and cannot be made one by
sampling the surface harder: the floor is set by the number of particles, and more resampling
reduces the *error* but not the *fluctuation content* of the high-n signal.

---

## 6. Reproducibility (demonstrated, not assumed)

Two independently submitted batches with byte-identical parameters agree **bit-for-bit** in
every pT-integrated `v_n`, real and imaginary, for every harmonic, with matching resampling
counts (1100/1100, 1380/1380, 1230/1230, 2180/2180).

This required a fix: `iss_dict['randomSeed']` was −1, which iSS reads as *"use the system
clock"*, and `run_afterburner.sh` deliberately left it there, so every subevent drew fresh
entropy. The seed is now `base + event_id·1000003 + subevent`, which is reproducible on re-run,
distinct per event, and **identical for the same event at every `dx`** — which is what turns the
`dx` comparison into a common-random-numbers comparison.

**No result produced before that fix is reproducible**, whatever it says about seeds.

---

## 7. Corrections to earlier conclusions

For the record, these were stated at some point and withdrawn:

| claim | why withdrawn |
|---|---|
| "`dx` = 0.20 is converged to <1%" | came from a MUSIC lattice proxy of unknown column meaning; the proxy is withdrawn |
| "the grid error grows strongly with `w`" (7–8% at w = 0.25 vs <1% at w = 0.50) | the 7–8% was measured with the cut table; the effect is real but far smaller |
| "the oversampling suppresses `v_n` by ~10×" | the magnitude of a noisy mean is biased upward; the "sensible" value was noise, and the script had already said "consistent with ZERO" |
| "higher harmonics have 70–126% grid errors" | percentages of noise, not of a signal |
| "the v_n vector can be averaged over events" | it cannot; odd harmonics cancel |
| "the `n` dependence of the grid error cannot be tested" | true only because the wrong table was used; with the all-charged table n = 3, 4, 5 are testable |
| "the error saturates at `dx` ≥ 0.30" | it does not; it was a local plateau, and beyond `dx` = 0.40 it grows steeply |

---

## 8. Open items

1. **Freeze-out quadrature vs hydro step** at `dx` = 0.20 (§4.1) — two points submitted.
2. **The converged-`dx` statement across the whole prior** — w = 1.0 and 1.5 at `dx` = 0.10 and
   0.15, so that "dx = 0.15 is the minimum for n ≥ 3" holds over w ∈ [0.5, 1.5] and not just at
   w = 0.50. *Partially closed: at `dx` = 0.15 the v₂ drift against `dx` = 0.20 is −0.01%
   (w = 1.0) and −0.04% (w = 1.5), so v₂ is converged at 0.15 across the prior. The
   `dx` = 0.10 references are still running.*
3. **The freeze-out surface averaging at `dx` = 0.20** — resolved in §4.1 as to *what* causes
   the 5–7% shift. Not resolved: whether the production value (10 steps at dt = 0.005) should
   be changed for a `dx` = 0.20 run, given that the finer averaging disagrees with it by ~5%
   in n = 3, 4, 5. At `dx` = 0.15 the question does not arise (≤1.7%).
4. **Why the `n` ≥ 3 drift stops growing between `dx` = 0.30 and 0.40** before resuming
   steeply. Not explained; the local plateau is real but its origin is not known.
5. **The acceptance of the unidentified table** (§2.3) — needs the toolkit source.
6. **Whether the n ≥ 3 floor can be broken** by restructuring the subevents (§5.2) — a code
   change and a new image, for an unknown gain. Low priority given that the 100× measurements
   are already good enough to measure the grid error.

---

## 9. Verification of the final job batch

Every parameter file is checked by **emitting the configuration and reading the emitted files**,
not by inspecting the source parameter file — the source is not what the run consumes. The
builder also asserts the expected pattern is present after each edit, so a silent no-op edit
fails loudly rather than producing a duplicate of the reference.

| point | Delta_Tau | nucleon-width | TRENTo grid-step | max_sampling_events | purpose |
|---|---|---|---|---|---|
| `tmx0dt25a10` | 0.0025 | 0.5 | 0.2 | 10 000 | hydro step vs surface quadrature |
| `tmx0dt125a10` | 0.00125 | 0.5 | 0.2 | 10 000 | hydro step vs surface quadrature |
| `crv100dx10` | 0.005 | 1.0 | 0.1 | 10 000 | converged-dx statement across the prior |
| `crv100dx15` | 0.005 | 1.0 | 0.15 | 10 000 | converged-dx statement across the prior |
| `crv150dx10` | 0.005 | 1.5 | 0.1 | 10 000 | converged-dx statement across the prior |
| `crv150dx15` | 0.005 | 1.5 | 0.15 | 10 000 | converged-dx statement across the prior |
| `osx10` | 0.005 | 0.5 | 0.2 | **100 000** | can the measurement floor be lowered? |

Reference for comparison: `fin50dx20` = Delta_Tau 0.005, nucleon-width 0.5, grid-step 0.2,
max_sampling_events 10 000.

---

## 10. Reproduction

```bash
# the convergence campaign, by hand
python3 config/parameters_dict_master.py -par <param>.py -path <out>
# then read the emitted model_parameters/ and run the event chain

# the analysis (this is the whole method, in one place)
#   per event, paired by event id:
#     dv_n = v_n(e,dx) - v_n(e,dx_ref)          complex, real/imag kept separate
#     rotate into the frame of v_n(dx_ref):  parallel / perpendicular
#     SEM = std(parallel)/sqrt(N),  z = mean/SEM
#   the benchmark table is particle_99999_vndata_eta_-4_4.dat  (all charged, 602 particles
#   per freeze-out resampling) -- NOT particle_9999_*  (40.5 particles per resampling)
```

The output data dictionary is in [`analysisKit/FLOW_OUTPUT_FORMAT.md`](analysisKit/FLOW_OUTPUT_FORMAT.md).
The campaign history, including every correction above and the reasoning behind it, is in
[`EMULATOR_SWEEP_PLAN.md`](EMULATOR_SWEEP_PLAN.md).

---

## 11. Resource budget for the production settings

All numbers measured from the OSG job logs (peak `ResidentSetSize`, and wall time from the
`006` running to the `005` terminated stamps). Note that the **submit node runs on Central
Time, 2 h behind the local clock** — reading a log timestamp as local time makes a 15-minute
job look like a 2-hour stall.

### 11.1 Measured cost per batch

**1× sampling** (the master default, `number_of_particles_needed` = 1e5), w = 0.50, 8 events/job:

| dx | job wall | per event | peak RSS |
|---|---|---|---|
| 0.10 | 169.9 min | 21.2 min | 267 MB |
| 0.15 | 74.4 min | 9.3 min | 259 MB |
| 0.20 | 22.8 min | 2.85 min | 242 MB |
| 0.25 | 23.4 min | 2.93 min | 246 MB |

**100× sampling**, 4 or 8 events/job:

| dx | w | job wall | per event | peak RSS |
|---|---|---|---|---|
| 0.10 | 1.0 | 97.5 min | 24.4 min | 625 MB |
| 0.10 | 1.5 | 199.8 min | 50.0 min | **1109 MB** |
| 0.15 | 1.0 | 83.2 min | 20.8 min | 780 MB |
| 0.15 | 1.5 | 59.0 min | 14.8 min | 717 MB |
| 0.20 | 0.5 | 81.4 min | 20.4 min | 351 MB |
| 0.20 | 1.0 | 69.3 min | 17.3 min | 878 MB |
| 0.30 | 0.5 | 197.1 min (8 ev) | 24.6 min | 768 MB |
| 0.40 | 0.5 | 180.4 min (8 ev) | 22.6 min | 976 MB |
| 0.50 | 0.5 | 94.2 min (8 ev) | 11.8 min | 733 MB |
| 0.75 | 0.5 | 53.3 min (8 ev) | 6.7 min | 429 MB |

Two cautions on these. First, **single-job wall times scatter by a factor ~4** between jobs of
the same nominal configuration (w = 1.5 at dx = 0.20 gave 55.7 min/event while dx = 0.40 at the
same w gave 13.7), so the table brackets a range rather than predicting a number. Second,
`music_seconds` in the grid-extent diagnostic is **not** wall time — it exceeds the measured job
wall time — so it cannot be used to size a batch.

### 11.2 What to request

**RAM.** The peak RSS is set by the freeze-out/afterburner stage, not the lattice, and it does
**not** fall with dx at coarse spacing (measured 0.6–0.9 GB at dx ≥ 0.25, 171 + 3.87/dx² MB
only for dx ≤ 0.10). At the production candidates the measured peaks are 259–780 MB, so:

| setting | request | rationale |
|---|---|---|
| dx = 0.15, any w in the prior | **1 GB** | measured peak 780 MB → 31 % headroom |
| dx = 0.20 | **1 GB** | measured peak 351–878 MB |
| dx ≤ 0.10, w = 1.5 | **2 GB** | measured peak 1109 MB — the one case that needs it |

**Disk.** `request_disk` refers to the **worker's local scratch**, not the data disk: the
submission directory only ever receives `spvn_results` via `transfer_output_files`, and the
whole campaign directory is 1.9 GB on the data disk. The scratch holds the per-subevent iSS
particle lists, which at 100× sampling is ~54 M particles × 13 B ≈ 700 MB per subevent and there
are 10 subevents, plus the concatenated copy. The peak was never measured directly, so the
honest statement is that 60 GB has always been comfortable and the requirement is dominated by
100× sampling; at 1× it is a small fraction of that. **Recommendation: 20 GB at 1× sampling,
60 GB at 100×** — and note the peak local scratch is the one quantity here that has not been
measured, so it is the one to watch on the first production batch.

### 11.3 Batch size

The requirement is a **minimum** of ~1 h per batch, so the fastest batch still amortises the
per-job overhead (image staging, `generate_jobs.py` setup, output transfer).

At dx = 0.15 the per-event cost is dominated by centrality, and the measured spread is large:
MUSIC time per event runs 162 s (most peripheral) to 834 s (most central) at dx = 0.15, and the
measured job mean is 9.3 min/event at 1× sampling. Taking the fastest event as the floor
(≈ 4 min/event wall) and the slowest as the ceiling (≈ 15 min/event):

| sampling | dx | events/job | min job | max job |
|---|---|---|---|---|
| 1× | 0.15 | 16 | ~1.1 h | ~4 h |
| 1× | 0.20 | 24 | ~1.6 h | ~6 h |
| 100× | 0.15 | 4 | ~0.3 h | ~1 h |

**16 events per job at dx = 0.15 with 1× sampling** is the setting that satisfies the ≥1 h
minimum in the worst case (fastest events) while keeping the slowest batch bounded. The
100× rows are already close to the floor at 4 events/job, which is why the convergence
campaign used 4.

### 11.4 How much oversampling production needs

The event-to-event scatter of the single-event `v_n` is what the emulator has to reproduce, and
it is **almost unaffected by the sampling level** — same events, w = 0.50:

| n | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| scatter(1×)/scatter(100×) at dx = 0.15 | 1.11 | **0.99** | 1.12 | **0.99** | 1.14 |
| at dx = 0.20 | 1.29 | 1.01 | 1.06 | 1.04 | 1.16 |

For n ≥ 2 the ratio is 0.99–1.06, i.e. **1× sampling does not inflate the physical
fluctuation structure** — the per-event thermal noise (scatter 0.0012) is 20× smaller than the
event-to-event scatter for v₂ and only becomes comparable for n = 1, where the inflation is
11–29 %.

**So 1× sampling is adequate for n ≥ 2** and marginal for n = 1. What 1× does cost is
per-event *label* noise: the two levels differ by 0.0012 per event (5 % of v₂), which averages
away as 1/√N for ensemble observables but is an irreducible label noise for event-by-event
predictions. That is the trade to make, and it is a physics decision rather than a numerical
one. The intermediate setting (`number_of_particles_needed` = 1e6, ~10× sampling) would cut
that by √10 = 3.2 for roughly 3× the per-event cost.
