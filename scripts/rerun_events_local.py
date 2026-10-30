#!/usr/bin/env python3
"""Re-run selected events of one design point locally, in the campaign image.

Each event is regenerated in the job folder the campaign used (see
rerun_event_inner.sh), so with no overrides it reproduces the campaign's
spvn_results_<id>.h5 and a variant can be compared to the campaign event by
event (common random numbers).  Parameter overrides are Python statements
appended to a copy of the design point's dictionary, e.g.

    python3 scripts/rerun_events_local.py \\
        --param zr96_design/DesignPoint583/parameter_dictionary_design_point_583.py \\
        --events 101,140,377 --out /scratch/cheaptest --variant fullTmunu \\
        --driver codes/hydro_plus_UrQMD_driver.py \\
        --set "music_dict['Initial_profile'] = 9" --jobs 8

Results: <out>/<variant>/results/spvn_results_<id>.h5 (+ TRENTo summary),
<out>/<variant>/log.csv (event, exit code, seconds), the exact parameter
file, driver and inner script used, and effective_parameters.txt (the
generated MUSIC/iSS settings that matter here, from the first event).  Work folders are deleted after a
successful event; a failed one keeps its logs under <out>/<variant>/failed/.
"""

import argparse
import concurrent.futures as cf
import glob
import os
import shutil
import subprocess
import time

HERE = os.path.dirname(os.path.abspath(__file__))


def parse_events(spec):
    if spec.startswith("@"):
        with open(spec[1:]) as fh:
            return [int(x) for x in fh.read().split()]
    return [int(x) for x in spec.split(",") if x.strip()]


def run_one(ev, vdir, par, image, per_job, use_driver, nice):
    wd = os.path.join(vdir, "work", "ev%d" % ev)
    shutil.rmtree(wd, ignore_errors=True)
    os.makedirs(wd)
    cmd = ["docker", "run", "--rm", "--user", "%d:%d" % (os.getuid(), os.getgid()),
           "-v", "%s:%s" % (vdir, vdir), "-w", wd, "--entrypoint", "nice", image,
           "-n", str(nice), "bash", os.path.join(vdir, "rerun_event_inner.sh"),
           os.path.join(vdir, par), str(ev), str(per_job)]
    if use_driver:
        cmd.append(os.path.join(vdir, "hydro_plus_UrQMD_driver.py"))
    t0 = time.time()
    with open(os.path.join(wd, "docker.log"), "w") as log:
        rc = subprocess.call(cmd, stdout=log, stderr=subprocess.STDOUT)
    dt = time.time() - t0
    h5 = glob.glob(os.path.join(wd, "playground", "event_*", "EVENT_RESULTS_%d" % ev,
                                "spvn_results_%d.h5" % ev))
    if rc == 0 and h5:
        res = os.path.join(vdir, "results")
        shutil.copy2(h5[0], res)
        for f in glob.glob(os.path.join(wd, "playground", "**",
                                        "trento_event_summary_%d*" % ev),
                           recursive=True)[:1]:
            shutil.copy2(f, res)
        eff = os.path.join(wd, "effective_parameters.txt")
        if os.path.exists(eff) and not os.path.exists(os.path.join(vdir, "effective_parameters.txt")):
            shutil.copy2(eff, vdir)
        shutil.rmtree(wd, ignore_errors=True)
    else:
        rc = rc or 99
        keep = os.path.join(vdir, "failed", "ev%d" % ev)
        os.makedirs(keep, exist_ok=True)
        for f in ("docker.log", "run.log", "generate.log", "effective_parameters.txt"):
            if os.path.exists(os.path.join(wd, f)):
                shutil.copy2(os.path.join(wd, f), keep)
        shutil.rmtree(wd, ignore_errors=True)
    return ev, rc, dt


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--param", required=True)
    ap.add_argument("--events", required=True, help="comma list or @file")
    ap.add_argument("--out", required=True)
    ap.add_argument("--variant", required=True)
    ap.add_argument("--set", action="append", default=[],
                    help="Python statement appended to the parameter file")
    ap.add_argument("--driver", default=None,
                    help="replacement hydro_plus_UrQMD_driver.py")
    ap.add_argument("--image", default="iebe-music:slim-3001ee9")
    ap.add_argument("--per-job", type=int, default=20,
                    help="events per OSG job in the campaign")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--nice", type=int, default=10)
    args = ap.parse_args()

    events = parse_events(args.events)
    vdir = os.path.abspath(os.path.join(args.out, args.variant))
    os.makedirs(os.path.join(vdir, "results"), exist_ok=True)
    with open(args.param) as fh:
        text = fh.read()
    if args.set:
        text += "\n# --- overrides (rerun_events_local.py) ---\n"
        text += "\n".join(args.set) + "\n"
    # Keep the campaign's file name: generate_jobs imports it as a module.
    par = os.path.basename(args.param)
    with open(os.path.join(vdir, par), "w") as fh:
        fh.write(text)
    shutil.copy2(os.path.join(HERE, "rerun_event_inner.sh"), vdir)
    if args.driver:
        shutil.copy2(args.driver, os.path.join(vdir, "hydro_plus_UrQMD_driver.py"))

    done = set()
    logp = os.path.join(vdir, "log.csv")
    if os.path.exists(logp):
        with open(logp) as fh:
            done = {int(l.split(",")[0]) for l in fh if l[0].isdigit()
                    and l.split(",")[1] == "0"}
    todo = [e for e in events if e not in done]
    print("%s: %d events (%d already done), %d parallel" %
          (args.variant, len(todo), len(events) - len(todo), args.jobs), flush=True)
    with cf.ThreadPoolExecutor(args.jobs) as pool, open(logp, "a") as log:
        futs = [pool.submit(run_one, e, vdir, par, args.image, args.per_job,
                            bool(args.driver), args.nice) for e in todo]
        for f in cf.as_completed(futs):
            ev, rc, dt = f.result()
            log.write("%d,%d,%.0f\n" % (ev, rc, dt))
            log.flush()
            print("  ev %d rc %d %.0fs" % (ev, rc, dt), flush=True)


if __name__ == "__main__":
    main()
