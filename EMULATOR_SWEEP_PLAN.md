# Emulator-targeted design-point sweep — implementation plan

Status: **Phase 0 complete** (branch `NME`, remote `mluzum`, container pinning, sampler ownership
D1). Phases A–F not started. This file is the authoritative plan; it supersedes nothing but should be
read before touching the code paths listed below.

Goal: train an emulator over a large, well-sampled parameter space (nuclear shape, deformation +
its event-by-event fluctuations, TRENTo, viscosity) by running a discrete design-point sweep on
OSG, using `afterburner_type = "decay"` (iSS + resonance decays, no hadronic transport).

---

## 1. Verified findings this plan depends on

All references were checked against the working tree. Re-verify before acting if much time has passed.

| Fact | Ref |
|---|---|
| Isobar-Sampler runs **on the fly, twice per event**, not once per design point | `codes/hydro_plus_UrQMD_driver.py:135-140`, `:244-247`; `generate_jobs.py:344-348` |
| Each invocation builds exactly **one** nucleus (`number_configs = 1`) | `generate_jobs.py:344-348` |
| Event→seed binding is strictly sequential: `target = 2·evid`, `projectile = 2·evid+1` | `generate_jobs.py:326-328` |
| `start_configuration` is bounds-checked against row count ⇒ **hard ceiling of 5000 events** | `codes/isobar_sampler_code/exec/build_isobars.py:643-647` |
| **Whole seed file read on every invocation**, then sliced | `build_isobars.py:636` (read), `:653` (slice) |
| 3× `solve_ivp` at `rtol=atol=1e-10`, depend only on `(R_ws, a_ws, l)` — **not** on β | `build_isobars.py:808-835` |
| β₂/γ/β₃ read once per `isobar1`, applied to every config — **no variance knob exists** | `build_isobars.py:696-703` |
| `deform_nucleus` takes β as **arguments** ⇒ per-config β is a clean threading change | `build_isobars.py:362` |
| `joblib.Parallel` dispatched to build a single nucleus | `build_isobars.py:893` |
| `isobars_conf_dict_*` dumped wholesale to YAML ⇒ **new keys need no plumbing** | `config/parameters_dict_master.py:848-849` |
| Sampler validation is a required-key **list**, not a whitelist ⇒ unknown keys are accepted | `build_isobars.py:530-538` |
| `decay` avoids all afterburner binaries; still produces `spvn_results_*.h5` | `generate_jobs.py:677-683`; `config/parameters_dict_master.py:1008-1012`; `driver:1086-1090` |
| OSG generator dispatches to the broken SMASH branch only for `SMASH` ⇒ `decay` is safe | `OSG/generate_submission_script.py:665` |
| OSG (UrQMD) sets global event ids correctly: `Process·nHydroEvents` | `OSG/…:331-332`, `:354-357` |
| OSG **SMASH** branch passes no event range ⇒ always `event_0` | `OSG/…:602`, `:611` |
| Seed HDF5 is in `transfer_input_files` **per job** ⇒ transfer scales with pool size × jobs | `OSG/…:158-159`; `HTCondor/…:145` |
| HTCondor generator passes **no** event range ⇒ every job is `event_0`; transfer globs use `EVENT_RESULTS_$(Process)` which never matches | `HTCondor/…:158-165` |
| HTCondor `mv`s the tarball **before** `submit_job.script` runs; no `set -e` | `HTCondor/…:283-285` |
| `-seed_file` is documented in that README but absent from its argparse; `SEED_ARG=--isobar_seed_file` would be rejected by `generate_jobs.py` | `Cluster_supports/HTCondor/README.md:43`; `HTCondor/…:511-534`, `:450` |
| Container clones a **branch**, not a SHA; base image is a mutable tag; `h5py`/`PyYAML`/`joblib`/`mpmath`/**`freestream`** unpinned | `docker/Dockerfile:46`, `:1`, `:36-40` |
| `freestream` is a physics input to every event | `driver:359` |
| Dev setup script clones an **unpinned** branch | `codes/get_code_packages.sh:7` |
| Container setup pins Isobar-Sampler at `bc586de0` — **and clobbers the in-tree fork** | `codes/get_code_packages_test.sh:38-42` |
| `make_seeds.py` exists upstream (required by compile step) but is absent from this tree | `codes/compile_code_packages.sh:49` |
| `MakeDictionaries.py` hardcodes `number_nucleons: 96`; never writes `beta_4` | `MakeDictionaries.py:419-422` |
| `combine_multiple_hdf5.py` renames colliding groups with **random letters** ⇒ breaks X/y join | `utilities/combine_multiple_hdf5.py:38-46` |
| Output data dictionary: exact pT bin edges, column layout, `9999` vs `99999` harmonic caps, the 16 hard-coded `9999` rapidity windows | **`analysisKit/FLOW_OUTPUT_FORMAT.md`** — read before writing extraction or analysis code |

---

## 2. Decisions

**D1 — Sampler ownership: in-tree (option b).** The sampler fork stays in this repo and
`get_code_packages_test.sh` is changed to install it *after* cloning instead of letting the clone
overwrite it. Rationale: the sampler changes are physics changes coupled to the parameter
dictionaries, design-point sweep, and fluctuation schema — all of which live here. Splitting them
across two repos means an emulator result cannot be traced to a single commit.

**D2 — Deterministic on-the-fly seed generation.** Replaces seed-file transfer. Uses
`numpy.random.Philox(key=master_seed, counter=row_address·STRIDE)`: a specified, counter-based
generator, so row *i* is a pure function of two integers — independent of call order and of how many
rows were drawn before. This is the property CRN requires. Also obsoletes the 72 MB-per-invocation
read rather than optimising it.

**D3 — Pool as a virtual address space.** Row for event *g* lives at `hash(g) mod M` with
`M ≈ 2³²`, recorded with the master seed in every design-point config. "Pool size" becomes a pinned
modulus, never a resource to be re-allocated. The pool is *not* the committed 63 MB file; that file
is retained only as a fallback path.

**D4 — Synchronization invariant (must hold everywhere).** The nucleus used by event *g* must be
identical across **all** design points. Therefore every quantity that determines the row — master
seed, modulus, hash function — must be a function of *g* alone. Never of the design point.

**D5 — Deformation prior.** Per event: half-normal β₂ `(μ₂, σ₂)`, Gaussian β₃ `(μ₃, σ₃)`, **von
Mises γ `(μ_γ, κ_γ)`**, then map to (β₂₀, β₂₂). von Mises is the natural circular distribution — γ
has period 2π, and `(β₂,γ) ≡ (−β₂,γ+π)` — so this avoids wrapping artefacts and contains the
fixed-deformation limit (σ→0, κ→∞) in the same parameterisation. If `(μ,σ)`-style specification is
preferred, apply the Jacobian `p(β₂₀,β₂₂) = p(β₂,γ)·β₂/√₂`.
Deformation draws come from the **same** Philox stream as the nucleon seeds, with a different counter
offset — one mechanism serving both.

**D6 — Anchor point: deferred.** Chosen after the first analysis, near the MAP. Valid because CRN
makes any design point re-runnable later with more events while remaining exactly comparable
(`--event_start_id/--event_end_id` + `--continueFlag`). Deferring also sharpens emulator validation:
error is smallest where training density is highest.

**D7 — Build args vs hardcoded URLs.** Hardcode. A build arg's value lives in CI/shell history, not
in git; two images could come from one commit, destroying `commit SHA ⇒ image`. But hardening goes
further — pin the commit **SHA** (not the branch), pin the base image by **digest**, and pin **all**
pip dependencies including `freestream`.

---

## 3. Master seed

```
MASTER_SEED = 8675309
```

Chosen once, arbitrarily. **It must never be changed.** Every result depends on it. It is to be:

- recorded in this file (done),
- emitted into every generated design-point parameter dictionary,
- written into every event's provenance record (Phase F),
- committed to git.

Bit-reproducibility additionally depends on numpy staying pinned (Phase 0).

---

## 4. Phases

Strictly sequential unless noted. **A has an explicit measurement gate.**

### Phase 0 — Branch, remote, container pinning, sampler ownership
Create a feature branch; add own GitHub as a third remote (current `origin` → jppicchetti,
`upstream` → genilssom).

In both `docker/Dockerfile` and `docker/Dockerfile_ubuntu`:
- hardcode own fork URL **and commit SHA** (not the branch),
- pin base image by digest,
- pin every pip dependency, `freestream` included.

In `codes/get_code_packages.sh`: pin Isobar-Sampler (currently clones a moving branch).
In `codes/get_code_packages_test.sh`: install the in-tree sampler after cloning (D1).
In `.github/workflows/docker-publish.yml`: let the feature branch publish, or promote to `main`/`dev`.

*Exit:* image builds reproducibly from a known SHA; container contains the in-tree sampler.

**Done, except the image build itself (needs the branch pushed first).** Completed:

- Branch `NME` created; remote `mluzum` → `git@github.com:mluzum/iEBE-MUSIC.git` added
  (`origin` → jppicchetti, `upstream` → genilssom both untouched).
- `docker/Dockerfile` + `docker/Dockerfile_ubuntu`: fork URL and branch `NME` hardcoded; base image
  pinned by digest; all pip deps pinned.
- `codes/get_code_packages.sh`: Isobar-Sampler pinned to `bc586de0` (same fork/commit as the
  container script, replacing the moving `test-newchain` branch); pin enforced explicitly, since
  this script has no `set -e`.
- Sampler fork (D1) preserved across `rm -fr isobar_sampler_code` in **both** setup scripts.
- `.github/workflows/docker-publish.yml`: `NME` added so the branch can publish an image.

Pin values are the *known-good* set read out of an image that built and ran successfully
(Python 3.9.25): numpy 1.24.4, scipy 1.10.1, h5py 3.14.0, PyYAML 6.0.3, joblib 1.5.3, mpmath 1.4.1,
freestream 1.0.1.

**Also done:** framework SHA pinning (the deferred item). Both Dockerfiles now
`git fetch --depth=1 origin <SHA>` + `git checkout FETCH_HEAD` + assert the SHA, instead of cloning
a branch — verified end-to-end against the real remote. Pinned to `868d681`; bump procedure is
documented in the Dockerfiles and the two must be updated together.

Behaviour change to be aware of: `Dockerfile_ubuntu` previously used `get_code_packages.sh`
(unpinned branch tips) and now uses `get_code_packages_test.sh` (pinned commits), matching the el9
variant. This is the parity fix, but those pins have never been built on ubuntu 22.04 — treat the
first ubuntu build as untested.

CI fixes made while validating the above (all on NME):
- `BuildTest.yml` now runs `get_code_packages_test.sh` so CI validates the pinned build the
  container performs. The dev script had drifted: MUSIC's `public_stable` no longer ships
  `EOS/download_hotQCD.sh` (exit 127).
- `get_code_packages_test.sh` was mode 644 while its siblings are 755; `./script` failed with
  "Permission denied". Fixed to 755 and invoked via `bash`.
- `docker-publish.yml`: push/login gated on `DOCKERHUB_*` secrets being present (forks don't
  inherit secrets, and `chunshen1987/iebe-music` is not writable from a fork); `IMAGE_NAME`
  overridable by repository variable.
- **PYTHIA8 acquisition rewritten.** `https://pythia.org/download/pythia83/pythia8315.tgz` now
  returns 404 — as do *every* 8.3.x tarball including the current 8.3.17, with and without a
  browser UA. The URL worked when the last image was built (2026-10-08) and rotted after. Replaced
  with a git pin on the ALICE mirror `alisw/pythia8` at commit `3c980c58` (tag `v8315-alice1`
  = 8.3.15, the version SMASH is built against). Verified by building: produces
  `bin/pythia8-config` reporting `8.315`, plus `libpythia8.{a,so}` and `share/Pythia8/xmldoc`.
  `PYTHIA_INSTALL_DIR` must stay `${HOME}/pythia8315` because `compile_code_packages.sh:186`
  hardcodes it via `-DPythia_CONFIG_EXECUTABLE`.

Housekeeping completed:
- **`shared_seeds/nucleon-seeds.hdf` removed from git** (63 MB, and GitHub flagged it as
  GH001). With `seed_source: philox` nothing reads it. It is now gitignored. The legacy `file`
  path remains functional; `utilities/make_seed_pool.py` generates a pool **reproducibly** from an
  integer seed, which upstream's `make_seeds.py` cannot do (it draws from numpy's unseeded global
  state, so two runs differ).
- The stale `isobar_seed_file = "shared_seeds/nucleon-seeds.hdf"` declaration was removed from the
  shipped parameter dictionaries and from `MakeDictionaries.py`'s output — it pointed at a file
  that no longer exists and is unused under `philox`.

### Phase A — Sampler efficiency (file path)

Measured first, in the container image (Python 3.9 + the pinned dependency set), because the
assumed bottleneck turned out not to be the bottleneck. Per `build_isobars.py` invocation:

| Component | Cost | Action |
|---|---|---|
| `Rst_w_from_WS` — BFGS `minimize`, each step a `quad` of `polylog` | **2.45 s (61%)** | Persist result to the run's YAML |
| Full seed read `f['isobar_seeds'][:,:,:]` (66 MB) | 429 ms | Read only the rows needed |
| `joblib.Parallel` dispatch for a single nucleus | 333 ms (135 ms overhead) | Call directly when `n_configs == 1` |
| 3× `solve_ivp` (depends only on `R_ws`,`a_ws`,`l`) | 120 ms | Memoise |
| Module imports (scipy, mpmath, joblib) | ~307 ms | unchanged |

`Rst_w_from_WS` is a pure function of `(R_ws, a_ws)` — constant for a whole design point — yet was
recomputed twice per event. The computed `step_radius`/`step_diffusiveness` are now written back
into the run's own configuration file with the `(R_ws, a_ws)` signature they came from; later
events in the same event folder reuse them, and a signature mismatch forces a recompute.
`run_trento.sh` already does a load-modify-dump of that YAML per event, so the cache survives.

Results (4 events per folder, seed rows `2·evid`, four shape/deformation scenarios):

| Scenario | Cold event | Warm events | Overall |
|---|---|---|---|
| spherical | 2.48 → 1.67 s | 2.51 → 0.37 s (6.7×) | 3.60× |
| quadrupole | 2.89 → 2.00 s | 2.86 → 0.69 s (4.1×) | 2.81× |
| quad + octupole | 2.84 → 1.98 s | 2.91 → 0.69 s (4.2×) | 2.85× |
| other shape params | 2.72 → 1.85 s | 2.74 → 0.69 s (4.0×) | 2.80× |

**All four scenarios produce bit-identical nucleon coordinates** to the pre-optimisation sampler
(`np.array_equal` on every event). Per event there are two invocations (target + projectile), so
the sampler stage drops from ~5.7 s to ~1.4 s per event on a warm event folder.

Verified separately: cold event computes and caches; `run_trento.sh`-style round trip preserves the
cache and skips the fit; changing `R_ws`/`a_ws` forces recomputation rather than reusing a stale
fit.

*Exit:* identical output hashes on a fixed seed **and** a measured per-event walltime for the
sampler stage. **This number gates everything downstream.**

### Phase C — HTCondor generator fixes *(blocking for local validation)*

Root cause: the generator never passed `--event_start_id`/`--event_end_id`, so
`generate_jobs.py` used its defaults (`event_start_id=0`, `n_jobs=1`) and **every queued job
recomputed events 0..N-1**. The transfer globs, `playground/event_0/EVENT_RESULTS_$(Process)/...`,
could never match either, because the driver names results after the *global* event id. A batch
therefore produced duplicate results and transferred nothing back.

Fixed in both the UrQMD and SMASH branches:

- Event range from `$(Process)`, mirroring OSG: job *P* owns `[P·N, P·N+N-1]`, one event folder
  per job. The range and the EXIT trap are emitted *before* `generate_jobs.py`, so a partial run
  still transfers what completed; the `submit_job.script` invocation stays after, since it needs
  the folder that creates.
- Outputs collected by the trap into `results_$(Process)/`, checkpoint archive written as
  `job_output_$(Process).tar.gz` — replacing globs that never matched.
- **Exit status now propagates.** Both `singularity` invocations used `if ! cmd; then status=$?`,
  where `$?` is the status of the *negation* (always 0) — a failed simulation exited 0, so
  `periodic_remove (ExitCode == 73)` and `on_exit_hold` could never fire. Replaced with
  `|| status=$?`, which is also safe under the added `set -e`.
- Removed the checkpoint `mv`, which ran *before* `submit_job.script` and so referenced a tarball
  that did not exist yet.
- Removed the phantom `-seed_file` option (documented in the HTCondor README but never defined in
  argparse) and the `--isobar_seed_file` flag it fed to `generate_jobs.py`, which does not accept
  that flag. Seeds are detected with the existing helper and staged into `shared_seeds/`.
- Fails loudly at generation time when `isobar_seed_file` is declared but unresolvable, instead
  of emitting a doomed queue.

Verified by executing the generated `run_singularity.sh` against a stubbed `singularity`:

- 4 jobs × 3 events ⇒ events 0..11, **each exactly once, no overlaps**
- mid-run `submit_job.script` failure ⇒ **exit 73**, completed events still transferred, checkpoint
  archive written
- `generate_jobs.py` failure ⇒ **exit 85**, trap still ran
- both branches emit syntactically valid shell

*Exit:* N jobs on the local cluster produce N distinct event ranges and return results.

Note: no container SHA bump was needed for this phase. `Cluster_supports/` runs from the submit
host, not from inside the image; the container only executes `generate_jobs.py`, the driver and the
sampler. Bump the pin when a change must take effect *inside* the container.

### Phase B — Deterministic generation + random selection
- Philox-based row generation keyed on `(MASTER_SEED, hash(g) mod M)`; no file transfer.
- Replace `generate_jobs.py:326-328` arithmetic. Target and projectile drawn independently from the
  virtual pool.
- Deformation z-scores from the same stream (D5).
- Retire the seed file from `transfer_input_files`.
- Keep the file-based path working as a fallback (lazy-read version from Phase A).

*Exit:* over N events, row usage is a full cycle with no repeat until `M` is exhausted, and is
**identical across two different design points** (verifies D4).

### Phase D — Fluctuating deformation

Per-configuration `(beta2, gamma, beta3)` via `sigma_beta_2`, `sigma_beta_3`, `sigma_gamma`. Absent
or zero reproduces the fixed shape exactly, so existing dictionaries are unaffected.

Latent z-scores come from the same counter-based generator as the nucleon seeds, at `purpose=1`
(the upper half of each address' counter range → independent of nucleon positions), keyed on
`(master_seed, address)` alone. This is what makes the sweep a **common-random-numbers** design:
every design point sees the same z for a given event, so differences between design points are
physical rather than sampling noise.

- β₂ folded about zero (a negative β₂ is the same shape as positive with γ shifted by π; folding
  keeps γ interpretable). β₃ stays signed — its sign is physical.
- **γ is the Bohr–Mottelson triaxiality angle γ_lit, in [0°, 60°]** — the ellipsoid angle used in
  the literature β–γ sector plots, not the harmonic angle the surface expansion takes. Per
  `BetaGammaDistribution.md`. Conversion (exact, round-trips to 1.4e-14°):
  `tan(g) = −√2 tan(γ_lit)`, then `beta20 = beta cos g`, `beta22 = beta sin g / √2`.
  Anchors: `γ_lit 0°` → pure Y₂₀ (axial prolate); `30°` → `T_yy = 0` (max triaxiality);
  `60°` → eigenvalues `(−2,1,1)` (axial oblate).
  The equivalences `γ_lit ≡ γ_lit + 120 ≡ −γ_lit ≡ 120 − γ_lit` are genuine — shape-preserving on
  4000 random draws — so the protocol's folding removes up to a 4-fold redundancy in the design
  space. The *same* folding on the harmonic angle fails on all 52 test points, which is why the
  conversion has to happen on the design side of the boundary.
  Draws are reflected rather than clipped, so overshoot lands back inside with **no boundary
  pile-up** (edge bins 261/252/245 vs 385/392/409 mid-range).
- **The prior is the bounded Beta of `BetaGammaDistribution.md` §3 Option B**, with §2/§4 also
  implemented. Beta is drawn on `[0, beta_max]` and γ_lit on the `[0°, 120°]` double domain, then
  folded by §4. Shape parameters are moment-matched from the same `(mu, sigma)` a design point
  already specifies, so no new CSV columns are required (`beta_max` is optional, default 0.5).
  **§3 is CRN-compatible**: draw a Philox uniform, push it through the Beta inverse CDF. The same
  `u` for every design point at a given event ⇒ common random numbers preserved.
  Consequences, measured: β is strictly bounded with no cusp at the origin (the old Gaussian draw
  put 2.7× uniform mass below β = 0.01 at µ/σ = 1.67); and the **uniform wedge prior is reachable
  and actually uniform** — `Beta(1,1)` has mean ½ and sd `1/√12`, so µ = `(lo+hi)/2` with
  `σ = (hi−lo)/√12`; joint density flat to 3%, **total variation from uniform 0.0076** (was 0.49).
- **Two shape-distribution modes (D8).** `shape_distribution: wedge | plane`.
  - `wedge` (default, Option B): each event's shape is a point (β, γ_lit) inside the
    Bohr–Mottelson domain. **Cannot express a nucleus with no mean deformation but real
    shape fluctuations** — the apex is where all six symmetry sectors meet, so reproducing it
    needs μ_β ≈ 0.01 *and* σ_β ≈ 0.03 *and* σ_γ ≈ 17° at once, and the feasibility guard
    rejects part of that region.
  - `plane`: mean tensor given in wedge coordinates, Gaussian drawn in the deformation plane
    about it, **folded per draw**. σ_plane = 0 is exactly rigid at any mean *including
    β = 0*. Zero mean deformation with real fluctuations is one parameter: measured prolate
    fraction **0.500** at σ_plane = 0.02/0.05/0.10/0.20, E[γ_lit] = 35.3° throughout.
    Prolate/oblate mix automatically.
  - At σ_plane = 0 the two modes are **bit-identical**, verified end to end; the wedge form is
    untouched, so existing parameter dictionaries keep their meaning.
  - **Trade-off, stated plainly:** the wedge form parameterises the *shape*; the plane form
    parameterises the *mean tensor*. E[γ_lit] still drifts with σ_plane (fold non-linearity),
    but now that is a **model prediction**, not prior distortion. A flat prior on the mean stays
    flat on the mean.
  - CRN carries over for free — the plane draw reuses two of the three existing normal latents.
  - `plane_anisotropy` is available but **off by default**; the emulator must show it can
    resolve it first.
- **Open (D7): §5 Jacobian `β⁴|sin 3γ_lit|` is deliberately not implemented.** It encodes a physics
  claim — a flat PES, i.e. a γ-unstable nucleus — not a default. Consequence to be aware of: under
  the old Gaussian latents *any* `sigma_gamma > 0` gave an essentially uniform γ_lit (peak/mean
  1.01–1.02, from σ_γ = 5° all the way to 150°), because folding equidistributes a smooth density
  onto [0°, 60°]. The parameter could not distinguish γ-soft from γ-unstable at all. Option B makes
  the choice explicit: σ_γ = uniform value for a soft vibrator, or apply the §5 weight when a
  γ-unstable prior is wanted.
- **Backward compatibility.** Every shipped design point uses `γ = 0`, the one value the two
  conventions agree on. Output is bit-identical: the previous commit's sampler and this one agree
  to `maxdiff = 0.0` across eight combinations of `beta2`/`beta3`/correlation, including the
  `beta2 = 0` axial case. (The comparison must zero `sigma_*`; with `sigma_gamma > 0` the two
  conventions deliberately give different shapes.)

- **Open (D7): γ prior width.** The support is now correct; the *width* is a physics choice.
  `sigma_gamma` is still set to 0.8 rad ≈ 46°, which over a 60°-wide domain folds a lot of mass
  back onto itself. Physically, ground states sit at small γ_lit (≲ 30°); a mean of ~25–30° with
  `sigma_gamma ≈ 10–15°` would be a better prior. Decide in Phase E.

Realised `(beta2, gamma, beta3)` is written to the output HDF5 as a `deformation` dataset plus
`master_seed`/width attributes, so results stay joinable to the shape that produced them — Phase F
builds on this.

`MakeDictionaries` reads the three widths from optional CSV columns.

Verified: σ=0 reproduces the fixed shape bit-for-bit; the same design point is bit-identical;
`beta2 = |mu + sigma*z|` holds exactly across design points with the shared latent; γ stays in
[0,2π) even at `sigma_gamma = 4`; z-scores are mean≈0, std≈1 over 4000 addresses; multi-config
batches draw one shape per configuration. End to end through generated event folders, events 0/1/2
(addresses 0, 1013904226, 2027808452) realise distinct shapes.

Also fixed here: `MakeDictionaries` referenced a module-level `DEFAULTS` constant introduced in
Phase B that never existed. It had gone unnoticed because `MakeDictionaries` had not been run end
to end since — it now reads its defaults from the template it was invoked against.

### Phase E — Validation & benchmarking *(blocking; must precede the production design)*

Everything below Phase E is worthless if results are not reproducible, and the batch size
determines how the whole campaign is submitted. Run this before committing to a design.

#### E1 — Timing benchmark  *(measured 2026-10-13, 76Ge+76Ge, decay path)*

Setup: full events run inside the container with `OMP_NUM_THREADS=1`, mirroring the OSG
job. Architecture is **one core per job, events sequential**, so per-event time is irreducible
at 1 core.

| stage | time |
|---|---|
| isobar sampler x2 + TRENTo | 5 s |
| MUSIC hydro | **119 s** |
| decay afterburner (iSS) | 32 s |
| spvn analysis | 9 s |
| **T_e (per event)** | **165-177 s** |

Measured singles: 165, 166, 165, 169 s. A 3-event sequential batch: 169+176+177 = **522 s =>
174 s/event**, confirming linearity and negligible per-event overhead. Generating 3 event
folders: 11 s (3.7 s/event, part of T_e).

```
batch N = floor((3600 - T_o) / 174)
```
With T_o measured only for image transfer (not reproducible locally, depends on OSG node
cache state):
- T_o = 0 (warm): N = 20
- T_o = 300 s: N = 19, overhead 7.9%  (above the 5% target)
- T_o = 150 s: N = 20, overhead 4.1%  (meets target)

**So ~19-20 events per 1-core job**, and the exact number depends on the image transfer, which
is why Phase F (slimming) can directly raise events-per-job. MUSIC at 119 s (68% of the event)
is the hard floor: on 1 core it does not parallelise further.

*Exit:* T_e = 174 s measured; batch N ~ 19-20 pending the OSG T_o measurement.

**Also measured through the real submission path** (fresh sif built from the pinned commit,
`singularity exec` on `run_singularity.sh`'s two calls):
- `singularity exec` startup + `generate_jobs.py`: **1 s**. Container startup is negligible.
- `singularity exec` + the event(s): dominated by physics, as above.

So `T_o` is essentially all image *transfer*, which is an OSG/GridFTP concern, not a container
startup concern. Locally the 766 MB `.sif` transfer to the HTCondor worker intermittently failed
with "Could not initiate file transfer" (evicted) -- a scratch/transfer flake on this shared
filesystem, not representative of OSG. The image transfer remains the one input to the batch
size that has not been measured on the target infrastructure.

*Local condor note:* the HTCondor generator's `run_singularity.sh` hardcodes `-c OSG` inside the
sandbox `generate_jobs.py` call, and the `-c osg` path adds `seed += job_id`. This did not affect
reproducibility of the two event-id-derived seeds (iSS, FD-analysis), which are pinned to the
global event id and unaffected by the job-id seed offset. Worth revisiting for the OSG pilot.


#### E2 — Reproducibility *(blocking; local PASSED 2026-10-13, OSG pending)*

Both tiers now pass locally for 76Ge+76Ge: **all 179 observables bit-identical** between two
full independent runs under NaN-aware exact comparison. Two blocking defects were found and
fixed to get there:

**Defect 1 -- TRENTo rejected the nucleus file.** TRENTo's `ManualNucleus::create` requires
exactly one object (`if (file.getNumObjs() != 1) throw`, nucleus.cxx:412). The Phase-D
provenance written as sibling datasets made it three objects, so every event died at TRENTo.
Invisible until a full run. Fixed by writing `deformation` / `deformation_harmonic` as HDF5
**attributes** (attributes are not objects).

**Defect 2 -- two clock-based seeds.** Two identical runs gave 19526 vs 19685 accepted
particles and 157/179 differing datasets. Two independent seeds default to -1 ("use system
clock"):
- `iSS_parameters.dat randomSeed` (afterburner). Parsed via `cut -f 3 -d " "`, so the value must
  be the third space-separated field and the line must carry no leading space.
- `hadronic_afterburner_toolkit/parameters.dat randomSeed` (the FD/MC analysis binary). After
  pinning only the first, v2 and counts matched but **69 of the 72** still-differing datasets
  were `_weakFD`.

Both now pinned to a Weyl offset of the **global event id** (bases 7919 and 104729 so they are
uncorrelated), not a clock and not the job-id seed that `-c osg` adds. Neighbouring events stay
decorrelated while each is reproducible.

Residual byte differences in the output HDF5 are NaN payload encodings in three padding cells
(numerically identical), plus `run.log` timestamps and `.pyc` caches -- expected to vary.

```
Tier 1 (nucleus HDF5): byte-identical, local  PASS
Tier 2 (observables):  all 179 bit-identical, local  PASS
```

**Cross-platform: OSG worker vs local (Phase E3, 2026-10-13).** Same event id 0, same
parameter file, run locally in docker and on an OSG worker (wsu-lg07.osris.org, glidein
MI-HORUS-CE2, `Cpus = 1`), image pulled via `osdf:///ospool/ap40/data/matthew.luzum/
singularity_repos/iebe-music_slim.sif`.

```
Tier 1  target_nucleus.h5  md5 6f2a22d4bafdb6b5724dc79a26586fa5  both sides
        BYTE-IDENTICAL, including every provenance attribute
        (master_seed, seed_source, deformation, deformation_harmonic)

Tier 2  28 of 114 datasets exactly equal; the rest agree to FLOATING POINT
        v2 elementwise |diff| <= 1.9e-9, max relative diff 4.3e-2 on a
        near-empty dNdeta cell
        event counts (pT bin, N_particles) EXACTLY equal: [99, 429, 100]
```

So the common-random-numbers design survives the platform change exactly where it has to:
**the nuclei are bit-identical**, which is what the CRN argument rests on. The observables
are reproducible to floating-point, not bitwise, because MUSIC's hydro solver reduces in a
hardware- and compiler-dependent order. For calibration that is far below any statistical
uncertainty (~1e-2 on v2 with a few thousand events), but it does mean **bit-identity of
observables must not be asserted across platforms** -- only within one machine.

Reference scale for how large a *real* difference looks: two different events locally differ
in v2 by 4.5e-3, i.e. ~7 orders of magnitude more than the local-vs-OSG same-event
difference. The nuclei cannot be differing; the residue is hydro arithmetic.

Known suspects to test rather than assume:

- **Thread count changes floating-point reduction order.** OpenMP/MPI in MUSIC can reorder
  summations, so `v2` can differ in the last bits between a 4-thread and an 8-thread run *with
  identical input*. Pin `OMP_NUM_THREADS` / `MKL_NUM_THREADS` in the job script and record the
  value in the output directory so a mismatch is diagnosable rather than mysterious.
- **TRENTo's own RNG.** Confirm it is seeded from the nucleon configuration. If it draws from its
  own seed, that seed must derive from the event id.
- **joblib parallelism** in the sampler is deterministic (verified in Phase A), but pin `n_jobs`
  anyway.
- **Result merging order.** Each event owns a global id, so merging must key on id, never on
  completion order (already the case per Phase C).
- **Archive ordering.** `tar` output must not depend on directory iteration order.

Acceptance: same event + same seed on local HTCondor, run twice → Tier 1 byte-identical. Same
event on OSG → Tier 1 byte-identical to local. Tier 2 agreement recorded to a stated relative
tolerance with threads pinned. **If Tier 1 fails anywhere, stop and fix it before any production
run** — there is no point spending OSG hours on unreproducible results.

#### E3 — Cross-platform pilot
One design point, ~20 events, submitted through the *real OSG path* (not the HTCondor one) and
collected with `collect_events.sh`. Verify against local. This also exercises the image pull on
OSG, which feeds Phase F.

*Exit:* local-vs-local and local-vs-OSG both reproduce Tier 1 byte-identically, Tier 2 to the
recorded tolerance, and `T_e`/`T_o`/`N` are measured.

### Phase F — Container slimming *(DONE 2026-10-13)*

The campaign is TRENTo+decay, so every other backend is dead weight that gets pulled per job
over OSDF. `docker/Dockerfile` now takes a build ARG:

```
docker build --build-arg WITH_OPTIONAL_CODES=0 -t iebe-music:slim .   # TRENTo+decay
docker build --build-arg WITH_OPTIONAL_CODES=1 -t iebe-music:full .   # + SMASH/UrQMD
```

`WITH_OPTIONAL_CODES=0` drops SMASH, UrQMD, osc2u, IPGlasma, KoMPoST, photon emission and
3dMCGlauber, plus `/opt/pythia8315` (only SMASH links it) -- ~555 MB. The always-kept list is
asserted present in **both** modes and the dropped paths asserted **absent** in mode 0, so a
future change cannot silently break the decay path.

| | docker image | SIF (what OSG pulls) |
|---|---|---|
| full (`WITH_OPTIONAL_CODES=1`) | 2.76 GB | 731 MB |
| slim (`WITH_OPTIONAL_CODES=0`) | 2.76 GB* | **527 MB** |
| previous (pythia + SMASH only) | 2.76 GB | 766 MB |

\* docker reports the same size because layers are append-only and `rm` only writes whiteouts;
the SIF is the number that matters for transfer, and it drops 28% vs the previous image and 28%
vs full.

Slim0 was verified to run a full 76Ge event end to end (210 s) before being shipped.

**Byte-identity is a within-build invariant, not a cross-build one.** Rebuilding the image
from a newer pin moved every target nucleon by 1-2 float32 ULP (max 2.4e-7 fm at r ~ 7 fm,
i.e. ~3e-8 relative). Cause: the Woods-Saxon -> step+Gaussian fit is a BFGS `minimize`, whose
last bits depend on the numpy/BLAS build; float32 storage rounds the resulting 1e-15
float64 difference up to 1-2 ULP. Nuclei are still "the same nuclei" for any physics purpose
(0.5 fm radius, 1 fm nucleon width), but **md5 of the nucleus HDF5 is only an audit tool
within one image build**. Compare nuclei across builds with a tolerance (~1e-6 fm), not md5.
Local-vs-OSG md5 equality earlier was same-image, and still stands as evidence.

**Deployment.** The SIF lives on the OSG spool at
`/ospool/ap40/data/matthew.luzum/singularity_repos/iebe-music_slim.sif` and is referenced as

```
+SingularityImage = "osdf:///ospool/ap40/data/matthew.luzum/singularity_repos/iebe-music_slim.sif"
```

**Image ledger.** Production images are named `iebe-music_slim_<short-sha>.sif` so the artifact
is self-identifying. `iebe-music_slim.sif` is kept as a stable alias for the newest one.

| SIF | framework commit | md5 | notes |
|---|---|---|---|
| `iebe-music_slim_2f840cc.sif` | `2f840cc` | `97bf05f9f39e411063dc2b887132c1d6` | **current production**, `WITH_OPTIONAL_CODES=0` |
| `iebe-music_slim_e340bbb.sif` | `e340bbb` | `5bc987954e7a2c546cb72838a643e439` | **current production**, instrumented driver |
| `iebe-music_slim_4d5e6f0.sif` | pre-2f840cc pin | `84eeb5b806f5da4b8d800b4bd48e6288` | superseded, do not use |

**There is deliberately no `iebe-music_slim.sif` alias.** One existed, was refreshed in place when
the instrumented image was deployed, and OSG's OSDF cache kept serving the previous bytes. Two
batches ran against the stale image; the giveaway was only that *some* workers held with a
checksum mismatch while others agreed with the cache and proceeded. Mutating a published path can
silently substitute a different image, so every submission references a commit-named file.

The commit is checked inside the image, not just recorded:
`docker run ... git -C /opt/iEBE-MUSIC rev-parse HEAD` must print the SHA in the filename.

Condor log/error/output files point at `/home/matthew.luzum/log/` (home disk), as required --
the generator takes the log directory from its own working directory, so run it from a home-disk
directory.

### Adaptive transverse grid (FEASIBILITY -- explored, not adopted)

Idea: keep the cell size fixed and size the transverse box to the event, so peripheral
collisions stop paying for empty cells. Investigation results, all checked against the code
rather than assumed:

**1. The grid is already fully described by a handful of keys.** MUSIC takes
`X_grid_size_in_fm`, `Y_grid_size_in_fm`, `Grid_size_in_x`, `Grid_size_in_y`; the driver takes
`grid_max`/`grid_step` and *derives* `n_grid = 2*grid_max/grid_step` with a hard assertion.
Both candidate schemes are therefore expressible without new physics code:

| | fixed | per-event | consequence |
|---|---|---|---|
| **A** | `dx` = 0.2 fm | number of cells | uniform resolution; runtime varies with b |
| **B** | number of cells | `dx` | constant runtime; resolution varies with b |

**2. `b` is available in exactly the right order.** TRENTo runs first, and the driver
*already* parses `impact_parameter` out of `run.log` (that is where the OSG summary value comes
from). So the box can be chosen after TRENTo and before MUSIC, with no need to take over b
sampling -- important, because TRENTo's b distribution comes from its own Glauber weight
function and reimplementing that would be a correctness risk.

**3. Cropping needs no change to `freestream.py`.** `FreeStreamer(initial, grid_max, time)`
derives its domain as `xymax = grid_max*(1 - 1/nsteps)` from the matrix size *and* the passed
`grid_max`. Crop the matrix to +/-L and pass `grid_max=L`, and it is consistent by construction.

**4. Per-event MUSIC input already exists.** Each `event_N/` carries its own copy of
`music_input_mode_2`, so the driver can rewrite the four grid keys in its own directory. No new
plumbing.

**5. The current setup is already oversized and self-inconsistent.** MUSIC's domain is
+/-20 fm (`Grid_size_in_x=200` at `dx=0.2`) while the IC table only spans +/-15 fm. For a
peripheral event (b = 0.274 fm) measured on the real output:

```
R(90%) = 5.57 fm    R(95%) = 6.22 fm    R(99%) = 7.65 fm    R(99.9%) = 9.12 fm
79.5% of IC cells hold less than 1% of the mean energy density
3028 of 22500 cells (13%) lie inside R95
```

So there is a real, already-banked win even without adaptivity: making MUSIC's domain match the
IC table instead of overhanging it by 5 fm.

#### Validation of the adaptive box at scale (49 paired events, adaptive vs fixed)

Three batches rerun with `adaptive_grid: true` and compared event-for-event against the
identical fixed-box runs:

| batch | b range | cells chosen (of 150) | MUSIC median | speedup |
|---|---|---|---|---|
| `b_max=4` (central) | 1.5-3.8 fm | 94-112 | 218 -> 104 s | 2.11x |
| `b_max=8` | 2.9-7.6 fm | 78-112 | 120 -> 72 s | 1.67x |
| `b_max=14` (peripheral) | 5.1-13.3 fm | 56-108 | 56 -> 9 s | 6.23x |

**Does it change the physics?** On v2, over the full (pT, vn) array:

```
max |dv2|        median 1.8e-3,  max 3.3e-2   against typical |v2| of ~3.3
|dv2| / |v2|     median 5.1e-4,  max 1.1e-2
49 events: 17 above 1e-3 relative, 1 above 1e-2
```

So the adaptive box perturbs v2 by ~5e-4 relative per event. That is well below the per-event
statistical error (order 10% at these multiplicities) and, unlike a systematic shift, it varies
with b and with the chosen box, so it averages down further across an ensemble. It does
nevertheless put a **numerical noise floor of ~5e-4 relative on v2** into the emulator, which
matters only if the emulator is asked to predict design-point differences below that.

This is looser than the single-event spot check, which showed 111 of 114 observables
bit-identical. The spot check was one event at 108 cells; across 49 events the box choice
varies from 56 to 112 cells and the surface is not always an exact sub-block of the original,
so a few particles move between discrete analysis bins. Expected, but worth recording rather
than quoting the best case.

**Realistic end-to-end gain.** MUSIC is only part of an event; ~46 s is sampler, TRENTo,
afterburner and analysis and does not shrink:

```
central     150 s ->  96 s   (24 -> 38 events per OSG hour)
mid         118 s ->  72 s   (30 -> 50)
peripheral   55 s ->  48 s   (66 -> 75)
```

So ~1.5-1.8x end to end, not the 2.2x the cell count alone suggests. The fixed ~46 s floor is
what caps it, and it caps peripheral events hardest.

#### Checks: resolution, extrapolation, oversampling

**Resolution ladder** (dx = 0.15 / 0.20 / 0.25 at a fixed +-15 fm box, so cost is identical and
only resolution changes; 16 and 14 paired events against the dx = 0.20 baseline):

```
dx = 0.15 vs 0.20:  median |dv2|/|v2| = 9.5e-4,  max 3.5e-3
dx = 0.25 vs 0.20:  median |dv2|/|v2| = 1.8e-3,  max 8.3e-3
```

The pair implies convergence of order ~1.2 in dx, so the discretisation error at the production
dx = 0.20 is **~1.3e-3 relative in v2**. Two consequences:

- It is *systematic* -- it does not average down over an ensemble, unlike statistical error. It
  is the floor on what design-point difference the emulator can resolve.
- It is about **2.5x larger than the adaptive-box noise floor (~5e-4)**. The adaptive grid is
  therefore cheaper, in accuracy terms, than the discretisation error we are already accepting.
  Resolution, not the box, is the limiting numerical factor.

**Min and max dx.** With the adaptive box as implemented, dx is *fixed* at 0.20 fm and only the
cell count varies (56-112). So min dx = max dx = 0.20 fm. The "fixed cells, scaled box"
alternative would instead give dx from 0.09 (peripheral, L = 5.1 fm at 112 cells) to 0.20
(central) -- but it is strictly more expensive for the same accuracy, because discretisation error
depends on dx and not on the cell count, so peripheral events would pay ~4x the cells to reach an
error the fixed-dx scheme gets for free. Not recommended. If finer resolution is wanted, the lever
is dx itself: dx = 0.15 costs ~1.8x the MUSIC time for a 1.35x error reduction.

**Extrapolation.** WS_radius 7.2 -> 8.1 pushes R_rms_trento to 4.91 fm, just past the 4.60 fm the
rule was fitted to; reduced-thickness 0.15 stays inside at 4.38 fm. The rule still covers the
extrapolated events with margin (needs 8.96 fm, rule asks 11.79 fm, zero under-covers), so mild
extrapolation of this kind is safe. Larger excursions should still be re-measured.

**Oversampling.** The default 10-sample configuration carries a large FD statistical error:
after normalising the per-species arrays by their own particle count, pi+ v_n differs from an
oversampled run by a median **34% relative** (max 99%) per event. The `momentum_anisotropy_eta`
array is *not* sensitive to this -- it is deterministic given the hydro and agrees to 3e-8 between
the two runs -- so it must not be used to judge flow statistics. Scaling as 1/sqrt(N), a target of
10^4 particles gives ~7% per event, 10^5 gives ~2%, 10^6 gives ~0.7%; averaged over 1000 events
per design point, 10^4 particles already gives ~0.2%, comparable to the discretisation floor.

#### The flow output format, read from the source (not inferred)

The toolkit source is public (`github.com/chunshen1987/hadronic_afterburner_toolkit`) and was
cloned to check what is actually written, rather than guessing from array shapes.

**The sample count was there all along.** `single_particleSpectra.cpp` ends every
`particle_<pid>_vndata_*.dat` with

```
// output total number of particles in the last row
// this quantities is useful when one wants to reconst the Qn vectors
99   total_N   total_number_of_events   0.0   0.0
```

so the third column is the number of iSS resamplings, exactly. Verified independently by
decoding `particle_list.bin` (`[int n_particle][n x (int pdg + 9 floats)]`): **5740 records**,
893,926 particles, 155.7 per resampling -- the same number the totals row reports. The earlier
"the count is not recoverable" conclusion was wrong; the column had simply been mislabelled.
Recorded per event now as `n_pions`, `n_iss_resamplings`, `pions_per_resampling`.

**V_n are stored as vectors, not magnitudes**, real and imaginary parts separately, and n=0 is
present as the yield. Header and layout of `particle_<pid>_vndata_diff_<rap>.dat`:

```
# pT  EdN/d^3p  Qn_real(pT)  Qn_imag(pT) (n=1-5)
col 0      pT bin centre
col 1      EdN/dp3p            <- n = 0, the yield
col 2,3    Qn_real, Qn_imag     n = 1
col 4,5    Qn_real, Qn_imag     n = 2
...
col 12     total_NpT            particles in this pT bin
```

This is exactly the object that was asked for: per identified species, n = 0 plus v_1..v_5 as
vector components, in fine pT bins, with the raw multiplicity per bin for normalisation and for
self-correlation subtraction. No fork is needed for this. Two notes: the columns are interleaved
(real, imag) per harmonic, not blocked by harmonic; and `EdN/dp3p` is the *invariant* yield, so
converting to dN/dy needs the pT weight and the pseudorapidity Jacobian.

**Identified-particle harmonics are hard-capped at n=5** by one line:

```cpp
if (particle_monval != 9999) order_max = 6;      // single_particleSpectra.cpp:52
```

All-charged output gets order_max = 10; anything else is forced to 6. Raising it for identified
species is a one-line change, and since the source is available that is a small fork rather than
an obstacle.

#### Grid convergence, measured on the final particle observables

The earlier resolution ladder was measured on `momentum_anisotropy_eta`, which is deterministic
given the hydro and therefore blind to freeze-out sampling. Redone on the identified-particle and
all-charged pT-integrated v_n from the flow output, with the adaptive box on and oversampled iSS,
against dx = 0.10 fm as reference (8 common events):

```
all charged  <v2> at dx = 0.10 : 0.00544 +- 0.00167  (ensemble SEM)
              dx = 0.25 vs 0.10 : -4.7%
              dx = 0.20 vs 0.10 : +1.3%
pion+        <v2> at dx = 0.10 : 0.01280 +- 0.00315
              dx = 0.25 vs 0.10 : +28%      <- within the statistical error
              dx = 0.20 vs 0.10 : +27%      <- within the statistical error
```

For all-charged v2 the scaling is clean and monotone in dx, so dx = 0.20 carries about a **1.3%**
discretisation error relative to dx = 0.10. For identified particles the differences sit inside
the statistical error, because per-event v_n on ~2e4 pions still fluctuates by ~5e-3 -- comparable
to the signal. So **per-event identified v_n cannot resolve dx differences at all**; the test only
works on ensemble means.

This reorders the error budget completely. With a few hundred events per design point the
statistical error on v2 falls to the percent level, at which point the dx = 0.20 discretisation
error becomes the limiting term. Reaching for dx ~ 0.15 to keep the discretisation error under
1% costs ~1.8x the MUSIC time; dx = 0.10 costs ~4x. dx = 0.15 and dx = 0.30 runs are still in
flight to complete the ladder and allow a Richardson extrapolation.

**On fixed cells.** The adaptive sizing rule already makes `dx` exactly the requested grid step
for every event (`n_cells = 2*ceil(L/dx)`), while the *box* shrinks, so resolution is uniform in
absolute terms. A fixed cell budget would instead give small systems finer resolution
(dx from ~0.09 to 0.20 fm) at a constant cell cost. Both are defensible; the trade is uniformity
in dx versus uniformity in cost. That is now testable with the same machinery, but it is a cost
decision rather than an accuracy one, since discretisation error depends on dx alone.

#### Statistical error depends strongly on the pT bin, so "how many particles" is the wrong question

Measured on the oversampled runs (dx = 0.10, ~2.2e4 pi+ per event), pion+:

```
pT range      particles/bin/event   Poisson sigma on v2
0.05-0.3                 2190            0.021
0.3-0.6                  1337            0.027
0.6-1.0                   282            0.060
1.0-1.5                     21            0.220
1.5-2.0                      1            ~1.0
2.0-3.0                      0            undefined
integrated 0.05-4.05      22205            0.0067
```

A single bin at 1.0-1.5 GeV is ~30x worse than the integrated value, and above ~1.5 GeV there
are on average *one or zero* pi+ per bin per event. So per-event identified v_n at high pT is
not reachable by any affordable oversampling: to get sigma ~0.01 in the 1.0-1.5 bin one would
need ~1e4 particles *in that bin*, i.e. ~1e7 pi+ per event.

**The oversampling target must therefore be set by the highest pT bin of interest, and high-pT
identified flow has to come from the ensemble, not from individual events.** With ~1000 events
per design point, the 1.0-1.5 bin accumulates ~2e4 particles and reaches sigma ~0.007; with
~1000 events and no oversampling (~410 pi+ per event) that bin would have ~210 particles and
sigma ~0.07. That, rather than the total particle count, is the argument for oversampling.

#### Grid convergence, final ladder

Measured on the **deterministic** hydrodynamic momentum anisotropy (per-event deviation from
dx = 0.10, median over common events). This is the right instrument for grid convergence: it has
no freeze-out sampling noise, so a 0.03% effect is measurable with 7-8 events, whereas the same
comparison on particle v_n needs ~10^3 events per point because the ensemble error is ~30%.

```
dx      CENTRAL b_max=4 (large L)     PERIPHERAL b_max=14 (small L)
0.30             n/a                     +0.066%
0.25           -0.146%                    -0.173%
0.20           -0.029%                    -0.074%
0.15           -0.031%                    -0.027%
```

**Correction.** The earlier claim that dx = 0.20 carries ~1.3% discretisation error came from a
script with two bugs (it matched `vndata_diff_` when it wanted the integrated file, and it
divided by a degenerate normaliser). The correct figure is **0.03-0.07%**, two orders of magnitude
smaller. dx = 0.20 is comfortably converged and there is no case for spending 4x the compute on
dx = 0.10.

**On absolute dx vs dx/L.** At every dx the two system sizes agree to within ~30% of each other,
and the batch means differ in size by only ~1.4x, so this is weak leverage. Within the
peripheral batch, where R_rms_trento spans 1.66-4.35 fm (2.6x), the correlation between system
size and deviation is -0.12 -- no trend. **There is no evidence that small systems need a finer
dx**, and no evidence that a fixed cell budget would buy accuracy. The measured cost of a fixed
cell budget is real (it multiplies cells for the small systems) while the benefit is not seen.

Caveat: the dx = 0.15 and 0.30 points come from the post-fix image and the dx = 0.20/0.25 points
from the pre-fix one. The fix only changes behaviour where TRENTo's grid arithmetic disagrees by
one cell, which is exactly dx = 0.15 and 0.30, so the other points are unaffected -- but a single
image for the whole ladder would be cleaner.

dx = 0.30 is non-monotonic (0.066% against 0.173% at 0.25), which suggests a numerical noise floor
of order 0.03-0.07% rather than a clean convergence curve. A Richardson extrapolation is therefore
not meaningful here.

#### Grid convergence: what the percent error actually is, and a bug in it

**Definition.** For each event, paired by event id (same seed, same b), take the MUSIC
lattice diagnostic `momentum_anisotropy_eta_-0.5_0.5.dat` -- shape `(n_tau, 19)`:

```
per_event_percent(w, dx) = 100 * (mean|v|_dx - mean|v|_0.10) / mean|v|_0.10
    |v|_dx = mean over columns 1..18 and all rows with tau <= min(tau_end_dx, tau_end_0.10)
```

then report the median and the max over events. The reference is dx = 0.10 **at the same w**,
so w is never confounded with dx. Reported as a max because the discretisation error is a
systematic per-event effect, not a fluctuation that averages away.

**Bug, and it was mine.** The statistic was originally written as `np.abs(arr).mean()` over the
whole array. **Column 0 is proper time `tau`, not anisotropy.** Its magnitude is ~1.2-1.7
against ~0.03-0.06 for the anisotropy columns, so tau supplied **96-98% of the quantity being
differenced** -- the statistic was mostly "mean proper time of the run". It happened to be
harmless at w = 0.50 and 0.75, where `tau_end` is bit-identical between dx values for all 8
events, and it wrecked w = 0.25, where `tau_end` *does* move with dx. The w = 0.25 row of the
table reported earlier was therefore contaminated and is replaced below.

**Corrected** (column 0 excluded, per-pair common time window, max over 7-8 events):

| w | dx=0.15 | dx=0.20 | dx=0.25 | dx=0.30 |
|---|---|---|---|---|
| 0.25 | 4.83% | **9.38%** | 6.74% | n/a |
| 0.50 | 0.48% | **0.48%** | 1.11% | 1.13% |
| 0.75 | n/a | **0.44%** | n/a | 0.80% |

**The conclusion survives and strengthens.** At dx = 0.20 the error is ~0.45-0.48% for
w = 0.50 and 0.75 but 9.4% at w = 0.25 -- a factor ~20. dx = 0.20 is comfortably converged for
w >= 0.5 and nowhere near it for w = 0.25, so **production dx must be a function of w**. The
large-w half of that is still unsupported: w = 0.75 at dx = 0.20 is indistinguishable from
w = 0.50, and only at dx = 0.30 is large w mildly better (0.80% vs 1.13%, about 1 IQR).

**Known weaknesses of this statistic, none of them fixed:**
* `tau_end` is an emergent, event-dependent quantity (event 5 at w = 0.25 ends at tau = 0.60,
  event 2 at 2.15). It varies by ~3x across events, so each event is only ever compared to
  itself over its own common window. A single row-wide window is *wrong* -- it truncates every
  event to the shortest one.
* Columns 7-18 supply 93% of the magnitude and their meaning is **unknown**; the MUSIC source
  is not in the tree. So the statistic averages 12 columns that are not identified.
* Uniform time weighting includes the early phase, which is dominated by initial-state geometry
  rather than the flow physics being tested.
* Using a signed mean instead of `mean|v|` explodes the answer (factor 368 instead of 20) because
  columns 1-6 average through zero. **A relative error is the wrong normalisation for a
  sign-changing quantity**; the absolute-value convention is a stabiliser, not a physics choice.
* It is a lattice proxy. The plan requires convergence tests on the final particle observables,
  and this is not that. The reason it was used is that it is deterministic and the particle
  comparison needs ~10^3 events per point to resolve a 0.5% effect.
* The reference dx = 0.10 is itself unverified as converged, and at w = 0.25 it is the least
  trustworthy point in the campaign.

#### The convergence ladder was run on the wrong file, and on events that cannot measure v_3

**The documented format was not used.** The ladder was computed from
`momentum_anisotropy_eta_-0.5_0.5.dat`, a MUSIC hydro output. That file is **not** described in
`analysisKit/FLOW_OUTPUT_FORMAT.md` (which documents the afterburner's `spvn_results_*.h5`), its
columns were never identified, and the 19-column layout means 93% of the magnitude comes from
columns 7-18 of unknown meaning. So no: the analysis was not being run on the documented output.

**The `c4dx` "central" arm was never central.** All 47 design-point parameter files carry
`"b-max": 14.0` except one. The `c4dx*` files that were meant to be the central arm
(`b-max = 4`) only ever had their `dx` substituted -- `b-max` was left at 14.0. Verified: the
`grid_extent` CSVs for `c4dx10` and `w25dx10` list **identical** impact parameters
(5.12, 9.74, 10.47, 11.49, 12.16, 12.33, 12.41, 13.31 fm). The earlier claim that central and
peripheral systems agreed on dx was therefore comparing a set of events with itself, and the
"does system size change the required dx" question is **untested**, not answered.

**Every existing w/dx event is extremely peripheral.** `b = 5-13 fm` of `b_max = 14`, giving
multiplicities of **7-89** against a central value near 700. Consequence, measured on the
pT-integrated `v_n` vectors (unidentified species, which reach n = 9):

| n | 1 | 2 | 3 | 4 | 5 | 8 |
|---|---|---|---|---|---|---|
| per-event precision `sigma/\|v_n\|` | 138% | 130% | 177% | 141% | 174% | 242% |

**Every `v_n` is measured with an error larger than the value itself.** No numerical-error bound
below ~25-200% can be extracted, so these runs cannot answer the question regardless of how they
are analysed.

**What they do establish.** Paired by event id against dx = 0.10 at the same w, the difference in
the pT-integrated `v_n` **vector** (real and imag separately, never the magnitude) is consistent
with zero for **every harmonic n = 1..9**, at both w = 0.25 and w = 0.50:
`chi2/dof` between 0.17 and 0.74 across 38 separate species-harmonic combinations, never above
1. The observed RMS of the difference is ~0.7x the quadrature statistical error, i.e. the runs
are correlated through the common nuclei and b, so the paired difference is cheaper than an
unpaired one.

**This does not support the proxy's headline.** The MUSIC proxy reported a 9.4% error at
w = 0.25, dx = 0.20 (a factor ~20 over w = 0.50). The particle observables show no such effect
-- differences are consistent with zero at both w. The proxy result is withdrawn, and the
conclusion "dx must depend on w" is **withdrawn with it**. That question is open, not settled.

**Method fixed for the retest** (now running, `cen*` batches, clusters 16042572-16042579):
b-max = 4.0, w in {0.25, 0.50}, dx in {0.10, 0.15, 0.20, 0.25}, 32 events per point, dx = 0.10
as the reference. Benchmark is the pT-integrated `v_n` vector for the unidentified species
(n up to 9), plus pi+ and the all-charged reference. The expectation being tested -- that the
grid-spacing error grows with harmonic n -- is only testable where `v_n` is above its own
statistical floor, which requires central events.

#### The Woods-Saxon radius was that of a lead nucleus

Every parameter file in this repo used **`WS_radius = 7.2 fm` with `A = 76`.** Under the
conventional `R = 1.2*A^(1/3)` Woods-Saxon scaling, `R = 7.2` corresponds to `A = (7.2/1.2)^3 = 216`.
The nuclei were built with 76 nucleons spread over the volume of a lead nucleus:

| | R (fm) | r_rms (fm) | |
|---|---|---|---|
| as used | 7.20 | 5.88 | A ≈ 216 |
| **A = 76 correct** | **5.08** | **4.35** | `1.2*A^(1/3)`; experimental matter r_rms ≈ 4.10 |

1.35x too large in `r_rms`, 2.5x in volume. `b_max = 14.0` was self-consistent with `R = 7.2`
(the formula in `MakeDictionaries.py` gives 14.6 at `w = 0.5`), which is why nothing looked wrong.
`MakeDictionaries.py`'s own template default is 6.38 fm, i.e. `A ≈ 151` -- also too large for 76Ge.

**Direction of the bias.** A larger IC has a larger structure scale, so at fixed `dx` the old
tests resolved a true 76Ge *better* than they resolved. Every convergence number obtained at
`R = 7.2` is therefore optimistic by roughly that factor in the length scale, which is a direct
error on the production `dx`.

*Verification note:* the `r_rms` figures come from integrating the Woods-Saxon **with the `r^2`
Jacobian**, matching the sampler's own analytic normalisation
(`norm = -8*a^3*pi*polylog(3, -exp(R/a))` in `build_isobars.py:166`). An earlier check omitted
that Jacobian and was caught by a Pb-208 cross-check: the correct convention must reproduce
~5.5 fm for lead, and the Jacobian-free version gave 4.20.

**Chosen value: R = 5.08 fm**, the conventional `1.2*A^(1/3)`. The alternative would be
`R = 4.72 fm`, tuned so that the modelled `r_rms` equals the experimental 4.10 fm exactly;
R = 5.08 is preferred because the residual ~6% excess is the usual Woods-Saxon bias (the same
convention gives 5.81 vs 5.52 fm for Pb-208, i.e. +5%), so it keeps nuclei comparable across
systems rather than absorbing a per-isotope correction.

**Also invalidated by this change, and not yet fixed:**
* `config/adaptive_grid.json` was fitted at `R = 7.2` (141 events, `b = 1.46-13.31`,
  `R_rms_trento = 1.66-4.6`). The slope `c1 = 1.009` relating the TRENTo IC radius to the nuclear
  `r_rms` is a property of the nuclear size, so it **does not transfer** and the rule must be
  refitted from the new runs. Its 7σ = 1.35 fm margin should keep the box from clipping in the
  meantime, but the rule is stale until refitted.
* All existing results, including every convergence number in this section, are at `R = 7.2` and
  are not comparable with the new ones. **No result in this repository has been produced at the
  correct nuclear radius yet.**

#### BLOCKING: the production configuration destroys the flow signal and is not reproducible

The correct-radius campaign (clusters 16042590-16042597, 32 events x 8 points) completed, but
**the study cannot be run on it** because two defects in the configuration remove the very
signal being measured.

**1. The freeze-out oversampling suppresses `v_n` by about an order of magnitude.**
`sample_upto_desired_particle_number = 1` (the "production" setting added earlier) makes iSS
resample the freeze-out surface thousands of times, and `run_afterburner.sh` concatenates every
subevent's `particle_list.bin` into one particle list that the toolkit reads as `N` events. The
pooled `v_n` is diluted roughly as `1/sqrt(N_samples)` -- consistent with each resampled subevent
having its flow referenced to its own randomly-oriented frame, so the average cancels.

| | resamplings | unidentified particles/event | mean \|<v_2>\| |
|---|---|---|---|
| oversampling OFF | 100 | 345 | **0.0630** |
| oversampling ON | 3780 | 44234 | 0.0064 |

0.063 is the physically sensible value for this system; 0.0064 is ~10x too small. Note the
oversampling *does* buy ~20x better per-event precision, so it trades a correct signal for a
statistically tighter wrong one -- a net loss.

**Consequence: with the production setting the ensemble mean `v_n` is consistent with zero for
every harmonic.** w=0.50, dx=0.10, 31 central events, unidentified:

| n | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 |
|---|---|---|---|---|---|---|---|---|---|
| `<v_n>` | 0.0016 | 0.0022 | 0.0011 | 0.0020 | 0.0008 | 0.0015 | 0.0006 | 0.0005 | 0.0013 |

All-channel v_1 = 0.00055 +/- 0.00050. **Every flow number produced under this setting is wrong,
and the per-event "precision" measured earlier (130-240%) was precision on noise.**

**2. The freeze-out sampler is seeded from the system clock.** `iss_dict['randomSeed'] = -1`
means "use system clock" (`parameters_dict_master.py:592`). In `run_afterburner.sh` the guard
`if [ $RANDOMSEED != "-1" ]; then RANDOMSEED=$((RANDOMSEED + iev)); fi` deliberately leaves
`-1` in place, so every subevent of every event draws a fresh clock seed. Therefore:

* **Runs are not reproducible.** Re-running the same event gives a different `v_n`. The plan's
  standing assumption that reproducibility merely "rests on the counter-based scheme" is wrong --
  it is broken at the freeze-out stage, which is downstream of everything the seed scheme covers.
* **The freeze-out sampling is not common random numbers.** The paired dx comparison therefore
  carries full freeze-out noise; only the event-level geometry cancels, since nuclei and `b` are
  shared. Measured: the paired difference is 0.63x the quadrature statistical error
  (`chi2/dof` ~ 0.4), which is exactly partial cancellation. That is the ceiling on how finely
  the convergence can be measured, and it is set by the clock seed.

Also unseeded: `hydro_plus_UrQMD_driver.py:183` draws
`ran = np.random.default_rng().integers(1e8)` from OS entropy on every call and feeds it to the
3dMCGlauber rapidity shift. Harmless for a 2D boost-invariant run where rapidity is bookkeeping,
but it is the same class of defect and should be pinned.

**What *is* verified sound**, and should not be redone:
* R = 5.08 fm, A = 76, b and multiplicity bit-identical across every dx point (CRN intact).
* 32 events per point, the full dx ladder at w in {0.25, 0.50}, both w rows complete.
* Cost scaling, MUSIC seconds/event: dx = 0.25 / 0.20 / 0.15 / 0.10 -> 31 / 69 / 157 / 286 s at
  w = 0.25. A clean ~4x from dx = 0.25 to dx = 0.10, which is the real argument for the
  production `dx` and does not depend on the broken sampling.
* The output plumbing: the pT-integrated `v_n` vectors (real and imag separately, n up to 9 for
  the unidentified species) are extracted and paired correctly.

**Required before the study can be run:** turn the oversampling off (`sample_upto_desired_particle_number = 0`),
and pin `iss_dict['randomSeed']` to a value derived from the event id so the freeze-out sampling is
reproducible and becomes common random numbers across the dx ladder. Both are one-line changes;
neither has been made, because they change every flow number in the repository and that is a
decision to take deliberately.

#### The analysis statistic was wrong: v_n must not be averaged over events

**The ensemble-mean `v_n` vector is not a meaningful quantity here, and reporting it was an
error.** Averaging the flow vector across events with different eccentricities, orientations and
magnitudes causes cancellation, and odd harmonics such as `v_3` in particular average almost to
zero. Two consequences, both of which invalidate things I reported earlier:

* The claim that "the flow is ~40x smaller than expected" was computed from `<v_n>` over events.
  That number is meaningless for odd `n` and was withdrawn.
* The "oversampling eats the flow" conclusion was **wrong**, and it came from the same bad
  statistic. The magnitude of a 2-component mean is biased upward by noise: pure noise over `E`
  events gives `E[|mean|] = 1.2533*sigma/sqrt(E)`. At 8 events with oversampling off, that is
  0.0451 against an observed 0.0630 -- a factor 1.4, i.e. **the "physically sensible" value was
  noise**. My own script printed `consistent with ZERO` on that row and I overrode it in the
  writeup. Oversampling adds no bias, only reduces the variance, exactly as expected: the
  largest number of samples gives the most accurate result. Oversampling stays **on**.

**The correct statistic** is event-by-event convergence of the *single-event* `v_n`:

```
for each event e, for each dx:
    dv_n(e, dx) = v_n(e, dx) - v_n(e, dx_ref)        complex difference, same event
    weight by the single-event statistical error the file already provides
    -> chi2/dof = sum(|dv|^2 / sigma_dv^2) / (2 * N_events)
```

Real and imaginary parts are carried separately throughout; magnitudes are never taken before the
difference. `dx_ref = 0.10` at the same `w`. With the fixed seed (below) the freeze-out sampling
becomes common random numbers across `dx`, so the shared nuclear geometry cancels exactly and the
residual is the numerical difference plus the surviving sampling noise.

**Under that statistic the earlier R=5.08 campaign already showed chi2/dof ~ 0.4 at every
harmonic 1-9 and every dx** -- differences below the single-event noise -- but the noise was set
by the clock seed, so that was a statement about the seed, not about convergence.

**Baseline corrected to an LHC collision:** TRENTo `normalization` 5.73 -> **15.0**, free
streaming `tau` = **1.0** fm/c (already the value in use).

**Seeds fixed.** `iss_dict['randomSeed']` was `-1`, which iSS reads as "use the system clock",
and `run_afterburner.sh` left it there, so every subevent drew fresh entropy. The seed is now
`base + event_id*1000003 + subevent`, which is reproducible on re-run, distinct per event, and
**identical for the same event at every dx** -- which is what turns the paired comparison into a
common-random-numbers one. A base of `-1` maps to `8675309`, so the clock is unreachable even if
the parameter is left alone. `hydro_plus_UrQMD_driver.py:183` and `:228` also drew
`np.random.default_rng().integers(1e8)` from OS entropy per call; both are now deterministic in
`(seed_add, event_id[, iev])`. Both files are baked into the container, so the pin was bumped to
`05ebd42` and a new image is required -- running the old image would silently use the
clock-seeded code.

#### Correction: b alone is the wrong criterion, and MUSIC already solves this for 3dMCGlauber

Two things were wrong in the first pass of this section.

**3dMCGlauber is not a template to copy, it is a different architecture.** MUSIC reads a
*participant list* (`read_in_participants_and_compute_TATB`), builds T_A and T_B itself, and
sizes the grid from the participant positions plus `gridPadding`. The grid is chosen *downstream*
of the model, by the hydrodynamic solver. TRENTo does the opposite: it deposits onto its own grid
and hands MUSIC a finished energy-density table, and that same grid is then used by the
free-streaming stage and by MUSIC. So there is no MUSIC-side auto-sizing to switch on. Making the
grid adaptive for TRENTo means either running TRENTo twice (measure, then re-emit on the chosen
grid) or modifying TRENTo to choose its own output grid, and then propagating that choice through
free-streaming into MUSIC.

**Scaling by b alone is wrong**, because the initial-condition size fluctuates event by event at
fixed b. The right criterion is the one stated in the plan's design principle: choose the number of
cells so that the *numerical* uncertainty is much smaller than every other uncertainty in play.
That is a bound on numerical error, not a matching of sizes, and it is the criterion the campaign
below is built to establish.

Note this dissolves the CRN worry raised earlier. If the box is sized so that discretisation error
is negligible, it does not matter whether the grid is identical across design points -- the error
is common-mode by construction. Making the grid depend on the IC extent is therefore acceptable,
provided the margin is large enough that the error stays negligible.

#### First measurement (batches A/B/D, 19 events each, b-max 0.75 fm) -- and why it was invalid

```
            b range     IC R99      surface max_r    MUSIC s
batch A   0.274-0.713   6.96-8.07      7.33-8.93      94-174
batch B   0.274-0.713   7.03-8.10      7.12-8.55      59-117
batch D   0.274-0.713   7.10-8.12      7.16-8.67      76-149
corr(b, mult) = +0.15    corr(b, R99) = +0.02    corr(b, max_r) = -0.09
```

Read naively this says the transverse extent does not care about b, which would make an
adaptive box pointless. That reading is wrong: **the campaign was invalid.**

`b-max` was 0.75 fm. For Ge+Ge the nuclear radius is about 5.1 fm, so `b_max` is about
10 fm; 0.75 fm samples only the central core. The correlations give it away -- a genuine
minimum-bias sample has multiplicity falling monotonically with b, and here `dN/dy` runs
197-300 with no trend. Every event was central. The flat extent-vs-b result therefore says
nothing about peripheral collisions, and the adaptive-grid question is still open.

What the run *does* establish, central events at least:

- The freeze-out surface reaches only **max_r = 7.3-8.9 fm** while MUSIC runs a **+-20 fm**
  box. Roughly 11 fm of transverse half-width goes unused even centrally, so there is a
  large win available from shrinking the box with no adaptivity at all.
- The surface sits barely outside the initial condition: IC R99.9 is 7.7-9.2 fm against a
  surface reaching 7.3-8.9 fm. At T_freeze = 0.12 GeV the criterion is met only ~0.5-1 fm
  beyond the IC edge, so the box is set by IC size plus a modest expansion margin, not by
  anything that grows with centrality.
- Runtime varies ~2x *within* a batch (94-174 s) and ~1.6x *between* batches, tracking the
  energy scale (B, lower `normalization`, is cheapest; A is dearest). Walltime planning must
  assume the slowest event, not the median.
- `e_fo = 0.0486 GeV/fm^3` is identical across all three batches, confirming the temperature
  criterion behaves and is insensitive to the energy-scale variation.

All four batches re-launched with `b-max = 14 fm` for a real minimum-bias sample. The open
question is whether peripheral collisions really are much smaller, which is the premise the
whole adaptive-grid idea rests on.

#### Result: a sizing rule for the transverse box (141 events, b = 1.46-13.31 fm)

Eight batches, 19 events each, spanning the full centrality range. **First correction to the
campaign design: `b` scales as a constant fraction of `b-max`**, verified because `b/b_max` came
out identical (0.366-0.951) for the same event ids at `b_max` = 0.75 and 14. So TRENTo here is
sampling b as a fixed fraction of `b_max`, not by the Glauber weight, and **central collisions
come from a small `b-max`, not a large one** -- the opposite of what was assumed when `b-max`
was raised from 0.75 to 14 to "get minimum bias". Coverage was completed with `b-max` = 4 and 8,
which together with 14 spans b = 1.46-13.31 fm and multiplicity 3-274.

Measured parameter sensitivity (paired, same events, same nuclei, same b):

| change | d(surface max_r) | d(MUSIC time) |
|---|---|---|
| `T_freeze` 0.10 | **+0.56 fm** (0/18 smaller) | +37 s |
| `T_freeze` 0.15 | -0.05 fm (18/18 smaller) | -57 s |
| `normalization` 4.50 (tau 1.128) | -0.41 fm | -12 s |
| `normalization` 7.00 (tau 0.905) | +0.24 fm | +42 s |
| `tau` 1.25 alone | -0.35 fm | +42 s |

`T_freeze` is the dominant lever and strongly asymmetric, as expected now that freeze-out is on
temperature: dropping it 0.02 GeV buys +0.56 fm of surface, raising it 0.03 costs almost nothing
(`e_fo` runs 0.016 / 0.049 / 0.234 GeV/fm^3 at 0.10 / 0.12 / 0.15). So **any sizing rule must
take the parameters, not just b** -- exactly the concern that motivated this campaign.

The freeze-out surface is well described by a *smoothed* size, not its outermost cell:

```
max_r / r_rms:  median 1.909   p99 2.543   max 2.573     (and flat vs system size:
   median 1.80 / 1.90 / 1.93 in successive r_rms bins -- the tail is a clean scale law)
r_rms  = -0.182 + 1.141 R_rms - 0.109 ln(e_fo) + 0.143 ln(normalization) - 0.810 tau
         R^2 = 0.966,  sigma = 0.165 fm
```

`R_rms` is the RMS radius of the **post-free-streaming** initial condition, which is why the
measure has to be taken after the free-streaming step rather than straight off TRENTo.

**The rule**

```
L = 2.25 * (r_rms_predicted + 5 * sigma)        # transverse half-width, fm
```

covers every one of the 141 measured events (requirement is `max(surface max_r, IC R99.9)`, the
largest of which is 9.24 fm), with zero under-covers. Per event it asks for 52-122 cells at
dx = 0.2 against the current fixed 200 -- a median MUSIC interior cost of **0.17**.

**Correction to the baseline, which changes the headline number.** MUSIC does *not* use
`X_grid_size_in_fm`/`Grid_size_in_x`; its log says

```
Using Initial_profile=9. Overwriting lattice dimensions: neta=1, nx=150, ny=150 deta=0.1, dx=0.2
```

i.e. the lattice comes from the IC table header and those keys are overridden. The box has
therefore always been the TRENTo grid, +-15 fm / 150 cells, never the +-20 fm / 200 cells
assumed earlier in this document. The earlier claim that MUSIC ran a +-20 fm domain with the
IC filling only part of it was wrong, and so was the ~2.6x figure derived from it. Against the
correct 150-cell baseline: median L = 8.1 fm -> 82 cells -> MUSIC factor 0.30 -> event
174 s -> ~82 s, **~2.1x**, ~44 rather than ~19 events per OSG hour. Range: 60 events/hour for
the smallest events, 29 for the largest. Still worth having, and less than it looked.

Caveats before this is used to size anything:

- Fit on `R_rms` in 1.81-4.37 fm. Design points with larger Woods-Saxon radius or higher
  `reduced-thickness` fall outside it; extrapolating the linear model to `R_rms` = 6 fm gives
  L = 13.6 fm, which is still below 200 cells but is an extrapolation and should be clamped or
  re-measured.
- `T_freeze` enters only through `ln(e_fo)`, calibrated over 0.10-0.15 GeV. A design space
  reaching outside that needs another batch, and the asymmetry above says the low side is the
  dangerous one.
- The rule needs `R_rms` *before* MUSIC starts, which is cheap: TRENTo plus free-streaming is
  ~5 s against 120-270 s of MUSIC, so measure, then crop and run. No need to run TRENTo twice.
- The `r_rms` model is fitted to a smoothed quantity while the requirement is a maximum, which
  is why the rule needs a 5-sigma term. That is honest but crude; a quantile of `max_r/r_rms`
  used directly would be tighter.

#### Measurement campaign (run this BEFORE designing anything)

The point of the campaign is to replace assumptions with measurements. Nothing about the dynamic
grid should be implemented until it completes.

**What is measured, per event:**

| quantity | source | why |
|---|---|---|
| impact parameter, multiplicity | `trento_event_summary_*.txt` | already produced |
| IC radial extent R90/R95/R99/R99.9 | TRENTo output matrix | sizes the IC |
| **max transverse extent of the CF freeze-out surface** | `surface*.dat` in hydro results | **the number that sets the box** |
| wall time per event | MUSIC `run.log` timestamps | cost model for batching |

The freeze-out surface is the important one, and it is nearly free: MUSIC already writes
`surface*.dat` every run (the driver globs it and hard-fails if it is empty -- it symlinks it into
the iSS results). It is simply not *collected* in quiet mode, so the campaign runs with full output
or with `surface*.dat` added to the collected set.

**Batching is the test, not just the transport.** A minimum-bias batch of ~19 events at 174 s/event
is ~1 hour on one core and naturally yields ~19 different b values, because each event draws b from
its own event-id-derived seed. So one batch tests batching *and* samples b at the same time.

**Batch matrix.** `normalization` and `tau` are varied *together*, never alone: the intrinsic
timescale of the initial condition goes as 1/sqrt(energy density), so changing `normalization`
without rescaling `tau` is not a physical variation. Proposed first pass:

| batch | normalization | tau (fm/c) | purpose |
|---|---|---|---|
| A | 5.73 (nominal) | 1.00 | reference |
| B | 4.50 | 1.13 | softer / larger system |
| C | 7.00 | 0.90 | harder / more compact |
| D | 5.73 | 1.25 | tau alone, deliberately unphysical, to size that sensitivity |

Batches A-C trace the physical correlation; D is a control that measures how much tau alone moves
the surface, which is what tells you whether the A-C design has enough leverage to be worth
running at all.

**Second, cheap experiment (numerical error bound).** A few events at `dx = 0.2` vs `0.14`,
comparing all observables. This is what converts "the grid is fine enough" from an assertion into
a number, and it is the same comparison that justifies the fixed grid spacing in the design space.

**Open question worth one line of testing.** `use_eps_for_freeze_out = 1` with
`eps_freeze_max = eps_freeze_min = 0.18`, i.e. the CF surface is found by *energy density*. MUSIC
also reads `T_freeze` (default 0.12 GeV). If the energy-density flag selects the criterion outright,
then `T_freeze` is inert in the current configuration -- which would matter directly to the design
space, since a switching temperature is one of the proposed axes. Test: one event with
`T_freeze = 0.12` vs `0.15`, diff the surface and the observables.

### Phase G — Design space (PROPOSED, needs sign-off)

Every key below was verified against the compiled MUSIC binary's string table, not assumed
from the dict: `T_freeze` is a real parameter (default 0.12 GeV), and all four
`bulk_viscosity_3_*` keys and all four `shear_viscosity_3_*` keys that `MakeDictionaries.py`
writes are accepted by MUSIC. MUSIC's input writer emits every music key verbatim
(`itype == 2`), so unknown keys reach the solver rather than being dropped by the framework --
meaning a *misspelled* design key would be silently inert, which is why the binary was checked.

#### Tier A — nuclear structure (the subject of the campaign)

| parameter | current | proposed range | why |
|---|---|---|---|
| `WS_radius` | 7.2 | 6.9 – 7.5 fm | Ge-76 radius; weak prior, couples with deformation |
| `WS_diffusiveness` | 0.50 | 0.44 – 0.60 | surface diffuseness |
| `beta_m` | 0.10 | 0 – 0.35 | quadrupole mean |
| `gamma_m` | 0.436 | 0 – 60 deg | triaxiality mean |
| `sigma_plane` | 0 (rigid) | 0 – 0.08 | event-by-event shape rigidity |
| `sigma_beta_3` | 0 | 0 – 0.02 | octupole fluctuation |

Excluded on purpose: the **sign** of `beta_3` (rotation, not a degree of freedom) and
`shape_distribution` itself (a sampler mode, not physics).

#### Tier B — TRENTo initial condition (deferred to a second phase)

| parameter | current | proposed | comment |
|---|---|---|---|
| `reduced-thickness` | 0.0 | 0 – 0.15 | |
| `fluctuation` | 1.0 | 1.0 fixed | narrowing below 1 is not well constrained by TRENTo |
| `nucleon-width` | 0.5 | **not agreed — deliberately left open** | w sets the scale on which TRENTo smears each nucleon, i.e. the sharpness of the initial condition, so it couples directly to the grid resolution. An earlier draft proposed 0.35–0.65 here; that was my proposal, not an agreed range, and the measurements below extend to w = 1.2 fm specifically so the production resolution can be derived from the numerics rather than inherited from an unreviewed prior. |

Tier B is deferred, not ignored. It is poorly prior-constrained and it is the dimension where
MUSIC is least smooth (small-system fluctuation edges, b -> 0), so putting it in the first LHS
costs emulator accuracy everywhere else. Fix at nominal, revisit after Tier A+C is trained.

#### Tier C — medium

| parameter | current | proposed range | comment |
|---|---|---|---|
| `shear_viscosity_3_eta_over_s_at_kink` | 0.12 | 0.08 – 0.20 | |
| `shear_viscosity_3_eta_over_s_T_kink_in_GeV` | 0.18 | 0.14 – 0.22 | **the switching temperature** |
| `shear_viscosity_3_eta_over_s_high_T_slope_in_GeV` | 0.0 | 0 – 8 | s / GeV, rise above Tc |
| `bulk_viscosity_3_max` | 0.10 | 0 – 0.15 | |
| `bulk_viscosity_3_T_peak_in_GeV` | 0.18 | 0.17 – 0.21 | keep tied to shear kink in phase 1 |
| `T_freeze` | 0.12 | 0.10 – 0.15 | **degeneracy warning below** |

**The one real physics problem in this table.** `T_freeze` and `eta/s` are close to degenerate
for v2: both act as an overall multiplier on accumulated anisotropy, so an LHS that varies both
over modest ranges lands samples on a narrow ridge and produces a long, thin, correlated
posterior in exactly the observable the emulator is being built to predict. Two defensible
resolutions:

1. Fix `T_freeze = 0.12` and spend the freed dimension on shape. Cheapest, and honest -- it is a
   modelling choice, not a measured property of the medium.
2. Widen `T_freeze` to 0.10 – 0.16 *and* keep it, but check the emulator posterior correlation
   matrix before adding anything else. A visible eta/s--T_freeze ridge is a finding, not a bug,
   as long as it is measured rather than hidden.

Recommendation: option 1 for the first LHS, option 2 as an explicit second campaign, so the
degenerate direction gets its own dedicated run rather than degrading the first.

#### Explicitly NOT in the design space

These are fixed for the whole campaign, and each one is a *choice* that must be defended in the
writeup rather than swept:

- `grid_step = 0.2 fm`. Resolution, not physics. MUSIC cost scales roughly as `dx^-2`, so this is
  the single most expensive knob in the file. Needs one resolution study (dx = 0.2 vs 0.14,
  ~2-3 events) to justify, not a design axis.
- `tau = 1.0` (free-streaming). Small systems are the most sensitive to this and it deserves its
  own sensitivity check, but it is an initialisation choice.
- `b`. Not varied: it is event-by-event, not design-by-design. CRN means every design point sees
  the *same* b sequence, so b contributes a common random effect that must be divided out when
  comparing design points.
- Events per design point. Fixed by a target statistical error on v2, not chosen for taste.
- `nthreads = 1`, pinned. Thread count changes reduction order in MUSIC and would destroy the
  bit-reproducibility established in Phase E.
- `tmax = 25`, EOS table, afterburner = decay.

**EOS is a deliberate exclusion.** It is a strong lever on essentially every flow observable, so
including it would be defensible scientifically -- but it multiplies the cost of the campaign and
it is a different paper's parameter. Recommendation: fix one EOS, and state it as a limitation
whose size can be bounded later by re-running a couple of points with a second EOS.

#### Recommended first LHS: 9 dimensions

`WS_radius`, `WS_diffusiveness`, `beta_m`, `gamma_m`, `sigma_plane`, `sigma_beta_3`,
`eta/s at kink`, `kink temperature`, `bulk zeta/s max` -- with `T_freeze` fixed and Tier B fixed.

Shape and viscosity first, because those are what the deformation question actually needs, and 9
dimensions is small enough that ~200 points with CRN should give a usable posterior.

 LHS design generator
Emit the design CSV over WS radius, diffuseness, deformations + fluctuation widths, TRENTo
parameters, viscosity. De-hardcode `submit_design_points.py:20` (`DEFAULT_OSG_SCRIPT`) and the
`-n/-nev/-nth` literals — **use the batch size measured in E1.**

### Phase H — Provenance + emulator join
Per-event record of `(MASTER_SEED, row_address, realised β₂/β₃/γ, b, mult, design-point id)`; design-point
id in generated parameter files; replace `combine_multiple_hdf5.py`'s random-letter renaming with
deterministic names so the X/y join survives merging.

*Exit:* a single table joins every event to its design point and its inputs.

---

## 5. Risks and open items

- **Reproducibility is the load-bearing assumption.** The whole common-random-numbers design rests
  on a given event producing the same nucleon configuration on every machine and every rerun. It
  is currently *believed*, not demonstrated — the container pins the framework to an exact SHA
  and the seeds are counter-based, but neither has been checked end to end. Phase E2 is blocking.
- **Thread count may perturb observables.** OpenMP/MPI reduction order in MUSIC can change `v2`
  in the last bits for identical input. Pin threads and record the value; do not assert
  bit-identity of observables without measuring it.
- **Phase A measurement may change the campaign size.** Do not commit to a design-point count before
  the gate.
- **Statistical floor.** The anchor's error is dominated by the shape ensemble. With a virtual pool
  this is negligible for any realistic precision, but if a *fixed finite* pool is ever reinstated,
  `P ≳ 1600` is needed for ~0.5% on the anchor's absolute values.
- **`decay` path is the only fully-validated one.** SMASH branches in both generators remain broken
  (OSG: `event_0`; transfer globs reference files SMASH does not emit). Avoid SMASH until fixed.
  This is also why Phase F's slimming is safe in principle — the campaign never uses SMASH.
- **Fetched code packages are missing from this checkout.** `codes/hadronic_afterburner_toolkit`,
  `codes/hadronic_afterburner_toolkit_code/ebe_scripts/average_event_spvn_h5.py` and
  `config/hadronic_afterburner_toolkit` are gitignored and absent, so `generate_jobs.py` cannot
  currently build a full event tree. Run `codes/get_code_packages.sh` before Phase E.
- **Anchor point parameters are undecided** (pool/events-per-design-point) pending Phase B.
- `MakeDictionaries.py` hardcodes `number_nucleons: 96` and omits `beta_4` — resolve if the sweep
  spans systems other than Zr/Ru.
- **`beta_3` sign is a rotation, not a degree of freedom** (Phase D). Its magnitude is the real
  parameter; do not spend a design axis on the sign.
