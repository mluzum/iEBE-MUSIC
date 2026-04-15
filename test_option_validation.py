#!/usr/bin/env python3
"""Unit tests for option/config validation helpers in generate_jobs.py."""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from generate_jobs import (
    normalize_model_choices,
    resolve_3dmcglauber_binary_path,
    resolve_isobar_seed_path,
    resolve_smash_binary_path,
    validate_runtime_requirements,
)


class ResolveIsobarSeedPathTests(unittest.TestCase):
    def _parameter_module(self, target_seed, projectile_seed):
        return SimpleNamespace(
            isobars_conf_dict_target={
                "isobar_samples": {
                    "seeds_file": {"filename": target_seed},
                }
            },
            isobars_conf_dict_projectile={
                "isobar_samples": {
                    "seeds_file": {"filename": projectile_seed},
                }
            },
        )

    def test_resolves_relative_seed_path_from_parameter_directory(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            seed_file = Path(tmp_dir) / "nucleon-seeds.hdf"
            seed_file.write_text("dummy", encoding="utf-8")

            parameter_module = self._parameter_module(
                "nucleon-seeds.hdf", "nucleon-seeds.hdf"
            )
            resolved = resolve_isobar_seed_path(parameter_module, tmp_dir)
            self.assertEqual(resolved, str(seed_file.resolve()))

    def test_mismatched_target_and_projectile_seed_filenames_raise(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            parameter_module = self._parameter_module(
                "target-seeds.hdf", "projectile-seeds.hdf"
            )
            with self.assertRaises(ValueError):
                resolve_isobar_seed_path(parameter_module, tmp_dir)

    def test_missing_seed_file_raises_file_not_found(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            parameter_module = self._parameter_module(
                "missing-seeds.hdf", "missing-seeds.hdf"
            )
            with self.assertRaises(FileNotFoundError):
                resolve_isobar_seed_path(parameter_module, tmp_dir)


class NormalizeModelChoicesTests(unittest.TestCase):
    def test_defaults_afterburner_to_urqmd(self):
        initial, afterburner = normalize_model_choices(
            {"initial_state_type": "3DMCGlauber_dynamical"}
        )
        self.assertEqual(initial, "3DMCGlauber_dynamical")
        self.assertEqual(afterburner, "urqmd")

    def test_normalizes_afterburner_case(self):
        _, afterburner = normalize_model_choices(
            {
                "initial_state_type": "TRENTo",
                "afterburner_type": "SMASH",
            }
        )
        self.assertEqual(afterburner, "smash")

    def test_invalid_initial_type_raises(self):
        with self.assertRaises(ValueError):
            normalize_model_choices(
                {
                    "initial_state_type": "InvalidModel",
                    "afterburner_type": "urqmd",
                }
            )

    def test_invalid_afterburner_type_raises(self):
        with self.assertRaises(ValueError):
            normalize_model_choices(
                {
                    "initial_state_type": "IPGlasma",
                    "afterburner_type": "BadBurner",
                }
            )


class RuntimeValidationTests(unittest.TestCase):
    def test_resolve_3dmcglauber_binary_prefers_installed_path(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            code_path = Path(tmp_dir)
            glauber_bin = code_path / "3dMCGlauber_code" / "3dMCGlb.e"
            glauber_bin.parent.mkdir(parents=True, exist_ok=True)
            glauber_bin.write_text("#!/bin/bash\n", encoding="utf-8")
            resolved = resolve_3dmcglauber_binary_path(str(code_path))
            self.assertEqual(resolved, str(glauber_bin))

    def test_resolve_smash_binary_prefers_packaged_path(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            code_path = Path(tmp_dir)
            smash_bin = code_path / "smash" / "smash"
            smash_bin.parent.mkdir(parents=True, exist_ok=True)
            smash_bin.write_text("#!/bin/bash\n", encoding="utf-8")
            resolved = resolve_smash_binary_path(str(code_path))
            self.assertEqual(resolved, str(smash_bin))

    def test_validate_runtime_requirements_smash_raises_without_binary(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            with self.assertRaises(FileNotFoundError):
                validate_runtime_requirements(
                    initial_condition_type="3DMCGlauber_dynamical",
                    afterburner_type="smash",
                    code_path=tmp_dir,
                    isobar_seed_file_path="",
                )

    def test_validate_runtime_requirements_3dmcglauber_requires_binary(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            with self.assertRaises(FileNotFoundError):
                validate_runtime_requirements(
                    initial_condition_type="3DMCGlauber_dynamical",
                    afterburner_type="decay",
                    code_path=tmp_dir,
                    isobar_seed_file_path="",
                    initial_condition_database="self",
                )

    def test_validate_runtime_requirements_urqmd_requires_files(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            code_path = Path(tmp_dir)
            (code_path / "osc2u").mkdir(parents=True, exist_ok=True)
            (code_path / "urqmd").mkdir(parents=True, exist_ok=True)
            (code_path / "urqmd_code" / "urqmd").mkdir(parents=True, exist_ok=True)
            (code_path / "osc2u" / "osc2u.e").write_text("", encoding="utf-8")
            (code_path / "urqmd" / "runqmd.sh").write_text("", encoding="utf-8")
            (code_path / "urqmd" / "uqmd.burner").write_text("", encoding="utf-8")
            (code_path / "urqmd_code" / "urqmd" / "urqmd.e").write_text("", encoding="utf-8")

            validate_runtime_requirements(
                initial_condition_type="3DMCGlauber_dynamical",
                afterburner_type="urqmd",
                code_path=str(code_path),
                isobar_seed_file_path="",
            )


if __name__ == "__main__":
    unittest.main()
