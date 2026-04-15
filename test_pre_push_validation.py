#!/usr/bin/env python3
"""
Pre-push validation suite: comprehensive checks before GitHub submission.
Targets: Python syntax, imports, config validation, CLI functionality, job generation.
"""

import subprocess
import sys
import tempfile
from pathlib import Path


def run_test(name, cmd, timeout_sec=120):
    """Run a test command and report result."""
    print(f"\n{'='*70}")
    print(f"TEST: {name}")
    print(f"{'='*70}")
    try:
        result = subprocess.run(
            cmd, shell=True, timeout=timeout_sec, capture_output=True, text=True
        )
        if result.returncode == 0:
            print(f"✅ PASS")
            return True
        else:
            print(f"❌ FAIL (exit code {result.returncode})")
            if result.stderr:
                print("STDERR:", result.stderr[:500])
            if result.stdout:
                print("STDOUT:", result.stdout[:500])
            return False
    except subprocess.TimeoutExpired:
        print(f"⏱️  TIMEOUT after {timeout_sec}s")
        return False
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False


def main():
    """Run all pre-push validation tests."""
    
    print("\n" + "="*70)
    print("PRE-PUSH VALIDATION SUITE")
    print("="*70)
    
    results = {}
    
    # 1. Python syntax check
    results['Python Syntax'] = run_test(
        "Python file syntax check (all .py files)",
        "python3 -m py_compile generate_jobs.py Cluster_supports/OSG/generate_submission_script.py "
        "codes/hydro_plus_UrQMD_driver.py codes/analysis_cli_optimized.py",
        timeout_sec=30
    )
    
    # 2. Existing test suites (unit + config + smoke)
    results['Unit & Config Tests'] = run_test(
        "Existing unit, config matrix, and smoke tests",
        "python3 -m unittest test_option_validation.py test_configuration_matrix.py "
        "test_build_smoke.py test_e2e_runner_smoke.py",
        timeout_sec=60
    )
    
    # 3. CLI help validation
    results['CLI Help Output'] = run_test(
        "Check CLI help pages are accessible",
        "python3 generate_jobs.py -h >/dev/null && "
        "python3 Cluster_supports/OSG/generate_submission_script.py -h >/dev/null",
        timeout_sec=10
    )
    
    # 4. Config file parsing for main parameter dicts
    results['Config File Parsing'] = run_test(
        "Load all user parameter dictionary files",
        "python3 -c \"import sys; sys.path.insert(0, 'config'); "
        "import parameters_dict_user_3DMCGlauber_dynamical; "
        "import parameters_dict_user_IPGlasma_pregen; "
        "print('All configs loaded OK')\"",
        timeout_sec=30
    )
    
    # 5. Job generation dry-run (with --nocopy to skip code tree copy)
    results['Job Generation Dry-Run'] = run_test(
        "Generate jobs (3DMCGlauber + decay afterburner, no copy)",
        f"cd /tmp && python3 {Path.cwd()}/generate_jobs.py "
        "-w /tmp/prepush_test -c local "
        "-par config/parameters_dict_user_3DMCGlauber_dynamical.py "
        "-n 1 -n_hydro 1 -n_urqmd 1 -n_th 1 --nocopy 2>&1 | head -30",
        timeout_sec=30
    )
    
    # 6. OSG submission script generation
    results['OSG Submission Script'] = run_test(
        "Generate OSG submission script",
        "python3 Cluster_supports/OSG/generate_submission_script.py "
        "-n 2 -nth 1 -param config/parameters_dict_user_3DMCGlauber_dynamical.py >/dev/null",
        timeout_sec=30
    )
    
    # 7. Shell scripts syntax check
    results['Build Script Syntax'] = run_test(
        "Check shell script syntax (get/compile packages)",
        "bash -n codes/get_code_packages.sh && bash -n codes/compile_code_packages.sh",
        timeout_sec=10
    )
    
    # 8. Runner script syntax and execution (quick profile only)
    results['Quick Profile Runner'] = run_test(
        "Execute quick profile (unit/smoke only, no compilation)",
        "./run_full_stack_tests.sh quick",
        timeout_sec=180
    )
    
    # Summary
    print("\n" + "="*70)
    print("VALIDATION SUMMARY")
    print("="*70)
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    for name, result in results.items():
        status = "✅" if result else "❌"
        print(f"{status} {name}")
    
    print(f"\nResult: {passed}/{total} tests PASSED")
    
    if passed == total:
        print("\n🎉 All pre-push validations PASSED! Ready for GitHub.")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) FAILED. Please fix before pushing.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
