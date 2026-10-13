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
- Root-level `collect_events.sh`, `combine_multiple_hdf5.py`, `average_event_spvn_h5.py` are
  gitignored because `generate_jobs.py` copies them into the CWD. Missing-from-git is not a bug.
- `submit_design_points.py` contains machine-specific hardcodes that must be edited before use:
  `DEFAULT_OSG_SCRIPT = /home/joaopaulo.picchetti/iEBE-MUSIC/...` and a singularity image under
  `$DATA/singularity_repos/`.
- `MakeDictionaries.py` defaults to a `./design` CSV that is **not in the repo** — supply your own.
  Columns are strict: `WS_radius`, `WS_diffuseness`, `beta_2`, `gamma`, `beta_3`, `nucleon-width`,
  `tau`, `reduced-thickness`, `fluctuation`, `shear_viscosity_*`, `bulk_viscosity_*`, `T_freeze`.
  `number_nucleons` is *not* taken from the CSV; it stays at the template value.
- The OSG/HTCondor generator copies the seed HDF5 next to the param file and references it by
  basename. That root-level `nucleon-seeds.hdf` is **not** gitignored — do not commit it.
- `README.md` references `generate_event_batches.py` / `submit_job_batches.py`; neither exists in
  this tree. Use `--event_start_id/--event_end_id` instead.
- Root-level `collect_events.sh`, `combine_multiple_hdf5.py`, `average_event_spvn_h5.py` are
  gitignored because `generate_jobs.py` copies them into the CWD. Missing-from-git is not a bug.
- `hydro_plus_UrQMD_driver.py`'s positional argument order is assembled in
  `generate_full_job_script()` (`generate_jobs.py:266`) — change both sides together.

## Style

YAPF only, google-based, configured in `.style.yapf` (2-space before comments, split before
arithmetic/logical operators). Run `./formatCode.sh` before committing; it formats the repo root and
`analysisKit/` to depth 2 and silently no-ops if `yapf` is not installed. Match the surrounding
spacing of generated files rather than reformatting them wholesale — many are machine-generated with
odd indentation.