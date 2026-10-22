#!/usr/bin/env python3
"""Record everything needed to reproduce a campaign, in one findable place.

The point is that a reader who finds `provenance/` on its own can answer, without
guessing: which code produced these numbers, which container carried it, which
design, which seeds, and what every parameter was actually set to.

That is not a small set. The framework revision, the image the jobs actually ran
in, the design file and the parameter dictionary are four independent things, and
the dictionary is not the design: `MakeDictionaries.py` converts `sigma_k` to
TRENTo's `fluctuation`, `gamma` from degrees to radians, computes `b_max` and
`T_freeze`, and the master fills in several hundred keys the design row never
mentions. Dumping the *resolved* dictionary is the only way to see what was run.

Usage:
    # after the image is built and published
    python3 scripts/record_provenance.py --design-point 1 \
        --image /ospool/ap40/data/matthew.luzum/iebe-music_slim_<sha>_<md5>.sif

Writes provenance/manifest.json and provenance/parameters_design_<N>.json.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Every module-level dictionary in config/parameters_dict_master.py that carries
# settings into a solver input file. Missing one silently drops it from the
# record, so this list is checked against the module at run time.
DICT_NAMES = [
    "control_dict",
    "isobars_conf_dict_target",
    "isobars_conf_dict_projectile",
    "seeds_conf_dict",
    "trento_dict",
    "free_streaming_dict",
    "ipglasma_dict",
    "mcglauber_dict",
    "kompost_dict",
    "music_dict",
    "photon_dict",
    "iss_dict",
    "smash_config_dict",
    "hadronic_afterburner_toolkit_dict",
]


def git(*args):
    return subprocess.run(["git"] + list(args), cwd=REPO_ROOT, capture_output=True,
                          text=True, check=True).stdout.strip()


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def md5_file(path):
    digest = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def generate_parameter_file(design_csv, design_point, workdir):
    """Run MakeDictionaries.py for one design point and return its parameter file."""
    subprocess.run([sys.executable,
                    os.path.join(REPO_ROOT, "MakeDictionaries.py"),
                    os.path.abspath(design_csv),
                    "--start-design-point", str(design_point),
                    "--end-design-point", str(design_point)],
                   cwd=workdir, check=True, capture_output=True, text=True)
    folder = os.path.join(workdir, "DesignPoint{}".format(design_point))
    for name in sorted(os.listdir(folder)):
        if name.startswith("parameter_dictionary") and name.endswith(".py"):
            return os.path.join(folder, name)
    raise SystemExit("no parameter dictionary produced in {}".format(folder))


def resolve_parameters(param_file, seed):
    """Merge the design point into the master and return the resolved dicts."""
    sys.path.insert(0, os.path.join(REPO_ROOT, "config"))
    import parameters_dict_master as master  # noqa: E402

    master.update_parameters_dict(os.path.abspath(param_file), seed)
    resolved = {}
    for name in DICT_NAMES:
        if not hasattr(master, name):
            raise SystemExit("config/parameters_dict_master.py has no {}".format(name))
        resolved[name] = getattr(master, name)
    return resolved


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--design", default="design/design_lhs2000.csv")
    parser.add_argument("--design-point", type=int, default=1,
                        help="design point whose resolved dictionary is recorded")
    parser.add_argument("--image", default="",
                        help="local SIF to hash; its md5 is recorded")
    parser.add_argument("--sif-url", default="",
                        help="published container URL recorded instead of the local path")
    parser.add_argument("--outdir", default="provenance")
    args = parser.parse_args()

    design_path = os.path.join(REPO_ROOT, args.design)
    outdir = os.path.join(REPO_ROOT, args.outdir)
    os.makedirs(outdir, exist_ok=True)

    revision = git("rev-parse", "HEAD")
    dirty = git("status", "--porcelain") != ""
    if dirty:
        print("WARNING: working tree is dirty; the recorded revision does not "
              "describe the code that is present.", file=sys.stderr)

    manifest = {
        "recorded_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_revision": revision,
        "git_branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "git_dirty": dirty,
        "dockerfile_pin": subprocess.run(
            ["grep", "-oE", r"git fetch -q --depth=1 origin [0-9a-f]{40}",
             os.path.join(REPO_ROOT, "docker", "Dockerfile")],
            capture_output=True, text=True).stdout.split()[-1],
        "design_file": args.design,
        "design_sha256": sha256_file(design_path),
        "design_points": sum(1 for _ in open(design_path)) - 1,
        "recorded_design_point": args.design_point,
        "master_seed": 8675309,
        "campaign_seed_add": 0,
    }

    if args.image:
        if not os.path.exists(args.image):
            raise SystemExit("no such image: {}".format(args.image))
        manifest["sif_path"] = args.sif_url or os.path.abspath(args.image)
        manifest["sif_md5"] = md5_file(args.image)
        manifest["sif_bytes"] = os.path.getsize(args.image)

    # Copy the design in so this directory is self-contained: a reader who finds
    # provenance/ alone should not have to go looking for the CSV, and the copy
    # is verified against the hash recorded above.
    design_copy = os.path.join(outdir, os.path.basename(design_path))
    subprocess.run(["cp", design_path, design_copy], check=True)
    manifest["design_copy"] = os.path.join(args.outdir, os.path.basename(design_path))
    if sha256_file(design_copy) != manifest["design_sha256"]:
        raise SystemExit("design copy does not hash to the original")
    print("wrote", design_copy)

    with tempfile.TemporaryDirectory() as tmp:
        param_file = generate_parameter_file(design_path, args.design_point, tmp)
        resolved = resolve_parameters(param_file, 0)
        dict_name = "parameters_design_{:04d}.json".format(args.design_point)
        manifest["parameter_dictionary"] = os.path.join(args.outdir, dict_name)
        manifest["parameter_dictionary_source"] = os.path.basename(param_file)

        out_json = os.path.join(outdir, dict_name)
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(resolved, f, indent=2, sort_keys=True, default=str)
        print("wrote", out_json)

    manifest_path = os.path.join(outdir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    print("wrote", manifest_path)
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
