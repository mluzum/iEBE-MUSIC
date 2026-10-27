# A=96 campaign — prior ranges (proposal, 2026-10-27)

Design for the ⁹⁶Zr/⁹⁶Ru campaign (`design/design_lhs2000_A96.csv`), to be run
after the A=76 campaign. This is the review copy: nothing here is used by the
running campaign; generating the CSV is free and can be repeated after any
change to the ranges below.

## Key property: the same design, rescaled

`MakeDictionaries`-facing designs are drawn by `scripts/make_design.py` in the
**unit cube** and then mapped per axis with `x = lo + u*(hi - lo)`. The maximin
ordering is computed **on the unit-cube points**. Therefore, changing only
`lo`/`hi`:

- keeps every design point's normalized coordinates `u` identical,
- keeps the maximin ordering (labels `design_000k`) identical,
- changes only the physical values, by the per-axis affine map.

Conditions: same number of points (`--n 2000`), same seed (`8675309`), and the
same 20 axes in the same order. Adding, removing or reordering an axis changes
the draw itself.

Consequence: `design_000k` is the *same* normalized point in the A=76 and A=96
campaigns, so the two runs are paired point-by-point.

## Planned priors

| # | axis (design column) | A=76 (current) | **A=96 (planned)** | change |
|---|---|---|---|---|
| 1 | `normalization` | 10 – 20 | **3 – 10** | ↓ for 200 GeV RHIC (JETSCAPE) |
| 2 | `reduced-thickness` | −0.7 – 0.7 | −0.7 – 0.7 | same |
| 3 | `nucleon-width` | 0.5 – 1.5 | 0.5 – 1.5 | same |
| 4 | `sigma_k` | 0.3 – 2.0 | 0.3 – 2.0 | same |
| 5 | `tau` | 0.3 – 2.0 | 0.3 – 2.0 | same |
| 6 | `shear_viscosity_3_eta_over_s_at_kink` | 0.01 – 0.20 | 0.01 – 0.20 | same |
| 7 | `shear_viscosity_3_eta_over_s_low_T_slope_in_GeV` | −2.0 – 0.0 | −2.0 – 0.0 | same |
| 8 | `shear_viscosity_3_eta_over_s_high_T_slope_in_GeV` | 0.0 – 2.0 | 0.0 – 2.0 | same |
| 9 | `shear_viscosity_3_eta_over_s_T_kink_in_GeV` | 0.13 – 0.30 | 0.13 – 0.30 | same |
| 10 | `bulk_viscosity_3_max` | 0.01 – 0.25 | 0.01 – 0.25 | same |
| 11 | `bulk_viscosity_3_T_peak_in_GeV` | 0.12 – 0.30 | 0.12 – 0.30 | same |
| 12 | `bulk_viscosity_3_width_in_GeV` | 0.025 – 0.15 | 0.025 – 0.15 | same |
| 13 | `T_freeze` | 0.135 – 0.165 | 0.135 – 0.165 | same |
| 14 | `WS_radius` | 4.9 – 5.3 | **5.0 – 5.7** | ↑ wider (r0 = 1.09 – 1.25) |
| 15 | `WS_diffusiveness` | 0.45 – 0.60 | 0.45 – 0.60 | same |
| 16 | `beta_2` | 0.0 – 0.5 | **0.0 – 0.4** | ↓ (same prior as beta_3) |
| 17 | `gamma` | 0 – 60 deg | 0 – 60 deg | same (full physical range) |
| 18 | `beta_3` | 0.0 – 0.2 | **0.0 – 0.4** | ↑ large octupole |
| 19 | `sigma_plane` | 0.0 – 0.08 | 0.0 – 0.08 | same |
| 20 | `sigma_beta_3` | 0.0 – 0.05 | **0.0 – 0.08** | ↑ larger octupole fluctuation |

Fixed (not design axes):

| column | value |
|---|---|
| `shear_relax_time_factor` | 5.0 |
| `bulk_viscosity_3_lambda_asymm` | 0.0 |
| `shape_distribution` | `plane` |
| `number_nucleons` | **96** (was 76) |

## Notes and open points

- **A=96 has no proton number.** The nuclear input is A nucleon positions from a
  Woods–Saxon profile; the sampler has no Z. An A=96 run therefore describes
  ⁹⁶Zr and ⁹⁶Ru identically — the isobar *pair* (same A, different Z) is not
  expressible in the current model. Worth keeping in mind if the physics goal
  is the Z difference (neutron skin, isospin).
- **`beta_max`** is the support of the Option-B `wedge` shape draw. Since this
  design uses `shape_distribution = plane`, it is inert; `MakeDictionaries`
  defaults it to 0.5. Could be set to 0.4 for tidiness with no effect.
- **`b_max`** is recomputed per design point from `WS_radius`,
  `WS_diffusiveness`, `nucleon-width` and the 2σ deformation, so `b/b_max`
  remains the synchronized variable across design points.
- **Seed pool**: `number_nucleons = 96` is well within the 300 available rows;
  the pool address depends only on the global event id, so the A=76 and A=96
  campaigns are event-synchronized with each other as well.
- Open for discussion: whether `nucleon-width` or `tau` need a 200-GeV-specific
  tweak; whether any axis should be added or removed (which would change the
  design itself, not just its scale).
- Decided: `gamma` stays at the full physical range 0–60°.

## Regenerating

```bash
python3 scripts/make_design_a96.py                     # writes design/design_lhs2000_A96.csv
python3 scripts/make_design_a96.py --check-against-a76 # also verifies u matches the A=76 design
```

Editing this table's ranges and rerunning is all that is needed; the labels and
the normalized design do not move.
