# Reading identified-particle pT-differential results

Short, practical guide for extracting **yields and $v_n$ vs $p_T$** for the 13
identified species from the merged campaign files. It is deliberately limited to
that use case; `FLOW_OUTPUT_FORMAT.md` remains the authoritative description of
every column and every trap.

---

## 1. Where the data is

```
merged/<dp>/<dp>.h5            one HDF5 file per design point
merged/<dp>/csv.tgz            the drawn-event table, one CSV per block
```

Inside `<dp>.h5` there is **one HDF5 group per event**, named
`spvn_results_<global_event_id>`. Each group holds 46 datasets: 26 of them are
the particle tables used here (13 species x differential + integrated), the rest
are eccentricities/mean-pT/etc.

```python
import h5py
f = h5py.File("merged/dp0001/dp0001.h5", "r")
events = list(f.keys())            # e.g. ['spvn_results_0', 'spvn_results_1', ...]
```

The group names are the **global event ids** used by the campaign, so events are
comparable one-to-one across design points.

## 2. Species

The 13 identified species are stored under their PDG ids:

| PDG | particle | dataset stem |
|---|---|---|
| 211 / -211 | pi+ / pi- | `particle_211_*`, `particle_-211_*` |
| 321 / -321 | K+ / K- | `particle_321_*`, `particle_-321_*` |
| 2212 / -2212 | p / pbar | `particle_2212_*`, `particle_-2212_*` |
| 3122 / -3122 | Lambda / Lambdabar | `particle_3122_*`, `particle_-3122_*` |
| 3312 / -3312 | Xi- / Xibar+ | `particle_3312_*`, `particle_-3312_*` |
| 3334 / -3334 | Omega- / Omegabar+ | `particle_3334_*`, `particle_-3334_*` |
| 333 | phi(1020) | `particle_333_*` |

Each species has two datasets:

```
particle_<pid>_vndata_diff_y_-30_30_boostinv.dat   pT-differential   (41, 13)
particle_<pid>_vndata_y_-30_30_boostinv.dat        pT-integrated     ( 7,  5)
```

The `-30_30` in the name is a stale label from the boost-invariant patch; the
yield is the **no-cut** boost-invariant estimator. Do not read an acceptance out
of the filename.

## 3. pT binning (fixed and analytic)

```
dpT      = (pT_max - pT_min) / npT
bin i    = [ pT_min + i*dpT , pT_min + (i+1)*dpT )
centre_i =   pT_min + (i + 0.5)*dpT
```

This campaign: `npT = 41`, `pT_min = 0.05 GeV`, `pT_max = 4.05 GeV`, so
`dpT = 0.097561 GeV` and the first centres are 0.0988, 0.1963, 0.2939, ...

> **Trap.** Column 0 of the differential table is the *mean pT of the particles
> that landed in that bin in that event*, not the bin centre. Use the analytic
> edges above. (It deviates from the centre by ~0.004 GeV on average.)

## 4. Differential table — shape (41, 13)

| col | meaning |
|---|---|
| 0 | mean pT of the particles in this bin, this event (see trap) |
| 1 | `EdN/dp^3` — the invariant yield as written by the toolkit |
| 2, 3 | `Q1_real`, `Q1_imag` |
| 4, 5 | `Q2_real`, `Q2_imag` |
| 6, 7 | `Q3_real`, `Q3_imag` |
| 8, 9 | `Q4_real`, `Q4_imag` |
| 10, 11 | `Q5_real`, `Q5_imag` |
| 12 | `total_NpT` — number of particles of this species in this pT bin |

Notes:

* The $Q_n$ entries are **per-particle averages within the bin**, i.e. $v_n(p_T)$
  directly: `v_n = hypot(cols[2n], cols[2n+1])`.
* Identified species are capped at **n <= 5** (13 columns), whatever
  `order_max` says.
* No statistical-error columns are written. Estimate them from `total_NpT`:
  `sigma_vn ~ sqrt((1 - v_n**2) / (2*N))` for a single event (and better by
  combining events as in section 6).

## 5. Yields — the two consistent routes

The count column is the safest basis. Two identities hold exactly in this
campaign (verified across events and species):

```
sum_bins(N_pT) / n_samples  =  10.0 * dN/dy        <-- boost-invariant width = 10
sum_bins(2*pi * mean_pT * dpT * col1) = 2.222 * dN/dy
```

So, per event and per pT bin:

```python
n_samples = int(g['particle_211_vndata_y_-30_30_boostinv.dat'][6, 2])   # row n=99, col 2
dN_dy_bin = d[:, 12] / n_samples / 10.0        # per unit rapidity, per pT bin
dN_dy_tot = g['particle_211_vndata_y_-30_30_boostinv.dat'][0, 1]        # integrated row
```

Use `d[:, 12] / n_samples / 10.0`. Column 1 (`EdN/dp^3`) is the toolkit's internal
normalisation (it carries a factor 2.222 relative to the count route); it is
correct in shape but is best avoided unless you reproduce the exact definition in
`FLOW_OUTPUT_FORMAT.md` section 2.

The width 10 is `y_RB - y_LB` for this campaign's boost-invariant estimator. It
is a property of the run: re-derive it with the identity above if the y range
ever changes.

## 6. Integrated table — shape (7, 5)

| row | col 0 | col 1 | col 2 | col 3 | col 4 |
|---|---|---|---|---|---|
| `n = 0` | 0 | `dN/dy` per sample | err | `<pT>` | err |
| `n = 1..5` | n | `Qn_real` | err | `Qn_imag` | err |
| `99` | 99 | `total_N` | **`n_samples`** | 0 | 0 |

The `n = 99` row is the bookkeeping row: **column 2 is the number of iSS
resamplings for that event**. It varies event to event (here 260, 480, 15,550,
...), so always read it per event — never assume a global sample count.

## 7. Events, samples, and centrality

* Number of events in a merged file = number of groups.
* The drawn-event record is in `csv.tgz`
  (`events_drawn_<block>.csv` with columns
  `event_id,b,b_max,b_over_bmax,mult,status,seed_add`). It lists **every drawn
  event**, including the ones that never produced results: `mult = 0` means the
  two nuclei missed, and a missing event file with `mult > 0` means the
  freeze-out surface was empty. Use it for centrality percentiles and for the
  inefficiency denominator.
* A physical event can have many samples (`n_samples`); yields and $Q_n$ are
  already per-sample/pooled inside a table, so do not divide by the sample count
  a second time when using the integrated rows.

## 8. Minimal reader

```python
import h5py, numpy as np

pT_min, pT_max, npT = 0.05, 4.05, 41
dpT = (pT_max - pT_min) / npT
centres = pT_min + (np.arange(npT) + 0.5) * dpT

def read_dp(path, pid="211"):
    """Return per-event (N, Qn) for one species from one merged design point."""
    out = []
    with h5py.File(path, "r") as f:
        for ev in f.keys():
            g = f[ev]
            d = g[f"particle_{pid}_vndata_diff_y_-30_30_boostinv.dat"][...]
            i = g[f"particle_{pid}_vndata_y_-30_30_boostinv.dat"][...]
            n_s = int(i[6, 2])
            N = d[:, 12] / n_s                      # per-sample count per pT bin
            vn = {n: np.hypot(d[:, 2*n], d[:, 2*n+1]) for n in range(1, 6)}
            out.append(dict(event=ev, n_samples=n_s, N=N, vn=vn,
                            dNdy=i[0, 1], meanpT=i[0, 3]))
    return centres, out

centres, evs = read_dp("merged/dp0001/dp0001.h5", "211")
# event-averaged v2(pT), weighted by N so rare bins do not dominate
N = np.array([e["N"] for e in evs])                 # (events, npT)
v2 = np.array([e["vn"][2] for e in evs])
v2_avg = (v2 * N).sum(0) / N.sum(0)
```

When averaging $v_n$ over events, weight by `N` per bin (as above) and quote the
event-to-event scatter as the uncertainty — that fluctuation is larger than the
per-event statistical error and is the relevant one for observables.

## 9. Traps worth remembering

1. Column 0 of the differential table is the event's mean pT in the bin, not the
   bin centre.
2. The `-30_30` in the filenames is stale; the yield is the no-cut
   boost-invariant estimator, normalised by width 10.
3. `n_samples` differs per event and per species? No — per event (same for all
   species), but it varies strongly between events.
4. Identified species have **n <= 5**; only the (pruned) `9999` reference carries
   higher harmonics.
5. Rare species (phi, Omega) can be exactly zero in an event: `dN/dy = 0` and
   all $Q_n$ = 0 there, with `total_N = 0`. Do not divide by zero when forming
   ratios.
6. The merged file contains only events that produced results; use
   `csv.tgz` for the drawn set.

For anything beyond these five points — the eta-vs-y Jacobian, the
`9999`/`99999` references, rapidity-resolved tables, or the exact source-level
definitions — see `FLOW_OUTPUT_FORMAT.md`.
