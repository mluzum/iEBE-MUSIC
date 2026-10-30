# Campaign 2 hand-off: full T^munu, three delta f models, new pT grid

For the session that manages the OSG jobs.  Status (2026-10-30): everything
below is implemented and validated; `NME` = `campaign2` is pushed to the fork;
the Dockerfile is pinned to `17ae5b4`; the slim image is built and verified on
the build host and saved as
**`/data/mluzum/iebe-music_slim_17ae5b4_f5242628.sif`** (md5
`f52426284ebb281b813f21d931bd847a`, 515575808 bytes).  Not done: publishing the SIF,
generating the campaign-2 dictionaries, the A=76 cross sections at the new
sigma_NN, staging and submission (steps 5-9 below).  Physics background and
all numbers:
`/data/Scripts/soft-sector-data-curation/docs/isobar_flow_investigation.md`
(sections 5-9).

## 1. What changes relative to the first zr96 / ge76 campaigns

| | campaign 1 | campaign 2 |
|---|---|---|
| hydro initial state | `Initial_profile 92`: free-streamed e only, fluid at rest | `Initial_profile 9`: full free-streaming T^munu (e, u^mu, pi^munu, Pi) |
| particlization | one iSS run per surface, linear CE delta f | one iSS + decays + analysis per **delta f model**: `Grad22`, `CE`, `PTB`, same surface and seeds |
| PTB delta f | - | new in iSS (`codes/patches/iSS_PTB_deltaf.patch`, `iss_dict['deltaf_model'] = 1`) |
| identified-particle pT grid | 0.2-2.0 GeV, 41 bins of 0.0439 GeV | **0-5 GeV, 100 bins of 0.05 GeV** |
| `spvn_results_<id>.h5` | flat | per-model sub-groups `deltaf_<name>`, attrs (see 5) |
| A=96 normalization prior | 3-10 | **6-13** (`design/design_lhs2000_A96_c2.csv`) |
| A=76 normalization prior | 10-20 | **12-24** (`design/design_lhs2000_c2.csv`) |
| A=76 TRENTo sigma_NN | 4.23 fm^2 (200 GeV) | **6.8 fm^2** (68 mb, ~5 TeV; design column) |

Both new designs are the old ones on the **same 2000-point unit-cube Latin
hypercube** (only the changed axes are remapped; labels, order and every
other column are identical), so `design_000k` corresponds point by point to
campaign 1 and between A=76 and A=96 (`design/CAMPAIGN2_DESIGNS.md`).

Why, in one paragraph each:

- **T^munu.** The driver wrote only e into MUSIC's initial table, so hydro
  started at rest and lost ~17% of the free-streaming energy (zr96 dp0583:
  215 instead of 258 GeV per unit rapidity).  Restoring it raises dN/dy by
  10-23%, <pT> by 13-21% and v2 by 1.4-2.4x on the two test points.
- **delta f.** iSS's sampler (`MC_sampling 4`) accepts momenta with
  probability (1 + delta f)/2 clipped to [0, 1], i.e. it silently clamps the
  linear delta f to [-1, 1]; `restrict_deltaf` is not read by this sampler.
  Where eta/s at freeze-out is large (~0.35 at dp0583), pi/(e+P) ~ 0.1 and
  the clamp acts on most of the emission above 1 GeV: a single-cell closure
  test recovers only 64% (CE) / 53% (22-moment) of the hydro pi.  PTB is a
  positive-definite modified equilibrium that recovers it to 5% and equals
  the CE delta f at small pi.  The three models together are the delta f
  systematic (JETSCAPE used the same kind of set).
- **pT grid.** The old toolkit settings gave bin edges 0.2 + i*0.0439 GeV,
  so no experimental cut other than 0.2 and 2.0 was a bin edge and the
  0.15/0.3/0.5/3/5 GeV cuts of ALICE/CMS/ATLAS records could not be applied
  without interpolation.  The toolkit's bins are edges
  `pT_min + i*(pT_max - pT_min)/npT` (`single_particleSpectra.cpp`), so
  0-5 GeV with npT = 100 puts an edge every 0.05 GeV.

Not changed: decays-only afterburner, seeds (an event is still
`(MASTER_SEED, seed_add, event_id, iev)`; all delta f models of an event use
the same iSS seed), b_max formula, hydro grid, `quest_revert_strength`,
the normalized design, number of events.

## 2. Code

Now on `NME` (fast-forwarded to `campaign2`, pushed to `mluzum/iEBE-MUSIC`),
in order:

| commit | content |
|---|---|
| `d365f42` | driver writes the full free-streaming T^munu into MUSIC's table (`scripts/check_freestream_table.py` validates it) |
| `e1e2297`, `e717680` | `scripts/rerun_events_local.py`: re-run campaign events locally in the campaign image |
| `813be61` | iSS PTB patch, applied (and checked) by both bootstrap scripts; master gains `deltaf_model`, `ptb_min_eigenvalue`, `control_dict['deltaf_models']` |
| `e4ffea5` | driver + `generate_jobs.py`: one particlization per model; `merge_dp_h5.py` copies sub-groups and attributes |
| `55084d1` | template `config/design_points/parameters_dict_user_TRENTo_realistic.py` (and MakeDictionaries' fallback): `Initial_profile 9`, the three models, the pT grid |
| `80ce750` | validation tools: `rerun_events_local.py --bind`, `scripts/validation/` |
| `e5dac45` | AGENTS.md notes |
| `315556b` | this file (first version) |
| `1306841` | A=96 design, normalization 6-13 (`scripts/remap_design_prior.py`) |
| `17ae5b4` | merge of `NME`'s A76 cross-section README -- **the image pin** |
| `06cc504` | Dockerfile pinned to `17ae5b4` |
| `0a8f4a4` | A=76 design, normalization 12-24 + `cross-section` 6.8 fm^2 column (MakeDictionaries reads it) |
| later | this file, updated |

Commits after `17ae5b4` change only submit-side files (designs, MakeDictionaries,
docs): the image does not need a rebuild for them.  `campaign2` was developed in
a git worktree under a temporary directory; `git worktree prune` if it is gone.

## 3. Steps to launch

Steps 1-4 are done (2026-10-30); they are kept here as the procedure for any
later image.

1. **Merge / push.** Done: `NME` fast-forwarded to `campaign2` (after merging
   `NME`'s one new commit) and pushed.
2. **Pin.** Done: `docker/Dockerfile` pins `17ae5b49c083a33783f72ed5d00b8822973a2d70`
   (`06cc504`); `scripts/check_docker_pin.sh` passes.
3. **Build.** Done on the build host:
   `cd docker && docker build --build-arg WITH_OPTIONAL_CODES=0 -t iebe-music:slim-17ae5b4 .`
   The bootstrap applies the iSS patch to the pinned iSS `d242555` and fails
   if it does not apply.
4. **Verify.** Done (results in 6 below); to repeat for any image:
   - delta f closure (needs only the image):
     ```
     V=/data/mluzum/campaign2_validation/closure_inputs
     python3 scripts/validation/deltaf_closure_test.py \
         /opt/iEBE-MUSIC/codes/iSS_code/iSS.e $V/iSS_parameters.dat \
         $V/surface_eps_0.1268.dat $V/music_input /tmp/closure_check \
         --image iebe-music:slim-17ae5b4
     ```
     must reproduce the reference numbers in the script's docstring
     (pi/(e+P) = 0.15: model 0 recovers ~0.64, model 1 ~1.05 of the input).
   - one design point end to end against reference events:
     ```
     R=/data/mluzum/campaign2_validation/reference_events
     python3 scripts/rerun_events_local.py --image iebe-music:slim-17ae5b4 \
         --param $R/parameter_dictionary_design_point_583.py \
         --events 10,220 --out /tmp/c2check --variant image --jobs 2
     ```
     and compare `/tmp/c2check/image/results/spvn_results_{10,220}.h5` with
     `$R/spvn_results_{10,220}.h5` dataset by dataset.
5. **Publish** `/data/mluzum/iebe-music_slim_17ae5b4_f5242628.sif` to OSDF under exactly that name (never reuse
   a name; AGENTS.md) and check the path in the submit files.
6. **Generate the dictionaries** from the campaign-2 designs into new folders
   (keep the campaign-1 ones; they document what ran), from the repo root:
   ```
   mkdir zr96_design_c2 && (cd zr96_design_c2 && python3 ../MakeDictionaries.py \
       --design ../design/design_lhs2000_A96_c2.csv \
       --start-design-point 1 --end-design-point 1000 --output-dir .)
   mkdir ge76_design_c2 && (cd ge76_design_c2 && python3 ../MakeDictionaries.py \
       --design ../design/design_lhs2000_c2.csv \
       --start-design-point 1 --end-design-point 1500 --output-dir .)
   ```
   (adjust the point ranges to the campaign size).  Diff one of each against
   campaign 1 before staging: A=96 differs in `control_dict['deltaf_models']`,
   `Initial_profile 9`, the toolkit `pT_min 0.0 / pT_max 5.0 / npT 100` and
   the normalization (+3); A=76 additionally in `'cross-section': 6.8` and the
   normalization (x1.2 on the 10-20 -> 12-24 map).
7. **A=76 cross sections.** sigma_NN changed, so recompute the A=76 sigma_inel
   / b_max tables on the new dictionaries (`scripts/cross_section/`: add a
   campaign entry for `ge76_design_c2` in `run_xsec.py`).  A 12-point estimate
   (n_conf 300) gives sigma_inel +6% and the share below b_max 0.75-0.90
   (median 0.835; was 0.79-0.92, median 0.87).  The A=96 tables stay valid
   (normalization does not enter TRENTo's collision probability).
8. **Provenance, stage, submit** as before: `scripts/record_provenance.py`
   with the new image and designs; `scripts/stage_campaign.py` with
   `--dict-dir zr96_design_c2` / `ge76_design_c2`, a new `--jobid-template`
   (e.g. `zr96c2_b{batch}_dp{dp}`) and a new `--apbase`, so campaign-2 output
   never mixes with campaign 1.
9. **Pull and consolidate** with the new `scripts/merge_dp_h5.py` (via
   `consolidate_dps.sh`; it is on `NME`).  The old merger kept only top-level
   datasets and would silently drop every delta f model.

## 4. Resources

Measured on this host (48 cores, 1 thread per event, loaded machine):

- wall time per event ~+45%: MUSIC 75-90 s unchanged, each particlization
  (10 iSS runs + decays + analysis) 25-30 s, three instead of one.  Expect
  the 20-event job median to go from ~1.1 h to ~1.6 h.  PTB itself costs
  ~0.4 s per iSS run.
- memory: unchanged (models run sequentially); keep 1 GB.
- scratch disk: per-model particle lists are deleted after each analysis;
  keep `--disk 4`.
- output: `spvn_results_<id>.h5` 160 -> 456 KB; per-job tarball ~5.7x
  (31 -> 174 KB per event: the old files were mostly compressible HDF5
  overhead), i.e. ~350 MB per design point at 2000 events instead of ~60 MB.
  The AP data disk (465 GB) then holds ~1300 design points of archives at
  once, so pull and prune as you go.  Merged files: 51 -> 254 KB per event,
  ~0.5 GB per design point, ~1.3 TB for 2500 points on `/data`.
  Dropping `Grad22` saves a third of the particlization time and output.

## 5. Output format (for any downstream reader)

`spvn_results_<id>` (one group per event, also in the merged file):
- top level: hydro-level datasets as before (`eccentricities_evo_*`,
  `momentum_anisotropy_*`, `meanpT_estimators_*`, ...);
- `deltaf_Grad22/`, `deltaf_CE/`, `deltaf_PTB/`: the identified-particle
  tables (`particle_<pid>_vndata_diff_y_-30_30_boostinv.dat` now 100 x 13,
  `particle_<pid>_vndata_y_-30_30_boostinv.dat` 7 x 5), attr
  `iss_overrides`;
- attrs `deltaf_models = "Grad22,CE,PTB"`, `toolkit_pT_min = 0.0`,
  `toolkit_pT_max = 5.0`, `toolkit_npT = 100`.

Readers must choose a model.  The soft-sector pipeline does
(`run_pipeline.py --sim isobar --deltaf-model CE`, grid read from the
attrs); analysisKit still expects the flat layout and needs the same change
before it can read campaign-2 files.

## 6. Validation done (all on zr96 dp0583 / dp0291 events, campaign image)

The built image (`iebe-music:slim-17ae5b4`, and the SIF above: same md5 for
iSS.e, MUSIChydro and the driver) reproduces the reference events 10 and 220
bit for bit (98/98 datasets, attributes equal) and the closure test's
reference numbers exactly.  Earlier checks, made with the patched iSS and the
new framework mounted into the campaign-1 image:

- iSS: patched binary with `deltaf_model 0` writes byte-identical samples to
  the campaign binary on a real surface (an unpatched local build does too).
- Closure (single static cell, 3.5e6 particles): pi^{ij} recovered at
  pi/(e+P) = 0.01 / 0.05 / 0.15: PTB 1.01 / 1.03 / 1.05, CE 1.01 / 0.96 /
  0.64, Grad22 - / 0.85 / 0.53; bulk Pi = -0.03(e+P): P + Pi and e exact for
  PTB and CE; particle number CE -6%, PTB +14% (a genuine model difference).
- Bookkeeping: with campaign-1 physics and the three models, `deltaf_CE`
  is bit-identical to the campaign output (26/26 particle tables, 20/20
  hydro datasets), CE run second in the loop; the merged file loads through
  the soft-sector loader with `deltaf="CE"` identical to the campaign event.
- Template path: events run from the regenerated dictionary equal the
  `--set`-override runs dataset for dataset (98/98).
- 160 paired events with the full new configuration, no failures; physics
  below.

## 7. What the new configuration does (paired with campaign 1, same events)

dp0583 (eta/s ~0.35 at T_f), 20-30% / 40-50%:

| | v2{2} | v3{2} | kappa3 | dN/dy |
|---|---|---|---|---|
| campaign 1 | 0.025 / 0.020 | 0.0095 / 0.016 | -0.032 / -0.053 | 111 / 53 |
| Grad22 | 0.051 / 0.061 | 0.013 / 0.0079 | +0.045 / +0.024 | 135 / 66 |
| CE | 0.045 / 0.049 | 0.0078 / 0.0039 | +0.024 / +0.001 | 135 / 66 |
| PTB | 0.042 / 0.042 | 0.0056 / 0.0092 | +0.007 / -0.022 | 136 / 67 |

dp0291 (eta/s_kink 0.076, zeta/s_max 0.10; the best campaign-1 point),
20-30% / 40-50%:

| | v2{2} | v3{2} | <pT> | dN/dy |
|---|---|---|---|---|
| campaign 1 | 0.059 / 0.066 | 0.021 / 0.011 | 0.578 / 0.555 | 106 / 50 |
| Grad22 | 0.082 / 0.103 | 0.040 / 0.032 | 0.651 / 0.639 | 119 / 57 |
| CE | 0.081 / 0.100 | 0.038 / 0.030 | 0.652 / 0.640 | 117 / 56 |
| PTB | 0.083 / 0.102 | 0.040 / 0.030 | 0.612 / 0.591 | 130 / 63 |

(STAR Ru+Ru 20-30%: v2{2} 0.059, v3{2} 0.021.)  At high-eta/s points the
delta f model changes the flow a lot (PTB, which applies all of pi, gives
the strongest viscous correction and keeps an anti-aligned v3 at dp0583
40-50%); at low eta/s it hardly changes the flow but PTB's bulk correction
moves dN/dy (+11-14%) and <pT> (-6 to -8%) relative to CE.  That spread is
the systematic the three models are there to measure.

## 8. Decisions

Taken by the user (2026-10-30): normalization priors A=96 6-13 and A=76
12-24 on the same hypercube; A=76 at sigma_NN = 6.8 fm^2 (~5 TeV); all three
delta f models despite the cost.

Open, for the user (not the job session):
- **b_max at sigma_NN = 6.8 fm^2 (A=76).**  b_max does not depend on
  sigma_NN, so a larger sigma_NN leaves more of sigma_inel beyond it.  From
  the 12-point estimate, the share of events of a centrality range with
  b > b_max (median / max over points): 0-60%: 0.0 / 1.2%; 0-70%: 1.0 /
  3.8%; 0-80%: 4.3 / 10% (at 4.23 fm^2: 0.1 / 0.6%, 0.6 / 2.9%, 2.8 / 7.6%).
  Fine to ~70% centrality; the 70-80% class loses events at the most
  extended nuclei.  Adding sqrt(sigma_NN/pi) - sqrt(4.23/pi) = 0.31 fm to
  b_max for A=76 would roughly restore campaign 1's coverage (a change to
  `bmax_from_design`, before generating the dictionaries).
- Centrality anchoring in the analysis uses the per-design-point share below
  b_max (`/data/mluzum/cross_sections/*/summary_*.csv`, A=76 to be redone).
