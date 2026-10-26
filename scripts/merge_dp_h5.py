#!/usr/bin/env python3
"""Merge per-event spvn_results_*.h5 files into one h5, by h5py copy.

Same output as combine_multiple_hdf5.py (one top-level group per event, named
after the global event id, with its datasets) but done in one process: the
h5copy-per-event approach spawns ~10,000 subprocesses for a 10,000-event
design point.

Usage: merge_dp_h5.py SOURCE_DIR OUTPUT_H5
"""
import glob
import os
import sys

import h5py


def merge(src_dir, out_path):
    files = sorted(glob.glob(os.path.join(src_dir, "spvn_results_*.h5")),
                   key=lambda p: int(os.path.basename(p).split("_")[-1].split(".")[0]))
    if not files:
        print("no input files in", src_dir)
        return 1
    with h5py.File(out_path, "w") as out:
        for i, path in enumerate(files):
            with h5py.File(path, "r") as src:
                for gname in src.keys():
                    if gname in out:
                        # duplicate event id (re-run overlap): keep the first
                        continue
                    sg = src[gname]
                    dg = out.create_group(gname)
                    for dname in sg.keys():
                        obj = sg[dname]
                        if isinstance(obj, h5py.Dataset):
                            dg.create_dataset(dname, data=obj[()])
            if (i + 1) % 500 == 0:
                print("  merged %d/%d events" % (i + 1, len(files)), flush=True)
    print("merged %d events -> %s" % (len(files), out_path))
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    sys.exit(merge(sys.argv[1], sys.argv[2]))
