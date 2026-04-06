#!/usr/bin/env python3
"""This script combine multiple hdf5 data files to one"""

import sys
import csv
import json
import time
from os import path, system, remove
from shutil import rmtree
from glob import glob
import h5py
import string
import random
import re
from numpy import nan_to_num

def randomString(stringLength=1):
    """Generate a random string of fixed length """
    letters = string.ascii_lowercase
    return ''.join(random.choice(letters) for i in range(stringLength))


def print_help():
    """This function outpus help messages"""
    print("{0} results_folder".format(sys.argv[0]))


def extract_process_id(file_name):
    """Extract Condor Process id from file names like *_<pid>.h5/.dat."""
    base_name = path.basename(file_name)
    match = re.search(r'_(\d+)\.(h5|dat)$', base_name)
    if match is None:
        return None
    return int(match.group(1))


def extract_event_id_from_group_name(group_name):
    """Extract event id from group names like spvn_results_<event_id>."""
    match = re.search(r'_(\d+)$', group_name)
    if match is None:
        return None
    return int(match.group(1))


def parse_events_summary_file(file_name):
    """Parse events_summary_*.dat into a list of per-event dictionaries."""
    rows = []
    with open(file_name, "r", encoding="utf-8") as summary_file:
        for line in summary_file:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            columns = line.split()
            if len(columns) < 9:
                continue
            rows.append({
                "event_id": int(columns[0]),
                "npart": int(columns[1]),
                "ncoll": int(columns[2]),
                "nstrings": int(columns[3]),
                "b_fm": float(columns[4]),
                "part_protons": int(columns[5]),
                "part_neutrons": int(columns[6]),
                "proj_config_id": int(columns[7]),
                "targ_config_id": int(columns[8]),
            })
    return rows


def build_events_summary_index(results_path):
    """Index all events_summary_*.dat files by Process id."""
    summary_index = {}
    summary_file_map = {}
    summary_files = glob(path.join(results_path, "events_summary_*.dat"))
    for summary_file in summary_files:
        process_id = extract_process_id(summary_file)
        if process_id is None:
            continue
        summary_index[process_id] = parse_events_summary_file(summary_file)
        summary_file_map[process_id] = summary_file
    return summary_index, summary_file_map


def match_summary_row(summary_rows, source_group, group_index):
    """Match one h5 group to one events_summary row deterministically."""
    if len(summary_rows) == 0:
        return None, None, "none"

    source_event_id = extract_event_id_from_group_name(source_group)
    if source_event_id is not None:
        for row_index, row in enumerate(summary_rows):
            if row.get("event_id", None) == source_event_id:
                return row, row_index, "event_id"

    if len(summary_rows) == 1:
        return summary_rows[0], 0, "single_row"

    if group_index < len(summary_rows):
        return summary_rows[group_index], group_index, "group_index"

    return None, None, "ambiguous"


def read_existing_index_rows(index_file_name):
    """Read existing sidecar index rows if present."""
    rows = []
    if not path.exists(index_file_name):
        return rows
    with open(index_file_name, "r", encoding="utf-8") as index_file:
        reader = csv.DictReader(index_file)
        for row in reader:
            rows.append(row)
    return rows


def sync_index_rows_from_h5(index_rows, merged_h5_file_name):
    """Backfill missing index rows from merged HDF5 provenance attrs.

    This keeps the CSV sidecar consistent even if a previous run merged data
    into HDF5 but failed before writing the index file.
    """
    rows_by_group = {}
    for row in index_rows:
        group_name = row.get("merged_group", "")
        if group_name:
            rows_by_group[group_name] = row

    with h5py.File(merged_h5_file_name, "r") as h5_file:
        for group_name in list(h5_file.keys()):
            if group_name in rows_by_group:
                continue

            group = h5_file[group_name]

            def _attr(key, default=""):
                if key in group.attrs:
                    return group.attrs[key]
                return default

            def _stringify(value):
                if value is None:
                    return ""
                return str(value)

            backfill_row = {
                "merged_group": group_name,
                "source_group": _stringify(_attr("source_group", group_name)),
                "source_h5_file": _stringify(_attr("source_h5_file", "")),
                "process_id": _stringify(_attr("process_id", "")),
                "source_event_id": _stringify(_attr("source_event_id", "")),
                "events_summary_row_index": _stringify(
                    _attr("events_summary_row_index", "")),
                "events_summary_mapping_method": _stringify(
                    _attr("events_summary_mapping_method", "")),
                "event_id": _stringify(_attr("event_id", "")),
                "npart": _stringify(_attr("npart", "")),
                "ncoll": _stringify(_attr("ncoll", "")),
                "nstrings": _stringify(_attr("nstrings", "")),
                "b_fm": _stringify(_attr("b_fm", "")),
                "part_protons": _stringify(_attr("part_protons", "")),
                "part_neutrons": _stringify(_attr("part_neutrons", "")),
                "proj_config_id": _stringify(_attr("proj_config_id", "")),
                "targ_config_id": _stringify(_attr("targ_config_id", "")),
            }
            rows_by_group[group_name] = backfill_row

    return [rows_by_group[key] for key in sorted(rows_by_group.keys())]


def open_h5_with_retry(file_name, mode, retries=8, initial_delay_s=0.2):
    """Open HDF5 file with retry/backoff for transient lock errors."""
    delay_s = initial_delay_s
    for attempt in range(retries):
        try:
            return h5py.File(file_name, mode)
        except OSError as err:
            err_msg = str(err)
            # errno 11 is common on shared filesystems when lock is transient.
            if "errno = 11" in err_msg or "unable to lock file" in err_msg:
                if attempt < retries - 1:
                    print(
                        "retry open {} mode={} after lock (attempt {}/{})".format(
                            file_name, mode, attempt + 1, retries))
                    time.sleep(delay_s)
                    delay_s = min(delay_s * 2.0, 5.0)
                    continue
            raise


def check_an_event_is_good(h5_event, dNtrigger):
    """This function checks the given event contains all required files"""
    required_files_list = [
        'particle_9999_vndata_eta_-0.5_0.5.dat',
        'particle_211_vndata_diff_y_-0.5_0.5.dat',
        'particle_321_vndata_diff_y_-0.5_0.5.dat',
        'particle_2212_vndata_diff_y_-0.5_0.5.dat',
        'particle_-211_vndata_diff_y_-0.5_0.5.dat',
        'particle_-321_vndata_diff_y_-0.5_0.5.dat',
        'particle_-2212_vndata_diff_y_-0.5_0.5.dat',
        'particle_3122_vndata_diff_y_-0.5_0.5.dat',
        'particle_3312_vndata_diff_y_-0.5_0.5.dat',
        'particle_3334_vndata_diff_y_-0.5_0.5.dat',
        'particle_-3122_vndata_diff_y_-0.5_0.5.dat',
        'particle_-3312_vndata_diff_y_-0.5_0.5.dat',
        'particle_-3334_vndata_diff_y_-0.5_0.5.dat',
        'particle_333_vndata_diff_y_-0.5_0.5.dat',
    ]
    event_file_list = list(h5_event.keys())
    for ifile in required_files_list:
        if ifile not in event_file_list:
            print("event {} is bad, missing {} ...".format(
                                                        h5_event.name, ifile))
            return False
        trigger_filename = "particle_9999_vndata_eta_-0.5_0.5.dat"
        temp_data = h5_event.get(trigger_filename)
        temp_data = nan_to_num(temp_data)
        dNchdeta = temp_data[0, 1]
        if dNchdeta < dNtrigger:
            return False
    return True


def check_events_are_good(h5_filename, dNtrigger):
    """This function is a shell to check all the events status in a h5 file"""
    h5_file = open_h5_with_retry(h5_filename, "a")
    event_list = list(h5_file.keys())
    event_status_all = False
    for event_name in event_list:
        test_event = h5_file.get(event_name)
        event_status = check_an_event_is_good(test_event, dNtrigger)
        if event_status:
            event_status_all = True
        else:
            print("checking {} ...".format(h5_filename))
            print("delete event {} ...".format(event_name))
            del h5_file[event_name]
    h5_file.close()
    if event_status_all:
        print("{} is good!".format(h5_filename))
    else:
        print("{} is not good! Ignored~".format(h5_filename))
    return(event_status_all)


if len(sys.argv) < 2:
    print_help()
    exit(1)

dNdeta_trigger = 0.

RESULTS_FOLDER = str(sys.argv[1])
RESULTS_NAME = RESULTS_FOLDER.split("/")[-1]
if RESULTS_NAME == "":
    RESULTS_NAME = RESULTS_FOLDER.split("/")[-2]
RESULTS_PATH = path.abspath(path.join(".", RESULTS_FOLDER))
# Only ingest per-process outputs, never the merged result file itself.
EVENT_LIST = sorted(glob(path.join(RESULTS_PATH, "spvn_results_*.h5")))
events_summary_index, events_summary_file_map = build_events_summary_index(
    RESULTS_PATH)

event_index_rows = []
processed_h5_files = []
processed_process_ids = set()
merge_success = True

index_file_name = "{}_event_index.csv".format(RESULTS_NAME)
event_index_rows = read_existing_index_rows(index_file_name)

h5Res = h5py.File("{}.h5".format(RESULTS_NAME), "a")
exist_group_keys = set(list(h5Res.keys()))
existing_source_h5_files = set()
existing_process_ids = set()
for group_name in list(h5Res.keys()):
    group = h5Res[group_name]
    if "source_h5_file" in group.attrs:
        existing_source_h5_files.add(str(group.attrs["source_h5_file"]))
    if "process_id" in group.attrs:
        existing_process_ids.add(int(group.attrs["process_id"]))

for ievent, event_path in enumerate(EVENT_LIST):
    print("processing {0} ... ".format(event_path))
    event_folder = "/".join(event_path.split("/")[0:-1])
    source_h5_file = path.basename(event_path)
    process_id = extract_process_id(event_path)
    if process_id is None:
        print("skip {} (cannot infer process id)".format(source_h5_file))
        continue
    if (source_h5_file in existing_source_h5_files
            or (process_id is not None and process_id in existing_process_ids)):
        print("skip {} (already collected)".format(source_h5_file))
        continue
    if not check_events_are_good(event_path, dNdeta_trigger):
        print("skip bad file {} (not deleting for safety)".format(event_path))
        continue
    summary_rows = events_summary_index.get(process_id, [])
    try:
        hftemp = open_h5_with_retry(event_path, "r")
        glist = list(hftemp.keys())
        for igroup, gtemp in enumerate(glist):
            gtemp2 = gtemp
            random_string_len = 1
            tol = 0
            while gtemp2 in exist_group_keys:
                randomlabel = randomString(random_string_len)
                gtemp2 = "{0}{1}".format(gtemp, randomlabel)
                tol += 1
                if tol > 30:
                    random_string_len += 1
                    tol = 0
            if gtemp2 != gtemp:
                print("Conflict in mergeing {0}, use {1}".format(gtemp, gtemp2))
            exist_group_keys.add(gtemp2)
            h5py.h5o.copy(hftemp.id, gtemp.encode('UTF-8'),
                          h5Res.id, gtemp2.encode('UTF-8'))

            # Attach provenance attributes without changing existing datasets.
            merged_group = h5Res[gtemp2]
            merged_group.attrs["source_h5_file"] = path.basename(event_path)
            if process_id is not None:
                merged_group.attrs["process_id"] = process_id

            source_event_id = extract_event_id_from_group_name(gtemp)
            if source_event_id is not None:
                merged_group.attrs["source_event_id"] = source_event_id

            summary_row, summary_row_index, mapping_method = match_summary_row(
                summary_rows, gtemp, igroup)
            merged_group.attrs["events_summary_mapping_method"] = mapping_method

            if summary_row_index is not None:
                merged_group.attrs["events_summary_row_index"] = summary_row_index

            if summary_row is not None:
                merged_group.attrs["event_id"] = summary_row["event_id"]
                merged_group.attrs["npart"] = summary_row["npart"]
                merged_group.attrs["ncoll"] = summary_row["ncoll"]
                merged_group.attrs["nstrings"] = summary_row["nstrings"]
                merged_group.attrs["b_fm"] = summary_row["b_fm"]
                merged_group.attrs["part_protons"] = summary_row["part_protons"]
                merged_group.attrs["part_neutrons"] = summary_row["part_neutrons"]
                merged_group.attrs["proj_config_id"] = summary_row["proj_config_id"]
                merged_group.attrs["targ_config_id"] = summary_row["targ_config_id"]
            elif len(summary_rows) > 1:
                merged_group.attrs["events_summary_json"] = json.dumps(summary_rows)

            event_index_row = {
                "merged_group": gtemp2,
                "source_group": gtemp,
                "source_h5_file": path.basename(event_path),
                "process_id": process_id,
                "source_event_id": source_event_id if source_event_id is not None else "",
                "events_summary_row_index": summary_row_index if summary_row_index is not None else "",
                "events_summary_mapping_method": mapping_method,
            }
            if summary_row is not None:
                event_index_row.update({
                    "event_id": summary_row["event_id"],
                    "npart": summary_row["npart"],
                    "ncoll": summary_row["ncoll"],
                    "nstrings": summary_row["nstrings"],
                    "b_fm": summary_row["b_fm"],
                    "part_protons": summary_row["part_protons"],
                    "part_neutrons": summary_row["part_neutrons"],
                    "proj_config_id": summary_row["proj_config_id"],
                    "targ_config_id": summary_row["targ_config_id"],
                })
            else:
                event_index_row.update({
                    "event_id": "",
                    "npart": "",
                    "ncoll": "",
                    "nstrings": "",
                    "b_fm": "",
                    "part_protons": "",
                    "part_neutrons": "",
                    "proj_config_id": "",
                    "targ_config_id": "",
                })
            event_index_rows.append(event_index_row)
        hftemp.close()
        processed_h5_files.append(event_path)
        if process_id is not None:
            processed_process_ids.add(process_id)
            existing_process_ids.add(process_id)
        existing_source_h5_files.add(source_h5_file)
    except Exception as err:
        print("error while processing {}: {}".format(event_path, err))
        merge_success = False
        continue
h5Res.close()

# Sidecar index for robust external joins and auditing.
index_write_success = True
try:
    event_index_rows = sync_index_rows_from_h5(
        event_index_rows, "{}.h5".format(RESULTS_NAME))
    with open(index_file_name, "w", newline="", encoding="utf-8") as index_file:
        writer = csv.DictWriter(
            index_file,
            fieldnames=[
                "merged_group",
                "source_group",
                "source_h5_file",
                "process_id",
                "source_event_id",
                "events_summary_row_index",
                "events_summary_mapping_method",
                "event_id",
                "npart",
                "ncoll",
                "nstrings",
                "b_fm",
                "part_protons",
                "part_neutrons",
                "proj_config_id",
                "targ_config_id",
            ],
        )
        writer.writeheader()
        writer.writerows(event_index_rows)
    print("wrote {}".format(index_file_name))
except Exception as err:
    print("failed to write {}: {}".format(index_file_name, err))
    index_write_success = False

if merge_success and index_write_success:
    for file_name in processed_h5_files:
        try:
            remove(file_name)
        except Exception as err:
            print("warning: failed to delete {}: {}".format(file_name, err))
    for process_id in processed_process_ids:
        summary_file = events_summary_file_map.get(process_id, None)
        if summary_file and path.exists(summary_file):
            try:
                remove(summary_file)
            except Exception as err:
                print("warning: failed to delete {}: {}".format(summary_file, err))
    print("collection successful; deleted processed spvn_results and events_summary files")
else:
    print("collection failed; input files were kept for safety")
