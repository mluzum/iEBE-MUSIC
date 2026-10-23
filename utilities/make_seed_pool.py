#!/usr/bin/env python3
"""Generate a reproducible nucleon-seed pool for the legacy `file` seed source.

The upstream Isobar-Sampler ships `make_seeds.py`, but it draws from numpy's
*global* random state without seeding it, so two runs produce different pools.
That is fine for a throwaway pool and useless for anything that has to be
reproduced, which is why this script exists: it takes an explicit integer seed
and a counter-based bit generator, so the same arguments always yield a
byte-identical file.

The default `seed_source` is "philox" (see EMULATOR_SWEEP_PLAN.md, decision D2),
which needs no pool at all and is what the emulator sweep uses. This exists only
for the legacy path and for anyone who needs an on-disk pool.

Output layout matches what `build_isobars.py` expects: a single dataset named
`isobar_seeds` of shape (number_configs, number_nucleons, 6), where columns
0-2 are uniform on [0,1) for radius, cos(theta) and phi, and columns 3-5 are
standard normal for the Gaussian folding.

Usage:
    python3 utilities/make_seed_pool.py --output shared_seeds/nucleon-seeds.hdf \\
        --number-configs 10000 --number-nucleons 300 --seed 8675309

Verify a pool reproduces:
    python3 utilities/make_seed_pool.py ... --verify
"""

import argparse
import hashlib
import sys

import h5py
import numpy as np

# Counter stride per configuration, matching build_isobars.generate_seed_rows so
# that a pool and a philox draw share the same layout.
COUNTER_STRIDE = 1 << 24


def seed_rows(master_seed,
              number_configs,
              number_nucleons,
              stride=COUNTER_STRIDE):
    """Return (number_configs, number_nucleons, 6) float32 seed rows.

    Each configuration is a pure function of (master_seed, config_index): the
    bit generator is counter-based, so rows do not depend on call order or on
    how many rows were produced earlier.
    """
    rows = np.empty((number_configs, number_nucleons, 6), dtype=np.float32)
    for i in range(number_configs):
        gen = np.random.Generator(
            np.random.Philox(key=master_seed,
                             counter=np.uint64(i)*np.uint64(stride)))
        rows[i, :, :3] = gen.random((number_nucleons, 3))
        rows[i, :, 3:] = gen.standard_normal((number_nucleons, 3))
    return rows


def file_digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--output', required=True, help='output HDF5 path')
    parser.add_argument('--number-configs', type=int, required=True)
    parser.add_argument('--number-nucleons', type=int, required=True)
    parser.add_argument('--seed',
                        type=int,
                        required=True,
                        help='integer seed; the same seed always yields the '
                        'same file')
    parser.add_argument('--compression',
                        type=int,
                        default=9,
                        help='gzip level for the dataset (0-9, default 9)')
    parser.add_argument('--verify',
                        action='store_true',
                        help='after writing, re-generate in memory and confirm '
                        'the contents match, then print the sha256')
    args = parser.parse_args()

    if args.number_configs <= 0 or args.number_nucleons <= 0:
        parser.error('number-configs and number-nucleons must be positive')

    data = seed_rows(args.seed, args.number_configs, args.number_nucleons)

    with h5py.File(args.output, 'w') as f:
        dset = f.create_dataset('isobar_seeds',
                                data.shape,
                                compression="gzip",
                                compression_opts=args.compression)
        dset[:] = data

    print('wrote {}  shape={} dtype={}  seed={}'.format(args.output, data.shape,
                                                        data.dtype, args.seed))
    print('sha256({}) = {}'.format(args.output, file_digest(args.output)))

    if args.verify:
        again = seed_rows(args.seed, args.number_configs, args.number_nucleons)
        with h5py.File(args.output, 'r') as f:
            on_disk = f['isobar_seeds'][:]
        if not np.array_equal(on_disk, again):
            print('VERIFY FAILED: file does not match a fresh generation',
                  file=sys.stderr)
            return 1
        print('verify: OK, file is byte-reproducible from '
              '(seed={}, n_configs={}, n_nucleons={})'.format(
                  args.seed, args.number_configs, args.number_nucleons))
    return 0


if __name__ == '__main__':
    sys.exit(main())
