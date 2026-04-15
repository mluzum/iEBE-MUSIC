#!/usr/bin/env python3
"""Configuration matrix tests for model/afterburner selection logic."""

import tempfile
import unittest
from pathlib import Path

from generate_jobs import normalize_model_choices, validate_runtime_requirements


KNOWN_INITIAL_TYPES = [
    "IPGlasma",
    "IPGlasma+KoMPoST",
    "3DMCGlauber_dynamical",
    "3DMCGlauber_participants",
    "3DMCGlauber_consttau",
    "TRENTo",
]

KNOWN_AFTERBURNERS = ["urqmd", "decay", "smash"]


class ConfigurationMatrixTests(unittest.TestCase):
    def test_all_known_initial_and_afterburner_combinations_normalize(self):
        for initial in KNOWN_INITIAL_TYPES:
            for afterburner in KNOWN_AFTERBURNERS:
                normalized_initial, normalized_afterburner = normalize_model_choices(
                    {
                        "initial_state_type": initial,
                        "afterburner_type": afterburner,
                    }
                )
                self.assertEqual(normalized_initial, initial)
                self.assertEqual(normalized_afterburner, afterburner)

    def test_trento_requires_seed_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            with self.assertRaises(FileNotFoundError):
                validate_runtime_requirements(
                    initial_condition_type="TRENTo",
                    afterburner_type="decay",
                    code_path=tmp_dir,
                    isobar_seed_file_path="",
                )

    def test_decay_has_no_extra_runtime_binary_requirement(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Decay path should not require UrQMD/SMASH runtime assets.
            validate_runtime_requirements(
                initial_condition_type="3DMCGlauber_dynamical",
                afterburner_type="decay",
                code_path=tmp_dir,
                isobar_seed_file_path="",
            )

    def test_trento_with_seed_and_binaries_passes(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            seed = base / "seeds.hdf"
            seed.write_text("dummy", encoding="utf-8")

            (base / "isobar_sampler_code" / "exec").mkdir(parents=True, exist_ok=True)
            (base / "trento_code" / "build" / "src").mkdir(parents=True, exist_ok=True)
            (base / "isobar_sampler_code" / "exec" / "build_isobars.py").write_text("", encoding="utf-8")
            (base / "trento_code" / "build" / "src" / "trento").write_text("", encoding="utf-8")

            validate_runtime_requirements(
                initial_condition_type="TRENTo",
                afterburner_type="decay",
                code_path=str(base),
                isobar_seed_file_path=str(seed),
            )


if __name__ == "__main__":
    unittest.main()
