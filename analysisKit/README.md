# analysisKit — quick pipeline

This directory contains tools to extract Qn vectors from `spvn_results_*.h5` files and run ensemble analyses.

**Read [`FLOW_OUTPUT_FORMAT.md`](FLOW_OUTPUT_FORMAT.md) before writing any extraction or
analysis code.** It is the data dictionary for what is actually inside the HDF5: the column
layout of every `particle_*_vndata*` table, the analytic pT bin edges, which species are
covered, which files are pruned, and the resample count. Two things in there are
counter-intuitive and will silently corrupt results if you assume otherwise — column 0 is
*not* the bin centre, and the rapidity in the filename is *not* the rapidity of the data.

Recommended pipeline (example):

1. Extract per-run pickles from each HDF5 `spvn_results_*.h5` using `fetch_Qnch_from_hdf5.py`.
2. Merge the produced pickles using `combine_pickle_files.py` to create `combined.pkl`.
3. Run the analyzer scripts on the merged pickle, e.g. `analyze_vnpT.py`, `analyze_vnch_inte.py`, `analyze_rapiditydistributions.py`.

Quick commands (replace paths as needed):

```bash
# extract pickles (one per h5 file)
python3 fetch_Qnch_from_hdf5.py /path/to/event_X/EVENT_RESULTS_X/spvn_results_X.h5
# rename/move the generated QnVectors.pickle so it doesn't get overwritten
mv QnVectors.pickle /path/to/out/QnVectors_runX.pickle

# merge pickles
cd /path/to/out
python3 ../combine_pickle_files.py QnVectors_run1.pickle QnVectors_run2.pickle QnVectors_run3.pickle
# this writes combined.pkl in the current directory

# analysis examples
python3 ../analyze_vnpT.py combined.pkl
python3 ../analyze_vnch_inte.py combined.pkl
python3 ../analyze_rapiditydistributions.py combined.pkl
python3 ../analyze_pTfluct.py combined.pkl
```

Convenience: a template script `run_analysis_pipeline.sh` is included to automate the extraction + merge + a few default analyzers. Edit the variables at the top to match your layout.

If you want, run the script with `--help` or open it to set the desired analyzers.
