import argparse
import struct
import math
import numpy as np
import os

# PDG particle masses in GeV/c^2 (from the notebook)
PARTICLE_MASSES = {
    211: 0.13957,   # pi+
    -211: 0.13957,  # pi-
    111: 0.13498,   # pi0
    2212: 0.93827,  # proton
    -2212: 0.93827, # anti-proton
    2112: 0.93957,  # neutron
    -2112: 0.93957, # anti-neutron
    321: 0.49368,   # K+
    -321: 0.49368,  # K-
    130: 0.49761,   # K0_S
    310: 0.49761,   # K0_L
    3122: 1.11568,  # Lambda
    -3122: 1.11568, # anti-Lambda
}

def get_pid_from_mass(mass, charge, tolerance=0.01):
    for pid, pid_mass in PARTICLE_MASSES.items():
        if abs(mass - pid_mass) < tolerance:
            if pid in [211, -211, 2212, -2212, 321, -321]:
                if (pid > 0 and charge > 0) or (pid < 0 and charge < 0):
                    return pid
            else:
                if charge == 0:
                    return pid
    return 0

def parse_oscar2013_to_unified(data):
    offset = 0
    events = []
    magic_number, format_version, format_variant, len_smash_version = struct.unpack_from('4sHHI', data, offset)
    offset += struct.calcsize('4sHHI') + len_smash_version
    while offset < len(data):
        block_type = struct.unpack_from('c', data, offset)[0].decode('ascii')
        offset += struct.calcsize('c')
        if block_type == 'p':
            event_number, ensemble_number, n_part_lines = struct.unpack_from('iiI', data, offset)
            offset += struct.calcsize('iiI')
            particles = []
            particle_format = '9d4i2d2id4i'
            particle_size = struct.calcsize(particle_format)
            for _ in range(n_part_lines):
                if offset + particle_size > len(data): break
                unpacked_data = struct.unpack_from(particle_format, data, offset)
                offset += particle_size
                particles.append([
                    unpacked_data[5],  # E
                    unpacked_data[6],  # px
                    unpacked_data[7],  # py
                    unpacked_data[8],  # pz
                    unpacked_data[9],  # pid
                    unpacked_data[10], # charge
                    unpacked_data[4]   # mass
                ])
            if len(particles) == n_part_lines:
                events.append(np.array(particles))
        elif block_type == 'f':
            offset += struct.calcsize('iid') + 1
        else:
            break
    return events

def parse_urqmd_ascii_to_unified(file_path):
    events = []
    with open(file_path, 'r') as f:
        lines = f.readlines()
    current_event_particles = []
    start_line_index = next((i for i, line in enumerate(lines) if "event#" in line), -1)
    if start_line_index == -1: return []
    line_idx = start_line_index
    while line_idx < len(lines):
        line = lines[line_idx]
        if "event#" in line:
            if current_event_particles: events.append(np.array(current_event_particles))
            current_event_particles = []
            for j in range(line_idx + 1, len(lines)):
                parts = lines[j].split()
                if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                    particles_to_read = int(parts[0])
                    for k in range(j + 1, len(lines)):
                        if 'pvec:' in lines[k]:
                            data_start_index = k + 2
                            for l in range(data_start_index, data_start_index + particles_to_read):
                                if l < len(lines):
                                    p_parts = lines[l].split()
                                    if len(p_parts) >= 11:
                                        try:
                                            mass, charge = float(p_parts[8]), int(float(p_parts[11]))
                                            pid = get_pid_from_mass(mass, charge)
                                            current_event_particles.append([
                                                float(p_parts[4]),  # E
                                                float(p_parts[5]),  # px
                                                float(p_parts[6]),  # py
                                                float(p_parts[7]),  # pz
                                                pid,
                                                charge,
                                                mass
                                            ])
                                        except (ValueError, IndexError): continue
                            line_idx = data_start_index + particles_to_read - 1
                            break
                    break
        line_idx += 1
    if current_event_particles: events.append(np.array(current_event_particles))
    return events

def load_data(file_path, file_format):
    fmt = file_format.lower()
    if fmt == 'smash':
        with open(file_path, 'rb') as f:
            content = f.read()
        return parse_oscar2013_to_unified(content)
    elif fmt == 'urqmd':
        return parse_urqmd_ascii_to_unified(file_path)
    else:
        raise ValueError("Unsupported format. Use 'SMASH' or 'UrQMD'.")

def calculate_rapidity(E, pz):
    E = np.asarray(E)
    pz = np.asarray(pz)
    mask = E > np.abs(pz)
    rapidity = np.full_like(E, np.nan, dtype=np.float64)
    rapidity[mask] = 0.5 * np.log((E[mask] + pz[mask]) / (E[mask] - pz[mask]))
    return rapidity

def calculate_pseudorapidity(px, py, pz):
    px = np.asarray(px)
    py = np.asarray(py)
    pz = np.asarray(pz)
    ptot = np.sqrt(px**2 + py**2 + pz**2)
    eta = np.full_like(ptot, np.nan, dtype=np.float64)
    mask = ptot != np.abs(pz)
    eta[mask] = 0.5 * np.log((ptot[mask] + pz[mask]) / (ptot[mask] - pz[mask]))
    return eta

def main():
    parser = argparse.ArgumentParser(description="Analyze particle data and compute Q-vectors (optimized).")
    parser.add_argument('--mode', required=True, choices=['2D', '3D'], help="Analysis mode: 2D (rapidity) or 3D (pseudorapidity)")
    parser.add_argument('--format', required=True, help="Format of the data file (SMASH or UrQMD).")
    parser.add_argument('--file', help="Path to the input data file. If not provided, a default is used based on the format.")
    args = parser.parse_args()
    file_format = args.format.lower()
    if file_format not in ['smash', 'urqmd']:
        print(f"Error: Invalid format '{args.format}'. Please use 'SMASH' or 'UrQMD'.")
        return
    filename = args.file
    if filename is None:
        filename = 'particle_list_urqmd.dat' if file_format == 'urqmd' else 'particle_lists_SMASH.bin'
    print(f"Loading data from '{filename}' in {file_format} format...")
    events = load_data(filename, file_format)
    if not events:
        print("No events found or parsed. Exiting.")
        return
    print(f"Found {len(events)} events.")
    pids = [-3334, -3322, -3312, -3222, -3212, -3122, -3112, -2212, -2112, -321, -311, -211, 22, 111, 130, 211, 221, 311, 321, 2112, 2212, 3112, 3122, 3212, 3222, 3312, 3322, 3334]
    print(f"Using fixed PID list with {len(pids)} entries.")
    harmonics = [1, 2, 3]
    if args.mode == '2D':
        rapidity_range = (-0.5, 0.5)
        pt_bins = np.array([
            0.0,0.05,0.1,0.15,0.2,0.25,0.3,0.35,0.4,0.45,0.5,0.55,0.6,0.65,0.7,0.75,0.8,0.85,0.9,0.95,1.,1.05,1.1,1.15,1.2,1.25,1.3,1.35,1.4,1.45,1.5,1.55,1.6,1.65,1.7,1.75,1.8,1.85,1.9,1.95,2.,2.1,2.2,2.3,2.4,2.5,2.6,2.7,2.8,2.9,3.,3.2,3.4,3.6,3.8,4.,10.
        ])
        num_bins = len(pt_bins)
        particle_dtype = np.dtype([
            ('E', 'f8'),
            ('px', 'f8'),
            ('py', 'f8'),
            ('pz', 'f8'),
            ('pid', 'i4'),
            ('charge', 'i4'),
            ('mass', 'f8')
        ])
        print("Stacking all events into a single structured array...")
        all_particles = np.concatenate([np.array(event, dtype=particle_dtype) for event in events])
        q_values = np.zeros((len(pids), len(harmonics), num_bins), dtype='complex128')
        counts = np.zeros((len(pids), num_bins), dtype='int32')
        sum_pt = np.zeros((len(pids), num_bins), dtype='float64')
        print("Calculating Q-vectors (2D mode, rapidity, optimized, vectorized)...")
        E = all_particles['E']
        px = all_particles['px']
        py = all_particles['py']
        pz = all_particles['pz']
        pid_arr = all_particles['pid']
        rapidity = calculate_rapidity(E, pz)
        pt = np.sqrt(px**2 + py**2)
        phi = np.arctan2(py, px)
        for i, pid_val in enumerate(pids):
            mask = pid_arr == pid_val
            if not np.any(mask):
                continue
            rapid = rapidity[mask]
            pt_sel = pt[mask]
            phi_sel = phi[mask]
            valid = (rapid >= rapidity_range[0]) & (rapid <= rapidity_range[1])
            pt_valid = pt_sel[valid]
            phi_valid = phi_sel[valid]
            bin_indices = np.digitize(pt_valid, pt_bins) - 1
            for k in range(num_bins):
                in_bin = bin_indices == k
                if np.any(in_bin):
                    for j, h in enumerate(harmonics):
                        q_values[i, j, k] += np.sum(np.exp(1j * h * phi_valid[in_bin]))
                    counts[i, k] += np.sum(in_bin)
                    sum_pt[i, k] += np.sum(pt_valid[in_bin])
        mean_pt = np.divide(sum_pt, counts, out=np.zeros_like(sum_pt), where=counts>0)
        output_filename = filename + '.npz'
        np.savez(output_filename, q_vectors=q_values, counts=counts, mean_pt=mean_pt, pids=pids, pt_bins=pt_bins, num_events=len(events))
        print(f"\nAnalysis complete. Results saved to '{output_filename}' (2D mode, optimized)")
        print(f"  - Number of oversampled events: {len(events)}")
        print(f"  - 'q_vectors' array shape: {q_values.shape}")
        print(f"  - 'counts' array shape: {counts.shape}")
        print(f"  - 'mean_pt' array shape: {mean_pt.shape}")
        print(f"  - 'pids' array with {len(pids)} entries")
        print(f"  - 'pt_bins' array: {pt_bins}")
    elif args.mode == '3D':
        eta_bins = np.linspace(-5, 5, 101)
        pt_bins = np.array([
            0.0,0.05,0.1,0.15,0.2,0.25,0.3,0.35,0.4,0.45,0.5,0.55,0.6,0.65,0.7,0.75,0.8,0.85,0.9,0.95,1.,1.05,1.1,1.15,1.2,1.25,1.3,1.35,1.4,1.45,1.5,1.55,1.6,1.65,1.7,1.75,1.8,1.85,1.9,1.95,2.,2.1,2.2,2.3,2.4,2.5,2.6,2.7,2.8,2.9,3.,3.2,3.4,3.6,3.8,4.,10.
        ])
        num_eta_bins = len(eta_bins) - 1
        num_pt_bins = len(pt_bins)
        particle_dtype = np.dtype([
            ('E', 'f8'),
            ('px', 'f8'),
            ('py', 'f8'),
            ('pz', 'f8'),
            ('pid', 'i4'),
            ('charge', 'i4'),
            ('mass', 'f8')
        ])
        print("Stacking all events into a single structured array...")
        all_particles = np.concatenate([np.array(event, dtype=particle_dtype) for event in events])
        q_values = np.zeros((len(pids), len(harmonics), num_eta_bins, num_pt_bins), dtype='complex128')
        counts = np.zeros((len(pids), num_eta_bins, num_pt_bins), dtype='int32')
        sum_pt = np.zeros((len(pids), num_eta_bins, num_pt_bins), dtype='float64')
        print("Calculating Q-vectors (3D mode, pseudorapidity, optimized, vectorized)...")
        E = all_particles['E']
        px = all_particles['px']
        py = all_particles['py']
        pz = all_particles['pz']
        pid_arr = all_particles['pid']
        eta = calculate_pseudorapidity(px, py, pz)
        pt = np.sqrt(px**2 + py**2)
        phi = np.arctan2(py, px)
        eta_bin_indices = np.digitize(eta, eta_bins) - 1
        pt_bin_indices = np.digitize(pt, pt_bins) - 1
        for i, pid_val in enumerate(pids):
            mask = pid_arr == pid_val
            if not np.any(mask):
                continue
            eta_sel = eta[mask]
            pt_sel = pt[mask]
            phi_sel = phi[mask]
            eta_idx_arr = eta_bin_indices[mask]
            pt_idx_arr = pt_bin_indices[mask]
            for eta_idx in range(num_eta_bins):
                in_eta = eta_idx_arr == eta_idx
                pt_eta = pt_sel[in_eta]
                phi_eta = phi_sel[in_eta]
                pt_idx_eta = pt_idx_arr[in_eta]
                for k in range(num_pt_bins):
                    in_bin = pt_idx_eta == k
                    if np.any(in_bin):
                        for j, h in enumerate(harmonics):
                            q_values[i, j, eta_idx, k] += np.sum(np.exp(1j * h * phi_eta[in_bin]))
                        counts[i, eta_idx, k] += np.sum(in_bin)
                        sum_pt[i, eta_idx, k] += np.sum(pt_eta[in_bin])
        mean_pt = np.divide(sum_pt, counts, out=np.zeros_like(sum_pt), where=counts>0)
        output_filename = filename + '.npz'
        np.savez(output_filename, q_vectors=q_values, counts=counts, mean_pt=mean_pt, pids=pids, eta_bins=eta_bins, pt_bins=pt_bins, num_events=len(events))
        print(f"\nAnalysis complete. Results saved to '{output_filename}' (3D mode, optimized)")
        print(f"  - Number of oversampled events: {len(events)}")
        print(f"  - 'q_vectors' array shape: {q_values.shape}")
        print(f"  - 'counts' array shape: {counts.shape}")
        print(f"  - 'mean_pt' array shape: {mean_pt.shape}")
        print(f"  - 'pids' array with {len(pids)} entries")
        print(f"  - 'eta_bins' array: {eta_bins}")
        print(f"  - 'pt_bins' array: {pt_bins}")

if __name__ == "__main__":
    main()
