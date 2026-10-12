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

Housekeeping available once Phase B lands: `shared_seeds/nucleon-seeds.hdf` is a tracked 62.8 MB
binary that GitHub warns exceeds its 50 MB recommendation (GH001). Retiring it from version control
is a natural follow-on to dropping seed-file transfer.

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
Port from the working OSG UrQMD path: pass `--event_start_id`/`--event_end_id`; fix
`EVENT_RESULTS_$(Process)` globs; move the tarball `mv` to after `submit_job.script`; add `set -e`;
drop the nonexistent `--isobar_seed_file` and the absent `-seed_file` flag.

*Exit:* N jobs on the local cluster produce N distinct event ranges and return results.

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
Per-config β₂/β₃/γ draws threaded from `build_nucleus` into `deform_nucleus` (already argument-based).
New YAML keys (`sigma_beta2`, `sigma_beta3`, `gamma_kappa`) need no plumbing (see findings table).

*Exit:* realised β values are recorded per event and match the intended distribution.

### Phase E — LHS design generator
Emit the design CSV over WS radius, diffuseness, deformations + fluctuation widths, TRENTo
parameters, viscosity. De-hardcode `submit_design_points.py:20` (`DEFAULT_OSG_SCRIPT`) and the
`-n/-nev/-nth` literals.

### Phase F — Provenance + emulator join
Per-event record of `(MASTER_SEED, row_address, realised β₂/β₃/γ, b, mult, design-point id)`; design-point
id in generated parameter files; replace `combine_multiple_hdf5.py`'s random-letter renaming with
deterministic names so the X/y join survives merging.

*Exit:* a single table joins every event to its design point and its inputs.

---

## 5. Risks and open items

- **Phase A measurement may change the campaign size.** Do not commit to a design-point count before
  the gate.
- **Statistical floor.** The anchor's error is dominated by the shape ensemble. With a virtual pool
  this is negligible for any realistic precision, but if a *fixed finite* pool is ever reinstated,
  `P ≳ 1600` is needed for ~0.5% on the anchor's absolute values.
- **`decay` path is the only fully-validated one.** SMASH branches in both generators remain broken
  (OSG: `event_0`; transfer globs reference files SMASH does not emit). Avoid SMASH until fixed.
- **Anchor point parameters are undecided** (pool/events-per-design-point) pending Phase B.
- `MakeDictionaries.py` hardcodes `number_nucleons: 96` and omits `beta_4` — resolve if the sweep
  spans systems other than Zr/Ru.
