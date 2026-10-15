# Flow output format (`spvn_results_*.h5`)

Definitive description of what the hadronic afterburner toolkit writes, read from
`single_particleSpectra.cpp` / `particleSamples.cpp` of
`github.com/chunshen1987/hadronic_afterburner_toolkit`. Do not infer column meanings
from the numbers — two of them are genuinely counter-intuitive and are flagged below.

All datasets live in the group `spvn_results_<event_id>` and keep their original
filenames including the `.dat` suffix.

---

## 1. Rapidities and pT bins

The bins are **analytic and fixed**; they are not stored in the file.

```
dpT       = (pT_max - pT_min) / npT
bin i     = [ pT_min + i*dpT , pT_min + (i+1)*dpT )
bin centre=   pT_min + (i + 0.5) * dpT
```

Defaults: `pT_min = 0.05`, `pT_max = 4.05`, `npT = 41`. At the production setting
`npT = 81`, `dpT = 0.049383 fm/c` and the first edges are 0.0500, 0.0994, 0.1488 ...

**Read these from the parameter file, not from the data.** `npT`, `pT_min` and `pT_max` are
in `model_parameters/hadronic_afterburner_toolkit/parameters.dat`; the production values are
`npT = 81`, `pT_min = 0.05`, `pT_max = 4.05`. The number of rows in a `_diff_` file equals
`npT` exactly and there is no totals row in that file, so a row count that disagrees with
`npT` means the run used a different setting than the file you are looking at.

**Rapidity is not binned in the retained files.** The per-species files use a single
acceptance window `rap_min .. rap_max` (`-4.0 .. 4.0` in production, `rap_type` selecting
`y` vs `eta`). The one binned-in-rapidity table, `particle_<pid>_pTeta_distribution.dat`, has
`n_rap = 141` bins spanning `rapidity_dis_min .. rapidity_dis_max`, and is **pruned by
default** — see section 5. `n_rap` stays 141 whatever `rapidity_dis_min/max` are set to, so
that overhead cannot be trimmed by parameter.

> **TRAP.** Column 0 of the `_diff_` files is **NOT the bin centre**. It is the mean pT of
> the particles that happened to land in that bin **in that event**:
> `mean_pT = pT_mean_array[ipT] / Qn_diff_vector_real[0][ipT]`.
> Measured rms deviation from the true centre is 0.0036 fm/c, and it moves by up to
> 0.0125 fm/c from event to event. Use the analytic edges above. Inferring edges from
> column 0 gives wrong edges and makes the file look inconsistent between events.

---

## 2. `particle_<pid>_vndata_diff_<rap>.dat` — pT-differential, per species

Rows: `npT` pT bins. Columns (as written when `ecoOutput = 1`):

| col | meaning |
|---|---|
| 0 | mean pT of the particles in this bin, **this event** (see trap above) |
| 1 | `EdN/dp^3p` — **n = 0, the yield** |
| 2,3 | `Qn_real(pT)`, `Qn_imag(pT)` for n = 1 |
| 4,5 | n = 2 |
| ... | interleaved (real, imag) per harmonic |
| 12 | `total_NpT` — **particles of this species in this pT bin** |

Column count is `2 + 2*n_harmonics + 1` (mean-pT, n=0 yield, real/imag per harmonic, `total_NpT`).
Verified shapes at the production setting: identified species `(npT, 13)` differential and
`(7, 5)` integrated; pid `9999` `(npT, 21)` and `(11, 5)`; pid `99999` `(npT, 13)`.

* `Qn_real/imag(pT) = Qn_diff_vector_real/imag[n][iP] / Qn_diff_vector_real[0][iP]`
  — a per-particle average **within the bin**, i.e. a v_n, *not* a density.
  To get a v_n(pT) density you must multiply by the bin's particle content.
* `EdN/dp^3p = dNpT_ev_avg / mean_pT / dpT / (2*pi) / drapidity`, i.e. the
  Lorentz-invariant differential yield. Converting to `dN/dy` needs the pT weight and
  the pseudorapidity Jacobian.
* The number of harmonics is **capped for everything except pid `9999`**:
  `single_particleSpectra.cpp:52` — `if (particle_monval != 9999) order_max = 6;`
  Only the *unidentified* reference keeps the full `order_max` (n up to 9 → 21 columns).
  Every identified species **and the all-charged `99999` reference** are capped at
  **n up to 5** → 13 columns, regardless of the `order_max` parameter. This was
  initially documented backwards (it was recorded that "all-charged gets 9"); the
  shapes above are the measured ground truth.

No statistical-error columns are written when `ecoOutput = 1`; estimate errors from
`total_NpT` (column 12).

---

## 3. `particle_<pid>_vndata_<rap>.dat` — pT-integrated, per species

Rows: `1 + (order_max-1) + 1`. Columns:

| row | col 1 | col 2 | col 3 | col 4 |
|---|---|---|---|---|
| `n = 0` | `dN/deta` per event | err | `<pT>` | err |
| `n = 1..` | `Qn_real` | err | `Qn_imag` | err |
| `99` | `total_N` | **`total_number_of_events`** | 0 | 0 |

The final row is the important one:

```
99   total_N   total_number_of_events   0.0   0.0
```

**`total_number_of_events` is the number of iSS resamplings for that event** — the
sample count needed to convert the extensive quantities to per-sample yields. The
comment in the source reads *"this quantity is useful when one wants to reconst the
Qn vectors"*. Verified independently by decoding `particle_list.bin`
(`[int n_particle][n x (int pdg + 9 floats)]`), which contains exactly that many
records.

The errors here are the standard error of the pooled per-particle average,
`sqrt(<cos^2 nphi> - v_n^2)/sqrt(N)`. They are **not** the event-to-event fluctuation,
which is much larger and is what limits single-event use.

---

## 4. Species covered

`vndata_*` files are emitted for 13 identified species
(pi+-, K+-, phi(1020), p+-, Lambda+-, Xi+-, Omega+-) plus `9999` (unidentified) and
`99999` (all charged). Summing identified species reproduces charged hadrons.

---

## 5. Files deliberately dropped by `prune_spvn_output`

Dropped as useless for 2D boost-invariant runs: `*_pTeta_distribution*`
(the 141-rapidity-bin table), `*_evo_*`, `*inverse_Reynolds*`, `*meanpT_estimators*`,
`*_vndata_diff_eta_*`, and identified-species `_vndata_eta_*` (duplicates of `_y_`).
Kept: all `_vndata_diff_y_*` and `_vndata_y_*`, the unidentified/all-charged
references, and the yields.

Note the retained `_y_` filenames still read `_y_-0.5_0.5` after changing `rap_min`/`rap_max`;
the name is stale in the compiled toolkit but the data is correct. Do not parse the
rapidity acceptance out of the filename — take it from the parameter file.

> **TRAP.** The `9999` tables are emitted for **16 hard-coded rapidity windows** compiled into
> the toolkit (`-0.5_0.5`, `-1_1`, `-3.9_-3.1`, `-4.9_-3.1`, `-5.1_-2.8`, `0.5_1`, …). They
> are *not* derived from `rap_min`/`rap_max` and cannot be configured away by parameter, so
> they reappear on every run. `prune_spvn_output` keeps only `particle_9999_vndata_eta_-0.5_0.5.dat`
> and drops the other 15 differential/integrated pairs — those 16 windows are useless for a
> 2D boost-invariant run by the same argument as the 141-bin pT-eta table. The `9999`
> `_y_-0.5_0.5` pair is kept at full length (21 columns, n up to 9).