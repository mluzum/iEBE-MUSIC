# AGENTS.md — iEBE-MUSIC (NewChain)

Event-by-event relativistic heavy-ion collision simulation driver. This is **not** an importable
library: top-level scripts generate job folders and cluster submission scripts. There is **no test
suite, no linter config, and no typechecker** — verification means running one event end-to-end.

## Architecture

- `generate_jobs.py` — main entrypoint. Imports a user parameter file with `__import__`, then writes
  `<working_folder>/event_<id>/` (each with `submit_job.script`, `hydro_plus_UrQMD_driver.py`,
  `run_trento.sh`) plus a shared `<working_folder>/model_parameters/` of generated MUSIC / iSS /
  TRENTo input files.
- `config/parameters_dict_master.py` — merges the user dict (and optional bayesian/posterior file)
  and emits the actual solver input files. It is the executable spec of every available parameter;
  read it instead of guessing key names.
- `config/parameters_dict_user_*.py`, `config/design_points/*` — user parameter files. Plain Python
  modules defining top-level dicts (`control_dict`, `trento_dict`, `free_streaming_dict`,
  `music_dict`, `iss_dict`, `isobars_conf_dict_{target,projectile}`, `isobar_seed_file`).
- `codes/` — external physics codes fetched at setup (`*_code` dirs are gitignored) plus two
  in-repo drivers: `codes/hydro_plus_UrQMD_driver.py` (copied into every event folder; takes
  **positional** args, no argparse) and `codes/isobar_sampler_code/exec/build_isobars.py`.
- `Cluster_supports/{OSG,HTCondor}/generate_submission_script.py` — Singularity+condor generators
  that emit `singularity.submit` + `run_singularity.sh`. These are a *separate* path from
  `generate_jobs.py` (which covers `local`, `nersc`, `wsugrid`, `guillimin`, `mcgill`, `stampede2`,
  `anvil`). See `Cluster_supports/HTCondor/README.md`.
- `analysisKit/` — post-processing from `spvn_results_*.h5` (pickle -> merge -> analyze; see its
  README). `utilities/` — result collection/merging into HDF5.

## Setup

```bash
cd codes && bash get_code_packages.sh && bash compile_code_packages.sh && cd ..
```

30–60 min. This also downloads EOS tables, hdf5 delta-f tables, and nucleus configurations.
On NERSC export `PYTHONIOENCODING=utf-8` and `LC_CTYPE=en_US.UTF8` first.

## Commands

```bash
# one event, local machine
python3 generate_jobs.py -w test_dp0 -n 1 -par config/design_points/parameters_dict_user_TRENTo_dp0.py
cd test_dp0/event_0 && bash submit_job.script

# explicit global event range (inclusive; overrides -n)
python3 generate_jobs.py -w dp0 -c local --event_start_id 0 --event_end_id 999 \
  -par config/design_points/parameters_dict_user_TRENTo_dp0.py -n_th 4

# HTCondor/OSG: generate then submit
python3 Cluster_supports/OSG/generate_submission_script.py -param <par.py> -singularity <img.sif> \
  -n 10 -nev 1 -nth 1 -jobid <Name>          # writes singularity.submit
condor_submit singularity.submit

# design-point sweeps (run from the directory that will hold the DesignPointN folders)
python3 MakeDictionaries.py <design.csv> --start-design-point 1 --end-design-point 250
python3 submit_design_points.py --dry-run      # then without --dry-run

# collect finished events into a merged HDF5
./collect_events.sh <fromFolder> <toFolder>
```

`python3 generate_jobs.py -h` and running `generate_submission_script.py` with no args print full
defaults — prefer those over guessing flags.

## Gotchas

- **Reproducibility is assumed, not demonstrated.** The seed scheme is counter-based and the
  container pins the framework to an exact SHA, but nobody has yet run the same event twice on
  local HTCondor and once on OSG and diffed the nucleus HDF5. The common-random-numbers design
  rests entirely on this. See Phase E2 in `EMULATOR_SWEEP_PLAN.md`; treat it as blocking.
- **Pin thread counts.** OpenMP/MPI reduction order in MUSIC can change `v2` in the last bits for
  *identical* input, so a 4-thread and an 8-thread run are not bit-identical even when the nucleon
  configurations are. Pin `OMP_NUM_THREADS`/`MKL_NUM_THREADS` in the job script and record the
  value in the event's output directory, so a future mismatch is diagnosable. Do not assert
  bit-identity of observables without measuring it — assert it of the nucleus HDF5, which must be
  exact.
- **Merge results by event id, never by completion order.** Each event owns a global id
  (`--event_start_id`/`--event_end_id`); parallel jobs finish out of order.
- **`tar` output must not depend on directory iteration order** if archives are compared across
  runs.
- **The sign of `beta_3` is a rotation, not a physical degree of freedom.** `Y_30` is odd in `z`, so
  a π rotation about x maps the `beta_3 = +b` surface onto `beta_3 = -b` (verified to 6.7e-16). The
  magnitude is the parameter. Do not spend a design axis on the sign.
- **Fetched code packages may be absent.** `codes/hadronic_afterburner_toolkit`,
  `codes/hadronic_afterburner_toolkit_code/ebe_scripts/average_event_spvn_h5.py` and
  `config/hadronic_afterburner_toolkit` are gitignored; without them `generate_jobs.py` cannot
  build a full event tree. Run `codes/get_code_packages.sh`.
- **Run `generate_jobs.py` from the repo root.** `isobar_seed_file` is resolved with
  `os.path.abspath` against the *current working directory*, not the parameter file's directory.
  This only applies to the legacy `seed_source: "file"` path — the default `philox` path reads no
  file at all.
- **Nucleon seeds are generated, not shipped (default `seed_source: "philox"`).** Event *g* maps to
  pool addresses `(2g)*2654435761` and `(2g+1)*2654435761 mod 2**32`, and each row is drawn from
  `numpy.random.Philox(key=master_seed, counter=address*2**24)`. **The address must depend only on
  the global event id, never on any nuclear parameter** — that is what keeps design points
  synchronised, so each sees the same nuclei and the deformation shows up as a small shift in
  positions. `MASTER_SEED = 8675309` is recorded in `EMULATOR_SWEEP_PLAN.md` and in every generated
  parameter dictionary; changing it invalidates all existing results. The committed
  `shared_seeds/nucleon-seeds.hdf` remains only for the legacy `seed_source: "file"` path.
- **`build_isobars.py` caches its step+Gaussian fit.** `Rst_w_from_WS` (a BFGS `minimize` over
  `quad`/`polylog`) costs ~2.4 s and is a pure function of `(WS_radius, WS_diffusiveness)`, but the
  shipped configs don't set `step_radius`/`step_diffusiveness`. The sampler therefore writes the
  result back into the run's own YAML with the `(R_ws, a_ws)` signature it came from, and later
  events in the same event folder reuse it. `run_trento.sh` rewrites that YAML per event via
  load-modify-dump, so the cache survives. Don't "clean up" the `_step_gaussian_cache` /
  `step_radius` keys — removing them silently costs ~2.4 s per invocation.
- The committed `shared_seeds/nucleon-seeds.hdf` is 63 MB with shape `(10000, 300, 6)`.
  `isobar_samples.number_nucleons.value` must be **<= 300**: `build_isobars.py` truncates each seed
  row to `number_nucleons` and exits 1 if `A` exceeds the available entries. Shipped templates use
  96/197, which is fine.
- Without `--nocopy`, `generate_jobs.py` `copytree`s the entire `codes/` tree into the working
  folder. `-c osg` forces `--nocopy` and also does `seed += job_id`.
- **`Cluster_supports/HTCondor/generate_submission_script.py` and the OSG one are separate
  submission paths from `generate_jobs.py`.** The HTCondor generator has its own defects history:
  it used to omit `--event_start_id`, so every job recomputed the same events, and it globs
  `EVENT_RESULTS_$(Process)` although the driver names results after the *global* event id. It now
  mirrors the OSG path (job *P* owns events `[P·N, P·N+N-1]`) and collects via an EXIT trap into
  `results_$(Process)/`. If you touch one generator, check whether the other needs the same change.
- The OSG **SMASH** branch still hardcodes `event_0` (no event range is passed). The UrQMD branch —
  which is what `afterburner_type: "decay"` uses — is correct. Avoid SMASH until that is fixed.
- **Never overwrite a path already published over OSDF.** OSG caches OSDF content by path, so
  overwriting a `.sif` in place leaves the cache serving the *old* bytes. The failure is
  inconsistent and therefore dangerous: some workers recompute the checksum from the local file
  and go on hold with `Pelican Client Error: checksum mismatch`, while others fetch the cached copy,
  both sides agree, and the job **silently runs the wrong image**. This actually happened —
  `iebe-music_slim.sif` was refreshed under the same name and two batches ran ~10 minutes against
  the previous, uninstrumented image before it was caught. Publish every image under a unique
  commit-named path (`iebe-music_slim_<short-sha>.sif`) and reference *that*; never use a mutable
  alias. When a batch's results are needed, check the image path in the submit file before
  concluding anything about the numbers.
- **Never reuse a published SIF filename, even for a "new" build.** Commit-named paths
  (`iebe-music_slim_<short-sha>.sif`) only protect you if the commit actually changed the
  image. They do not when the `Dockerfile` pin lags `HEAD`: two builds can both be built
  from `HEAD = 4723b7e` while containing different pins, so the second overwrites the first
  under the same path and OSG's OSDF cache keeps serving the stale bytes. That happened here
  and the workers pulled the *previous* image (`def37b56...`) while the server reported the
  current one (`443fcee...`). **Put the md5 prefix in the filename**
  (`iebe-music_slim_<sha>_<md5prefix>.sif`) so uniqueness does not depend on the commit
  having moved, and derive the name from the pinned SHA rather than from `HEAD`.
- **OSG resource requests: ask for 1 GB, not 4.** Peak RSS for a 19-event 76Ge batch on one core
  was 212 MB, so the old 4 GB default requested ~19x what is used purely for scheduling speed.
  `request_disk` must cover the *whole* batch, not one event, because events run sequentially into
  one working directory; it is now settable with `-disk` (default 10 GB). Run large batches from
  the data disk (`/ospool/ap40/data/matthew.luzum`, ~465 GB) so results land there, but keep
  condor `log`/`error`/`output` on the home disk, which the generator already does via an absolute
  `home_log_dir`.
- Root-level `collect_events.sh`, `combine_multiple_hdf5.py`, `average_event_spvn_h5.py` are
  gitignored because `generate_jobs.py` copies them into the CWD. Missing-from-git is not a bug.
- `submit_design_points.py` contains machine-specific hardcodes that must be edited before use:
  `DEFAULT_OSG_SCRIPT = /home/joaopaulo.picchetti/iEBE-MUSIC/...` and a singularity image under
  `$DATA/singularity_repos/`.
- `MakeDictionaries.py` defaults to a `./design` CSV that is **not in the repo** — supply your own.
  Columns are strict: `WS_radius`, `WS_diffuseness`, `beta_2`, `gamma`, `beta_3`, `nucleon-width`,
  `tau`, `reduced-thickness`, `sigma_k`, `shear_viscosity_3_*`, `bulk_viscosity_3_*`, `T_freeze`
  (plus optional `beta_max`, `number_nucleons`). `sigma_k` is the JETSCAPE axis and is converted
  to TRENTo's `fluctuation` as `k = 1/sigma_k**2`; a `fluctuation` column (k itself) is only used
  when `sigma_k` is absent. `number_nucleons` is *not* taken from the CSV — it stays at the
  template value unless a `number_nucleons` column is supplied.
- **`gamma` is degrees in the CSV and radians in the isobar YAML.** The sampler treats
  `isobar_conf['gamma']['value']` as radians everywhere (see its own comment at
  `build_isobars.py:375`), while the design matrix documents `gamma` in degrees (prior
  [0, 60]). `MakeDictionaries.py` converts; if you write a parameter file by hand, convert
  there too, or 60 becomes 60 rad.
- **Every key `MakeDictionaries.py` writes must match `config/parameters_dict_master.py`
  exactly.** The merge is `dict.update()`, so a misspelt key is silently carried along
  unused and the master default wins — no error, no warning. This hid the whole `zeta/s`
  block: `bulk_viscosity_3_max` vs the master's `bulk_viscosity_3_zeta_over_s_max` meant
  axes 10-12 of the design were constants. Audit with
  `set(user_dict) - set(master_dict)` per dictionary. (`music_dict['T_freeze']` is the one
  expected extra: the driver reads it out of the generated MUSIC input.)
- **The yield normalisation uses the same window it counts in.** The toolkit's
  `drapidity = rap_max - rap_min` and its particle cut are the same window, so
  `dN/dy = N(in window)/(window width)`. That is right *only* because the density is flat
  in rapidity: identified species (`rap_type = 1`) are flat to 0.7 % for |y| < 4, but the
  all-charged references `9999`/`99999` are forced to `rap_type = 0`, i.e. pseudorapidity,
  whose y→η Jacobian gives a ~25 % mid-rapidity dip and a window-dependent "yield". Use
  identified particles in rapidity for the yield. The `_vndata_diff_y_-0.5_0.5` filename
  suffix is hardcoded and stale — the table is filled over `rap_min..rap_max`.
- **The master's `music_dict` is the only thing that decides the viscosity.** MUSIC has always
  supported the JETSCAPE parametrisation (`T_dependent_Shear_to_S_ratio = 3` with
  `shear_viscosity_3_eta_over_s_{T_kink_in_GeV,low_T_slope_in_GeV,high_T_slope_in_GeV,at_kink}`,
  and `T_dependent_zeta_over_s = 3` with `bulk_viscosity_3_zeta_over_s_{max,T_peak_in_GeV,
  width_in_GeV,lambda_asymm}`), but the master only forwarded a constant `Shear_to_S_ratio` and
  the fixed-shape option 7 until 2026-10-22, and `shear_relax_time_factor` was never forwarded at
  all (so every run silently used MUSIC's default 5.0). Option 7 has **no** amplitude knob, so
  `(zeta/s)_max` was not a tunable parameter before the switch. Every ge76 param file inherits
  this block from the master, so changing the master changes every run that does not override it;
  set `T_dependent_Shear_to_S_ratio = 0` + `Shear_to_S_ratio = 0.12` + `T_dependent_zeta_over_s = 7`
  to reproduce anything from before that date.
- The OSG/HTCondor generator copies the seed HDF5 next to the param file and references it by
  basename. That root-level `nucleon-seeds.hdf` is **not** gitignored — do not commit it.
- `README.md` references `generate_event_batches.py` / `submit_job_batches.py`; neither exists in
  this tree. Use `--event_start_id/--event_end_id` instead.
- Root-level `collect_events.sh`, `combine_multiple_hdf5.py`, `average_event_spvn_h5.py` are
  gitignored because `generate_jobs.py` copies them into the CWD. Missing-from-git is not a bug.
- `hydro_plus_UrQMD_driver.py`'s positional argument order is assembled in
  `generate_full_job_script()` (`generate_jobs.py:266`) — change both sides together.

- **`hadronic_afterburner_toolkit`'s `Analysis.cpp` ignores `rap_min`/`rap_max`.** `FlowAnalysis()`
  constructs one `singleParticleSpectra` per entry of a hardcoded list of experimental acceptance
  windows (ALICE ±0.5, STAR ±1, CMS ±2.4, ATLAS ±2.5/±4.9, V0A/V0C, PHENIX BBC, ...) and calls
  `paraRdr.setVal("rap_min", ...)` before each. Editing `rap_min` in `parameters.dat` changes
  nothing. The identified-species `_vndata_y_-0.5_0.5` files are ALICE's window, not yours. Any new
  rapidity analysis has to be added as another entry in that list - see the boost-invariant
  `_boostinv` block and `codes/patches/hadronic_afterburner_toolkit_boost_invariant_dNdy.patch`.
- **Boost-invariant dN/dy must not be cut in rapidity.** For (2+1)-d runs the density is flat and
  `dN/dy = N(all particles)/(y_RB - y_LB)`. The toolkit's `dN_ev_avg = Q0/N_events/(rap_max-rap_min)`
  computed on a cut window loses the daughters that decayed outside it and is biased low (0.7 % at
  ±4, worse toward the edge). `dNdy_normalization_width` switches to the no-cut estimator and is
  derived from `iss_dict` only when `music_dict['boost_invariant'] == 1`; it must stay 0 for
  (3+1)-d runs. The `9999`/`99999` references use pseudorapidity and never get it.

- **An event is identified by `(MASTER_SEED, seed_add, event_id, iev)` — all four, and
  `seed_add` must never be random.** The freeze-out seed is
  `np.random.default_rng([seed_add, event_id, iev])`, the TRENTo seed is `event_id + 1`, and the
  nucleon pool address depends only on `event_id`. The OSG and HTCondor generators used to draw
  `seed_add` with `random.SystemRandom().randint(0, 1e7)` once per submission, so every design point
  got its own private event set and the common random numbers the ensemble rests on were silently
  absent. The 2026-10-22 corner run is the documented case: three corners, seeds 9418965, 4477493
  and 1182519. It is now `CAMPAIGN_SEED_ADD = 0`, overridable with `IBEM_SEED_ADD` only for
  deliberately uncorrelated exploratory runs.
- **`b_max` is per design point on purpose; do not "simplify" it to a campaign constant.** It is
  computed from `WS_radius`, `WS_diffusiveness`, `nucleon-width` and the 2-sigma deformation, so a
  larger nucleus draws a proportionally larger `b`. That is what keeps `b/b_max` — not `b` — the
  synchronised variable between design points: the same event index at a bigger `WS_radius` stays at
  the same centrality instead of drifting more central. Fixing `b` in fm instead would *reduce* the
  cancellation of statistical error between design points.
- **`events_drawn.csv` records every drawn event, including the ones that never collide.** TRENTo
  returns `mult = 0` when two randomly oriented deformed nuclei miss each other, and such an event
  produces no `spvn_results`, so without this file it is invisible downstream and the merged HDF5
  just has fewer rows than were requested. The CSV (`event_id, b, b_max, b_over_bmax, mult, status,
  seed_add`) is rewritten per event, keyed by event id, so the adaptive-grid rerun cannot duplicate
  rows. Centrality percentiles need the count of failures, not only the count of survivors.


## Style

YAPF only, google-based, configured in `.style.yapf` (2-space before comments, split before
arithmetic/logical operators). Run `./formatCode.sh` before committing; it formats the repo root and
`analysisKit/` to depth 2 and silently no-ops if `yapf` is not installed. Match the surrounding
spacing of generated files rather than reformatting them wholesale — many are machine-generated with
odd indentation.