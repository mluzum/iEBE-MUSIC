#!/usr/bin/env python3
"""Build submission staging for one campaign tranche.

For every design point in --dps and every event offset in --offsets it runs the
OSG generator and rewrites the four submit-side paths so that everything except
the output directory lives on the AP home disk:

    executable            -> <aphome>/run/run_singularity.sh
    transfer_input_files  -> <aphome>/dicts/<dict name>
    initialdir            -> <apbase>/<dp>
    log/output/error      -> <aplog>/job.$(Cluster).$(Process).*

The run script is generated once by the same generator invocation as the submit
files and shipped inside the staging tree, so the submit side and the worker
side can never come from different generator versions (that mismatch held 192
repair jobs once).

Layout produced:
    <out>/submit/<batch>/<dp>/singularity.submit
    <out>/run/run_singularity.sh
    <out>/dicts/<dict>.py
    <out>/chunks.txt                  submission chunks of --chunk dps

Adding design points later is just another run with a wider --dps range (and
--batches if new event offsets are wanted): the naming is derived from the
design point and the event offset, and batch 1 is always untagged.

Example (A=96, 1000 points, 3 batches):
    python3 scripts/stage_campaign.py --dict-dir zr96_design --dps 1-1000 \
        --offsets 0,2000,4000 --jobid-template 'zr96_b{batch}_dp{dp}' \
        --apbase /ospool/ap40/data/matthew.luzum/zr96_prod \
        --aphome /home/matthew.luzum/zr96_stage \
        --out /tmp/opencode/stage_zr96
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GENERATOR = os.path.join(REPO, "Cluster_supports", "OSG",
                         "generate_submission_script.py")


def parse_dps(spec):
    out = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-")
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dict-dir", required=True,
                    help="directory holding DesignPointN/parameter_dictionary_design_point_N.py")
    ap.add_argument("--dps", required=True, help="e.g. 1-1000 or 1,5,9-20")
    ap.add_argument("--offsets", default="0",
                    help="comma-separated event offsets, one per batch (default 0)")
    ap.add_argument("--jobid-template", required=True,
                    help="e.g. 'zr96_b{batch}_dp{dp}'")
    ap.add_argument("--image", required=True)
    ap.add_argument("--apbase", required=True, help="AP output root (<apbase>/<dp>)")
    ap.add_argument("--aphome", required=True, help="AP staging root on the home disk")
    ap.add_argument("--aplog", default="/home/matthew.luzum/log")
    ap.add_argument("--n-events", type=int, default=20)
    ap.add_argument("--n-jobs", type=int, default=100)
    ap.add_argument("--mem", default="1")
    ap.add_argument("--disk", default="4",
                    help="per-job scratch request in GB; 2 GB is exceeded by "
                         "20-event jobs (hydro intermediate files)")
    ap.add_argument("--chunk", type=int, default=50, help="design points per submission chunk")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    offsets = [int(x) for x in args.offsets.split(",") if x.strip() != ""]
    dps = parse_dps(args.dps)
    out = args.out
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(os.path.join(out, "dicts"), exist_ok=True)
    os.makedirs(os.path.join(out, "run"), exist_ok=True)

    exec_path = os.path.join(args.aphome, "run", "run_singularity.sh")
    staged = {0}  # dicts already copied
    run_scripts = set()
    tmp = tempfile.mkdtemp(prefix="stagegen_")
    n = 0
    for batch_index, offset in enumerate(offsets, start=1):
        for dp in dps:
            dict_src = os.path.join(args.dict_dir, "DesignPoint%d" % dp,
                                    "parameter_dictionary_design_point_%d.py" % dp)
            if not os.path.isfile(dict_src):
                print("MISSING_DICT %d" % dp, file=sys.stderr)
                continue
            if dp not in staged:
                shutil.copy2(dict_src, os.path.join(out, "dicts"))
                staged.add(dp)
            odir = os.path.join(out, "submit", "b%d" % batch_index, "dp%04d" % dp)
            os.makedirs(odir, exist_ok=True)
            # {dp} is the 4-digit number so templates read naturally:
            #   'ge76_dp{dp}'      -> ge76_dp1461
            #   'zr96_b{batch}_dp{dp}' -> zr96_b2_dp0421
            jobid = args.jobid_template.format(batch=batch_index, dp="%04d" % dp)
            cmd = [
                sys.executable, GENERATOR,
                "-param", dict_src,
                "-singularity", args.image,
                "-n", str(args.n_jobs), "-nev", str(args.n_events),
                "-nth", "1", "-mem", args.mem, "-disk", args.disk,
                "-event_start_id", str(offset), "-jobid", jobid,
            ]
            r = subprocess.run(cmd, cwd=odir, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
            if r.returncode != 0:
                print("GENFAIL dp%d offset%d" % (dp, offset), file=sys.stderr)
                continue
            sub = os.path.join(odir, "singularity.submit")
            with open(sub) as f:
                text = f.read()
            # rewrite only the four absolute-side paths
            lines = []
            for line in text.splitlines():
                if line.startswith("executable ="):
                    line = "executable = " + exec_path
                elif line.startswith("transfer_input_files ="):
                    line = ("transfer_input_files = %s/dicts/%s" %
                            (args.aphome, os.path.basename(dict_src)))
                elif line.startswith("initialdir ="):
                    line = "initialdir = %s/dp%04d" % (args.apbase, dp)
                elif line.startswith(("output =", "error =", "log =")):
                    # the generator ran on the local host, so the home-directory
                    # paths carry the local $HOME; retarget them at the AP log dir
                    line = line.replace("/home/mluzum/log/", args.aplog + "/")
                lines.append(line)
            if not any(l.startswith("initialdir =") for l in lines):
                idx = next((i for i, l in enumerate(lines) if l.startswith("queue")), len(lines))
                lines.insert(idx, "initialdir = %s/dp%04d" % (args.apbase, dp))
            text = "\n".join(lines)
            if not text.endswith("\n"):
                text += "\n"
            with open(sub, "w") as f:
                f.write(text)
            runf = os.path.join(odir, "run_singularity.sh")
            if os.path.isfile(runf):
                run_scripts.add(open(runf).read())
            n += 1

    if len(run_scripts) == 1:
        shutil.copy2(os.path.join(out, "submit", "b1", "dp%04d" % dps[0],
                                  "run_singularity.sh"),
                     os.path.join(out, "run", "run_singularity.sh"))
        # drop the per-dp copies: the shared one is shipped and referenced
        for b in range(1, len(offsets) + 1):
            for dp in dps:
                p = os.path.join(out, "submit", "b%d" % b, "dp%04d" % dp,
                                 "run_singularity.sh")
                if os.path.isfile(p):
                    os.remove(p)
    elif len(run_scripts) > 1:
        print("WARNING: %d distinct run scripts; keeping per-dp copies"
              % len(run_scripts), file=sys.stderr)

    with open(os.path.join(out, "chunks.txt"), "w") as f:
        for batch_index in range(1, len(offsets) + 1):
            for i in range(0, len(dps), args.chunk):
                grp = dps[i:i + args.chunk]
                if grp:
                    f.write("%d %d %d\n" % (batch_index, grp[0], grp[-1]))
    shutil.rmtree(tmp, ignore_errors=True)
    print("staged %d submit files for %d design points x %d batches"
          % (n, len(dps), len(offsets)))
    print("run scripts distinct: %d" % len(run_scripts))
    print("chunks: %d" % (sum(1 for _ in open(os.path.join(out, "chunks.txt")))))


if __name__ == "__main__":
    main()
