# Handoff: TRENTo-only total cross sections for both campaigns

Purpose: compute the total (and inelastic) nucleus–nucleus cross section for
every design point of both campaigns from TRENTo alone — no iSS/MUSIC/UrQMD —
and record it per design point. This is a separate, fast workload; it does not
need the campaign session's state.

---

## 1. Should this be its own session?

Yes. It is self-contained, it has its own output tree, and it can run while the
campaign continues:

* Load on the OSG queue: a TRENTo-only event takes seconds. Pack many impact
  parameters per job (e.g. 100 runs/job) and the whole scan is a few hundred
  short jobs — negligible next to the campaign's ~25k.
* The 50k-per-owner cap is shared. Keep the cross-section tranche small (a few
  thousand jobs) and submit it in chunks, exactly as the campaign feeders do.
* Nothing in this document depends on the campaign session being alive.

What follows is everything that session needs.

---

## 2. Where the design information lives

### A=76 campaign (76Ge + 76Ge)

| what | path |
|---|---|
| design matrix | `design/design_lhs2000.csv` (2000 rows, 25 columns) |
| rows actually used | 1-1500 (the maximin prefix; dp1501-2000 were never submitted) |
| per-point parameters | `DesignPoint<N>/parameter_dictionary_design_point_<N>.py`, N = 1-1500 |
| generator | `scripts/make_design.py` (unit-cube LHS + maximin order, seed 8675309) |
| prior ranges | the `PRIOR` list in `make_design.py` |
| campaign outputs (local) | `/data/mluzum/ge76_results/merged/<dp>/<dp>.h5` (1460 points) + `prod/` raw archives |
| event draw records | `/data/mluzum/ge76_results/merged/<dp>/csv.tgz` |

### A=96 campaign (96Zr/96Ru, A=96)

| what | path |
|---|---|
| design matrix | `design/design_lhs2000_A96.csv` (2000 rows, same columns) |
| rows actually used | 1-1000 |
| per-point parameters | `zr96_design/DesignPoint<N>/parameter_dictionary_design_point_<N>.py`, N = 1-1000 |
| generator | `scripts/make_design_a96.py` (same unit-cube design, rescaled priors) |
| prior ranges | `design/A96_priors.md` and `PRIOR_A96` in that generator |
| staging (submit side) | `/home/matthew.luzum/zr96_stage` on the AP |
| campaign outputs | AP: `/home/matthew.luzum/zr96_prod/<dp>/` (transient); local: `/data/mluzum/zr96_results/` |
| event draw records | `/data/mluzum/zr96_results/merged/<dp>/csv.tgz` (as points complete) |

Both design files are **the same normalized Latin hypercube** (identical
unit-cube coordinates row for row, verified to 1.7e-9), so `design_000k` in one
campaign is the same point in normalized space as `design_000k` in the other.

All parameters that TRENTo needs are in the design row itself (columns are
documented in the CSV header) plus the derived `b_max` (next section). Nothing
about the cross section depends on hydrodynamics or on the results files.

---

## 3. `b_max` — per design point, and where to get it

`MakeDictionaries.bmax_from_design(row)` computes it from the design row:

```
b_max = 1.789 * sqrt( R^2 * [1 + (7/(4*pi))*(beta_2'^2 + beta_3'^2)]
                      + (7*pi^2/3)*a^2 ) + w + 0.5
```

with `R = WS_radius`, `a = WS_diffusiveness`, `w = nucleon-width`,
`beta_2' = beta_2 + 2*sigma_plane`, `beta_3' = beta_3 + 2*sigma_beta_3`.
It is used as the upper end of the uniform impact-parameter draw and is
recorded per drawn event in the CSVs (column 3, constant within a design point).

Quick ways to get it:

* from the draw CSV: any row's `b_max` column (needs a pulled point), or
* recompute with `python3 -c "import MakeDictionaries as m; ..."` from the design
  row — deterministic, no campaign data required.

---

## 4. What already exists that bears on the cross section

Each `events_drawn_<block>.csv` row is one TRENTo draw:

```
event_id,b,b_max,b_over_bmax,mult,status,seed_add
```

`mult > 0` means the two nuclei collided; `mult = 0` means they missed. The
campaign drew `b` uniformly in `[0, b_max]`, so per design point:

```
P_inel(b) is sampled on [0, b_max];   sigma_inel_lower = pi * b_max^2 * N(mult>0)/N_drawn
```

**That is a lower bound, not the total cross section.** The campaign's `b_max`
is a finite geometric estimate, and the measured capture is still ~88% in the
last 5% of the range (`b/b_max` 0.95-1.00) — there is a real inelastic tail
beyond `b_max` that the campaign never sampled. For the *total* cross section
the scan must extend beyond `b_max` until `P(b) -> 0`.

---

## 5. How the TRENTo-only run works

The campaign's TRENTo stage is a generated shell script,
`generate_jobs.py:generate_script_trento` -> `run_trento.sh <event_id>`, which

1. writes the isobar-sampler configs for target/projectile with the design
   point's nuclear shape (`WS_radius`, `WS_diffusiveness`, `beta_2`, `gamma`,
   `beta_3`, widths) and the **event id as the nucleus-pool address**
   (`build_isobars.py`, one configuration), then
2. writes the TRENTo `input` (normalization, reduced-thickness, fluctuation
   `k = 1/sigma_k^2`, `b` and the b range, nucleon width) and calls

```
./trento -c input --random-seed=$((event_id + 1)) > run.log
```

3. TRENTo writes `TRENTo/trento_results/**/0.dat`, whose header carries
   `# b = <fm>` and `# mult = <...>`, plus `sampling_metadata.json` with the
   impact parameter. The driver reads exactly these two numbers
   (`codes/hydro_plus_UrQMD_driver.py:587-635`) to fill the CSV.

Consequences for the cross-section scan:

* **Same nuclei, same seed scheme.** Event id -> nucleon pool addresses and
  `trento_seed = event_id + 1`. Reuse the campaign's event ids (or a dedicated
  range) to reproduce identical nuclei; do not invent a new random scheme.
* **Impact parameter is inside the generated input**, not a command-line
  argument. A scan must generate one input per `b` (or set a fixed `b` and a
  narrow range) — this is the one piece of new code needed: a thin wrapper
  around the same isobar-sampler + trento calls that loops over `b`.
* **No hydro required**: stop after `./trento`. A TRENTo-only job only needs the
  container (same image), the parameter dictionary (for the nuclear shape and
  TRENTo knobs), and the event id.

Suggested implementation sketch (not yet written):

```
for each design point dp:
    b_grid = 0 .. (b_max + 6 fm) in steps of 0.25 fm
    for each b in b_grid:
        run TRENTo with the dp's parameters at that fixed b, same seed scheme
        record (b, mult)          # mult > 0 means inelastic
    sigma_inel(dp) = 2*pi * sum(b * P_inel(b) * db)
    sigma_tot(dp)  = pi * b_zero^2   # b_zero: smallest b where P(b)=0,
                                     # or 2*pi*int b P_any(b) db
```

A job should carry its whole (dp, b-grid) payload — one job per design point is
already only ~30-60 short TRENTo runs, and 2,460 design points become ~2,460
jobs, which fits the queue rules used by the campaign (chunks, priority, cap).

---

## 6. Output layout and provenance

Suggested, mirroring the campaign convention (paths are proposals, not yet
created):

```
/data/mluzum/cross_sections/a76/dp<N>/cross_section.csv     b, mult, P_inel
/data/mluzum/cross_sections/a76/summary.csv                 dp, sigma_inel, sigma_tot, b_max, n_draws
/data/mluzum/cross_sections/a96/...                         same
```

Record in each summary row: design file and row, `b_max` used, the b-grid, the
number of draws per b, and the seed/event-id range, so the numbers can be
re-derived. The distinction to keep explicit is **inelastic** (mult > 0) versus
**total/geometric** (the b at which all collisions cease).

---

## 7. Open decisions for that session

1. Precision target: how many TRENTo draws per b per point (the campaign used
   2000 draws over `[0, b_max]`; a scan with 50-100 b values x 20-50 draws is
   comparable and much cheaper).
2. Whether to reuse the campaign event ids (identical nuclei to the production
   run) or a fresh id range (independent sample); reusing is preferable for
   consistency and costs nothing.
3. Whether `sigma_tot` should be defined as the geometric `pi*b_zero^2` or as
   `2*pi*int b P_any(b) db`; for a sharp-edged TRENTo these agree, but the
   definition should be stated in the output.
4. Whether to also write the elastic cross section (`sigma_tot - sigma_inel`).

---

## 8. What NOT to depend on

* The campaign session's in-memory state and its `/tmp/opencode` state files.
* The AP queue's current contents — the cross-section jobs are independent.
* `merged/*/csv.tgz` for the *total* cross section: it is truncated at `b_max`
  by construction and only supports the lower-bound estimate in section 4.
