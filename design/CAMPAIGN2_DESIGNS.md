# Campaign-2 designs (2026-10-30)

Both campaign-2 designs are the campaign-1 designs on the **same 2000-point
unit-cube Latin hypercube**: `scripts/remap_design_prior.py` maps only the
changed axes through each point's unit-cube coordinate and copies every
other column, the labels and the row order verbatim (nothing is redrawn).
`design_000k` is therefore the same normalized point in campaign 1 and 2, and
in A=76 and A=96, which allows paired comparisons and transfer between the
ensembles.

| file | from | changed |
|---|---|---|
| `design_lhs2000_A96_c2.csv` | `design_lhs2000_A96.csv` | `normalization` 3-10 -> **6-13** |
| `design_lhs2000_c2.csv` (A=76) | `design_lhs2000.csv` | `normalization` 10-20 -> **12-24**; new constant column `cross-section` = **6.8** fm^2 |

- A=96 (200 GeV RHIC): with the full free-streaming T^munu the multiplicity
  at fixed normalization rises 10-23%; the STAR data want roughly 7.5-9.5.
- A=76 (hypothetical LHC run, ~5 TeV): 10-20 was the Pb+Pb 2.76 TeV prior;
  x1.2 is the measured 5.02/2.76 TeV multiplicity ratio.  Campaign-1 A=76
  gives a 0-5% charged dN/dy (0.2-2 GeV) of ~29 per unit normalization;
  with full T^munu and sigma_NN = 68 mb a ~5 TeV run (dN_ch/deta ~ 670 at
  0-5%) wants ~17 +- 4.
- `cross-section` is TRENTo's sigma_NN.  Campaign 1 (both A) used the
  template's 4.23 fm^2 (42.3 mb, 200 GeV); A=76 campaign 2 uses 6.8 fm^2
  (68 mb, ~5 TeV).  MakeDictionaries takes it from the design column (else the
  template).  b_max now grows with the interaction range,
  + sqrt(sigma_NN/pi) - sqrt(4.23/pi) (+0.31 fm at 6.8 fm^2, 0 for A=96),
  which keeps the share of sigma_inel below b_max at campaign 1's level
  (12-point estimate: median 0.867 vs 0.870).  Recompute the A=76 cross
  sections (`scripts/cross_section/`) on the campaign-2 dictionaries.
- Normalization does not enter TRENTo's collision probability: the A=96
  cross-section tables stay valid.
