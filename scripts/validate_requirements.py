#!/usr/bin/env python3
"""Validate requirements.json schema completeness and internal consistency.

When completeness is confirmed the script exits 0; otherwise 1.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

from _version_profile import profile_for

# ---------------------------------------------------------------------------
# Required field paths (dotted notation) keyed by build phase.
# "always" = needed before dependency planning.
# "build"  = additionally needed before entity-build.sh generation.
# ---------------------------------------------------------------------------

REQUIRED_ALWAYS = [
    "entity.checkout_root",
    "entity.workdir",
]

REQUIRED_BUILD = [
    "compile.pgen",
    "environment.backend",
]

OPTIONAL_WITH_DEFAULTS = {
    "entity.dependency_profile": "auto-detect from entity.version_bucket",
    "environment.output": "true",
    "environment.mpi": "false",
    "environment.gpu_aware_mpi": "false",
    "compile.precision": "single",
    "compile.deposit": "zigzag",
    "compile.shape_order": "1",
    "compile.debug": "false",
    "compile.tests": "false",
    "compile.build_intent": "unspecified",
    "compile.cxx_standard": "profile-derived",
}

# Fields that must be consistent pairs — if both are set, the condition must hold.
CONSISTENCY_RULES = [
    # (rule_id, condition, field_pair, message)
    ("pgen.mutex", None, ("compile.pgen", "compile.pgens"),
     "compile.pgen and compile.pgens are mutually exclusive. Use one."),
    ("output.requires_adios2", None, ("environment.output", None),
     "environment.output=true requires ADIOS2 and HDF5 in the dependency plan."),
    ("cuda.requires_nvcc", ("environment.backend", "cuda"), ("compile.cxx_standard", None),
     "CUDA backend requires Kokkos nvcc_wrapper as CXX."),
    ("hip.requires_rocm", ("environment.backend", "hip"), ("compile.cxx_standard", None),
     "HIP backend requires ROCm/hipcc toolchain and HIP-aware Kokkos."),
]


def _get(obj: Dict[str, Any], dotted: str) -> Any:
    """Drill into *obj* using dotted path. Returns None when any key is missing."""
    cur: Any = obj
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def _has(obj: Dict[str, Any], dotted: str) -> bool:
    val = _get(obj, dotted)
    if val is None:
        return False
    if isinstance(val, str) and val == "":
        return False
    return True


def check_required(
    req: Dict[str, Any], fields: List[str], phase: str
) -> List[Dict[str, str]]:
    missing: List[Dict[str, str]] = []
    for path in fields:
        if not _has(req, path):
            missing.append({"field": path, "phase": phase})
    return missing


def check_consistency(req: Dict[str, Any]) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    for rule_id, condition, pair, msg in CONSISTENCY_RULES:
        if condition:
            cond_field, cond_val = condition
            actual = _get(req, cond_field)
            if actual is None or str(actual).lower() != cond_val:
                continue  # condition not met, skip

        field_a, field_b = pair
        val_a = _get(req, field_a)
        if field_b:
            val_b = _get(req, field_b)
            # For pgen mutex: both must not be set simultaneously
            if rule_id == "pgen.mutex" and val_a is not None and val_b is not None:
                issues.append({"rule": rule_id, "message": msg, "fields": [field_a, field_b]})
        else:
            # Single-field rule with a condition match — just warn if field not set
            if val_a is None or (isinstance(val_a, str) and val_a == ""):
                issues.append({"rule": rule_id, "message": msg, "fields": [field_a]})

    # Logical checks that require both fields present
    # output=true -> environment.output matches compile expectations
    env_output = _get(req, "environment.output")
    if env_output is True or str(env_output).lower() == "true":
        if not _has(req, "environment.dependency_policy"):
            issues.append({
                "rule": "output.policy",
                "message": "output=true: ensure dependency_policy covers ADIOS2 + HDF5.",
                "fields": ["environment.dependency_policy"],
            })

    return issues


def run_validation(req: Dict[str, Any]) -> Dict[str, Any]:
    always_missing = check_required(req, REQUIRED_ALWAYS, "always")
    build_missing = check_required(req, REQUIRED_BUILD, "build")
    missing_fields = always_missing + build_missing

    consistency_issues = check_consistency(req)

    status = "pass"
    if missing_fields:
        status = "fail"
    elif consistency_issues:
        status = "partial"

    return {
        "status": status,
        "missing_fields": missing_fields,
        "consistency_issues": consistency_issues,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("requirements_json", type=Path)
    args = parser.parse_args()

    if not args.requirements_json.exists():
        print(json.dumps({
            "status": "fail",
            "missing_fields": [{"field": "(file)", "phase": "always"}],
            "consistency_issues": [],
        }))
        raise SystemExit(1)

    with args.requirements_json.open("r", encoding="utf-8") as f:
        req = json.load(f)
    if not isinstance(req, dict):
        print(json.dumps({
            "status": "fail",
            "missing_fields": [],
            "consistency_issues": [{"rule": "schema", "message": "requirements.json must contain a JSON object"}],
        }))
        raise SystemExit(1)

    result = run_validation(req)
    print(json.dumps(result, indent=2, sort_keys=True))
    if result["status"] == "fail":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
