# Provenance

Everything needed to reproduce the 76Ge emulator ensemble, in one place. A reader who
finds only this directory should be able to answer: which code, which container, which
design, which seeds, and what every parameter was actually set to.

| file | what it is |
|---|---|
| `manifest.json` | git revision, container path and md5, design file and its sha256, the two seeds, and the Dockerfile framework pin |
| `parameters_design_0001.json` | the **fully resolved** parameter dictionary for design point 1 — every key the master fills in, not just the design row |

`git_revision` names the commit whose code produced the numbers. The commit that adds this
directory is one step later and contains nothing but provenance, so check out `git_revision`,
not the tip, if in doubt.

## Why the resolved dictionary and not the design row

The design row is not the parameter dictionary. `MakeDictionaries.py` converts
`sigma_k` into TRENTo's `fluctuation` (k = 1/sigma_k²), `gamma` from degrees to radians,
computes `b_max` from the shape parameters, and the master then derives the freeze-out
width, the afterburner switches, the EOS, the dissipation coefficients and several hundred
other keys. `parameters_design_0001.json` is the state after all of that, which is the only
form in which the inputs are actually complete.

To regenerate it for any design point:

```bash
python3 scripts/record_provenance.py --design-point 250 \
    --image /ospool/ap40/data/matthew.luzum/iebe-music_slim_<sha>_<md5>.sif
```

## How to reproduce a run

1. Check out `git_revision` from `manifest.json`.
2. Use the container whose md5 is `sif_md5`. The image is built by `docker/Dockerfile`
   from the framework pin recorded as `dockerfile_pin`, so rebuild it with
   `docker build --build-arg WITH_OPTIONAL_CODES=0 docker/` if the SIF is gone. Verify
   `md5sum` before use: OSDF caches by path, and a mismatched image produces numbers that
   look plausible and are wrong.
3. Take `design/design_lhs2000.csv`, which must hash to `design_sha256`. Rows are in the
   campaign order (maximin), so design points 1..N are the intended prefix.
4. Generate and submit with the campaign seeds: `MASTER_SEED = 8675309` and
   `campaign_seed_add = 0`. An event is then identified exactly by
   `(8675309, 0, global_event_id, iev)`.

## Two keys that mean something other than what they look like

The resolved dictionary contains three near-identical-looking switches, and only some of
them are authoritative. This has already caused one silent misreading, so:

- `control_dict['afterburner_type']` — **the master's default, literally `"SMASH"`, and
  never updated by the merge.** Do not read it. The user parameter file and the driver
  decide the chain.
- `iss_dict['afterburner_type']` — iSS's own switch, left at its default `1`. The
  decays-only path does not use it.
- What actually identifies the decays-only chain: `iss_dict['perform_decays'] == 1`,
  `iss_dict['use_binary_format'] == 1`, `hadronic_afterburner_toolkit_dict['read_in_mode'] == 9`,
  and `hadronic_afterburner_toolkit_dict['dNdy_normalization_width'] == 10.0`
  (= `y_RB - y_LB`). The width is non-zero **only** for the decays-only path; it must be
  0 for any 3+1-d cascade.
