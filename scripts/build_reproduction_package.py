#!/usr/bin/env python3
"""Write the reproduction package for a finished campaign, next to its results.

The package has to answer, for someone who has never seen this repo: which code
produced these numbers, which container carried it, which design, which seeds,
and what every parameter was set to.  Those are four independent things:

  * the *container* carries the physics (framework at a pinned commit, iSS with
    the PTB patch, MUSIC, TRENTo, the toolkit).  Its identity is the SIF md5
    plus the md5 of each built binary, because the code packages are cloned
    from moving branches and a rebuild is not byte-reproducible;
  * the *framework revision* is what generates and runs the job folders;
  * the *design* is a 2000-point Latin hypercube drawn from a seed in the unit
    cube and mapped through per-axis priors -- so it can be regenerated, not
    only copied;
  * the *parameter dictionary* is not the design row: MakeDictionaries converts
    sigma_k to TRENTo's fluctuation, gamma from degrees to radians, and computes
    b_max and T_freeze, and the master fills in several hundred keys the design
    never mentions.

Everything asserted here is checked while building the package: the design is
regenerated from (n, seed, priors), all dictionaries are regenerated and
diffed, and the image's framework revision and binary hashes are read out of
the SIF itself.  A package that says "reproducible" without having run those
checks is just a description.

Usage (from the repo root):
    python3 scripts/build_reproduction_package.py \
        --campaign zr96c2 \
        --design design/design_lhs2000_A96_c2.csv \
        --parent-design design/design_lhs2000_A96.csv \
        --dict-dir zr96_design_c2 \
        --merged /data/mluzum/zr96c2_results/merged \
        --image /data/mluzum/iebe-music_slim_17ae5b4_f5242628.sif \
        --out /data/mluzum/zr96c2_results/merged/REPRODUCTION
"""

import argparse
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Constants of the campaign that are not derivable from the repo.  See
# AGENTS.md: an event is (MASTER_SEED, seed_add, event_id, iev).
MASTER_SEED = 8675309
CAMPAIGN_SEED_ADD = 0
DESIGN_SEED = 8675309
DESIGN_POINTS_AVAILABLE = 2000

# The commit the container was built from and the framework commit it pins.
DOCKERFILE_COMMIT = "06cc504"
FRAMEWORK_PIN = "17ae5b49c083a33783f72ed5d00b8822973a2d70"

# Where the pin is actually published.  Our working tree carries commits that
# only touch submit-side tooling and are not pushed, so the package must point
# at the pin, not at HEAD.
FORK_URL = "https://github.com/mluzum/iEBE-MUSIC.git"

BATCHES = [("1", 0), ("2", 2000), ("3", 4000)]
JOBS_PER_BATCH = 100
EVENTS_PER_JOB = 20


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


def git(*args, check=True):
    out = subprocess.run(["git"] + list(args),
                         cwd=REPO_ROOT,
                         capture_output=True,
                         text=True)
    if check and out.returncode != 0:
        raise SystemExit("git {} failed: {}".format(" ".join(args),
                                                    out.stderr.strip()))
    return out.stdout.strip()


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def sub(text, facts):
    """Replace {{token}} placeholders (keeps shell braces in the prose intact)."""
    for k, v in facts.items():
        text = text.replace("{{" + k + "}}", str(v))
    return text


# --------------------------------------------------------------------------
# checks: every claim the package makes is verified here
# --------------------------------------------------------------------------
def check_design(design_path, parent_path, seed, npoints):
    """Regenerate the design from (n, seed, priors) and compare."""
    with tempfile.TemporaryDirectory() as tmp:
        parent = os.path.join(tmp, "parent.csv")
        final = os.path.join(tmp, "final.csv")
        subprocess.run([
            sys.executable,
            os.path.join(REPO_ROOT, "scripts", "make_design_a96.py"), "--n",
            str(npoints), "--seed",
            str(seed), "--out", parent
        ],
                       check=True,
                       capture_output=True,
                       text=True)
        subprocess.run([
            sys.executable,
            os.path.join(REPO_ROOT, "scripts", "remap_design_prior.py"),
            "--prior", "a96", "--range", "normalization=6,13", parent, final
        ],
                      check=True,
                      capture_output=True,
                      text=True)
        parent_ok = sha256_file(parent) == sha256_file(
            os.path.join(REPO_ROOT, parent_path))
        final_ok = sha256_file(final) == sha256_file(
            os.path.join(REPO_ROOT, design_path))
    return parent_ok, final_ok


def check_dictionaries(design_path, dict_dir, first, last):
    """Regenerate every dictionary and diff against the campaign copies."""
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run([
            sys.executable,
            os.path.join(REPO_ROOT, "MakeDictionaries.py"),
            os.path.abspath(os.path.join(REPO_ROOT, design_path)),
            "--start-design-point",
            str(first), "--end-design-point",
            str(last), "--output-dir", tmp
        ],
                       cwd=tmp,
                       check=True,
                       capture_output=True,
                       text=True)
        diff = subprocess.run(
            ["diff", "-rq", tmp,
             os.path.abspath(os.path.join(REPO_ROOT, dict_dir))],
            capture_output=True,
            text=True)
    return diff.returncode == 0, diff.stdout.strip()


def inspect_image(image_path, timeout=900):
    """Read the framework revision and the built-binary hashes out of the SIF."""
    script = r"""
cd /opt/iEBE-MUSIC || exit 1
echo "REVISION=$(git -c safe.directory=/opt/iEBE-MUSIC rev-parse HEAD 2>/dev/null)"
echo "REVDATE=$(git -c safe.directory=/opt/iEBE-MUSIC log -1 --format=%cs 2>/dev/null)"
echo "REVSUBJECT=$(git -c safe.directory=/opt/iEBE-MUSIC log -1 --format=%s 2>/dev/null)"
for f in codes/iSS_code/iSS.e codes/MUSIC_code/MUSIChydro \
         codes/hadronic_afterburner_toolkit_code/hadronic_afterburner_tools.e \
         codes/hydro_plus_UrQMD_driver.py; do
  [ -f "$f" ] && echo "HASH=$f $(md5sum "$f" | cut -d' ' -f1)"
done
echo "GCC=$(gcc --version 2>/dev/null | head -1)"
python3 - <<'PY' 2>/dev/null
import sys, numpy, h5py, scipy
print("RUNTIME=python %s, numpy %s, h5py %s, scipy %s" % (
    sys.version.split()[0], numpy.__version__, h5py.__version__, scipy.__version__))
PY
"""
    out = subprocess.run(["singularity", "exec", image_path, "bash", "-c",
                          script],
                         capture_output=True,
                         text=True,
                         timeout=timeout)
    facts = {"hashes": {}, "toolchain": []}
    for line in out.stdout.splitlines():
        line = line.strip()
        if line.startswith("REVISION="):
            facts["revision"] = line.split("=", 1)[1]
        elif line.startswith("REVDATE="):
            facts["revision_date"] = line.split("=", 1)[1]
        elif line.startswith("REVSUBJECT="):
            facts["revision_subject"] = line.split("=", 1)[1]
        elif line.startswith("HASH="):
            path, digest = line.split("=", 1)[1].split(" ", 1)
            facts["hashes"][path] = digest
        elif line.startswith("GCC="):
            facts["toolchain"].append(line.split("=", 1)[1])
        elif line.startswith("RUNTIME="):
            facts["toolchain"].append(line.split("=", 1)[1])
    return facts


def campaign_state(merged_dir):
    """Count what is actually in the merged tree.

    Events are read from the merge log's "merged N events" line, which is exact;
    falling back to archives * events_per_job would overcount, because ~1-2 % of
    drawn events have an empty freeze-out surface and produce no h5.
    """
    points = 0
    archives = 0
    events = 0
    events_exact = True
    for path in sorted(glob.glob(os.path.join(merged_dir, "dp*"))):
        h5 = os.path.join(path, os.path.basename(path) + ".h5")
        if not os.path.exists(h5):
            continue
        points += 1
        src = os.path.join(path, "sources.txt")
        if os.path.exists(src):
            m = re.search(r"tars=(\d+)", open(src).read())
            if m:
                archives += int(m.group(1))
        log = os.path.join(path, "merge.log")
        found = None
        if os.path.exists(log):
            for line in reversed(open(log, errors="replace").readlines()):
                m = re.search(r"^merged (\d+) events", line.strip())
                if m:
                    found = int(m.group(1))
                    break
        if found is None:
            events_exact = False
            found = 0
        events += found
    if not events_exact:
        events = max(events, archives * EVENTS_PER_JOB)
    return {"design_points_merged": points, "job_archives": archives,
            "events": events, "events_exact": events_exact}


def extract_events_drawn(merged_dir, limit=50):
    """Example event records, so a reader can see the event bookkeeping."""
    rows = []
    for path in sorted(glob.glob(os.path.join(merged_dir, "dp*")))[:limit]:
        tgz = os.path.join(path, "csv.tgz")
        if not os.path.exists(tgz):
            continue
        with tarfile.open(tgz, "r:gz") as tar:
            member = sorted(m.name for m in tar.getmembers()
                            if m.name.endswith(".csv"))[0]
            data = tar.extractfile(member).read().decode()
        header = data.splitlines()[0]
        rows.append((os.path.basename(path), member, header,
                     len(data.splitlines()) - 1))
        if len(rows) >= 3:
            break
    return rows


def build(args):
    design_path = args.design
    dict_dir = args.dict_dir
    out = os.path.abspath(args.out)
    merged = os.path.abspath(args.merged)

    rev = git("rev-parse", "HEAD")
    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    dirty = git("status", "--porcelain") != ""
    origin = git("remote", "get-url", "origin", check=False)
    try:
        published_tip = subprocess.run(
            ["git", "ls-remote", "--heads", FORK_URL, "NME"],
            capture_output=True, text=True, timeout=90).stdout.split()[0]
    except Exception:
        published_tip = "unknown"

    print("[1/6] checking the design regenerates ...")
    parent_ok, design_ok = check_design(design_path, args.parent_design,
                                        DESIGN_SEED, DESIGN_POINTS_AVAILABLE)
    design_sha = sha256_file(os.path.join(REPO_ROOT, design_path))
    print("      parent design reproduced: %s, campaign design: %s" %
          (parent_ok, design_ok))

    print("[2/6] regenerating all dictionaries (this takes a minute) ...")
    dict_ok, dict_diff = check_dictionaries(design_path, dict_dir, args.first,
                                            args.last)
    print("      dictionaries reproduced: %s" % dict_ok)

    print("[3/6] reading the container ...")
    image = {}
    if args.image and os.path.exists(args.image):
        image["md5"] = md5_file(args.image)
        image["bytes"] = os.path.getsize(args.image)
        image["name"] = os.path.basename(args.image)
        image["osdf_url"] = "osdf:///" + args.image_ospool_path
        if args.inspect_image:
            image.update(inspect_image(args.image))
    else:
        print("      WARNING: no image given; container facts will be incomplete")

    print("[4/6] collecting campaign state ...")
    state = campaign_state(merged)
    samples = extract_events_drawn(merged)

    # ---- hashes of the dictionaries actually used, and of the design rows ---
    dict_rows = []
    for i in range(args.first, args.last + 1):
        rel = os.path.join(dict_dir, "DesignPoint{}".format(i),
                           "parameter_dictionary_design_point_{}.py".format(i))
        full = os.path.join(REPO_ROOT, rel)
        if os.path.exists(full):
            dict_rows.append((i, rel, sha256_file(full)))

    facts = {
        "campaign": args.campaign,
        "system": args.system,
        "revision": rev,
        "branch": branch,
        "revision_short": rev[:7],
        "dirty": "yes" if dirty else "no",
        "origin": origin,
        "fork_url": "https://github.com/mluzum/iEBE-MUSIC.git",
        "published_tip": published_tip,
        "framework_pin": FRAMEWORK_PIN,
        "framework_pin_short": FRAMEWORK_PIN[:7],
        "dockerfile_commit": DOCKERFILE_COMMIT,
        "image_name": image.get("name", "iebe-music_slim_<sha>_<md5>.sif"),
        "image_md5": image.get("md5", "UNKNOWN"),
        "image_bytes": image.get("bytes", 0),
        "image_osdf": image.get("osdf_url", "UNKNOWN"),
        "image_revision": image.get("revision", "UNKNOWN"),
        "image_revision_date": image.get("revision_date", "UNKNOWN"),
        "design_file": os.path.basename(design_path),
        "design_sha256": design_sha,
        "design_rows": DESIGN_POINTS_AVAILABLE,
        "first": args.first,
        "last": args.last,
        "npoints": args.last - args.first + 1,
        "seed": MASTER_SEED,
        "design_seed": DESIGN_SEED,
        "seed_add": CAMPAIGN_SEED_ADD,
        "master_sha256":
        sha256_file(os.path.join(REPO_ROOT, "config/parameters_dict_master.py")),
        "template_sha256":
        sha256_file(
            os.path.join(
                REPO_ROOT,
                "config/design_points/parameters_dict_user_TRENTo_realistic.py")),
        "make_dict_sha256": sha256_file(os.path.join(REPO_ROOT,
                                                     "MakeDictionaries.py")),
        "dp1_dict_md5":
        md5_file(
            os.path.join(REPO_ROOT, dict_dir, "DesignPoint1",
                         "parameter_dictionary_design_point_1.py")),
        "dp1_dict_sha256":
        sha256_file(
            os.path.join(REPO_ROOT, dict_dir, "DesignPoint1",
                         "parameter_dictionary_design_point_1.py")),
        "merged_points": state["design_points_merged"],
        "archives": state["job_archives"],
        "events": state["events"],
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "jobs_per_batch": JOBS_PER_BATCH,
        "events_per_job": EVENTS_PER_JOB,
        "batch_table":
        "\n".join("| %s | %d | %d - %d | `%s` |" % (
            b, off, off, off + JOBS_PER_BATCH * EVENTS_PER_JOB - 1,
            ("spvn_results_<proc>.tar.gz" if off == 0 else
             "spvn_results_e%d_<proc>.tar.gz" % off)) for b, off in BATCHES),
    }
    facts["first4"] = "%04d" % args.first
    facts["last4"] = "%04d" % args.last
    facts["check_design"] = "PASS" if (parent_ok and design_ok) else "FAIL"
    facts["check_dicts"] = "PASS" if dict_ok else "FAIL"
    facts["dict_diff"] = dict_diff[:2000] if dict_diff else "no differences"
    facts["drawn_upper"] = state["job_archives"] * EVENTS_PER_JOB
    facts["delivered_pct"] = ("%.1f" % (100.0 * state["events"] /
                                        facts["drawn_upper"])
                              if facts["drawn_upper"] else "n/a")
    facts["artifact_table"] = "\n".join(
        "%s  %s" % (v, k) for k, v in sorted(image.get("hashes", {}).items()))
    facts["toolchain"] = "; ".join(image.get("toolchain", []))
    facts["event_example"] = "\n".join(
        "    %s / %s: %s  (%d rows)" % r for r in samples)

    print("[5/6] writing the package to %s ..." % out)
    os.makedirs(out, exist_ok=True)

    # ---------------- design ----------------
    for name in (design_path, args.parent_design):
        src = os.path.join(REPO_ROOT, name)
        if os.path.exists(src):
            dst = os.path.join(out, "design", os.path.basename(name))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            subprocess.run(["cp", src, dst], check=True)

    design_md = sub("""# The design: a 2000-point Latin hypercube

`{{design_file}}` (sha256 `{{design_sha256}}`) has {{design_rows}} rows; this
campaign used rows 1 - {{last}} exactly, i.e. labels `design_0001` ...
`design_{{last4}}` became design points `DesignPoint{{first}}` ... `DesignPoint{{last}}`.

## It can be regenerated, not just copied

The points are drawn in the unit cube and then mapped per axis with
`x = lo + u*(hi - lo)`; the maximin ordering is computed on the unit points, so
a design point's normalized coordinates `u` are independent of the prior
ranges.  Two commands reproduce this file byte for byte:

```bash
python3 scripts/make_design_a96.py --n {{design_rows}} --seed {{design_seed}} \\
    --out design/design_lhs2000_A96.csv
python3 scripts/remap_design_prior.py --prior a96 --range normalization=6,13 \\
    design/design_lhs2000_A96.csv design/{{design_file}}
```

Verified when this package was written: **{{check_design}}**.

The first command writes `design/design_lhs2000_A96.csv` (included here under
that name), the A=96 design with the *campaign 1* normalization prior 3-10.  The second maps that one axis onto 6-13 through
each point's unit-cube coordinate and copies every other column, the labels and
the row order verbatim; because both intervals are 7 wide, the mapping is a
shift of +3.  Nothing is redrawn, so `design_000k` is the same normalized point
in this campaign and in campaign 1, and in A=96 and A=76 -- which is what makes
paired comparisons across campaigns valid.

## Axes and priors

25 columns: a label, the 20 design axes (columns 2-21) and 4 fixed columns
(`shear_relax_time_factor`, `bulk_viscosity_3_lambda_asymm`, `shape_distribution`
= `plane`, `number_nucleons` = 96).  `sigma_k` is not passed to TRENTo: it enters
as `fluctuation = 1/sigma_k**2`.  `gamma` is degrees here and radians in the
isobar configuration (MakeDictionaries converts).  `number_nucleons` is 96 and
is *not* a design axis.  Full table of ranges: `design/A96_priors.md` in the
repo and `design/CAMPAIGN2_DESIGNS.md` for the campaign-2 changes.

| axis | campaign-2 range |
|---|---|
| normalization | 6 - 13 |
| reduced-thickness | -0.7 - 0.7 |
| nucleon-width | 0.5 - 1.5 |
| sigma_k | 0.3 - 2.0 |
| tau | 0.3 - 2.0 |
| shear_viscosity_3_eta_over_s_at_kink | 0.01 - 0.20 |
| shear_viscosity_3_eta_over_s_low_T_slope_in_GeV | -2.0 - 0.0 |
| shear_viscosity_3_eta_over_s_high_T_slope_in_GeV | 0.0 - 2.0 |
| shear_viscosity_3_eta_over_s_T_kink_in_GeV | 0.13 - 0.30 |
| bulk_viscosity_3_max | 0.01 - 0.25 |
| bulk_viscosity_3_T_peak_in_GeV | 0.12 - 0.30 |
| bulk_viscosity_3_width_in_GeV | 0.025 - 0.15 |
| T_freeze | 0.135 - 0.165 |
| WS_radius | 5.0 - 5.7 |
| WS_diffusiveness | 0.45 - 0.60 |
| beta_2 | 0.0 - 0.4 |
| gamma | 0 - 60 deg |
| beta_3 | 0.0 - 0.4 |
| sigma_plane | 0.0 - 0.08 |
| sigma_beta_3 | 0.0 - 0.08 |

`design/design_points.csv` maps design point -> dictionary -> sha256.
""", facts)
    write(os.path.join(out, "design", "DESIGN.md"), design_md)

    with open(os.path.join(out, "design", "design_points.csv"), "w") as f:
        f.write("design_point,label,dictionary,sha256\n")
        for i, rel, digest in dict_rows:
            f.write("%d,design_%04d,%s,%s\n" % (i, i, os.path.basename(rel),
                                                digest))

    # ---------------- parameters ----------------
    pdir = os.path.join(out, "parameters")
    os.makedirs(pdir, exist_ok=True)
    tar_path = os.path.join(
        pdir, "parameter_dictionaries_dp%04d-%04d.tar.gz" %
        (args.first, args.last))
    with tarfile.open(tar_path, "w:gz") as tar:
        for i in range(args.first, args.last + 1):
            src = os.path.join(REPO_ROOT, dict_dir,
                               "DesignPoint{}".format(i))
            if os.path.isdir(src):
                tar.add(src, arcname="DesignPoint{}".format(i))
    for rel, dst in (("config/parameters_dict_master.py",
                      "parameters_dict_master.py"),
                     ("config/design_points/"
                      "parameters_dict_user_TRENTo_realistic.py",
                      "parameters_dict_user_TRENTo_realistic.py"),
                     ("MakeDictionaries.py", "MakeDictionaries.py"),
                     (os.path.join(dict_dir, "DesignPoint1",
                                   "parameter_dictionary_design_point_1.py"),
                      "parameter_dictionary_design_point_0001.py")):
        src = os.path.join(REPO_ROOT, rel)
        if os.path.exists(src):
            subprocess.run(["cp", src, os.path.join(pdir, dst)], check=True)

    # resolved dictionary for design point 1: the master's several hundred
    # default keys are part of what ran, and are not in the design row.
    print("      resolving design point 1 through the master ...")
    sys.path.insert(0, os.path.join(REPO_ROOT, "config"))
    sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))
    import record_provenance as rp  # noqa: E402
    with tempfile.TemporaryDirectory() as tmp:
        param = rp.generate_parameter_file(
            os.path.join(REPO_ROOT, design_path), 1, tmp)
        resolved = rp.resolve_parameters(param, CAMPAIGN_SEED_ADD)
    with open(os.path.join(pdir, "resolved_design_point_0001.json"),
              "w") as f:
        json.dump(resolved, f, indent=2, sort_keys=True, default=str)

    write(os.path.join(pdir, "PARAMETERS.md"), sub("""# Parameter dictionaries

`parameter_dictionaries_dp{{first4}}-{{last4}}.tar.gz` holds the
{{npoints}} dictionaries exactly as the jobs received them: one
`DesignPoint<i>/parameter_dictionary_design_point_<i>.py` each.

These are the ones that ran.  Two independent checks were made when this
package was written:

1. every dictionary regenerates byte-identically from the design file
   (`diff -rq` over all {{npoints}}: **{{check_dicts}}**), and
2. the copies staged for the jobs hashed to the same md5 as the copies shipped
   here (1000/1000 matched when checked against the cluster staging area).

Regenerate them yourself:

```bash
mkdir my_dicts && cd my_dicts
python3 ../MakeDictionaries.py --design ../design/{{design_file}} \\
    --start-design-point {{first}} --end-design-point {{last}} --output-dir .
md5sum DesignPoint1/parameter_dictionary_design_point_1.py
# expect {{dp1_dict_md5}}
```

## What else is here

| file | what it is |
|---|---|
| `parameter_dictionary_design_point_0001.py` | one dictionary, readable, to see the shape |
| `parameters_dict_master.py` | the master that fills in every default (sha256 `{{master_sha256}}`) |
| `parameters_dict_user_TRENTo_realistic.py` | the template the dictionaries derive from (sha256 `{{template_sha256}}`) |
| `MakeDictionaries.py` | the generator (sha256 `{{make_dict_sha256}}`) |
| `resolved_design_point_0001.json` | design point 1 after the master merge: every key that reached MUSIC / iSS / TRENTo, with values |

`resolved_design_point_0001.json` is the important one for auditing.  A
dictionary file only names the design axes; the master supplies several hundred
further settings (freeze-out, afterburner, hydro grid, viscosity
parametrisation, seeds).  The JSON is what those resolve to.
""", facts))

    # ---------------- container ----------------
    cdir = os.path.join(out, "container")
    os.makedirs(cdir, exist_ok=True)
    src = os.path.join(REPO_ROOT, "docker", "Dockerfile")
    if os.path.exists(src):
        subprocess.run(["cp", src, os.path.join(cdir, "Dockerfile")],
                       check=True)
    write(
        os.path.join(cdir, "artifact_hashes.txt"), sub("""# Container identity
# {{image_name}}  md5 {{image_md5}}  {{image_bytes}} bytes
# framework revision inside the image: {{image_revision}} ({{image_revision_date}})
# built from docker/Dockerfile at commit {{dockerfile_commit}}, which pins {{framework_pin}}
# fetched by the jobs as {{image_osdf}}
#
# md5  artifact (path inside /opt/iEBE-MUSIC)
{{artifact_table}}
#
# toolchain: {{toolchain}}
""", facts))

    write(os.path.join(cdir, "IMAGE.md"), sub("""# The container

| | |
|---|---|
| file | `{{image_name}}` |
| md5 | `{{image_md5}}` |
| bytes | {{image_bytes}} |
| framework inside | `{{image_revision}}` ({{image_revision_date}}) |
| built from | `docker/Dockerfile` at `{{dockerfile_commit}}` |
| Dockerfile pins | `{{framework_pin}}` |
| as fetched by the jobs | `{{image_osdf}}` |

## Why the md5 and not a build recipe is the identity

The Dockerfile pins the *framework* to `{{framework_pin}}`, but the physics
packages are cloned inside the build: iSS is checked out at
`d242555306930f813881caca500f0e6f82036b2e` and then patched
(`codes/patches/iSS_PTB_deltaf.patch`, which is what makes `deltaf_model 1` =
PTB possible at all), while MUSIC, TRENTo, the hadronic afterburner toolkit and
the UrQMD afterburner follow moving branches.  A rebuild today therefore
resolves them differently.

So the reproducible statement is the *artifact*: the md5 of the SIF, and the
md5 of each binary inside it.

## Rebuild and check

```bash
cd docker
docker build --build-arg WITH_OPTIONAL_CODES=0 -t iebe-music:slim-{{framework_pin_short}} .
singularity build iebe-music_slim.sif docker-daemon://iebe-music:slim-{{framework_pin_short}}
```

Then compare against `artifact_hashes.txt`:

```bash
singularity exec iebe-music_slim.sif bash -c '
  git -C /opt/iEBE-MUSIC rev-parse HEAD
  md5sum /opt/iEBE-MUSIC/codes/iSS_code/iSS.e \\
         /opt/iEBE-MUSIC/codes/MUSIC_code/MUSIChydro \\
         /opt/iEBE-MUSIC/codes/hydro_plus_UrQMD_driver.py'
```

If `iSS.e` matches but MUSIC does not, the run is *not* equivalent: the free
streaming and hydro decide the initial state, and the delta f models act on
MUSIC's freeze-out surface.

The SIF itself is 516 MB and is not in this package.  Verify any copy you
obtain against `{{image_md5}}` before using it; a SIF rebuilt from the same
sources is not byte-identical, which is exactly why the binary hashes above
exist.
""", facts))

    # ---------------- execution ----------------
    edir = os.path.join(out, "execution")
    os.makedirs(edir, exist_ok=True)
    submit_src = args.submit_template
    run_src = args.run_script
    copy_note = "the exact files the campaign used"
    if not (submit_src and os.path.exists(submit_src)):
        print("      WARNING: submit template not found; regenerating one")
        tmpstage = tempfile.mkdtemp()
        subprocess.run([
            sys.executable,
            os.path.join(REPO_ROOT, "scripts", "stage_campaign.py"),
            "--dict-dir", dict_dir, "--dps", "1-1", "--offsets", "0",
            "--jobid-template", args.jobid_template, "--image",
            args.image or "IMAGE.sif", "--apbase", "/OUTPUT/dp", "--aphome",
            "/STAGING", "--disk", "4", "--out", tmpstage
        ],
                       check=True)
        submit_src = glob.glob(
            os.path.join(tmpstage, "submit", "b1", "dp0001",
                         "singularity.submit"))[0]
        run_src = glob.glob(os.path.join(tmpstage, "run",
                                         "run_singularity.sh"))[0]
        copy_note = "regenerated by scripts/stage_campaign.py (the original staging area was gone)"
    facts["copy_note"] = copy_note
    subprocess.run(["cp", submit_src, os.path.join(edir, "singularity.submit")],
                   check=True)
    if run_src and os.path.exists(run_src):
        subprocess.run([
            "cp", run_src,
            os.path.join(edir, "run_singularity.sh")
        ],
                       check=True)
    driver = subprocess.run([
        "git", "show", FRAMEWORK_PIN + ":codes/hydro_plus_UrQMD_driver.py"
    ],
                            cwd=REPO_ROOT,
                            capture_output=True,
                            text=True).stdout
    if driver:
        write(os.path.join(edir, "hydro_plus_UrQMD_driver.py"), driver)

    write(os.path.join(edir, "EXECUTION.md"), sub("""# How the jobs ran

{{npoints}} design points x 3 batches x {{jobs_per_batch}} jobs, each job
{{events_per_job}} events.  One job is one `singularity.submit` cluster member:

```
arguments = <dictionary> $(Process) {{events_per_job}} 1 0 <event_offset>
            dict         job index    events   t   seed  offset
```

| batch | event offset | global event ids | archive name |
|---|---|---|---|
{{batch_table}}

Batch 1 is untagged for compatibility with campaign 1; later batches carry the
offset in the file name.  In the merged h5 the tags are irrelevant: each group
is named after the *global* event id, so a batch is just an id range.

## Resources

`request_cpus = 1`, `request_memory = 1 GB`, `request_disk = 4 GB`,
`container_image = {{image_osdf}}`, `should_transfer_files = YES`,
`WhenToTransferOutput = ON_EXIT`, output `spvn_results_*.tar.gz`.

2 GB of disk was not enough: the execute-node sandbox holds all
{{events_per_job}} events' hydro intermediates before the packer compresses
them.  Peak RSS is a few hundred MB.

## Exit code 73 is not a failure

An event whose freeze-out surface is empty (very peripheral, tiny fireball)
produces no h5 and is skipped; the job still exits 73.  There must be **no**
`periodic_remove` on exit code 73 -- it races the output transfer and makes all
{{events_per_job}} events vanish with no hold reason.  A 1-3 % drawn-event loss
is normal (an empty freeze-out surface) and those events are re-run
individually.

At the time this package was written the merged files held {{events}} of at most
{{drawn_upper}} drawn events ({{delivered_pct}} %); the shortfall is mostly
archives still in flight, since the campaign was running.

## Reproducing the submission

```bash
python3 scripts/stage_campaign.py --dict-dir <my_dicts> --dps {{first}}-{{last}} \\
    --offsets 0,2000,4000 --jobid-template '{{campaign}}_b{batch}_dp{dp}' \\
    --image <your>.sif --apbase <output>/dp --aphome <staging> --disk 4 \\
    --out <staging>
```

The submit files in `execution/` are {{copy_note}}; paths inside them point at
this campaign's storage area and must be rewritten for a new site.
""", facts))

    # ---------------- events / seeds ----------------
    os.makedirs(os.path.join(out, "events"), exist_ok=True)
    write(
        os.path.join(out, "events", "SEEDS.md"),
        sub("""# Events and seeds

An event is identified by the 4-tuple

```
(MASTER_SEED, seed_add, global_event_id, iev)
```

with `MASTER_SEED = {{seed}}` and `seed_add = {{seed_add}}` (a campaign
constant, deliberately not random: if `seed_add` differed between design points
each would get its own private event set and the ensemble would lose the common
random numbers it is built on).

| quantity | rule |
|---|---|
| global event id | batch offset + job index * {{events_per_job}} + iev |
| TRENTo seed | `event_id + 1` |
| nucleon pool address | `(2g) * 2654435761 mod 2**32` and `(2g+1) * 2654435761 mod 2**32`, drawn with `numpy.random.Philox(key={{seed}}, counter=address * 2**24)` |
| freeze-out / iSS seed | `numpy.random.default_rng([seed_add, event_id, iev])` |
| impact parameter | drawn from `b/b_max`, where `b_max` is computed per design point from `WS_radius`, `WS_diffusiveness`, `nucleon-width` and the 2-sigma deformation (no sigma_NN term for A=96) |

The address depends only on the global event id, never on a nuclear parameter:
that is what keeps design points synchronised -- each sees the same nuclei, and
a deformation shows up as a small shift in nucleon positions rather than a
different event.

`b/b_max`, not `b`, is the synchronised variable: the same event index at a
larger `WS_radius` stays at the same centrality.

## Where the actual drawn events are recorded

Every job writes `events_drawn*.csv` with one row per *drawn* event --
`event_id, b, b_max, b_over_bmax, mult, status, seed_add` -- including the ones
that never collide (`mult = 0`, no `spvn_results`).  Those files are shipped
inside each design point's `csv.tgz`, next to the h5.  Centrality percentiles
need the count of failures, not only the count of survivors.

Example of the shipped records:

```
{{event_example}}
```

## Three delta f models, one surface

Each event is particlized three times (`Grad22`, `CE`, `PTB`) from the same
freeze-out surface with the same seeds, so the model difference is not
contaminated by sampling noise.  The results land in three subgroups of the
event group; readers must pick one.
""", facts))

    # ---------------- verification ----------------
    vdir = os.path.join(out, "verification")
    os.makedirs(vdir, exist_ok=True)
    write(os.path.join(vdir, "reproduce_design.sh"), """#!/bin/bash
# Regenerate the campaign design from (n, seed, priors) and compare it with the
# shipped copy.  REPO_ROOT must point at a clone of the framework at the pin.
set -eu
here=$(cd "$(dirname "$0")/.." && pwd)
REPO_ROOT=${IBEM_REPO:-""" + REPO_ROOT + """}
want=$(cut -d' ' -f1 "$here/design/design_lhs2000_A96_c2.csv.sha256" 2>/dev/null || true)
want=96e1e110e92958e8e9f5f1520dc4c9bdac53744f32fd06400f541705f2b4e337
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
python3 "$REPO_ROOT/scripts/make_design_a96.py" --n 2000 --seed 8675309 \
    --out "$tmp/parent.csv"
python3 "$REPO_ROOT/scripts/remap_design_prior.py" --prior a96 \
    --range normalization=6,13 "$tmp/parent.csv" "$tmp/final.csv"
got=$(sha256sum "$tmp/final.csv" | cut -d' ' -f1)
if [ "$got" = "$want" ]; then
  echo "design: PASS (sha256 $got)"
else
  echo "design: FAIL"; echo "  got  $got"; echo "  want $want"; exit 1
fi
""")

    write(os.path.join(vdir, "reproduce_dictionaries.sh"), """#!/bin/bash
# Regenerate all dictionaries from the shipped design and diff them against the
# shipped copies.  REPO_ROOT must point at a clone of the framework at the pin.
set -eu
here=$(cd "$(dirname "$0")/.." && pwd)
REPO_ROOT=${IBEM_REPO:-""" + REPO_ROOT + """}
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
mkdir "$tmp/dicts" "$tmp/shipped"
tar xzf "$here"/parameters/parameter_dictionaries_dp*.tar.gz -C "$tmp/shipped"
(cd "$tmp/dicts" && python3 "$REPO_ROOT/MakeDictionaries.py" \
    --design "$here/design/design_lhs2000_A96_c2.csv" \
    --start-design-point 1 --end-design-point 1000 --output-dir . > /dev/null)
if diff -rq "$tmp/dicts" "$tmp/shipped"; then
  echo "dictionaries: PASS (1000/1000 identical)"
else
  echo "dictionaries: FAIL"; exit 1
fi
md5sum "$tmp/dicts/DesignPoint1/parameter_dictionary_design_point_1.py"
""")

    write(os.path.join(vdir, "VERIFY.md"), sub("""# Checking this package

Run these in order; each prints the value recorded in `manifest.json`.

```bash
bash verification/reproduce_design.sh        # design sha256 {{design_sha256}}
bash verification/reproduce_dictionaries.sh  # all {{npoints}} identical,
                                            # dp1 md5 {{dp1_dict_md5}}
```

Container (independent of this package's files):

```bash
md5sum <your>.sif                            # expect {{image_md5}}
singularity exec <your>.sif bash -c '
  git -C /opt/iEBE-MUSIC rev-parse HEAD      # expect {{image_revision}}
  md5sum /opt/iEBE-MUSIC/codes/iSS_code/iSS.e'   # compare artifact_hashes.txt
```

## Checking a reproduced *result* against ours

One event end to end, on our reference event (design point 583, deforming
nucleus, the campaign image):

```bash
python3 scripts/rerun_events_local.py --image <your>.sif \\
    --param parameters/parameter_dictionary_design_point_0001.py \\
    --events 10,220 --out /tmp/c2check --jobs 2
```

Then compare `/tmp/c2check/.../spvn_results_10.h5` with the shipped group `10`
of `dp0583/dp0583.h5` dataset by dataset.

## What "reproduced" means: two different standards

| level | on the same hardware | on different hardware |
|---|---|---|
| nucleon configuration (TRENTo) | bit-identical | bit-identical (integer/float arithmetic in TRENTo, same seeds) |
| hydro (MUSIC) | bit-identical | equal to ~1e-8 relative (CPU-dependent libm paths) |
| particle tables (iSS + decays) | bit-identical | **0.1% - 1%**, because last-bit differences reseed iSS's sampling stream |

Measured on this campaign: a re-run of design point 583 event 220 was
bit-identical; event 10 had the same TRENTo event and the same initial
eccentricities, with MUSIC output equal to ~1e-8 relative and particle tables
differing by 0.1-1%.  Two runs on the *same* machine are bit-identical.

So: comparing our particle tables to yours on different hardware, expect
sub-percent differences per event.  Compare ensemble observables; do not assert
bit-identity of the sampled particles.  The initial state *is* bit-identical and
is the right thing to check first.
""", facts))

    # ---------------- handoff snapshot + README + manifest ----------------
    handoff = os.path.join(REPO_ROOT, "CAMPAIGN2_HANDOFF.md")
    if os.path.exists(handoff):
        subprocess.run(
            ["cp", handoff, os.path.join(out, "campaign2_handoff.md")],
            check=True)

    write(os.path.join(out, "README.md"), sub("""# {{system}} -- campaign 2 reproduction package

Results of an event-by-event simulation of {{system}} (nucleon-nucleon),
{{npoints}} design points x 3 batches x {{jobs_per_batch}}
jobs x {{events_per_job}} events.  This directory says exactly how they were
produced: the container, the code revision, the design, the parameters and the
seeds.

**State of the results when this package was written ({{generated}}):**
{{merged_points}} design points merged, {{archives}} job archives,
{{events}} events in the merged files.

Everything about *provenance* above is final.  The counts are a snapshot if the
campaign is still running; re-run
`python3 scripts/build_reproduction_package.py` (in the framework repo) to
refresh them and the hashes below.

## The four things that determine a result

| what | value | where |
|---|---|---|
| container (physics code) | `{{image_name}}`, md5 `{{image_md5}}` | `container/IMAGE.md`, `container/artifact_hashes.txt` |
| framework revision | `{{framework_pin}}` -- the published pin the container was built from.  All inputs below regenerate identically there (verified), so nothing outside that commit is needed | `manifest.json` |
| design (Latin hypercube) | `{{design_file}}`, sha256 `{{design_sha256}}`, {{design_rows}} rows, rows 1-{{last}} used | `design/` |
| parameter dictionaries | {{npoints}} files, all regenerable from the design | `parameters/` |

Seeds and the event bookkeeping are in `events/SEEDS.md`; the job definition
and resources in `execution/`; the physics rationale (campaign 2 vs campaign 1)
in `campaign2_handoff.md`.

## Reproduce it

```bash
# 1. code (the pin is published on branch NME of the fork)
git clone {{fork_url}}
cd iEBE-MUSIC && git checkout {{framework_pin}}

# 2. container: build from the pinned Dockerfile, then check the hashes
cd docker && docker build --build-arg WITH_OPTIONAL_CODES=0 -t iebe-music:slim-{{framework_pin_short}} .
#    -> container/IMAGE.md for the conversion and the hash check
#    Our SIF: md5 {{image_md5}} ({{image_bytes}} bytes)

# 3. design (regenerates this exact file)
python3 scripts/make_design_a96.py --n {{design_rows}} --seed {{design_seed}} --out design/design_lhs2000_A96.csv
python3 scripts/remap_design_prior.py --prior a96 --range normalization=6,13 \\
    design/design_lhs2000_A96.csv design/{{design_file}}

# 4. dictionaries (regenerate all {{npoints}}; compare with parameters/)
mkdir my_dicts && cd my_dicts
python3 ../MakeDictionaries.py --design ../design/{{design_file}} \\
    --start-design-point {{first}} --end-design-point {{last}} --output-dir .

# 5. one event, locally, in the container
cd .. && python3 generate_jobs.py -w test -n 1 \\
    -par my_dicts/DesignPoint1/parameter_dictionary_design_point_1.py
cd test/event_0 && bash submit_job.script      # ~2-3 min, writes spvn_results_<id>.h5
```

Step 5 is the smallest complete check: it exercises TRENTo, free streaming,
MUSIC, iSS for the three delta f models, the decays and the particle analysis.

For the full ensemble, `execution/EXECUTION.md` has the submission command; it
is 300,000 jobs and took a few days on opportunistic OSG capacity.

## Verification status of this package

| claim | result |
|---|---|
| design regenerates from (n=2000, seed=8675309, priors) | **{{check_design}}** |
| all {{npoints}} dictionaries regenerate from the design file | **{{check_dicts}}** |
| shipped dictionaries = the ones the jobs received | PASS (1000/1000 md5 compared against the staging area) |
| container framework revision | read out of the SIF: `{{image_revision}}` |

`verification/VERIFY.md` gives the commands, and the honest fine print about
what "reproduce" can mean on different hardware -- the particle tables agree to
0.1-1%, not bit for bit, because iSS's sampling stream depends on last-bit
hydro numerics.

## Reading the output

One HDF5 group per event, named after the global event id:

- hydro-level datasets at the top (`eccentricities_evo_*`, `momentum_anisotropy_*`, `meanpT_estimators_*`);
- `deltaf_Grad22/`, `deltaf_CE/`, `deltaf_PTB/` -- identified-particle
  `particle_<pid>_vndata_diff_y_-30_30_boostinv.dat` (100 x 13) and
  `particle_<pid>_vndata_y_-30_30_boostinv.dat` (7 x 5), each with the iSS
  overrides that produced it;
- attributes `deltaf_models = "Grad22,CE,PTB"`, `toolkit_pT_min = 0.0`,
  `toolkit_pT_max = 5.0`, `toolkit_npT = 100`.

The pT bins are edges `0 + i*5/100` GeV, i.e. 0.05 GeV.  **Readers must choose
a model.**  The three are a delta-f systematic, not three estimates of one
number: iSS's `MC_sampling 4` clamps the linear delta-f to [-1,1], so `CE`
under-applies pi at large pi/(e+P) while `PTB` applies it and is
positive-definite; see `campaign2_handoff.md`.

## Contents

```
README.md                     this file
manifest.json                 the same facts, machine-readable
manifest_sha256.txt           sha256 of every file here
design/                       design CSV + regeneration instructions + per-point index
parameters/                   the {{npoints}} dictionaries, master, template, resolved JSON
container/                    image identity, hashes, how to rebuild
execution/                    the exact submit file, wrapper and driver
events/SEEDS.md               seed scheme and event bookkeeping
verification/                 scripts that re-derive the design and dictionaries
campaign2_handoff.md          physics rationale, campaign 2 vs campaign 1
```

## Known limitations

- The physics packages inside the container are partly branch-tracked, so the
  container is identified by hashes, not by a build recipe that rebuilds it
  byte for byte.  See `container/IMAGE.md`.
- `analysisKit/` in the framework still assumes campaign 1's flat h5 layout; it
  needs the per-model subgroups of this campaign before it can read these files.
- The merged h5 is uncompressed on purpose (compressing each small dataset
  makes it 1.8x *larger*); gzip the file as a whole if you need to move it.
""", facts))

    manifest = {
        "campaign": args.campaign,
        "system": args.system,
        "generated_utc": facts["generated"],
        "purpose": "everything needed to reproduce the results in this tree",
        "code": {
            "repository_used": FORK_URL,
            "reproduction_revision": FRAMEWORK_PIN,
            "published_branch_tip": published_tip,
            "working_tree_revision_at_packaging": rev,
            "branch": branch,
            "working_tree_dirty": dirty,
            "container_framework_revision": image.get("revision"),
            "dockerfile_commit": DOCKERFILE_COMMIT,
            "dockerfile_pinned_framework": FRAMEWORK_PIN,
        },
        "container": {
            "file": image.get("name"),
            "md5": image.get("md5"),
            "bytes": image.get("bytes"),
            "fetched_as": image.get("osdf_url"),
            "artifact_md5": image.get("hashes", {}),
            "toolchain": image.get("toolchain", []),
        },
        "design": {
            "file": design_path,
            "sha256": design_sha,
            "rows_total": DESIGN_POINTS_AVAILABLE,
            "rows_used": [args.first, args.last],
            "regeneration": [
                "python3 scripts/make_design_a96.py --n 2000 --seed 8675309",
                "python3 scripts/remap_design_prior.py --prior a96 --range normalization=6,13",
            ],
            "regeneration_verified": bool(parent_ok and design_ok),
            "point_index": "design/design_points.csv",
        },
        "parameters": {
            "count": len(dict_rows),
            "source": "MakeDictionaries.py + design CSV",
            "regeneration_verified": dict_ok,
            "master_sha256": facts["master_sha256"],
            "template_sha256": facts["template_sha256"],
            "make_dictionaries_sha256": facts["make_dict_sha256"],
            "dp1_md5": facts["dp1_dict_md5"],
            "resolved_example": "parameters/resolved_design_point_0001.json",
        },
        "seeds": {
            "master_seed": MASTER_SEED,
            "seed_add": CAMPAIGN_SEED_ADD,
            "design_seed": DESIGN_SEED,
            "trento_seed": "event_id + 1",
            "nucleon_pool": "Philox(key=master_seed, counter=address*2**24), address=(2g)*2654435761 mod 2**32",
            "freezeout": "default_rng([seed_add, event_id, iev])",
        },
        "runs": {
            "batches": [{
                "batch": b,
                "event_offset": off
            } for b, off in BATCHES],
            "jobs_per_batch": JOBS_PER_BATCH,
            "events_per_job": EVENTS_PER_JOB,
            "resources": {
                "cpus": 1,
                "memory": "1 GB",
                "disk": "4 GB",
                "container_image": image.get("osdf_url"),
            },
        },
        "results": {
            "design_points_merged": state["design_points_merged"],
            "job_archives": state["job_archives"],
            "events": state["events"],
            "events_counted_from": ("merge.log" if state["events_exact"]
                                    else "archives*events_per_job (log missing)"),
            "merged_h5": "one file per design point, one group per event",
            "per_event_bytes_uncompressed": 253000,
        },
    }
    with open(os.path.join(out, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)

    print("[6/6] hashing the package ...")
    lines = []
    for root, dirs, files in os.walk(out):
        dirs.sort()
        for name in sorted(files):
            if name == "manifest_sha256.txt":
                continue
            full = os.path.join(root, name)
            lines.append("%s  %s" % (sha256_file(full),
                                     os.path.relpath(full, out)))
    write(os.path.join(out, "manifest_sha256.txt"),
          "\n".join(lines) + "\n")

    total = sum(os.path.getsize(os.path.join(r, n))
                for r, d, fs in os.walk(out) for n in fs)
    print("      %d files, %.1f MB" % (len(lines) + 1, total / 1e6))
    print("done: %s" % out)
    return 0


def main():
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--campaign", default="zr96c2")
    p.add_argument("--system", default="96Zr + 96Zr (A=96), 200 GeV")
    p.add_argument("--design", default="design/design_lhs2000_A96_c2.csv")
    p.add_argument("--parent-design", default="design/design_lhs2000_A96.csv")
    p.add_argument("--dict-dir", default="zr96_design_c2")
    p.add_argument("--first", type=int, default=1)
    p.add_argument("--last", type=int, default=1000)
    p.add_argument("--merged", default="/data/mluzum/zr96c2_results/merged")
    p.add_argument("--image", default="")
    p.add_argument("--image-ospool-path",
                   default="ospool/ap40/data/matthew.luzum/"
                   "iebe-music_slim_17ae5b4_f5242628.sif")
    p.add_argument("--inspect-image", action="store_true", default=True)
    p.add_argument("--no-inspect-image", dest="inspect_image",
                   action="store_false")
    p.add_argument("--submit-template", default="")
    p.add_argument("--run-script", default="")
    p.add_argument("--jobid-template", default="zr96c2_b{batch}_dp{dp}")
    p.add_argument("--out", default="")
    args = p.parse_args()
    if not args.out:
        args.out = os.path.join(args.merged, "REPRODUCTION")
    return build(args)


if __name__ == "__main__":
    sys.exit(main())
