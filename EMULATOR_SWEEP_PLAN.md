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
| `iebe-music_slim.sif` | -- | `97bf05f9...` | alias -> the above |
| `iebe-music_slim_4d5e6f0.sif` | pre-2f840cc pin | `1370bd59...` nucleus-era image | superseded |

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

#### The design decision that actually matters: what should L depend on?

- **L = f(b), identical for every design point.** The grid then depends only on the impact
  parameter, which is a common random number, so *discretisation error becomes a common random
  effect and cancels in design-point contrasts.* This is the version that fits the existing
  CRN design.
- **L = f(measured IC extent).** Tempting, because it automatically tracks Woods-Saxon radius,
  deformation, `reduced-thickness` and `nucleon-width` -- all of which are design parameters.
  But it makes the *numerical grid itself* design-point-dependent, so the emulator would absorb
  a discretisation systematic as if it were physics. **Not recommended.**

Recommendation: **Route A (fixed dx) with L = f(b), quantised** to a coarse ladder of cell
counts (e.g. multiples of 25) so runtime is predictable and you do not accumulate a continuum of
distinct MUSIC configurations.

#### The one risk that must be tested first

An undersized box is only safe if MUSIC **fails loudly** when the freeze-out surface reaches the
domain edge. If it instead silently clamps the surface, the damage is invisible. The binary
contains "freeze-out surface set by temperature is not ...", which suggests a hard error, but that
is a string, not a guarantee. **This is the blocking question for the whole idea.**

#### Proposed feasibility test

- **Step 0 (instrument only, no behaviour change).** At the current fixed grid, run ~12 events
  spanning b and record, per event: IC R99 and R99.9, the maximum |x| reached by the freeze-out
  surface, and wall time. This calibrates the required margin and gives the cost-vs-b curve, and
  costs about an hour on one core. Everything downstream depends on these numbers.
- **Step 1.** Implement crop + per-event MUSIC input patch behind a flag (default off).
- **Step 2.** Validate: rerun the same events adaptive vs reference, compare all 179
  observables, require the difference to be far below the statistical error, and confirm zero
  freeze-out failures. Also confirm the IC momentum-distribution files
  (`ed_etas_distribution_*.dat`) are regenerated on the new grid.

Nothing here should be adopted before Step 0 and Step 2 pass.

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
| `nucleon-width` | 0.5 | 0.35 – 0.65 | |

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
